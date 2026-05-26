"""
Amendment Chain Client: AMENDMENT-path retrieval for v0.3.0 dual-mode RAG.

Responsibilities:
1. Given a document number reference (e.g. "108/QD-DHCNTT"), traverse the
   PostgreSQL amendment chain via recursive CTE to find the latest (leaf) document.
2. Fetch that document's chunks from Qdrant by full_doc_id filter, ranked by
   vector similarity to the query.
3. Return results in qdrant_point_to_chunk format (compatible with reranker).

Amendment chain direction:
  Doc A (original) ← Doc B (amends A, B.amends_documents = ["A"])
                    ← Doc C (amends B, C.amends_documents = ["B"])
  Leaf = C (most recent, not amended by anything)
"""

from __future__ import annotations

import logging
import os

import psycopg2
import requests
from dotenv import load_dotenv
from typing import Any

from agent.config import PROJECT_ROOT, settings
from agent.clients.qdrant_cohort_client import QdrantCohortClient

logger = logging.getLogger(__name__)

QDRANT_BASE_URL = "http://localhost:6336"
QDRANT_COLLECTION = "lightrag_vdb_chunks_aiteamvn_vietnamese_embedding_v2_1024d"
DEFAULT_TOP_K = 30
DEFAULT_WORKSPACE = "uit_docs_agent"
MAX_CHAIN_DEPTH = 10


class AmendmentChainError(RuntimeError):
    """Raised when amendment chain lookup or chunk fetch fails."""


class AmendmentChainClient:
    """
    Client for AMENDMENT-path retrieval.

    Walks the amendment chain in PostgreSQL to find the latest (leaf) document,
    then fetches its chunks from Qdrant via full_doc_id filter + vector search.

    Args:
        qdrant_base_url: Qdrant REST base URL (default: localhost:6336).
        collection: Qdrant collection name.
        workspace: LightRAG workspace name.
        timeout: HTTP timeout for Qdrant requests.
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
        load_dotenv(f"{PROJECT_ROOT}/.env.lightrag")
        # Reuse cohort client for embed + _point_to_chunk
        self._cohort_client = QdrantCohortClient(
            qdrant_base_url=qdrant_base_url,
            collection=collection,
            workspace=workspace,
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # PostgreSQL: amendment chain traversal
    # ------------------------------------------------------------------

    def _get_pg_connection(self):
        return psycopg2.connect(
            host="localhost",
            port=5433,
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            database=os.getenv("POSTGRES_DATABASE", "lightrag"),
        )

    def get_latest_in_chain(self, doc_number_ref: str) -> list[dict[str, Any]]:
        """
        Traverse the amendment chain and return the leaf document(s).

        Starts from `doc_number_ref`, recursively finds any document whose
        amends_documents JSONB array contains the previous doc's number,
        up to MAX_CHAIN_DEPTH hops. Returns the leaf doc(s) — those not
        amended by any other document in the chain.

        Returns:
            List of dicts with keys: doc_id, doc_number, depth.
            Empty list if `doc_number_ref` not found in DB.

        Raises:
            AmendmentChainError on database errors.
        """
        # Normalise: strip whitespace, preserve original case
        doc_number_ref = doc_number_ref.strip()

        sql = """
            WITH RECURSIVE amendment_chain AS (
                -- Base: starting document matching the reference
                SELECT
                    id AS doc_id,
                    metadata->>'document_number' AS doc_number,
                    1 AS depth
                FROM lightrag_doc_status
                WHERE metadata->>'document_number' = %(ref)s
                  AND workspace = %(workspace)s

                UNION ALL

                -- Recursive: any document whose amends_documents contains
                -- a doc_number already in the chain
                SELECT
                    d.id,
                    d.metadata->>'document_number',
                    ac.depth + 1
                FROM lightrag_doc_status d
                JOIN amendment_chain ac
                  ON d.metadata->'amends_documents' ? ac.doc_number
                WHERE d.workspace = %(workspace)s
                  AND ac.depth < %(max_depth)s
            )
            SELECT DISTINCT doc_id, doc_number, depth
            FROM amendment_chain
            ORDER BY depth DESC
        """

        conn = None
        try:
            conn = self._get_pg_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {
                        "ref": doc_number_ref,
                        "workspace": self.workspace,
                        "max_depth": MAX_CHAIN_DEPTH,
                    })
                    rows = cur.fetchall()
        except psycopg2.Error as exc:
            raise AmendmentChainError(
                f"Amendment chain query failed for '{doc_number_ref}': {exc}"
            ) from exc
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        if not rows:
            logger.warning("[Amendment] No chain found for '%s'", doc_number_ref)
            return []

        chain = [
            {"doc_id": r[0], "doc_number": r[1], "depth": r[2]}
            for r in rows
        ]

        # Leaf = docs at maximum depth (not superseded by anything further)
        max_depth = chain[0]["depth"]
        leaves = [c for c in chain if c["depth"] == max_depth]

        logger.debug(
            "[Amendment] Chain for '%s': %d docs, leaf(ves): %s",
            doc_number_ref,
            len(chain),
            [l["doc_number"] for l in leaves],
        )
        return leaves

    # ------------------------------------------------------------------
    # Qdrant: fetch chunks for a doc_id
    # ------------------------------------------------------------------

    def fetch_chunks_by_doc_id(
        self,
        doc_id: str,
        query_embedding: list[float],
        top_k: int = DEFAULT_TOP_K,
    ) -> list[dict[str, Any]]:
        """
        Fetch chunks from Qdrant for a specific doc_id, ranked by vector similarity.

        Uses `full_doc_id` payload filter (the canonical link field between
        Qdrant points and PostgreSQL documents), combined with vector search
        so results are ranked by relevance to the query.
        """
        url = f"{self.qdrant_base_url}/collections/{self.collection}/points/search"
        body = {
            "vector": query_embedding,
            "limit": top_k,
            "with_payload": True,
            "filter": {
                "must": [
                    {"key": "full_doc_id", "match": {"value": doc_id}}
                ]
            },
        }
        try:
            resp = self._session.post(
                url,
                json=body,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            points = resp.json().get("result", [])
        except requests.RequestException as exc:
            raise AmendmentChainError(
                f"Qdrant fetch failed for doc_id '{doc_id}': {exc}"
            ) from exc

        return [QdrantCohortClient._point_to_chunk(p) for p in points]

    # ------------------------------------------------------------------
    # Public convenience method
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query_text: str,
        doc_number_ref: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[dict[str, Any]]:
        """
        End-to-end: resolve amendment chain → embed query → fetch leaf chunks.

        Args:
            query_text: The user query (or parsed intention from Agent 1).
            doc_number_ref: Document number extracted by Agent 1 (e.g. "108/QD-DHCNTT").
            top_k: Max chunks to return per leaf document.

        Returns:
            List of qdrant_point_to_chunk dicts sorted by score desc.
            Empty list if chain not found or no chunks indexed for leaf.
        """
        leaves = self.get_latest_in_chain(doc_number_ref)
        if not leaves:
            return []

        embedding = self._cohort_client.embed_query(query_text)

        chunks: list[dict[str, Any]] = []
        for leaf in leaves:
            doc_chunks = self.fetch_chunks_by_doc_id(leaf["doc_id"], embedding, top_k)
            logger.debug(
                "[Amendment] '%s' (depth=%d): %d chunks",
                leaf["doc_number"], leaf["depth"], len(doc_chunks),
            )
            chunks.extend(doc_chunks)

        # Re-sort by score desc if multiple leaves contributed chunks
        chunks.sort(key=lambda c: c["score"], reverse=True)
        return chunks[:top_k]
