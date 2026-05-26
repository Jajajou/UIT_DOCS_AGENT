"""
Retrieval Diagnostic Tool

For each failed pair in an ablation result JSON, checks:
  1. temporal_metadata    -- does expected doc have metadata + temporal score?
  2. lightrag_doc_status  -- is doc indexed and processed?
  3. Qdrant               -- are there chunk vectors with a payload linking to this doc?
  4. Root cause hypothesis

Usage:
    python tests/eval/diagnose_retrieval.py ablation_v0.3.0_Full.json
    python tests/eval/diagnose_retrieval.py ablation_v0.3.0_Full.json --type amendment_boundary
    python tests/eval/diagnose_retrieval.py ablation_v0.3.0_Full.json --pair-id 54 --verbose
    python tests/eval/diagnose_retrieval.py ablation_v0.3.0_Full.json --all  # include passing pairs
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import requests

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6336")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_CHUNKS_COLLECTION = "lightrag_vdb_chunks_aiteamvn_vietnamese_embedding_v2_1024d"

RESULTS_DIR = Path(__file__).parent / "results_archive"

DB_CONFIG = dict(
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", 5433)),
    user=os.getenv("POSTGRES_USER", "lightrag"),
    password=os.getenv("POSTGRES_PASSWORD", ""),
    database=os.getenv("POSTGRES_DATABASE", "lightrag"),
)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Strip diacritics, lower, collapse separators to empty string."""
    if not s:
        return ""
    s = s.lower()
    replacements = [
        (r"[áàảãạăắằẳẵặâấầẩẫậ]", "a"),
        (r"[éèẻẽẹêếềểễệ]", "e"),
        (r"[íìỉĩị]", "i"),
        (r"[óòỏõọôốồổỗộơớờởỡợ]", "o"),
        (r"[úùủũụưứừửữự]", "u"),
        (r"[ýỳỷỹỵ]", "y"),
        (r"[đ]", "d"),
    ]
    for pat, rep in replacements:
        s = re.sub(pat, rep, s)
    # Collapse all separator chars so "354/QD-DHCNTT" == "354QDDHCNTT"
    s = re.sub(r"[\s/\\_\-]", "", s)
    return s


def doc_numbers_match(a: str, b: str) -> bool:
    """True if two doc numbers refer to same document after normalization."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    return na == nb


def any_match(target: str, candidates: List[str]) -> bool:
    return any(doc_numbers_match(target, c) for c in candidates)


def _like_patterns(doc_number: str) -> List[str]:
    """
    Build SQL ILIKE patterns that work regardless of Vietnamese chars.
    Uses the numeric prefix + rough suffix.
    """
    # Extract leading numeric token, e.g. "354" from "354/QD-DHCNTT"
    m = re.match(r"^(\d[\d/]*)", doc_number)
    prefix = m.group(1) if m else doc_number[:3]
    return [f"%{prefix}%"]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def open_db() -> Optional[Any]:
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"[WARN] DB connection failed: {e}")
        return None


def check_temporal_metadata(conn, doc_number: str) -> List[Dict]:
    """Find temporal_metadata rows matching doc_number."""
    if not conn:
        return []
    patterns = _like_patterns(doc_number)
    rows = []
    with conn.cursor() as cur:
        for pat in patterns:
            cur.execute("""
                SELECT
                    tm.document_number,
                    tm.is_archived,
                    tm.extraction_confidence,
                    tm.cohort_scope,
                    tm.valid_from,
                    tm.valid_until,
                    tm.amends_documents,
                    tm.amended_by_documents,
                    lds.file_path,
                    lds.status
                FROM temporal_metadata tm
                LEFT JOIN lightrag_doc_status lds ON tm.doc_id = lds.id
                WHERE tm.document_number ILIKE %s
            """, (pat,))
            for r in cur.fetchall():
                row = {
                    "document_number": r[0],
                    "is_archived": r[1],
                    "extraction_confidence": r[2],
                    "cohort_scope": r[3],
                    "valid_from": str(r[4]) if r[4] else None,
                    "valid_until": str(r[5]) if r[5] else None,
                    "amends_documents": r[6],
                    "amended_by_documents": r[7],
                    "file_path": r[8],
                    "status": r[9],
                }
                # Deduplicate by normalized doc number
                if doc_numbers_match(row["document_number"], doc_number):
                    rows.append(row)
    return rows


def check_lightrag_doc_status(conn, doc_number: str) -> List[Dict]:
    """Find lightrag_doc_status rows matching doc_number via file_path pattern."""
    if not conn:
        return []
    # Extract numeric prefix for file_path search
    m = re.match(r"^(\d+)", doc_number)
    if not m:
        return []
    prefix = m.group(1)
    rows = []
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, file_path, status, created_at
            FROM lightrag_doc_status
            WHERE file_path ILIKE %s
            ORDER BY created_at DESC
        """, (f"%{prefix}%",))
        for r in cur.fetchall():
            rows.append({
                "doc_id": r[0],
                "file_path": r[1],
                "status": r[2],
                "created_at": str(r[3]),
            })
    return rows


# ---------------------------------------------------------------------------
# Qdrant helpers
# ---------------------------------------------------------------------------

def qdrant_headers() -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if QDRANT_API_KEY:
        h["api-key"] = QDRANT_API_KEY
    return h


def check_qdrant(doc_number: str, file_path: Optional[str] = None) -> Dict:
    """
    Check Qdrant for chunks related to this document.
    Tries two strategies:
      1. Filter by payload.document_number (if chunks have it)
      2. Filter by payload.file_path (if file_path is known)
    """
    result = {"by_doc_number": 0, "by_file_path": 0, "sample": None}
    base = f"{QDRANT_URL}/collections/{QDRANT_CHUNKS_COLLECTION}"
    headers = qdrant_headers()

    # Strategy 1: filter by document_number payload field
    norm_dn = _norm(doc_number).upper()
    try:
        body = {
            "filter": {
                "must": [{"key": "document_number", "match": {"value": doc_number}}]
            },
            "limit": 3,
            "with_payload": True,
        }
        r = requests.post(f"{base}/points/scroll", json=body, headers=headers, timeout=10)
        if r.ok:
            pts = r.json().get("result", {}).get("points", [])
            result["by_doc_number"] = len(pts)
            if pts:
                result["sample"] = pts[0].get("payload", {})
    except Exception as e:
        result["qdrant_error"] = str(e)

    # Strategy 2: filter by file_path if known
    if file_path:
        try:
            body = {
                "filter": {
                    "must": [{"key": "file_path", "match": {"value": file_path}}]
                },
                "limit": 3,
                "with_payload": True,
            }
            r = requests.post(f"{base}/points/scroll", json=body, headers=headers, timeout=10)
            if r.ok:
                pts = r.json().get("result", {}).get("points", [])
                result["by_file_path"] = len(pts)
                if pts and not result["sample"]:
                    result["sample"] = pts[0].get("payload", {})
        except Exception:
            pass

    return result


def qdrant_collection_info() -> Optional[Dict]:
    try:
        r = requests.get(
            f"{QDRANT_URL}/collections/{QDRANT_CHUNKS_COLLECTION}",
            headers=qdrant_headers(),
            timeout=5,
        )
        if r.ok:
            return r.json().get("result", {})
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Root cause classification
# ---------------------------------------------------------------------------

ROOT_CAUSES = {
    "NOT_INDEXED": "Doc not in lightrag_doc_status — never ingested",
    "INDEXED_NO_METADATA": "In lightrag_doc_status but no temporal_metadata — no temporal score",
    "ARCHIVED": "Doc exists but is_archived=True — filtered out by default",
    "ZERO_QDRANT_CHUNKS": "Indexed + metadata but 0 Qdrant chunks — vector search can't find it",
    "LOW_TEMPORAL_CONF": "Temporal metadata exists but confidence low (<0.5) — weak temporal boost",
    "AMENDMENT_OVERRIDE": "Doc demoted by amendment override (another doc in candidates amends it)",
    "AUTHORITY_MISMATCH": "Doc at wrong authority level for query (local vs system)",
    "EXISTS_RETRIEVED_WRONG_RANK": "Doc retrieved but ranked below @1 cutoff — ranking issue",
    "DUPLICATE_METADATA": "Multiple temporal_metadata rows for same doc — ambiguous scoring",
    "HALLUCINATION_ACC": "accuracy@1=1 but doc not in retrieved list — LLM mentioned it from context",
    "UNKNOWN": "Doc exists everywhere — deeper investigation needed",
}


def classify_root_cause(
    tm_rows: List[Dict],
    lds_rows: List[Dict],
    qdrant: Dict,
    acc: float,
    mrr: float,
    retrieved: List[str],
    expected_doc: str,
) -> Tuple[str, str]:
    """Return (code, detail) for the most likely root cause."""

    # Docs in retrieved list?
    in_retrieved = any_match(expected_doc, retrieved)

    if acc == 1.0 and mrr == 0.0 and not in_retrieved:
        return "HALLUCINATION_ACC", "acc=1 but not in retrieved_doc_numbers; LLM mentioned from chunk content"

    if not lds_rows:
        return "NOT_INDEXED", "No lightrag_doc_status row found"

    if not tm_rows:
        detail = f"lightrag_doc_status has {len(lds_rows)} row(s), status={lds_rows[0]['status']}"
        return "INDEXED_NO_METADATA", detail

    archived = [r for r in tm_rows if r.get("is_archived")]
    if archived:
        return "ARCHIVED", f"is_archived=True, {len(archived)} row(s)"

    if len(tm_rows) > 1:
        confs = [r.get("extraction_confidence") for r in tm_rows]
        return "DUPLICATE_METADATA", f"{len(tm_rows)} rows, confidences={confs}"

    conf = tm_rows[0].get("extraction_confidence")
    if conf is not None and conf < 0.5:
        return "LOW_TEMPORAL_CONF", f"extraction_confidence={conf:.3f}"

    chunk_count = qdrant.get("by_doc_number", 0) + qdrant.get("by_file_path", 0)
    if chunk_count == 0:
        return "ZERO_QDRANT_CHUNKS", "No Qdrant chunks found by doc_number or file_path"

    if in_retrieved and acc < 1.0:
        rank = next((i + 1 for i, r in enumerate(retrieved) if doc_numbers_match(r, expected_doc)), None)
        return "EXISTS_RETRIEVED_WRONG_RANK", f"Retrieved at rank={rank} but acc@1=0"

    return "UNKNOWN", f"Doc exists in all stores, {chunk_count} Qdrant chunks, conf={conf}"


# ---------------------------------------------------------------------------
# Per-pair diagnosis
# ---------------------------------------------------------------------------

def diagnose_pair(pair: Dict, conn, verbose: bool = False) -> Dict:
    pair_id = pair["id"]
    query = pair["query"]
    pair_type = pair["type"]
    expected_docs = pair.get("expected_doc_numbers", [])
    retrieved = pair.get("retrieved_doc_numbers", [])
    acc = pair.get("accuracy@1", 0.0)
    mrr = pair.get("mrr@10", 0.0)
    ap = pair.get("ap@3", 0.0)

    diagnoses = []

    for expected_doc in expected_docs:
        tm_rows = check_temporal_metadata(conn, expected_doc)
        lds_rows = check_lightrag_doc_status(conn, expected_doc)

        # Get file_path for Qdrant lookup
        file_path = None
        if tm_rows and tm_rows[0].get("file_path"):
            file_path = tm_rows[0]["file_path"]
        elif lds_rows:
            file_path = lds_rows[0].get("file_path")

        qdrant = check_qdrant(expected_doc, file_path)

        cause_code, cause_detail = classify_root_cause(
            tm_rows, lds_rows, qdrant, acc, mrr, retrieved, expected_doc
        )

        d = {
            "expected_doc": expected_doc,
            "root_cause": cause_code,
            "root_cause_detail": cause_detail,
            "in_temporal_metadata": len(tm_rows) > 0,
            "in_lightrag_doc_status": len(lds_rows) > 0,
            "qdrant_chunks_by_doc_number": qdrant.get("by_doc_number", 0),
            "qdrant_chunks_by_file_path": qdrant.get("by_file_path", 0),
            "temporal_rows": tm_rows if verbose else len(tm_rows),
            "lds_rows": lds_rows if verbose else len(lds_rows),
            "file_path": file_path,
        }
        diagnoses.append(d)

    return {
        "id": pair_id,
        "type": pair_type,
        "query": query,
        "accuracy@1": acc,
        "mrr@10": mrr,
        "ap@3": ap,
        "retrieved_doc_numbers": retrieved,
        "diagnoses": diagnoses,
    }


# ---------------------------------------------------------------------------
# Aggregate report
# ---------------------------------------------------------------------------

def aggregate(results: List[Dict]) -> Dict:
    cause_counts: Dict[str, int] = {}
    type_breakdown: Dict[str, Dict[str, int]] = {}

    for r in results:
        ptype = r["type"]
        if ptype not in type_breakdown:
            type_breakdown[ptype] = {}
        for d in r["diagnoses"]:
            code = d["root_cause"]
            cause_counts[code] = cause_counts.get(code, 0) + 1
            type_breakdown[ptype][code] = type_breakdown[ptype].get(code, 0) + 1

    total = sum(cause_counts.values())
    return {
        "total_expected_docs_analyzed": total,
        "root_cause_distribution": {
            k: {"count": v, "pct": round(100 * v / total, 1) if total else 0}
            for k, v in sorted(cause_counts.items(), key=lambda x: -x[1])
        },
        "by_query_type": type_breakdown,
        "root_cause_descriptions": {k: ROOT_CAUSES[k] for k in cause_counts if k in ROOT_CAUSES},
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Diagnose retrieval failures in ablation results")
    parser.add_argument("results_file", help="JSON results file (filename or full path)")
    parser.add_argument("--type", help="Filter by query type (e.g. amendment_boundary)")
    parser.add_argument("--pair-id", type=int, help="Diagnose single pair by ID")
    parser.add_argument("--all", action="store_true", help="Include passing pairs (acc=1 AND mrr>0)")
    parser.add_argument("--verbose", action="store_true", help="Include full DB rows in output")
    parser.add_argument("--output", help="Write JSON report to file instead of stdout")
    args = parser.parse_args()

    # Resolve file path
    results_path = Path(args.results_file)
    if not results_path.exists():
        results_path = RESULTS_DIR / args.results_file
    if not results_path.exists():
        print(f"ERROR: File not found: {args.results_file}", file=sys.stderr)
        sys.exit(1)

    with open(results_path) as f:
        data = json.load(f)

    # Flatten all pairs
    by_type = data.get("by_type", {})
    all_pairs: List[Dict] = []
    for pairs in by_type.values():
        all_pairs.extend(pairs)

    # Filter
    if args.type:
        all_pairs = [p for p in all_pairs if p["type"] == args.type]
    if args.pair_id is not None:
        all_pairs = [p for p in all_pairs if p["id"] == args.pair_id]
    if not args.all:
        # Only failed/partial pairs: acc<1 OR mrr=0
        all_pairs = [p for p in all_pairs if p.get("accuracy@1", 0) < 1.0 or p.get("mrr@10", 0) == 0.0]

    print(f"Diagnosing {len(all_pairs)} pairs...", file=sys.stderr)

    # Check Qdrant reachability
    coll_info = qdrant_collection_info()
    if coll_info:
        print(f"Qdrant OK — {coll_info.get('points_count', '?')} points in {QDRANT_CHUNKS_COLLECTION}", file=sys.stderr)
    else:
        print(f"[WARN] Qdrant unreachable at {QDRANT_URL}", file=sys.stderr)

    conn = open_db()

    results = []
    for i, pair in enumerate(all_pairs, 1):
        print(f"  [{i}/{len(all_pairs)}] pair={pair['id']} type={pair['type']}", file=sys.stderr, end="\r")
        results.append(diagnose_pair(pair, conn, verbose=args.verbose))

    print(file=sys.stderr)  # newline after progress

    agg = aggregate(results)

    report = {
        "source_file": str(results_path),
        "summary": data.get("summary", {}),
        "filters": {
            "type": args.type,
            "pair_id": args.pair_id,
            "include_passing": args.all,
        },
        "aggregate": agg,
        "pairs": results,
    }

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
