"""
Backfill education_system field for temporal_metadata and Qdrant chunk payloads.

Usage:
  # Step 1: Run DB classification (ALTER TABLE + UPDATE via psycopg2)
  python backfill_education_system.py --db-only

  # Step 2: Export classifications to JSON (for review)
  python backfill_education_system.py --export classifications.json

  # Step 3: Update Qdrant payloads (reads from DB or JSON file)
  python backfill_education_system.py --qdrant-only
  python backfill_education_system.py --qdrant-only --from-json classifications.json

  # Step 4: Dry run (print without sending)
  python backfill_education_system.py --dry-run

  # Full pipeline:
  python backfill_education_system.py

IMPORTANT: DB connection uses DATABASE_URL env var or defaults to
  postgresql://uitrag:admin123@localhost:5433/lightrag
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://uitrag:admin123@localhost:5433/lightrag"
)
QDRANT_BASE_URL = os.environ.get("QDRANT_BASE_URL", "http://localhost:6336")
QDRANT_COLLECTION = "lightrag_vdb_chunks_aiteamvn_vietnamese_embedding_v2_1024d"
WORKSPACE = "uit_docs_agent"

# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

KNOWN_OVERRIDES: Dict[str, str] = {
    "507/QD-DHCNTT": "tu_xa",
}

MINISTRY_PATTERN = re.compile(
    r"^\d+\s*/\s*(ND-CP|TT-BGD|TT-BGDDT|QD-BGDDT|QD-TTg)",
    re.IGNORECASE,
)
VNU_PATTERN = re.compile(r"/QD-DHQG", re.IGNORECASE)


def classify_document(
    doc_id: str,
    document_number: Optional[str],
    file_path: Optional[str],
) -> str:
    """
    Classify document into education_system category.

    Rules applied in order (first match wins):
    1. KNOWN_OVERRIDES (hardcoded, highest priority)
    2. file_path contains 'tu_xa' -> tu_xa
    3. file_path contains 'tien_tien' -> tien_tien
    4. file_path contains 'song_nganh' -> song_nganh
    5. document_number matches ministry pattern -> universal
    6. document_number contains /QD-DHQG -> universal
    7. Default -> chinh_quy
    """
    doc_num = (document_number or "").strip()
    fp = (file_path or "").lower()

    # 1. Hardcoded overrides
    if doc_num in KNOWN_OVERRIDES:
        return KNOWN_OVERRIDES[doc_num]

    # 2-4. File path keywords
    if "tu_xa" in fp:
        return "tu_xa"
    if "tien_tien" in fp:
        return "tien_tien"
    if "song_nganh" in fp:
        return "song_nganh"

    # 5. Ministry pattern
    if MINISTRY_PATTERN.match(doc_num):
        return "universal"

    # 6. VNU (DHQG) documents
    if VNU_PATTERN.search(doc_num):
        return "universal"

    # 7. Default: chinh_quy (UIT internal documents)
    return "chinh_quy"


# ---------------------------------------------------------------------------
# DB operations
# ---------------------------------------------------------------------------

def get_db_connection():
    """Get psycopg2 connection."""
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)
    return psycopg2.connect(DATABASE_URL)


def alter_table(conn) -> None:
    """Add education_system column if not exists."""
    cur = conn.cursor()
    sql = "ALTER TABLE temporal_metadata ADD COLUMN IF NOT EXISTS education_system TEXT DEFAULT 'universal';"
    print(f"[DB] Executing: {sql}")
    cur.execute(sql)
    conn.commit()
    print("[DB] ALTER TABLE OK")
    cur.close()


def fetch_all_docs(conn) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """
    Fetch all docs for classification.
    Returns list of (doc_id, document_number, file_path).
    """
    cur = conn.cursor()
    sql = """
        SELECT tm.doc_id, tm.document_number, lds.file_path
        FROM temporal_metadata tm
        LEFT JOIN lightrag_doc_status lds ON tm.doc_id = lds.id
        WHERE tm.workspace = %s
    """
    print(f"[DB] Fetching all docs for workspace={WORKSPACE}")
    cur.execute(sql, (WORKSPACE,))
    rows = cur.fetchall()
    cur.close()
    print(f"[DB] Found {len(rows)} docs")
    return rows


def apply_classifications(
    conn, classifications: Dict[str, str], dry_run: bool = False
) -> int:
    """
    UPDATE temporal_metadata.education_system for each doc.
    Returns count of updated rows.
    """
    cur = conn.cursor()
    updated = 0
    for doc_id, edu_system in classifications.items():
        sql = "UPDATE temporal_metadata SET education_system = %s WHERE doc_id = %s;"
        if dry_run:
            print(f"[DRY-RUN] {sql} -- ({edu_system!r}, {doc_id!r})")
        else:
            cur.execute(sql, (edu_system, doc_id))
            updated += cur.rowcount
    if not dry_run:
        conn.commit()
    cur.close()
    print(f"[DB] Updated {updated} rows" if not dry_run else "[DRY-RUN] DB updates skipped")
    return updated


def verify_db(conn) -> None:
    """Print GROUP BY summary and 507 override verification."""
    cur = conn.cursor()

    cur.execute("""
        SELECT education_system, COUNT(*)
        FROM temporal_metadata
        GROUP BY education_system
        ORDER BY COUNT(*) DESC
    """)
    print("\n[DB] Classification summary:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    cur.execute("""
        SELECT document_number, education_system
        FROM temporal_metadata
        WHERE document_number LIKE '%507%'
    """)
    rows = cur.fetchall()
    print("\n[DB] 507 override verification:")
    for row in rows:
        print(f"  {row[0]}: {row[1]}")
    cur.close()


# ---------------------------------------------------------------------------
# Qdrant operations
# ---------------------------------------------------------------------------

def update_qdrant_for_doc(
    document_number: str, education_system: str, dry_run: bool = False
) -> bool:
    """
    Set education_system payload on all Qdrant chunk points matching document_number.
    Chunks have no full_doc_id field; filter by document_number instead.
    """
    url = f"{QDRANT_BASE_URL}/collections/{QDRANT_COLLECTION}/points/payload"
    body = {
        "payload": {"education_system": education_system},
        "filter": {
            "must": [
                {"key": "document_number", "match": {"value": document_number}}
            ]
        },
    }
    if dry_run:
        print(f"[DRY-RUN] PUT {url} -- doc_num={document_number}, education_system={education_system}")
        return True

    try:
        r = requests.put(url, json=body, timeout=30)
        if r.status_code == 200:
            return True
        print(f"[QDRANT] WARN: doc_num={document_number} -> status {r.status_code}: {r.text[:200]}")
        return False
    except requests.RequestException as e:
        print(f"[QDRANT] ERROR: doc_num={document_number} -> {e}")
        return False


def backfill_qdrant(
    docnum_to_edu: Dict[str, str], dry_run: bool = False
) -> Tuple[int, int]:
    """
    Update Qdrant payloads for all docs keyed by document_number.
    Returns (success_count, fail_count).
    """
    success = 0
    fail = 0
    total = len(docnum_to_edu)
    for i, (document_number, edu_system) in enumerate(docnum_to_edu.items(), 1):
        if not document_number:
            fail += 1
            continue
        ok = update_qdrant_for_doc(document_number, edu_system, dry_run=dry_run)
        if ok:
            success += 1
        else:
            fail += 1
        if i % 10 == 0 or i == total:
            print(f"[QDRANT] Progress: {i}/{total} (ok={success}, fail={fail})")
    return success, fail


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_classifications_from_db(conn) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Fetch docs and classify all.
    Returns (doc_id_to_edu, docnum_to_edu).
    doc_id_to_edu used for DB UPDATE.
    docnum_to_edu used for Qdrant payload filter (chunks indexed by document_number).
    """
    rows = fetch_all_docs(conn)
    doc_id_to_edu: Dict[str, str] = {}
    docnum_to_edu: Dict[str, str] = {}
    for doc_id, document_number, file_path in rows:
        edu = classify_document(doc_id, document_number, file_path)
        doc_id_to_edu[doc_id] = edu
        if document_number:
            docnum_to_edu[document_number] = edu
        print(f"  {doc_id}: {document_number!r} -> {edu}")
    return doc_id_to_edu, docnum_to_edu


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill education_system for temporal_metadata and Qdrant"
    )
    parser.add_argument(
        "--db-only", action="store_true", help="Only run DB ALTER + UPDATE (no Qdrant)"
    )
    parser.add_argument(
        "--qdrant-only", action="store_true", help="Only run Qdrant backfill (no DB writes)"
    )
    parser.add_argument(
        "--from-json",
        metavar="FILE",
        help="Load classifications from JSON file (skip DB fetch)",
    )
    parser.add_argument(
        "--export",
        metavar="FILE",
        help="Export classifications to JSON file after DB fetch",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print actions without executing"
    )
    args = parser.parse_args()

    dry_run = args.dry_run
    if dry_run:
        print("[INFO] DRY-RUN mode: no DB writes, no Qdrant updates")

    # ---- Load classifications ----
    if args.from_json:
        print(f"[INFO] Loading classifications from {args.from_json}")
        with open(args.from_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Support both old format {doc_id: edu} and new format {doc_id_to_edu, docnum_to_edu}
        if "doc_id_to_edu" in data:
            doc_id_to_edu = data["doc_id_to_edu"]
            docnum_to_edu = data["docnum_to_edu"]
        else:
            doc_id_to_edu = data
            docnum_to_edu = {}
        conn = None
    else:
        conn = get_db_connection()
        if not args.qdrant_only:
            alter_table(conn)
        doc_id_to_edu, docnum_to_edu = build_classifications_from_db(conn)

    # ---- Export if requested ----
    if args.export:
        export_data = {"doc_id_to_edu": doc_id_to_edu, "docnum_to_edu": docnum_to_edu}
        with open(args.export, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Exported {len(doc_id_to_edu)} classifications to {args.export}")

    # ---- Apply DB updates ----
    if not args.qdrant_only:
        if conn is None:
            conn = get_db_connection()
        apply_classifications(conn, doc_id_to_edu, dry_run=dry_run)
        verify_db(conn)

    # ---- Qdrant backfill ----
    if not args.db_only:
        print(f"\n[QDRANT] Backfilling {len(docnum_to_edu)} docs by document_number...")
        success, fail = backfill_qdrant(docnum_to_edu, dry_run=dry_run)
        print(f"[QDRANT] Done: {success} OK, {fail} failed")

    if conn:
        conn.close()

    print("\n[INFO] Backfill complete.")


if __name__ == "__main__":
    main()
