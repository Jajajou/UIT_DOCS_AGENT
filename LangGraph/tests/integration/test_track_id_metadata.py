#!/usr/bin/env python3
"""Test metadata update using track_id (no polling needed)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.clients.lightrag_client import LightRAGAPIClient
from agent.agents.agent_temporal_extraction import TemporalExtractionAgent
from langchain.chat_models import init_chat_model
from agent.config import settings
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env.lightrag")

async def test_track_id_workflow():
    """Test complete workflow using track_id instead of doc_id polling."""

    print("=== Track ID Metadata Update Test ===\n")

    # 1. Initialize
    client = LightRAGAPIClient()
    llm = init_chat_model(
        model_provider="openai",
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.llm_model,
        streaming=False,
        temperature=0.1,
        model_kwargs={"tool_choice": "none"}
    )
    agent = TemporalExtractionAgent(llm, settings)

    # 2. Test content
    test_content = """
# ĐẠI HỌC QUỐC GIA TP.HCM
TRƯỜNG ĐẠI HỌC CÔNG NGHỆ THÔNG TIN

Số: 108/QĐ-ĐHCNTT
Tp.Hồ Chí Minh, ngày 15 tháng 03 năm 2019

## QUYẾT ĐỊNH
V/v sửa đổi, bổ sung quy định đào tạo ngoại ngữ

Căn cứ Quyết định số 141/QĐ-ĐHCNTT ngày 16/3/2018

Hiệu lực từ ngày 01/09/2019 đến hết năm học 2024-2025.
"""

    # 3. Extract metadata
    print("Step 1: Extract temporal metadata")
    print("-" * 50)
    metadata_dict = await agent.extract(
        content=test_content,
        filename="108-qd-dhcntt.md",
        file_source="test://sample.md"
    )
    print(f"✓ Document Number: {metadata_dict.get('document_number')}")
    print(f"✓ Amends: {metadata_dict.get('amends_documents')}")

    # 4. Upload document (use unique filename to avoid duplicates)
    print("\nStep 2: Upload document")
    print("-" * 50)
    import time
    unique_filename = f"test://sample_{int(time.time())}.md"
    result = client.insert_text(
        text=test_content,
        file_source=unique_filename
    )

    track_id = result.get("track_id")
    print(f"✓ Upload response: {result}")
    print(f"✓ Track ID: {track_id}")

    if not track_id:
        print("✗ No track_id in response!")
        return False

    # 5. Save metadata using track_id (NO POLLING!)
    print("\nStep 3: Save metadata using track_id")
    print("-" * 50)
    meta_result = client.update_document_metadata_by_track_id(
        track_id=track_id,
        metadata=metadata_dict,
        merge=True
    )

    if meta_result.get("success"):
        doc_id = meta_result.get("doc_id")
        print(f"✓ Metadata saved successfully")
        print(f"✓ Doc ID: {doc_id}")

        # 6. Test amendment linking
        amended_docs = metadata_dict.get("amends_documents", [])
        if amended_docs:
            print(f"\nStep 4: Link to amended documents")
            print("-" * 50)
            link_result = client.link_amended_documents(doc_id, amended_docs)

            linked = len(link_result.get("linked_docs", []))
            not_found = link_result.get("not_found", [])

            print(f"✓ Linked: {linked} documents")
            if not_found:
                print(f"  Not found: {not_found}")

        print("\n" + "=" * 50)
        print("✓ Track ID workflow test completed successfully!")
        print("=" * 50)
        return True
    else:
        print(f"✗ Failed to save metadata: {meta_result.get('error')}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_track_id_workflow())
    sys.exit(0 if success else 1)
