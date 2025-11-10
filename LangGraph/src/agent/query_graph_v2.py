"""
Query Graph V2: 2-Agent RAG Pipeline with Confidence Scoring

This graph implements a sophisticated RAG pipeline with:
- Agent 1: Query Understanding with confidence scoring
- Agent 2: Data Quality Assessment and Response Generation
- Fallback mechanisms for low confidence scenarios
- Hyperlinked references in responses
"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, AnyMessage

from agent.state_v2 import QueryStateV2, DEFAULT_RETRIEVAL_MODE, DEFAULT_TOP_K
from agent.lightrag_client import LightRAGAPIClient
from agent.agent1_query_understanding import (
    agent1_understand_query,
    decide_after_agent1,
    ask_clarification
)
from agent.agent2_response_generation import (
    agent2_assess_data_quality,
    agent2_generate_response
)


# ============================================================================
# LightRAG API Client
# ============================================================================

api_client = LightRAGAPIClient()


# ============================================================================
# Helper Functions
# ============================================================================

def _content_to_text(content: Any) -> str:
    """Extract text from message content."""
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
    """Get text from the last human message."""
    for msg in reversed(messages or []):
        if isinstance(msg, HumanMessage) or getattr(msg, "type", None) == "human":
            return _content_to_text(getattr(msg, "content", ""))
    return ""


# ============================================================================
# Graph Nodes
# ============================================================================

def prepare_input(state: QueryStateV2) -> QueryStateV2:
    """
    Prepare input for the pipeline.
    
    Extract query from messages if not provided directly.
    """
    
    query = state.get("query")
    
    # If no direct query, extract from messages
    if not query:
        query = _last_human_text(state.get("messages", []))
    
    if not query:
        state["error"] = "No query provided"
        state["status_message"] = "Error: No query"
        return state
    
    # Store query
    state["query"] = query
    state["error"] = None  # type: ignore
    
    print("=" * 80)
    print(f"[PREPARE] Query: {query}")
    print("=" * 80)
    
    return state


def retrieve_data(state: QueryStateV2) -> QueryStateV2:
    """
    Retrieve data from LightRAG using /query/data endpoint.
    
    This node:
    1. Uses parsed_intention from Agent 1
    2. Calls LightRAG /query/data (NOT /query)
    3. Stores raw entities, relationships, chunks
    """
    
    # Get query (use parsed_intention if available)
    query = state.get("parsed_intention") or state.get("query", "")
    
    if not query:
        state["error"] = "No query for retrieval"
        return state
    
    # Get retrieval parameters
    mode = state.get("retrieval_mode", DEFAULT_RETRIEVAL_MODE)
    top_k = state.get("top_k", DEFAULT_TOP_K)
    chunk_top_k = state.get("chunk_top_k")
    max_entity_tokens = state.get("max_entity_tokens")
    max_relation_tokens = state.get("max_relation_tokens")
    max_total_tokens = state.get("max_total_tokens")
    
    print("=" * 80)
    print(f"[RETRIEVE] Query: {query}")
    print(f"[RETRIEVE] Mode: {mode}, Top-K: {top_k}")
    print("=" * 80)
    
    try:
        # Call LightRAG /query/data endpoint
        result = api_client.query_data(
            query_text=query,
            mode=mode,
            top_k=top_k,
            chunk_top_k=chunk_top_k,
            max_entity_tokens=max_entity_tokens,
            max_relation_tokens=max_relation_tokens,
            max_total_tokens=max_total_tokens
        )
        
        # Parse result
        # Expected format: {"entities": [...], "relationships": [...], "chunks": [...]}
        entities = result.get("entities", [])
        relationships = result.get("relationships", [])
        chunks = result.get("chunks", [])
        
        # Store in state
        state["retrieved_entities"] = entities
        state["retrieved_relationships"] = relationships
        state["retrieved_chunks"] = chunks
        state["retrieval_metadata"] = {
            "mode": mode,
            "top_k": top_k,
            "total_entities": len(entities),
            "total_relationships": len(relationships),
            "total_chunks": len(chunks)
        }
        
        print(f"[RETRIEVE] ✓ Retrieved {len(entities)} entities, {len(relationships)} relationships, {len(chunks)} chunks")
        
        state["error"] = None  # type: ignore
        
    except Exception as e:
        error_msg = f"Retrieval error: {str(e)}"
        print(f"[RETRIEVE] ✗ {error_msg}")
        
        state["error"] = error_msg
        state["retrieved_entities"] = []
        state["retrieved_relationships"] = []
        state["retrieved_chunks"] = []
    
    return state


def format_final_answer(state: QueryStateV2) -> QueryStateV2:
    """
    Format final answer with confidence summary.
    
    This node adds metadata about confidence scores to help with debugging/monitoring.
    """
    
    # Build confidence summary
    confidence_summary = {
        "query_confidence": state.get("query_confidence", 0.0),
        "query_confidence_reason": state.get("query_confidence_reason", ""),
        "data_quality_score": state.get("data_quality_score", 0.0),
        "data_quality_reason": state.get("data_quality_reason", ""),
        "data_coverage": state.get("data_coverage", "unknown"),
        "response_type": state.get("response_type", "unknown")
    }
    
    state["confidence_summary"] = confidence_summary
    
    # Final answer is already set by agent2_generate_response
    # Just add status message
    response_type = state.get("response_type", "unknown")
    
    if response_type == "full_answer":
        state["status_message"] = "Success: Full answer generated"
    elif response_type == "partial_answer":
        state["status_message"] = "Success: Partial answer generated"
    elif response_type == "fallback":
        state["status_message"] = "Fallback: Suggested to contact advisor"
    elif response_type == "clarification":
        state["status_message"] = "Waiting for user clarification"
    else:
        state["status_message"] = "Completed"
    
    print("=" * 80)
    print(f"[FINAL] Response Type: {response_type}")
    print(f"[FINAL] Query Confidence: {confidence_summary['query_confidence']:.2f}")
    print(f"[FINAL] Data Quality: {confidence_summary['data_quality_score']:.2f}")
    print("=" * 80)
    
    return state


# ============================================================================
# Graph Builder
# ============================================================================

builder = StateGraph(state_schema=QueryStateV2)

# Add nodes
builder.add_node("prepare_input", prepare_input)
builder.add_node("agent1_understand_query", agent1_understand_query)
builder.add_node("ask_clarification", ask_clarification)
builder.add_node("retrieve_data", retrieve_data)
builder.add_node("agent2_assess_data_quality", agent2_assess_data_quality)
builder.add_node("agent2_generate_response", agent2_generate_response)
builder.add_node("format_final_answer", format_final_answer)

# Set entry point
builder.set_entry_point("prepare_input")

# Add edges
builder.add_edge("prepare_input", "agent1_understand_query")

# Conditional edge after Agent 1
builder.add_conditional_edges(
    "agent1_understand_query",
    decide_after_agent1,
    {
        "ask_clarification": "ask_clarification",
        "retrieve_data": "retrieve_data"
    }
)

# Clarification ends the flow (wait for user)
builder.add_edge("ask_clarification", END)

# Continue with retrieval and Agent 2
builder.add_edge("retrieve_data", "agent2_assess_data_quality")
builder.add_edge("agent2_assess_data_quality", "agent2_generate_response")
builder.add_edge("agent2_generate_response", "format_final_answer")
builder.add_edge("format_final_answer", END)

# Compile graph
graph = builder.compile()
graph.name = "RetrievalGraphV2"


# ============================================================================
# Export
# ============================================================================

__all__ = ["graph", "QueryStateV2"]
