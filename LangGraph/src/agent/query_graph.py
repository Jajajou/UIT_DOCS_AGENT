from __future__ import annotations
import json


from typing import Any, Dict, Optional, cast, List
from langgraph.graph import StateGraph, END
from agent.state import QueryState
from agent.lightrag_client import LightRAGAPIClient
from langchain_core.messages import HumanMessage, AIMessage, AnyMessage

# Reuse a single API client (reads env for URL, API key, token)
api_client = LightRAGAPIClient()

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
    """Validate inputs and assemble payload for LightRAG /query."""
    query = state.get("query")
    
    # If no direct query, extract from messages (for Chat UI)
    if not query:
        query = _last_human_text(state.get("messages", []))
    
    mode = state.get("mode", "mix")
    top_k = state.get("top_k", 5)

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
        "include_references": True,
        "top_k": top_k,
    }
    state["api_payload"] = payload
    state["error"] = None # type: ignore
    return state

# ---------------------- Helpers ----------------------
def _to_conv_item(msg: AnyMessage) -> Dict[str, Any]:
    if isinstance(msg, HumanMessage):
        return {"role": "user", "content": msg.content}
    elif isinstance(msg, AIMessage):
        return {"role": "assistant", "content": msg.content}
    return {"role": "unknown", "content": getattr(msg, "content", "")}

def call_query_api(state: QueryState) -> QueryState:
    if state.get("error"):
        return state

    payload = cast(Dict[str, Any], state.get("api_payload") or {})
    try:
        endpoint = "/query/stream" if payload.get("stream") else "/query"
        # Use raw _post to preserve full payload shape
        r = api_client._post(endpoint, json=payload, stream=payload.get("stream", False))
        r.raise_for_status()

        if payload.get("stream"):
            # NDJSON streaming
            chunks: List[str] = []
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    if "response" in obj and isinstance(obj["response"], str):
                        chunks.append(obj["response"])
                    state["api_response"] = obj
            answer = ("".join(chunks)).strip() or None
        else:
            resp = r.json()
            state["api_response"] = resp
            answer = resp.get("response") or resp.get("answer")

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
builder.add_node("call_api", call_query_api)
builder.set_entry_point("prepare_payload")
builder.add_edge("prepare_payload", "call_api")
builder.add_edge("call_api", END)

graph = builder.compile()
graph.name = "RetrievalGraph"