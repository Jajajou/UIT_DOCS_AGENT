
import os
import json
from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6336")
collection_name = 'lightrag_vdb_chunks'

# Scan all points to find unique full_doc_ids missing document_number
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
        doc_id = p.payload.get("full_doc_id")
        if not doc_id:
            continue
        
        # Check both doc_number and document_number
        if ("document_number" in p.payload and p.payload["document_number"]) or \
           ("doc_number" in p.payload and p.payload["doc_number"]):
            doc_ids_with_doc_number.add(doc_id)
        else:
            doc_ids_missing_doc_number.add(doc_id)
            
    if offset is None:
        break

totally_missing = doc_ids_missing_doc_number - doc_ids_with_doc_number

print(f"Total unique full_doc_ids found: {len(doc_ids_with_doc_number | doc_ids_missing_doc_number)}")
print(f"Doc IDs with document_number: {len(doc_ids_with_doc_number)}")
print(f"Doc IDs totally missing document_number: {len(totally_missing)}")

# Sample of totally missing
if totally_missing:
    sample_id = list(totally_missing)[0]
    print(f"Sample totally missing ID: {sample_id}")
    # Show payload of one chunk from this doc
    p, _ = client.scroll(collection_name, limit=1, with_payload=True, 
                         scroll_filter={"must": [{"key": "full_doc_id", "match": {"value": sample_id}}]})
    if p:
        print(f"Sample payload: {p[0].payload.keys()}")
