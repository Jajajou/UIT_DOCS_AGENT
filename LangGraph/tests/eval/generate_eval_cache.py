"""
Regenerate eval_metadata_cache.json from current DB state.

Schema per entry:
{
  "doc_id": str,
  "amends_documents": [doc_number, ...],   # docs this one amends
  "amended_by": [doc_id, ...],             # doc_ids that amend this one (reverse link)
  "cohort_years": [...] | null,
  "valid_from": "YYYY-MM-DD" | null,
  "valid_until": "YYYY-MM-DD" | null,
  "document_type": str | null,
  "authority_level": str                   # derived: "uit" | "dhqg" | "bo"
}

Run from project root:
  cd LangGraph && ../.venv/bin/python tests/eval/generate_eval_cache.py
"""

import json
import os
import re
from pathlib import Path

import psycopg2
import psycopg2.extras

DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://uitrag:uitrag@localhost:5433/lightrag"
)

OUTPUT = Path(__file__).parent / "eval_metadata_cache.json"


def _authority_level(doc_number: str | None) -> str:
    if not doc_number:
        return "unknown"
    upper = doc_number.upper()
    if "BGDDT" in upper or "BGDĐT" in upper or "ND-CP" in upper or "NĐ-CP" in upper or "TT-BGD" in upper:
        return "bo"
    if "DHQG" in upper or "ĐHQG" in upper:
        return "dhqg"
    if "DHCNTT" in upper or "ĐHCNTT" in upper or "ĐHCNTT" in upper:
        return "uit"
    return "other"


def _fmt_date(val) -> str | None:
    if val is None:
        return None
    s = str(val)
    # keep YYYY-MM-DD only
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else s


def main():
    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT doc_id, document_number, document_type,
               valid_from, valid_until, cohort_years,
               amends_documents, amended_by_documents
        FROM temporal_metadata
        WHERE doc_id IS NOT NULL
        ORDER BY document_number
    """)
    rows = cur.fetchall()
    conn.close()

    # First pass: build bidirectional maps doc_number ↔ doc_id
    num_to_id: dict[str, str] = {}
    id_to_num: dict[str, str] = {}
    for row in rows:
        dn = row["document_number"]
        if dn:
            num_to_id[dn] = row["doc_id"]
            id_to_num[row["doc_id"]] = dn

    def _resolve_to_docnum(val: str) -> str | None:
        """Resolve either a doc_id or doc_number to a doc_number."""
        if val in id_to_num:
            return id_to_num[val]
        if val in num_to_id:
            return val
        return None

    # Second pass: build cache entries
    cache: dict[str, dict] = {}

    for row in rows:
        dn = row["document_number"]
        if not dn:
            continue

        amends = row["amends_documents"] or []
        # Resolve amended_by_documents: may contain doc_ids or doc_numbers — normalise to doc_numbers
        raw_amended_by = row["amended_by_documents"] or []
        amended_by_nums = []
        for val in raw_amended_by:
            resolved = _resolve_to_docnum(val)
            if resolved and resolved not in amended_by_nums:
                amended_by_nums.append(resolved)

        cache[dn] = {
            "doc_id": row["doc_id"],
            "amends_documents": amends,
            "amended_by": amended_by_nums,
            "cohort_years": row["cohort_years"],
            "valid_from": _fmt_date(row["valid_from"]),
            "valid_until": _fmt_date(row["valid_until"]),
            "document_type": row["document_type"],
            "authority_level": _authority_level(dn),
        }

    # Third pass: fill reverse links from amends_documents (store doc_number not doc_id)
    # For each doc A that amends [B, C, ...], add A's doc_number to B.amended_by and C.amended_by
    for dn, entry in cache.items():
        for amended_target in entry["amends_documents"]:
            if amended_target in cache:
                if dn not in cache[amended_target]["amended_by"]:
                    cache[amended_target]["amended_by"].append(dn)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    print(f"Written {len(cache)} entries → {OUTPUT}")
    amended_count = sum(1 for v in cache.values() if v["amended_by"])
    print(f"Entries with amended_by: {amended_count}")
    amends_count = sum(1 for v in cache.values() if v["amends_documents"])
    print(f"Entries with amends_documents: {amends_count}")


if __name__ == "__main__":
    main()
