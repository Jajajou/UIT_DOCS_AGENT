
import os
import json
from qdrant_client import QdrantClient

# Load env vars
if os.path.exists(".env.lightrag"):
    with open(".env.lightrag") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value

client = QdrantClient(url="http://localhost:6336")
collection_name = 'lightrag_vdb_chunks'

# Scan all points to find unique doc_ids missing doc_number
doc_ids_missing_doc_number = set()
doc_ids_with_doc_number = set()

offset = None
while True:
    points, offset = client.scroll(
        collection_name=collection_name,
        limit=500,
        with_payload=True,
        offset=offset
    )
    for p in points:
        doc_id = p.payload.get("doc_id")
        if not doc_id:
            continue
        
        if "doc_number" in p.payload and p.payload["doc_number"]:
            doc_ids_with_doc_number.add(doc_id)
        else:
            doc_ids_missing_doc_number.add(doc_id)
            
    if offset is None:
        break

# A doc_id might have some chunks with doc_number and some without if backfill was partial.
# Let's see docs that have NO chunks with doc_number.
totally_missing = doc_ids_missing_doc_number - doc_ids_with_doc_number

print(f"Total unique doc_ids found: {len(doc_ids_with_doc_number | doc_ids_missing_doc_number)}")
print(f"Doc IDs with doc_number: {len(doc_ids_with_doc_number)}")
print(f"Doc IDs missing doc_number (on at least one chunk): {len(doc_ids_missing_doc_number)}")
print(f"Doc IDs totally missing doc_number: {len(totally_missing)}")

# Sample of totally missing
print(f"Sample totally missing: {list(totally_missing)[:5]}")
