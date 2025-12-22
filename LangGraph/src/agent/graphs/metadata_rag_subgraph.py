"""
Metadata RAG Subgraph

This subgraph handles temporal metadata extraction from documents using a dedicated RAG pipeline.

Architecture:
1. Chunk document (1024 tokens, large chunks for metadata context)
2. Index to in-memory ChromaDB (temporary vector DB)
3. Query for each metadata field (document_number, dates, cohorts, amendments)
4. Calculate extraction confidence
5. Format and validate metadata with Pydantic
6. Cleanup temporary vector DB

Input (from parent IndexingState):
    - doc_text: Full document text
    - file_source: Document filename/path
    - doc_id: Document ID from LightRAG

Output (to parent IndexingState):
    - final_metadata: Dict[str, Any] with validated temporal metadata
    - success: bool
    - error: Optional error message
"""

from langgraph.graph import StateGraph, END
from ..states.metadata_rag_state import MetadataRAGState
from ..agents.metadata_rag_nodes import (
    chunk_document_node,
    index_to_vector_db_node,
    query_metadata_fields_node,
    calculate_confidence_node,
    format_metadata_node,
    cleanup_node
)
import logging

logger = logging.getLogger(__name__)


def create_metadata_rag_subgraph() -> StateGraph:
    """
    Create the Metadata RAG subgraph.

    Returns:
        Compiled StateGraph for metadata extraction
    """
    # Create subgraph
    graph = StateGraph(MetadataRAGState)

    # Add nodes
    graph.add_node("chunk_document", chunk_document_node)
    graph.add_node("index_to_vector_db", index_to_vector_db_node)
    graph.add_node("query_metadata", query_metadata_fields_node)
    graph.add_node("calculate_confidence", calculate_confidence_node)
    graph.add_node("format_metadata", format_metadata_node)
    graph.add_node("cleanup", cleanup_node)

    # Set entry point
    graph.set_entry_point("chunk_document")

    # Add edges (linear flow)
    graph.add_edge("chunk_document", "index_to_vector_db")
    graph.add_edge("index_to_vector_db", "query_metadata")
    graph.add_edge("query_metadata", "calculate_confidence")
    graph.add_edge("calculate_confidence", "format_metadata")
    graph.add_edge("format_metadata", "cleanup")
    graph.add_edge("cleanup", END)

    logger.info("Metadata RAG subgraph created successfully")

    return graph


# Compile the subgraph
metadata_rag_subgraph = create_metadata_rag_subgraph().compile()


# For testing the subgraph in isolation
async def test_metadata_rag_subgraph(doc_text: str, file_source: str, doc_id: str):
    """
    Test the metadata RAG subgraph with a sample document.

    Args:
        doc_text: Full document text
        file_source: Document filename
        doc_id: Document ID

    Returns:
        Final metadata extraction result
    """
    initial_state = {
        "doc_text": doc_text,
        "file_source": file_source,
        "doc_id": doc_id,
        "success": False
    }

    logger.info(f"Testing Metadata RAG subgraph with document: {file_source}")

    # Run the subgraph
    result = await metadata_rag_subgraph.ainvoke(initial_state)

    logger.info(f"Test result: success={result.get('success')}")
    logger.info(f"Extracted metadata: {result.get('final_metadata')}")
    logger.info(f"Confidence: {result.get('extraction_confidence')}")

    if result.get("error"):
        logger.error(f"Error: {result.get('error')}")

    return result


if __name__ == "__main__":
    """
    Test script for running the subgraph in isolation.

    Usage:
        python -m agent.graphs.metadata_rag_subgraph
    """
    import asyncio

    sample_doc = """
    TRƯỜNG ĐẠI HỌC CÔNG NGHỆ THÔNG TIN
    ĐHQG - HCM

    QUYẾT ĐỊNH
    Về việc ban hành Quy định điểm danh sinh viên

    HIỆU TRƯỞNG TRƯỜNG ĐẠI HỌC CÔNG NGHỆ THÔNG TIN

    Căn cứ Luật Giáo dục đại học...
    Xét đề nghị của Trưởng phòng Đào tạo,

    QUYẾT ĐỊNH:

    Điều 1. Ban hành kèm theo Quyết định này Quy định về điểm danh sinh viên
    áp dụng cho sinh viên khóa tuyển sinh từ năm 2024 đến năm 2028.

    Điều 2. Quyết định này có hiệu lực từ ngày ký và thay thế Quyết định số 141/QĐ-ĐHCNTT
    ngày 15/08/2023.

    Nơi nhận:                           HIỆU TRƯỞNG
    - ...                               (Đã ký)
    - ...
                                        TS. Nguyễn Tấn Trần Minh Khang

    Số: 108/QĐ-ĐHCNTT
    TP.HCM, ngày 01 tháng 09 năm 2024
    """

    async def run_test():
        result = await test_metadata_rag_subgraph(
            doc_text=sample_doc,
            file_source="QD_108_QD_DHCNTT_2024.pdf",
            doc_id="test_doc_123"
        )
        print("\n" + "="*80)
        print("FINAL RESULT:")
        print("="*80)
        print(f"Success: {result.get('success')}")
        print(f"Metadata: {result.get('final_metadata')}")
        print(f"Confidence: {result.get('extraction_confidence')}")
        if result.get('error'):
            print(f"Error: {result.get('error')}")

    asyncio.run(run_test())
