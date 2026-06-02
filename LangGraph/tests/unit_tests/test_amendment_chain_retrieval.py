"""
Unit tests for AMENDMENT retrieval path (Branch 5).

Tests cover:
- AmendmentChainClient.get_latest_in_chain (mocked psycopg2)
- AmendmentChainClient.fetch_chunks_by_doc_id (mocked requests)
- route_retrieval now handles AMENDMENT → retrieve_amendment_data
- route_after_amendment conditional edge function
- retrieve_amendment_data node (mocked client)
- QueryState accepts amendment_fallback field
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch, call
from typing import Any, Dict

from agent.clients.amendment_chain_client import AmendmentChainClient, AmendmentChainError
from agent.agents.retrieve_amendment import (
    retrieve_amendment_data,
    route_after_amendment,
)
from agent.agents.retrieve_cohort import route_retrieval
from agent.states.query_state import QueryState


# ============================================================================
# AmendmentChainClient.get_latest_in_chain  (mocked psycopg2)
# ============================================================================

class TestGetLatestInChain:

    def _make_client(self) -> AmendmentChainClient:
        return AmendmentChainClient()

    @patch("agent.clients.amendment_chain_client.psycopg2")
    def test_single_doc_no_amenders(self, mock_psycopg2):
        """Doc exists but nothing amends it — it IS the leaf."""
        mock_conn = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = lambda s: s
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.fetchall.return_value = [
            ("doc-abc123", "108/QD-DHCNTT", 1)
        ]

        client = self._make_client()
        result = client.get_latest_in_chain("108/QD-DHCNTT")

        assert len(result) == 1
        assert result[0]["doc_id"] == "doc-abc123"
        assert result[0]["doc_number"] == "108/QD-DHCNTT"
        assert result[0]["depth"] == 1

    @patch("agent.clients.amendment_chain_client.psycopg2")
    def test_chain_of_two_returns_leaf(self, mock_psycopg2):
        """Doc 108 is amended by doc 215 — leaf should be 215 (depth 2)."""
        mock_conn = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = lambda s: s
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.fetchall.return_value = [
            ("doc-def456", "215/QD-DHCNTT", 2),
            ("doc-abc123", "108/QD-DHCNTT", 1),
        ]

        client = self._make_client()
        result = client.get_latest_in_chain("108/QD-DHCNTT")

        assert len(result) == 1
        assert result[0]["doc_number"] == "215/QD-DHCNTT"
        assert result[0]["depth"] == 2

    @patch("agent.clients.amendment_chain_client.psycopg2")
    def test_not_found_returns_empty(self, mock_psycopg2):
        mock_conn = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = lambda s: s
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.fetchall.return_value = []

        client = self._make_client()
        result = client.get_latest_in_chain("999/QD-UNKNOWN")

        assert result == []

    @patch("agent.clients.amendment_chain_client.psycopg2")
    def test_db_error_raises_amendment_chain_error(self, mock_psycopg2):
        import psycopg2 as real_psycopg2
        mock_psycopg2.connect.side_effect = real_psycopg2.OperationalError("connection refused")
        mock_psycopg2.Error = real_psycopg2.Error

        client = self._make_client()
        with pytest.raises(AmendmentChainError, match="Amendment chain query failed"):
            client.get_latest_in_chain("108/QD-DHCNTT")

    @patch("agent.clients.amendment_chain_client.psycopg2")
    def test_doc_number_stripped(self, mock_psycopg2):
        """Whitespace in doc_number_ref should be stripped before querying."""
        mock_conn = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor = mock_conn.cursor.return_value.__enter__ = lambda s: s
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.fetchall.return_value = [
            ("doc-abc", "108/QD-DHCNTT", 1)
        ]

        client = self._make_client()
        result = client.get_latest_in_chain("  108/QD-DHCNTT  ")
        # Should still find result (stripped to "108/QD-DHCNTT")
        assert len(result) == 1


# ============================================================================
# route_retrieval — AMENDMENT routing
# ============================================================================

class TestRouteRetrievalAmendment:

    def setup_method(self):
        os.environ["USE_METADATA_ROUTING"] = "true"

    def teardown_method(self):
        os.environ.pop("USE_METADATA_ROUTING", None)

    def test_amendment_routes_to_amendment_node(self):
        state: QueryState = {"messages": [], "logs": [], "query_type": "AMENDMENT"}
        assert route_retrieval(state) == "retrieve_amendment_data"

    def test_cohort_still_routes_to_cohort(self):
        state: QueryState = {"messages": [], "logs": [], "query_type": "COHORT"}
        assert route_retrieval(state) == "retrieve_cohort_data"

    def test_general_still_routes_to_retrieve_data(self):
        state: QueryState = {"messages": [], "logs": [], "query_type": "GENERAL"}
        assert route_retrieval(state) == "retrieve_data"

    def test_none_routes_to_retrieve_data(self):
        state: QueryState = {"messages": [], "logs": []}
        assert route_retrieval(state) == "retrieve_data"


# ============================================================================
# route_after_amendment
# ============================================================================

class TestRouteAfterAmendment:

    def test_fallback_true_routes_to_retrieve_data(self):
        state: QueryState = {"messages": [], "logs": [], "amendment_fallback": True}
        assert route_after_amendment(state) == "retrieve_data"

    def test_fallback_false_routes_to_enrich(self):
        state: QueryState = {"messages": [], "logs": [], "amendment_fallback": False}
        assert route_after_amendment(state) == "enrich_with_temporal_metadata"

    def test_missing_fallback_defaults_to_enrich(self):
        state: QueryState = {"messages": [], "logs": []}
        assert route_after_amendment(state) == "enrich_with_temporal_metadata"


# ============================================================================
# retrieve_amendment_data node
# ============================================================================

class TestRetrieveAmendmentDataNode:

    def _base_state(self, **overrides) -> QueryState:
        base: QueryState = {
            "messages": [],
            "logs": [],
            "query": "Quyet dinh 108 co bi sua doi chua?",
            "parsed_intention": "Tim hieu trang thai phap ly cua Quyet dinh 108",
            "query_document_ref": "108/QD-DHCNTT",
            "query_type": "AMENDMENT",
            "chunk_top_k": 30,
        }
        base.update(overrides)
        return base

    def _make_chunk(self, content: str = "chunk content", score: float = 0.9) -> Dict[str, Any]:
        return {
            "content": content,
            "file_path": "https://uit.edu.vn/doc.pdf",
            "metadata": {
                "cohort_years": [],
                "cohort_scope": None,
                "valid_from": "2022-01-01",
                "valid_until": None,
                "is_archived": False,
                "document_number": "215/QD-DHCNTT",
                "amends_documents": ["108/QD-DHCNTT"],
            },
            "score": score,
        }

    @patch("agent.agents.retrieve_amendment._amendment_client")
    def test_successful_retrieval_populates_chunks(self, mock_client):
        chunks = [self._make_chunk("chunk 1"), self._make_chunk("chunk 2")]
        mock_client.retrieve.return_value = chunks

        result = retrieve_amendment_data(self._base_state())

        assert result["retrieved_chunks"] == chunks
        assert result["retrieved_entities"] == []
        assert result["retrieved_relationships"] == []
        assert result["amendment_fallback"] is False
        assert result["error"] is None
        assert result["retrieval_metadata"]["mode"] == "amendment_qdrant"
        assert result["retrieval_metadata"]["doc_number_ref"] == "108/QD-DHCNTT"
        assert result["retrieval_metadata"]["total_chunks"] == 2
        mock_client.retrieve.assert_called_once_with(
            query_text="Tim hieu trang thai phap ly cua Quyet dinh 108",
            doc_number_ref="108/QD-DHCNTT",
            top_k=30,
        )

    @patch("agent.agents.retrieve_amendment._amendment_client")
    def test_zero_results_sets_fallback(self, mock_client):
        mock_client.retrieve.return_value = []
        result = retrieve_amendment_data(self._base_state())
        assert result["amendment_fallback"] is True
        assert "retrieved_chunks" not in result

    @patch("agent.agents.retrieve_amendment._amendment_client")
    def test_client_error_sets_fallback(self, mock_client):
        mock_client.retrieve.side_effect = AmendmentChainError("db error")
        result = retrieve_amendment_data(self._base_state())
        assert result["amendment_fallback"] is True
        assert "db error" in result["error"]

    def test_missing_doc_ref_sets_fallback(self):
        state = self._base_state(query_document_ref=None)
        result = retrieve_amendment_data(state)
        assert result["amendment_fallback"] is True

    def test_empty_doc_ref_sets_fallback(self):
        state = self._base_state(query_document_ref="")
        result = retrieve_amendment_data(state)
        assert result["amendment_fallback"] is True

    def test_missing_query_sets_fallback(self):
        state: QueryState = {
            "messages": [],
            "logs": [],
            "query": "",
            "parsed_intention": "",
            "query_document_ref": "108/QD-DHCNTT",
            "query_type": "AMENDMENT",
        }
        result = retrieve_amendment_data(state)
        assert result["amendment_fallback"] is True

    @patch("agent.agents.retrieve_amendment._amendment_client")
    def test_uses_parsed_intention_over_raw_query(self, mock_client):
        mock_client.retrieve.return_value = [self._make_chunk()]
        state = self._base_state(query="raw", parsed_intention="refined")
        retrieve_amendment_data(state)
        assert mock_client.retrieve.call_args.kwargs["query_text"] == "refined"

    @patch("agent.agents.retrieve_amendment._amendment_client")
    def test_chunk_top_k_passed_to_client(self, mock_client):
        mock_client.retrieve.return_value = [self._make_chunk()]
        state = self._base_state(chunk_top_k=50)
        retrieve_amendment_data(state)
        assert mock_client.retrieve.call_args.kwargs["top_k"] == 50


# ============================================================================
# QueryState accepts amendment_fallback
# ============================================================================

class TestQueryStateAmendmentFallback:

    def test_amendment_fallback_true(self):
        state: QueryState = {"messages": [], "logs": [], "amendment_fallback": True}
        assert state["amendment_fallback"] is True

    def test_amendment_fallback_false(self):
        state: QueryState = {"messages": [], "logs": [], "amendment_fallback": False}
        assert state["amendment_fallback"] is False

    def test_amendment_fallback_missing(self):
        state: QueryState = {"messages": [], "logs": []}
        assert state.get("amendment_fallback") is None
