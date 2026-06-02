"""
Unit tests for HITL query phase routing.

Covers:
- route_after_agent1: all 5 routing paths
- request_context: interrupt payload shape + state update on resume
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from agent.agents.agent1_query_understanding import route_after_agent1
from agent.states.query_state import QueryState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(**kwargs) -> QueryState:
    base: QueryState = {
        "messages": [],
        "query": "test query",
        "query_type": "GENERAL",
        "query_cohort_year": None,
        "education_system": None,
        "extracted_topics": [],
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# route_after_agent1
# ---------------------------------------------------------------------------

class TestRouteAfterAgent1:

    def test_general_no_cohort_no_policy(self):
        """Non-policy GENERAL query → retrieve_data."""
        state = _state(query_type="GENERAL", extracted_topics=["lịch thi"])
        assert route_after_agent1(state) == "retrieve_data"

    def test_amendment_routes_directly(self):
        """AMENDMENT type without cohort_year → retrieve_amendment_data."""
        state = _state(
            query_type="AMENDMENT",
            query_cohort_year=None,
            education_system="chinh_quy",
            extracted_topics=["sửa đổi quyết định 108"],
        )
        assert route_after_agent1(state) == "retrieve_amendment_data"

    def test_cohort_with_full_context(self):
        """COHORT query + cohort_year + edu_system → retrieve_cohort_data."""
        state = _state(
            query_type="COHORT",
            query_cohort_year=2022,
            education_system="chinh_quy",
            extracted_topics=["quy định ngoại ngữ"],
        )
        assert route_after_agent1(state) == "retrieve_cohort_data"

    def test_cohort_missing_cohort_year_triggers_hitl(self):
        """COHORT + needs_student_context + missing cohort_year → request_context."""
        state = _state(
            query_type="COHORT",
            query_cohort_year=None,
            education_system="chinh_quy",
            needs_student_context=True,
            extracted_topics=[],
        )
        assert route_after_agent1(state) == "request_context"

    def test_cohort_missing_edu_system_does_not_trigger_hitl(self):
        """COHORT + needs_student_context + has cohort_year but missing education_system → retrieve_cohort_data (optional enrichment)."""
        state = _state(
            query_type="COHORT",
            query_cohort_year=2022,
            education_system=None,
            needs_student_context=True,
            extracted_topics=[],
        )
        assert route_after_agent1(state) == "retrieve_cohort_data"

    def test_cohort_missing_both_triggers_hitl(self):
        """COHORT + needs_student_context + missing both → request_context."""
        state = _state(
            query_type="COHORT",
            query_cohort_year=None,
            education_system=None,
            needs_student_context=True,
        )
        assert route_after_agent1(state) == "request_context"

    def test_policy_topic_missing_cohort_triggers_hitl(self):
        """GENERAL + needs_student_context + no cohort → request_context."""
        state = _state(
            query_type="GENERAL",
            query_cohort_year=None,
            education_system=None,
            needs_student_context=True,
            extracted_topics=["quy chế học vụ"],
        )
        assert route_after_agent1(state) == "request_context"

    def test_policy_topic_with_full_context_routes_data(self):
        """GENERAL + full context + no needs_student_context → retrieve_data."""
        state = _state(
            query_type="GENERAL",
            query_cohort_year=None,
            education_system="chinh_quy",
            needs_student_context=False,
            extracted_topics=["quy định học bổng"],
        )
        assert route_after_agent1(state) == "retrieve_data"

    def test_tot_nghiep_topic_missing_cohort(self):
        """needs_student_context + no cohort_year → request_context."""
        state = _state(
            query_type="GENERAL",
            query_cohort_year=None,
            education_system="chinh_quy",
            needs_student_context=True,
            extracted_topics=["điều kiện tốt nghiệp"],
        )
        assert route_after_agent1(state) == "request_context"

    def test_amendment_bypasses_hitl_regardless_of_context(self):
        """AMENDMENT type never triggers HITL even with no cohort/edu."""
        state = _state(
            query_type="AMENDMENT",
            query_cohort_year=None,
            education_system=None,
            extracted_topics=["sửa đổi"],
        )
        assert route_after_agent1(state) == "retrieve_amendment_data"


# ---------------------------------------------------------------------------
# request_context node
# ---------------------------------------------------------------------------

class TestRequestContextNode:

    @patch("langgraph.types.interrupt")
    def test_interrupt_called_with_missing_cohort(self, mock_interrupt):
        """When cohort_year missing, interrupt payload includes it in missing_fields."""
        from agent.graphs.query_graph import request_context

        mock_interrupt.return_value = {"cohort_year": 2022, "education_system": "chinh_quy"}

        state = _state(query_cohort_year=None, education_system="chinh_quy", query="học bổng khóa tôi")
        result = request_context(state)

        mock_interrupt.assert_called_once()
        payload = mock_interrupt.call_args[0][0]
        assert payload["action"] == "request_context"
        assert any("khóa" in f for f in payload["missing_fields"])
        assert payload["current_query"] == "học bổng khóa tôi"

    @patch("langgraph.types.interrupt")
    def test_interrupt_called_with_missing_edu_system(self, mock_interrupt):
        """When edu_system missing, interrupt payload includes it in missing_fields."""
        from agent.graphs.query_graph import request_context

        mock_interrupt.return_value = {"cohort_year": 2022, "education_system": "lien_thong"}

        state = _state(query_cohort_year=2022, education_system=None)
        result = request_context(state)

        payload = mock_interrupt.call_args[0][0]
        assert any("hệ đào tạo" in f for f in payload["missing_fields"])

    @patch("langgraph.types.interrupt")
    def test_resume_updates_cohort_year(self, mock_interrupt):
        """After resume with cohort_year, state update contains query_cohort_year."""
        from agent.graphs.query_graph import request_context

        mock_interrupt.return_value = {"cohort_year": 2023, "education_system": "chinh_quy"}

        state = _state(query_cohort_year=None, education_system=None)
        result = request_context(state)

        assert result["query_cohort_year"] == 2023
        assert result["education_system"] == "chinh_quy"

    @patch("langgraph.types.interrupt")
    def test_resume_partial_only_cohort(self, mock_interrupt):
        """Resume with only cohort_year — education_system not in update."""
        from agent.graphs.query_graph import request_context

        mock_interrupt.return_value = {"cohort_year": 2024}

        state = _state(query_cohort_year=None, education_system=None)
        result = request_context(state)

        assert result["query_cohort_year"] == 2024
        assert "education_system" not in result

    @patch("langgraph.types.interrupt")
    def test_resume_non_dict_response_no_crash(self, mock_interrupt):
        """Non-dict resume response → empty update, no crash."""
        from agent.graphs.query_graph import request_context

        mock_interrupt.return_value = None

        state = _state(query_cohort_year=None, education_system=None)
        result = request_context(state)

        assert result == {}
