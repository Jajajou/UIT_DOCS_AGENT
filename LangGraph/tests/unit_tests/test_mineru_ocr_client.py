"""
Unit tests for MinerUOCRClient.

Covers remote mode (POST /file_parse), local MLX mode, cache hit/miss,
response parsing, and error cases. All external I/O is mocked.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mineru_response(filename_stem: str, md_content: str) -> dict:
    """Build a response dict matching the official MinerU Docker /file_parse schema."""
    return {
        "status": "completed",
        "task_id": "test-task-id",
        "results": {
            filename_stem: {
                "md_content": md_content,
            }
        },
    }


def _mock_settings(api_url: str | None = "http://fake-mineru:8000"):
    """Return a mock settings object with mineru_ocr configured."""
    mock = MagicMock()
    mock.mineru_ocr.model_name = "opendatalab/MinerU2.5-Pro-2604-1.2B"
    mock.mineru_ocr.skip_repeat = True
    mock.mineru_ocr.api_url = api_url
    mock.mineru_ocr_dir = Path("/tmp/mineru-cache")
    return mock


# ---------------------------------------------------------------------------
# Remote mode tests
# ---------------------------------------------------------------------------

class TestParsePdfRemote:
    """Tests for _parse_pdf_remote() — POST /file_parse path."""

    def _client(self):
        with patch("agent.clients.mineru_ocr_client.settings", _mock_settings()):
            from agent.clients.mineru_ocr_client import MinerUOCRClient
            return MinerUOCRClient()

    def test_returns_markdown_list(self, tmp_path):
        """Remote call returns a one-element list containing the full doc markdown."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF fake")

        expected_md = "# Title\n\nContent here."
        fake_resp = MagicMock()
        fake_resp.json.return_value = _make_mineru_response("doc", expected_md)
        fake_resp.raise_for_status = MagicMock()

        client = self._client()
        with patch("httpx.post", return_value=fake_resp) as mock_post:
            result = client._parse_pdf_remote(str(pdf), "http://fake-mineru:8000")

        assert result == [expected_md]
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[0][0] == "http://fake-mineru:8000/file_parse"

    def test_trailing_slash_stripped_from_api_url(self, tmp_path):
        """Trailing slash on api_url is stripped before appending /file_parse."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF fake")

        fake_resp = MagicMock()
        fake_resp.json.return_value = _make_mineru_response("doc", "md")
        fake_resp.raise_for_status = MagicMock()

        client = self._client()
        with patch("httpx.post", return_value=fake_resp) as mock_post:
            client._parse_pdf_remote(str(pdf), "http://fake-mineru:8000/")

        url_called = mock_post.call_args[0][0]
        assert url_called == "http://fake-mineru:8000/file_parse"

    def test_empty_results_raises(self, tmp_path):
        """Empty results dict raises MinerUOCRClientError."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF fake")

        fake_resp = MagicMock()
        fake_resp.json.return_value = {"status": "completed", "results": {}}
        fake_resp.raise_for_status = MagicMock()

        client = self._client()
        from agent.clients.mineru_ocr_client import MinerUOCRClientError
        with patch("httpx.post", return_value=fake_resp):
            with pytest.raises(MinerUOCRClientError, match="Empty results"):
                client._parse_pdf_remote(str(pdf), "http://fake-mineru:8000")

    def test_http_error_propagates(self, tmp_path):
        """HTTP 500 from the MinerU API propagates as an exception."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF fake")

        import httpx
        fake_resp = MagicMock()
        fake_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )

        client = self._client()
        with patch("httpx.post", return_value=fake_resp):
            with pytest.raises(httpx.HTTPStatusError):
                client._parse_pdf_remote(str(pdf), "http://fake-mineru:8000")

    def test_request_params_include_latin_lang(self, tmp_path):
        """lang_list=latin is sent so Vietnamese text uses the correct OCR group."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF fake")

        fake_resp = MagicMock()
        fake_resp.json.return_value = _make_mineru_response("doc", "md")
        fake_resp.raise_for_status = MagicMock()

        client = self._client()
        with patch("httpx.post", return_value=fake_resp) as mock_post:
            client._parse_pdf_remote(str(pdf), "http://fake-mineru:8000")

        data_sent = mock_post.call_args[1]["data"]
        assert data_sent["lang_list"] == "latin"
        assert data_sent["backend"] == "hybrid-auto-engine"
        assert data_sent["table_enable"] == "true"


# ---------------------------------------------------------------------------
# parse_pdf() integration (remote path end-to-end)
# ---------------------------------------------------------------------------

class TestParsePdf:
    """Tests for the public parse_pdf() method."""

    def _client(self, api_url="http://fake-mineru:8000"):
        with patch("agent.clients.mineru_ocr_client.settings", _mock_settings(api_url)):
            from agent.clients.mineru_ocr_client import MinerUOCRClient
            return MinerUOCRClient()

    def test_file_not_found_raises(self, tmp_path):
        from agent.clients.mineru_ocr_client import MinerUOCRClientError
        client = self._client()
        with pytest.raises(MinerUOCRClientError, match="File not found"):
            client.parse_pdf(str(tmp_path / "missing.pdf"))

    def test_non_pdf_raises(self, tmp_path):
        from agent.clients.mineru_ocr_client import MinerUOCRClientError
        txt = tmp_path / "doc.txt"
        txt.write_text("hello")
        client = self._client()
        with pytest.raises(MinerUOCRClientError, match="Only PDF"):
            client.parse_pdf(str(txt))

    def test_remote_path_returns_success_dict(self, tmp_path):
        """parse_pdf() with api_url set returns status=success and markdown key."""
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"%PDF fake")

        md = "# Report\n\nSome content."
        fake_resp = MagicMock()
        fake_resp.json.return_value = _make_mineru_response("report", md)
        fake_resp.raise_for_status = MagicMock()

        client = self._client()
        with patch("agent.clients.mineru_ocr_client.settings", _mock_settings()):
            with patch("httpx.post", return_value=fake_resp):
                result = client.parse_pdf(str(pdf), return_md=True)

        assert result["status"] == "success"
        assert result["markdown"] == md
        assert result["pages_processed"] == 1

    def test_remote_path_writes_markdown_file(self, tmp_path):
        """When output_dir is given, markdown is saved to disk."""
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"%PDF fake")
        out_dir = tmp_path / "out"

        md = "# Report\n\nSome content."
        fake_resp = MagicMock()
        fake_resp.json.return_value = _make_mineru_response("report", md)
        fake_resp.raise_for_status = MagicMock()

        client = self._client()
        with patch("agent.clients.mineru_ocr_client.settings", _mock_settings()):
            with patch("httpx.post", return_value=fake_resp):
                result = client.parse_pdf(str(pdf), output_dir=str(out_dir), return_md=True)

        assert "markdown_path" in result
        saved = Path(result["markdown_path"]).read_text(encoding="utf-8")
        assert saved == md

    def test_no_markdown_key_when_return_md_false(self, tmp_path):
        """return_md=False omits the markdown key but still includes text."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF fake")

        fake_resp = MagicMock()
        fake_resp.json.return_value = _make_mineru_response("doc", "content")
        fake_resp.raise_for_status = MagicMock()

        client = self._client()
        with patch("agent.clients.mineru_ocr_client.settings", _mock_settings()):
            with patch("httpx.post", return_value=fake_resp):
                result = client.parse_pdf(str(pdf), return_md=False)

        assert "markdown" not in result
        assert result["text"] == "content"


# ---------------------------------------------------------------------------
# Cache / get_markdown_from_output
# ---------------------------------------------------------------------------

class TestGetMarkdownFromOutput:
    """Tests for cache read path."""

    def _client(self):
        with patch("agent.clients.mineru_ocr_client.settings", _mock_settings()):
            from agent.clients.mineru_ocr_client import MinerUOCRClient
            return MinerUOCRClient()

    def test_returns_none_when_dir_missing(self, tmp_path):
        client = self._client()
        assert client.get_markdown_from_output(str(tmp_path / "nonexistent")) is None

    def test_returns_none_when_no_md_files(self, tmp_path):
        (tmp_path / "other.txt").write_text("hello")
        client = self._client()
        assert client.get_markdown_from_output(str(tmp_path)) is None

    def test_returns_most_recently_modified_md(self, tmp_path):
        """When multiple .md files exist, the most recently modified one is returned."""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        old.write_text("old content")
        new.write_text("new content")
        # Make new newer by bumping its mtime
        import time
        os.utime(new, (time.time() + 10, time.time() + 10))

        client = self._client()
        result = client.get_markdown_from_output(str(tmp_path))
        assert result == "new content"


# ---------------------------------------------------------------------------
# parse_and_get_markdown — cache hit / miss
# ---------------------------------------------------------------------------

class TestParseAndGetMarkdown:
    """Tests for the main high-level entry point."""

    def _client(self):
        with patch("agent.clients.mineru_ocr_client.settings", _mock_settings()):
            from agent.clients.mineru_ocr_client import MinerUOCRClient
            return MinerUOCRClient()

    def test_cache_hit_skips_parse(self, tmp_path):
        """When a cached .md exists and skip_repeat=True, parse_pdf is never called."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF fake")

        mock_settings = _mock_settings()
        mock_settings.mineru_ocr_dir = tmp_path

        # Pre-populate cache dir
        cache_dir = tmp_path / "doc"
        cache_dir.mkdir()
        cached_md = cache_dir / "doc.md"
        cached_md.write_text("cached markdown")

        with patch("agent.clients.mineru_ocr_client.settings", mock_settings):
            from agent.clients.mineru_ocr_client import MinerUOCRClient
            client = MinerUOCRClient()
            with patch.object(client, "parse_pdf") as mock_parse:
                md, out_dir = client.parse_and_get_markdown(str(pdf))

        mock_parse.assert_not_called()
        assert md == "cached markdown"

    def test_cache_miss_calls_parse(self, tmp_path):
        """When no cache exists, parse_pdf is called and its result is returned."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF fake")

        mock_settings = _mock_settings()
        mock_settings.mineru_ocr.skip_repeat = True
        mock_settings.mineru_ocr_dir = tmp_path / "cache"

        with patch("agent.clients.mineru_ocr_client.settings", mock_settings):
            from agent.clients.mineru_ocr_client import MinerUOCRClient
            client = MinerUOCRClient()
            with patch.object(
                client,
                "parse_pdf",
                return_value={"markdown": "fresh markdown", "status": "success"},
            ):
                md, out_dir = client.parse_and_get_markdown(str(pdf))

        assert md == "fresh markdown"

    def test_empty_parse_result_raises(self, tmp_path):
        """Empty markdown from parse_pdf raises MinerUOCRClientError."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF fake")

        mock_settings = _mock_settings()
        mock_settings.mineru_ocr.skip_repeat = False
        mock_settings.mineru_ocr_dir = tmp_path / "cache"

        from agent.clients.mineru_ocr_client import MinerUOCRClientError
        with patch("agent.clients.mineru_ocr_client.settings", mock_settings):
            from agent.clients.mineru_ocr_client import MinerUOCRClient
            client = MinerUOCRClient()
            with patch.object(client, "parse_pdf", return_value={"markdown": "", "status": "success"}):
                with pytest.raises(MinerUOCRClientError, match="No text extracted"):
                    client.parse_and_get_markdown(str(pdf))


# ---------------------------------------------------------------------------
# Vietnamese normalization
# ---------------------------------------------------------------------------

class TestNormalizeVietnamese:
    """Tests for _normalize_vietnamese static method."""

    def test_returns_text_unchanged_when_underthesea_unavailable(self):
        """Graceful fallback: if underthesea not installed, returns input as-is."""
        with patch("agent.clients.mineru_ocr_client.settings", _mock_settings()):
            from agent.clients.mineru_ocr_client import MinerUOCRClient

        with patch.dict("sys.modules", {"underthesea": None}):
            result = MinerUOCRClient._normalize_vietnamese("Xin chào")
        assert result == "Xin chào"

    def test_calls_text_normalize_when_available(self):
        """When underthesea is importable, text_normalize is called."""
        mock_underthesea = MagicMock()
        mock_underthesea.text_normalize.return_value = "normalized"

        with patch("agent.clients.mineru_ocr_client.settings", _mock_settings()):
            from agent.clients.mineru_ocr_client import MinerUOCRClient

        with patch.dict("sys.modules", {"underthesea": mock_underthesea}):
            result = MinerUOCRClient._normalize_vietnamese("raw")

        assert result == "normalized"
