"""
State Schema for 3-Agent RAG Pipeline with Reranker.

This module defines the state schema for an advanced RAG pipeline that includes:
- Agent 1: Query Understanding with automatic parameter tuning
- Reranker: Score and re-rank retrieved data
- Agent 2: Confidence Assessment based on rerank scores
- Agent 3: Response Generation with high-quality data
"""

from __future__ import annotations

import operator
from typing_extensions import TypedDict, Literal, Optional, List, Dict, Any, Annotated, Tuple
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from typing_extensions import NotRequired
from pydantic import BaseModel, Field
from ..config import settings


# ============================================================================
# Pydantic Models for Structured Outputs
# ============================================================================

class QueryUnderstanding(BaseModel):
    """
    Structured output from Agent 1: Query Understanding with Parameter Tuning.
    
    Include automatic parameter tuning for retrieval.
    """
    
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
    
    # Cohort year extracted from query (e.g. 2022 for "K2022", "khoa 2022")
    query_cohort_year: Optional[int] = Field(
        default=None,
        description="Nam nhap hoc cua khoa sinh vien neu co (vi du: 2022 cho 'K2022', 'khoa 2022')"
    )

    # NEW: Parameter tuning outputs
    suggested_mode: Literal["naive", "local", "global", "hybrid", "mix"] = Field(
        default=settings.retrieval.default_mode,
        description="Suggested retrieval mode based on query type"
    )
    suggested_top_k: int = Field(
        ge=1,
        le=20,
        default=settings.retrieval.default_top_k,
        description="Suggested number of top results to retrieve"
    )
    suggested_chunk_top_k: int = Field(
        ge=1,
        le=130,
        default=settings.retrieval.default_chunk_top_k,
        description="Suggested number of top chunks to retrieve"
    )
    tuning_reason: str = Field(
        description="Explanation for the suggested parameters (mode and top_k)"
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


class ConfidenceAssessment(BaseModel):
    """
    Confidence assessment from Agent 2.
    
    This combines query confidence and rerank confidence to make a decision.
    """
    
    overall_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence score (combined from query and rerank)"
    )
    needs_followup: bool = Field(
        description="Whether to ask a follow-up question to the user"
    )
    followup_question: Optional[str] = Field(
        default=None,
        description="Follow-up question if needs_followup=True"
    )
    confidence_reason: str = Field(
        description="Detailed explanation for the confidence assessment and decision"
    )


class ResponseGeneration(BaseModel):
    """Generated response from Agent 3."""
    
    response_text: str = Field(
        description="Nội dung câu trả lời chi tiết, có thể chứa markdown formatting và hyperlinks"
    )
    response_type: Literal["full_answer", "partial_answer", "fallback"] = Field(
        description="Loại response: full_answer (đầy đủ), partial_answer (một phần + suggest advisor), fallback (chỉ suggest advisor)"
    )


# ============================================================================
# TypedDict State Schema for LangGraph
# ============================================================================

class QueryState(TypedDict):
    """
    Extended state schema for 3-agent RAG pipeline with reranker.
    
    Flow:
    1. User input → Agent 1 (Query Understanding + Parameter Tuning)
    2. If low confidence → Ask clarification → END (wait user)
    3. If high confidence → Retrieve data from LightRAG (with tuned params)
    4. Retrieved data → Reranker (Score and re-rank all items)
    5. Reranked data → Agent 2 (Confidence Assessment)
    6. If overall confidence < threshold → Ask follow-up → END (wait user)
    7. If overall confidence >= threshold → Agent 3 (Generate Response)
    8. Format final answer → END
    """
    
    # ============ Required: Messages for Chat UI ============
    # Use add_messages to handle message history updates (append/update by ID)
    messages: Annotated[List[AnyMessage], add_messages]
    
    # ============ Logging & Tracing ============
    # Accumulate logs from steps (return {"logs": ["step completed"]} to append)
    logs: Annotated[List[str], operator.add]
    
    # ============ Input ============
    query: NotRequired[Optional[str]]  
    
    # ============ Agent 1: Query Understanding + Parameter Tuning ============
    # Agent 1 Output
    parsed_intention: NotRequired[Optional[str]]
    extracted_entities: NotRequired[List[str]]
    extracted_topics: NotRequired[List[str]]
    query_confidence: NotRequired[float]
    query_confidence_reason: NotRequired[Optional[str]]
    query_cohort_year: NotRequired[Optional[int]]  # e.g. 2022 for "K2022" queries

    # Agent 1 Decision
    needs_clarification: NotRequired[bool]
    clarification_question: NotRequired[Optional[str]]

    # Tuned parameters từ Agent 1
    retrieval_mode: NotRequired[Literal["naive", "local", "global", "hybrid", "mix"]]
    top_k: NotRequired[Optional[int]]
    chunk_top_k: NotRequired[Optional[int]]
    tuning_reason: NotRequired[Optional[str]]  # Explanation for parameter choices
    
    # ============ Data Retrieval (LightRAG) ============
    # Optional parameters for fine-tuning
    max_entity_tokens: NotRequired[Optional[int]]
    max_relation_tokens: NotRequired[Optional[int]]
    max_total_tokens: NotRequired[Optional[int]]
    
    # Raw data from LightRAG /query/data endpoint
    retrieved_entities: NotRequired[List[Dict[str, Any]]]  
    retrieved_relationships: NotRequired[List[Dict[str, Any]]]  
    retrieved_chunks: NotRequired[List[Dict[str, Any]]]  
    retrieval_metadata: NotRequired[Dict[str, Any]]  
    
    # ============ Reranker ============
    # Reranked data with scores
    reranked_entities: NotRequired[List[Tuple[Dict[str, Any], float]]]  
    reranked_relationships: NotRequired[List[Tuple[Dict[str, Any], float]]]  
    reranked_chunks: NotRequired[List[Tuple[Dict[str, Any], float]]]  
    
    # Rerank scores and confidence
    entity_scores: NotRequired[List[float]]
    relationship_scores: NotRequired[List[float]]
    chunk_scores: NotRequired[List[float]]
    rerank_confidence: NotRequired[float]  
    rerank_metadata: NotRequired[Dict[str, Any]]  
    
    # ============ Agent 2: Confidence Assessment ============
    # Overall confidence combining query + rerank
    overall_confidence: NotRequired[float]  
    needs_followup: NotRequired[bool]  
    followup_question: NotRequired[Optional[str]]  
    confidence_reason: NotRequired[Optional[str]]  
    
    # ============ Agent 3: Response Generation ============
    generated_response: NotRequired[Optional[str]]  
    response_type: NotRequired[Literal["full_answer", "partial_answer", "fallback"]]
    references: NotRequired[List[Dict[str, Any]]]  
    
    # ============ Final Output ============
    final_answer: NotRequired[Optional[str]]  
    confidence_summary: NotRequired[Dict[str, Any]]  
    
    # ============ Legacy/Compatibility Fields ============
    # Keep for backward compatibility
    mode: NotRequired[Literal["default", "naive", "local", "global", "hybrid", "mix"]]
    conversation_history: NotRequired[List[Dict[str, Any]]]
    user_prompt: NotRequired[Optional[str]]
    enable_rerank: NotRequired[bool]
    include_references: NotRequired[bool]
    stream: NotRequired[bool]
    
    # API interaction fields
    api_payload: NotRequired[Dict[str, Any]]
    api_response: NotRequired[Dict[str, Any]]
    
    # ============ Error Handling ============
    error: NotRequired[Optional[str]]
    status_message: NotRequired[Optional[str]]


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "QueryState",
    "QueryUnderstanding",
    "Reference",
    "ConfidenceAssessment",
    "ResponseGeneration",
]