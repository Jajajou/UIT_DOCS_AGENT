import requests
import os
import typing as t
import json
import psycopg2
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
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
    def upload_file(self, file_path: str) -> dict:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f)}
            r = self._post("/documents/upload", files=files)
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
        load_dotenv(".env.lightrag")

        return psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            database=os.getenv("POSTGRES_DATABASE", "lightrag")
        )

    def update_document_metadata(
        self,
        doc_id: str,
        metadata: Dict[str, Any],
        merge: bool = True
    ) -> Dict[str, Any]:
        """
        Update document metadata in PostgreSQL.

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
                # LightRAG stores document status in lightrag_kv table
                # Key format: "doc_status:{doc_id}"
                key = f"doc_status:{doc_id}"

                # Fetch current document data
                cur.execute(
                    "SELECT value FROM lightrag_kv WHERE workspace = %s AND key = %s",
                    (workspace, key)
                )
                row = cur.fetchone()

                if not row:
                    conn.close()
                    return {
                        "success": False,
                        "error": f"Document {doc_id} not found in workspace {workspace}"
                    }

                # Parse document data
                doc_data = json.loads(row[0])

                # Update metadata
                if merge:
                    # Merge with existing metadata
                    existing_metadata = doc_data.get("metadata", {})
                    if existing_metadata:
                        existing_metadata.update(metadata)
                        doc_data["metadata"] = existing_metadata
                    else:
                        doc_data["metadata"] = metadata
                else:
                    # Replace metadata
                    doc_data["metadata"] = metadata

                # Update in database
                cur.execute(
                    "UPDATE lightrag_kv SET value = %s WHERE workspace = %s AND key = %s",
                    (json.dumps(doc_data), workspace, key)
                )

                conn.commit()

            conn.close()

            return {
                "success": True,
                "doc_id": doc_id,
                "metadata": doc_data["metadata"]
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

        cutoff = datetime.fromisoformat(cutoff_date)

        # Get all documents (large page size to get everything)
        all_docs_response = self.documents_paginated(page_size=10000)
        all_docs = all_docs_response.get("documents", [])

        expired_doc_ids = []
        expired_docs_info = []

        for doc in all_docs:
            metadata = doc.get("metadata", {})

            # Skip already archived
            if metadata.get("is_archived"):
                continue

            # Check expiration
            valid_until = metadata.get("valid_until")
            if valid_until:
                try:
                    expiry_date = datetime.fromisoformat(valid_until)
                    if expiry_date.date() < cutoff.date():
                        expired_doc_ids.append(doc["id"])
                        expired_docs_info.append({
                            "id": doc["id"],
                            "file_path": doc.get("file_path", "unknown"),
                            "valid_until": valid_until,
                            "document_type": metadata.get("document_type", "unknown")
                        })
                except (ValueError, TypeError):
                    # Invalid date format, skip
                    continue

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
