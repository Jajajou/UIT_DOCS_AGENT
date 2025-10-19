from __future__ import annotations

from typing import TypedDict, Literal, Optional, List, Dict, Any, Union
from langgraph.graph import StateGraph, END, MessagesState
from langchain_core.messages import HumanMessage, AIMessage, AnyMessage
from typing import Any, Dict, Optional, List, cast

class IndexingState(TypedDict):
    """State for the document indexing pipeline/graph."""

    input_source: Union[str, List[str]]
    source_type: Literal["file", "text", "scan", "batch"]
    description: Optional[str]
    api_payload: Optional[Dict[str, Any]]
    api_response: Optional[Dict[str, Any]]
    status_message: str
    error: Optional[str]


class QueryState(MessagesState):
    """State for the querying pipeline/graph."""

    query: str
    mode: Literal["default", "naive", "local", "global", "hybrid", "mix"]
    only_need_context: bool
    only_need_prompt: bool
    response_type: Optional[str]
    top_k: int
    chunk_top_k: int
    max_entity_tokens: int
    max_relation_tokens: int
    max_total_tokens: int
    conversation_history: Optional[List[Dict[str, Any]]]
    user_prompt: Optional[str]
    enable_rerank: bool
    include_references: bool    
    stream: bool
    api_payload: Optional[Dict[str, Any]]    
    api_response: Optional[Dict[str, Any]]    
    final_answer: Optional[str]    
    error: Optional[str]