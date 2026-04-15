#!/usr/bin/env python3
"""Test complete temporal workflow: upload → extract → save metadata → link amendments."""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.clients.lightrag_client import LightRAGAPIClient
from agent.agents.agent_temporal_extraction import TemporalExtractionAgent
from langchain.chat_models import init_chat_model
from agent.config import settings
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env.lightrag")

async def test_workflow():
    """Test the complete temporal metadata workflow."""

    print("=== Temporal Workflow Test ===\n")

    # 1. Initialize clients
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

    # 2. Test document content (from your test file)
    test_content = """
# ĐẠI HỌC QUỐC GIA TP.HCM
TRƯỜNG ĐẠI HỌC CÔNG NGHỆ THÔNG TIN

Số: 108/QĐ-ĐHCNTT
Tp.Hồ Chí Minh, ngày 15 tháng 03 năm 2019

## QUYẾT ĐỊNH

V/v sửa đổi, bổ sung quy định đào tạo ngoại ngữ đối với hệ đại học chính quy

Căn cứ Quyết định số 141/QĐ-ĐHCNTT ngày 16/3/2018

Hiệu lực từ ngày 01/09/2019 đến hết năm học 2024-2025.

Áp dụng cho sinh viên khóa 2024, 2025, 2026, 2027, 2028, 2029.
"""

    print("Step 1: Extract temporal metadata")
    print("-" * 50)
    metadata_dict = await agent.extract(
        content=test_content,
        filename="108-qd-dhcntt.md",
        file_source="test://sample.md"
    )

    print(f"✓ Extracted metadata:")
    print(f"  - Document Number: {metadata_dict.get('document_number')}")
    print(f"  - Valid: {metadata_dict.get('valid_from')} → {metadata_dict.get('valid_until')}")
    print(f"  - Amends: {metadata_dict.get('amends_documents')}")
    print(f"  - Confidence: {metadata_dict.get('temporal_confidence'):.2f}")

    # 3. Upload document
    print("\nStep 2: Upload document to LightRAG")
    print("-" * 50)
    result = client.insert_text(
        text=test_content,
        file_source="test://sample.md"
    )

    track_id = result.get("track_id")
    print(f"✓ Upload started - Track ID: {track_id}")

    # 4. Poll for doc_id
    print("\nStep 3: Poll for doc_id (max 30s)")
    print("-" * 50)
    doc_id = client.get_doc_id_by_track_id(track_id, max_wait_seconds=30) #type: ignore

    if not doc_id:
        print("✗ Failed to get doc_id - timeout")
        return False

    print(f"✓ Got doc_id: {doc_id}")

    # 5. Save temporal metadata
    print("\nStep 4: Save temporal metadata to PostgreSQL")
    print("-" * 50)
    meta_result = client.update_document_metadata(
        doc_id=doc_id,
        metadata=metadata_dict,
        merge=True
    )

    if meta_result.get("success"):
        print(f"✓ Metadata saved successfully")
    else:
        print(f"✗ Failed to save metadata: {meta_result.get('error')}")
        return False

    # 6. Test amendment linking (if applicable)
    amended_docs = metadata_dict.get("amends_documents", [])
    if amended_docs:
        print(f"\nStep 5: Link to amended documents")
        print("-" * 50)
        link_result = client.link_amended_documents(doc_id, amended_docs)

        linked = len(link_result.get("linked_docs", []))
        not_found = len(link_result.get("not_found", []))

        print(f"✓ Linked: {linked} documents")
        if not_found > 0:
            print(f"  Not found: {link_result.get('not_found')}")

    print("\n" + "=" * 50)
    print("✓ Temporal workflow test completed successfully!")
    print("=" * 50)

    return True

if __name__ == "__main__":
    success = asyncio.run(test_workflow())
    sys.exit(0 if success else 1)
