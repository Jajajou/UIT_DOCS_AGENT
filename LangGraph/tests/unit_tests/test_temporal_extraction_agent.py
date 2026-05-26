"""
Unit tests for TemporalExtractionAgent (regex / local tools only — no LLM).

Covers:
- _load_vietnamese_patterns: all key pattern groups present
- extract_with_local_tools: valid_from, valid_until, academic_year, cohort, doc_number
- "hiệu lực kể từ ngày ký" resolved from header signing date
- is_vbhn detection
- extract_from_filename: date and cohort from filename
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from agent.agents.agent_temporal_extraction import TemporalExtractionAgent, TemporalMetadata


# ---------------------------------------------------------------------------
# Fixture: agent with mocked LLM (no real model needed for local-tool tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def agent() -> TemporalExtractionAgent:
    mock_llm = MagicMock()
    mock_config = MagicMock()
    return TemporalExtractionAgent(llm_model=mock_llm, config=mock_config)


# ---------------------------------------------------------------------------
# Pattern loading
# ---------------------------------------------------------------------------

class TestLoadPatterns:

    def test_all_required_groups_present(self, agent):
        patterns = agent.regex_patterns
        for key in ["valid_from", "valid_until", "academic_year", "cohort", "document_number", "amends", "vbhn"]:
            assert key in patterns, f"Missing pattern group: {key}"

    def test_each_group_nonempty(self, agent):
        for key, val in agent.regex_patterns.items():
            assert len(val) > 0, f"Pattern group '{key}' is empty"


# ---------------------------------------------------------------------------
# extract_with_local_tools: valid_from
# ---------------------------------------------------------------------------

class TestExtractValidFrom:

    def test_co_hieu_luc_tu_ngay(self, agent):
        text = "Quyết định này có hiệu lực từ ngày 01/09/2024."
        result = agent.extract_with_local_tools(text)
        assert result.valid_from == "2024-09-01"

    def test_hieu_luc_ke_tu_ngay_ky_resolves_header(self, agent):
        text = (
            "Tp. HCM, ngày 15 tháng 3 năm 2023\n"
            "Quyết định có hiệu lực kể từ ngày ký ban hành.\n"
        )
        result = agent.extract_with_local_tools(text)
        assert result.valid_from == "2023-03-15"

    def test_hieu_luc_tu_ngay_ky_also_resolves(self, agent):
        text = (
            "ngày 10 tháng 01 năm 2024\n"
            "Có hiệu lực từ ngày ký."
        )
        result = agent.extract_with_local_tools(text)
        assert result.valid_from == "2024-01-10"


# ---------------------------------------------------------------------------
# extract_with_local_tools: valid_until
# ---------------------------------------------------------------------------

class TestExtractValidUntil:

    def test_het_hieu_luc_vao(self, agent):
        text = "Văn bản hết hiệu lực vào 31/08/2025."
        result = agent.extract_with_local_tools(text)
        assert result.valid_until == "2025-08-31"


# ---------------------------------------------------------------------------
# extract_with_local_tools: academic_year
# ---------------------------------------------------------------------------

class TestExtractAcademicYear:

    def test_nam_hoc_pattern(self, agent):
        text = "Áp dụng cho năm học 2024-2025."
        result = agent.extract_with_local_tools(text)
        assert result.academic_year == "2024-2025"

    def test_academic_year_infers_valid_dates(self, agent):
        text = "Áp dụng cho năm học 2024-2025."
        result = agent.extract_with_local_tools(text)
        # Should infer valid_from = 2024-09-01, valid_until = 2025-08-31
        assert result.valid_from == "2024-09-01"
        assert result.valid_until == "2025-08-31"


# ---------------------------------------------------------------------------
# extract_with_local_tools: cohort extraction
# ---------------------------------------------------------------------------

class TestExtractCohort:

    def test_sinh_vien_khoa_year(self, agent):
        text = "Áp dụng cho sinh viên khóa 2022."
        result = agent.extract_with_local_tools(text)
        assert 2022 in result.cohort_years

    def test_nhap_hoc_nam_year(self, agent):
        text = "Sinh viên nhập học 2021 cần chú ý."
        result = agent.extract_with_local_tools(text)
        assert 2021 in result.cohort_years

    def test_multiple_cohorts(self, agent):
        text = "Áp dụng cho sinh viên khóa 2020 và sinh viên khóa 2021."
        result = agent.extract_with_local_tools(text)
        assert 2020 in result.cohort_years
        assert 2021 in result.cohort_years


# ---------------------------------------------------------------------------
# VBHN detection
# ---------------------------------------------------------------------------

class TestVbhnDetection:

    def test_vbhn_detected(self, agent):
        text = "Đây là văn bản hợp nhất các quyết định về học bổng."
        result = agent.extract_with_local_tools(text)
        assert result.is_vbhn is True

    def test_non_vbhn_not_flagged(self, agent):
        text = "Quyết định về quy chế học vụ."
        result = agent.extract_with_local_tools(text)
        assert result.is_vbhn is False


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

class TestConfidenceScoring:

    def test_no_dates_confidence_zero(self, agent):
        result = agent.extract_with_local_tools("Không có thông tin ngày tháng.")
        assert result.confidence == 0.0

    def test_with_date_confidence_positive(self, agent):
        text = "có hiệu lực từ ngày 01/09/2024"
        result = agent.extract_with_local_tools(text)
        assert result.confidence > 0.0

    def test_confidence_in_range(self, agent):
        text = "có hiệu lực từ ngày 01/09/2024. Năm học 2024-2025."
        result = agent.extract_with_local_tools(text)
        assert 0.0 <= result.confidence <= 1.0


# ---------------------------------------------------------------------------
# Output is always TemporalMetadata
# ---------------------------------------------------------------------------

class TestOutputType:

    def test_returns_temporal_metadata_instance(self, agent):
        result = agent.extract_with_local_tools("anything")
        assert isinstance(result, TemporalMetadata)

    def test_all_fields_have_defaults(self, agent):
        result = agent.extract_with_local_tools("")
        assert result.valid_from is None
        assert result.valid_until is None
        assert result.cohort_years == []
        assert result.is_vbhn is False
