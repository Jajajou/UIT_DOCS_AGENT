"""Unit tests for agent utility functions."""

import pytest
from langchain_core.messages import HumanMessage, AIMessage

from agent.utils import strip_think_tags, content_to_text, get_last_human_message


class TestStripThinkTags:
    def test_strips_single_think_block(self):
        content = "<think>chain of thought here</think>actual answer"
        assert strip_think_tags(content) == "actual answer"

    def test_strips_multiline_think_block(self):
        content = "<think>\nline1\nline2\n</think>\n{\"key\": \"value\"}"
        assert strip_think_tags(content) == "{\"key\": \"value\"}"

    def test_no_think_tags_unchanged(self):
        content = "plain response text"
        assert strip_think_tags(content) == "plain response text"

    def test_empty_think_block(self):
        content = "<think></think>answer"
        assert strip_think_tags(content) == "answer"

    def test_multiple_think_blocks(self):
        content = "<think>a</think>middle<think>b</think>end"
        assert strip_think_tags(content) == "middleend"


class TestContentToText:
    def test_string_input(self):
        assert content_to_text("  hello  ") == "hello"

    def test_list_with_text_parts(self):
        content = [{"type": "text", "text": "part1"}, {"type": "text", "text": "part2"}]
        assert content_to_text(content) == "part1 part2"

    def test_list_skips_non_text_parts(self):
        content = [{"type": "image_url", "url": "x"}, {"type": "text", "text": "hi"}]
        assert content_to_text(content) == "hi"

    def test_empty_list(self):
        assert content_to_text([]) == ""

    def test_none_input(self):
        assert content_to_text(None) == ""


class TestGetLastHumanMessage:
    def test_returns_last_human_message(self):
        msgs = [HumanMessage(content="first"), AIMessage(content="reply"), HumanMessage(content="second")]
        result = get_last_human_message(msgs)
        assert result.content == "second"

    def test_returns_none_when_no_human_message(self):
        msgs = [AIMessage(content="ai only")]
        assert get_last_human_message(msgs) is None

    def test_empty_list(self):
        assert get_last_human_message([]) is None

    def test_single_human_message(self):
        msgs = [HumanMessage(content="query")]
        result = get_last_human_message(msgs)
        assert result.content == "query"
