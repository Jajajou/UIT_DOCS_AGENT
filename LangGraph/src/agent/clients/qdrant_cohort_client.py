"""
Qdrant Cohort Client: COHORT-path retrieval for v0.3.0 dual-mode RAG.

Responsibilities:
1. Embed a query text using the same OpenAI-compatible embedding endpoint
   that LightRAG uses — ensuring vector-space parity with indexed chunks.
2. Run a filtered vector search on Qdrant `lightrag_vdb_chunks`:
   - cohort_years contains `cohort_year` (int) OR "*" (universal)
   - is_archived is NOT true
3. Return results in `qdrant_point_to_chunk` format (compatible with reranker).
"""

from __future__ import annotations

import logging
import requests
from typing import Any

from agent.config import settings

logger = logging.getLogger(__name__)

QDRANT_BASE_URL = "http://localhost:6336"
QDRANT_COLLECTION = "lightrag_vdb_chunks"
DEFAULT_TOP_K = 40
DEFAULT_WORKSPACE = "uit_docs_agent"


class QdrantCohortError(RuntimeError):
    """Raised when Qdrant cohort search fails."""


class QdrantCohortClient:
    """
    Client for COHORT-path Qdrant retrieval.

    Embeds the query via the OpenAI-compatible embedding endpoint (same model
    as LightRAG), then performs a filtered vector search.

    Args:
        qdrant_base_url: Qdrant REST base URL (default: localhost:6336).
        collection: Qdrant collection name.
        workspace: LightRAG workspace name (used for result context).
        timeout: HTTP timeout in seconds.
    """

    def __init__(
        self,
        qdrant_base_url: str = QDRANT_BASE_URL,
        collection: str = QDRANT_COLLECTION,
        workspace: str = DEFAULT_WORKSPACE,
        timeout: int = 30,
    ) -> None:
        self.qdrant_base_url = qdrant_base_url.rstrip("/")
        self.collection = collection
        self.workspace = workspace
        self.timeout = timeout
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def embed_query(self, text: str) -> list[float]:
        """
        Embed `text` using the same OpenAI-compatible endpoint as LightRAG.

        Reads endpoint + model from settings (EMBEDDING_BASE_URL, EMBEDDING_MODEL,
        EMBEDDING_API_KEY) so that the resulting vector is in the same space as
        the indexed Qdrant points.
        """
        base_url = (settings.embedding_base_url or "").rstrip("/")
        if not base_url:
            raise QdrantCohortError("EMBEDDING_BASE_URL not configured in settings")

        url = f"{base_url}/embeddings"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.embedding_api_key or 'EMPTY'}",
        }
        body = {
            "model": settings.embedding_model,
            "input": text,
        }
        try:
            resp = self._session.post(url, headers=headers, json=body, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
        except requests.RequestException as exc:
            raise QdrantCohortError(f"embed_query failed: {exc}") from exc
        except (KeyError, IndexError) as exc:
            raise QdrantCohortError(f"embed_query: unexpected response shape: {exc}") from exc

    # ------------------------------------------------------------------
    # Qdrant search
    # ------------------------------------------------------------------

    def search_by_cohort(
        self,
        query_embedding: list[float],
        cohort_year: int,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[dict[str, Any]]:
        """
        Vector search on lightrag_vdb_chunks filtered by cohort_year.

        Filter logic:
        - cohort_years contains `cohort_year` (int) OR "*" (universal marker)
        - is_archived is NOT true (missing field is treated as not-archived)

        Returns a list of `qdrant_point_to_chunk` dicts, ordered by score desc.
        """
        url = f"{self.qdrant_base_url}/collections/{self.collection}/points/search"
        body = {
            "vector": query_embedding,
            "limit": top_k,
            "with_payload": True,
            "filter": {
                "must": [
                    {
                        "should": [
                            {"key": "cohort_years", "match": {"value": cohort_year}},
                            {"key": "cohort_years", "match": {"value": "*"}},
                            {"is_empty": {"key": "cohort_years"}},
                        ]
                    }
                ],
                "must_not": [
                    {"key": "is_archived", "match": {"value": True}}
                ],
            },
        }
        try:
            resp = self._session.post(
                url,
                json=body,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            points = data.get("result", [])
        except requests.RequestException as exc:
            raise QdrantCohortError(f"search_by_cohort failed: {exc}") from exc

        return [self._point_to_chunk(p) for p in points]

    # ------------------------------------------------------------------
    # Public convenience method
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query_text: str,
        cohort_year: int,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[dict[str, Any]]:
        """
        End-to-end: embed query then search Qdrant by cohort.

        Args:
            query_text: The user query (or parsed intention from Agent 1).
            cohort_year: Integer cohort year extracted by Agent 1 (e.g. 2022).
            top_k: Max number of chunks to return.

        Returns:
            List of `qdrant_point_to_chunk` dicts, sorted by score desc.
            Empty list if no matching chunks.
        """
        embedding = self.embed_query(query_text)
        return self.search_by_cohort(embedding, cohort_year, top_k)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _point_to_chunk(point: dict[str, Any]) -> dict[str, Any]:
        """
        Convert a Qdrant ScoredPoint dict to the standard chunk shape used by
        the reranker and Agent 3.

        Output schema (qdrant_point_to_chunk):
        {
            "content": str,
            "file_path": str,
            "metadata": {
                "cohort_years": list,
                "cohort_scope": str | None,
                "valid_from": str | None,
                "valid_until": str | None,
                "is_archived": bool,
                "document_number": str | None,
                "amends_documents": list,
            },
            "score": float,
        }
        """
        payload = point.get("payload") or {}
        score = float(point.get("score", 0.0))

        content = payload.get("content") or payload.get("text") or ""
        file_path = payload.get("file_path") or payload.get("file_source") or ""

        metadata = {
            "cohort_years": payload.get("cohort_years") or [],
            "cohort_scope": payload.get("cohort_scope"),
            "valid_from": payload.get("valid_from"),
            "valid_until": payload.get("valid_until"),
            "is_archived": bool(payload.get("is_archived", False)),
            "document_number": payload.get("document_number"),
            "amends_documents": payload.get("amends_documents") or [],
        }

        return {
            "content": content,
            "file_path": file_path,
            "metadata": metadata,
            "score": score,
        }
