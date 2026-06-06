#!/usr/bin/env python3
"""
Backfill Qdrant chunk payloads with clause_numbers.

Scans content of chunks for Vietnamese legal clause patterns (Điều X / Dieu X),
extracts clause numbers, and updates Qdrant payloads.

Usage:
    cd LangGraph
    python scripts/backfill_clause_numbers.py [--dry-run]
"""

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
import psycopg2
import requests
from dotenv import load_dotenv

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(os.path.dirname(_script_dir))
load_dotenv(os.path.join(_root, ".env.lightrag"))

QDRANT_BASE_URL = "http://localhost:6336"
COLLECTION = "lightrag_vdb_chunks"
WORKSPACE = "uit_docs_agent"

# Pattern to find "Điều 5", "Dieu 5", "Điều 5a", etc.
# Scans anywhere in content for Phase 1.
CLAUSE_REGEX = re.compile(r'(?:Điều|Dieu|ĐIỀU)\s+(\d+[a-z]?)', re.IGNORECASE)

def _chunk_uuid(chunk_id: str, prefix: str = WORKSPACE) -> str:
    hashed = hashlib.sha256((prefix + chunk_id).encode("utf-8")).digest()
    return str(uuid.UUID(bytes=hashed[:16], version=4))

def _pg_conn():
    return psycopg2.connect(
        host="localhost",
        port=5433,
        user=os.getenv("POSTGRES_USER", "uitrag"),
        password=os.getenv("POSTGRES_PASSWORD", "admin123"),
        database=os.getenv("POSTGRES_DATABASE", "lightrag"),
    )

def fetch_chunks(conn):
    query = "SELECT id, content FROM lightrag_doc_chunks"
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()

def extract_clause_numbers(content: str) -> list[int]:
    matches = CLAUSE_REGEX.findall(content)
    clause_nums = []
    for m in matches:
        # Extract the leading integer part
        num_match = re.match(r'(\d+)', m)
        if num_match:
            clause_nums.append(int(num_match.group(1)))
    return sorted(list(set(clause_nums)))

def update_qdrant_payload(point_id: str, clause_numbers: list[int], dry_run: bool, session: requests.Session) -> bool:
    url = f"{QDRANT_BASE_URL.rstrip('/')}/collections/{COLLECTION}/points/payload"
    # Use POST to add fields (overwrite if exists, keep others)
    body = {
        "payload": {
            "clause_numbers": clause_numbers
        },
        "points": [point_id],
    }

    if dry_run:
        return True

    try:
        resp = session.post(url, json=body, timeout=10)
        resp.raise_for_status()
        return resp.json().get("status") == "ok"
    except Exception as exc:
        print(f"  ERROR updating {point_id}: {exc}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Backfill clause_numbers to Qdrant")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without writing")
    args = parser.parse_args()

    print(f"Connecting to Postgres...")
    conn = _pg_conn()
    chunks = fetch_chunks(conn)
    conn.close()

    print(f"Found {len(chunks)} chunks. Processing...")
    
    session = requests.Session()
    ok_count = 0
    skip_count = 0
    fail_count = 0

    for i, (chunk_id, content) in enumerate(chunks, 1):
        clause_numbers = extract_clause_numbers(content)
        if not clause_numbers:
            skip_count += 1
            continue

        point_id = _chunk_uuid(chunk_id)
        
        if args.dry_run:
            if i <= 10:
                print(f"[DRY-RUN] Chunk {chunk_id} -> Point {point_id}: clause_numbers={clause_numbers}")
            ok_count += 1
            continue

        if update_qdrant_payload(point_id, clause_numbers, args.dry_run, session):
            ok_count += 1
        else:
            fail_count += 1

        if i % 100 == 0:
            print(f"Processed {i}/{len(chunks)}...")

    print(f"\nFinished.")
    print(f"Updated: {ok_count}")
    print(f"Skipped: {skip_count} (no clauses found)")
    print(f"Failed:  {fail_count}")

if __name__ == "__main__":
    main()
