"""
Unit tests for core/prompts.py.

Covers:
- PROMPTS dict not empty
- get_prompt: returns string, handles missing key
- format_prompt: variable substitution, missing variable raises
"""

from __future__ import annotations

import pytest

from agent.core.prompts import PROMPTS, METADATA_PROMPTS, get_prompt, format_prompt


class TestPromptsDict:

    def test_prompts_not_empty(self):
        assert len(PROMPTS) > 0

    def test_metadata_prompts_not_empty(self):
        assert len(METADATA_PROMPTS) > 0

    def test_query_understanding_system_exists(self):
        assert "query_understanding_system" in PROMPTS

    def test_query_understanding_is_string(self):
        assert isinstance(PROMPTS["query_understanding_system"], str)

    def test_metadata_document_number_exists(self):
        assert "document_number" in METADATA_PROMPTS


class TestGetPrompt:

    def test_existing_key_returns_string(self):
        result = get_prompt("query_understanding_system")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_missing_key_returns_empty_string(self):
        result = get_prompt("nonexistent_prompt_key_xyz")
        assert result == ""

    def test_prompt_contains_expected_content(self):
        result = get_prompt("query_understanding_system")
        # Query understanding prompt should mention JSON or query analysis
        assert any(kw in result.lower() for kw in ["json", "query", "phân tích", "câu hỏi"])


class TestFormatPrompt:

    def test_variable_substitution(self):
        template = "Tên file: {filename}\nNội dung: {context}"
        result = format_prompt(template, filename="test.pdf", context="nội dung văn bản")
        assert "test.pdf" in result
        assert "nội dung văn bản" in result
        assert "{filename}" not in result

    def test_no_variables_unchanged(self):
        template = "No variables here."
        assert format_prompt(template) == "No variables here."

    def test_missing_variable_raises(self):
        template = "Hello {name}, you are {age} years old."
        with pytest.raises((KeyError, IndexError)):
            format_prompt(template, name="Alice")

    def test_metadata_prompt_document_number_format(self):
        result = format_prompt(
            METADATA_PROMPTS["document_number"],
            filename="108-qd-dhcntt.pdf",
            context="Quyết định số 108/QĐ-ĐHCNTT ngày 01/01/2024",
        )
        assert "108-qd-dhcntt.pdf" in result
        assert "108/QĐ-ĐHCNTT" in result
