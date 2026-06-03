"""
Unit tests for Reranker temporal scoring and aggregate confidence.

Tests calculate_temporal_score and calculate_aggregate_confidence in isolation
(no model load needed — we patch reranker_base_url and avoid FlagEmbedding).
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch

# Force HTTP mode so Reranker.__init__ skips FlagEmbedding load
os.environ.setdefault("RERANKER_BASE_URL", "http://localhost:8001")


def _make_reranker():
    with patch("agent.clients.reranker.settings") as mock_settings:
        mock_settings.reranker_base_url = "http://localhost:8001"
        mock_settings.reranker.default_model = "test-model"
        mock_settings.reranker.use_fp16 = False
        mock_settings.reranker.top_n_for_confidence = 5
        mock_settings.reranker.batch_size = 8
        mock_settings.reranker.normalize_scores = True
        mock_settings.reranker.max_length = 512
        from agent.clients.reranker import Reranker
        r = Reranker.__new__(Reranker)
        r.config = mock_settings.reranker
        r._model = None
        return r


@pytest.fixture
def reranker():
    return _make_reranker()


def _item(metadata: dict) -> dict:
    return {"content": "text", "metadata": metadata}


# ---------------------------------------------------------------------------
# calculate_temporal_score
# ---------------------------------------------------------------------------

class TestCalculateTemporalScore:

    def test_archived_returns_zero(self, reranker):
        item = _item({"is_archived": True})
        assert reranker.calculate_temporal_score(item, "2026-05-26") == 0.0

    def test_no_temporal_info_returns_neutral(self, reranker):
        item = _item({})
        score = reranker.calculate_temporal_score(item, "2026-05-26")
        assert score == 0.5

    def test_valid_current_doc_returns_high(self, reranker):
        item = _item({"valid_from": "2020-01-01", "valid_until": "2099-12-31", "amended_by": []})
        score = reranker.calculate_temporal_score(item, "2026-05-26")
        assert score >= 0.75

    def test_expired_long_ago_returns_low(self, reranker):
        item = _item({"valid_until": "2020-01-01"})
        score = reranker.calculate_temporal_score(item, "2026-05-26")
        assert score <= 0.2

    def test_expired_recently_returns_partial(self, reranker):
        item = _item({"valid_until": "2026-04-01"})
        score = reranker.calculate_temporal_score(item, "2026-05-26")
        assert 0.1 <= score <= 0.5

    def test_future_doc_not_yet_valid_returns_low(self, reranker):
        item = _item({"valid_from": "2030-01-01"})
        score = reranker.calculate_temporal_score(item, "2026-05-26")
        assert score == 0.3

    def test_recent_index_returns_high(self, reranker):
        item = _item({"indexed_at": "2026-05-20"})
        score = reranker.calculate_temporal_score(item, "2026-05-26")
        assert score == 1.0

    def test_old_index_decays(self, reranker):
        item = _item({"indexed_at": "2024-01-01"})
        score_2024 = reranker.calculate_temporal_score(item, "2026-05-26")
        item2 = _item({"indexed_at": "2026-05-01"})
        score_2026 = reranker.calculate_temporal_score(item2, "2026-05-26")
        assert score_2026 > score_2024

    def test_score_always_in_range(self, reranker):
        test_cases = [
            {"is_archived": True},
            {},
            {"valid_from": "2020-01-01"},
            {"valid_until": "2019-01-01"},
            {"valid_from": "2030-01-01"},
            {"indexed_at": "2020-06-01"},
        ]
        for meta in test_cases:
            score = reranker.calculate_temporal_score(_item(meta), "2026-05-26")
            assert 0.0 <= score <= 1.0, f"Out of range for {meta}: {score}"


# ---------------------------------------------------------------------------
# calculate_aggregate_confidence
# ---------------------------------------------------------------------------

class TestCalculateAggregateConfidence:

    def test_empty_scores_returns_zero(self, reranker):
        assert reranker.calculate_aggregate_confidence([]) == 0.0

    def test_perfect_scores_return_high(self, reranker):
        conf = reranker.calculate_aggregate_confidence([1.0, 1.0, 1.0])
        assert conf >= 0.9

    def test_zero_scores_return_low(self, reranker):
        conf = reranker.calculate_aggregate_confidence([0.0, 0.0, 0.0])
        assert conf <= 0.2

    def test_single_score_returns_correct(self, reranker):
        conf = reranker.calculate_aggregate_confidence([0.8])
        # 0.6*0.8 + 0.3*0.8 + 0.1*1.0 = 0.48+0.24+0.1 = 0.82
        assert abs(conf - 0.82) < 0.01

    def test_result_in_unit_interval(self, reranker):
        for scores in [[0.5, 0.6, 0.7], [0.1], [0.9, 0.95, 1.0]]:
            conf = reranker.calculate_aggregate_confidence(scores)
            assert 0.0 <= conf <= 1.0

    def test_top_n_limits_considered_scores(self, reranker):
        # With top_n=2, only top 2 scores matter
        conf_small = reranker.calculate_aggregate_confidence([1.0, 1.0, 0.0], top_n=2)
        conf_all = reranker.calculate_aggregate_confidence([1.0, 1.0, 0.0], top_n=3)
        # Small n should exclude the 0.0 and give higher result
        assert conf_small >= conf_all
