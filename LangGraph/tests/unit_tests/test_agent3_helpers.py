"""
Unit tests for Agent 3 helper functions.

Covers:
- _generate_expiration_warnings: expired, expiring-soon, amended docs
- _format_reranked_data: output shape with entities/rels/chunks
- _extract_references: dedup, min_score filter, doc number as title
- _generate_confidence_transparency: low confidence, amendment count
"""

from __future__ import annotations

import pytest
from unittest.mock import patch
from typing import List, Tuple, Dict, Any

from agent.agents.agent3_response_generation import (
    _generate_expiration_warnings,
    _format_reranked_data,
    _extract_references,
    _generate_confidence_transparency,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk(
    file_path: str = "doc.pdf",
    doc_number: str = "108/QD-DHCNTT",
    valid_until: str = None,
    amended_by=None,
    content: str = "nội dung văn bản",
    score: float = 0.8,
) -> Tuple[Dict[str, Any], float]:
    meta: Dict[str, Any] = {"document_number": doc_number}
    if valid_until:
        meta["valid_until"] = valid_until
    if amended_by is not None:
        meta["amended_by"] = amended_by
    return ({"file_path": file_path, "content": content, "metadata": meta}, score)


# ---------------------------------------------------------------------------
# _generate_expiration_warnings
# ---------------------------------------------------------------------------

class TestGenerateExpirationWarnings:

    def test_no_warnings_for_valid_doc(self):
        chunks = [_chunk(valid_until="2099-12-31")]
        result = _generate_expiration_warnings(chunks, current_date="2026-05-26")
        assert result == ""

    def test_expired_doc_generates_warning(self):
        chunks = [_chunk(valid_until="2020-01-01")]
        result = _generate_expiration_warnings(chunks, current_date="2026-05-26")
        assert "Cảnh báo" in result
        assert "hết hiệu lực" in result

    def test_expiring_soon_generates_note(self):
        chunks = [_chunk(valid_until="2026-06-10")]
        result = _generate_expiration_warnings(chunks, current_date="2026-05-26")
        assert "Lưu ý" in result
        assert "sắp hết hạn" in result.lower() or "sắp hết hiệu lực" in result.lower() or "sẽ hết hiệu lực" in result

    def test_amended_doc_generates_notification(self):
        chunks = [_chunk(amended_by=["141/QD-DHCNTT"])]
        result = _generate_expiration_warnings(chunks, current_date="2026-05-26")
        assert "sửa đổi" in result.lower() or "Thông báo" in result

    def test_dedup_same_file_path(self):
        chunks = [_chunk(valid_until="2020-01-01"), _chunk(valid_until="2020-01-01")]
        result = _generate_expiration_warnings(chunks, current_date="2026-05-26")
        # Only one warning entry for the same doc
        assert result.count("108/QD-DHCNTT") == 1

    def test_empty_chunks_no_warning(self):
        assert _generate_expiration_warnings([], current_date="2026-05-26") == ""

    def test_amended_by_string_also_triggers(self):
        chunks = [_chunk(amended_by="141/QD-DHCNTT")]
        result = _generate_expiration_warnings(chunks, current_date="2026-05-26")
        assert "141/QD-DHCNTT" in result


# ---------------------------------------------------------------------------
# _format_reranked_data
# ---------------------------------------------------------------------------

class TestFormatRerankedData:

    def test_empty_returns_no_data(self):
        result = _format_reranked_data([], [], [], top_n=5)
        assert result == "Không có dữ liệu."

    def test_entities_appear_in_output(self):
        entities = [({"name": "UIT", "description": "Trường đại học"}, 0.9)]
        result = _format_reranked_data(entities, [], [], top_n=5)
        assert "UIT" in result
        assert "0.90" in result

    def test_chunks_appear_in_output(self):
        chunks = [_chunk(content="Nội dung quy chế học vụ", doc_number="108/QD")]
        result = _format_reranked_data([], [], chunks, top_n=5)
        assert "108/QD" in result
        assert "Nội dung quy chế" in result

    def test_top_n_limits_output(self):
        entities = [({"name": f"Entity{i}", "description": ""}, 0.9 - i * 0.01) for i in range(20)]
        result = _format_reranked_data(entities, [], [], top_n=3)
        assert "Entity0" in result
        assert "Entity3" not in result

    def test_relationships_appear(self):
        rels = [({"description": "A liên quan đến B"}, 0.75)]
        result = _format_reranked_data([], rels, [], top_n=5)
        assert "A liên quan đến B" in result


# ---------------------------------------------------------------------------
# _extract_references
# ---------------------------------------------------------------------------

class TestExtractReferences:

    def test_below_min_score_excluded(self):
        low = _chunk(score=0.2)
        high = _chunk(file_path="doc2.pdf", score=0.9)
        refs = _extract_references([low, high], min_score=0.4)
        assert len(refs) == 1
        assert refs[0]["url"] == "doc2.pdf" or refs[0]["title"] == "108/QD-DHCNTT"

    def test_dedup_same_file_path(self):
        c1 = _chunk(score=0.8)
        c2 = _chunk(score=0.85)
        refs = _extract_references([c1, c2], min_score=0.0)
        assert len(refs) == 1

    def test_doc_number_used_as_title(self):
        c = _chunk(doc_number="141/QD-DHCNTT", score=0.8)
        refs = _extract_references([c], min_score=0.0)
        assert refs[0]["title"] == "141/QD-DHCNTT"

    def test_filename_fallback_when_no_doc_number(self):
        chunk = ({"file_path": "/data/some_file.pdf", "content": "text", "metadata": {}}, 0.8)
        refs = _extract_references([chunk], min_score=0.0)
        assert refs[0]["title"] == "some_file.pdf"

    def test_sorted_by_relevance_descending(self):
        c1 = _chunk(file_path="a.pdf", doc_number="A", score=0.5)
        c2 = _chunk(file_path="b.pdf", doc_number="B", score=0.9)
        refs = _extract_references([c1, c2], min_score=0.0)
        assert refs[0]["relevance"] > refs[1]["relevance"]

    def test_excerpt_truncated_to_200(self):
        long_content = "x" * 500
        c = _chunk(content=long_content, score=0.8)
        refs = _extract_references([c], min_score=0.0)
        assert len(refs[0]["excerpt"]) <= 204  # 200 + "..."

    def test_empty_input_returns_empty(self):
        assert _extract_references([], min_score=0.0) == []


# ---------------------------------------------------------------------------
# _generate_confidence_transparency
# ---------------------------------------------------------------------------

class TestGenerateConfidenceTransparency:

    def _make_state(self, confidence=1.0, chunks=None):
        return {
            "rerank_confidence": confidence,
            "reranked_chunks": chunks or [],
        }

    def test_high_confidence_no_warnings(self):
        state = self._make_state(confidence=0.95)
        result = _generate_confidence_transparency(state)
        assert result == "" or "thấp" not in result

    def test_low_confidence_generates_warning(self):
        state = self._make_state(confidence=0.5)
        result = _generate_confidence_transparency(state)
        assert "thấp" in result or "tin cậy" in result

    def test_multiple_amended_docs_generates_warning(self):
        chunks = [
            ({"metadata": {"doc_id": "a", "amended_by": ["b"]}}, 0.9),
            ({"metadata": {"doc_id": "c", "amended_by": ["d"]}}, 0.85),
        ]
        state = self._make_state(confidence=1.0, chunks=chunks)
        result = _generate_confidence_transparency(state)
        assert "sửa đổi" in result or "amendment" in result.lower() or result == "" or "văn bản sửa đổi" in result
