"""
Backfill temporal metadata for docs that have none.

Content priority:
  1. lightrag_doc_full table (already cleaned/OCR'd text)
  2. MinerU2.5_final_cleaned directory (OCR .md files)

Uses metadata_rag_subgraph (RAG-based, ~0.84 conf) not legacy regex agent.
"""

import asyncio
import os
import argparse
import psycopg2
import json
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Load env before importing agent modules
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from agent.graphs.metadata_rag_subgraph import metadata_rag_subgraph
from agent.clients.lightrag_client import LightRAGAPIClient

OCR_DIR = Path("/Users/jajajou1778/UIT_DOCS_AGENT/data/MinerU2.5_final_cleaned")
WORKSPACE = os.getenv("WORKSPACE", "uit_docs_agent")


def get_pg_connection():
    return psycopg2.connect(
        host="localhost",
        port=5433,
        user=os.getenv("POSTGRES_USER", "uitrag"),
        password=os.getenv("POSTGRES_PASSWORD", "admin123"),
        dbname="lightrag",
    )


def find_ocr_file(file_path: str) -> Path | None:
    """Match file_path URL basename to OCR dir (prefix match, ignores hash suffix)."""
    if not file_path:
        return None
    basename = Path(file_path).stem  # e.g. "172-qd-dhcntt_08-3-2023_quy_che_van_bang_chung_chi"
    for entry in OCR_DIR.iterdir():
        if entry.is_dir():
            dir_name = entry.name
            # Dir name = "<basename>-<8char_hash>" or exact match
            if dir_name == basename or dir_name.startswith(basename + "-"):
                md_file = entry / f"{dir_name}.md"
                if md_file.exists():
                    return md_file
    return None


def fetch_missing_docs(conn, force: bool = False, skip_confident: bool = False) -> list[tuple]:
    """Return (doc_id, file_path, track_id, content) for target docs.

    force=False (default): only docs with no temporal_metadata row.
    force=True: all docs.
    force=True + skip_confident=True: all docs except those with extraction_confidence >= 0.84
      (protects manually-patched high-quality rows).
    """
    with conn.cursor() as cur:
        if not force:
            cur.execute("""
                SELECT s.id, s.file_path, s.track_id, f.content
                FROM lightrag_doc_status s
                JOIN lightrag_doc_full f ON s.id = f.id AND f.workspace = s.workspace
                LEFT JOIN temporal_metadata t ON s.id = t.doc_id AND t.workspace = s.workspace
                WHERE s.workspace = %s
                  AND t.doc_id IS NULL
                  AND LENGTH(f.content) > 200
                ORDER BY s.created_at
            """, (WORKSPACE,))
        elif skip_confident:
            # Re-extract all except high-confidence rows (manually patched)
            cur.execute("""
                SELECT s.id, s.file_path, s.track_id, f.content
                FROM lightrag_doc_status s
                JOIN lightrag_doc_full f ON s.id = f.id AND f.workspace = s.workspace
                LEFT JOIN temporal_metadata t ON s.id = t.doc_id AND t.workspace = s.workspace
                WHERE s.workspace = %s
                  AND LENGTH(f.content) > 200
                  AND (t.doc_id IS NULL OR COALESCE(t.extraction_confidence, 0) < 0.84)
                ORDER BY s.created_at
            """, (WORKSPACE,))
        else:
            # Force all — overwrites everything including manual patches
            cur.execute("""
                SELECT s.id, s.file_path, s.track_id, f.content
                FROM lightrag_doc_status s
                JOIN lightrag_doc_full f ON s.id = f.id AND f.workspace = s.workspace
                WHERE s.workspace = %s
                  AND LENGTH(f.content) > 200
                ORDER BY s.created_at
            """, (WORKSPACE,))
        return cur.fetchall()


async def process_doc(
    doc_id: str,
    file_path: str,
    track_id: str,
    pg_content: str,
    client: LightRAGAPIClient,
    dry_run: bool,
    semaphore: asyncio.Semaphore,
) -> dict:
    async with semaphore:
        # Resolve content: PG primary, OCR fallback
        content = pg_content
        content_source = "lightrag_doc_full"

        if not content or len(content) < 200:
            ocr_file = find_ocr_file(file_path)
            if ocr_file:
                content = ocr_file.read_text(encoding="utf-8")
                content_source = f"ocr:{ocr_file}"
            else:
                print(f"  [SKIP] {doc_id} — no usable content")
                return {"doc_id": doc_id, "status": "skipped", "reason": "no_content"}

        print(f"  [PROC] {doc_id} | src={content_source} | len={len(content)}")

        try:
            t0 = time.monotonic()
            state = {
                "doc_text": content,
                "file_source": file_path or "",
                "doc_id": doc_id,
            }
            result = await metadata_rag_subgraph.ainvoke(state)
            elapsed = time.monotonic() - t0
            metadata = result.get("final_metadata") or result.get("document_metadata") or {}

            if not metadata:
                print(f"  [WARN] {doc_id} — subgraph returned empty metadata")
                return {"doc_id": doc_id, "status": "empty_metadata"}

            conf = metadata.get("temporal_confidence") or metadata.get("extraction_confidence") or 0.0
            docnum = metadata.get("document_number", "")
            print(f"  [META] {doc_id} | doc_num={docnum} | conf={conf:.3f} | elapsed={elapsed:.1f}s")

            if dry_run:
                print(f"  [DRY] {json.dumps(metadata, ensure_ascii=False, indent=2)}")
                return {"doc_id": doc_id, "status": "dry_run", "metadata": metadata}

            # Map subgraph output fields → save_temporal_metadata expected fields
            save_payload = {
                "document_number": metadata.get("document_number"),
                "document_type": metadata.get("document_type"),
                "valid_from": metadata.get("valid_from"),
                "valid_until": metadata.get("valid_until"),
                "cohort_years": metadata.get("cohort_years", []),
                "cohort_scope": metadata.get("cohort_scope", "unspecified"),
                "student_cohorts": metadata.get("student_cohorts"),
                "amends_documents": metadata.get("amends_documents", []),
                "amended_clauses": metadata.get("amended_clauses"),
                "education_system": metadata.get("education_system"),
                "extraction_method": "metadata_rag_subgraph",
                "extraction_confidence": conf,
            }

            res = client.save_temporal_metadata(
                track_id=track_id or "",
                doc_id=doc_id,
                metadata=save_payload,
            )

            if res.get("success"):
                print(f"  [OK]   {doc_id} saved (id={res.get('id')})")
                return {"doc_id": doc_id, "status": "ok"}
            else:
                print(f"  [ERR]  {doc_id} save failed: {res.get('error')}")
                return {"doc_id": doc_id, "status": "error", "error": res.get("error")}

        except Exception as exc:
            import traceback
            print(f"  [EXC]  {doc_id}: {exc}")
            traceback.print_exc()
            return {"doc_id": doc_id, "status": "exception", "error": str(exc)}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="No DB writes, print extracted metadata")
    parser.add_argument("--limit", type=int, default=None, help="Process only first N docs")
    parser.add_argument("--workers", type=int, default=3, help="Parallel workers (default 3)")
    parser.add_argument("--force", action="store_true", help="Re-extract ALL docs, not just missing ones")
    parser.add_argument("--skip-confident", action="store_true", help="With --force: skip rows with confidence>=0.84 (protects manual patches)")
    parser.add_argument("--skip-amendment-links", action="store_true", help="Skip backfilling amendment reverse links after run")
    args = parser.parse_args()

    conn = get_pg_connection()
    docs = fetch_missing_docs(conn, force=args.force, skip_confident=args.skip_confident)
    conn.close()

    if args.limit:
        docs = docs[: args.limit]

    total = len(docs)
    print(f"Found {total} docs missing temporal metadata. workers={args.workers} dry_run={args.dry_run}")

    client = LightRAGAPIClient()
    semaphore = asyncio.Semaphore(args.workers)

    tasks = [
        process_doc(doc_id, file_path, track_id, content, client, args.dry_run, semaphore)
        for doc_id, file_path, track_id, content in docs
    ]
    results = await asyncio.gather(*tasks)

    ok = sum(1 for r in results if r["status"] == "ok")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors = sum(1 for r in results if r["status"] in ("error", "exception"))
    dry = sum(1 for r in results if r["status"] == "dry_run")

    print(f"\n=== DONE: ok={ok} dry={dry} skipped={skipped} errors={errors} / total={total} ===")

    if not args.dry_run and not args.skip_amendment_links and ok > 0:
        print("\nBackfilling amendment reverse links (amended_by_documents)...")
        try:
            link_res = client.backfill_amendment_links()
            print(f"Amendment links: {json.dumps(link_res, ensure_ascii=False)}")
        except Exception as exc:
            print(f"ERROR backfilling amendment links: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
