"""
Extended State Schema for 2-Agent RAG Pipeline with Confidence Scoring.

This module defines the state schema for a sophisticated RAG pipeline that includes:
- Agent 1: Query Understanding with confidence scoring
- Agent 2: Data Quality Assessment and Response Generation
- Fallback mechanisms for low confidence scenarios
"""

from __future__ import annotations

from typing import TypedDict, Literal, Optional, List, Dict, Any, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from typing_extensions import NotRequired
from pydantic import BaseModel, Field


# ============================================================================
# Pydantic Models for Structured Outputs
# ============================================================================

class QueryUnderstanding(BaseModel):
    """Structured output from Agent 1: Query Understanding."""
    
    parsed_intention: str = Field(
        description="Ý định rõ ràng của user sau khi phân tích, có thể là rephrase của query gốc"
    )
    extracted_entities: List[str] = Field(
        default_factory=list,
        description="Các thực thể quan trọng được trích xuất từ query (tên phòng ban, quy chế, học bổng...)"
    )
    extracted_topics: List[str] = Field(
        default_factory=list,
        description="Các chủ đề chính của query (quy chế đào tạo, học bổng, thủ tục hành chính...)"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Độ tự tin về việc hiểu đúng ý định của user (0.0 - 1.0)"
    )
    confidence_reason: str = Field(
        description="Lý do cụ thể cho confidence score (query rõ ràng/mơ hồ, đủ context hay không...)"
    )
    needs_clarification: bool = Field(
        description="Có cần hỏi lại user để làm rõ query không"
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="Câu hỏi để clarify nếu needs_clarification=True"
    )


class Reference(BaseModel):
    """Reference to a source document with optional hyperlink."""
    
    title: str = Field(
        description="Tên/tiêu đề của tài liệu tham khảo"
    )
    url: Optional[str] = Field(
        default=None,
        description="URL trực tiếp đến tài liệu (nếu có từ file_source)"
    )
    relevance: float = Field(
        ge=0.0,
        le=1.0,
        description="Độ liên quan của tài liệu này đến câu trả lời (0.0 - 1.0)"
    )
    excerpt: Optional[str] = Field(
        default=None,
        description="Trích dẫn ngắn từ tài liệu (nếu cần)"
    )


class DataQualityAssessment(BaseModel):
    """Assessment of retrieved data quality from Agent 2."""
    
    quality_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Điểm đánh giá chất lượng data (0.0 - 1.0)"
    )
    quality_reason: str = Field(
        description="Lý do cụ thể cho quality score (data đầy đủ/thiếu, mâu thuẫn, lỗi thời...)"
    )
    coverage: Literal["complete", "partial", "insufficient"] = Field(
        description="Mức độ đầy đủ của data để trả lời query"
    )
    should_fallback: bool = Field(
        description="Có nên fallback sang response 'liên hệ cố vấn' không"
    )
    fallback_reason: Optional[str] = Field(
        default=None,
        description="Lý do cụ thể cho việc fallback (nếu should_fallback=True)"
    )


class ResponseGeneration(BaseModel):
    """Generated response from Agent 2."""
    
    response_text: str = Field(
        description="Nội dung câu trả lời chi tiết, có thể chứa markdown formatting và hyperlinks"
    )
    response_type: Literal["full_answer", "partial_answer", "fallback"] = Field(
        description="Loại response: full (đầy đủ), partial (một phần + suggest advisor), fallback (chỉ suggest advisor)"
    )
    references: List[Reference] = Field(
        default_factory=list,
        description="Danh sách tài liệu tham khảo với hyperlinks"
    )


# ============================================================================
# TypedDict State Schema for LangGraph
# ============================================================================

class QueryStateV2(TypedDict):
    """
    Extended state schema for 2-agent RAG pipeline.
    
    Flow:
    1. User input → Agent 1 (Query Understanding)
    2. If low confidence → Ask clarification → END (wait user)
    3. If high confidence → Retrieve data from LightRAG
    4. Retrieved data → Agent 2 (Data Quality Assessment + Response Generation)
    5. If low data quality → Fallback response
    6. If high data quality → Full/Partial response with references
    """
    
    # ============ Required: Messages for Chat UI ============
    messages: Annotated[List[AnyMessage], add_messages]
    
    # ============ Input ============
    query: NotRequired[str]  # Original user query (extracted from messages if not provided)
    
    # ============ Agent 1: Query Understanding ============
    # Output từ Agent 1
    parsed_intention: NotRequired[str]  # Clarified/rephrased query
    extracted_entities: NotRequired[List[str]]  # Important entities
    extracted_topics: NotRequired[List[str]]  # Main topics
    query_confidence: NotRequired[float]  # 0.0 - 1.0
    query_confidence_reason: NotRequired[str]  # Reason for confidence score
    
    # Decision từ Agent 1
    needs_clarification: NotRequired[bool]  # True if need to ask user
    clarification_question: NotRequired[str]  # Question to clarify
    
    # ============ Data Retrieval (LightRAG) ============
    # Parameters for retrieval
    retrieval_mode: NotRequired[Literal["naive", "local", "global", "hybrid", "mix"]]
    top_k: NotRequired[int]
    chunk_top_k: NotRequired[int]
    max_entity_tokens: NotRequired[int]
    max_relation_tokens: NotRequired[int]
    max_total_tokens: NotRequired[int]
    
    # Raw data from LightRAG /query/data endpoint
    retrieved_entities: NotRequired[List[Dict[str, Any]]]  # Entity data
    retrieved_relationships: NotRequired[List[Dict[str, Any]]]  # Relationship data
    retrieved_chunks: NotRequired[List[Dict[str, Any]]]  # Text chunks with metadata
    retrieval_metadata: NotRequired[Dict[str, Any]]  # Additional metadata (scores, etc.)
    
    # ============ Agent 2: Data Quality Assessment ============
    # Assessment output
    data_quality_score: NotRequired[float]  # 0.0 - 1.0
    data_quality_reason: NotRequired[str]  # Reason for quality score
    data_coverage: NotRequired[Literal["complete", "partial", "insufficient"]]  # Coverage level
    
    # Decision from Agent 2
    should_fallback: NotRequired[bool]  # True if should use fallback response
    fallback_reason: NotRequired[str]  # Reason for fallback
    
    # ============ Agent 2: Response Generation ============
    generated_response: NotRequired[str]  # Generated response text
    response_type: NotRequired[Literal["full_answer", "partial_answer", "fallback"]]
    references: NotRequired[List[Dict[str, Any]]]  # References with hyperlinks
    
    # ============ Final Output ============
    final_answer: NotRequired[str]  # Formatted final answer for user
    confidence_summary: NotRequired[Dict[str, Any]]  # Summary of all confidence scores
    
    # ============ Legacy/Compatibility Fields ============
    # Keep for backward compatibility with existing query_graph.py
    mode: NotRequired[Literal["default", "naive", "local", "global", "hybrid", "mix"]]
    response_type_legacy: NotRequired[str]  # Old response_type field
    conversation_history: NotRequired[List[Dict[str, Any]]]
    user_prompt: NotRequired[str]
    enable_rerank: NotRequired[bool]
    include_references: NotRequired[bool]
    stream: NotRequired[bool]
    
    # API interaction fields
    api_payload: NotRequired[Dict[str, Any]]
    api_response: NotRequired[Dict[str, Any]]
    
    # ============ Error Handling ============
    error: NotRequired[str]
    status_message: NotRequired[str]


# ============================================================================
# Configuration Constants
# ============================================================================

# Thresholds for decision making
QUERY_CONFIDENCE_THRESHOLD = 0.5  # Below this → ask clarification
DATA_QUALITY_THRESHOLD_HIGH = 0.7  # Above this → full answer
DATA_QUALITY_THRESHOLD_LOW = 0.4  # Below this → fallback

# Default retrieval parameters
DEFAULT_RETRIEVAL_MODE = "mix"
DEFAULT_TOP_K = 60
DEFAULT_CHUNK_TOP_K = 10

# Response templates
FALLBACK_RESPONSE_TEMPLATE = """
Cảm ơn bạn đã đặt câu hỏi về {topic}.

Dựa trên thông tin hiện có trong hệ thống, tôi chưa thể cung cấp câu trả lời đầy đủ và chính xác cho câu hỏi này.

**Đề xuất:**
Để được tư vấn chi tiết và chính xác nhất, bạn vui lòng liên hệ:
- **Cố vấn học tập** của lớp/khoa
- **Phòng Đào tạo** (nếu liên quan đến quy chế, quy trình đào tạo)
- **Phòng Công tác Sinh viên** (nếu liên quan đến học bổng, hoạt động sinh viên)

**Lý do:** {fallback_reason}
"""

PARTIAL_ANSWER_SUFFIX = """

---

**Lưu ý:** Thông tin trên có thể chưa đầy đủ. Để được tư vấn chi tiết hơn, bạn vui lòng liên hệ cố vấn học tập hoặc phòng ban liên quan.
"""
