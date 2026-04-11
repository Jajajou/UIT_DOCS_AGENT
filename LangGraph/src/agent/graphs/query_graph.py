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

from agent.states.query_state import (
    QueryState,
)
from agent.clients.lightrag_client import LightRAGAPIClient
from agent.clients.reranker import MultiSourceReranker
from agent.agents.agent1_query_understanding import (
    agent1_understand_query,
    decide_after_agent1,
    ask_clarification
)
from agent.agents.agent2_confidence_assessment import (
    agent2_assess_confidence,
    decide_after_agent2,
    ask_followup
)
from agent.agents.agent3_response_generation import agent3_generate_response
from agent.utils import content_to_text, get_last_human_message
from agent.config import settings


# ============================================================================
# API Clients
# ============================================================================

api_client = LightRAGAPIClient()
reranker = MultiSourceReranker()


# ============================================================================
# Graph Nodes
# ============================================================================

def prepare_input(state: QueryState) -> Dict[str, Any]:
    """
    Prepare input for the pipeline.
    
    Extract query from messages if not provided directly.
    """
    
    # Extract query
    messages = state.get("messages", [])
    if not messages:
        return {
            "error": "No input provided",
            "status_message": "Error: No input"
        }
    
    # Get last human message
    last_msg = get_last_human_message(messages)
    if not last_msg:
        return {
            "error": "No human message found",
            "status_message": "Error: No human message"
        }

    query = content_to_text(last_msg.content)
    
    print("=" * 80)
    print(f"[PREPARE] Query: {query}")
    print("=" * 80)
    
    return {
        "query": query,
        "error": None,
        "logs": [f"Prepared query: {query}"]
    }


def retrieve_data(state: QueryState) -> Dict[str, Any]:
    """
    Retrieve data from LightRAG using /query/data endpoint.
    
    This node:
    1. Uses parsed_intention from Agent 1
    2. Uses tuned parameters (mode, top_k, chunk_top_k) from Agent 1
    3. Calls LightRAG /query/data
    4. Returns raw entities, relationships, chunks
    """
    
    # Get query (use parsed_intention if available)
    query = state.get("parsed_intention") or state.get("query", "")
    
    if not query:
        return {"error": "No query for retrieval"}
    
    # Get retrieval parameters (tuned by Agent 1)
    mode = state.get("retrieval_mode", settings.retrieval.default_mode)
    top_k = state.get("top_k", settings.retrieval.default_top_k)
    chunk_top_k = state.get("chunk_top_k", settings.retrieval.default_chunk_top_k)
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
        
        print(f"[RETRIEVE] ✓ Retrieved {len(entities)} entities, {len(relationships)} relationships, {len(chunks)} chunks")
        
        return {
            "retrieved_entities": entities,
            "retrieved_relationships": relationships,
            "retrieved_chunks": chunks,
            "retrieval_metadata": {
                "mode": metadata["query_mode"],
                "top_k": top_k,
                "chunk_top_k": chunk_top_k,
                "total_entities": len(entities),
                "total_relationships": len(relationships),
                "total_chunks": len(chunks)
            },
            "error": None,
            "logs": [f"Retrieved {len(entities)} entities, {len(relationships)} relationships, {len(chunks)} chunks"]
        }
        
    except Exception as e:
        error_msg = f"Retrieval error: {str(e)}"
        print(f"[RETRIEVE] ✗ {error_msg}")
        
        return {
            "error": error_msg,
            "retrieved_entities": [],
            "retrieved_relationships": [],
            "retrieved_chunks": [],
            "logs": [f"Retrieval error: {error_msg}"]
        }


def enrich_with_temporal_metadata(state: QueryState) -> Dict[str, Any]:
    """
    Enrich retrieved items with temporal metadata from PostgreSQL.

    Joins temporal_metadata via file_source for all retrieved chunks,
    entities, and relationships in a single batch query, then merges
    the temporal fields into each item's metadata dict so that
    calculate_temporal_score() and assess_temporal_freshness() receive
    real data instead of empty dicts.
    """
    chunks = state.get("retrieved_chunks", [])
    entities = state.get("retrieved_entities", [])
    relationships = state.get("retrieved_relationships", [])

    all_file_paths = {
        item.get("file_path", "")
        for item in chunks + entities + relationships
        if item.get("file_path")
    }

    if not all_file_paths:
        print("[ENRICH] No file_path found in retrieved items, skipping enrichment")
        return {}

    temporal_map = api_client.get_temporal_metadata_by_file_sources(list(all_file_paths))

    if not temporal_map:
        print(f"[ENRICH] No temporal metadata found for {len(all_file_paths)} file paths")
        return {}

    def enrich(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for item in items:
            fp = item.get("file_path", "")
            if fp in temporal_map:
                enriched = {**item, "metadata": {**item.get("metadata", {}), **temporal_map[fp]}}
                result.append(enriched)
            else:
                result.append(item)
        return result

    enriched_chunks = enrich(chunks)
    enriched_entities = enrich(entities)
    enriched_relationships = enrich(relationships)

    matched = sum(1 for item in chunks + entities + relationships if item.get("file_path", "") in temporal_map)
    total = len(chunks) + len(entities) + len(relationships)
    print(f"[ENRICH] Enriched {matched}/{total} items with temporal metadata")

    return {
        "retrieved_chunks": enriched_chunks,
        "retrieved_entities": enriched_entities,
        "retrieved_relationships": enriched_relationships,
    }


def rerank_data(state: QueryState) -> Dict[str, Any]:
    """
    Rerank all retrieved data using the reranker.
    
    This node:
    1. Gets query and retrieved data
    2. Calls reranker to score and re-rank all items
    3. Returns reranked data with scores
    """
    
    # Get query
    query = state.get("parsed_intention") or state.get("query", "")
    
    if not query:
        return {"error": "No query for reranking"}
    
    # Get retrieved data
    entities = state.get("retrieved_entities", [])
    relationships = state.get("retrieved_relationships", [])
    chunks = state.get("retrieved_chunks", [])
    
    if not entities and not relationships and not chunks:
        print("[RERANK] No data to rerank, setting zero confidence")
        return {
            "reranked_entities": [],
            "reranked_relationships": [],
            "reranked_chunks": [],
            "entity_scores": [],
            "relationship_scores": [],
            "chunk_scores": [],
            "rerank_confidence": 0.0,
            "rerank_metadata": {"error": "No data to rerank"},
            "logs": ["No data to rerank"]
        }
    
    try:
        # Rerank all sources
        result = reranker.rerank_all(
            query=query,
            entities=entities,
            relationships=relationships,
            chunks=chunks,
            top_k_entities=None,  # Keep all
            top_k_relationships=None,
            top_k_chunks=None,
            use_temporal_boost=settings.use_temporal_scoring,
            query_cohort_year=state.get("query_cohort_year")
        )
        
        return {
            "reranked_entities": result["reranked_entities"],
            "reranked_relationships": result["reranked_relationships"],
            "reranked_chunks": result["reranked_chunks"],
            "entity_scores": result["entity_scores"],
            "relationship_scores": result["relationship_scores"],
            "chunk_scores": result["chunk_scores"],
            "rerank_confidence": result["overall_confidence"],
            "rerank_metadata": result["metadata"],
            "error": None,
            "logs": [f"Reranked data with confidence: {result['overall_confidence']:.2f}"]
        }
        
    except Exception as e:
        error_msg = f"Reranking error: {str(e)}"
        print(f"[RERANK] ✗ {error_msg}")
        
        return {
            "error": error_msg,
            "reranked_entities": [],
            "reranked_relationships": [],
            "reranked_chunks": [],
            "entity_scores": [],
            "relationship_scores": [],
            "chunk_scores": [],
            "rerank_confidence": 0.0,
            "rerank_metadata": {"error": error_msg},
            "logs": [f"Reranking error: {error_msg}"]
        }


def format_final_answer(state: QueryState) -> Dict[str, Any]:
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
    
    # Final answer is already set by agent3_generate_response
    # Just add status message
    response_type = state.get("response_type", "unknown")
    status_message = "Completed"
    
    if response_type == "full_answer":
        status_message = "Success: Full answer generated"
    elif response_type == "partial_answer":
        status_message = "Success: Partial answer generated"
    elif response_type == "fallback":
        status_message = "Fallback: Suggested to contact advisor"
    
    print("=" * 80)
    print(f"[FINAL] Response Type: {response_type}")
    print(f"[FINAL] Query Confidence: {confidence_summary['query_confidence']:.2f}")
    print(f"[FINAL] Rerank Confidence: {confidence_summary['rerank_confidence']:.2f}")
    print(f"[FINAL] Overall Confidence: {confidence_summary['overall_confidence']:.2f}")
    print("=" * 80)
    
    return {
        "confidence_summary": confidence_summary,
        "status_message": status_message,
        "logs": [f"Final answer formatted ({response_type})"]
    }


# ============================================================================
# Graph Builder
# ============================================================================

builder = StateGraph(state_schema=QueryState)

# Add nodes
builder.add_node("prepare_input", prepare_input)
builder.add_node("agent1_understand_query", agent1_understand_query)
builder.add_node("ask_clarification", ask_clarification)
builder.add_node("retrieve_data", retrieve_data)
builder.add_node("enrich_with_temporal_metadata", enrich_with_temporal_metadata)
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
builder.add_edge("retrieve_data", "enrich_with_temporal_metadata")
builder.add_edge("enrich_with_temporal_metadata", "rerank_data")
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