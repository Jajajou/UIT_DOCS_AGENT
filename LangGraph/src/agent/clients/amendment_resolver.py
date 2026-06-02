"""
Clause-level amendment resolver with Option 2 pending logic.

Per-doc flow (called once per doc after upload + metadata save):

  Step A — forward: for each clause amendment extracted from the new doc:
    - If target doc exists in temporal_metadata → resolve immediately:
        INSERT clause_amendments
        UPDATE Qdrant target-clause payload (amended_by, is_superseded)
    - Else → INSERT pending_amendments (will resolve when target is indexed)

  Step B — backward: check pending_amendments WHERE target_doc_number = new doc:
    - For each pending row whose target is NOW available:
        INSERT clause_amendments
        UPDATE Qdrant new-doc clause payload (amended_by, is_superseded)
        DELETE from pending_amendments

pending_amendments drains naturally as corpus builds. After full reindex
it should contain only external government docs (86/2018/NĐ-CP etc.) which
will never be indexed — expected, not an error.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

import psycopg2
import psycopg2.pool
import requests
from dotenv import load_dotenv

from agent.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

load_dotenv(f"{PROJECT_ROOT}/.env.lightrag")

QDRANT_BASE_URL = os.getenv("QDRANT_BASE_URL", "http://localhost:6336")
QDRANT_COLLECTION = "lightrag_vdb_chunks"
DEFAULT_WORKSPACE = "uit_docs_agent"

_pg_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pg_pool_lock = threading.Lock()


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pg_pool
    with _pg_pool_lock:
        if _pg_pool is None:
            _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=4,
                host="localhost",
                port=int(os.getenv("POSTGRES_PORT", "5433")),
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD"),
                database=os.getenv("POSTGRES_DATABASE", "lightrag"),
            )
    return _pg_pool


class _PgConn:
    """Returns connection to pool on close()."""

    def __init__(self) -> None:
        self._pool = _get_pool()
        self._conn = self._pool.getconn()

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        self._pool.putconn(self._conn)


class AmendmentResolver:
    """
    Resolves clause-level amendment links at index time.

    Designed to be instantiated once per indexing job (or as singleton).
    Thread-safe via connection pool.
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
    # Main entry point
    # ------------------------------------------------------------------

    def resolve_for_doc(
        self,
        doc_number: str,
        doc_id: str,
        clause_amendments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Call once after a doc is fully indexed and metadata saved.

        Args:
            doc_number: Normalized doc number of newly indexed doc (e.g. "108/QĐ-ĐHCNTT").
            doc_id: LightRAG doc_id (e.g. "doc-abc123").
            clause_amendments: Output of clause_amendment_extractor.extract_clause_amendments().

        Returns:
            Summary dict: {resolved, pending_inserted, backward_resolved}
        """
        summary = {"resolved": 0, "pending_inserted": 0, "backward_resolved": 0}

        # Step A: forward — process amendments FROM this doc
        for ca in clause_amendments:
            target_doc_number = ca.get("target_doc_number")
            if not target_doc_number:
                continue

            target_doc_id = self._lookup_doc_id(target_doc_number)

            if target_doc_id:
                self._resolve_link(
                    source_doc_number=doc_number,
                    source_clause_id=ca.get("source_clause_id"),
                    source_doc_id=doc_id,
                    target_doc_number=target_doc_number,
                    target_clause_id=ca.get("target_clause_id"),
                    target_doc_id=target_doc_id,
                    amendment_type=ca.get("amendment_type", "replace_partial"),
                )
                summary["resolved"] += 1
                logger.info(
                    "[Resolver] Resolved: %s %s → %s %s (%s)",
                    doc_number, ca.get("source_clause_id"),
                    target_doc_number, ca.get("target_clause_id"),
                    ca.get("amendment_type"),
                )
            else:
                self._insert_pending(
                    source_doc_number=doc_number,
                    source_clause_id=ca.get("source_clause_id"),
                    source_doc_id=doc_id,
                    target_doc_number=target_doc_number,
                    target_clause_id=ca.get("target_clause_id"),
                    amendment_type=ca.get("amendment_type", "replace_partial"),
                )
                summary["pending_inserted"] += 1
                logger.info(
                    "[Resolver] Pending: %s %s → %s %s (target not indexed yet)",
                    doc_number, ca.get("source_clause_id"),
                    target_doc_number, ca.get("target_clause_id"),
                )

        # Step B: backward — resolve any pending rows targeting THIS doc
        pending = self._fetch_pending_for_target(doc_number)
        for row in pending:
            self._resolve_link(
                source_doc_number=row["source_doc_number"],
                source_clause_id=row["source_clause_id"],
                source_doc_id=row["source_doc_id"],
                target_doc_number=doc_number,
                target_clause_id=row["target_clause_id"],
                target_doc_id=doc_id,
                amendment_type=row["amendment_type"],
            )
            self._delete_pending(row["id"])
            summary["backward_resolved"] += 1
            logger.info(
                "[Resolver] Backward resolved: %s %s → %s %s",
                row["source_doc_number"], row["source_clause_id"],
                doc_number, row["target_clause_id"],
            )

        return summary

    # ------------------------------------------------------------------
    # PostgreSQL helpers
    # ------------------------------------------------------------------

    def _lookup_doc_id(self, doc_number: str) -> str | None:
        """Return doc_id from temporal_metadata if doc is indexed, else None."""
        sql = """
            SELECT doc_id FROM temporal_metadata
            WHERE document_number = %s AND workspace = %s
              AND doc_id IS NOT NULL
            LIMIT 1
        """
        with _PgConn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (doc_number, self.workspace))
                row = cur.fetchone()
        return row[0] if row else None

    def _resolve_link(
        self,
        source_doc_number: str,
        source_clause_id: str | None,
        source_doc_id: str | None,
        target_doc_number: str,
        target_clause_id: str | None,
        target_doc_id: str,
        amendment_type: str,
    ) -> None:
        """INSERT into clause_amendments + UPDATE Qdrant payload."""
        sql = """
            INSERT INTO clause_amendments (
                workspace, source_doc_number, source_clause_id, source_doc_id,
                target_doc_number, target_clause_id, target_doc_id, amendment_type
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """
        with _PgConn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    self.workspace,
                    source_doc_number, source_clause_id, source_doc_id,
                    target_doc_number, target_clause_id, target_doc_id,
                    amendment_type,
                ))
            conn.commit()

        # Update Qdrant payload for target clause chunks
        self._update_qdrant_amended_by(
            target_doc_id=target_doc_id,
            target_clause_id=target_clause_id,
            source_doc_number=source_doc_number,
            source_clause_id=source_clause_id,
            amendment_type=amendment_type,
        )

    def _insert_pending(
        self,
        source_doc_number: str,
        source_clause_id: str | None,
        source_doc_id: str | None,
        target_doc_number: str,
        target_clause_id: str | None,
        amendment_type: str,
    ) -> None:
        sql = """
            INSERT INTO pending_amendments (
                workspace, source_doc_number, source_clause_id, source_doc_id,
                target_doc_number, target_clause_id, amendment_type
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        with _PgConn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    self.workspace,
                    source_doc_number, source_clause_id, source_doc_id,
                    target_doc_number, target_clause_id,
                    amendment_type,
                ))
            conn.commit()

    def _fetch_pending_for_target(self, target_doc_number: str) -> list[dict[str, Any]]:
        sql = """
            SELECT id, source_doc_number, source_clause_id, source_doc_id,
                   target_clause_id, amendment_type
            FROM pending_amendments
            WHERE workspace = %s AND target_doc_number = %s
        """
        with _PgConn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (self.workspace, target_doc_number))
                rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "source_doc_number": r[1],
                "source_clause_id": r[2],
                "source_doc_id": r[3],
                "target_clause_id": r[4],
                "amendment_type": r[5],
            }
            for r in rows
        ]

    def _delete_pending(self, row_id: int) -> None:
        with _PgConn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM pending_amendments WHERE id = %s", (row_id,))
            conn.commit()

    # ------------------------------------------------------------------
    # Qdrant payload update
    # ------------------------------------------------------------------

    def _update_qdrant_amended_by(
        self,
        target_doc_id: str,
        target_clause_id: str | None,
        source_doc_number: str,
        source_clause_id: str | None,
        amendment_type: str,
    ) -> None:
        """
        Find target clause chunks in Qdrant and update their payload:
          amended_by += [{source_doc_number, source_clause_id, amendment_type}]
          is_superseded = True  (for replace_partial / replace_full / repeal)
        """
        point_ids = self._find_clause_point_ids(target_doc_id, target_clause_id)
        if not point_ids:
            logger.warning(
                "[Resolver] No Qdrant points found for doc_id=%s clause=%s",
                target_doc_id, target_clause_id,
            )
            return

        amendment_entry = {
            "source_doc_number": source_doc_number,
            "source_clause_id": source_clause_id,
            "amendment_type": amendment_type,
        }
        is_superseded = amendment_type in ("replace_partial", "replace_full", "repeal")

        # Qdrant set_payload endpoint
        url = f"{self.qdrant_base_url}/collections/{self.collection}/points/payload"
        for point_id in point_ids:
            # Read current amended_by list first (avoid overwriting concurrent updates)
            current = self._get_point_payload(point_id)
            amended_by: list = current.get("amended_by") or []
            if amendment_entry not in amended_by:
                amended_by = amended_by + [amendment_entry]

            payload = {"amended_by": amended_by}
            if is_superseded:
                payload["is_superseded"] = True

            body = {"payload": payload, "points": [point_id]}
            try:
                resp = self._session.post(url, json=body, timeout=self.timeout)
                resp.raise_for_status()
            except requests.RequestException as exc:
                logger.error(
                    "[Resolver] Qdrant payload update failed for point %s: %s",
                    point_id, exc,
                )

    def _find_clause_point_ids(
        self, doc_id: str, clause_id: str | None
    ) -> list[str]:
        """Scroll Qdrant for points matching full_doc_id [+ clause_id]."""
        url = f"{self.qdrant_base_url}/collections/{self.collection}/points/scroll"

        must_filter: list[dict] = [
            {"key": "full_doc_id", "match": {"value": doc_id}}
        ]
        if clause_id:
            must_filter.append({"key": "clause_id", "match": {"value": clause_id}})

        body: dict[str, Any] = {
            "filter": {"must": must_filter},
            "limit": 100,
            "with_payload": False,
        }
        try:
            resp = self._session.post(url, json=body, timeout=self.timeout)
            resp.raise_for_status()
            points = resp.json().get("result", {}).get("points", [])
            return [p["id"] for p in points]
        except requests.RequestException as exc:
            logger.error("[Resolver] Qdrant scroll failed: %s", exc)
            return []

    def _get_point_payload(self, point_id: str) -> dict[str, Any]:
        """Fetch current payload for a single Qdrant point."""
        url = f"{self.qdrant_base_url}/collections/{self.collection}/points/{point_id}"
        try:
            resp = self._session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json().get("result", {}).get("payload") or {}
        except requests.RequestException:
            return {}

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def pending_summary(self) -> dict[str, Any]:
        """Return count of unresolved pending amendments."""
        sql = """
            SELECT COUNT(*), COUNT(DISTINCT target_doc_number)
            FROM pending_amendments WHERE workspace = %s
        """
        with _PgConn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (self.workspace,))
                row = cur.fetchone()
        return {
            "pending_links": row[0] if row else 0,
            "pending_target_docs": row[1] if row else 0,
        }
