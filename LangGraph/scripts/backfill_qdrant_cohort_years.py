"""
Backfill cohort_years (and cohort_scope) from temporal_metadata PostgreSQL table
into Qdrant chunk payloads.

Matches by computing Qdrant point UUIDs from PG chunk IDs (no payload index needed).

Run: python scripts/backfill_qdrant_cohort_years.py
"""

import hashlib
import sys
import uuid

import psycopg2
from qdrant_client import QdrantClient

POSTGRES_DSN = dict(host="localhost", port=5433, user="uitrag", password="admin123", dbname="lightrag")
QDRANT_HOST = "localhost"
QDRANT_PORT = 6336
COLLECTION = "lightrag_vdb_chunks"
BATCH = 100
WORKSPACE = "uit_docs_agent"


def chunk_uuid(namespace: str, chunk_id: str) -> str:
    raw = hashlib.sha256(f"{namespace}{chunk_id}".encode()).digest()[:16]
    b = bytearray(raw)
    b[6] = (b[6] & 0x0F) | 0x40  # version 4
    b[8] = (b[8] & 0x3F) | 0x80  # RFC 4122 variant
    return str(uuid.UUID(bytes=bytes(b)))


def main() -> None:
    pg = psycopg2.connect(**POSTGRES_DSN)
    qc = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    cur = pg.cursor()
    # Get all docs with cohort_years set
    cur.execute("""
        SELECT tm.doc_id, tm.cohort_years, tm.cohort_scope, tm.document_number
        FROM temporal_metadata tm
        WHERE tm.cohort_years IS NOT NULL
          AND tm.cohort_years::text NOT IN ('[]', 'null')
    """)
    docs = cur.fetchall()
    print(f"Docs with cohort_years in DB: {len(docs)}")

    updated_points = 0
    updated_docs = 0

    for doc_id, cohort_years, cohort_scope, document_number in docs:
        # Get PG chunk IDs for this doc
        cur.execute(
            "SELECT id FROM lightrag_doc_chunks WHERE full_doc_id = %s AND workspace = %s",
            (doc_id, WORKSPACE),
        )
        chunk_rows = cur.fetchall()
        if not chunk_rows:
            print(f"  SKIP {document_number or doc_id[:16]} — no chunks in PG")
            continue

        # Compute Qdrant UUIDs
        point_ids = [chunk_uuid(WORKSPACE, row[0]) for row in chunk_rows]

        # Verify at least one exists in Qdrant
        sample = qc.retrieve(COLLECTION, ids=point_ids[:1], with_payload=False)
        if not sample:
            print(f"  SKIP {document_number or doc_id[:16]} — chunks not in Qdrant (UUID mismatch?)")
            continue

        # Batch-update payload
        for i in range(0, len(point_ids), BATCH):
            batch_ids = point_ids[i:i + BATCH]
            qc.set_payload(
                collection_name=COLLECTION,
                payload={
                    "cohort_years": cohort_years,
                    "cohort_scope": cohort_scope or "explicit",
                    "document_number": document_number or "",
                },
                points=batch_ids,
            )

        updated_points += len(point_ids)
        updated_docs += 1
        print(f"  OK {document_number or doc_id[:24]}  cohort_years={cohort_years}  points={len(point_ids)}")

    pg.close()
    print(f"\nDone. Updated {updated_docs} docs, {updated_points} Qdrant points.")


if __name__ == "__main__":
    main()
