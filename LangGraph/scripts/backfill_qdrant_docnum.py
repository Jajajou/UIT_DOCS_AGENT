"""
Backfill document_number (and amends_documents, is_archived) from temporal_metadata
into Qdrant chunk payloads.

Chunks indexed before temporal extraction have document_number='' in Qdrant,
causing them to be invisible in retrieved_doc_numbers during eval.

Run: python scripts/backfill_qdrant_docnum.py
"""

import hashlib
import sys
import uuid

import psycopg2
from qdrant_client import QdrantClient
from qdrant_client.models import PointIdsList

POSTGRES_DSN = dict(host="localhost", port=5433, user="uitrag", password="admin123", dbname="lightrag")
QDRANT_HOST = "localhost"
QDRANT_PORT = 6336
COLLECTION = "lightrag_vdb_chunks"
BATCH = 100
WORKSPACE = "uit_docs_agent"


def chunk_uuid(namespace: str, chunk_id: str) -> str:
    raw = hashlib.sha256(f"{namespace}{chunk_id}".encode()).digest()[:16]
    b = bytearray(raw)
    b[6] = (b[6] & 0x0F) | 0x40
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


def main() -> None:
    pg = psycopg2.connect(**POSTGRES_DSN)
    qc = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    cur = pg.cursor()

    # All docs with document_number in temporal_metadata
    cur.execute("""
        SELECT doc_id, document_number, amends_documents, is_archived
        FROM temporal_metadata
        WHERE workspace = %s
          AND document_number IS NOT NULL
          AND document_number != ''
    """, (WORKSPACE,))
    docs = cur.fetchall()
    print(f"Docs with document_number in temporal_metadata: {len(docs)}")

    updated_points = 0
    updated_docs = 0
    skipped = 0

    for doc_id, document_number, amends_documents, is_archived in docs:
        cur.execute(
            "SELECT id FROM lightrag_doc_chunks WHERE full_doc_id = %s AND workspace = %s",
            (doc_id, WORKSPACE),
        )
        chunk_rows = cur.fetchall()
        if not chunk_rows:
            skipped += 1
            continue

        point_ids = [chunk_uuid(WORKSPACE, row[0]) for row in chunk_rows]

        payload = {
            "document_number": document_number,
            "is_archived": bool(is_archived),
        }
        if amends_documents:
            import json
            amends = amends_documents if isinstance(amends_documents, list) else json.loads(amends_documents)
            payload["amends_documents"] = amends

        # Batch update
        for i in range(0, len(point_ids), BATCH):
            batch = point_ids[i:i + BATCH]
            qc.set_payload(
                collection_name=COLLECTION,
                payload=payload,
                points=batch,
            )

        updated_points += len(point_ids)
        updated_docs += 1
        print(f"  {document_number}: {len(point_ids)} chunks updated")

    print(f"\nDone: {updated_docs} docs, {updated_points} points updated, {skipped} skipped (no chunks)")


if __name__ == "__main__":
    main()
