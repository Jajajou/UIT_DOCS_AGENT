from __future__ import annotations
import json


from typing import Any, Dict, Optional, cast, List
from langgraph.graph import StateGraph, END
from agent.state import QueryState
from agent.lightrag_core import get_lightrag_core
from langchain_core.messages import HumanMessage, AIMessage, AnyMessage

# Get LightRAG Core instance (will be initialized on first use)
lightrag_core = get_lightrag_core()

def _content_to_text(content: Any) -> str:
    # content may be a str OR a list of message parts like [{"type":"text", "text":"..."}]
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                txt = (part.get("text") or "").strip()
                if txt:
                    return txt
    return ""

def _last_human_text(messages: List[AnyMessage]) -> str:
    for msg in reversed(messages or []):
        # LangChain HumanMessage OR any object with type 'human'
        if isinstance(msg, HumanMessage) or getattr(msg, "type", None) == "human":
            return _content_to_text(getattr(msg, "content", ""))
    return ""


# ---------------------- Graph Nodes ----------------------
def prepare_payload(state: QueryState) -> QueryState:
    """Validate inputs and assemble payload for LightRAG query."""
    query = state.get("query")
    
    # If no direct query, extract from messages (for Chat UI)
    if not query:
        query = _last_human_text(state.get("messages", []))
    
    mode = state.get("mode", "mix")
    top_k = state.get("top_k", 60)
    response_type = state.get("response_type", "Multiple Paragraphs")
    include_references = state.get("include_references", True)

    if not query or not isinstance(query, str):
        state["error"] = "query must be a non-empty string"
        state["final_answer"] = None # type: ignore
        state["api_payload"] = None # type: ignore
        return state

    # Map legacy/custom mode names if needed (keep passthrough for valid modes)
    mode_map = {
        "default": "mix",
    }
    mode = mode_map.get(mode, mode)

    payload: Dict[str, Any] = {
        "query": query,
        "mode": mode,
        "include_references": include_references,
        "response_type": response_type,
        "top_k": top_k,
    }
    state["api_payload"] = payload
    state["error"] = None # type: ignore
    return state


async def call_lightrag_core(state: QueryState) -> QueryState:
    """
    Call LightRAG Core directly instead of API.
    This replaces the API call with direct library usage.
    """
    if state.get("error"):
        return state

    payload = cast(Dict[str, Any], state.get("api_payload") or {})
    
    try:
        # Initialize if not already initialized
        if not lightrag_core.initialized:
            await lightrag_core.initialize()
        
        # Query using LightRAG Core
        result = await lightrag_core.query(
            query_text=payload.get("query", ""),
            mode=payload.get("mode", "mix"),
            include_references=payload.get("include_references", True),
            response_type=payload.get("response_type", "Multiple Paragraphs"),
            top_k=payload.get("top_k", 60),
            conversation_history=payload.get("conversation_history"),
            max_total_tokens=payload.get("max_total_tokens"),
            stream=False  # Core mode doesn't support streaming yet
        )
        
        # Store result
        state["api_response"] = result
        
        # Extract answer
        answer = result.get("response") or result.get("answer")
        
        if result.get("error"):
            state["error"] = result["error"]
            state["final_answer"] = None # type: ignore
        else:
            state["final_answer"] = answer # type: ignore
            
            # Append assistant message so Studio Chat shows the answer
            if answer:
                msgs = list(state.get("messages", []))
                msgs.append(AIMessage(content=answer))
                state["messages"] = msgs

    except Exception as e:
        state["error"] = str(e)
        state["api_response"] = None # type: ignore
        state["final_answer"] = None # type: ignore

    return state


# ---------------------- Builder ----------------------
builder = StateGraph(state_schema=QueryState)
builder.add_node("prepare_payload", prepare_payload)
builder.add_node("call_lightrag", call_lightrag_core)
builder.set_entry_point("prepare_payload")
builder.add_edge("prepare_payload", "call_lightrag")
builder.add_edge("call_lightrag", END)

graph = builder.compile()
graph.name = "RetrievalGraph"
