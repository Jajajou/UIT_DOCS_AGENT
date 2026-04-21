# indexing_graph.py - Matches the perfect flowchart
from __future__ import annotations

import io
import os
import re
import glob
import requests
import sys
import tempfile
import time
from pathlib import Path
from typing import Literal, List, Dict, Any, Union, Optional, cast
from urllib.parse import unquote

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END, START

from agent.config import MINERU_OCR_DIR
from agent.clients.mineru_ocr_client import MinerUOCRClient, MinerUOCRClientError
from agent.states.indexing_state import IndexingState
from agent.clients.lightrag_client import LightRAGAPIClient
from agent.utils import get_url, content_to_text, get_last_human_message, preprocess_image_for_ocr
from agent.agents.agent_temporal_extraction import extract_temporal_metadata_node
from agent.graphs.metadata_rag_subgraph import metadata_rag_subgraph
from langchain_core.messages import HumanMessage, AIMessage, AnyMessage

load_dotenv() 


api_client = LightRAGAPIClient()
mineru_client = MinerUOCRClient()

# ---------------------- Helper Functions ----------------------

def _dedupe_paths(paths: list[str]) -> list[str]:
    seen = set()
    out = []
    for p in paths:
        ap = os.path.abspath(p)
        if ap not in seen:
            seen.add(ap)
            out.append(ap)
    return out

def _parse_chat_command(msg: AnyMessage) -> Dict[str, Any]:
    """
    Parse chat message to determine command.

    Supported commands:
    - "upload /path/to/file.pdf" -> Upload single file
    - "upload /path/to/file.pdf --url https://..." -> Upload with explicit source URL
    - "upload /path/to/folder" -> Upload all files in folder
    - "scan" -> Trigger scan
    - anything else -> insert as text
    """
    content = getattr(msg, "content", "")
    text = content_to_text(content).strip()

    print("=" * 80)
    print(f"[PARSE] Input text: '{text}'")
    print("=" * 80)

    # Check for upload command with path
    if text.lower().startswith("upload ") and len(text.split(maxsplit=1)) > 1:
        rest = text.split(maxsplit=1)[1].strip()

        # Extract optional --url flag before processing the path
        explicit_url = None
        url_match = re.search(r'\s+--url\s+(\S+)', rest)
        if url_match:
            explicit_url = url_match.group(1)
            rest = rest[:url_match.start()].strip()

        path = rest
        path = os.path.expanduser(path)
        if (path.startswith('"') and path.endswith('"')) or \
           (path.startswith("'") and path.endswith("'")):
            path = path[1:-1]

        print(f"[PARSE] Detected upload command with path: {path}")
        if explicit_url:
            print(f"[PARSE] Explicit source URL: {explicit_url}")

        return {
            "command": "upload_path",
            "path": path,
            "explicit_url": explicit_url,
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


def _dedupe_file_copies(file_paths: List[str]) -> List[str]:
    """
    Remove Firecrawl dedup copies (file_001.pdf, file_001_001.pdf etc.).
    Keeps the shortest-named version for each base stem so the URL lookup
    always matches the original filename rather than a deep copy.
    """
    _DEDUP_RE = re.compile(r"([_ ]+\d+)+$")

    def base_stem(path: str) -> str:
        name = unquote(Path(path).stem).lower()
        return _DEDUP_RE.sub("", name)

    seen_bases: dict[str, str] = {}
    for fp in sorted(file_paths, key=lambda p: len(Path(p).name)):
        b = base_stem(fp)
        if b not in seen_bases:
            seen_bases[b] = fp

    original_count = len(file_paths)
    deduped = list(seen_bases.values())
    skipped = original_count - len(deduped)
    if skipped:
        print(f"[FILE_LIST] Skipped {skipped} duplicate copies (keeping shortest-named per stem)")
    return deduped


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

def prepare_indexing(state: IndexingState) -> Dict[str, Any]:
    """Prepare indexing request - determine command type."""
    
    messages = state.get("messages", [])
    if not messages:
        return {
            "error": "No input provided",
            "status_message": "Error: No input"
        }
    
    # Get last human message
    print("Messages list length:", len(messages))
    last_msg = get_last_human_message(messages)
    
    if not last_msg:
        return {
            "error": "No input provided",
            "status_message": "Error: No input"
        }
    
    # Parse command
    parsed = _parse_chat_command(last_msg)
    command = parsed["command"]
    
    print("=" * 80)
    print(f"[COMMAND] {command}")
    print("=" * 80)
    
    # Store command type and data
    if command == "upload_path":
        return {
            "source_type": "file",
            "input_source": parsed["path"],
            "explicit_url": parsed.get("explicit_url"),
            "description": f"Upload from path: {parsed['path']}",
            "error": None
        }
    
    elif command == "scan":
        return {
            "source_type": "scan",
            "input_source": None,
            "description": "Manual scan triggered",
            "error": None
        }
    
    elif command == "text":
        return {
            "source_type": "text",
            "input_source": parsed["text"],
            "description": "Insert text from chat",
            "error": None
        }
    
    else:
        return {
            "error": f"Unknown command: {command}",
            "status_message": "Error: Unknown command"
        }


def prepare_file_list(state: IndexingState) -> Dict[str, Any]:
    """Prepare list of files from path (file or directory)."""
    
    path = state.get("input_source")
    
    if not path or not isinstance(path, str):
        return {"error": "Invalid path"}
    
    # Check if path exists
    if not os.path.exists(path):
        error_msg = f"Path not found: {path}"
        return {
            "error": error_msg,
            "status_message": "Error: Path not found",
            "messages": [AIMessage(content=f"{error_msg}")]
        }
    
    # Get files from path
    file_paths = _get_files_from_path(path, recursive=False)
    
    if not file_paths:
        error_msg = f"No files found in: {path}"
        return {
            "error": error_msg,
            "status_message": "Error: No files",
            "messages": [AIMessage(content=f"{error_msg}")]
        }
    
    # Filter supported files
    supported_files = _filter_supported_files(file_paths)
    # Deduplicate: skip files whose stem is a _NNN copy of an already-seen stem.
    # Firecrawl saves duplicate PDFs as file_001.pdf, file_001_001.pdf etc.
    # We only need one copy; LightRAG deduplicates by content hash anyway, and
    # uploading the deep copies last risks overwriting a correctly-stored URL.
    supported_files = _dedupe_file_copies(supported_files)
    
    if not supported_files:
        total_files = len(file_paths)
        skipped_files = [os.path.basename(f) for f in file_paths[:5]]
        more_text = f" and {total_files - 5} more" if total_files > 5 else ""
        
        error_msg = (
            f"No supported file types found in: {path}\n\n"
            f"Found {total_files} file(s) but none are supported.\n"
            f"Skipped: {', '.join(skipped_files)}{more_text}"
        )
        return {
            "error": error_msg,
            "status_message": "Error: No supported files",
            "messages": [AIMessage(content=f"{error_msg}")]
        }
    
    # Show preview
    total_files = len(supported_files)
    preview_count = min(5, total_files)
    preview_files = [os.path.basename(f) for f in supported_files[:preview_count]]
    more_text = f" and {total_files - preview_count} more" if total_files > preview_count else ""
    
    print(f"[FILE_LIST] Found {total_files} supported file(s)")
    print(f"[FILE_LIST] Files: {', '.join(preview_files)}{more_text}")
    
    # Initialize file processing state
    existing = state.get("file_list", [])
    merged = _dedupe_paths(existing + supported_files)
    
    # Only reset index if it's not set (initial run)
    # Assuming 0 if not set
    updates = {
        "file_list": merged,
        "error": None
    }
    
    if "current_file_index" not in state:
        updates["current_file_index"] = 0
        
    return updates


def check_if_pdf(state: IndexingState) -> Dict[str, Any]:
    """Check if current file is a PDF."""

    file_list = state.get("file_list", [])
    current_index = state.get("current_file_index", 0)

    print(f"current file list: {len(file_list)} - current_index: {current_index}")

    if current_index >= len(file_list):
        # No more files
        return {
            "is_pdf": False,
            "all_files_processed": True
        }

    current_file = file_list[current_index]
    print(f"current file path: {current_file}")
    is_pdf = _is_pdf(current_file)

    print(f"[CHECK_PDF] File {current_index + 1}/{len(file_list)}: {os.path.basename(current_file)}")
    print(f"[CHECK_PDF] Is PDF: {is_pdf}")

    # Set file_path and file_source for all files (for temporal extraction)
    file_source = get_url(current_file)

    return {
        "is_pdf": is_pdf,
        "current_file_path": current_file,
        "file_path": current_file,
        "file_source": file_source,
        "all_files_processed": False
    }


def parse_with_ocr(state: IndexingState) -> Dict[str, Any]:
    """Pre-processes and parses a PDF file with MinerU OCR."""
    file_path = state.get("current_file_path")
    if not file_path:
        return {"ocr_error": "No file path for OCR"}

    try:
        print(f"[OCR] Processing: {os.path.basename(file_path)}")
        file_stem = Path(file_path).stem
        output_path = str(MINERU_OCR_DIR / file_stem)

        md_content, output_path = mineru_client.parse_and_get_markdown(
            file_path,
            output_dir=output_path,
        )

        print(f"[OCR] Success - {len(md_content):,} chars")

        return {
            "parsed_content": md_content,
            "ocr_output_dir": output_path,
            "ocr_success": True,
            "file_path": file_path,
        }
    except Exception as e:
        print(f"[OCR] Failed: {str(e)}")
        return {
            "parsed_content": "",
            "ocr_success": False,
            "ocr_error": str(e),
        }


async def extract_temporal_metadata_rag(state: IndexingState) -> Dict[str, Any]:
    """
    Extract temporal metadata using the Metadata RAG subgraph.

    This is an async wrapper that invokes the async metadata RAG subgraph.
    Maps between IndexingState and MetadataRAGState.
    """
    from agent.graphs.metadata_rag_subgraph import metadata_rag_subgraph

    try:
        # Get document text from either parsed_content (PDF) or file
        doc_text = state.get("parsed_content", "")
        if not doc_text:
            # For non-PDF files, try reading from file
            file_path = state.get("current_file_path")
            if file_path:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        doc_text = f.read()
                except Exception as e:
                    print(f"[Metadata RAG] WARNING: Could not read file {file_path}: {e}")

        file_source = state.get("file_source") or state.get("current_file_path", "unknown")
        doc_id = state.get("doc_id", "")

        if not doc_text:
            print(f"[Metadata RAG] WARNING: No document text for {file_source}, falling back to regex")
            # Use old extraction as fallback
            return await extract_temporal_metadata_node(state)

        # Prepare subgraph input
        subgraph_input = {
            "doc_text": doc_text,
            "file_source": file_source,
            "doc_id": doc_id,
            "success": False
        }

        print(f"[Metadata RAG] Processing: {file_source}")

        # Invoke async subgraph
        result = await metadata_rag_subgraph.ainvoke(subgraph_input)

        success = result.get("success", False)
        final_metadata = result.get("final_metadata", {})
        confidence = result.get("extraction_confidence", 0.0)

        if success:
            print(f"[Metadata RAG] Confidence: {confidence:.2f} | Metadata: {final_metadata}")
            return {
                "document_metadata": final_metadata,
                "temporal_extraction_complete": True
            }
        else:
            error = result.get("error", "Unknown error")
            print(f"[Metadata RAG] Failed: {error}, falling back to regex")
            return await extract_temporal_metadata_node(state)

    except Exception as e:
        print(f"[Metadata RAG] Exception: {str(e)}, falling back to regex")
        return await extract_temporal_metadata_node(state)


def upload_to_lightrag(state: IndexingState) -> Dict[str, Any]:
    """Upload to LightRAG (handles text, scan, and files)."""
    
    source_type = state.get("source_type")
    
    # Handle scan
    if source_type == "scan":
        try:
            result = api_client.trigger_scan()
            track_id = result.get("track_id", "N/A")
            response_text = f"✓ Scan initiated!\n\nTrack ID: `{track_id}`\n\nProcessing in background..."
            
            return {
                "api_response": result,
                "status_message": "Scan initiated",
                "messages": [AIMessage(content=response_text)]
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "messages": [AIMessage(content=f"Error: {str(e)}")]
            }
    
    # Handle text
    if source_type == "text":
        try:
            input_source = state.get("input_source")
            if isinstance(input_source, list):
                result = api_client.insert_texts(cast(List[str], input_source))
            else:
                result = api_client.insert_text(cast(str, input_source))
            
            track_id = result.get("track_id", "N/A")
            response_text = f"✓ Text inserted!\n\nTrack ID: `{track_id}`\n\nProcessing in background..."
            
            return {
                "api_response": result,
                "status_message": "Text inserted",
                "messages": [AIMessage(content=response_text)]
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "messages": [AIMessage(content=f"Error: {str(e)}")]
            }
    
    # Handle file upload
    if source_type == "file":
        file_path = state.get("current_file_path")

        if not file_path:
            return {}

        file_name = os.path.basename(file_path)
        file_list = state.get("file_list", [])
        current_index = state.get("current_file_index", 0)
        # explicit_url is only meaningful for single-file uploads; ignore for batch
        url = (state.get("explicit_url") if len(file_list) == 1 else None) or get_url(file_path)

        print(f"[UPLOAD] {current_index + 1}/{len(file_list)}: {file_name}, {url}")

        upload_result = {}
        doc_id = None

        try:
            parsed_content = state.get("parsed_content")

            # Upload as text if we have parsed content (from OCR or direct file read)
            if parsed_content:
                # Upload parsed content
                result = api_client.insert_text(
                    text=parsed_content,
                    file_source=url
                )

                track_id = result.get("track_id")

                if track_id:
                    print(f"[UPLOAD] ✓ Upload started (Text) - Track: {track_id}")
                else:
                    print(f"[UPLOAD] WARNING: No track_id returned")

                upload_result = {
                    "file_path": file_path,
                    "file_name": file_name,
                    "file_source": url,
                    "track_id": track_id,
                    "doc_id": None,  # Will be retrieved when saving metadata
                    "status": "success",
                    "parse_with_ocr": state.get("ocr_success", False),
                    "output_dir": state.get("ocr_output_dir"),
                    "markdown_length": len(parsed_content),
                    "response": result
                }

            else:
                # Direct file upload (binary files without parsed content)
                result = api_client.upload_file(file_path, file_source=url)

                doc_id = result.get("doc_id")
                track_id = result.get("track_id")

                upload_result = {
                    "file_path": file_path,
                    "file_name": file_name,
                    "file_source": url,
                    "track_id": track_id,
                    "doc_id": doc_id,
                    "status": "success",
                    "parse_with_ocr": False,
                    "response": result
                }

                ocr_error = state.get("ocr_error")
                if ocr_error:
                    upload_result["fallback_reason"] = ocr_error

                print(f"[UPLOAD] ✓ Success (Direct) - Track: {result.get('track_id')}, Doc ID: {doc_id}")

            # Save temporal metadata to separate table (to avoid LightRAG overwrite)
            document_metadata = state.get("document_metadata", {})
            if track_id and document_metadata and state.get("temporal_extraction_complete"): #type: ignore
                try:
                    print(f"[METADATA] Saving temporal metadata for {file_name} (track_id: {track_id})...")

                    # LightRAG processes insert_text asynchronously — poll until the
                    # lightrag_doc_status row appears (usually < 10s after upload).
                    doc_id = None
                    workspace = None
                    for _attempt in range(60):
                        conn = api_client._get_pg_connection()
                        workspace = os.getenv("WORKSPACE", "default")
                        try:
                            with conn.cursor() as cur:
                                cur.execute(
                                    "SELECT id FROM lightrag_doc_status WHERE workspace = %s AND track_id = %s",
                                    (workspace, track_id)
                                )
                                row = cur.fetchone()
                                doc_id = row[0] if row else None
                        finally:
                            conn.close()
                        if doc_id:
                            break
                        print(f"[METADATA] Waiting for LightRAG to create doc row (attempt {_attempt + 1}/60)...")
                        time.sleep(2)

                    if doc_id:
                        # Save to separate temporal_metadata table
                        metadata_result = api_client.save_temporal_metadata(
                            track_id=track_id,
                            doc_id=doc_id,
                            metadata=document_metadata
                        )

                        if metadata_result.get("success"):
                            print(f"[METADATA] ✓ Temporal metadata saved to separate table (doc_id: {doc_id})")
                            upload_result["temporal_metadata_saved"] = True
                            upload_result["doc_id"] = doc_id

                            # Handle reverse linking for amended documents
                            amended_docs = document_metadata.get("amends_documents", [])
                            if amended_docs and doc_id:
                                print(f"[LINKING] Processing amendments for {len(amended_docs)} documents...")
                                link_result = api_client.link_amended_documents(doc_id, amended_docs)

                                linked_count = len(link_result.get("linked_docs", []))
                                upload_result["linked_amendments"] = linked_count

                                if linked_count > 0:
                                    print(f"[LINKING] ✓ Successfully linked to {linked_count} old documents")
                                else:
                                    print(f"[LINKING] WARNING: No matching old documents found to link")
                        else:
                            print(f"[METADATA] ✗ Failed to save metadata: {metadata_result.get('error')}")
                            upload_result["temporal_metadata_error"] = metadata_result.get("error")
                    else:
                        print(f"[METADATA] WARNING: Document not found in LightRAG (track_id: {track_id})")
                        upload_result["temporal_metadata_error"] = "Document not found in LightRAG"

                except Exception as meta_error:
                    print(f"[METADATA] ✗ Exception saving metadata: {str(meta_error)}")
                    upload_result["temporal_metadata_error"] = str(meta_error)

        except Exception as e:
            print(f"[UPLOAD] ✗ Failed: {str(e)}")

            upload_result = {
                "file_path": file_path,
                "file_name": file_name,
                "file_source": url,
                "status": "failed",
                "error": str(e)
            }

        # Move to next file
        next_index = current_index + 1

        # Return updates
        # Note: upload_results uses operator.add, so we return a list with the single result
        return {
            "upload_results": [upload_result],
            "current_file_index": next_index,
            "doc_id": upload_result.get("doc_id"),
            # Reset per-file state
            "current_file_path": None,
            "parsed_content": None,
            "ocr_success": False,
            "ocr_error": None,
            "document_metadata": {},
            "temporal_extraction_complete": False
        }
    
    return {}

def finalize_upload(state: IndexingState) -> Dict[str, Any]:
    """Finalize and send summary."""
    
    upload_results = state.get("upload_results", [])
    
    if not upload_results:
        return {}
    
    success_count = sum(1 for r in upload_results if r["status"] == "success")
    failed_count = len(upload_results) - success_count
    ocr_count = sum(1 for r in upload_results if r.get("parse_with_ocr"))
    
    response_lines = []
    file_list = state.get("file_list", [])
    is_batch = len(file_list) > 1
    
    if is_batch:
        response_lines.append(f"**Batch Upload Complete**")
        response_lines.append(f"✓ {success_count} succeeded | ✗ {failed_count} failed | Total: {len(file_list)}")
    else:
        # Use first file from results or list
        file_name = "Unknown"
        if file_list:
            file_name = os.path.basename(file_list[0])
        elif upload_results:
            file_name = upload_results[0].get("file_name", "Unknown")
            
        status_icon = "✓" if success_count > 0 else "✗"
        response_lines.append(f"{status_icon} **File:** `{file_name}`")
    
    response_lines.append("")
    
    if ocr_count > 0:
        response_lines.append(f"**PDFs parsed with MinerU OCR:** {ocr_count}")
        response_lines.append("")
    
    if success_count > 0:
        response_lines.append("**✓ Successful uploads:**")
        for result in upload_results:
            if result["status"] == "success":
                extra = ""
                if result.get("parse_with_ocr"):
                    md_len = result.get("markdown_length", 0)
                    extra = f" (MinerU: {md_len:,} chars)"
                elif result.get("fallback_reason"):
                    extra = " (Direct - OCR failed)"
                
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
    
    return {
        "messages": [AIMessage(content=response_text)],
        "status_message": "Complete",
        "api_response": {"results": upload_results}
    }


def error_handler(state: IndexingState) -> Dict[str, Any]:
    """Handle errors."""
    error_msg = state.get("error") or "Unknown error"
    status_message = state.get("status_message") or "Error"
    
    updates: Dict[str, Any] = {
        "status_message": status_message
    }
    
    # Only add message if it doesn't exist or last one isn't the same error
    msgs = state.get("messages", [])
    should_add = True
    if msgs and isinstance(msgs[-1], AIMessage) and error_msg in str(msgs[-1].content):
        should_add = False
        
    if should_add:
        updates["messages"] = [AIMessage(content=f"Error: {error_msg}")]
    
    return updates


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

def route_after_pdf_check(state: IndexingState) -> Literal["parse_with_ocr", "extract_temporal_metadata"]:
    """Route based on whether file is PDF."""
    if state.get("is_pdf"):
        return "parse_with_ocr"
    # Non-PDF files go directly to temporal extraction
    return "extract_temporal_metadata"

def route_after_upload(state: IndexingState) -> Literal["check_if_pdf", "finalize_upload", "end"]:
    """Route after upload: check if more files or done."""
    source_type = state.get("source_type")
    
    if source_type == "file":
        # Check if more files to process
        file_list = state.get("file_list", [])
        current_index = state.get("current_file_index", 0)
        
        print(f"current_index - {current_index:,}")
        print(f"file_list - {len(file_list):,}")

        if current_index < len(file_list):
            # current_file_index
            return "check_if_pdf"
        else:
            return "finalize_upload"
    else:
        # Text or scan - we're done
        return "end"


# ---------------------- Graph Builder ----------------------

builder = StateGraph(state_schema=IndexingState)

# Add all nodes
# builder.add_node("ingest_user_text", ingest_user_text)
builder.add_node("prepare_indexing", prepare_indexing)
builder.add_node("prepare_file_list", prepare_file_list)
builder.add_node("check_if_pdf", check_if_pdf)
builder.add_node("parse_with_ocr", parse_with_ocr)
builder.add_node("extract_temporal_metadata", extract_temporal_metadata_rag)
builder.add_node("upload_to_lightrag", upload_to_lightrag)
builder.add_node("finalize_upload", finalize_upload)
builder.add_node("error_handler", error_handler)

# Build the graph following the flowchart exactly
builder.add_edge(START, "prepare_indexing")
# builder.add_edge("ingest_user_text", "prepare_indexing")

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
        "parse_with_ocr": "parse_with_ocr",
        "extract_temporal_metadata": "extract_temporal_metadata"
    }
)

# After parsing PDF, extract temporal metadata
builder.add_edge("parse_with_ocr", "extract_temporal_metadata")

# After temporal extraction, upload to LightRAG
builder.add_edge("extract_temporal_metadata", "upload_to_lightrag")

builder.add_conditional_edges(
    "upload_to_lightrag",
    route_after_upload,
    {
        "check_if_pdf": "check_if_pdf",
        "finalize_upload": "finalize_upload",
        "end": END
    }
)

builder.add_edge("finalize_upload", END)
builder.add_edge("error_handler", END)

graph = builder.compile()
graph.name = "IndexGraph"
