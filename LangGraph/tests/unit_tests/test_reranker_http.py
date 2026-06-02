"""
Unit tests for HTTP reranker mode in MultiSourceReranker.

Tests compute_scores() when reranker_base_url is set (HTTP mode).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestComputeScoresHTTP:
    """Tests for Reranker.compute_scores() in HTTP mode."""

    @pytest.fixture
    def reranker(self):
        with patch("agent.clients.reranker.settings") as mock_settings:
            mock_settings.reranker_base_url = "http://fake-reranker:8001"
            mock_settings.reranker.default_model = "fake-model"
            mock_settings.reranker.use_fp16 = False
            from agent.clients.reranker import Reranker
            r = Reranker()
        return r

    def test_http_mode_returns_scores(self, reranker):
        """HTTP mode: response data list is parsed into float scores."""
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "results": [
                {"index": 0, "relevance_score": 0.9},
                {"index": 1, "relevance_score": 0.3}
            ]
        }
        with patch("agent.clients.reranker.settings") as mock_settings:
            mock_settings.reranker_base_url = "http://fake-reranker:8001"
            mock_settings.reranker.default_model = "fake-model"
            with patch("requests.post", return_value=fake_response):
                scores = reranker.compute_scores("query", ["doc1", "doc2"])

        assert scores == [0.9, 0.3]

    def test_http_mode_raises_on_http_error(self, reranker):
        """HTTP mode: non-2xx response raises an exception."""
        import requests

        fake_response = MagicMock()
        fake_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")

        with patch("agent.clients.reranker.settings") as mock_settings:
            mock_settings.reranker_base_url = "http://fake-reranker:8001"
            mock_settings.reranker.default_model = "fake-model"
            with patch("requests.post", return_value=fake_response):
                with pytest.raises(requests.HTTPError):
                    reranker.compute_scores("query", ["doc1"])

    def test_empty_texts_raises_before_http_call(self, reranker):
        """Empty texts list raises RuntimeError before any HTTP call is made."""
        with patch("agent.clients.reranker.settings") as mock_settings:
            mock_settings.reranker_base_url = "http://fake-reranker:8001"
            mock_settings.reranker.default_model = "fake-model"
            with patch("requests.post") as mock_post:
                with pytest.raises(RuntimeError, match="Texts empty"):
                    reranker.compute_scores("query", [])
                mock_post.assert_not_called()
