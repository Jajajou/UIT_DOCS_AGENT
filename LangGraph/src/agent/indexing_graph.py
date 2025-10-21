# indexing_graph.py - Matches the perfect flowchart
from __future__ import annotations

import io
import os
import glob
import requests
from pathlib import Path
from typing import Literal, List, Dict, Any, Union, Optional, cast
from langgraph.graph import StateGraph, END, START
from agent.state import IndexingState
from agent.lightrag_client import LightRAGAPIClient
from agent.mineru_client import MinerUClient, MinerUClientError
from langchain_core.messages import HumanMessage, AIMessage, AnyMessage


api_client = LightRAGAPIClient()
mineru_client = MinerUClient()

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
    """
    path_obj = Path(path)
    
    if not path_obj.exists():
        return []
    
    if path_obj.is_file():
        return [str(path_obj.absolute())]
    
    if path_obj.is_dir():
        files = []
        
        if recursive:
            for file_path in path_obj.rglob("*"):
                if file_path.is_file():
                    files.append(str(file_path.absolute()))
        else:
            for file_path in path_obj.glob("*"):
                if file_path.is_file():
                    files.append(str(file_path.absolute()))
        
        return sorted(files)
    
    return []


def _filter_supported_files(file_paths: List[str]) -> List[str]:
    """Filter files by supported extensions."""
    supported_extensions = {
        # Documents
        '.txt', '.md', '.pdf', '.docx', '.doc', '.rtf', '.odt',
        # Code
        '.py', '.js', '.java', '.cpp', '.c', '.h', '.hpp', '.cs',
        '.go', '.rs', '.rb', '.php', '.ts', '.jsx', '.tsx',
        # Data
        '.json', '.xml', '.csv', '.yaml', '.yml',
        # Images
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


def _is_pdf(file_path: str) -> bool:
    """Check if file is a PDF."""
    return file_path.lower().endswith('.pdf')


# ---------------------- Graph Nodes ----------------------

def prepare_indexing(state: IndexingState) -> IndexingState:
    """Prepare indexing request - determine command type."""
    
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
    
    # Store command type and data
    if command == "upload_path":
        state["source_type"] = "file"
        state["input_source"] = parsed["path"]  # Store path for next node
        state["description"] = f"Upload from path: {parsed['path']}"
    
    elif command == "scan":
        state["source_type"] = "scan"
        state["input_source"] = None  # type: ignore
        state["description"] = "Manual scan triggered"
    
    elif command == "text":
        state["source_type"] = "text"
        state["input_source"] = parsed["text"]
        state["description"] = "Insert text from chat"
    
    else:
        state["error"] = f"Unknown command: {command}"
        state["status_message"] = "Error: Unknown command"
        return state
    
    state["error"] = None  # type: ignore
    return state


def prepare_file_list(state: IndexingState) -> IndexingState:
    """Prepare list of files from path (file or directory)."""
    
    path = state.get("input_source")
    
    if not path or not isinstance(path, str):
        state["error"] = "Invalid path"
        return state
    
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
        total_files = len(file_paths)
        skipped_files = [os.path.basename(f) for f in file_paths[:5]]
        more_text = f" and {total_files - 5} more" if total_files > 5 else ""
        
        error_msg = (
            f"No supported file types found in: {path}\n\n"
            f"Found {total_files} file(s) but none are supported.\n"
            f"Skipped: {', '.join(skipped_files)}{more_text}"
        )
        state["error"] = error_msg
        state["status_message"] = "Error: No supported files"
        
        msgs = list(state.get("messages", []))
        msgs.append(AIMessage(content=f"{error_msg}"))
        state["messages"] = msgs
        return state
    
    # Show preview
    total_files = len(supported_files)
    preview_count = min(5, total_files)
    preview_files = [os.path.basename(f) for f in supported_files[:preview_count]]
    more_text = f" and {total_files - preview_count} more" if total_files > preview_count else ""
    
    print(f"[FILE_LIST] Found {total_files} supported file(s)")
    print(f"[FILE_LIST] Files: {', '.join(preview_files)}{more_text}")
    
    # Initialize file processing state
    state["file_list"] = supported_files
    state["current_file_index"] = 0
    state["upload_results"] = []
    state["error"] = None  # type: ignore
    
    return state


def check_if_pdf(state: IndexingState) -> IndexingState:
    """Check if current file is a PDF."""
    
    file_list = state.get("file_list", [])
    current_index = state.get("current_file_index", 0)
    
    if current_index >= len(file_list):
        # No more files
        state["is_pdf"] = False
        state["all_files_processed"] = True
        return state
    
    current_file = file_list[current_index]
    is_pdf = _is_pdf(current_file)
    
    state["is_pdf"] = is_pdf
    state["current_file_path"] = current_file
    state["all_files_processed"] = False
    
    print(f"[CHECK_PDF] File {current_index + 1}/{len(file_list)}: {os.path.basename(current_file)}")
    print(f"[CHECK_PDF] Is PDF: {is_pdf}")
    
    return state


def parse_with_mineru(state: IndexingState) -> IndexingState:
    """Parse PDF with MinerU."""
    
    file_path = state.get("current_file_path")
    
    if not file_path:
        state["error"] = "No file path for MinerU"
        return state
    
    try:
        file_stem = Path(file_path).stem
        output_dir = f"./output/{file_stem}"
        
        print(f"[MINERU] Parsing: {os.path.basename(file_path)}")
        
        md_content, output_path = mineru_client.parse_and_get_markdown(
            file_path,
            output_dir=output_dir,
            parse_method="auto",
            lang_list="latin",
            table_enable=True,
            formula_enable=True,
        )
        
        print(f"[MINERU] ✓ Success - {len(md_content):,} chars")
        
        state["parsed_content"] = md_content
        state["mineru_output_dir"] = output_path
        state["mineru_success"] = True
        state["error"] = None  # type: ignore
        
    except Exception as e:
        print(f"[MINERU] ✗ Failed: {str(e)}")
        state["parsed_content"] = None  # type: ignore
        state["mineru_success"] = False
        state["mineru_error"] = str(e)
    
    return state


def upload_to_lightrag(state: IndexingState) -> IndexingState:
    """Upload to LightRAG (handles text, scan, and files)."""
    
    source_type = state.get("source_type")
    
    # Handle scan
    if source_type == "scan":
        try:
            result = api_client.trigger_scan()
            state["api_response"] = result
            state["status_message"] = "Scan initiated"
            
            track_id = result.get("track_id", "N/A")
            response_text = f"✓ Scan initiated!\n\nTrack ID: `{track_id}`\n\nProcessing in background..."
            
            msgs = list(state.get("messages", []))
            msgs.append(AIMessage(content=response_text))
            state["messages"] = msgs
            
        except Exception as e:
            state["error"] = str(e)
            msgs = list(state.get("messages", []))
            msgs.append(AIMessage(content=f"Error: {str(e)}"))
            state["messages"] = msgs
        
        return state
    
    # Handle text
    if source_type == "text":
        try:
            input_source = state.get("input_source")
            if isinstance(input_source, list):
                result = api_client.insert_texts(cast(List[str], input_source))
            else:
                result = api_client.insert_text(cast(str, input_source))
            
            state["api_response"] = result
            state["status_message"] = "Text inserted"
            
            track_id = result.get("track_id", "N/A")
            response_text = f"✓ Text inserted!\n\nTrack ID: `{track_id}`\n\nProcessing in background..."
            
            msgs = list(state.get("messages", []))
            msgs.append(AIMessage(content=response_text))
            state["messages"] = msgs
            
        except Exception as e:
            state["error"] = str(e)
            msgs = list(state.get("messages", []))
            msgs.append(AIMessage(content=f"Error: {str(e)}"))
            state["messages"] = msgs
        
        return state
    
    # Handle file upload
    if source_type == "file":
        file_path = state.get("current_file_path")
        
        if not file_path:
            return state
        
        file_name = os.path.basename(file_path)
        file_list = state.get("file_list", [])
        current_index = state.get("current_file_index", 0)
        
        print(f"[UPLOAD] {current_index + 1}/{len(file_list)}: {file_name}")
        
        try:
            parsed_content = state.get("parsed_content")
            
            if state.get("mineru_success") and parsed_content:
                # Upload parsed content
                result = api_client.insert_text(
                    text=parsed_content,
                    file_source=file_name
                )
                
                upload_result = {
                    "file_path": file_path,
                    "file_name": file_name,
                    "track_id": result.get("track_id"),
                    "status": "success",
                    "parsed_with_mineru": True,
                    "output_dir": state.get("mineru_output_dir"),
                    "markdown_length": len(parsed_content),
                    "response": result
                }
                
                print(f"[UPLOAD] ✓ Success (MinerU) - Track: {result.get('track_id')}")
            
            else:
                # Direct file upload
                result = api_client.upload_file(file_path)
                
                upload_result = {
                    "file_path": file_path,
                    "file_name": file_name,
                    "track_id": result.get("track_id"),
                    "status": "success",
                    "parsed_with_mineru": False,
                    "response": result
                }
                
                mineru_error = state.get("mineru_error")
                if mineru_error:
                    upload_result["fallback_reason"] = mineru_error
                
                print(f"[UPLOAD] ✓ Success (Direct) - Track: {result.get('track_id')}")
            
            results = state.get("upload_results", [])
            results.append(upload_result)
            state["upload_results"] = results
            
        except Exception as e:
            print(f"[UPLOAD] ✗ Failed: {str(e)}")
            
            results = state.get("upload_results", [])
            results.append({
                "file_path": file_path,
                "file_name": file_name,
                "status": "failed",
                "error": str(e)
            })
            state["upload_results"] = results
        
        # Move to next file
        current_index = state.get("current_file_index", 0)
        state["current_file_index"] = current_index + 1
        
        # Clear current file state
        state["current_file_path"] = None  # type: ignore
        state["parsed_content"] = None  # type: ignore
        state["mineru_success"] = False
        state["mineru_error"] = None  # type: ignore
    
    return state


def finalize_upload(state: IndexingState) -> IndexingState:
    """Finalize and send summary."""
    
    upload_results = state.get("upload_results", [])
    
    if not upload_results:
        return state
    
    success_count = sum(1 for r in upload_results if r["status"] == "success")
    failed_count = len(upload_results) - success_count
    mineru_count = sum(1 for r in upload_results if r.get("parsed_with_mineru"))
    
    response_lines = []
    file_list = state.get("file_list", [])
    is_batch = len(file_list) > 1
    
    if is_batch:
        response_lines.append(f"**Batch Upload Complete**")
        response_lines.append(f"✓ {success_count} succeeded | ✗ {failed_count} failed | Total: {len(file_list)}")
    else:
        file_name = os.path.basename(file_list[0])
        status_icon = "✓" if success_count > 0 else "✗"
        response_lines.append(f"{status_icon} **File:** `{file_name}`")
    
    response_lines.append("")
    
    if mineru_count > 0:
        response_lines.append(f"**PDFs parsed with MinerU:** {mineru_count}")
        response_lines.append("")
    
    if success_count > 0:
        response_lines.append("**✓ Successful uploads:**")
        for result in upload_results:
            if result["status"] == "success":
                extra = ""
                if result.get("parsed_with_mineru"):
                    md_len = result.get("markdown_length", 0)
                    extra = f" (MinerU: {md_len:,} chars)"
                elif result.get("fallback_reason"):
                    extra = " (Direct - MinerU failed)"
                
                response_lines.append(f"  • `{result['file_name']}`{extra}")
                response_lines.append(f"    Track ID: `{result['track_id']}`")
    
    if failed_count > 0:
        response_lines.append("")
        response_lines.append("**✗ Failed uploads:**")
        for result in upload_results:
            if result["status"] == "failed":
                response_lines.append(f"  • `{result['file_name']}`")
                response_lines.append(f"    Error: {result['error']}")
    
    response_lines.append("")
    response_lines.append("Processing in background...")
    
    response_text = "\n".join(response_lines)
    
    msgs = list(state.get("messages", []))
    msgs.append(AIMessage(content=response_text))
    state["messages"] = msgs
    
    state["status_message"] = "Complete"
    state["api_response"] = {"results": upload_results}
    
    return state


def error_handler(state: IndexingState) -> IndexingState:
    """Handle errors."""
    error_msg = state.get("error", "Unknown error")
    state["status_message"] = state.get("status_message") or "Error"
    
    if "messages" in state:
        msgs = list(state.get("messages", []))
        if not msgs or not isinstance(msgs[-1], AIMessage):
            msgs.append(AIMessage(content=f"Error: {error_msg}"))
            state["messages"] = msgs
    
    return state


# ---------------------- Router Functions ----------------------

def route_after_prepare(state: IndexingState) -> Literal["error_handler", "upload_to_lightrag", "prepare_file_list"]:
    """Route after prepare: check for errors, then route by type."""
    if state.get("error"):
        return "error_handler"
    
    source_type = state.get("source_type")
    
    if source_type in ["text", "scan"]:
        return "upload_to_lightrag"
    elif source_type == "file":
        return "prepare_file_list"
    
    return "upload_to_lightrag"


def route_after_file_list(state: IndexingState) -> Literal["check_if_pdf", "error_handler"]:
    """Route after file list preparation."""
    if state.get("error"):
        return "error_handler"
    return "check_if_pdf"


def route_after_pdf_check(state: IndexingState) -> Literal["parse_with_mineru", "upload_to_lightrag"]:
    """Route based on whether file is PDF."""
    if state.get("is_pdf"):
        return "parse_with_mineru"
    return "upload_to_lightrag"


def route_after_upload(state: IndexingState) -> Literal["prepare_file_list", "finalize_upload", "end"]:
    """Route after upload: check if more files or done."""
    source_type = state.get("source_type")
    
    if source_type == "file":
        # Check if more files to process
        file_list = state.get("file_list", [])
        current_index = state.get("current_file_index", 0)
        
        if current_index < len(file_list):
            return "prepare_file_list"
        else:
            return "finalize_upload"
    else:
        # Text or scan - we're done
        return "end"


# ---------------------- Graph Builder ----------------------

builder = StateGraph(state_schema=IndexingState)

# Add all nodes
builder.add_node("prepare_indexing", prepare_indexing)
builder.add_node("prepare_file_list", prepare_file_list)
builder.add_node("check_if_pdf", check_if_pdf)
builder.add_node("parse_with_mineru", parse_with_mineru)
builder.add_node("upload_to_lightrag", upload_to_lightrag)
builder.add_node("finalize_upload", finalize_upload)
builder.add_node("error_handler", error_handler)

# Build the graph following the flowchart exactly
builder.add_edge(START, "prepare_indexing")

builder.add_conditional_edges(
    "prepare_indexing",
    route_after_prepare,
    {
        "error_handler": "error_handler",
        "upload_to_lightrag": "upload_to_lightrag",
        "prepare_file_list": "prepare_file_list"
    }
)

builder.add_conditional_edges(
    "prepare_file_list",
    route_after_file_list,
    {
        "check_if_pdf": "check_if_pdf",
        "error_handler": "error_handler"
    }
)

builder.add_conditional_edges(
    "check_if_pdf",
    route_after_pdf_check,
    {
        "parse_with_mineru": "parse_with_mineru",
        "upload_to_lightrag": "upload_to_lightrag"
    }
)

builder.add_edge("parse_with_mineru", "upload_to_lightrag")

builder.add_conditional_edges(
    "upload_to_lightrag",
    route_after_upload,
    {
        "prepare_file_list": "prepare_file_list",
        "finalize_upload": "finalize_upload",
        "end": END
    }
)

builder.add_edge("finalize_upload", END)
builder.add_edge("error_handler", END)

graph = builder.compile()
graph.name = "IndexGraph"