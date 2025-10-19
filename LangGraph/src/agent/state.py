from __future__ import annotations

from typing import TypedDict, Literal, Optional, List, Dict, Any, Union, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from typing_extensions import NotRequired


class IndexingState(TypedDict):
    """State for the document indexing pipeline/graph."""

    input_source: Union[str, List[str]]
    source_type: Literal["file", "text", "scan", "batch"]
    description: Optional[str]
    api_payload: Optional[Dict[str, Any]]
    api_response: Optional[Dict[str, Any]]
    status_message: str
    error: Optional[str]


class QueryState(TypedDict):
    """State for the querying pipeline/graph."""
    # Messages field with reducer - REQUIRED for Chat UI
    messages: Annotated[list[AnyMessage], add_messages]
    
    # Query parameters - all optional
    query: NotRequired[str]
    mode: NotRequired[Literal["default", "naive", "local", "global", "hybrid", "mix"]]
    only_need_context: NotRequired[bool]
    only_need_prompt: NotRequired[bool]
    response_type: NotRequired[str]
    top_k: NotRequired[int]
    chunk_top_k: NotRequired[int]
    max_entity_tokens: NotRequired[int]
    max_relation_tokens: NotRequired[int]
    max_total_tokens: NotRequired[int]
    conversation_history: NotRequired[List[Dict[str, Any]]]
    user_prompt: NotRequired[str]
    enable_rerank: NotRequired[bool]
    include_references: NotRequired[bool]
    stream: NotRequired[bool]
    
    # API interaction fields
    api_payload: NotRequired[Dict[str, Any]]
    api_response: NotRequired[Dict[str, Any]]
    final_answer: NotRequired[str]
    error: NotRequired[str]