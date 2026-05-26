"""
Query Graph: Temporal-Aware RAG Pipeline

This graph implements a temporal-aware RAG pipeline with:
- Agent 1: Query Understanding with automatic parameter tuning
- Reranker: Temporal scoring (semantic + temporal + cohort + amendment)
- Agent 3: Response Generation — always produces a direct answer
"""

from __future__ import annotations

import json
import os
import re
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
    route_after_agent1,
)
from agent.agents.agent3_response_generation import agent3_generate_response
from agent.agents.agent4_validation import agent4_validate_response, route_after_validation
from agent.agents.retrieve_cohort import (
    retrieve_cohort_data,
    route_after_cohort,
)
from agent.agents.retrieve_amendment import (
    retrieve_amendment_data,
    route_after_amendment,
)
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
    # FORCE_RETRIEVAL_MODE env var overrides agent1 suggestion (for ablation testing)
    forced_mode = os.getenv("FORCE_RETRIEVAL_MODE")
    mode = forced_mode or state.get("retrieval_mode", settings.retrieval.default_mode)
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
        # 1. Direct Lookup by Document Number (Bypass semantic failure)
        direct_chunks = []
        doc_num_matches = re.findall(r'\b(\d{1,4}(?:/\d{4})?/(?:QĐ|TT|TB|NQ|HD|KL|VBHN)(?:-[A-ZĐ]+)+)\b', query, re.IGNORECASE)
        # Also catch simple formats like 141/QĐ-ĐHCNTT without specific prefixes
        simple_matches = re.findall(r'\b(\d{1,4}/[A-ZĐ]+-[A-ZĐ]+)\b', query, re.IGNORECASE)
        all_matches = list(set(doc_num_matches + simple_matches))
        
        if all_matches:
            print(f"[RETRIEVE] Direct lookup for doc numbers: {all_matches}")
            direct_chunks = api_client.get_chunks_by_doc_numbers(all_matches)
            if direct_chunks:
                print(f"[RETRIEVE] Found {len(direct_chunks)} direct chunks via doc number lookup.")

        # Call LightRAG /query/data endpoint (retry up to 3x on 5xx)
        import time as _time
        result = None
        for _attempt in range(3):
            try:
                result = api_client.query_data(
                    query_text=query,
                    mode=mode,
                    top_k=top_k,
                    chunk_top_k=chunk_top_k,
                    max_entity_tokens=max_entity_tokens,
                    max_relation_tokens=max_relation_tokens,
                    max_total_tokens=max_total_tokens
                )
                break
            except Exception as _e:
                if _attempt < 2:
                    print(f"[RETRIEVE] Attempt {_attempt+1} failed: {_e}, retrying in 5s...")
                    _time.sleep(5)
                else:
                    raise
        
        # Parse result
        entities = result["data"]["entities"]
        relationships = result["data"]["relationships"]
        chunks = result["data"]["chunks"]
        
        # Inject direct lookup chunks
        if direct_chunks:
            # Avoid duplicates based on file_path or doc_id
            existing_paths = {c.get("file_path") for c in chunks}
            for dc in direct_chunks:
                if dc.get("file_path") not in existing_paths:
                    chunks.append(dc)

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
    Also fetches sibling documents (documents that amend or are amended by
    the retrieved documents) to ensure the amendment chain is complete
    for the reranker to evaluate.
    """
    chunks = state.get("retrieved_chunks", [])
    entities = state.get("retrieved_entities", [])
    relationships = state.get("retrieved_relationships", [])

    all_file_paths = set()
    for item in chunks + entities + relationships:
        fp = item.get("file_path") or item.get("file_source")
        if fp:
            all_file_paths.add(fp)

    if not all_file_paths:
        print("[ENRICH] No file_path or file_source found in retrieved items, skipping enrichment")
        return {}

    temporal_map = api_client.get_temporal_metadata_by_file_sources(list(all_file_paths))

    if not temporal_map:
        print(f"[ENRICH] No temporal metadata found for {len(all_file_paths)} file paths")
        return {}

    # Sibling enrichment: find docs that amend or are amended by the retrieved docs
    sibling_file_paths = set()
    for fp, meta in temporal_map.items():
        # Get documents this doc amends
        amends = meta.get("amends_documents", [])
        if amends:
            # We need to fetch metadata for these document numbers
            # This is a bit tricky since get_temporal_metadata_by_file_sources takes file_paths, not doc numbers.
            # We'll need a new client method or just add a placeholder.
            pass
        # Get documents that amend this doc
        amended_by = meta.get("amended_by", [])
        if amended_by:
            pass

    def enrich(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for item in items:
            fp = item.get("file_path") or item.get("file_source")
            if fp and fp in temporal_map:
                enriched = {**item, "metadata": {**item.get("metadata", {}), **temporal_map[fp]}}
                result.append(enriched)
            else:
                result.append(item)
        return result

    enriched_chunks = enrich(chunks)
    
    # Sibling Enrichment Implementation
    # If doc X is retrieved and it's amended by doc Y (which wasn't retrieved),
    # we MUST pull doc Y into the candidate set so the reranker can promote Y over X.
    # We do this by checking the 'amended_by' field, which contains doc_ids of amending documents.
    try:
        sibling_doc_ids = set()
        for fp, meta in temporal_map.items():
            amended_by = meta.get("amended_by")
            if isinstance(amended_by, list):
                for doc_id in amended_by:
                    if not str(doc_id).startswith("error-"):
                        sibling_doc_ids.add(str(doc_id))
        
        # Check which siblings are missing from chunks
        existing_doc_ids = {c.get("doc_id") or c.get("id") or c.get("metadata", {}).get("doc_id") for c in enriched_chunks}
        missing_siblings = sibling_doc_ids - existing_doc_ids
        
        if missing_siblings:
            print(f"[ENRICH] Found {len(missing_siblings)} missing sibling docs. Fetching from DB...")
            sibling_metadata = api_client.get_temporal_metadata_by_doc_ids(list(missing_siblings))
            real_chunks = api_client.get_chunks_by_doc_ids(list(missing_siblings))

            # Merge metadata into real chunks and truncate content to avoid vLLM 400 Bad Request
            for chunk in real_chunks:
                s_doc_id = chunk.get("doc_id")
                if s_doc_id in sibling_metadata:
                    chunk["metadata"] = {**chunk.get("metadata", {}), **sibling_metadata[s_doc_id]}
                # Truncate content to safe limit for reranker (e.g., 2000 chars)
                if chunk.get("content") and len(chunk["content"]) > 2000:
                    chunk["content"] = chunk["content"][:2000] + " ... [TRUNCATED]"
                enriched_chunks.append(chunk)

            print(f"[ENRICH] Added {len(real_chunks)} full sibling chunks to candidate set.")
    except Exception as e:
        print(f"[ENRICH] Error during sibling enrichment: {e}")

    enriched_entities = enrich(entities)
    enriched_relationships = enrich(relationships)

    matched = sum(1 for item in chunks + entities + relationships if (item.get("file_path") or item.get("file_source")) in temporal_map)
    total = len(chunks) + len(entities) + len(relationships)
    print(f"[ENRICH] Enriched {matched}/{total} items with temporal metadata")

    return {
        "retrieved_chunks": enriched_chunks,
        "retrieved_entities": enriched_entities,
        "retrieved_relationships": enriched_relationships,
    }


def filter_by_metadata(state: QueryState) -> Dict[str, Any]:
    """
    Hard-filter retrieved items based on cohort constraints and article-level relevance.
    
    1. Cohort Filtering: Drops documents explicitly NOT for the detected cohort year.
    2. Article Prioritization: If query mentions a specific article (e.g. Điều 5),
       prioritizes items from documents that explicitly amend that article.
    """
    query = state.get("query", "")
    query_cohort_year = state.get("query_cohort_year")
    query_edu_system = state.get("education_system", "chinh_quy")

    chunks = state.get("retrieved_chunks", [])
    entities = state.get("retrieved_entities", [])
    relationships = state.get("retrieved_relationships", [])

    # Extract specific articles from query for prioritization
    # Using local regex for efficiency
    query_articles = []
    article_matches = re.findall(r"điều\s+(\d+\.?\d*)", query, re.IGNORECASE)
    if article_matches:
        query_articles = [f"Điều {m}" for m in article_matches]

    def is_match(item: Dict[str, Any]) -> bool:
        meta = item.get("metadata", {})
        
        # --- 1. Cohort Filtering ---
        if query_cohort_year is not None:
            try:
                target_year = int(query_cohort_year)
                cohorts = meta.get("cohort_years")
                
                if cohorts and "*" not in cohorts and "*" not in [str(c) for c in cohorts]:
                    item_years = []
                    for c in cohorts:
                        try:
                            item_years.append(int(float(str(c))))
                        except (ValueError, TypeError):
                            pass
                    if item_years and target_year not in item_years:
                        return False # Explicit cohort mismatch
            except (ValueError, TypeError):
                pass

        # --- 2. Education System Filtering ---
        item_edu_system = meta.get("education_system")
        if item_edu_system and item_edu_system != "universal" and item_edu_system != query_edu_system:
            return False

        return True

    filtered_chunks = [c for c in chunks if is_match(c)]
    filtered_entities = [e for e in entities if is_match(e)]
    filtered_relationships = [r for r in relationships if is_match(r)]

    # --- 2. Article Prioritization (Boost items matching mentioned articles) ---
    if query_articles:
        print(f"[FILTER] Query mentions articles: {query_articles}. Prioritizing amended versions.")
        for item in filtered_chunks:
            meta = item.get("metadata", {})
            amended = meta.get("amended_articles", [])
            # If this chunk's doc amends one of the query's articles, give it a metadata boost
            # that the reranker can see (or just log it for now)
            if any(art in amended for art in query_articles):
                item["metadata"]["article_priority_boost"] = True
                print(f"[FILTER] ✓ Boosted chunk from {meta.get('document_number')} (amends {query_articles})")

    dropped = (len(chunks) + len(entities) + len(relationships)) - \
              (len(filtered_chunks) + len(filtered_entities) + len(filtered_relationships))
    
    if query_cohort_year:
        print(f"[FILTER] Dropped {dropped} items that don't match cohort {query_cohort_year}")
    if query_edu_system != "chinh_quy":
        print(f"[FILTER] Education system filter active: {query_edu_system}")
    
    return {
        "retrieved_chunks": filtered_chunks,
        "retrieved_entities": filtered_entities,
        "retrieved_relationships": filtered_relationships,
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
        query_is_historical = state.get("query_is_historical", False)
        result = reranker.rerank_all(
            query=query,
            entities=entities,
            relationships=relationships,
            chunks=chunks,
            top_k_entities=None,  # Keep all
            top_k_relationships=None,
            top_k_chunks=None,
            use_temporal_boost=settings.use_temporal_scoring,
            query_cohort_year=state.get("query_cohort_year"),
            query_authority_scope=state.get("query_authority_scope"),
            query_is_historical=query_is_historical,
            query_type=state.get("query_type", "GENERAL")
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
    print("=" * 80)
    
    return {
        "confidence_summary": confidence_summary,
        "status_message": status_message,
        "logs": [f"Final answer formatted ({response_type})"]
    }


def request_context(state: QueryState) -> Dict[str, Any]:
    """
    HITL node: pause and ask user for missing student context (cohort / education system).
    Resumes when user provides: {"cohort_year": int, "education_system": str}
    """
    from langgraph.types import interrupt

    cohort_year = state.get("query_cohort_year")
    edu_system = state.get("education_system")

    missing = []
    if cohort_year is None:
        missing.append("khóa học (ví dụ: 2022, K22)")
    if edu_system is None:
        missing.append("hệ đào tạo (chinh_quy / lien_thong / tu_xa)")

    response = interrupt({
        "action": "request_context",
        "missing_fields": missing,
        "message": f"Câu hỏi liên quan đến quy chế/quy định sinh viên. Vui lòng cung cấp: {', '.join(missing)}.",
        "current_query": state.get("query", ""),
    })

    updates: Dict[str, Any] = {}
    if isinstance(response, dict):
        if "cohort_year" in response:
            updates["query_cohort_year"] = response["cohort_year"]
        if "education_system" in response:
            updates["education_system"] = response["education_system"]

    print(f"[HITL] Context received: {updates}")
    return updates


# ============================================================================
# Graph Builder
# ============================================================================

builder = StateGraph(state_schema=QueryState)

# Add nodes
builder.add_node("prepare_input", prepare_input)
builder.add_node("agent1_understand_query", agent1_understand_query)
builder.add_node("retrieve_cohort_data", retrieve_cohort_data)
builder.add_node("retrieve_amendment_data", retrieve_amendment_data)
builder.add_node("retrieve_data", retrieve_data)
builder.add_node("enrich_with_temporal_metadata", enrich_with_temporal_metadata)
builder.add_node("filter_by_metadata", filter_by_metadata)
builder.add_node("rerank_data", rerank_data)
builder.add_node("agent3_generate_response", agent3_generate_response)
builder.add_node("agent4_validate_response", agent4_validate_response)
builder.add_node("format_final_answer", format_final_answer)
builder.add_node("request_context", request_context)

# Set entry point
builder.add_edge(START, "prepare_input")
builder.add_edge("prepare_input", "agent1_understand_query")

# Consolidated routing after Agent 1:
#   request_context → stop and ask user (HITL)
#   retrieve_cohort_data →Filtered Qdrant search
#   retrieve_amendment_data → PostgreSQL amendment chain
#   retrieve_data → Standard LightRAG retrieval
builder.add_conditional_edges(
    "agent1_understand_query",
    route_after_agent1,
    {
        "request_context": "request_context",
        "retrieve_cohort_data": "retrieve_cohort_data",
        "retrieve_amendment_data": "retrieve_amendment_data",
        "retrieve_data": "retrieve_data",
    },
)

# After user provides context, re-route to the correct retrieval node
builder.add_conditional_edges(
    "request_context",
    route_after_agent1,
    {
        "request_context": "request_context",
        "retrieve_cohort_data": "retrieve_cohort_data",
        "retrieve_amendment_data": "retrieve_amendment_data",
        "retrieve_data": "retrieve_data",
    },
)

# COHORT path: results → rerank, 0 results → fallback to GENERAL
builder.add_conditional_edges(
    "retrieve_cohort_data",
    route_after_cohort,
    {
        "rerank_data": "rerank_data",
        "retrieve_data": "retrieve_data",
    },
)

# AMENDMENT path: results → rerank, no ref / 0 results → fallback to GENERAL
builder.add_conditional_edges(
    "retrieve_amendment_data",
    route_after_amendment,
    {
        "rerank_data": "rerank_data",
        "retrieve_data": "retrieve_data",
    },
)

# GENERAL path: retrieve → enrich → filter → rerank
builder.add_edge("retrieve_data", "enrich_with_temporal_metadata")
builder.add_edge("enrich_with_temporal_metadata", "filter_by_metadata")
builder.add_edge("filter_by_metadata", "rerank_data")

# Common tail: rerank → answer → validate → format → end
builder.add_edge("rerank_data", "agent3_generate_response")
builder.add_edge("agent3_generate_response", "agent4_validate_response")

# Validation loop: either retry Agent 3 or proceed to formatting
builder.add_conditional_edges(
    "agent4_validate_response",
    route_after_validation,
    {
        "retry_agent3": "agent3_generate_response",
        "format_final_answer": "format_final_answer"
    }
)

builder.add_edge("format_final_answer", END)

# Compile graph
graph = builder.compile()
graph.name = "RetrievalGraph"


# ============================================================================
# Export
# ============================================================================

__all__ = ["graph", "QueryState"]