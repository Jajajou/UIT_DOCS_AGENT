"""
Unit tests for COHORT retrieval path (Branch 4).

Tests cover:
- QdrantCohortClient._point_to_chunk conversion (no I/O)
- route_retrieval conditional edge function
- route_after_cohort conditional edge function
- retrieve_cohort_data node (mocked client)
- QueryState accepts cohort_fallback field
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from typing import Any, Dict

from agent.clients.qdrant_cohort_client import QdrantCohortClient, QdrantCohortError
from agent.agents.retrieve_cohort import (
    retrieve_cohort_data,
    route_retrieval,
    route_after_cohort,
)
from agent.states.query_state import QueryState
import agent.agents.retrieve_cohort as retrieve_cohort_module


# ============================================================================
# QdrantCohortClient._point_to_chunk
# ============================================================================

class TestPointToChunk:
    """Tests for _point_to_chunk static conversion (no I/O)."""

    def _make_point(self, payload: Dict[str, Any], score: float = 0.85) -> Dict[str, Any]:
        return {"payload": payload, "score": score}

    def test_full_payload_converted(self):
        payload = {
            "content": "Quy dinh ngoai ngu K2022",
            "file_path": "https://uit.edu.vn/docs/qc2022.pdf",
            "cohort_years": [2022, 2023],
            "cohort_scope": "explicit",
            "valid_from": "2022-09-01",
            "valid_until": None,
            "is_archived": False,
            "document_number": "108/QD-DHCNTT",
            "amends_documents": [],
        }
        result = QdrantCohortClient._point_to_chunk(self._make_point(payload, score=0.92))

        assert result["content"] == "Quy dinh ngoai ngu K2022"
        assert result["file_path"] == "https://uit.edu.vn/docs/qc2022.pdf"
        assert result["score"] == pytest.approx(0.92)
        assert result["metadata"]["cohort_years"] == [2022, 2023]
        assert result["metadata"]["document_number"] == "108/QD-DHCNTT"
        assert result["metadata"]["is_archived"] is False

    def test_universal_cohort(self):
        payload = {
            "content": "Quy dinh chung",
            "file_path": "general.pdf",
            "cohort_years": ["*"],
            "cohort_scope": "universal",
            "is_archived": False,
        }
        result = QdrantCohortClient._point_to_chunk(self._make_point(payload))
        assert result["metadata"]["cohort_years"] == ["*"]
        assert result["metadata"]["cohort_scope"] == "universal"

    def test_missing_optional_fields_default_to_safe_values(self):
        result = QdrantCohortClient._point_to_chunk(self._make_point({}, score=0.0))
        assert result["content"] == ""
        assert result["file_path"] == ""
        assert result["metadata"]["cohort_years"] == []
        assert result["metadata"]["amends_documents"] == []
        assert result["metadata"]["is_archived"] is False
        assert result["metadata"]["document_number"] is None
        assert result["score"] == pytest.approx(0.0)

    def test_text_field_fallback_for_content(self):
        payload = {"text": "alternative content field"}
        result = QdrantCohortClient._point_to_chunk(self._make_point(payload))
        assert result["content"] == "alternative content field"

    def test_file_source_fallback_for_file_path(self):
        payload = {"file_source": "https://example.com/doc.pdf"}
        result = QdrantCohortClient._point_to_chunk(self._make_point(payload))
        assert result["file_path"] == "https://example.com/doc.pdf"

    def test_is_archived_true(self):
        payload = {"is_archived": True}
        result = QdrantCohortClient._point_to_chunk(self._make_point(payload))
        assert result["metadata"]["is_archived"] is True


# ============================================================================
# route_retrieval
# ============================================================================

class TestRouteRetrieval:
    """Tests for the conditional edge after agent1_understand_query."""

    def test_cohort_routes_to_cohort_node(self):
        state: QueryState = {"messages": [], "logs": [], "query_type": "COHORT"}
        assert route_retrieval(state) == "retrieve_cohort_data"

    def test_general_routes_to_retrieve_data(self):
        state: QueryState = {"messages": [], "logs": [], "query_type": "GENERAL"}
        assert route_retrieval(state) == "retrieve_data"

    def test_amendment_routes_to_amendment_node(self):
        state: QueryState = {"messages": [], "logs": [], "query_type": "AMENDMENT"}
        assert route_retrieval(state) == "retrieve_amendment_data"

    def test_missing_query_type_defaults_to_retrieve_data(self):
        state: QueryState = {"messages": [], "logs": []}
        assert route_retrieval(state) == "retrieve_data"

    def test_none_query_type_defaults_to_retrieve_data(self):
        state: QueryState = {"messages": [], "logs": [], "query_type": None}
        assert route_retrieval(state) == "retrieve_data"

    def test_routing_bypass_forces_retrieve_data_for_cohort(self):
        """USE_METADATA_ROUTING=false: COHORT queries fall through to GENERAL path."""
        mock_settings = MagicMock()
        mock_settings.use_metadata_routing = False
        state: QueryState = {"messages": [], "logs": [], "query_type": "COHORT"}
        with patch.object(retrieve_cohort_module, "settings", mock_settings):
            assert route_retrieval(state) == "retrieve_data"

    def test_routing_bypass_forces_retrieve_data_for_amendment(self):
        """USE_METADATA_ROUTING=false: AMENDMENT queries fall through to GENERAL path."""
        mock_settings = MagicMock()
        mock_settings.use_metadata_routing = False
        state: QueryState = {"messages": [], "logs": [], "query_type": "AMENDMENT"}
        with patch.object(retrieve_cohort_module, "settings", mock_settings):
            assert route_retrieval(state) == "retrieve_data"


# ============================================================================
# route_after_cohort
# ============================================================================

class TestRouteAfterCohort:
    """Tests for the conditional edge after retrieve_cohort_data."""

    def test_fallback_true_routes_to_retrieve_data(self):
        state: QueryState = {"messages": [], "logs": [], "cohort_fallback": True}
        assert route_after_cohort(state) == "retrieve_data"

    def test_fallback_false_routes_to_rerank(self):
        state: QueryState = {"messages": [], "logs": [], "cohort_fallback": False}
        assert route_after_cohort(state) == "rerank_data"

    def test_missing_fallback_defaults_to_rerank(self):
        state: QueryState = {"messages": [], "logs": []}
        assert route_after_cohort(state) == "rerank_data"


# ============================================================================
# retrieve_cohort_data node
# ============================================================================

class TestRetrieveCohortDataNode:
    """Tests for the retrieve_cohort_data node function (mocked client)."""

    def _base_state(self, **overrides) -> QueryState:
        base: QueryState = {
            "messages": [],
            "logs": [],
            "query": "Quy dinh ngoai ngu cho sinh vien K2022?",
            "parsed_intention": "Quy dinh ngoai ngu cho sinh vien K2022",
            "query_cohort_year": 2022,
            "query_type": "COHORT",
            "chunk_top_k": 40,
        }
        base.update(overrides)
        return base

    def _make_chunk(self, content: str = "test chunk", score: float = 0.9) -> Dict[str, Any]:
        return {
            "content": content,
            "file_path": "https://uit.edu.vn/doc.pdf",
            "metadata": {
                "cohort_years": [2022],
                "cohort_scope": "explicit",
                "valid_from": None,
                "valid_until": None,
                "is_archived": False,
                "document_number": None,
                "amends_documents": [],
            },
            "score": score,
        }

    @patch("agent.agents.retrieve_cohort._cohort_client")
    def test_successful_retrieval_populates_chunks(self, mock_client):
        chunks = [self._make_chunk("chunk 1"), self._make_chunk("chunk 2")]
        mock_client.retrieve.return_value = chunks

        result = retrieve_cohort_data(self._base_state())

        assert result["retrieved_chunks"] == chunks
        assert result["retrieved_entities"] == []
        assert result["retrieved_relationships"] == []
        assert result["cohort_fallback"] is False
        assert result["error"] is None
        assert result["retrieval_metadata"]["mode"] == "cohort_qdrant"
        assert result["retrieval_metadata"]["cohort_year"] == 2022
        assert result["retrieval_metadata"]["total_chunks"] == 2
        mock_client.retrieve.assert_called_once_with(
            query_text="Quy dinh ngoai ngu cho sinh vien K2022",
            cohort_year=2022,
            top_k=40,
        )

    @patch("agent.agents.retrieve_cohort._cohort_client")
    def test_zero_results_sets_fallback(self, mock_client):
        mock_client.retrieve.return_value = []

        result = retrieve_cohort_data(self._base_state())

        assert result["cohort_fallback"] is True
        assert "retrieved_chunks" not in result

    @patch("agent.agents.retrieve_cohort._cohort_client")
    def test_qdrant_error_sets_fallback(self, mock_client):
        mock_client.retrieve.side_effect = QdrantCohortError("connection refused")

        result = retrieve_cohort_data(self._base_state())

        assert result["cohort_fallback"] is True
        assert "connection refused" in result["error"]

    def test_missing_cohort_year_sets_fallback(self):
        state = self._base_state(query_cohort_year=None)
        result = retrieve_cohort_data(state)
        assert result["cohort_fallback"] is True

    def test_missing_query_sets_fallback(self):
        state: QueryState = {
            "messages": [],
            "logs": [],
            "query": "",
            "parsed_intention": "",
            "query_cohort_year": 2022,
            "query_type": "COHORT",
        }
        result = retrieve_cohort_data(state)
        assert result["cohort_fallback"] is True
        assert result.get("error")

    @patch("agent.agents.retrieve_cohort._cohort_client")
    def test_uses_parsed_intention_over_raw_query(self, mock_client):
        mock_client.retrieve.return_value = [self._make_chunk()]
        state = self._base_state(
            query="raw query",
            parsed_intention="parsed and refined query",
        )
        retrieve_cohort_data(state)
        call_kwargs = mock_client.retrieve.call_args
        assert call_kwargs.kwargs["query_text"] == "parsed and refined query"

    @patch("agent.agents.retrieve_cohort._cohort_client")
    def test_chunk_top_k_passed_to_client(self, mock_client):
        mock_client.retrieve.return_value = [self._make_chunk()]
        state = self._base_state(chunk_top_k=80)
        retrieve_cohort_data(state)
        call_kwargs = mock_client.retrieve.call_args
        assert call_kwargs.kwargs["top_k"] == 80


# ============================================================================
# QueryState accepts cohort_fallback
# ============================================================================

class TestQueryStateCohortFallback:
    def test_cohort_fallback_true(self):
        state: QueryState = {"messages": [], "logs": [], "cohort_fallback": True}
        assert state["cohort_fallback"] is True

    def test_cohort_fallback_false(self):
        state: QueryState = {"messages": [], "logs": [], "cohort_fallback": False}
        assert state["cohort_fallback"] is False

    def test_cohort_fallback_missing(self):
        state: QueryState = {"messages": [], "logs": []}
        assert state.get("cohort_fallback") is None
