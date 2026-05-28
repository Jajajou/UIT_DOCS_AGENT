import requests
import json
import os
import sys
import argparse

# Configuration
QDRANT_BASE_URL = os.environ.get("QDRANT_BASE_URL", "http://localhost:6336")
COLLECTION_NAME = "lightrag_vdb_chunks"

def update_qdrant_for_doc(doc_id: str, education_system: str, dry_run: bool = False) -> bool:
    """Update education_system payload for all points belonging to a doc_id."""
    url = f"{QDRANT_BASE_URL}/collections/{COLLECTION_NAME}/points/payload"
    
    # We use a filter to target all chunks of this document
    body = {
        "payload": {"education_system": education_system},
        "filter": {
            "must": [
                {"key": "full_doc_id", "match": {"value": doc_id}}
            ]
        }
    }
    
    if dry_run:
        print(f"[DRY-RUN] Would update {doc_id} -> {education_system}")
        return True
        
    try:
        r = requests.put(url, json=body, timeout=30)
        if r.status_code == 200:
            print(f"✓ Updated {doc_id} -> {education_system}")
            return True
        else:
            print(f"✗ Failed to update {doc_id}: {r.status_code} {r.text}")
            return False
    except Exception as e:
        print(f"✗ Error updating {doc_id}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Backfill education_system field in Qdrant")
    parser.add_argument("classifications", help="Path to JSON file with {doc_id: education_system} mapping")
    parser.add_argument("--dry-run", action="store_true", help="Print updates without sending to Qdrant")
    args = parser.parse_args()

    if not os.path.exists(args.classifications):
        print(f"Error: File not found {args.classifications}")
        sys.exit(1)

    with open(args.classifications, "r") as f:
        mapping = json.load(f)

    print(f"Starting backfill for {len(mapping)} documents...")
    
    success_count = 0
    for doc_id, edu_system in mapping.items():
        if update_qdrant_for_doc(doc_id, edu_system, args.dry_run):
            success_count += 1

    print(f"\nDone. Successfully processed {success_count}/{len(mapping)} documents.")

if __name__ == "__main__":
    main()
