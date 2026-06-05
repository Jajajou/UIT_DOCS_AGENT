
import os
import json
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Load env vars manually
if os.path.exists(".env.lightrag"):
    with open(".env.lightrag") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value

qdrant_url = "http://localhost:6336"
client = QdrantClient(url=qdrant_url)
collection_name = 'lightrag_vdb_chunks'

# Total points
total_count = client.count(collection_name).count
print(f"Total points: {total_count}")

# Points with doc_number=null
null_count = client.count(
    collection_name,
    count_filter=models.Filter(
        must=[models.IsNullCondition(is_null=models.PayloadField(key="doc_number"))]
    )
).count
print(f"Points with doc_number=null: {null_count}")

# Points without doc_number field at all
# (In Qdrant, FieldCondition with MatchValue won't find missing. We use scroll to check sample)
points, _ = client.scroll(collection_name, limit=100, with_payload=True)
missing_field_count = 0
unique_doc_ids_missing = set()
for p in points:
    if "doc_number" not in p.payload or p.payload["doc_number"] is None:
        missing_field_count += 1
        unique_doc_ids_missing.add(p.payload.get("doc_id"))

print(f"Sample (first 100): {missing_field_count} missing doc_number")
print(f"Sample unique missing doc_ids: {len(unique_doc_ids_missing)}")
