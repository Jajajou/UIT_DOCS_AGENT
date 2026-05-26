"""
Unit tests for config.py and utils.py utility functions.

Covers:
- get_attr_safe: BaseModel, dict, nested, None, default
- set_config_overrides / reset_config_overrides: thread-local override
- find_urls_by_filename: case-insensitive match, no match, percent-encoding
- extract_pdf_links: URL extraction from text, deduplication
- strip_think_tags, content_to_text, get_last_human_message (extended edge cases)
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

from agent.config import get_attr_safe, set_config_overrides, reset_config_overrides, settings
from agent.utils import (
    find_urls_by_filename,
    extract_pdf_links,
    strip_think_tags,
    content_to_text,
    get_last_human_message,
)


# ---------------------------------------------------------------------------
# get_attr_safe
# ---------------------------------------------------------------------------

class _Inner(BaseModel):
    value: int = 42

class _Outer(BaseModel):
    name: str = "test"
    inner: _Inner = _Inner()


class TestGetAttrSafe:

    def test_simple_attr_from_pydantic(self):
        obj = _Outer()
        assert get_attr_safe(obj, "name") == "test"

    def test_nested_attr_from_pydantic(self):
        obj = _Outer()
        assert get_attr_safe(obj, "inner.value") == 42

    def test_simple_attr_from_dict(self):
        d = {"key": "val"}
        assert get_attr_safe(d, "key") == "val"

    def test_nested_attr_from_dict(self):
        d = {"a": {"b": 99}}
        assert get_attr_safe(d, "a.b") == 99

    def test_missing_attr_returns_default(self):
        obj = _Outer()
        assert get_attr_safe(obj, "nonexistent", "fallback") == "fallback"

    def test_missing_nested_returns_default(self):
        d = {"a": {"b": 1}}
        assert get_attr_safe(d, "a.c", 0) == 0

    def test_none_obj_returns_default(self):
        assert get_attr_safe(None, "anything", "x") == "x"

    def test_deep_nesting(self):
        d = {"a": {"b": {"c": "deep"}}}
        assert get_attr_safe(d, "a.b.c") == "deep"

    def test_non_model_non_dict_returns_default(self):
        assert get_attr_safe(42, "attr", "default") == "default"

    def test_default_is_none_when_not_specified(self):
        assert get_attr_safe({}, "missing") is None


# ---------------------------------------------------------------------------
# set_config_overrides / reset_config_overrides
# ---------------------------------------------------------------------------

class TestConfigOverrides:

    def test_override_use_cohort_boost(self):
        token = set_config_overrides({"use_cohort_boost": False})
        try:
            assert settings.use_cohort_boost is False
        finally:
            reset_config_overrides(token)

    def test_reset_restores_original(self):
        original = settings.use_cohort_boost
        token = set_config_overrides({"use_cohort_boost": not original})
        reset_config_overrides(token)
        assert settings.use_cohort_boost == original

    def test_override_temporal_scoring(self):
        token = set_config_overrides({"use_temporal_scoring": False})
        try:
            assert settings.use_temporal_scoring is False
        finally:
            reset_config_overrides(token)

    def test_override_amendment(self):
        token = set_config_overrides({"use_amendment_override": True})
        try:
            assert settings.use_amendment_override is True
        finally:
            reset_config_overrides(token)

    def test_empty_override_does_not_change_settings(self):
        original_cohort = settings.use_cohort_boost
        token = set_config_overrides({})
        try:
            assert settings.use_cohort_boost == original_cohort
        finally:
            reset_config_overrides(token)


# ---------------------------------------------------------------------------
# find_urls_by_filename
# ---------------------------------------------------------------------------

class TestFindUrlsByFilename:

    def test_exact_match(self):
        urls = ["https://example.com/path/to/file.pdf"]
        assert find_urls_by_filename(urls, "file.pdf") == "https://example.com/path/to/file.pdf"

    def test_case_insensitive_match(self):
        urls = ["https://example.com/FILE.PDF"]
        assert find_urls_by_filename(urls, "file.pdf") == "https://example.com/FILE.PDF"

    def test_case_sensitive_no_match(self):
        urls = ["https://example.com/FILE.PDF"]
        result = find_urls_by_filename(urls, "file.pdf", case_insensitive=False)
        assert result is None

    def test_no_match_returns_none(self):
        urls = ["https://example.com/other.pdf"]
        assert find_urls_by_filename(urls, "file.pdf") is None

    def test_percent_encoded_filename(self):
        urls = ["https://example.com/my%20file.pdf"]
        result = find_urls_by_filename(urls, "my file.pdf", decode_percent_escapes=True)
        assert result == "https://example.com/my%20file.pdf"

    def test_ignores_query_string(self):
        urls = ["https://example.com/doc.pdf?v=2"]
        assert find_urls_by_filename(urls, "doc.pdf") == "https://example.com/doc.pdf?v=2"

    def test_empty_list_returns_none(self):
        assert find_urls_by_filename([], "file.pdf") is None


# ---------------------------------------------------------------------------
# extract_pdf_links
# ---------------------------------------------------------------------------

class TestExtractPdfLinks:

    def test_single_link(self):
        text = "Xem tại https://uit.edu.vn/files/doc.pdf để biết thêm."
        result = extract_pdf_links(text)
        assert result == ["https://uit.edu.vn/files/doc.pdf"]

    def test_multiple_links(self):
        text = "https://a.com/x.pdf và https://b.com/y.pdf"
        result = extract_pdf_links(text)
        assert len(result) == 2

    def test_deduplication(self):
        text = "https://a.com/x.pdf và https://a.com/x.pdf"
        result = extract_pdf_links(text)
        assert len(result) == 1

    def test_no_links_returns_empty(self):
        assert extract_pdf_links("không có link nào") == []

    def test_non_pdf_links_excluded(self):
        text = "https://a.com/x.html và https://a.com/y.pdf"
        result = extract_pdf_links(text)
        assert result == ["https://a.com/y.pdf"]

    def test_order_preserved(self):
        text = "https://a.com/a.pdf https://b.com/b.pdf https://c.com/c.pdf"
        result = extract_pdf_links(text)
        assert result[0].endswith("/a.pdf")
        assert result[1].endswith("/b.pdf")


# ---------------------------------------------------------------------------
# strip_think_tags (edge cases beyond existing tests)
# ---------------------------------------------------------------------------

class TestStripThinkTagsExtended:

    def test_no_think_tags_unchanged(self):
        assert strip_think_tags("Hello world") == "Hello world"

    def test_nested_content_removed(self):
        result = strip_think_tags("<think>some reasoning\nmultiline</think>answer")
        assert result == "answer"
        assert "<think>" not in result

    def test_multiple_think_blocks(self):
        text = "<think>first</think>data<think>second</think>more"
        result = strip_think_tags(text)
        assert result == "datamore"

    def test_empty_string(self):
        assert strip_think_tags("") == ""

    def test_only_think_tag_returns_empty(self):
        result = strip_think_tags("<think>all thinking</think>")
        assert result == ""


# ---------------------------------------------------------------------------
# content_to_text (edge cases)
# ---------------------------------------------------------------------------

class TestContentToTextExtended:

    def test_list_with_multiple_text_parts(self):
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "world"},
        ]
        assert content_to_text(content) == "Hello world"

    def test_list_skips_non_text_parts(self):
        content = [
            {"type": "image_url", "image_url": "http://x.com/img.jpg"},
            {"type": "text", "text": "caption"},
        ]
        assert content_to_text(content) == "caption"

    def test_empty_list_returns_empty(self):
        assert content_to_text([]) == ""

    def test_non_string_non_list_returns_empty(self):
        assert content_to_text(42) == ""


# ---------------------------------------------------------------------------
# get_last_human_message (edge cases)
# ---------------------------------------------------------------------------

class TestGetLastHumanMessageExtended:

    def test_returns_last_human_not_first(self):
        msgs = [
            HumanMessage(content="first"),
            AIMessage(content="ai response"),
            HumanMessage(content="second"),
        ]
        msg = get_last_human_message(msgs)
        assert msg.content == "second"

    def test_no_human_returns_none(self):
        msgs = [AIMessage(content="only ai")]
        assert get_last_human_message(msgs) is None

    def test_empty_list_returns_none(self):
        assert get_last_human_message([]) is None

    def test_none_list_returns_none(self):
        assert get_last_human_message(None) is None
