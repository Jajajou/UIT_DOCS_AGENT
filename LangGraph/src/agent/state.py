from __future__ import annotations

from typing import TypedDict, Literal, Optional, List, Dict, Any, Union, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from typing_extensions import NotRequired

class Data(TypedDict):
    path: str
    source: str

class IndexingState(TypedDict):
    """State for the document indexing pipeline/graph with Chat UI support."""
    
    # Messages field for Chat UI support
    messages: Annotated[list[AnyMessage], add_messages]
    
    # Indexing parameters - all optional now since we can extract from messages
    input_source: NotRequired[Union[Data, List[Data]]]
    source_type: NotRequired[Literal["file", "text", "scan", "batch"]]
    description: NotRequired[str]
    
    # File processing fields (for batch uploads)
    file_list: NotRequired[List[str]]  # List of all file paths to process
    current_file_index: NotRequired[int]  # Index of current file being processed
    current_file_path: NotRequired[str]  # Path of current file
    all_files_processed: NotRequired[bool]  # Flag when all files are done
    upload_results: NotRequired[List[Dict[str, Any]]]  # Results for each file
    
    # PDF detection fields
    is_pdf: NotRequired[bool]  # Whether current file is PDF
    
    # MinerU parsing fields
    parsed_content: NotRequired[str]  # Markdown content from MinerU
    mineru_output_dir: NotRequired[str]  # Output directory from MinerU
    mineru_success: NotRequired[bool]  # Whether MinerU parsing succeeded
    mineru_error: NotRequired[str]  # Error message if MinerU failed
    
    # API interaction fields
    api_payload: NotRequired[Dict[str, Any]]
    api_response: NotRequired[Dict[str, Any]]
    status_message: NotRequired[str]
    error: NotRequired[str]


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