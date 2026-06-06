"""
RC-1: Backfill amended_by_documents for all docs that are referenced in
another doc's amends_documents.

For each doc A with amends_documents = [B, C]:
  - Find rows in temporal_metadata where document_number matches B or C
  - Append A's document_number to those rows' amended_by_documents

Safe to run multiple times (idempotent — uses jsonb set logic, no duplicates).
"""

import json
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from agent.utils import normalize_docnum  # noqa: E402


def get_pg_connection():
    password = os.getenv("POSTGRES_PASSWORD", "admin123")
    user = os.getenv("POSTGRES_USER", "uitrag")
    return psycopg2.connect(
        host="localhost",
        port=5433,
        user=user,
        password=password,
        dbname="lightrag",
    )


def main():
    conn = get_pg_connection()
    cur = conn.cursor()

    # 1. Fetch all rows with amends_documents populated
    cur.execute("""
        SELECT id, document_number, amends_documents
        FROM temporal_metadata
        WHERE amends_documents IS NOT NULL
          AND amends_documents != 'null'::jsonb
          AND jsonb_array_length(amends_documents) > 0
          AND document_number IS NOT NULL
          AND document_number != ''
    """)
    amenders = cur.fetchall()
    print(f"Found {len(amenders)} rows with non-empty amends_documents")

    # 2. Fetch all rows to build a lookup: normalized_docnum → list of row ids
    cur.execute("SELECT id, document_number FROM temporal_metadata WHERE document_number IS NOT NULL AND document_number != ''")
    all_rows = cur.fetchall()
    lookup: dict[str, list[int]] = {}
    for row_id, docnum in all_rows:
        key = normalize_docnum(docnum)
        lookup.setdefault(key, []).append(row_id)
    print(f"Lookup table: {len(lookup)} unique normalized doc numbers across {len(all_rows)} rows")

    # 3. Build reverse map: target_row_id → set of amender doc numbers
    reverse: dict[int, set[str]] = {}
    unmatched_pairs: list[tuple[str, str]] = []

    for _amender_row_id, amender_docnum, amends_json in amenders:
        if not amender_docnum:
            continue
        amends_list: list[str] = amends_json if isinstance(amends_json, list) else json.loads(amends_json)
        for target_docnum in amends_list:
            key = normalize_docnum(target_docnum)
            if key in lookup:
                for target_row_id in lookup[key]:
                    reverse.setdefault(target_row_id, set()).add(amender_docnum)
            else:
                unmatched_pairs.append((amender_docnum, target_docnum))

    print(f"Will update {len(reverse)} target rows")
    if unmatched_pairs:
        print(f"  {len(unmatched_pairs)} referenced doc numbers not found in KB (external/ministry docs — OK to skip):")
        for amender, target in unmatched_pairs[:10]:
            print(f"    {amender} -> {target}")
        if len(unmatched_pairs) > 10:
            print(f"    ... and {len(unmatched_pairs) - 10} more")

    # 4. Apply updates idempotently
    updated = 0
    for target_row_id, amender_set in reverse.items():
        cur.execute(
            "SELECT amended_by_documents FROM temporal_metadata WHERE id = %s",
            (target_row_id,),
        )
        row = cur.fetchone()
        if not row:
            continue

        existing_raw = row[0]
        existing: list[str] = existing_raw if isinstance(existing_raw, list) else (
            json.loads(existing_raw) if existing_raw else []
        )
        existing_set = set(existing)
        merged = sorted(existing_set | amender_set)

        if merged != sorted(existing_set):
            cur.execute(
                "UPDATE temporal_metadata SET amended_by_documents = %s WHERE id = %s",
                (json.dumps(merged, ensure_ascii=False), target_row_id),
            )
            updated += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Done. Updated {updated} rows with amended_by_documents.")


if __name__ == "__main__":
    main()
