from __future__ import annotations

import operator
from typing import TypedDict, Literal, List, Dict, Any, Union, Annotated, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from typing_extensions import NotRequired

class Data(TypedDict):
    path: str
    source: str

class IndexingState(TypedDict):
    """
    State for the document indexing pipeline/graph with Chat UI support.
    
    Uses Annotated/reducers for fields that require accumulation (e.g., logs, results).
    """
    
    # ============ Required: Messages for Chat UI ============
    messages: Annotated[List[AnyMessage], add_messages]
    
    # ============ Input ============
    # Source configuration
    input_source: NotRequired[Optional[Union[str, Data, List[Data]]]] # Changed to allow str path directly and Optional
    source_type: NotRequired[Literal["file", "text", "scan", "batch"]]
    description: NotRequired[Optional[str]]
    
    # ============ Batch Processing ============
    # List of all files to process
    file_list: NotRequired[List[str]]  
    
    # Accumulate results from multiple file processing steps
    # Usage: return {"upload_results": [new_result]} to append
    upload_results: Annotated[List[Dict[str, Any]], operator.add]
    
    # Iteration state (overwrite default)
    current_file_index: NotRequired[int]
    current_file_path: NotRequired[Optional[str]]
    all_files_processed: NotRequired[bool]
    
    # ============ File Processing State ============
    # PDF detection
    is_pdf: NotRequired[bool]

    # OCR fields
    doc_text: NotRequired[Optional[str]]
    parsed_content: NotRequired[Optional[str]]
    ocr_output_dir: NotRequired[Optional[str]]
    ocr_success: NotRequired[bool]
    ocr_error: NotRequired[Optional[str]]

    # ============ Temporal Metadata Extraction ============
    # Extracted temporal metadata (valid_from, valid_until, cohorts, etc.)
    document_metadata: NotRequired[Dict[str, Any]]
    temporal_extraction_complete: NotRequired[bool]

    # ============ HITL Review (review_temporal_tags node) ============
    human_feedback: NotRequired[Optional[str]]
    loop_count: NotRequired[int]
    review_status: NotRequired[str]

    # File source tracking
    file_path: NotRequired[str]
    file_source: NotRequired[str]
    # Admin-supplied URL (overrides auto-discovered URL from get_url())
    explicit_url: NotRequired[Optional[str]]

    # ============ API Interaction ============
    api_payload: NotRequired[Dict[str, Any]]
    api_response: NotRequired[Dict[str, Any]]
    upload_result: NotRequired[Dict[str, Any]]
    doc_id: NotRequired[Optional[str]]

    # ============ Status & Errors ============
    status_message: NotRequired[Optional[str]]
    error: NotRequired[Optional[str]]
