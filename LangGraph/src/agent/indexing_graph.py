# indexing_graph.py
from __future__ import annotations

from typing import Literal, List, Dict, Any, Union, Optional, cast
from langgraph.graph import StateGraph, END
from agent.state import IndexingState
from agent.lightrag_client import LightRAGAPIClient


api_client = LightRAGAPIClient()


# ------------------------- Graph Nodes -------------------------
def ingestion_router(state: IndexingState) -> Literal["call_api", "error_handler"]:
    """Validate inputs and decide next step."""
    source_type = state.get("source_type")
    input_source = state.get("input_source")

    # Basic validation
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
    """Call LightRAG ingestion endpoints based on source_type."""
    source_type: str = cast(str, state["source_type"])
    input_source: Union[str, List[str], None] = state.get("input_source")
    description: Optional[str] = state.get("description")

    # Prepare payload record (for debugging/traceability)
    payload: Dict[str, Any] = {
        "source_type": source_type,
        "description": description,
    }

    try:
        if source_type == "file":
            if isinstance(input_source, list):
                results = []
                for path in input_source:
                    res = api_client.upload_file(path)
                    results.append(res)
                state["api_response"] = {"results": results}
            else:
                state["api_response"] = api_client.upload_file(cast(str, input_source))

        elif source_type == "text":
            if isinstance(input_source, list):
                # batch insert text
                state["api_response"] = api_client.insert_texts(cast(List[str], input_source))
            else:
                state["api_response"] = api_client.insert_text(cast(str, input_source))

        elif source_type == "scan":
            state["api_response"] = api_client.trigger_scan()

        elif source_type == "batch":
            # For now, treat as a list of files (most common case).
            # If you need mixed file/text batches, extend here.
            if not isinstance(input_source, list):
                raise ValueError("batch expects a list of file paths")
            results = []
            for path in input_source:
                results.append(api_client.upload_file(path))
            state["api_response"] = {"results": results}

        else:
            raise ValueError(f"Unknown source_type: {source_type}")

        payload["ok"] = True
        state["api_payload"] = payload
        state["status_message"] = "Ingestion successful"
        state["error"] = None
        return state

    except Exception as e:
        state["api_payload"] = payload
        state["api_response"] = None
        state["status_message"] = "Ingestion failed"
        state["error"] = str(e)
        return state


def error_handler(state: IndexingState) -> IndexingState:
    """No-op node to return state with error info."""
    state["status_message"] = state.get("status_message") or "Error"
    return state


# ------------------------- Builder -------------------------
builder = StateGraph(state_schema=IndexingState)
builder.add_node("call_api", call_api)
builder.add_node("error_handler", error_handler)
builder.set_conditional_entry_point(
    ingestion_router, {"call_api": "call_api", "error_handler": "error_handler"}
)
builder.add_edge("call_api", END)
builder.add_edge("error_handler", END)
graph = builder.compile()
graph.name = "IndexGraph"
