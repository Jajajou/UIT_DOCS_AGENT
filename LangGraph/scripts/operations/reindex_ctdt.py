#!/usr/bin/env python3
"""
Delete CTDT curriculum docs from LightRAG and re-upload with OCR v2.

Steps:
  1. Find all CTDT_*_khoa* doc IDs in PostgreSQL
  2. Delete them from LightRAG via API (cleans PG, Qdrant, graph)
  3. Clear their OCR cache directories
  4. Invalidate their checkpoint entries so script.py re-uploads
  5. Re-upload via LangGraph indexing pipeline

Usage:
    source .venv/bin/activate
    python reindex_ctdt.py [--dry-run] [--skip-delete]
"""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

import psycopg2
import requests
from langgraph_sdk import get_sync_client
from tqdm import tqdm

# --- Config ---
PROJECT_ROOT = Path(__file__).parent
PG_CONN = dict(host="localhost", port=5433, database="lightrag", user="uitrag", password="admin123")
LIGHTRAG_URL = "http://localhost:9622"
LIGHTRAG_USER = "uit"
LIGHTRAG_PASS = "admin123"
LANGGRAPH_URL = "http://localhost:2024"
WORKSPACE = "uit_docs_agent"
OCR_CACHE_DIR = PROJECT_ROOT / "data" / "DeepSeek-OCR"
CHECKPOINT_FILE = PROJECT_ROOT / ".upload_checkpoint.jsonl"
CTDT_PDF_DIR = PROJECT_ROOT / "firecrawl" / "data" / "daa" / "chuongtrinh_daotao" / "he-chinhquy" / "ctdt-cu" / "pdf"


def get_lightrag_token() -> str:
    resp = requests.post(
        f"{LIGHTRAG_URL}/login",
        data={"username": LIGHTRAG_USER, "password": LIGHTRAG_PASS},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_ctdt_docs() -> list[dict]:
    """Get CTDT curriculum doc IDs - only the actual CTDT_*_khoa* files."""
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor()
    cur.execute("""
        SELECT f.id, f.doc_name
        FROM lightrag_doc_full f
        WHERE f.workspace = %s
          AND (
            f.doc_name SIMILAR TO '%%CTDT_[A-Z]%%khoa%%'
            OR f.doc_name SIMILAR TO '%%CTDT_[A-Z]%%khoa%%'
            OR f.doc_name ILIKE '%%/CTDT_%%khoa%%'
          )
        ORDER BY f.doc_name
    """, (WORKSPACE,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"doc_id": r[0], "doc_name": r[1]} for r in rows]


def delete_from_lightrag(doc_ids: list[str], token: str, dry_run: bool) -> None:
    print(f"\n[1/4] Deleting {len(doc_ids)} docs from LightRAG...")
    if dry_run:
        for d in doc_ids:
            print(f"  [DRY] Would delete: {d}")
        return

    # Delete in batches of 10
    batch_size = 10
    for i in range(0, len(doc_ids), batch_size):
        batch = doc_ids[i:i + batch_size]
        resp = requests.delete(
            f"{LIGHTRAG_URL}/documents",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"doc_ids": batch},
        )
        resp.raise_for_status()
        result = resp.json()
        print(f"  Batch {i//batch_size + 1}: {result.get('message', result)}")


def delete_temporal_metadata(doc_ids: list[str], dry_run: bool) -> None:
    print(f"\n[2/4] Cleaning temporal_metadata for {len(doc_ids)} docs...")
    if dry_run:
        print("  [DRY] Would delete from temporal_metadata")
        return
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor()
    cur.execute("DELETE FROM temporal_metadata WHERE doc_id = ANY(%s)", (doc_ids,))
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    print(f"  Deleted {deleted} rows from temporal_metadata")


def clear_ocr_cache(doc_names: list[str], dry_run: bool) -> None:
    print(f"\n[3/4] Clearing OCR cache for CTDT files...")
    cleared = 0
    for doc_name in doc_names:
        # Extract filename stem from doc_name (may be a URL or local path)
        stem = Path(doc_name.split("/")[-1]).stem
        # URL decode %20 etc
        stem = requests.utils.unquote(stem)
        cache_dir = OCR_CACHE_DIR / stem
        if cache_dir.exists():
            if dry_run:
                print(f"  [DRY] Would remove: {cache_dir}")
            else:
                shutil.rmtree(cache_dir)
                print(f"  Removed: {cache_dir.name}")
            cleared += 1
        else:
            print(f"  No cache: {stem}")
    print(f"  Cleared {cleared} cache dirs")


def invalidate_checkpoint(dry_run: bool) -> None:
    """Mark CTDT entries in checkpoint as 'deleted' so script.py re-uploads them."""
    print(f"\n[4/4] Invalidating checkpoint entries for CTDT files...")
    if not CHECKPOINT_FILE.exists():
        print("  No checkpoint file found, skipping")
        return

    lines = CHECKPOINT_FILE.read_text().splitlines()
    new_lines = []
    invalidated = 0

    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            path = rec.get("path", "")
            if "CTDT_" in path and "khoa" in path.lower():
                if not dry_run:
                    rec["status"] = "deleted"
                    line = json.dumps(rec)
                else:
                    print(f"  [DRY] Would invalidate: {Path(path).name}")
                invalidated += 1
        except json.JSONDecodeError:
            pass
        new_lines.append(line)

    if not dry_run:
        CHECKPOINT_FILE.write_text("\n".join(new_lines) + "\n")
    print(f"  Invalidated {invalidated} checkpoint entries")


def reupload_ctdt(dry_run: bool) -> None:
    """Re-upload all CTDT PDFs from the ctdt-cu/pdf directory."""
    pdf_files = sorted(CTDT_PDF_DIR.glob("CTDT_*.pdf"))
    print(f"\n[5/5] Re-uploading {len(pdf_files)} CTDT PDFs via LangGraph...")

    if not pdf_files:
        print("  No CTDT PDFs found in:", CTDT_PDF_DIR)
        return

    for f in pdf_files:
        print(f"  - {f.name}")

    if dry_run:
        print("  [DRY] Would upload the above files")
        return

    client = get_sync_client(url=LANGGRAPH_URL)

    pbar = tqdm(pdf_files, desc="Uploading", unit="file")
    success, errors = 0, []
    for pdf_path in pbar:
        pbar.set_postfix(file=pdf_path.name[:30])
        try:
            for _ in client.runs.stream(
                None,
                "index",
                input={"messages": [{"role": "human", "content": f"upload {pdf_path}"}]},
                stream_mode="updates",
            ):
                pass
            success += 1
        except Exception as e:
            errors.append((pdf_path.name, str(e)))
            print(f"\n  [ERROR] {pdf_path.name}: {e}")
    pbar.close()

    print(f"\nDone: {success} succeeded, {len(errors)} failed")
    if errors:
        for name, err in errors:
            print(f"  - {name}: {err}")


def main():
    parser = argparse.ArgumentParser(description="Delete and re-index CTDT curriculum docs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without doing it")
    parser.add_argument("--skip-delete", action="store_true", help="Skip deletion, only re-upload")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN MODE - no changes will be made ===\n")

    # Find CTDT docs
    docs = get_ctdt_docs()
    print(f"Found {len(docs)} CTDT curriculum docs to re-index:")
    for d in docs:
        name = d["doc_name"].split("/")[-1]
        print(f"  {d['doc_id']} | {name}")

    if not docs:
        print("Nothing to do.")
        return

    doc_ids = [d["doc_id"] for d in docs]
    doc_names = [d["doc_name"] for d in docs]

    if not args.skip_delete:
        # Get LightRAG auth token
        print("\nAuthenticating with LightRAG...")
        token = get_lightrag_token() if not args.dry_run else "dry-run-token"

        # Step 1: Delete from LightRAG (handles PG tables + Qdrant vectors)
        delete_from_lightrag(doc_ids, token, args.dry_run)

        # Step 2: Clean temporal_metadata (not managed by LightRAG)
        delete_temporal_metadata(doc_ids, args.dry_run)

        # Step 3: Clear OCR cache so v2 runs fresh
        clear_ocr_cache(doc_names, args.dry_run)

        # Step 4: Invalidate checkpoint entries
        invalidate_checkpoint(args.dry_run)

        if not args.dry_run:
            print("\nWaiting 3s for LightRAG to settle...")
            time.sleep(3)

    # Step 5: Re-upload
    reupload_ctdt(args.dry_run)


if __name__ == "__main__":
    main()
