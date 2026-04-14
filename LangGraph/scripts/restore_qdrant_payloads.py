"""Restore Qdrant chunk payloads from PostgreSQL lightrag_doc_chunks.

The original LightRAG fields (id, workspace_id, created_at, content,
full_doc_id, file_path) were overwritten by a PUT (overwrite) instead of
POST (merge) call. This script restores them using the deterministic UUID
formula that LightRAG uses to map chunk IDs to Qdrant point UUIDs.

LightRAG UUID formula (from qdrant_impl.py):
    SHA-256(workspace + chunk_id)[:16] -> UUID v4

Run BEFORE re-running inject_qdrant_payloads.py.

Usage:
    cd /Users/jajajou1778/UIT_DOCS_AGENT
    source .venv/bin/activate
    python LangGraph/scripts/restore_qdrant_payloads.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
import uuid
import os

import psycopg2
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

load_dotenv("LangGraph/.env")
load_dotenv(".env.lightrag")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

QDRANT_URL = "http://localhost:6336"
COLLECTION = "lightrag_vdb_chunks"
BATCH_SIZE = 50


def chunk_id_to_qdrant_uuid(chunk_id: str, workspace: str) -> str:
    """Reproduce LightRAG's compute_mdhash_id_for_qdrant formula."""
    hashed = hashlib.sha256((workspace + chunk_id).encode("utf-8")).digest()
    return str(uuid.UUID(bytes=hashed[:16], version=4))


def get_pg_conn() -> psycopg2.extensions.connection:
    user = os.getenv("POSTGRES_USER", "uitrag")
    password = os.getenv("POSTGRES_PASSWORD", "")
    dbname = os.getenv("POSTGRES_DATABASE", "lightrag")
    return psycopg2.connect(
        host="localhost", port=5433,
        user=user, password=password, dbname=dbname
    )


def restore_payloads() -> None:
    conn = get_pg_conn()
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, workspace, full_doc_id, file_path, content, create_time
            FROM lightrag_doc_chunks
            ORDER BY id
        """)
        rows = cur.fetchall()

    conn.close()

    logger.info("Found %d chunks in lightrag_doc_chunks", len(rows))

    restored = 0
    not_found = 0
    errors = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        points_payload = []

        for chunk_id, workspace, full_doc_id, file_path, content, create_time in batch:
            qdrant_uuid = chunk_id_to_qdrant_uuid(chunk_id, workspace or "uit_docs_agent")
            created_at = int(create_time.timestamp()) if create_time else 0

            points_payload.append({
                "qdrant_uuid": qdrant_uuid,
                "payload": {
                    "id": chunk_id,
                    "workspace_id": workspace or "uit_docs_agent",
                    "created_at": created_at,
                    "content": content or "",
                    "full_doc_id": full_doc_id or "",
                    "file_path": file_path or "",
                },
            })

        # POST = set_payload (MERGE) — restores original fields without
        # touching the temporal fields already injected
        for item in points_payload:
            body = {
                "payload": item["payload"],
                "points": [item["qdrant_uuid"]],
            }
            url = f"{QDRANT_URL}/collections/{COLLECTION}/points/payload"
            try:
                resp = session.post(url, data=json.dumps(body), timeout=15)
                resp.raise_for_status()
                result = resp.json()
                if result.get("status") == "ok":
                    restored += 1
                else:
                    logger.warning("Unexpected response for %s: %s", item["qdrant_uuid"], result)
                    errors += 1
            except requests.RequestException as exc:
                logger.error("Error restoring %s: %s", item["qdrant_uuid"], exc)
                errors += 1

        logger.info(
            "Progress: %d/%d (restored=%d, not_found=%d, errors=%d)",
            min(i + BATCH_SIZE, len(rows)), len(rows), restored, not_found, errors
        )

    print("\n--- Restore Summary ---")
    print(f"  Total chunks in PG : {len(rows)}")
    print(f"  Restored           : {restored}")
    print(f"  Errors             : {errors}")


if __name__ == "__main__":
    restore_payloads()
