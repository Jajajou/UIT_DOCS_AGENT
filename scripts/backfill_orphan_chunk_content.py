"""
Backfill content + full_doc_id into Qdrant chunk points that have workspace_id
but are missing content (orphan points from indexing before restore script ran).

Matches PG chunks to Qdrant points via UUID = sha256(workspace + chunk_id).
"""

import hashlib
import uuid
import sys
import psycopg2
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

WORKSPACE = "uit_docs_agent"
PG_HOST = "localhost"
PG_PORT = 5433
PG_USER = "uitrag"
PG_PASSWORD = "admin123"
PG_DB = "lightrag"
QDRANT_HOST = "localhost"
QDRANT_PORT = 6336
COLLECTION = "lightrag_vdb_chunks"
BATCH_SIZE = 100


def chunk_id_to_uuid(workspace: str, chunk_id: str) -> str:
    h = hashlib.sha256(f"{workspace}{chunk_id}".encode()).digest()[:16]
    return str(uuid.UUID(bytes=h, version=4))


def main(dry_run: bool = False):
    print(f"[backfill] dry_run={dry_run}")

    pg = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DB
    )
    cur = pg.cursor()

    # Fetch all PG chunks for this workspace
    cur.execute(
        """
        SELECT id, full_doc_id, content, file_path
        FROM lightrag_doc_chunks
        WHERE workspace = %s AND content IS NOT NULL AND content != ''
        """,
        (WORKSPACE,),
    )
    pg_chunks = {row[0]: {"full_doc_id": row[1], "content": row[2], "file_path": row[3]} for row in cur.fetchall()}
    print(f"[backfill] PG chunks loaded: {len(pg_chunks)}")
    cur.close()
    pg.close()

    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # Find points missing content OR file_path
    orphan_point_ids = []
    offset = None
    while True:
        pts, next_offset = qdrant.scroll(
            COLLECTION,
            scroll_filter=Filter(
                must=[FieldCondition(key="workspace_id", match=MatchValue(value=WORKSPACE))]
            ),
            offset=offset,
            limit=500,
            with_payload=["content", "full_doc_id", "file_path"],
            with_vectors=False,
        )
        for p in pts:
            if not p.payload.get("content") or not p.payload.get("file_path"):
                orphan_point_ids.append(p.id)
        if next_offset is None:
            break
        offset = next_offset

    print(f"[backfill] Points missing content or file_path: {len(orphan_point_ids)}")

    # Build lookup: computed_uuid -> chunk data
    uuid_to_chunk = {}
    for chunk_id, data in pg_chunks.items():
        computed = chunk_id_to_uuid(WORKSPACE, chunk_id)
        uuid_to_chunk[computed] = {**data, "chunk_id": chunk_id}

    print(f"[backfill] UUID lookup built: {len(uuid_to_chunk)} entries")

    # Match and patch
    matched = 0
    not_found = 0
    errors = 0

    for i in range(0, len(orphan_point_ids), BATCH_SIZE):
        batch = orphan_point_ids[i : i + BATCH_SIZE]
        for point_id in batch:
            pid_str = str(point_id)
            chunk_data = uuid_to_chunk.get(pid_str)
            if not chunk_data:
                not_found += 1
                continue
            payload_update = {
                "content": chunk_data["content"],
                "full_doc_id": chunk_data["full_doc_id"],
            }
            if chunk_data.get("file_path"):
                payload_update["file_path"] = chunk_data["file_path"]
            if dry_run:
                matched += 1
                if matched <= 3:
                    print(f"  [DRY] would patch {pid_str} full_doc_id={chunk_data['full_doc_id']} file_path={chunk_data.get('file_path','')[:60]} content_len={len(chunk_data['content'])}")
            else:
                try:
                    qdrant.set_payload(
                        collection_name=COLLECTION,
                        payload=payload_update,
                        points=[point_id],
                    )
                    matched += 1
                except Exception as e:
                    print(f"  [ERROR] {pid_str}: {e}")
                    errors += 1

        if not dry_run and (i // BATCH_SIZE) % 5 == 0:
            print(f"  progress: {i + len(batch)}/{len(orphan_point_ids)} matched={matched}")

    print(f"\n[backfill] DONE matched={matched} not_found={not_found} errors={errors}")
    if not_found > 0:
        print(f"  {not_found} orphan points had no PG match (may be from old indexing runs)")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
