"""
Backfill content, file_path, full_doc_id from lightrag_doc_chunks (PG)
into Qdrant lightrag_vdb_chunks payload.

These fields are required by LightRAG's _get_vector_context (operate.py:3404)
and by QdrantCohortClient._point_to_chunk. Without them, vector search
returns 0 valid chunks.

Run: python scripts/backfill_qdrant_content.py [--dry-run]
"""

import argparse
import hashlib
import sys
import uuid

import psycopg2
from qdrant_client import QdrantClient

POSTGRES_DSN = dict(host="localhost", port=5433, user="uitrag", password="admin123", dbname="lightrag")
QDRANT_HOST = "localhost"
QDRANT_PORT = 6336
COLLECTION = "lightrag_vdb_chunks"
BATCH = 200
WORKSPACE = "uit_docs_agent"


def chunk_uuid(namespace: str, chunk_id: str) -> str:
    """Match LightRAG's compute_mdhash_id_for_qdrant formula."""
    raw = hashlib.sha256((namespace + chunk_id).encode("utf-8")).digest()[:16]
    generated = uuid.UUID(bytes=raw, version=4)
    return generated.hex  # LightRAG uses hex (no hyphens); Qdrant normalises both


def main(dry_run: bool = False) -> None:
    pg = psycopg2.connect(**POSTGRES_DSN)
    qc = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    cur = pg.cursor()

    cur.execute("""
        SELECT id, content, file_path, full_doc_id
        FROM lightrag_doc_chunks
        WHERE workspace = %s
          AND content IS NOT NULL
          AND content != ''
        ORDER BY id
    """, (WORKSPACE,))
    rows = cur.fetchall()
    print(f"PG chunks with content: {len(rows)}")

    found = 0
    not_found = 0
    updated_pts = 0

    batch_ids = []
    batch_payloads = []

    def flush_batch():
        nonlocal updated_pts
        if not batch_ids or dry_run:
            return
        for pt_id, payload in zip(batch_ids, batch_payloads):
            qc.set_payload(
                collection_name=COLLECTION,
                payload=payload,
                points=[pt_id],
            )
        updated_pts += len(batch_ids)
        batch_ids.clear()
        batch_payloads.clear()

    for chunk_id, content, file_path, full_doc_id in rows:
        pt_id = chunk_uuid(WORKSPACE, chunk_id)

        # Verify point exists in Qdrant
        result = qc.retrieve(COLLECTION, ids=[pt_id], with_payload=False)
        if not result:
            not_found += 1
            if not_found <= 5:
                print(f"  NOT FOUND: chunk={chunk_id[:20]} uuid={pt_id[:16]}")
            continue

        found += 1
        payload = {
            "content": content,
            "file_path": file_path or "",
            "full_doc_id": full_doc_id or "",
        }
        batch_ids.append(pt_id)
        batch_payloads.append(payload)

        if len(batch_ids) >= BATCH:
            flush_batch()
            print(f"  Progress: {found} found, {not_found} not_found, {updated_pts} updated...")

    flush_batch()

    print(f"\nDone. found={found} not_found={not_found} updated={updated_pts}")
    if not_found > 0:
        print(f"WARNING: {not_found} PG chunks not in Qdrant — UUID mismatch or not indexed")
    if dry_run:
        print("DRY RUN — no changes written")

    cur.close()
    pg.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
