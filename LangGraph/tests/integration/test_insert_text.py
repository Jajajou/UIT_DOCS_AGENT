#!/usr/bin/env python3
"""Test insert_text API response."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.clients.lightrag_client import LightRAGAPIClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env.lightrag")

def test_insert_text():
    """Test what insert_text returns."""

    client = LightRAGAPIClient()

    test_content = "This is a test document for checking the API response."

    print("=== Testing insert_text API ===\n")
    print(f"Content: {test_content}")

    result = client.insert_text(
        text=test_content,
        file_source="test://test.txt"
    )

    print(f"\n=== API Response ===")
    print(f"Type: {type(result)}")
    print(f"Keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
    print(f"\nFull response:")
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))

    print(f"\n=== Extracted Values ===")
    print(f"track_id: {result.get('track_id')}")
    print(f"doc_id: {result.get('doc_id')}")
    print(f"status: {result.get('status')}")

    # Check all possible field names
    possible_keys = ['track_id', 'tracking_id', 'id', 'doc_id', 'document_id', 'task_id']
    print(f"\n=== Checking possible field names ===")
    for key in possible_keys:
        value = result.get(key)
        if value:
            print(f"[FOUND] {key}: {value}")
        else:
            print(f"[MISSING] {key}: Not found")

if __name__ == "__main__":
    test_insert_text()
