"""Qdrant payload injector for temporal metadata annotation.

Injects temporal metadata fields from PostgreSQL temporal_metadata table
into existing LightRAG chunk points in Qdrant via set_payload REST API.

Key facts about the schema (confirmed by inspection 2026-04-14):
- Collection: lightrag_vdb_chunks (907 points)
- Link field: payload["full_doc_id"] == lightrag_doc_status.id == temporal_metadata.doc_id
- set_payload with filter = one REST call per doc, no scroll needed
- Port: 6336 (Docker maps 6336 -> 6333 inside container)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv("LangGraph/.env")

logger = logging.getLogger(__name__)

COLLECTION = "lightrag_vdb_chunks"


class QdrantPayloadInjectorError(RuntimeError):
    pass


class QdrantPayloadInjector:
    """Injects temporal metadata into Qdrant chunk points post-hoc.

    Uses the Qdrant REST API directly (no qdrant-client SDK needed).
    A single set_payload call with a full_doc_id filter handles all chunks
    for a document in one round-trip.

    Usage:
        injector = QdrantPayloadInjector()
        result = injector.inject_doc_metadata(
            doc_id="doc-abc123",
            metadata={
                "cohort_years": [2022, 2023],
                "cohort_scope": "explicit",
                "is_archived": False,
                "valid_from": "2022-09-01",
                "valid_until": None,
                "document_number": "108/QD-DHCNTT",
                "amends_documents": [],
            }
        )
    """

    def __init__(
        self,
        base_url: str | None = None,
        collection: str = COLLECTION,
        timeout: int = 30,
    ) -> None:
        # Default to localhost:6336 to match Docker port mapping (6336->6333).
        # Do NOT read QDRANT_URL from env — that var is set to host.docker.internal
        # for container-to-container comms and is unreachable from the host machine.
        self.base_url = (base_url or "http://localhost:6336").rstrip("/")
        self.collection = collection
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def inject_doc_metadata(
        self,
        doc_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Inject temporal metadata into all Qdrant chunks for a document.

        Calls set_payload with a full_doc_id filter — one REST call handles
        all chunks belonging to the document.

        Args:
            doc_id: LightRAG doc ID (e.g. "doc-abc123ef...")
            metadata: dict with temporal fields to inject. Unknown keys are
                      ignored. Missing keys are excluded from the payload
                      (existing values preserved).

        Returns:
            {"success": bool, "doc_id": str, "updated_count": int | None}
        """
        payload = self._build_qdrant_payload(metadata)
        if not payload:
            logger.warning("[QdrantInject] No payload fields for %s — skipping", doc_id)
            return {"success": True, "doc_id": doc_id, "updated_count": 0}

        body = {
            "payload": payload,
            "filter": {
                "must": [
                    {"key": "full_doc_id", "match": {"value": doc_id}}
                ]
            },
        }

        # POST /points/payload = set_payload (MERGE — keeps existing fields)
        # PUT  /points/payload = overwrite_payload (REPLACES entire payload — DO NOT USE)
        url = f"{self.base_url}/collections/{self.collection}/points/payload"
        try:
            resp = self._session.post(url, data=json.dumps(body), timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "ok":
                raise QdrantPayloadInjectorError(
                    f"Qdrant returned non-ok status: {data}"
                )
            logger.debug("[QdrantInject] set_payload ok for %s | payload keys: %s", doc_id, list(payload))
            return {"success": True, "doc_id": doc_id, "updated_count": None}
        except requests.RequestException as exc:
            raise QdrantPayloadInjectorError(
                f"set_payload failed for {doc_id}: {exc}"
            ) from exc

    def backfill_from_postgres(
        self,
        pg_dsn: str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Backfill all docs in temporal_metadata into Qdrant.

        Reads every row from temporal_metadata, builds the payload, and
        calls inject_doc_metadata for each. Safe to re-run (idempotent).

        Args:
            pg_dsn: PostgreSQL DSN. Falls back to env vars.
            workspace: Filter by workspace. Falls back to WORKSPACE env var.

        Returns:
            {"total": int, "injected": int, "skipped": int, "errors": list}
        """
        import psycopg2

        dsn = pg_dsn or self._build_pg_dsn()
        ws = workspace or os.getenv("WORKSPACE", "default")

        conn = psycopg2.connect(dsn)
        try:
            rows = self._fetch_temporal_metadata(conn, ws)
        finally:
            conn.close()

        total = len(rows)
        injected = 0
        skipped = 0
        errors: list[dict[str, Any]] = []

        for row in rows:
            doc_id = row["doc_id"]
            try:
                result = self.inject_doc_metadata(doc_id, row)
                if result.get("updated_count") == 0:
                    skipped += 1
                else:
                    injected += 1
                    logger.info("[QdrantInject] Injected %s", doc_id)
            except QdrantPayloadInjectorError as exc:
                logger.error("[QdrantInject] Error for %s: %s", doc_id, exc)
                errors.append({"doc_id": doc_id, "error": str(exc)})

        logger.info(
            "[QdrantInject] Backfill complete: %d total, %d injected, %d skipped, %d errors",
            total, injected, skipped, len(errors),
        )
        return {
            "total": total,
            "injected": injected,
            "skipped": skipped,
            "errors": errors,
        }

    def get_chunk_payload(self, doc_id: str) -> list[dict[str, Any]]:
        """Scroll chunks for a doc_id and return their payloads (for verification)."""
        url = f"{self.base_url}/collections/{self.collection}/points/scroll"
        body = {
            "limit": 100,
            "with_payload": True,
            "with_vector": False,
            "filter": {
                "must": [{"key": "full_doc_id", "match": {"value": doc_id}}]
            },
        }
        try:
            resp = self._session.post(url, data=json.dumps(body), timeout=self.timeout)
            resp.raise_for_status()
            return resp.json().get("result", {}).get("points", [])
        except requests.RequestException as exc:
            raise QdrantPayloadInjectorError(
                f"scroll failed for {doc_id}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_qdrant_payload(metadata: dict[str, Any]) -> dict[str, Any]:
        """Extract and normalize temporal fields for Qdrant injection.

        Only include fields that are present and non-None to avoid clobbering
        existing values with nulls.
        """
        payload: dict[str, Any] = {}

        cohort_years = metadata.get("cohort_years")
        if cohort_years is not None:
            # Normalize: JSON arrays from psycopg2 may already be lists.
            # Qdrant stores as JSON array; ensure Python list of ints or "*".
            if isinstance(cohort_years, str):
                cohort_years = json.loads(cohort_years)
            payload["cohort_years"] = cohort_years

        cohort_scope = metadata.get("cohort_scope")
        if cohort_scope is not None:
            payload["cohort_scope"] = cohort_scope

        is_archived = metadata.get("is_archived")
        if is_archived is not None:
            payload["is_archived"] = bool(is_archived)

        valid_from = metadata.get("valid_from")
        if valid_from is not None:
            payload["valid_from"] = str(valid_from)

        valid_until = metadata.get("valid_until")
        if valid_until is not None:
            payload["valid_until"] = str(valid_until)

        document_number = metadata.get("document_number")
        if document_number is not None:
            payload["document_number"] = document_number

        amends_documents = metadata.get("amends_documents")
        if amends_documents is not None:
            if isinstance(amends_documents, str):
                amends_documents = json.loads(amends_documents)
            payload["amends_documents"] = amends_documents

        return payload

    @staticmethod
    def _fetch_temporal_metadata(
        conn: Any,
        workspace: str,
    ) -> list[dict[str, Any]]:
        """Fetch all temporal_metadata rows for a workspace."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    doc_id,
                    cohort_years,
                    cohort_scope,
                    is_archived,
                    valid_from,
                    valid_until,
                    document_number,
                    amends_documents
                FROM temporal_metadata
                WHERE workspace = %s
                """,
                (workspace,),
            )
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    @staticmethod
    def _build_pg_dsn() -> str:
        # Use localhost:5433 to match lightrag_client._get_pg_connection() convention.
        # POSTGRES_HOST in .env.lightrag is the Docker-internal name (postgres_uit),
        # which is not reachable from the host machine.
        user = os.getenv("POSTGRES_USER", "uitrag")
        password = os.getenv("POSTGRES_PASSWORD", "")
        dbname = os.getenv("POSTGRES_DATABASE", "lightrag")
        return f"host=localhost port=5433 user={user} password={password} dbname={dbname}"
