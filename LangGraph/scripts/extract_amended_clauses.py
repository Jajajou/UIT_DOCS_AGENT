#!/usr/bin/env python3
"""
Extract amended clauses from document chunks and update temporal_metadata.

Scans chunks of docs that have amends_documents set for amendment patterns:
- 'sua doi Dieu X'
- 'bo sung khoan Y Dieu X'
- 'bai bo Dieu X'
And Vietnamese variants.

Updates temporal_metadata.amended_clauses in PostgreSQL.

Usage:
    cd LangGraph
    python scripts/extract_amended_clauses.py [--dry-run]
"""

import argparse
import json
import os
import re
import sys
import psycopg2
from dotenv import load_dotenv

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(os.path.dirname(_script_dir))
load_dotenv(os.path.join(_root, ".env.lightrag"))

# Patterns for amendment detection
# Group 1: target doc number (if mentioned in pattern) or we rely on amends_documents metadata
# Group 2: clause number
AMENDMENT_PATTERNS = [
    r'(?:sửa đổi|sua doi)\s+Điều\s+(\d+[a-z]?)',
    r'(?:bổ sung|bo sung)\s+(?:khoản|khoan)\s+\d+\s+Điều\s+(\d+[a-z]?)',
    r'(?:bãi bỏ|bai bo)\s+Điều\s+(\d+[a-z]?)',
]
# Compiled pattern to match any of the above
AMEND_REGEX = re.compile('|'.join(AMENDMENT_PATTERNS), re.IGNORECASE)

def _pg_conn():
    return psycopg2.connect(
        host="localhost",
        port=5433,
        user=os.getenv("POSTGRES_USER", "uitrag"),
        password=os.getenv("POSTGRES_PASSWORD", "admin123"),
        database=os.getenv("POSTGRES_DATABASE", "lightrag"),
    )

def fetch_amending_docs(conn):
    # Fetch docs that have amends_documents and their chunks
    query = """
        SELECT tm.doc_id, tm.document_number, tm.amends_documents, array_agg(dc.content)
        FROM temporal_metadata tm
        JOIN lightrag_doc_chunks dc ON dc.full_doc_id = tm.doc_id
        WHERE tm.amends_documents IS NOT NULL AND tm.amends_documents != '[]'::jsonb
        GROUP BY tm.doc_id, tm.document_number, tm.amends_documents
    """
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()

def extract_amended_clauses(chunks_content, amends_list):
    """
    Builds {target_doc_number: [clause_nums]} map.
    Since one doc might amend multiple others, we try to associate clauses with docs.
    However, for simplicity and following the prompt "builds {target_doc_number: [clause_nums]} map",
    we will scan all chunks.
    If multiple target docs are amended, it's often hard to tell which clause belongs to which doc
    without deep NLP. We'll assign found clauses to ALL target docs for now if ambiguous, 
    or just return a map if the pattern includes the doc number.
    
    Instruction says: "builds {target_doc_number: [clause_nums]} map"
    """
    amended_map = {}
    for target_doc in amends_list:
        target_doc = str(target_doc).strip().upper()
        amended_map[target_doc] = set()

    for content in chunks_content:
        # Find all matches
        # Note: AMEND_REGEX matches will have groups based on which sub-pattern matched.
        # We find all digits that follow the keywords.
        matches = re.findall(r'(?:sửa đổi|sua doi|bổ sung|bo sung|bãi bỏ|bai bo).*?Điều\s+(\d+)', content, re.IGNORECASE | re.DOTALL)
        for m in matches:
            val = int(m)
            for target_doc in amended_map:
                amended_map[target_doc].add(val)
                
    # Convert sets to sorted lists
    return {k: sorted(list(v)) for k, v in amended_map.items()}

def main():
    parser = argparse.ArgumentParser(description="Extract amended clauses")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done")
    args = parser.parse_args()

    conn = _pg_conn()
    docs = fetch_amending_docs(conn)
    
    print(f"Found {len(docs)} documents that amend others.")

    updated_count = 0
    for doc_id, doc_num, amends_list, chunks_content in docs:
        if not amends_list: continue
        
        # amends_list is a list of doc numbers
        amended_clauses = extract_amended_clauses(chunks_content, amends_list)
        
        if not any(amended_clauses.values()):
            continue

        if args.dry_run:
            print(f"[DRY-RUN] Doc {doc_num} ({doc_id}) amends: {json.dumps(amended_clauses)}")
            updated_count += 1
            continue

        # Update PostgreSQL
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE temporal_metadata SET amended_clauses = %s WHERE doc_id = %s",
                (json.dumps(amended_clauses), doc_id)
            )
        updated_count += 1

    conn.commit()
    conn.close()
    print(f"Done. Updated {updated_count} documents.")

if __name__ == "__main__":
    main()
