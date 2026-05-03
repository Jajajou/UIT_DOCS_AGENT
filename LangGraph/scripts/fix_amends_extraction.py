"""
Re-extract document_number and amends_documents using header-based extraction
for all processed docs where amends_documents is empty or null.

This is the targeted backfill for the header_extraction.py improvement.
It does NOT re-run the full RAG pipeline (slow) — only runs the fast
header extraction (first 2000 chars → LLM + regex) and patches just
document_number and amends_documents in the DB, leaving cohort_years,
valid_dates, and confidence untouched.

Usage:
    cd LangGraph
    python scripts/fix_amends_extraction.py [--dry-run] [--limit N] [--content-only]
    python scripts/fix_amends_extraction.py --only-missing-doc-num  # also fix null doc_numbers

Options:
    --dry-run              Show what would happen without writing to DB
    --limit N              Process only first N docs
    --content-only         Use content_summary from postgres (no OCR, fast)
    --only-missing-doc-num Also include docs with null document_number (not just empty amends)
    --min-confidence F     Only process docs with confidence >= F (default 0.0 = all)
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


def get_pg_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5433")),
        database=os.getenv("POSTGRES_DATABASE", os.getenv("POSTGRES_DB", "lightrag")),
        user=os.getenv("POSTGRES_USER", "uitrag"),
        password=os.getenv("POSTGRES_PASSWORD", "admin123"),
    )


def get_target_docs(limit=None, only_missing_doc_num=False, min_confidence=0.0):
    """
    Return docs that need amends re-extraction.

    Target criteria:
    - status = 'processed'
    - amends_documents IS NULL or = '[]'
    - optionally: also include document_number IS NULL
    - optionally: filter by min_confidence
    """
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            if only_missing_doc_num:
                where = """
                    (
                        tm.amends_documents IS NULL
                        OR tm.amends_documents::text IN ('[]', 'null', '')
                        OR tm.document_number IS NULL
                        OR tm.document_number = ''
                    )
                """
            else:
                where = """
                    (
                        tm.amends_documents IS NULL
                        OR tm.amends_documents::text IN ('[]', 'null', '')
                    )
                """

            q = f"""
                SELECT tm.doc_id, tm.track_id, lds.file_path, lds.content_summary,
                       tm.extraction_confidence, tm.document_number
                FROM temporal_metadata tm
                JOIN lightrag_doc_status lds ON tm.doc_id = lds.id
                WHERE lds.status = 'processed'
                  AND tm.extraction_confidence >= {min_confidence}
                  AND {where}
                ORDER BY tm.extraction_confidence DESC, lds.created_at
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


def patch_row(doc_id: str, patch: dict) -> bool:
    """
    Update only document_number, amends_documents, amendment_confidence,
    implicit_amendment_flag, extraction_method in temporal_metadata.
    Does NOT touch cohort_years, valid_dates, or extraction_confidence.
    """
    conn = get_pg_connection()
    try:
        import json as _json

        def to_json(v):
            return _json.dumps(v) if v is not None else None

        # Build dynamic SET clause — only patch fields that are present
        set_parts = []
        params = []

        if "document_number" in patch:
            set_parts.append("document_number = %s")
            params.append(patch["document_number"])

        if "amends_documents" in patch:
            set_parts.append("amends_documents = %s")
            params.append(to_json(patch["amends_documents"]))

        # Store amendment_confidence and implicit_amendment_flag in additional_metadata
        extra = {}
        if "amendment_confidence" in patch:
            extra["amendment_confidence"] = patch["amendment_confidence"]
        if "implicit_amendment_flag" in patch:
            extra["implicit_amendment_flag"] = patch["implicit_amendment_flag"]
        if "extraction_method_header" in patch:
            extra["extraction_method_header"] = patch["extraction_method_header"]

        if extra:
            # Merge with existing additional_metadata (JSONB coalesce)
            set_parts.append(
                "additional_metadata = COALESCE(additional_metadata, '{}'::jsonb) || %s::jsonb"
            )
            params.append(_json.dumps(extra))

        set_parts.append("updated_at = CURRENT_TIMESTAMP")

        if not set_parts:
            return True  # Nothing to update

        params.append(doc_id)
        sql = f"UPDATE temporal_metadata SET {', '.join(set_parts)} WHERE doc_id = %s"

        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"  [DB] {e}")
        return False
    finally:
        conn.close()


def process_doc(doc_id, track_id, file_path, content_summary, existing_doc_num,
                dry_run, content_only):
    """Synchronous per-doc processing — header extraction only, no RAG."""
    from agent.agents.header_extraction import extract_from_header

    # 1. Get text
    doc_text = ""
    source = "?"

    if not content_only and file_path:
        disk_path = find_pdf(file_path)
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
        doc_text = content_summary or ""
        source = "content_summary"

    if not doc_text or len(doc_text.strip()) < 20:
        return "skip:no_text", {}

    print(f"  text={len(doc_text)}c via {source}", end=" ")

    # 2. Header extraction (fast — no embedding, no rerank)
    result = extract_from_header(doc_text, file_path or doc_id)

    doc_num = result.get("document_number")
    amends = result.get("amends_documents", [])
    amend_conf = result.get("amendment_confidence", "none")
    implicit = result.get("implicit_amendment_flag", False)
    method = result.get("extraction_method_header", "header_regex_only")

    print(
        f"-> doc_num={doc_num!r} amends={amends} "
        f"amend_conf={amend_conf} implicit={implicit} via {method}",
        end=" "
    )

    # Build patch — only overwrite doc_number if we found one and the existing is null
    patch = {
        "amends_documents": amends,
        "amendment_confidence": amend_conf,
        "implicit_amendment_flag": implicit,
        "extraction_method_header": method,
    }
    if doc_num and not existing_doc_num:
        patch["document_number"] = doc_num

    if dry_run:
        return f"dry_run:{method}", patch

    ok = patch_row(doc_id, patch)
    return f"{'ok' if ok else 'db_error'}:{method}", patch


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--content-only", action="store_true",
                        help="Skip OCR, use content_summary from postgres")
    parser.add_argument("--only-missing-doc-num", action="store_true",
                        help="Also target docs with null document_number")
    parser.add_argument("--min-confidence", type=float, default=0.0,
                        help="Only process docs with confidence >= this value")
    args = parser.parse_args()

    print("=== Fix Amends Extraction (Header-Based) ===")
    docs = get_target_docs(
        limit=args.limit,
        only_missing_doc_num=args.only_missing_doc_num,
        min_confidence=args.min_confidence,
    )
    print(f"Found {len(docs)} docs with empty amends_documents to process")
    if args.dry_run:
        print("DRY RUN — no DB writes")
    if args.content_only:
        print("CONTENT-ONLY mode — using content_summary, no OCR")
    print()

    counts: dict[str, int] = {}
    found_amends = 0
    found_implicit = 0
    t0 = time.time()

    for row in docs:
        doc_id, track_id, file_path, content_summary, conf, existing_doc_num = row
        fname = Path(file_path).name if file_path else doc_id[:16]
        print(f"[{fname}] conf={conf:.2f} existing_num={existing_doc_num!r}", end=" ")

        status, patch = process_doc(
            doc_id, track_id, file_path, content_summary, existing_doc_num,
            dry_run=args.dry_run,
            content_only=args.content_only,
        )

        counts[status] = counts.get(status, 0) + 1
        amends = patch.get("amends_documents", [])
        if amends:
            found_amends += 1
        if patch.get("implicit_amendment_flag"):
            found_implicit += 1

        print(f"[{status}]")

    elapsed = time.time() - t0
    print(f"\n=== Done in {elapsed:.1f}s ===")
    print(f"Results: {counts}")
    print(f"Docs with explicit amends found: {found_amends}/{len(docs)}")
    print(f"Docs with implicit amendment flag: {found_implicit}/{len(docs)}")


if __name__ == "__main__":
    asyncio.run(main())
