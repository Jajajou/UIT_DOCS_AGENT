import requests
import os
import typing as t
import json
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
