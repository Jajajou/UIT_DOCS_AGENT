"""
Sync PostgreSQL Metadata to Qdrant

This script reads updated temporal and cohort metadata from PostgreSQL 
and synchronizes it to the corresponding points in the Qdrant vector database.
"""

import os
import sys
import asyncio
import json
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from qdrant_client import QdrantClient, models

# Add LangGraph/src to path for settings
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "LangGraph" / "src"))
from agent.config import settings

# Load project environment
load_dotenv(ROOT / ".env.lightrag")

# --- Configuration ---
WORKSPACE = "uit_docs_agent"
QDRANT_URL = "http://localhost:6336"
QDRANT_COLLECTION = "lightrag_vdb_chunks"

def get_pg_connection():
    return psycopg2.connect(
        host="localhost",
        port=5433,
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        database=os.getenv("POSTGRES_DATABASE", "lightrag")
    )

async def sync():
    print("=== Syncing PostgreSQL Metadata to Qdrant ===")
    
    # 1. Connect to Qdrant
    q_client = QdrantClient(url=QDRANT_URL)
    print(f"Connected to Qdrant at {QDRANT_URL}")

    # 2. Connect to PG
    conn = get_pg_connection()
    print("Connected to PostgreSQL")
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Query all metadata for the workspace
            cur.execute("""
                SELECT doc_id, valid_from, valid_until, academic_year, 
                       cohort_years, document_type, document_number, 
                       amends_documents, is_archived, additional_metadata
                FROM temporal_metadata
                WHERE workspace = %s
            """, (WORKSPACE,))
            
            docs_metadata = cur.fetchall()
            print(f"Found {len(docs_metadata)} documents to sync.")
            
            total_points_updated = 0
            
            for doc in docs_metadata:
                doc_id = doc['doc_id']
                
                # Combine standard and additional metadata
                payload = {
                    "valid_from": doc['valid_from'],
                    "valid_until": doc['valid_until'],
                    "academic_year": doc['academic_year'],
                    "cohort_years": doc['cohort_years'],
                    "document_type": doc['document_type'],
                    "document_number": doc['document_number'],
                    "amends_documents": doc['amends_documents'],
                    "is_archived": doc['is_archived']
                }
                
                if doc['additional_metadata']:
                    payload.update(doc['additional_metadata'])
                
                # Update Qdrant points where doc_id matches
                # LightRAG stores doc_id in the payload of chunks
                
                # First, find all points with this doc_id
                search_result = q_client.scroll(
                    collection_name=QDRANT_COLLECTION,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="full_doc_id",
                                match=models.MatchValue(value=doc_id),
                            )
                        ]
                    ),
                    limit=1000,
                    with_payload=True,
                    with_vectors=False
                )
                
                points = search_result[0]
                if not points:
                    # Try file_path if doc_id didn't work (some older versions might differ)
                    # We can't easily guess file_path here without joining more tables,
                    # but let's stick to doc_id for now as it's the standard.
                    continue
                
                # Bulk update payload for these points
                point_ids = [p.id for p in points]
                
                q_client.set_payload(
                    collection_name=QDRANT_COLLECTION,
                    payload=payload,
                    points=point_ids
                )
                
                total_points_updated += len(point_ids)
                if len(point_ids) > 0:
                    print(f"  ✓ Updated {len(point_ids)} points for doc {doc_id} ({doc['document_number']})")

            print(f"=== Sync Complete: {total_points_updated} total points updated across Qdrant ===")

    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(sync())
