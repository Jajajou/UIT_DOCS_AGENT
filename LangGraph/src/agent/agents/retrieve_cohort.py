"""
COHORT Retrieval Node (v0.3.0)

Handles the COHORT path of the dual-mode retrieval router:
1. Reads cohort_year from state (set by Agent 1 for COHORT queries)
2. Embeds the query using the same model as LightRAG
3. Runs filtered Qdrant vector search: cohort_years HAS [year OR "*"] AND NOT archived
4. If 0 results: sets cohort_fallback=True so the router falls back to GENERAL path
5. If results: populates retrieved_chunks in qdrant_point_to_chunk format,
   sets retrieved_entities=[] and retrieved_relationships=[] (Qdrant path has no KG data)
"""

from __future__ import annotations

import os
from typing import Any, Dict

from agent.states.query_state import QueryState
from agent.clients.qdrant_cohort_client import QdrantCohortClient, QdrantCohortError
from agent.config import settings

# Module-level client (one per worker, no shared state)
_cohort_client = QdrantCohortClient()


def retrieve_cohort_data(state: QueryState) -> Dict[str, Any]:
    """
    COHORT retrieval node.

    Queries Qdrant with cohort-year metadata filter instead of
    LightRAG's full-graph retrieval. Skips temporal enrichment since
    metadata is already embedded in the Qdrant payload.

    Sets `cohort_fallback=True` if Qdrant returns 0 results, which causes
    the router to fall back to the GENERAL retrieve_data path.
    """
    query = state.get("parsed_intention") or state.get("query", "")
    cohort_year = state.get("query_cohort_year")
    chunk_top_k = state.get("chunk_top_k", settings.retrieval.default_chunk_top_k)

    if not query:
        return {"error": "No query for cohort retrieval", "cohort_fallback": True, "query_cohort_year": None}

    if cohort_year is None:
        # Should not happen if router is correct, but be defensive
        return {
            "cohort_fallback": True,
            "query_cohort_year": None,
            "logs": ["COHORT node: no cohort_year in state, falling back to GENERAL"],
        }

    print("=" * 80)
    print(f"[COHORT] Query: {query}")
    print(f"[COHORT] Cohort year: {cohort_year}, top_k: {chunk_top_k}")
    print("=" * 80)

    try:
        chunks = _cohort_client.retrieve(
            query_text=query,
            cohort_year=int(cohort_year),
            top_k=int(chunk_top_k),
        )
    except QdrantCohortError as exc:
        error_msg = f"Qdrant cohort search failed: {exc}"
        print(f"[COHORT] Error: {error_msg}")
        return {
            "error": error_msg,
            "cohort_fallback": True,
            "query_cohort_year": None,
            "logs": [f"COHORT retrieval error: {error_msg} — falling back to GENERAL"],
        }

    if not chunks:
        print(f"[COHORT] 0 results for cohort {cohort_year} — triggering fallback to GENERAL")
        return {
            "cohort_fallback": True,
            "query_cohort_year": None,
            "logs": [f"COHORT: 0 results for K{cohort_year}, fallback to GENERAL"],
        }

    print(f"[COHORT] Retrieved {len(chunks)} chunks for cohort {cohort_year}")

    return {
        "retrieved_chunks": chunks,
        "retrieved_entities": [],
        "retrieved_relationships": [],
        "retrieval_metadata": {
            "mode": "cohort_qdrant",
            "cohort_year": cohort_year,
            "chunk_top_k": chunk_top_k,
            "total_chunks": len(chunks),
        },
        "cohort_fallback": False,
        "error": None,
        "logs": [f"COHORT: retrieved {len(chunks)} chunks for K{cohort_year} via Qdrant"],
    }


# ------------------------------------------------------------------
# Conditional edge functions
# ------------------------------------------------------------------

def route_retrieval(state: QueryState) -> str:
    """
    Conditional edge: route after agent1_understand_query.

    When USE_METADATA_ROUTING=false (ablation bypass):
        All queries → retrieve_data (LightRAG, v0.2.0 behaviour)

    When USE_METADATA_ROUTING=true (default):
        COHORT     → retrieve_cohort_data
        AMENDMENT  → retrieve_amendment_data
        GENERAL    → retrieve_data (LightRAG)
    """
    if os.getenv("USE_METADATA_ROUTING", "true").lower() == "false":
        return "retrieve_data"
    query_type = state.get("query_type", "GENERAL")
    # Force COHORT path if cohort_year explicitly set (eval injection or Agent 1)
    if query_type == "COHORT" or state.get("query_cohort_year"):
        return "retrieve_cohort_data"
    if query_type == "AMENDMENT":
        return "retrieve_amendment_data"
    return "retrieve_data"


def route_after_cohort(state: QueryState) -> str:
    """
    Conditional edge: route after retrieve_cohort_data.

    0 results (fallback=True) → retrieve_data (GENERAL path)
    Has results               → rerank_data (skip enrich + filter)
    """
    if state.get("cohort_fallback", False):
        return "retrieve_data"
    return "rerank_data"


__all__ = [
    "retrieve_cohort_data",
    "route_retrieval",
    "route_after_cohort",
]
