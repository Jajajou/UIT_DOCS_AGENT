"""Tests for citation URL resolution in agent3_response_generation._extract_references."""
import pytest
from unittest.mock import patch
from agent.agents.agent3_response_generation import _extract_references


def _make_chunk(file_path="firecrawl/data/daa/pdf/test.pdf", doc_num="108/QD-DHCNTT", content="Test content"):
    return {
        "file_path": file_path,
        "content": content,
        "metadata": {"document_number": doc_num},
    }


@patch("agent.agents.agent3_response_generation.get_url")
def test_extract_references_resolves_http_url(mock_get_url):
    mock_get_url.return_value = "https://daa.uit.edu.vn/sites/daa/files/test.pdf"
    chunks = [(_make_chunk(), 0.8)]
    refs = _extract_references(chunks)
    assert len(refs) == 1
    assert refs[0]["url"] == "https://daa.uit.edu.vn/sites/daa/files/test.pdf"


@patch("agent.agents.agent3_response_generation.get_url")
def test_extract_references_fallback_to_file_path(mock_get_url):
    mock_get_url.return_value = None
    chunks = [(_make_chunk(), 0.8)]
    refs = _extract_references(chunks)
    assert len(refs) == 1
    assert refs[0]["url"] == "firecrawl/data/daa/pdf/test.pdf"


@patch("agent.agents.agent3_response_generation.get_url")
def test_extract_references_no_file_path(mock_get_url):
    chunk = {"content": "test", "metadata": {}}
    refs = _extract_references([(chunk, 0.8)])
    assert len(refs) == 0


@patch("agent.agents.agent3_response_generation.get_url")
def test_extract_references_deduplicates(mock_get_url):
    mock_get_url.return_value = "https://example.com/test.pdf"
    chunks = [(_make_chunk(), 0.9), (_make_chunk(), 0.7)]
    refs = _extract_references(chunks)
    assert len(refs) == 1


@patch("agent.agents.agent3_response_generation.get_url")
def test_extract_references_filters_low_score(mock_get_url):
    mock_get_url.return_value = "https://example.com/test.pdf"
    chunks = [(_make_chunk(), 0.2)]
    refs = _extract_references(chunks)
    assert len(refs) == 0
