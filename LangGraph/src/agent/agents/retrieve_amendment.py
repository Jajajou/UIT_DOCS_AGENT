"""
AMENDMENT Retrieval Node (v0.3.0)

Handles the AMENDMENT path of the dual-mode retrieval router:
1. Reads query_document_ref from state (set by Agent 1 for AMENDMENT queries)
2. If no query_document_ref: falls back immediately to GENERAL path (no doc ref to trace)
3. Traverses PostgreSQL amendment chain to find the latest (leaf) document
4. Embeds query + fetches leaf document's chunks from Qdrant
5. If 0 results: sets amendment_fallback=True → router falls back to GENERAL path
6. Populates retrieved_chunks in qdrant_point_to_chunk format (entities/relationships empty)
"""

from __future__ import annotations

from typing import Any, Dict

from agent.states.query_state import QueryState
from agent.clients.amendment_chain_client import AmendmentChainClient, AmendmentChainError
from agent.config import settings

# Module-level client
_amendment_client = AmendmentChainClient()


def retrieve_amendment_data(state: QueryState) -> Dict[str, Any]:
    """
    AMENDMENT retrieval node.

    Resolves the amendment chain for the referenced document number and
    fetches the latest document's chunks from Qdrant. Skips temporal
    enrichment since metadata is already in the Qdrant payload.

    Falls back to GENERAL path (amendment_fallback=True) when:
    - No query_document_ref in state
    - Document not found in DB
    - Qdrant returns 0 chunks
    - Any client error
    """
    query = state.get("parsed_intention") or state.get("query", "")
    doc_number_ref = state.get("query_document_ref")
    chunk_top_k = state.get("chunk_top_k", settings.retrieval.default_chunk_top_k)

    if not query:
        return {"error": "No query for amendment retrieval", "amendment_fallback": True}

    if not doc_number_ref:
        print("[AMENDMENT] No query_document_ref — falling back to GENERAL path")
        return {
            "amendment_fallback": True,
            "logs": ["AMENDMENT node: no document ref extracted, falling back to GENERAL"],
        }

    print("=" * 80)
    print(f"[AMENDMENT] Query: {query}")
    print(f"[AMENDMENT] Document ref: {doc_number_ref}, top_k: {chunk_top_k}")
    print("=" * 80)

    try:
        chunks = _amendment_client.retrieve(
            query_text=query,
            doc_number_ref=doc_number_ref,
            top_k=int(chunk_top_k),
        )
    except AmendmentChainError as exc:
        error_msg = f"Amendment chain retrieval failed: {exc}"
        print(f"[AMENDMENT] Error: {error_msg}")
        return {
            "error": error_msg,
            "amendment_fallback": True,
            "logs": [f"AMENDMENT retrieval error: {error_msg} — falling back to GENERAL"],
        }

    if not chunks:
        print(f"[AMENDMENT] 0 results for '{doc_number_ref}' — triggering fallback to GENERAL")
        return {
            "amendment_fallback": True,
            "logs": [f"AMENDMENT: no chunks found for '{doc_number_ref}', fallback to GENERAL"],
        }

    print(f"[AMENDMENT] Retrieved {len(chunks)} chunks for '{doc_number_ref}' amendment chain")

    return {
        "retrieved_chunks": chunks,
        "retrieved_entities": [],
        "retrieved_relationships": [],
        "retrieval_metadata": {
            "mode": "amendment_qdrant",
            "doc_number_ref": doc_number_ref,
            "chunk_top_k": chunk_top_k,
            "total_chunks": len(chunks),
        },
        "amendment_fallback": False,
        "error": None,
        "logs": [f"AMENDMENT: retrieved {len(chunks)} chunks for '{doc_number_ref}' chain"],
    }


# ------------------------------------------------------------------
# Conditional edge function
# ------------------------------------------------------------------

def route_after_amendment(state: QueryState) -> str:
    """
    Conditional edge: route after retrieve_amendment_data.

    0 results / no ref (fallback=True) → retrieve_data (GENERAL path)
    Has results                         → rerank_data (skip enrich + filter)
    """
    if state.get("amendment_fallback", False):
        return "retrieve_data"
    return "rerank_data"


__all__ = [
    "retrieve_amendment_data",
    "route_after_amendment",
]
