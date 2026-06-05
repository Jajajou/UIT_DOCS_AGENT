from qdrant_client import QdrantClient
from qdrant_client.http import models

client = QdrantClient(url="http://localhost:6336")
collection_name = 'lightrag_vdb_chunks'

updates = [
    ('doc-bb3827f1635e67657bc975af8a489b00', '671/ĐHQG-ĐT'),
    ('doc-75e95d97488ffe01869f552ead853ddc', '1681/QĐ-ĐHQG')
]

for doc_id, doc_num in updates:
    print(f"Updating {doc_id} with {doc_num}...")
    # Scroll to get all point IDs for this doc
    offset = None
    all_point_ids = []
    while True:
        points, offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="full_doc_id", match=models.MatchValue(value=doc_id))]
            ),
            limit=500,
            offset=offset,
            with_payload=False
        )
        all_point_ids.extend([p.id for p in points])
        if offset is None:
            break
    
    print(f"Found {len(all_point_ids)} points. Updating...")
    
    if all_point_ids:
        client.set_payload(
            collection_name=collection_name,
            payload={"document_number": doc_num},
            points=all_point_ids
        )
        print(f"Done for {doc_id}.")
    else:
        print(f"No points for {doc_id}?")

print("All updates finished.")
