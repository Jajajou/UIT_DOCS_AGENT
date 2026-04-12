#!/usr/bin/env python3
"""
Standalone metadata extraction script.

Runs metadata RAG extraction on all documents already indexed in LightRAG
without re-running the full indexing pipeline.

Usage:
    source .venv/bin/activate
    python extract_metadata_standalone.py [--force] [--doc-id DOC_ID] [--limit N]

Options:
    --force     Re-extract even for docs that already have metadata
    --doc-id    Process only a specific doc_id
    --limit N   Process only N documents (for testing)
    --min-confidence 0.3  Skip docs that already have confidence >= this threshold
"""

import asyncio
import argparse
import json
import os
import sys
from datetime import datetime

import psycopg2
from dotenv import load_dotenv

# Setup paths
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LANGGRAPH_SRC = os.path.join(PROJECT_ROOT, "LangGraph", "src")
sys.path.insert(0, LANGGRAPH_SRC)

# Load env vars from LangGraph/.env (has OPENAI_API_KEY etc.)
load_dotenv(os.path.join(PROJECT_ROOT, "LangGraph", ".env"))
# Also load main .env
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

PG_CONN_PARAMS = {
    "host": "localhost",
    "port": 5433,
    "database": "lightrag",
    "user": "uitrag",
    "password": "admin123",
}
WORKSPACE = "uit_docs_agent"


def get_pg_connection():
    return psycopg2.connect(**PG_CONN_PARAMS)


def get_docs_to_process(
    force: bool = False,
    doc_id: str | None = None,
    limit: int | None = None,
    min_confidence: float = 0.3,
) -> list[dict]:
    """
    Get docs that need metadata extraction.

    Returns docs that either:
    - Have no entry in temporal_metadata
    - Have entry but extraction_confidence is NULL or below threshold
    """
    conn = get_pg_connection()
    cur = conn.cursor()

    if doc_id:
        query = """
            SELECT f.id, f.doc_name, f.content,
                   tm.extraction_confidence, tm.document_number
            FROM lightrag_doc_full f
            LEFT JOIN temporal_metadata tm ON tm.doc_id = f.id
            WHERE f.workspace = %s AND f.id = %s
        """
        cur.execute(query, (WORKSPACE, doc_id))
    elif force:
        query = """
            SELECT f.id, f.doc_name, f.content,
                   tm.extraction_confidence, tm.document_number
            FROM lightrag_doc_full f
            LEFT JOIN temporal_metadata tm ON tm.doc_id = f.id
            WHERE f.workspace = %s
            ORDER BY f.create_time ASC
        """
        params = [WORKSPACE]
        if limit:
            query += " LIMIT %s"
            params.append(limit)
        cur.execute(query, params)
    else:
        # Only process docs without good metadata
        query = """
            SELECT f.id, f.doc_name, f.content,
                   tm.extraction_confidence, tm.document_number
            FROM lightrag_doc_full f
            LEFT JOIN temporal_metadata tm ON tm.doc_id = f.id
            WHERE f.workspace = %s
              AND (
                tm.doc_id IS NULL
                OR tm.extraction_confidence IS NULL
                OR tm.extraction_confidence < %s
              )
            ORDER BY f.create_time ASC
        """
        params = [WORKSPACE, min_confidence]
        if limit:
            query += " LIMIT %s"
            params.append(limit)
        cur.execute(query, params)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    docs = []
    for row in rows:
        doc_id_val, doc_name, content, conf, doc_num = row
        docs.append({
            "doc_id": doc_id_val,
            "doc_name": doc_name,
            "content": content or "",
            "existing_confidence": conf,
            "existing_document_number": doc_num,
        })

    return docs


def get_track_id_for_doc(doc_id: str) -> str | None:
    """Get track_id for a doc_id from lightrag_doc_status."""
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT track_id FROM lightrag_doc_status WHERE id = %s AND workspace = %s",
        (doc_id, WORKSPACE),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None


def upsert_temporal_metadata(doc_id: str, track_id: str | None, metadata: dict) -> bool:
    """Upsert metadata into temporal_metadata table."""
    conn = get_pg_connection()

    known_fields = {
        "document_number", "document_type", "valid_from", "valid_until",
        "cohort_years", "cohort_scope", "student_cohorts", "amends_documents",
        "extraction_method", "extraction_confidence",
    }
    additional = {k: v for k, v in metadata.items() if k not in known_fields}

    document_number = metadata.get("document_number")
    document_type = metadata.get("document_type")
    valid_from = metadata.get("valid_from")
    valid_until = metadata.get("valid_until")
    cohort_years = metadata.get("cohort_years")
    cohort_scope = metadata.get("cohort_scope", "unspecified")
    student_cohorts = metadata.get("student_cohorts")
    amends_documents = metadata.get("amends_documents")
    extraction_method = metadata.get("extraction_method", "metadata_rag_standalone")
    extraction_confidence = metadata.get("extraction_confidence")

    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO temporal_metadata (
                    doc_id, track_id, workspace,
                    document_number, document_type,
                    valid_from, valid_until,
                    cohort_years, cohort_scope, student_cohorts,
                    amends_documents,
                    extraction_method, extraction_confidence,
                    extraction_timestamp,
                    additional_metadata
                ) VALUES (
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s,
                    %s, %s,
                    CURRENT_TIMESTAMP,
                    %s
                )
                ON CONFLICT (doc_id) DO UPDATE SET
                    track_id = EXCLUDED.track_id,
                    document_number = EXCLUDED.document_number,
                    document_type = EXCLUDED.document_type,
                    valid_from = EXCLUDED.valid_from,
                    valid_until = EXCLUDED.valid_until,
                    cohort_years = EXCLUDED.cohort_years,
                    cohort_scope = EXCLUDED.cohort_scope,
                    student_cohorts = EXCLUDED.student_cohorts,
                    amends_documents = EXCLUDED.amends_documents,
                    extraction_method = EXCLUDED.extraction_method,
                    extraction_confidence = EXCLUDED.extraction_confidence,
                    extraction_timestamp = CURRENT_TIMESTAMP,
                    additional_metadata = EXCLUDED.additional_metadata,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                doc_id, track_id, WORKSPACE,
                document_number, document_type,
                valid_from, valid_until,
                json.dumps(cohort_years) if cohort_years else None,
                cohort_scope,
                json.dumps(student_cohorts) if student_cohorts else None,
                json.dumps(amends_documents) if amends_documents else None,
                extraction_method, extraction_confidence,
                json.dumps(additional) if additional else None,
            ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"  [DB ERROR] {e}")
        return False
    finally:
        conn.close()


async def extract_metadata_for_doc(doc: dict) -> dict | None:
    """Run metadata RAG subgraph on a single document."""
    from agent.graphs.metadata_rag_subgraph import metadata_rag_subgraph

    initial_state = {
        "doc_text": doc["content"],
        "file_source": doc["doc_name"],
        "doc_id": doc["doc_id"],
        "success": False,
    }

    try:
        result = await metadata_rag_subgraph.ainvoke(initial_state)
        if result.get("success") and result.get("final_metadata"):
            return result["final_metadata"]
        return None
    except Exception as e:
        print(f"  [RAG ERROR] {e}")
        return None


async def main():
    parser = argparse.ArgumentParser(description="Standalone metadata extraction")
    parser.add_argument("--force", action="store_true", help="Re-extract all docs")
    parser.add_argument("--doc-id", help="Process a specific doc_id only")
    parser.add_argument("--limit", type=int, help="Limit number of docs to process")
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.3,
        help="Skip docs with confidence >= this (default: 0.3)",
    )
    args = parser.parse_args()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting standalone metadata extraction")
    print(f"  Mode: {'force re-extract all' if args.force else 'skip docs with good metadata'}")
    print(f"  Min confidence threshold: {args.min_confidence}")

    docs = get_docs_to_process(
        force=args.force,
        doc_id=args.doc_id,
        limit=args.limit,
        min_confidence=args.min_confidence,
    )

    total = len(docs)
    print(f"  Documents to process: {total}")

    if total == 0:
        print("Nothing to do.")
        return

    success_count = 0
    skip_count = 0
    fail_count = 0

    for i, doc in enumerate(docs, 1):
        doc_id = doc["doc_id"]
        doc_name = doc["doc_name"]
        content_len = len(doc["content"])

        print(f"\n[{i}/{total}] {doc_name}")
        print(f"  doc_id: {doc_id} | content: {content_len} chars")

        if content_len < 100:
            print("  [SKIP] Content too short, skipping")
            skip_count += 1
            continue

        track_id = get_track_id_for_doc(doc_id)

        metadata = await extract_metadata_for_doc(doc)

        if metadata is None:
            print("  [FAIL] Metadata extraction returned nothing")
            fail_count += 1
            continue

        confidence = metadata.get("extraction_confidence", 0.0)
        doc_num = metadata.get("document_number")
        cohorts = metadata.get("cohort_years", [])
        print(f"  confidence={confidence:.3f} | doc_num={doc_num} | cohorts={cohorts}")

        saved = upsert_temporal_metadata(doc_id, track_id, metadata)
        if saved:
            print(f"  [OK] Saved to temporal_metadata")
            success_count += 1
        else:
            print(f"  [FAIL] Could not save to DB")
            fail_count += 1

    print(f"\n{'='*60}")
    print(f"Done: {success_count} saved, {skip_count} skipped, {fail_count} failed")
    print(f"Total: {total}")


if __name__ == "__main__":
    asyncio.run(main())
