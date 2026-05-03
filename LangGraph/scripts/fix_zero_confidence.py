"""
Re-extract temporal metadata for docs that have extraction_confidence=0.

These docs have temporal_metadata rows but the extraction silently failed
(usually because the LLM/embedding endpoint was unreachable during indexing).

Usage:
    cd LangGraph
    source ../.venv/bin/activate
    python scripts/fix_zero_confidence.py [--dry-run] [--limit N] [--content-only]

Options:
    --dry-run       Show what would happen without writing to DB
    --limit N       Process only first N docs
    --content-only  Use content_summary from postgres instead of re-running OCR
                    (faster, less accurate for PDFs — good for testing)
"""

import asyncio
import argparse
import os
import sys
import re
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import psycopg2
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

FIRECRAWL_DATA = Path(__file__).parent.parent.parent / "firecrawl" / "data"
OCR_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "DeepSeek-OCR"


def get_pg_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5433")),
        database=os.getenv("POSTGRES_DATABASE", os.getenv("POSTGRES_DB", "lightrag")),
        user=os.getenv("POSTGRES_USER", "uitrag"),
        password=os.getenv("POSTGRES_PASSWORD", "admin123"),
    )


def get_zero_confidence_docs(limit=None):
    """Return (doc_id, track_id, file_path, content_summary) for conf=0 processed docs."""
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            q = """
                SELECT tm.doc_id, tm.track_id, lds.file_path, lds.content_summary
                FROM temporal_metadata tm
                JOIN lightrag_doc_status lds ON tm.doc_id = lds.id
                WHERE tm.extraction_confidence = 0
                  AND lds.status = 'processed'
                ORDER BY lds.created_at
            """
            if limit:
                q += f" LIMIT {limit}"
            cur.execute(q)
            return cur.fetchall()
    finally:
        conn.close()


def find_pdf(file_path: str):
    """Resolve a file_path to an absolute disk path."""
    from urllib.parse import unquote
    filename = unquote(Path(file_path).name)
    for pdf in FIRECRAWL_DATA.rglob("*.pdf"):
        if pdf.name == filename:
            return pdf
    filename_space = filename.replace("%20", " ")
    for pdf in FIRECRAWL_DATA.rglob("*.pdf"):
        if pdf.name == filename_space:
            return pdf
    stem_stripped = re.sub(r'_\d{3}(\.pdf)$', r'\1', filename, flags=re.IGNORECASE)
    if stem_stripped != filename:
        for pdf in FIRECRAWL_DATA.rglob("*.pdf"):
            if pdf.name == stem_stripped:
                return pdf
    return None


def extract_text_pypdf(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception as e:
        print(f"  [pypdf] {e}")
        return ""


def update_row(doc_id: str, track_id: str, metadata: dict):
    conn = get_pg_connection()
    try:
        import json as _json
        known = {"document_number", "document_type", "valid_from", "valid_until",
                 "cohort_years", "cohort_scope", "student_cohorts", "amends_documents",
                 "extraction_method", "extraction_confidence"}
        extra = {k: v for k, v in metadata.items() if k not in known}

        def to_json(v):
            return _json.dumps(v) if v is not None else None

        with conn.cursor() as cur:
            cur.execute("""
                UPDATE temporal_metadata SET
                    document_number       = %s,
                    document_type         = %s,
                    valid_from            = %s,
                    valid_until           = %s,
                    cohort_years          = %s,
                    cohort_scope          = %s,
                    student_cohorts       = %s,
                    amends_documents      = %s,
                    extraction_method     = %s,
                    extraction_confidence = %s,
                    extraction_timestamp  = CURRENT_TIMESTAMP,
                    additional_metadata   = %s,
                    updated_at            = CURRENT_TIMESTAMP
                WHERE doc_id = %s
            """, (
                metadata.get("document_number"),
                metadata.get("document_type"),
                metadata.get("valid_from") or None,
                metadata.get("valid_until") or None,
                to_json(metadata.get("cohort_years")),
                metadata.get("cohort_scope"),
                to_json(metadata.get("student_cohorts")),
                to_json(metadata.get("amends_documents")),
                metadata.get("extraction_method", "rag_backfill"),
                metadata.get("extraction_confidence", 0.0),
                to_json(extra) if extra else None,
                doc_id,
            ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"  [DB] {e}")
        return False
    finally:
        conn.close()


async def run_rag(doc_text: str, doc_id: str, file_source: str):
    """
    Two-stage extraction matching the production indexing pipeline:
    Stage 1 — header extraction (document_number, amends_documents)
    Stage 2 — RAG subgraph (cohort_years, valid_dates)
    """
    try:
        from agent.agents.header_extraction import extract_from_header
        from agent.graphs.metadata_rag_subgraph import metadata_rag_subgraph

        # Stage 1: header
        header = extract_from_header(doc_text, file_source)

        # Stage 2: RAG for dates + cohorts
        rag_result = await metadata_rag_subgraph.ainvoke({
            "doc_text": doc_text, "file_source": file_source,
            "doc_id": doc_id, "success": False,
        })

        rag_ok = rag_result.get("success") and rag_result.get("extraction_confidence", 0) > 0
        rag_meta = rag_result.get("final_metadata", {}) if rag_ok else {}
        rag_conf = rag_result.get("extraction_confidence", 0.0) if rag_ok else 0.0

        # Merge: header wins for doc_number/amends, RAG for everything else
        merged: dict = dict(rag_meta)
        if header.get("document_number"):
            merged["document_number"] = header["document_number"]
        merged["amends_documents"] = header.get("amends_documents", [])
        merged["amendment_confidence"] = header.get("amendment_confidence", "none")
        merged["implicit_amendment_flag"] = header.get("implicit_amendment_flag", False)

        header_method = header.get("extraction_method_header", "header_regex_only")
        merged["extraction_method"] = f"{header_method}+rag_backfill"
        merged["extraction_confidence"] = rag_conf

        # Only return if we got at least a document_number
        if merged.get("document_number") or rag_ok:
            return merged
        return None

    except Exception as e:
        print(f"  [Header+RAG] {e}")
        return None


def run_regex(doc_text: str):
    try:
        from agent.agents.agent_temporal_extraction import TemporalMetadataExtractor
        extractor = TemporalMetadataExtractor()
        result = extractor.extract(doc_text)
        if result and result.get("document_number"):
            result.setdefault("extraction_method", "regex_backfill")
            result.setdefault("extraction_confidence", 0.5)
            return result
        return None
    except Exception as e:
        print(f"  [Regex] {e}")
        return None


async def process(doc_id, track_id, file_path, content_summary, dry_run, content_only):
    # Step 1: get full text
    doc_text = ""
    source = "?"
    if not content_only:
        disk_path = find_pdf(file_path or "")
        if disk_path:
            try:
                from agent.clients.mineru_ocr_client import MinerUOCRClient
                client = MinerUOCRClient()
                result = client.parse_pdf(str(disk_path))
                doc_text = result.get("text", "") if isinstance(result, dict) else str(result)
                source = f"mineru:{disk_path.name}"
            except Exception:
                pass
            if not doc_text or len(doc_text.strip()) < 100:
                doc_text = extract_text_pypdf(disk_path)
                source = f"pypdf:{disk_path.name}"

    if not doc_text or len(doc_text.strip()) < 50:
        # Fall back to content_summary
        doc_text = content_summary or ""
        source = "content_summary"

    if not doc_text or len(doc_text.strip()) < 20:
        return "skip:no_text"

    print(f"  text={len(doc_text)}c via {source}", end=" ")

    # Step 2: try RAG then regex
    metadata = await run_rag(doc_text, doc_id, file_path or doc_id)
    method = "rag"
    if not metadata:
        metadata = run_regex(doc_text)
        method = "regex"

    if not metadata:
        return "fail:no_extraction"

    doc_num = metadata.get("document_number", "")
    conf = metadata.get("extraction_confidence", 0)
    print(f"-> [{method}] doc_num={doc_num!r} conf={conf:.2f}", end=" ")

    if dry_run:
        return f"dry_run:{method}"

    ok = update_row(doc_id, track_id or "", metadata)
    return f"{'ok' if ok else 'db_error'}:{method}"


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--content-only", action="store_true",
                        help="Skip OCR, use content_summary from postgres (fast but less accurate)")
    args = parser.parse_args()

    print("=== Fix Zero-Confidence Temporal Metadata ===")
    docs = get_zero_confidence_docs(args.limit)
    print(f"Found {len(docs)} conf=0 docs to process")
    if args.dry_run:
        print("DRY RUN — no DB writes")
    if args.content_only:
        print("CONTENT-ONLY mode — using content_summary, no OCR")
    print()

    counts = {}
    t0 = time.time()

    for i, (doc_id, track_id, file_path, content_summary) in enumerate(docs, 1):
        print(f"[{i:3d}/{len(docs)}] {doc_id[:20]}...", end=" ")
        status = await process(doc_id, track_id, file_path, content_summary,
                               args.dry_run, args.content_only)
        print(f"=> {status}")
        counts[status.split(":")[0]] = counts.get(status.split(":")[0], 0) + 1
        await asyncio.sleep(0.3)

    print(f"\n=== Done in {time.time()-t0:.1f}s ===")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
