# indexing_graph.py - Updated version with file/folder path support
from __future__ import annotations

import io
import os
import glob
import requests
from pathlib import Path
from typing import Literal, List, Dict, Any, Union, Optional, cast
from langgraph.graph import StateGraph, END
from agent.state import IndexingState
from agent.lightrag_client import LightRAGAPIClient
from langchain_core.messages import HumanMessage, AIMessage, AnyMessage


api_client = LightRAGAPIClient()

# ---------------------- Helper Functions ----------------------
def _content_to_text(content: Any) -> str:
    """Extract text from message content."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                txt = (part.get("text") or "").strip()
                if txt:
                    texts.append(txt)
        return " ".join(texts) if texts else ""
    return ""


def _last_human_message(messages: List[AnyMessage]) -> Optional[AnyMessage]:
    """Get the last human message."""
    for msg in reversed(messages or []):
        if isinstance(msg, HumanMessage) or getattr(msg, "type", None) == "human":
            return msg
    return None


def _parse_chat_command(msg: AnyMessage) -> Dict[str, Any]:
    """
    Parse chat message to determine command.
    
    Supported commands:
    - "upload /path/to/file.pdf" -> Upload single file
    - "upload /path/to/folder" -> Upload all files in folder
    - "scan" -> Trigger scan
    - anything else -> insert as text
    """
    content = getattr(msg, "content", "")
    text = _content_to_text(content).strip()
    
    print("=" * 80)
    print(f"[PARSE] Input text: '{text}'")
    print("=" * 80)
    
    # Check for upload command with path
    if text.lower().startswith("upload ") and len(text.split(maxsplit=1)) > 1:
        parts = text.split(maxsplit=1)
        path = parts[1].strip()
        
        # Expand user home directory
        path = os.path.expanduser(path)
        
        # Remove quotes if present
        if (path.startswith('"') and path.endswith('"')) or \
           (path.startswith("'") and path.endswith("'")):
            path = path[1:-1]
        
        print(f"[PARSE] Detected upload command with path: {path}")
        
        return {
            "command": "upload_path",
            "path": path,
            "text": text
        }
    
    # Check for scan command
    if text.lower() == "scan" or text.lower().startswith("scan"):
        return {
            "command": "scan",
            "text": text
        }
    
    # Default: treat as text to insert
    return {
        "command": "text",
        "text": text
    }


def _get_files_from_path(path: str, recursive: bool = False) -> List[str]:
    """
    Get list of files from a path.
    - If path is a file, return [file]
    - If path is a directory, return all files in it
    
    Args:
        path: File or directory path
        recursive: If True, scan subdirectories
    
    Returns:
        List of absolute file paths
    """
    path_obj = Path(path)
    
    if not path_obj.exists():
        return []
    
    if path_obj.is_file():
        return [str(path_obj.absolute())]
    
    if path_obj.is_dir():
        files = []
        
        if recursive:
            # Recursive: get all files in subdirectories
            for file_path in path_obj.rglob("*"):
                if file_path.is_file():
                    files.append(str(file_path.absolute()))
        else:
            # Non-recursive: only files in current directory
            for file_path in path_obj.glob("*"):
                if file_path.is_file():
                    files.append(str(file_path.absolute()))
        
        return sorted(files)
    
    return []


def _filter_supported_files(file_paths: List[str]) -> List[str]:
    """
    Filter files by supported extensions.
    Add or remove extensions as needed.
    """
    supported_extensions = {
        # Documents
        '.txt', '.md', '.pdf', '.docx', '.doc', '.rtf', '.odt',
        # Code
        '.py', '.js', '.java', '.cpp', '.c', '.h', '.hpp', '.cs',
        '.go', '.rs', '.rb', '.php', '.ts', '.jsx', '.tsx',
        # Data
        '.json', '.xml', '.csv', '.yaml', '.yml',
        # Images (if your system supports OCR)
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff',
        # Others
        '.html', '.htm', '.css', '.sql', '.sh', '.bat'
    }
    
    filtered = []
    for file_path in file_paths:
        ext = Path(file_path).suffix.lower()
        if ext in supported_extensions:
            filtered.append(file_path)
    
    return filtered


def _upload_files_to_lightrag(file_paths: List[str]) -> List[Dict[str, Any]]:
    """
    Upload multiple files to LightRAG.
    
    Returns:
        List of API responses for each successful upload
    """
    results = []
    
    for file_path in file_paths:
        try:
            print(f"[UPLOAD] Uploading: {file_path}")
            result = api_client.upload_file(file_path)
            results.append({
                "file_path": file_path,
                "file_name": os.path.basename(file_path),
                "track_id": result.get("track_id"),
                "status": "success",
                "response": result
            })
            print(f"[UPLOAD] ✓ Success - Track ID: {result.get('track_id')}")
        except Exception as e:
            print(f"[UPLOAD] ✗ Failed: {str(e)}")
            results.append({
                "file_path": file_path,
                "file_name": os.path.basename(file_path),
                "status": "failed",
                "error": str(e)
            })
    
    return results


# ---------------------- Graph Nodes ----------------------
def prepare_indexing(state: IndexingState) -> IndexingState:
    """Prepare indexing request from Chat UI or direct input."""
    
    # If direct input provided (from Graph tab), use it
    if state.get("source_type") and state.get("input_source") is not None:
        return state
    
    messages = state.get("messages", [])
    if not messages:
        state["error"] = "No input provided"
        state["status_message"] = "Error: No input"
        return state
    
    # Get last human message
    last_msg = _last_human_message(messages)
    if not last_msg:
        state["error"] = "No input provided"
        state["status_message"] = "Error: No input"
        return state
    
    # Parse command
    parsed = _parse_chat_command(last_msg)
    command = parsed["command"]
    
    print("=" * 80)
    print(f"[COMMAND] {command}")
    print("=" * 80)
    
    # Handle upload by path (file or directory)
    if command == "upload_path":
        path = parsed["path"]
        
        # Check if path exists
        if not os.path.exists(path):
            error_msg = f"Path not found: {path}"
            state["error"] = error_msg
            state["status_message"] = "Error: Path not found"
            
            msgs = list(state.get("messages", []))
            msgs.append(AIMessage(content=f"{error_msg}"))
            state["messages"] = msgs
            return state
        
        # Get files from path
        is_dir = os.path.isdir(path)
        file_paths = _get_files_from_path(path, recursive=False)
        
        if not file_paths:
            error_msg = f"No files found in: {path}"
            state["error"] = error_msg
            state["status_message"] = "Error: No files"
            
            msgs = list(state.get("messages", []))
            msgs.append(AIMessage(content=f"{error_msg}"))
            state["messages"] = msgs
            return state
        
        # Filter supported files
        supported_files = _filter_supported_files(file_paths)
        
        if not supported_files:
            error_msg = f"No supported file types found in: {path}\n\nFound {len(file_paths)} file(s) but none are supported."
            state["error"] = error_msg
            state["status_message"] = "Error: No supported files"
            
            msgs = list(state.get("messages", []))
            msgs.append(AIMessage(content=f"{error_msg}"))
            state["messages"] = msgs
            return state
        
        # Upload files
        print(f"[UPLOAD] Found {len(supported_files)} supported file(s)")
        upload_results = _upload_files_to_lightrag(supported_files)
        
        # Count successes and failures
        success_count = sum(1 for r in upload_results if r["status"] == "success")
        failed_count = len(upload_results) - success_count
        
        # Store results
        state["source_type"] = "file"
        state["input_source"] = None
        state["description"] = f"Uploaded from path: {path}"
        state["api_response"] = {"results": upload_results}
        state["status_message"] = "Upload complete"
        state["error"] = None if failed_count == 0 else f"{failed_count} file(s) failed"
        
        # Build response message
        response_lines = []
        
        if is_dir:
            response_lines.append(f"**Directory:** `{path}`")
            response_lines.append(f"**Summary:** {success_count} succeeded, {failed_count} failed (out of {len(supported_files)} files)")
        else:
            response_lines.append(f"**File:** `{os.path.basename(path)}`")
        
        response_lines.append("")
        
        # Show successful uploads
        if success_count > 0:
            response_lines.append("**Successful uploads:**")
            for result in upload_results:
                if result["status"] == "success":
                    response_lines.append(f"- `{result['file_name']}` (Track ID: `{result['track_id']}`)")
        
        # Show failed uploads
        if failed_count > 0:
            response_lines.append("")
            response_lines.append("**Failed uploads:**")
            for result in upload_results:
                if result["status"] == "failed":
                    response_lines.append(f"- `{result['file_name']}`: {result['error']}")
        
        response_lines.append("")
        response_lines.append("Processing in background...")
        
        response_text = "\n".join(response_lines)
        
        msgs = list(state.get("messages", []))
        msgs.append(AIMessage(content=response_text))
        state["messages"] = msgs
        
        return state
    
    # Handle scan command
    elif command == "scan":
        state["source_type"] = "scan"
        state["input_source"] = None
        state["description"] = "Manual scan triggered"
    
    # Handle text insert
    elif command == "text":
        text_content = parsed["text"]
        if not text_content or len(text_content) < 3:
            state["error"] = "Text content is too short"
            state["status_message"] = "Error: Invalid text"
            return state
        
        state["source_type"] = "text"
        state["input_source"] = text_content
        state["description"] = "Insert text from chat"
    
    else:
        state["error"] = f"Unknown command: {command}"
        state["status_message"] = "Error: Unknown command"
        return state
    
    state["error"] = None
    return state


def ingestion_router(state: IndexingState) -> Literal["call_api", "error_handler", "end"]:
    """Route to appropriate handler based on state."""
    if state.get("error"):
        return "error_handler"
    
    source_type = state.get("source_type")
    
    # If already uploaded files via path, skip call_api
    if source_type == "file" and state.get("api_response"):
        return "end"
    
    input_source = state.get("input_source")
    
    if source_type not in {"file", "text", "scan", "batch"}:
        state["error"] = f"Unsupported source_type: {source_type!r}"
        state["status_message"] = "Validation failed"
        return "error_handler"

    if source_type != "scan" and (input_source is None or (isinstance(input_source, list) and len(input_source) == 0)):
        state["error"] = "input_source is required unless source_type='scan'"
        state["status_message"] = "Validation failed"
        return "error_handler"

    state["status_message"] = "Validated"
    return "call_api"


def call_api(state: IndexingState) -> IndexingState:
    """Call LightRAG ingestion endpoints for scan and text."""
    source_type: str = cast(str, state["source_type"])
    input_source: Union[str, List[str], None] = state.get("input_source")

    try:
        if source_type == "text":
            if isinstance(input_source, list):
                state["api_response"] = api_client.insert_texts(cast(List[str], input_source))
            else:
                state["api_response"] = api_client.insert_text(cast(str, input_source))

        elif source_type == "scan":
            state["api_response"] = api_client.trigger_scan()

        else:
            raise ValueError(f"Unexpected source_type in call_api: {source_type}")

        state["status_message"] = "Operation successful"
        state["error"] = None
        
        # Add success message
        response_text = ""
        if source_type == "scan":
            track_id = state["api_response"].get("track_id", "N/A")
            response_text = f"Scan initiated successfully!\n\nTrack ID: `{track_id}`\n\nProcessing in background..."
        elif source_type == "text":
            track_id = state["api_response"].get("track_id", "N/A")
            response_text = f"Text inserted successfully!\n\nTrack ID: `{track_id}`\n\nProcessing in background..."
        
        if response_text:
            msgs = list(state.get("messages", []))
            msgs.append(AIMessage(content=response_text))
            state["messages"] = msgs
        
        return state

    except Exception as e:
        state["api_response"] = None
        state["status_message"] = "Operation failed"
        state["error"] = str(e)
        
        msgs = list(state.get("messages", []))
        msgs.append(AIMessage(content=f"Error: {str(e)}"))
        state["messages"] = msgs
        
        return state


def error_handler(state: IndexingState) -> IndexingState:
    """Handle errors and return user-friendly message."""
    error_msg = state.get("error", "Unknown error")
    state["status_message"] = state.get("status_message") or "Error"
    
    if "messages" in state:
        msgs = list(state.get("messages", []))
        # Only add error message if not already added
        if not msgs or not isinstance(msgs[-1], AIMessage):
            msgs.append(AIMessage(content=f"Error: {error_msg}"))
            state["messages"] = msgs
    
    return state


# ---------------------- Graph Builder ----------------------
builder = StateGraph(state_schema=IndexingState)
builder.add_node("prepare_indexing", prepare_indexing)
builder.add_node("call_api", call_api)
builder.add_node("error_handler", error_handler)

builder.set_entry_point("prepare_indexing")
builder.add_conditional_edges(
    "prepare_indexing",
    ingestion_router,
    {"call_api": "call_api", "error_handler": "error_handler", "end": END}
)
builder.add_edge("call_api", END)
builder.add_edge("error_handler", END)

graph = builder.compile()
graph.name = "IndexGraph"