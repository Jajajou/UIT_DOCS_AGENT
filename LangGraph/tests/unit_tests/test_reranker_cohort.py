"""
Unit tests for cohort-aware scoring in MultiSourceReranker.

Tests _compute_cohort_score() across all branches and verifies
that use_cohort_boost=False regression is preserved.
"""

from __future__ import annotations

from typing import Dict, Any, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_item(cohort_years: Optional[list]) -> Dict[str, Any]:
    """Build a minimal item dict with optional cohort_years in metadata."""
    if cohort_years is None:
        return {"content": "test", "metadata": {}}
    return {"content": "test", "metadata": {"cohort_years": cohort_years}}


# ---------------------------------------------------------------------------
# _compute_cohort_score tests
# ---------------------------------------------------------------------------

class TestComputeCohortScore:
    """Tests for Reranker._compute_cohort_score()."""

    @pytest.fixture
    def reranker(self):
        """Return a Reranker instance with model load skipped."""
        with patch("agent.clients.reranker.settings") as mock_settings:
            mock_settings.reranker_base_url = "http://fake-reranker"
            mock_settings.reranker.default_model = "fake-model"
            mock_settings.reranker.use_fp16 = False
            from agent.clients.reranker import Reranker
            r = Reranker()
        return r

    def test_cohort_match_returns_1(self, reranker):
        """query_cohort_year=2022, cohort_years=[2022, 2023] -> 1.0"""
        item = make_item([2022, 2023])
        score = reranker._compute_cohort_score(item, 2022)
        assert score == 1.0

    def test_cohort_no_match_returns_0(self, reranker):
        """query_cohort_year=2022, cohort_years=[2021] -> 0.0"""
        item = make_item([2021])
        score = reranker._compute_cohort_score(item, 2022)
        assert score == 0.0

    def test_no_metadata_returns_neutral(self, reranker):
        """query_cohort_year=2022, cohort_years=None (no metadata) -> 0.5"""
        item = make_item(None)
        score = reranker._compute_cohort_score(item, 2022)
        assert score == 0.5

    def test_no_query_cohort_returns_neutral(self, reranker):
        """query_cohort_year=None (no cohort in query) -> 0.5 regardless of item"""
        item = make_item([2022])
        score = reranker._compute_cohort_score(item, None)
        assert score == 0.5


# ---------------------------------------------------------------------------
# Regression: use_cohort_boost=False preserves original 2-weight formula
# ---------------------------------------------------------------------------

class TestCohortBoostDisabledRegression:
    """
    When use_cohort_boost=False, rerank_with_temporal_boost must produce
    identical results whether or not query_cohort_year is set.
    """

    @pytest.fixture
    def reranker_with_fake_scores(self):
        """Reranker with mocked compute_scores and calculate_temporal_score."""
        with patch("agent.clients.reranker.settings") as mock_settings:
            mock_settings.reranker_base_url = "http://fake-reranker"
            mock_settings.reranker.default_model = "fake-model"
            mock_settings.reranker.use_fp16 = False
            mock_settings.use_cohort_boost = False
            temporal = MagicMock()
            temporal.recency_weight = 0.3
            temporal.semantic_weight_cohort = 0.55
            temporal.temporal_weight_cohort = 0.20
            temporal.cohort_weight = 0.25
            mock_settings.temporal = temporal
            from agent.clients.reranker import Reranker
            r = Reranker()

        r.compute_scores = MagicMock(return_value=[0.8, 0.6])
        r.calculate_temporal_score = MagicMock(side_effect=lambda item, _date: 0.5)
        return r

    def test_cohort_year_ignored_when_boost_disabled(self, reranker_with_fake_scores):
        """
        With use_cohort_boost=False, passing query_cohort_year=2022 must
        produce the same score as passing query_cohort_year=None.
        """
        items = [make_item([2022]), make_item([2021])]
        query = "test query"

        with patch("agent.clients.reranker.settings") as mock_settings:
            mock_settings.use_cohort_boost = False
            temporal = MagicMock()
            temporal.recency_weight = 0.3
            mock_settings.temporal = temporal

            result_with_cohort = reranker_with_fake_scores.rerank_with_temporal_boost(
                query, items, query_cohort_year=2022
            )
            result_without_cohort = reranker_with_fake_scores.rerank_with_temporal_boost(
                query, items, query_cohort_year=None
            )

        scores_with = [score for _, score in result_with_cohort]
        scores_without = [score for _, score in result_without_cohort]

        assert scores_with == scores_without, (
            "use_cohort_boost=False must ignore query_cohort_year entirely"
        )
