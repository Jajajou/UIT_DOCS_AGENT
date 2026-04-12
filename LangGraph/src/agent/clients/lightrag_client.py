import requests
import os
import typing as t
import json
import psycopg2
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from agent.config import PROJECT_ROOT
DEFAULT_TIMEOUT = 60  # seconds


class LightRAGAPIError(RuntimeError):
    pass


class LightRAGAPIClient:
    load_dotenv("LangGraph/.env")
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        access_token: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("LIGHTRAG_URL") or "").rstrip("/")
        if not self.base_url:
            raise ValueError("Base URL is required (env LIGHTRAG_URL or constructor arg).")

        self.api_key = api_key or os.getenv("LIGHTRAG_API_KEY")
        self.access_token = access_token or os.getenv("LIGHTRAG_ACCESS_TOKEN")
        self.timeout = timeout
        self._session = session or requests.Session()

    # ------------------------------ auth & headers ------------------------------
    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
        }
        # API key header per OpenAPI: name "X-API-Key", in "header"
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if extra:
            headers.update(extra)
        return headers

    def login(self, username: str, password: str, scope: str = "") -> dict:
        """
        Password grant to /login (form-encoded).
        On success, sets self.access_token.
        """
        url = f"{self.base_url}/login"
        data = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "scope": scope,
        }
        # NOTE: per spec, content-type is application/x-www-form-urlencoded
        resp = self._session.post(url, data=data, headers=self._headers(), timeout=self.timeout)
        resp.raise_for_status()
        out = resp.json()
        token = out.get("access_token") or out.get("token") or out.get("id_token")
        if token:
            self.access_token = token
        return out

    # ------------------------------ utility ------------------------------
    def _get(self, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        return self._session.get(url, headers=self._headers(), timeout=self.timeout, **kwargs)

    def _post(self, path: str, json: dict | None = None, data: dict | None = None, files: dict | None = None, stream: bool = False, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        return self._session.post(url, headers=self._headers(), timeout=self.timeout, json=json, data=data, files=files, stream=stream, **kwargs)

    def _delete(self, path: str, json: dict | None = None, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        return self._session.delete(url, headers=self._headers(), timeout=self.timeout, json=json, **kwargs)

    # ------------------------------ health & meta ------------------------------
    def health(self) -> dict:
        r = self._get("/health")
        r.raise_for_status()
        return r.json()

    def auth_status(self) -> dict:
        r = self._get("/auth-status")
        r.raise_for_status()
        return r.json()

    # ------------------------------ documents ------------------------------
    def upload_file(self, file_path: str, file_source: str | None = None) -> dict:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f)}
            data = {"file_source": file_source} if file_source else None
            r = self._post("/documents/upload", files=files, data=data)
        r.raise_for_status()
        return r.json()

    def insert_text(self, text: str, file_source: str | None = None) -> dict:
        payload = {"text": text}
        if file_source is not None:
            payload["file_source"] = file_source
        r = self._post("/documents/text", json=payload)
        r.raise_for_status()
        return r.json()

    def insert_texts(self, texts: list[str], file_sources: list[str] | None = None) -> dict:
        payload: dict[str, t.Any] = {"texts": texts}
        if file_sources is not None:
            payload["file_sources"] = file_sources
        r = self._post("/documents/texts", json=payload)
        r.raise_for_status()
        return r.json()

    def documents(self) -> dict:
        r = self._get("/documents")
        r.raise_for_status()
        return r.json()

    def documents_paginated(
        self,
        page: int = 1,
        page_size: int = 50,
        sort_field: str = "updated_at",
        sort_direction: str = "desc",
        status_filter: str | None = None,
    ) -> dict:
        payload: dict[str, t.Any] = {
            "page": page,
            "page_size": page_size,
            "sort_field": sort_field,
            "sort_direction": sort_direction,
        }
        if status_filter:
            payload["status_filter"] = status_filter
        r = self._post("/documents/paginated", json=payload)
        r.raise_for_status()
        return r.json()

    def status_counts(self) -> dict:
        r = self._get("/documents/status_counts")
        r.raise_for_status()
        return r.json()

    def pipeline_status(self) -> dict:
        r = self._get("/documents/pipeline_status")
        r.raise_for_status()
        return r.json()

    def trigger_scan(self) -> dict:
        r = self._post("/documents/scan")
        r.raise_for_status()
        return r.json()

    def reprocess_failed(self) -> dict:
        r = self._post("/documents/reprocess_failed")
        r.raise_for_status()
        return r.json()

    def delete_document(self, doc_ids: list[str], delete_file: bool = False) -> dict:
        payload = {"doc_ids": doc_ids, "delete_file": delete_file}
        r = self._delete("/documents/delete_document", json=payload)
        r.raise_for_status()
        return r.json()

    def clear_cache(self) -> dict:
        r = self._post("/documents/clear_cache", json={})
        r.raise_for_status()
        return r.json()

    # ------------------------------ query ------------------------------
    def query(
        self,
        query_text: str,
        mode: str = "mix",
        include_references: bool = False,
        response_type: str | None = None,
        top_k: int | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        max_total_tokens: int | None = None,
    ) -> dict:
        payload: dict[str, t.Any] = {
            "query": query_text,
            "mode": mode,
            "include_references": include_references,
        }
        if response_type is not None:
            payload["response_type"] = response_type
        if top_k is not None:
            payload["top_k"] = top_k
        if conversation_history is not None:
            payload["conversation_history"] = conversation_history
        if max_total_tokens is not None:
            payload["max_total_tokens"] = max_total_tokens

        r = self._post("/query", json=payload)
        r.raise_for_status()
        return r.json()

    def query_stream(
        self,
        query_text: str,
        mode: str = "mix",
        include_references: bool = False,
        response_type: str | None = None,
        top_k: int | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        max_total_tokens: int | None = None,
        stream: bool = True,
        decode_unicode: bool = True,
    ) -> t.Iterable[dict]:
        """
        Streams NDJSON objects from /query/stream.
        Yields Python dicts per line: { "references": [...] } or { "response": "..." } or { "error": "..." }
        """
        payload: dict[str, t.Any] = {
            "query": query_text,
            "mode": mode,
            "stream": stream,
            "include_references": include_references,
        }
        if response_type is not None:
            payload["response_type"] = response_type
        if top_k is not None:
            payload["top_k"] = top_k
        if conversation_history is not None:
            payload["conversation_history"] = conversation_history
        if max_total_tokens is not None:
            payload["max_total_tokens"] = max_total_tokens

        r = self._post("/query/stream", json=payload, stream=True)
        r.raise_for_status()
        # Iterate NDJSON lines
        for line in r.iter_lines(decode_unicode=decode_unicode):
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # In case server accidentally sends a full JSON, try to handle it once.
                try:
                    obj = json.loads(line.decode() if isinstance(line, (bytes, bytearray)) else line)
                    yield obj
                except Exception:
                    yield {"error": f"Failed to decode line: {line!r}"}

    def query_data(
        self,
        query_text: str,
        mode: str = "mix",
        top_k: int | None = None,
        chunk_top_k: int | None = None,
        max_entity_tokens: int | None = None,
        max_relation_tokens: int | None = None,
        max_total_tokens: int | None = None,
    ) -> dict:
        payload: dict[str, t.Any] = {
            "query": query_text,
            "mode": mode,
            "enable_rerank": False
        }
        if top_k is not None:
            payload["top_k"] = top_k
        if chunk_top_k is not None:
            payload["chunk_top_k"] = chunk_top_k
        if max_entity_tokens is not None:
            payload["max_entity_tokens"] = max_entity_tokens
        if max_relation_tokens is not None:
            payload["max_relation_tokens"] = max_relation_tokens
        if max_total_tokens is not None:
            payload["max_total_tokens"] = max_total_tokens

        r = self._post("/query/data", json=payload)
        r.raise_for_status()
        return r.json()

    # ------------------------------ graph ------------------------------
    def graph_labels(self) -> list[str]:
        r = self._get("/graph/label/list")
        r.raise_for_status()
        return r.json()

    def graph_popular_labels(self, limit: int = 300) -> list[str]:
        r = self._get("/graph/label/popular", params={"limit": limit})
        r.raise_for_status()
        return r.json()

    def graph_search_labels(self, q: str, limit: int = 50) -> list[str]:
        r = self._get("/graph/label/search", params={"q": q, "limit": limit})
        r.raise_for_status()
        return r.json()

    def get_graph(self, label: str, max_depth: int | None = None, max_nodes: int | None = None) -> dict:
        params: dict[str, t.Any] = {"label": label}
        if max_depth is not None:
            params["max_depth"] = max_depth
        if max_nodes is not None:
            params["max_nodes"] = max_nodes
        r = self._get("/graphs", params=params)
        r.raise_for_status()
        return r.json()

    def entity_exists(self, name: str) -> dict:
        r = self._get("/graph/entity/exists", params={"name": name})
        r.raise_for_status()
        return r.json()

    def update_entity(self, entity_name: str, updated_data: dict, allow_rename: bool = False) -> dict:
        payload = {"entity_name": entity_name, "updated_data": updated_data, "allow_rename": allow_rename}
        r = self._post("/graph/entity/edit", json=payload)
        r.raise_for_status()
        return r.json()

    def update_relation(self, source_id: str, target_id: str, relation_data: dict) -> dict:
        payload = {"source_id": source_id, "target_id": target_id, "updated_data": relation_data}
        r = self._post("/graph/relation/edit", json=payload)
        r.raise_for_status()
        return r.json()

    def create_entity(self, entity_name: str, entity_data: dict) -> dict:
        payload = {"entity_name": entity_name, "entity_data": entity_data}
        r = self._post("/graph/entity/create", json=payload)
        r.raise_for_status()
        return r.json()

    def create_relation(self, source_entity: str, target_entity: str, relation_data: dict) -> dict:
        payload = {"source_entity": source_entity, "target_entity": target_entity, "relation_data": relation_data}
        r = self._post("/graph/relation/create", json=payload)
        r.raise_for_status()
        return r.json()

    def merge_entities(self, entities_to_change: list[str], entity_to_change_into: str) -> dict:
        payload = {"entities_to_change": entities_to_change, "entity_to_change_into": entity_to_change_into}
        r = self._post("/graph/entities/merge", json=payload)
        r.raise_for_status()
        return r.json()

    # ------------------------------ ollama emulation ------------------------------
    def api_version(self) -> dict:
        r = self._get("/api/version")
        r.raise_for_status()
        return r.json()

    def api_tags(self) -> dict:
        r = self._get("/api/tags")
        r.raise_for_status()
        return r.json()

    def api_ps(self) -> dict:
        r = self._get("/api/ps")
        r.raise_for_status()
        return r.json()

    def api_generate(self, payload: dict) -> dict:
        r = self._post("/api/generate", json=payload)
        r.raise_for_status()
        return r.json()

    def api_chat(self, payload: dict) -> dict:
        r = self._post("/api/chat", json=payload)
        r.raise_for_status()
        return r.json()

    # ------------------------------ temporal metadata management ------------------------------

    def _get_pg_connection(self):
        """
        Get PostgreSQL connection for direct metadata management.

        LightRAG stores documents in PostgreSQL when using PGKVStorage.
        This allows us to update document metadata directly.
        """
        load_dotenv(f"{PROJECT_ROOT}/.env.lightrag")

        return psycopg2.connect(
                host="localhost",
                port=5433,
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD"),
                database=os.getenv("POSTGRES_DATABASE", "lightrag")
            )

    def update_document_metadata_by_track_id(
        self,
        track_id: str,
        metadata: Dict[str, Any],
        merge: bool = True
    ) -> Dict[str, Any]:
        """
        Update document metadata using track_id (faster, no polling needed).

        Args:
            track_id: Tracking ID from insert_text/upload_file
            metadata: Metadata dictionary to set/merge
            merge: If True, merge with existing metadata. If False, replace.

        Returns:
            Result dictionary with status
        """
        try:
            conn = self._get_pg_connection()
            workspace = os.getenv("WORKSPACE", "default")

            with conn.cursor() as cur:
                # Find document by track_id
                cur.execute(
                    "SELECT id, metadata FROM lightrag_doc_status WHERE workspace = %s AND track_id = %s",
                    (workspace, track_id)
                )
                row = cur.fetchone()

                if not row:
                    conn.close()
                    return {
                        "success": False,
                        "error": f"Document with track_id {track_id} not found in workspace {workspace}"
                    }

                doc_id = row[0]
                existing_metadata = row[1] if row[1] else {}

                # Update metadata
                if merge:
                    existing_metadata.update(metadata)
                    new_metadata = existing_metadata
                else:
                    new_metadata = metadata

                # Update in database
                cur.execute(
                    "UPDATE lightrag_doc_status SET metadata = %s WHERE workspace = %s AND id = %s",
                    (json.dumps(new_metadata), workspace, doc_id)
                )

                conn.commit()

            conn.close()

            return {
                "success": True,
                "doc_id": doc_id,
                "track_id": track_id,
                "metadata": new_metadata
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def save_temporal_metadata(
        self,
        track_id: str,
        doc_id: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Save temporal metadata to separate temporal_metadata table.

        This method stores temporal metadata in a dedicated table to avoid
        conflicts with LightRAG's metadata overwrites during processing.

        Args:
            track_id: LightRAG tracking ID
            doc_id: LightRAG document ID
            metadata: Temporal metadata dictionary containing:
                - document_number: Document number (e.g., "108/2024/QĐ-ĐHQGTP")
                - document_type: Document type (e.g., "Quyết định")
                - valid_from: Effective date
                - valid_until: Expiry date (optional)
                - cohort_years: List of cohort years
                - student_cohorts: Alternative cohort field
                - amends_documents: List of amended document numbers
                - extraction_method: Method used for extraction
                - extraction_confidence: Confidence score (0.0-1.0)
                - additional fields stored in additional_metadata

        Returns:
            Result dictionary with success status and inserted ID
        """
        try:
            conn = self._get_pg_connection()
            workspace = os.getenv("WORKSPACE", "default")

            # Extract known fields
            document_number = metadata.get("document_number")
            document_type = metadata.get("document_type")
            valid_from = metadata.get("valid_from")
            valid_until = metadata.get("valid_until")
            cohort_years = metadata.get("cohort_years")
            cohort_scope = metadata.get("cohort_scope")
            student_cohorts = metadata.get("student_cohorts")
            amends_documents = metadata.get("amends_documents")
            extraction_method = metadata.get("extraction_method")
            extraction_confidence = metadata.get("extraction_confidence")

            # Store remaining fields in additional_metadata
            known_fields = {
                "document_number", "document_type", "valid_from", "valid_until",
                "cohort_years", "cohort_scope", "student_cohorts", "amends_documents",
                "extraction_method", "extraction_confidence"
            }
            additional_metadata = {
                k: v for k, v in metadata.items() if k not in known_fields
            }

            with conn.cursor() as cur:
                # Insert or update temporal metadata
                cur.execute("""
                    INSERT INTO temporal_metadata (
                        doc_id, track_id, workspace,
                        document_number, document_type,
                        valid_from, valid_until,
                        cohort_years, cohort_scope, student_cohorts,
                        amends_documents,
                        extraction_method, extraction_confidence,
                        extraction_timestamp,
                        additional_metadata
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s,
                        %s, %s,
                        CURRENT_TIMESTAMP,
                        %s
                    )
                    ON CONFLICT (doc_id) DO UPDATE SET
                        track_id = EXCLUDED.track_id,
                        workspace = EXCLUDED.workspace,
                        document_number = EXCLUDED.document_number,
                        document_type = EXCLUDED.document_type,
                        valid_from = EXCLUDED.valid_from,
                        valid_until = EXCLUDED.valid_until,
                        cohort_years = EXCLUDED.cohort_years,
                        cohort_scope = EXCLUDED.cohort_scope,
                        student_cohorts = EXCLUDED.student_cohorts,
                        amends_documents = EXCLUDED.amends_documents,
                        extraction_method = EXCLUDED.extraction_method,
                        extraction_confidence = EXCLUDED.extraction_confidence,
                        extraction_timestamp = CURRENT_TIMESTAMP,
                        additional_metadata = EXCLUDED.additional_metadata,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id;
                """, (
                    doc_id, track_id, workspace,
                    document_number, document_type,
                    valid_from, valid_until,
                    json.dumps(cohort_years) if cohort_years else None,
                    cohort_scope,
                    json.dumps(student_cohorts) if student_cohorts else None,
                    json.dumps(amends_documents) if amends_documents else None,
                    extraction_method, extraction_confidence,
                    json.dumps(additional_metadata) if additional_metadata else None
                ))

                inserted_id = cur.fetchone()[0]
                conn.commit()

            conn.close()

            return {
                "success": True,
                "id": inserted_id,
                "doc_id": doc_id,
                "track_id": track_id,
                "metadata_saved": True
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def update_document_metadata(
        self,
        doc_id: str,
        metadata: Dict[str, Any],
        merge: bool = True
    ) -> Dict[str, Any]:
        """
        Update document metadata in PostgreSQL by doc_id.

        Since LightRAG API doesn't expose metadata update endpoint yet,
        we update the metadata field directly in PostgreSQL.

        Args:
            doc_id: Document ID to update
            metadata: Metadata dictionary to set/merge
            merge: If True, merge with existing metadata. If False, replace.

        Returns:
            Result dictionary with status
        """
        try:
            conn = self._get_pg_connection()
            workspace = os.getenv("WORKSPACE", "default")

            with conn.cursor() as cur:
                # LightRAG stores document status in lightrag_doc_status table
                # Fetch current document metadata
                cur.execute(
                    "SELECT metadata FROM lightrag_doc_status WHERE workspace = %s AND id = %s",
                    (workspace, doc_id)
                )
                row = cur.fetchone()

                if not row:
                    conn.close()
                    return {
                        "success": False,
                        "error": f"Document {doc_id} not found in workspace {workspace}"
                    }

                # Get existing metadata (may be None)
                existing_metadata = row[0] if row[0] else {}

                # Update metadata
                if merge:
                    # Merge with existing metadata
                    existing_metadata.update(metadata)
                    new_metadata = existing_metadata
                else:
                    # Replace metadata
                    new_metadata = metadata

                # Update in database
                cur.execute(
                    "UPDATE lightrag_doc_status SET metadata = %s WHERE workspace = %s AND id = %s",
                    (json.dumps(new_metadata), workspace, doc_id)
                )

                conn.commit()

            conn.close()

            return {
                "success": True,
                "doc_id": doc_id,
                "metadata": new_metadata
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def soft_delete_documents(
        self,
        doc_ids: List[str],
        reason: str = "expired"
    ) -> Dict[str, Any]:
        """
        Soft delete documents by marking them as archived in metadata.

        Sets metadata.is_archived = True without removing from knowledge graph.

        Args:
            doc_ids: List of document IDs to archive
            reason: Reason for archiving (expired, superseded, manual)

        Returns:
            Results of archiving operation
        """
        results = {"archived": [], "failed": []}

        for doc_id in doc_ids:
            archive_metadata = {
                "is_archived": True,
                "archived_at": datetime.now().isoformat(),
                "archive_reason": reason
            }

            result = self.update_document_metadata(
                doc_id=doc_id,
                metadata=archive_metadata,
                merge=True
            )

            if result.get("success"):
                results["archived"].append(doc_id)
            else:
                results["failed"].append({
                    "doc_id": doc_id,
                    "error": result.get("error", "Unknown error")
                })

        # Also update temporal_metadata table for accurate archival tracking
        if results["archived"]:
            try:
                conn = self._get_pg_connection()
                workspace = os.getenv("WORKSPACE", "default")
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE temporal_metadata
                        SET
                          is_archived = TRUE,
                          archived_at = CURRENT_TIMESTAMP,
                          archive_reason = %s,
                          updated_at = CURRENT_TIMESTAMP
                        WHERE doc_id = ANY(%s) AND workspace = %s
                        """,
                        (reason, results["archived"], workspace)
                    )
                    conn.commit()
                conn.close()
            except Exception as e:
                print(f"[Soft Delete] Warning: failed to update temporal_metadata: {e}")

        return results

    def get_active_documents(
        self,
        page: int = 1,
        page_size: int = 50,
        sort_field: str = "updated_at",
        sort_direction: str = "desc",
        filter_archived: bool = True
    ) -> Dict[str, Any]:
        """
        Get documents with optional filtering of archived items.

        Args:
            page: Page number
            page_size: Items per page
            sort_field: Field to sort by
            sort_direction: Sort direction (asc/desc)
            filter_archived: If True, exclude archived documents

        Returns:
            Paginated documents response
        """
        # Fetch documents from API
        response = self.documents_paginated(
            page=page,
            page_size=page_size * 2 if filter_archived else page_size,  # Fetch more to account for filtering
            sort_field=sort_field,
            sort_direction=sort_direction
        )

        if not filter_archived:
            return response

        # Filter out archived documents
        all_docs = response.get("documents", [])
        active_docs = [
            doc for doc in all_docs
            if not doc.get("metadata", {}).get("is_archived", False)
        ]

        # Apply pagination to filtered results
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_docs = active_docs[start_idx:end_idx]

        return {
            "documents": paginated_docs,
            "total": len(active_docs),
            "page": page,
            "page_size": page_size,
            "total_filtered": len(all_docs) - len(active_docs)
        }

    def archive_expired_documents(
        self,
        cutoff_date: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Archive documents that have passed their valid_until date.

        Args:
            cutoff_date: ISO date string. Documents expired before this are archived.
                         Defaults to today.
            dry_run: If True, return what would be archived without making changes

        Returns:
            Summary of archiving operation
        """
        if not cutoff_date:
            cutoff_date = datetime.now().date().isoformat()

        expired_doc_ids = []
        expired_docs_info = []

        try:
            conn = self._get_pg_connection()
            workspace = os.getenv("WORKSPACE", "default")
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      tm.doc_id, tm.valid_until::text, tm.document_number,
                      tm.document_type, lds.file_source
                    FROM temporal_metadata tm
                    LEFT JOIN lightrag_doc_status lds ON lds.id = tm.doc_id
                    WHERE tm.workspace = %s
                      AND tm.is_archived = FALSE
                      AND tm.valid_until IS NOT NULL
                      AND tm.valid_until < %s::date
                    """,
                    (workspace, cutoff_date)
                )
                rows = cur.fetchall()
            conn.close()

            for row in rows:
                doc_id, valid_until, doc_number, doc_type, file_source = row
                expired_doc_ids.append(doc_id)
                expired_docs_info.append({
                    "id": doc_id,
                    "file_path": file_source or "unknown",
                    "valid_until": valid_until,
                    "document_number": doc_number or "unknown",
                    "document_type": doc_type or "unknown"
                })
        except Exception as e:
            print(f"[Archive Expired] Error querying temporal_metadata: {e}")
            return {
                "archived": [],
                "failed": [],
                "error": str(e),
                "cutoff_date": cutoff_date
            }

        if dry_run:
            return {
                "dry_run": True,
                "would_archive_count": len(expired_doc_ids),
                "expired_documents": expired_docs_info,
                "cutoff_date": cutoff_date
            }

        # Archive expired docs
        if expired_doc_ids:
            result = self.soft_delete_documents(expired_doc_ids, reason="expired")
            result["expired_documents"] = expired_docs_info
            result["cutoff_date"] = cutoff_date
            return result
        else:
            return {
                "archived": [],
                "failed": [],
                "message": "No expired documents found",
                "cutoff_date": cutoff_date
            }

    def _find_doc_ids_by_number(self, doc_number: str) -> List[str]:
        """
        Find document IDs by their official document number using PostgreSQL.

        Queries temporal_metadata.document_number (the authoritative source).
        Falls back to a fuzzy match to handle minor formatting differences.

        Args:
            doc_number: Document number (e.g., "123/QĐ-ĐHCNTT")

        Returns:
            List of matching document IDs
        """
        doc_ids = []
        try:
            conn = self._get_pg_connection()
            workspace = os.getenv("WORKSPACE", "default")

            with conn.cursor() as cur:
                # Exact match in temporal_metadata (authoritative source)
                query = """
                    SELECT doc_id
                    FROM temporal_metadata
                    WHERE workspace = %s
                    AND document_number = %s
                """
                cur.execute(query, (workspace, doc_number))
                rows = cur.fetchall()

                if not rows:
                    # Fuzzy match: strip spaces and compare case-insensitively
                    query_fuzzy = """
                        SELECT doc_id
                        FROM temporal_metadata
                        WHERE workspace = %s
                        AND REPLACE(LOWER(document_number), ' ', '') =
                            REPLACE(LOWER(%s), ' ', '')
                    """
                    cur.execute(query_fuzzy, (workspace, doc_number))
                    rows = cur.fetchall()

                for row in rows:
                    doc_ids.append(row[0])

            conn.close()
        except Exception as e:
            print(f"[LightRAG Client] Error searching for doc number {doc_number}: {e}")

        return doc_ids

    def backfill_amendment_links(self) -> Dict[str, Any]:
        """
        Post-reindex pass: for every document that has amends_documents set,
        try to populate amended_by_documents on the referenced old documents.

        Run this once after a full reindex to ensure bidirectional links are
        complete regardless of indexing order.

        Returns:
            Summary dict with counts of linked, skipped, not_found, errors.
        """
        summary = {"total_amending_docs": 0, "linked": 0, "not_found": 0, "errors": 0}
        try:
            conn = self._get_pg_connection()
            workspace = os.getenv("WORKSPACE", "default")

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT doc_id, amends_documents
                    FROM temporal_metadata
                    WHERE workspace = %s
                    AND amends_documents IS NOT NULL
                    AND jsonb_array_length(amends_documents) > 0
                    """,
                    (workspace,)
                )
                rows = cur.fetchall()

            conn.close()

            summary["total_amending_docs"] = len(rows)
            print(f"[Backfill] Found {len(rows)} documents with amends_documents to process")

            for doc_id, amends_list in rows:
                amended_numbers = amends_list if isinstance(amends_list, list) else []
                if not amended_numbers:
                    continue

                result = self.link_amended_documents(doc_id, amended_numbers)
                summary["linked"] += len(result.get("linked_docs", []))
                summary["not_found"] += len(result.get("not_found", []))
                summary["errors"] += len(result.get("errors", []))

        except Exception as e:
            print(f"[Backfill] Fatal error: {e}")
            summary["errors"] += 1

        print(f"[Backfill] Done: {summary}")
        return summary

    def link_amended_documents(
        self, 
        new_doc_id: str, 
        amended_doc_numbers: List[str]
    ) -> Dict[str, Any]:
        """
        Link a new document to the documents it amends.

        1. Finds old documents by their document numbers.
        2. Updates old documents' metadata: adds new_doc_id to 'amended_by' list.
        3. Returns summary of links created.

        Args:
            new_doc_id: ID of the new amending document
            amended_doc_numbers: List of document numbers being amended (e.g. ["123/QĐ-ĐHCNTT"])

        Returns:
            Dictionary summary of operations
        """
        results = {
            "linked_docs": [],
            "not_found": [],
            "errors": []
        }

        if not amended_doc_numbers:
            return results

        print(f"[Temporal Linking] Linking new doc {new_doc_id} to {amended_doc_numbers}")

        for old_doc_number in amended_doc_numbers:
            # 1. Find old document IDs
            old_doc_ids = self._find_doc_ids_by_number(old_doc_number)
            
            if not old_doc_ids:
                print(f"[Temporal Linking] WARNING: Old document number '{old_doc_number}' not found in DB.")
                results["not_found"].append(old_doc_number)
                continue

            # 2. Update each found old document
            for old_doc_id in old_doc_ids:
                try:
                    # Get current metadata to append to list, not overwrite
                    # We can't use simple merge because we need to append to a list
                    conn = self._get_pg_connection()
                    workspace = os.getenv("WORKSPACE", "default")
                    
                    with conn.cursor() as cur:
                        # Get current metadata
                        cur.execute(
                            "SELECT metadata FROM lightrag_doc_status WHERE workspace = %s AND id = %s",
                            (workspace, old_doc_id)
                        )
                        row = cur.fetchone()

                        if row:
                            metadata = row[0] if row[0] else {}

                            # Update amended_by list in lightrag_doc_status (backward compat)
                            amended_by = metadata.get("amended_by", [])
                            if new_doc_id not in amended_by:
                                amended_by.append(new_doc_id)
                                metadata["amended_by"] = amended_by

                                # Save back to lightrag_doc_status
                                cur.execute(
                                    "UPDATE lightrag_doc_status SET metadata = %s WHERE workspace = %s AND id = %s",
                                    (json.dumps(metadata), workspace, old_doc_id)
                                )
                                conn.commit()

                                # Also update temporal_metadata for durable amended_by tracking
                                cur.execute(
                                    """
                                    UPDATE temporal_metadata
                                    SET
                                      amended_by_documents = CASE
                                        WHEN amended_by_documents IS NULL THEN to_jsonb(ARRAY[%s::text])
                                        WHEN NOT (amended_by_documents @> to_jsonb(ARRAY[%s::text]))
                                          THEN amended_by_documents || to_jsonb(ARRAY[%s::text])
                                        ELSE amended_by_documents
                                      END,
                                      updated_at = CURRENT_TIMESTAMP
                                    WHERE doc_id = %s AND workspace = %s
                                    """,
                                    (new_doc_id, new_doc_id, new_doc_id, old_doc_id, workspace)
                                )
                                conn.commit()

                                results["linked_docs"].append({
                                    "old_doc_id": old_doc_id,
                                    "old_doc_number": old_doc_number
                                })
                                print(f"[Temporal Linking] Linked: {old_doc_number} ({old_doc_id}) <- amended by {new_doc_id}")

                    conn.close()

                except Exception as e:
                    error_msg = f"Error updating old doc {old_doc_id}: {str(e)}"
                    print(f"[Temporal Linking] ERROR: {error_msg}")
                    results["errors"].append(error_msg)

        return results

    def get_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document data or None if not found
        """
        # LightRAG doesn't have a get-by-ID endpoint, so we fetch all and filter
        # This is inefficient for large datasets - should be improved in upstream
        all_docs_response = self.documents_paginated(page_size=1000)

        for doc in all_docs_response.get("documents", []):
            if doc["id"] == doc_id:
                return doc

        return None

    def get_all_documents_with_metadata(
        self,
        include_archived: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all documents with their metadata from PostgreSQL.

        Used by ping_service for automated archiving.

        Args:
            include_archived: If True, include already archived documents

        Returns:
            List of documents with id, file_source, and metadata
        """
        try:
            conn = self._get_pg_connection()
            workspace = os.getenv("WORKSPACE", "default")

            with conn.cursor() as cur:
                if include_archived:
                    cur.execute(
                        """
                        SELECT id, file_source, metadata, created_at, updated_at
                        FROM lightrag_doc_status
                        WHERE workspace = %s
                        ORDER BY created_at DESC
                        """,
                        (workspace,)
                    )
                else:
                    # Exclude already archived documents
                    cur.execute(
                        """
                        SELECT id, file_source, metadata, created_at, updated_at
                        FROM lightrag_doc_status
                        WHERE workspace = %s
                        AND (metadata->>'is_archived' IS NULL OR metadata->>'is_archived' = 'false')
                        ORDER BY created_at DESC
                        """,
                        (workspace,)
                    )

                rows = cur.fetchall()

            conn.close()

            documents = []
            for row in rows:
                documents.append({
                    "id": row[0],
                    "file_source": row[1],
                    "metadata": row[2] if row[2] else {},
                    "created_at": row[3].isoformat() if row[3] else None,
                    "updated_at": row[4].isoformat() if row[4] else None
                })

            return documents

        except Exception as e:
            print(f"[LightRAG Client] Error fetching all documents: {e}")
            return []

    def get_temporal_metadata_by_file_sources(
        self,
        file_sources: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Batch-fetch temporal metadata for a list of file_sources.

        Joins lightrag_doc_status with temporal_metadata in a single query.
        Returns a mapping of file_source -> temporal metadata dict so callers
        can enrich retrieved items without N+1 queries.

        Key names in the returned dicts match what calculate_temporal_score()
        and assess_temporal_freshness() expect:
          valid_from, valid_until, is_archived, indexed_at,
          amended_by (mapped from amended_by_documents),
          document_number, cohort_years, extraction_confidence

        On any error, returns {} (graceful fallback — items scored neutral 0.5).
        """
        if not file_sources:
            return {}

        try:
            conn = self._get_pg_connection()
            workspace = os.getenv("WORKSPACE", "default")

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      lds.file_source,
                      tm.doc_id,
                      tm.document_number,
                      tm.document_type,
                      tm.valid_from::text,
                      tm.valid_until::text,
                      tm.cohort_years,
                      tm.cohort_scope,
                      tm.amends_documents,
                      tm.amended_by_documents,
                      tm.is_archived,
                      tm.archived_at::text,
                      tm.archive_reason,
                      tm.extraction_confidence,
                      tm.extraction_timestamp::text AS indexed_at
                    FROM lightrag_doc_status lds
                    INNER JOIN temporal_metadata tm ON tm.doc_id = lds.id
                    WHERE lds.workspace = %s
                      AND lds.file_source = ANY(%s)
                    """,
                    (workspace, list(file_sources))
                )
                rows = cur.fetchall()
            conn.close()

            result: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                (
                    file_source, doc_id, document_number, document_type,
                    valid_from, valid_until, cohort_years, cohort_scope,
                    amends_documents, amended_by_documents, is_archived,
                    archived_at, archive_reason, extraction_confidence, indexed_at
                ) = row
                if file_source:
                    result[file_source] = {
                        "doc_id": doc_id,
                        "document_number": document_number,
                        "document_type": document_type,
                        "valid_from": valid_from,
                        "valid_until": valid_until,
                        "cohort_years": cohort_years or [],
                        "cohort_scope": cohort_scope,
                        "amends_documents": amends_documents or [],
                        "amended_by": amended_by_documents or [],
                        "is_archived": bool(is_archived),
                        "archived_at": archived_at,
                        "archive_reason": archive_reason,
                        "extraction_confidence": extraction_confidence,
                        "indexed_at": indexed_at,
                    }
            return result

        except Exception as e:
            print(f"[LightRAG Client] Error fetching temporal metadata by file_sources: {e}")
            return {}

    def get_doc_id_by_track_id(
        self,
        track_id: str,
        max_wait_seconds: int = 30,
        poll_interval: float = 1.0
    ) -> Optional[str]:
        """
        Poll for doc_id using track_id after background processing.

        Uses PostgreSQL direct query as fallback when API endpoint returns empty.
        LightRAG stores track_id in document metadata during processing.

        Args:
            track_id: Tracking ID from insert_text/upload_file
            max_wait_seconds: Maximum time to wait for processing (default 30s)
            poll_interval: Seconds between polling attempts (default 1s)

        Returns:
            Document ID if found, None if timeout or error
        """
        import time

        start_time = time.time()

        while (time.time() - start_time) < max_wait_seconds:
            try:
                # Try API endpoint first (faster when available)
                r = self._get(f"/documents/track_status/{track_id}")
                r.raise_for_status()
                response = r.json()

                documents = response.get("documents", [])
                if documents and len(documents) > 0:
                    doc_id = documents[0].get("id")
                    if doc_id:
                        return doc_id

                # API returned empty - try PostgreSQL direct query
                # LightRAG may have created doc_status entry but not finished processing
                doc_id = self._find_doc_id_by_track_id_in_db(track_id)
                if doc_id:
                    return doc_id

                # Wait before next poll
                time.sleep(poll_interval)

            except Exception as e:
                print(f"[LightRAG Client] Error polling track_id {track_id}: {e}")
                time.sleep(poll_interval)

        # Timeout
        print(f"[LightRAG Client] Timeout waiting for doc_id (track_id: {track_id})")
        return None

    def _find_doc_id_by_track_id_in_db(self, track_id: str) -> Optional[str]:
        """
        Find doc_id by searching PostgreSQL for track_id in document metadata.

        This is a fallback when the API endpoint hasn't returned documents yet,
        but the doc_status entry has been created.

        Args:
            track_id: Tracking ID to search for

        Returns:
            Document ID if found, None otherwise
        """
        try:
            conn = self._get_pg_connection()
            workspace = os.getenv("WORKSPACE", "default")

            with conn.cursor() as cur:
                # Search for track_id in lightrag_doc_status table
                # LightRAG stores track_id at root level
                query = """
                    SELECT id
                    FROM lightrag_doc_status
                    WHERE workspace = %s
                    AND track_id = %s
                    LIMIT 1
                """
                cur.execute(query, (workspace, track_id))
                row = cur.fetchone()

                if row:
                    doc_id = row[0]
                    conn.close()
                    return doc_id

            conn.close()

        except Exception as e:
            print(f"[LightRAG Client] Error searching DB for track_id {track_id}: {e}")

        return None

# if __name__ == "__main__":
#     load_dotenv("LangGraph/.env")
#     base_url = (os.getenv("LIGHTRAG_URL" ) or "").rstrip("/")
#     api_key = os.getenv("LIGHTRAG_API_KEY")
#     token = os.getenv("LIGHTRAG_ACCESS_TOKEN")
#     client = LightRAGAPIClient(base_url=base_url, api_key=api_key, access_token=token)

#     try:
#         print("Health:", client.health())
#     except Exception as e:
#         print("Health check failed:", e)

#     try:
#         print("Auth status:", client.auth_status())
#     except Exception as e:
#         print("Auth status check failed:", e)
