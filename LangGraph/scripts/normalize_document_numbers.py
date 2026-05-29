"""
Normalize document_number in temporal_metadata and lightrag_doc_status tables.

Applies same logic as DocumentMetadata.normalize_document_number validator:
- Uppercase
- Replace underscore-before-slash artifacts (filename noise)
- Collapse consecutive slashes
- Reject if no slash remains or length > 80

Also normalizes amends_documents jsonb array using the same rules.

Usage:
    python scripts/normalize_document_numbers.py [--dry-run] [--workspace uit_docs_agent]
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from agent.utils import normalize_docnum  # noqa: E402

WORKSPACE = os.getenv("WORKSPACE", "uit_docs_agent")


def get_conn():
    return psycopg2.connect(
        host="localhost",
        port=5433,
        user=os.getenv("POSTGRES_USER", "uitrag"),
        password=os.getenv("POSTGRES_PASSWORD", "admin123"),
        dbname="lightrag",
    )


def normalize_amends_list(items: list | None) -> list:
    if not items:
        return []
    normalized = []
    seen: set = set()
    for item in items:
        n = normalize_docnum(item)
        if n and n not in seen:
            seen.add(n)
            normalized.append(n)
    return normalized


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workspace", default=WORKSPACE)
    args = parser.parse_args()

    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # --- temporal_metadata ---
    cur.execute(
        "SELECT id, document_number, amends_documents FROM temporal_metadata WHERE workspace = %s",
        (args.workspace,),
    )
    rows = cur.fetchall()
    print(f"temporal_metadata: {len(rows)} rows")

    tm_updated = 0
    for row in rows:
        rid = row["id"]
        orig_num = row["document_number"]
        orig_amends = row["amends_documents"] or []

        new_num = normalize_docnum(orig_num)
        new_amends = normalize_amends_list(orig_amends)

        num_changed = new_num != orig_num
        amends_changed = new_amends != orig_amends

        if num_changed or amends_changed:
            tm_updated += 1
            if num_changed:
                print(f"  [TM id={rid}] document_number: {orig_num!r} -> {new_num!r}")
            if amends_changed:
                print(f"  [TM id={rid}] amends_documents: {orig_amends} -> {new_amends}")
            if not args.dry_run:
                cur.execute(
                    """
                    UPDATE temporal_metadata
                    SET document_number = %s,
                        amends_documents = %s::jsonb,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (new_num, psycopg2.extras.Json(new_amends), rid),
                )

    # --- lightrag_doc_status (document_number stored in metadata jsonb) ---
    cur.execute(
        """
        SELECT id, metadata
        FROM lightrag_doc_status
        WHERE workspace = %s
          AND metadata IS NOT NULL
          AND metadata ? 'document_number'
        """,
        (args.workspace,),
    )
    status_rows = cur.fetchall()
    print(f"lightrag_doc_status: {len(status_rows)} rows with document_number in metadata")

    ds_updated = 0
    for row in status_rows:
        rid = row["id"]
        meta = row["metadata"] or {}
        orig_num = meta.get("document_number")
        new_num = normalize_docnum(orig_num)

        if new_num != orig_num:
            ds_updated += 1
            print(f"  [DS id={rid}] document_number: {orig_num!r} -> {new_num!r}")
            if not args.dry_run:
                meta["document_number"] = new_num
                cur.execute(
                    "UPDATE lightrag_doc_status SET metadata = %s::jsonb WHERE id = %s",
                    (psycopg2.extras.Json(meta), rid),
                )

    if args.dry_run:
        print(f"\n[DRY RUN] temporal_metadata: {tm_updated} would change, lightrag_doc_status: {ds_updated} would change")
        conn.rollback()
    else:
        conn.commit()
        print(f"\nDone. temporal_metadata: {tm_updated} updated, lightrag_doc_status: {ds_updated} updated")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
