"""
Backfill Qdrant vectors for docs that have KV chunks in lightrag_doc_chunks
but no vector points in Qdrant lightrag_vdb_chunks.

Root cause: embedding step failed silently during indexing run on 2026-05-30
for 8 specific docs. This script embeds their chunks and upserts to Qdrant.

Run: python scripts/backfill_missing_vectors.py [--dry-run] [--doc-id DOC_ID]
"""

import argparse
import hashlib
import json
import sys
import uuid

import psycopg2
import requests
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

POSTGRES_DSN = dict(host="localhost", port=5433, user="uitrag", password="admin123", dbname="lightrag")
QDRANT_HOST = "localhost"
QDRANT_PORT = 6336
COLLECTION = "lightrag_vdb_chunks"
WORKSPACE = "uit_docs_agent"
EMBED_URL = "http://localhost:8000/v1/embeddings"
EMBED_MODEL = "AITeamVN/Vietnamese_Embedding_V2"
EMBED_BATCH = 32

# 8 docs confirmed missing from Qdrant (identified 2026-06-02)
MISSING_DOCS = [
    "doc-0b136887e781405ef424ce8c1fb054e3",  # 131/QĐ-ĐHCNTT
    "doc-423894a05199de23688f25c150c9ebda",  # 1314/QĐ-BGDĐT
    "doc-88616ad3e652eb2aea6df385745c3293",
    "doc-9c926ef5e4e5c4236f89a31abb3c1ca7",  # 434/QĐ-ĐHCNTT (old URL)
    "doc-b19922ed133e6244f7219b00491b3dbf",  # 15/QĐ-ĐHQG (2018)
    "doc-bdaffd543528fa85a98de696b3f74de8",  # 15/QĐ-ĐHQG (2025 new)
    "doc-e5c1ca87e57a5d47830ec21bdf44e016",  # 1032/QĐ-ĐHCNTT
    "doc-ed24ff475a86f2525fede5206c9c836f",  # 434/QĐ-ĐHCNTT (new URL)
]


def chunk_uuid(namespace: str, chunk_id: str) -> str:
    """Match LightRAG's compute_mdhash_id_for_qdrant formula."""
    raw = hashlib.sha256((namespace + chunk_id).encode("utf-8")).digest()[:16]
    return uuid.UUID(bytes=raw, version=4).hex


def embed_texts(texts: list[str]) -> list[list[float]]:
    resp = requests.post(
        EMBED_URL,
        json={"model": EMBED_MODEL, "input": texts},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    data.sort(key=lambda x: x["index"])
    return [item["embedding"] for item in data]


def get_temporal_payload(cur, doc_id: str) -> dict:
    cur.execute(
        """
        SELECT document_number, cohort_years, cohort_scope, valid_from, valid_until,
               is_archived, education_system, amends_documents
        FROM temporal_metadata
        WHERE doc_id = %s
        """,
        (doc_id,),
    )
    row = cur.fetchone()
    if not row:
        return {
            "document_number": "",
            "cohort_years": ["*"],
            "cohort_scope": "universal",
            "valid_from": None,
            "valid_until": None,
            "is_archived": False,
            "education_system": "",
            "amends_documents": [],
        }
    doc_num, cohort_years, cohort_scope, valid_from, valid_until, is_archived, edu_sys, amends = row
    return {
        "document_number": doc_num or "",
        "cohort_years": cohort_years if cohort_years else ["*"],
        "cohort_scope": cohort_scope or "universal",
        "valid_from": valid_from.isoformat() if valid_from else None,
        "valid_until": valid_until.isoformat() if valid_until else None,
        "is_archived": bool(is_archived),
        "education_system": edu_sys or "",
        "amends_documents": amends if amends else [],
    }


def main(dry_run: bool = False, target_docs: list[str] | None = None) -> None:
    docs_to_fix = target_docs or MISSING_DOCS
    print(f"Backfilling vectors for {len(docs_to_fix)} docs. dry_run={dry_run}")

    pg = psycopg2.connect(**POSTGRES_DSN)
    qc = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    cur = pg.cursor()

    total_inserted = 0

    for doc_id in docs_to_fix:
        # Verify still missing from Qdrant
        cur.execute(
            "SELECT id, content, file_path FROM lightrag_doc_chunks WHERE full_doc_id = %s AND workspace = %s ORDER BY chunk_order_index",
            (doc_id, WORKSPACE),
        )
        chunks = cur.fetchall()
        if not chunks:
            print(f"[SKIP] {doc_id[:24]}: no KV chunks found")
            continue

        temporal = get_temporal_payload(cur, doc_id)
        file_path = chunks[0][2] or ""
        print(f"[DOC] {doc_id[:24]} ({len(chunks)} chunks) file={file_path.split('/')[-1][:50]}")
        print(f"      docnum={temporal['document_number']} cohort={temporal['cohort_scope']}")

        # Embed in batches
        chunk_ids = [c[0] for c in chunks]
        chunk_texts = [c[1] for c in chunks]
        chunk_files = [c[2] or "" for c in chunks]

        all_vectors: list[list[float]] = []
        for i in range(0, len(chunk_texts), EMBED_BATCH):
            batch = chunk_texts[i : i + EMBED_BATCH]
            vecs = embed_texts(batch)
            all_vectors.extend(vecs)
            print(f"      embedded {min(i + EMBED_BATCH, len(chunk_texts))}/{len(chunk_texts)}")

        # Build Qdrant points
        points = []
        for chunk_id, text, fp, vec in zip(chunk_ids, chunk_texts, chunk_files, all_vectors):
            pt_id = chunk_uuid(WORKSPACE, chunk_id)
            payload = {
                **temporal,
                "content": text,
                "file_path": fp,
                "full_doc_id": doc_id,
                "workspace_id": WORKSPACE,
            }
            points.append(PointStruct(id=pt_id, vector=vec, payload=payload))

        if dry_run:
            print(f"      [DRY RUN] would upsert {len(points)} points")
            continue

        qc.upsert(collection_name=COLLECTION, points=points)
        total_inserted += len(points)
        print(f"      upserted {len(points)} points")

    print(f"\nDone. total_inserted={total_inserted}")
    cur.close()
    pg.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--doc-id", help="Backfill single doc_id only")
    args = parser.parse_args()

    target = [args.doc_id] if args.doc_id else None
    main(dry_run=args.dry_run, target_docs=target)
