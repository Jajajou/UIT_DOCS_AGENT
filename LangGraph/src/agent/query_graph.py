"""
Query Graph V3: 3-Agent RAG Pipeline with Reranker

This graph implements an advanced RAG pipeline with:
- Agent 1: Query Understanding with automatic parameter tuning
- Reranker: Score and re-rank all retrieved data
- Agent 2: Confidence Assessment based on combined scores
- Agent 3: Response Generation with high-quality reranked data
- Multi-level confidence thresholds and fallback mechanisms
"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from langgraph.graph import StateGraph, START,END
from langchain_core.messages import HumanMessage, AIMessage, AnyMessage

from agent.query_state import (
    QueryState,
    DEFAULT_RETRIEVAL_MODE,
    DEFAULT_TOP_K,
    DEFAULT_CHUNK_TOP_K
)
from agent.lightrag_client import LightRAGAPIClient
from agent.reranker import MultiSourceReranker
from agent.agent1_query_understanding import (
    agent1_understand_query,
    decide_after_agent1,
    ask_clarification
)
from agent.agent2_confidence_assessment import (
    agent2_assess_confidence,
    decide_after_agent2,
    ask_followup
)
from agent.agent3_response_generation import agent3_generate_response


# ============================================================================
# API Clients
# ============================================================================

api_client = LightRAGAPIClient()
reranker = MultiSourceReranker()


# ============================================================================
# Helper Functions
# ============================================================================

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

        return "".join(texts) if texts else ""
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

def prepare_input(state: QueryState) -> QueryState:
    """
    Prepare input for the pipeline.
    
    Extract query from messages if not provided directly.
    """
    
    # Extract query
    messages = state.get("messages", [])
    if not messages:
        state["error"] = "No input provided"
        state["status_message"] = "Error: No input"
        return state
    
    # Get last human message
    last_msg = _last_human_text(messages)
    state["query"] = _content_to_text(last_msg)
    query = state["query"]
    
    # Store query
    state["query"] = query
    state["error"] = None  # type: ignore
    
    print("=" * 80)
    print(f"[PREPARE] Query: {query}")
    print("=" * 80)
    
    return state


def retrieve_data(state: QueryState) -> QueryState:
    """
    Retrieve data from LightRAG using /query/data endpoint.
    
    This node:
    1. Uses parsed_intention from Agent 1
    2. Uses tuned parameters (mode, top_k, chunk_top_k) from Agent 1
    3. Calls LightRAG /query/data
    4. Stores raw entities, relationships, chunks
    """
    
    # Get query (use parsed_intention if available)
    query = state.get("parsed_intention") or state.get("query", "")
    
    if not query:
        state["error"] = "No query for retrieval"
        return state
    
    # Get retrieval parameters (tuned by Agent 1)
    mode = state.get("retrieval_mode", DEFAULT_RETRIEVAL_MODE)
    top_k = state.get("top_k", DEFAULT_TOP_K)
    chunk_top_k = state.get("chunk_top_k", DEFAULT_CHUNK_TOP_K)
    max_entity_tokens = state.get("max_entity_tokens")
    max_relation_tokens = state.get("max_relation_tokens")
    max_total_tokens = state.get("max_total_tokens")
    
    print("=" * 80)
    print(f"[RETRIEVE] Query: {query}")
    print(f"[RETRIEVE] Mode: {mode}, Top-K: {top_k}, Chunk-top-k: {chunk_top_k}")
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
        entities = result["data"]["entities"]
        relationships = result["data"]["relationships"]
        chunks = result["data"]["chunks"]
        metadata = result["metadata"]
        
        # Store in state
        state["retrieved_entities"] = entities
        state["retrieved_relationships"] = relationships
        state["retrieved_chunks"] = chunks
        state["retrieval_metadata"] = {
            "mode": metadata["query_mode"],
            "top_k": top_k,
            "chunk_top_k": chunk_top_k,
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


def rerank_data(state: QueryState) -> QueryState:
    """
    Rerank all retrieved data using the reranker.
    
    This node:
    1. Gets query and retrieved data
    2. Calls reranker to score and re-rank all items
    3. Stores reranked data with scores
    4. Calculates aggregate confidence
    """
    
    # Get query
    query = state.get("parsed_intention") or state.get("query", "")
    
    if not query:
        state["error"] = "No query for reranking"
        return state
    
    # Get retrieved data
    entities = state.get("retrieved_entities", [])
    relationships = state.get("retrieved_relationships", [])
    chunks = state.get("retrieved_chunks", [])
    
    if not entities and not relationships and not chunks:
        print("[RERANK] No data to rerank, setting zero confidence")
        state["reranked_entities"] = []
        state["reranked_relationships"] = []
        state["reranked_chunks"] = []
        state["entity_scores"] = []
        state["relationship_scores"] = []
        state["chunk_scores"] = []
        state["rerank_confidence"] = 0.0
        state["rerank_metadata"] = {"error": "No data to rerank"}
        return state
    
    try:
        # Rerank all sources
        result = reranker.rerank_all(
            query=query,
            entities=entities,
            relationships=relationships,
            chunks=chunks,
            top_k_entities=None,  # Keep all
            top_k_relationships=None,
            top_k_chunks=None
        )
        
        # Store in state
        state["reranked_entities"] = result["reranked_entities"]
        state["reranked_relationships"] = result["reranked_relationships"]
        state["reranked_chunks"] = result["reranked_chunks"]
        state["entity_scores"] = result["entity_scores"]
        state["relationship_scores"] = result["relationship_scores"]
        state["chunk_scores"] = result["chunk_scores"]
        state["rerank_confidence"] = result["overall_confidence"]
        state["rerank_metadata"] = result["metadata"]
        
        state["error"] = None  # type: ignore
        
    except Exception as e:
        error_msg = f"Reranking error: {str(e)}"
        print(f"[RERANK] ✗ {error_msg}")
        
        state["error"] = error_msg
        state["reranked_entities"] = []
        state["reranked_relationships"] = []
        state["reranked_chunks"] = []
        state["entity_scores"] = []
        state["relationship_scores"] = []
        state["chunk_scores"] = []
        state["rerank_confidence"] = 0.0
        state["rerank_metadata"] = {"error": error_msg}
    
    return state


def format_final_answer(state: QueryState) -> QueryState:
    """
    Format final answer with confidence summary.
    
    This node adds metadata about all confidence scores for debugging/monitoring.
    """
    
    # Build confidence summary
    confidence_summary = {
        "query_confidence": state.get("query_confidence", 0.0),
        "query_confidence_reason": state.get("query_confidence_reason", ""),
        "rerank_confidence": state.get("rerank_confidence", 0.0),
        "overall_confidence": state.get("overall_confidence", 0.0),
        "confidence_reason": state.get("confidence_reason", ""),
        "response_type": state.get("response_type", "unknown"),
        "tuning_reason": state.get("tuning_reason", ""),
        "retrieval_mode": state.get("retrieval_mode", ""),
        "top_k": state.get("top_k", 0),
        "chunk_top_k": state.get("chunk_top_k", 0)
    }
    
    state["confidence_summary"] = confidence_summary
    
    # Final answer is already set by agent3_generate_response
    # Just add status message
    response_type = state.get("response_type", "unknown")
    
    if response_type == "full_answer":
        state["status_message"] = "Success: Full answer generated"
    elif response_type == "partial_answer":
        state["status_message"] = "Success: Partial answer generated"
    elif response_type == "fallback":
        state["status_message"] = "Fallback: Suggested to contact advisor"
    else:
        state["status_message"] = "Completed"
    
    print("=" * 80)
    print(f"[FINAL] Response Type: {response_type}")
    print(f"[FINAL] Query Confidence: {confidence_summary['query_confidence']:.2f}")
    print(f"[FINAL] Rerank Confidence: {confidence_summary['rerank_confidence']:.2f}")
    print(f"[FINAL] Overall Confidence: {confidence_summary['overall_confidence']:.2f}")
    print("=" * 80)
    
    return state


# ============================================================================
# Graph Builder
# ============================================================================

builder = StateGraph(state_schema=QueryState)

# Add nodes
builder.add_node("prepare_input", prepare_input)
builder.add_node("agent1_understand_query", agent1_understand_query)
builder.add_node("ask_clarification", ask_clarification)
builder.add_node("retrieve_data", retrieve_data)
builder.add_node("rerank_data", rerank_data)
builder.add_node("agent2_assess_confidence", agent2_assess_confidence)
builder.add_node("ask_followup", ask_followup)
builder.add_node("agent3_generate_response", agent3_generate_response)
builder.add_node("format_final_answer", format_final_answer)

# Set entry point
builder.add_edge(START, "prepare_input")

# Add edges
builder.add_edge("prepare_input", "agent1_understand_query")

# Conditional edge after Agent 1
builder.add_conditional_edges(
    "agent1_understand_query",
    decide_after_agent1,
    {
        "ask_clarification": "ask_clarification",
        # "agent3_generate_response": "agent3_generate_response",
        "retrieve_data": "retrieve_data"
    }
)

# Clarification ends the flow (wait for user)
builder.add_edge("ask_clarification", END)

# Continue with retrieval and reranking
builder.add_edge("retrieve_data", "rerank_data")
builder.add_edge("rerank_data", "agent2_assess_confidence")

# Conditional edge after Agent 2
builder.add_conditional_edges(
    "agent2_assess_confidence",
    decide_after_agent2,
    {
        "ask_followup": "ask_followup",
        "generate_response": "agent3_generate_response"
    }
)

# Follow-up ends the flow (wait for user)
builder.add_edge("ask_followup", END)

# Continue with response generation
builder.add_edge("agent3_generate_response", "format_final_answer")
builder.add_edge("format_final_answer", END)

# Compile graph
graph = builder.compile()
graph.name = "RetrievalGraph"


# ============================================================================
# Export
# ============================================================================

__all__ = ["graph", "QueryState"]
