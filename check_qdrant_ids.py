from qdrant_client import QdrantClient
from qdrant_client.http import models

client = QdrantClient(url="http://localhost:6336")
collection_name = 'lightrag_vdb_chunks'

doc_ids = [
    'doc-bb3827f1635e67657bc975af8a489b00',
    'doc-75e95d97488ffe01869f552ead853ddc'
]

for doc_id in doc_ids:
    points, _ = client.scroll(
        collection_name=collection_name,
        scroll_filter=models.Filter(
            must=[models.FieldCondition(key="full_doc_id", match=models.MatchValue(value=doc_id))]
        ),
        limit=1
    )
    if points:
        print(f"Found points for {doc_id}: {len(points)}")
        print(f"Payload: {points[0].payload}")
    else:
        print(f"No points found for {doc_id}")
