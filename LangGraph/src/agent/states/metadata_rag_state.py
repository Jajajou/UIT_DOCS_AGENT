from typing import TypedDict, List, Dict, Any, Union, Optional
from typing_extensions import NotRequired

class MetadataRAGState(TypedDict):
    """
    Internal state for the Metadata Extraction RAG Subgraph.
    Documentation: Stores intermediate data like chunks, embeddings, and extraction results.
    """
    
    # --- INPUT (từ Indexing Graph) ---
    doc_text: str
    file_source: str      # Dùng để tạo ID duy nhất cho collection
    doc_id: str           # DB ID (nếu có)
    
    # --- PROCESSING (Internal) ---
    chunks: NotRequired[List[str]]                 # Text chunks (1024 tokens)
    chunk_count: NotRequired[int]
    
    # Vector DB Context
    collection_name: NotRequired[str]              # Tên collection trong ChromaDB (in-memory)
    # Note: Embeddings không cần lưu trong state để tiết kiệm RAM transfer, 
    # nó sẽ được tạo và dùng ngay trong node indexing.
    
    # --- QUERY RESULTS (Raw Chunks từ Reranker) ---
    # Lưu lại để debug hoặc verify nếu cần
    document_number_chunks: NotRequired[List[str]]
    valid_from_chunks: NotRequired[List[str]]
    valid_until_chunks: NotRequired[List[str]]
    cohort_years_chunks: NotRequired[List[str]]
    amends_documents_chunks: NotRequired[List[str]]
    concept_chunks: NotRequired[List[str]]
    
    # --- EXTRACTED METADATA (Final Output) ---
    document_number: NotRequired[Optional[str]]
    document_type: NotRequired[Optional[str]]        # "Quyết định", "Thông báo", etc.
    issuing_authority: NotRequired[Optional[str]]    # "Hiệu trưởng", "Phòng Đào tạo"
    
    concept_id: NotRequired[Optional[str]]           # For Canonical Registry Mapping
    
    valid_from: NotRequired[Optional[str]]
    valid_until: NotRequired[Optional[str]]
    academic_year: NotRequired[Optional[str]]
    
    cohort_years: NotRequired[List[Union[int, str]]] # [2024, 2025] hoặc ["*"]
    cohort_scope: NotRequired[str]                   # "universal", "explicit", "unspecified"
    
    amends_documents: NotRequired[List[str]]
    
    extraction_confidence: NotRequired[float]        # 0.0 to 1.0
    
    # --- HITL (Human-in-the-Loop) ---
    human_feedback: NotRequired[Optional[str]]
    loop_count: NotRequired[int]                     # Max 1 retry
    review_status: NotRequired[str]                 # "pending", "approved", "rejected", "edited"
    
    # --- OUTPUT (Trả về Parent Graph) ---
    final_metadata: NotRequired[Dict[str, Any]]      # Dict hoàn chỉnh để save vào DB
    document_metadata: NotRequired[Dict[str, Any]]   # Shared key with IndexingState for subgraph→parent merge
    temporal_extraction_complete: NotRequired[bool]
    success: bool
    error: NotRequired[str]