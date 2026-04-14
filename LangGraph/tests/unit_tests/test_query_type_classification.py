"""
Unit tests for query_type classification in QueryUnderstanding (Branch 3).

Tests cover:
- QueryUnderstanding Pydantic model accepts query_type + query_document_ref
- QueryState TypedDict accepts these fields
- Default values are correct
- Classification logic via field descriptions (smoke tests)
"""

from __future__ import annotations

import pytest
from agent.states.query_state import QueryUnderstanding, QueryState


# ============================================================================
# QueryUnderstanding model tests
# ============================================================================

class TestQueryUnderstandingModel:
    """Tests for QueryUnderstanding Pydantic model."""

    def _base_kwargs(self) -> dict:
        return {
            "parsed_intention": "test intention",
            "extracted_entities": [],
            "extracted_topics": [],
            "confidence": 0.8,
            "confidence_reason": "clear query",
            "suggested_mode": "local",
            "suggested_top_k": 5,
            "suggested_chunk_top_k": 15,
            "tuning_reason": "simple query",
        }

    def test_default_query_type_is_general(self):
        model = QueryUnderstanding(**self._base_kwargs())
        assert model.query_type == "GENERAL"

    def test_default_query_document_ref_is_none(self):
        model = QueryUnderstanding(**self._base_kwargs())
        assert model.query_document_ref is None

    def test_default_query_cohort_year_is_none(self):
        model = QueryUnderstanding(**self._base_kwargs())
        assert model.query_cohort_year is None

    def test_cohort_query_type(self):
        kwargs = {**self._base_kwargs(), "query_type": "COHORT", "query_cohort_year": 2022}
        model = QueryUnderstanding(**kwargs)
        assert model.query_type == "COHORT"
        assert model.query_cohort_year == 2022

    def test_amendment_query_type_with_doc_ref(self):
        kwargs = {
            **self._base_kwargs(),
            "query_type": "AMENDMENT",
            "query_document_ref": "108/QD-DHCNTT",
        }
        model = QueryUnderstanding(**kwargs)
        assert model.query_type == "AMENDMENT"
        assert model.query_document_ref == "108/QD-DHCNTT"

    def test_amendment_query_type_without_doc_ref(self):
        kwargs = {**self._base_kwargs(), "query_type": "AMENDMENT"}
        model = QueryUnderstanding(**kwargs)
        assert model.query_type == "AMENDMENT"
        assert model.query_document_ref is None

    def test_general_query_type_explicit(self):
        kwargs = {**self._base_kwargs(), "query_type": "GENERAL"}
        model = QueryUnderstanding(**kwargs)
        assert model.query_type == "GENERAL"

    def test_invalid_query_type_raises(self):
        kwargs = {**self._base_kwargs(), "query_type": "INVALID"}
        with pytest.raises(Exception):
            QueryUnderstanding(**kwargs)

    def test_all_fields_round_trip(self):
        kwargs = {
            **self._base_kwargs(),
            "query_type": "COHORT",
            "query_cohort_year": 2023,
            "query_document_ref": None,
        }
        model = QueryUnderstanding(**kwargs)
        dumped = model.model_dump()
        assert dumped["query_type"] == "COHORT"
        assert dumped["query_cohort_year"] == 2023
        assert dumped["query_document_ref"] is None

    def test_query_document_ref_various_formats(self):
        """Document refs can take multiple formats."""
        formats = [
            "108/QD-DHCNTT",
            "141/QĐ-ĐHCNTT",
            "QD-108",
            "Quyết định 108",
        ]
        base = {**self._base_kwargs(), "query_type": "AMENDMENT"}
        for ref in formats:
            model = QueryUnderstanding(**base, query_document_ref=ref)
            assert model.query_document_ref == ref


# ============================================================================
# QueryState TypedDict tests
# ============================================================================

class TestQueryStateTypedDict:
    """Tests that QueryState TypedDict accepts query_type and query_document_ref."""

    def test_query_state_accepts_query_type(self):
        state: QueryState = {
            "messages": [],
            "logs": [],
            "query_type": "COHORT",
        }
        assert state["query_type"] == "COHORT"

    def test_query_state_accepts_query_document_ref(self):
        state: QueryState = {
            "messages": [],
            "logs": [],
            "query_document_ref": "108/QD-DHCNTT",
        }
        assert state["query_document_ref"] == "108/QD-DHCNTT"

    def test_query_state_query_type_defaults_to_missing(self):
        state: QueryState = {"messages": [], "logs": []}
        assert state.get("query_type") is None

    def test_query_state_all_three_cohort_fields(self):
        state: QueryState = {
            "messages": [],
            "logs": [],
            "query_cohort_year": 2022,
            "query_type": "COHORT",
            "query_document_ref": None,
        }
        assert state["query_cohort_year"] == 2022
        assert state["query_type"] == "COHORT"
        assert state["query_document_ref"] is None


# ============================================================================
# Classification semantics smoke tests
# ============================================================================

class TestQueryTypeSemantics:
    """
    Smoke tests that verify the Pydantic model correctly stores values
    that simulate what the LLM would output for known query patterns.

    These do NOT invoke the LLM — they validate that the model correctly
    validates and stores the expected classification outputs.
    """

    def _make_understanding(self, query_type: str, cohort_year=None, doc_ref=None) -> QueryUnderstanding:
        return QueryUnderstanding(
            parsed_intention="test",
            extracted_entities=[],
            extracted_topics=[],
            confidence=0.9,
            confidence_reason="test",
            query_cohort_year=cohort_year,
            query_type=query_type,
            query_document_ref=doc_ref,
            suggested_mode="local",
            suggested_top_k=5,
            suggested_chunk_top_k=15,
            tuning_reason="test",
        )

    def test_cohort_query_stores_year(self):
        # "Quy dinh ngoai ngu cho sinh vien K2022?" -> COHORT, year=2022
        model = self._make_understanding("COHORT", cohort_year=2022)
        assert model.query_type == "COHORT"
        assert model.query_cohort_year == 2022
        assert model.query_document_ref is None

    def test_amendment_query_stores_doc_ref(self):
        # "Quyet dinh 108 co bi sua doi chua?" -> AMENDMENT, ref="108/QD-DHCNTT"
        model = self._make_understanding("AMENDMENT", doc_ref="108/QD-DHCNTT")
        assert model.query_type == "AMENDMENT"
        assert model.query_document_ref == "108/QD-DHCNTT"
        assert model.query_cohort_year is None

    def test_amendment_no_ref_for_latest_query(self):
        # "Quy che dao tao moi nhat la gi?" -> AMENDMENT, no specific doc ref
        model = self._make_understanding("AMENDMENT")
        assert model.query_type == "AMENDMENT"
        assert model.query_document_ref is None

    def test_general_query_no_special_fields(self):
        # "Lam sao de xin hoc bong?" -> GENERAL
        model = self._make_understanding("GENERAL")
        assert model.query_type == "GENERAL"
        assert model.query_cohort_year is None
        assert model.query_document_ref is None

    def test_cohort_2024(self):
        model = self._make_understanding("COHORT", cohort_year=2024)
        assert model.query_type == "COHORT"
        assert model.query_cohort_year == 2024

    def test_amendment_priority_over_cohort(self):
        # "Quy che K2022 moi nhat la gi?" -> AMENDMENT takes priority
        model = self._make_understanding("AMENDMENT", cohort_year=2022)
        assert model.query_type == "AMENDMENT"
        assert model.query_cohort_year == 2022  # cohort year still captured
