"""
Unit tests for amendment override in rerank_with_temporal_boost().

When use_amendment_override=True, any item with a non-empty amended_by field
in its metadata has its temporal score replaced with amendment_override_score.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_item(amended_by=None) -> dict:
    return {"content": "doc text", "metadata": {"amended_by": amended_by or []}}


def _make_reranker(use_amendment_override: bool = True):
    mock_settings = MagicMock()
    # Non-None URL skips FlagEmbedding import in _load_model; compute_scores is mocked anyway.
    mock_settings.reranker_base_url = "http://fake-reranker:8001"
    mock_settings.reranker.default_model = "fake-model"
    mock_settings.reranker.use_fp16 = False
    mock_settings.reranker.batch_size = 32
    mock_settings.reranker.normalize_scores = True
    mock_settings.reranker.top_n_for_confidence = 5
    mock_settings.use_cohort_boost = False
    mock_settings.use_amendment_override = use_amendment_override
    # quality_penalties is a dict
    mock_settings.temporal.quality_penalties = {"amendment_override_score": 0.3}
    mock_settings.temporal.recency_weight = 0.3
    return mock_settings


class TestAmendmentOverride:
    """Tests for amendment override in rerank_with_temporal_boost."""

    def _run_rerank(self, items, use_amendment_override, semantic_scores=None):
        mock_settings = _make_reranker(use_amendment_override)
        if semantic_scores is None:
            semantic_scores = [0.8] * len(items)

        with patch("agent.clients.reranker.settings", mock_settings):
            from agent.clients.reranker import Reranker
            r = Reranker()
            with patch.object(r, "compute_scores", return_value=semantic_scores):
                with patch.object(r, "calculate_temporal_score", return_value=1.0):
                    result = r.rerank_with_temporal_boost("query", items)
        return result

    def test_superseded_item_gets_override_score(self):
        """Item with amended_by populated gets amendment_override_score applied."""
        old_doc = _make_item(amended_by=["doc-new-id"])
        new_doc = _make_item(amended_by=[])

        # Both get semantic=0.8, temporal=1.0 before override
        result = self._run_rerank([old_doc, new_doc], use_amendment_override=True)

        items_out = [item for item, _ in result]
        scores_out = [score for _, score in result]

        old_idx = items_out.index(old_doc)
        new_idx = items_out.index(new_doc)

        # old_doc: 0.7 * 0.8 + 0.3 * 0.3 = 0.56 + 0.09 = 0.65
        # new_doc: 0.7 * 0.8 + 0.3 * 1.0 = 0.56 + 0.30 = 0.86
        assert scores_out[new_idx] > scores_out[old_idx]

    def test_override_disabled_does_not_penalise(self):
        """When use_amendment_override=False, amended_by has no effect on scores."""
        old_doc = _make_item(amended_by=["doc-new-id"])
        new_doc = _make_item(amended_by=[])

        result = self._run_rerank([old_doc, new_doc], use_amendment_override=False)
        scores_out = dict(zip([id(item) for item, _ in result], [s for _, s in result]))

        # Both should get identical scores (same semantic=0.8, temporal=1.0)
        all_scores = [s for _, s in result]
        assert len(set(round(s, 6) for s in all_scores)) == 1

    def test_item_without_amended_by_unaffected(self):
        """Item with no amended_by field is not penalised by override."""
        doc = {"content": "doc text", "metadata": {}}  # no amended_by key at all

        result = self._run_rerank([doc], use_amendment_override=True)
        _, score = result[0]

        # temporal=1.0 unmodified, semantic=0.8 → 0.7*0.8 + 0.3*1.0 = 0.86
        assert score == pytest.approx(0.86, abs=1e-6)

    def test_empty_amended_by_list_not_penalised(self):
        """Empty amended_by list is treated as not amended (neutral)."""
        doc = _make_item(amended_by=[])

        result = self._run_rerank([doc], use_amendment_override=True)
        _, score = result[0]

        # temporal stays 1.0, score = 0.7*0.8 + 0.3*1.0 = 0.86
        assert score == pytest.approx(0.86, abs=1e-6)
