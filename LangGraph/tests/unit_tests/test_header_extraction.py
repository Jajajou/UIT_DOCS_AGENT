"""
Unit tests for header_extraction.py

Tests focus on:
- Regex doc_number extraction from header line "So: X/Y-Z"
- Regex amends extraction from "Can cu... so X", "sua doi... so X" preambles
- Implicit amendment detection (blanket-replacement language, no citation)
- Merge logic (_merge_amends, _normalise_doc_ref)
- LLM path mocked so tests run without network
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.agents.header_extraction import (
    _has_implicit_amendment,
    _merge_amends,
    _regex_amends,
    _regex_doc_number,
    extract_from_header,
)
from agent.utils import normalize_docnum as _normalise_doc_ref


# ---------------------------------------------------------------------------
# Fixtures — sample Vietnamese document headers
# ---------------------------------------------------------------------------

SAMPLE_HEADER_SIMPLE = """
TRUONG DAI HOC CONG NGHE THONG TIN
                   CONG HOA XA HOI CHU NGHIA VIET NAM
                        Doc lap - Tu do - Hanh phuc
So: 108/QD-DHCNTT
                                   TP. Ho Chi Minh, ngay 15 thang 3 nam 2024

QUYET DINH
Ve viec ban hanh Quy dinh hoc vu danh cho sinh vien chinh quy
"""

SAMPLE_HEADER_AMENDS = """
So: 20/TB-KHTC

THONG BAO
Ve viec sua doi muc hoc phi

Can cu Quyet dinh so 108/QĐ-ĐHCNTT ngay 15/3/2024 cua Hieu truong
Sua doi khoan 3 dieu 5 Quyet dinh so 141/QD-DHCNTT ngay 10/1/2023
"""

SAMPLE_HEADER_BLANKET = """
So: 55/QD-DHCNTT

QUYET DINH
Ve viec ban hanh Quy che moi

Quyet dinh nay thay the toan bo cac quy dinh truoc day ve hoc vu sinh vien.
Co hieu luc ke tu ngay ky.
"""

SAMPLE_HEADER_NO_AMENDS = """
So: 33/TB-CTSV

THONG BAO
Ve viec to chuc Le tot nghiep dot 1 nam 2024

Can cu Quyet dinh so 05/2018/QD-TTg cua Thu tuong Chinh phu.
"""

SAMPLE_HEADER_MINISTRY = """
Bo GIAO DUC VA DAO TAO

So: 02/2022/TT-BGDDT

THONG TU
Sua doi, bo sung mot so dieu cua Thong tu so 07/2020/TT-BGDDT ngay 20/3/2020.
"""


# ---------------------------------------------------------------------------
# _regex_doc_number
# ---------------------------------------------------------------------------

class TestRegexDocNumber:
    def test_simple_header_line(self):
        result = _regex_doc_number("So: 108/QD-DHCNTT\nSome content")
        assert result == "108/QD-DHCNTT"

    def test_header_with_spaces(self):
        result = _regex_doc_number("So :  20/TB-KHTC\n")
        assert result is not None
        assert "20/TB-KHTC" in result

    def test_no_doc_number(self):
        result = _regex_doc_number("Khong co so hieu van ban nao trong doan nay.")
        assert result is None

    def test_not_extracted_from_body(self):
        # Doc number pattern buried in body text should NOT be picked up
        # because we only search first 600 chars for "So:" prefix
        long_preamble = "x" * 700 + "\nSo: 99/QD-DHCNTT\n"
        result = _regex_doc_number(long_preamble)
        assert result is None

    def test_ministry_format(self):
        result = _regex_doc_number("So: 02/2022/TT-BGDDT\n")
        assert result is not None
        assert "/" in result


# ---------------------------------------------------------------------------
# _regex_amends
# ---------------------------------------------------------------------------

class TestRegexAmends:
    def test_sua_doi_quyet_dinh(self):
        text = "sửa đổi khoản 3 điều 5 quyết định số 141/QD-DHCNTT ngày 10/1/2023"
        result = _regex_amends(text)
        assert any("141" in r for r in result), f"Got: {result}"

    def test_thay_the_thong_bao(self):
        text = "thay thế thông báo số 05/TB-KHTC ngày 01/01/2024"
        result = _regex_amends(text)
        assert any("05" in r for r in result), f"Got: {result}"

    def test_bo_sung(self):
        text = "bổ sung điều 3 quyết định số 88/QD-DHCNTT"
        result = _regex_amends(text)
        assert any("88" in r for r in result), f"Got: {result}"

    def test_no_amends(self):
        text = "thông báo về lễ tốt nghiệp đợt 1 năm 2024"
        result = _regex_amends(text)
        assert result == []

    def test_deduplication(self):
        text = (
            "sửa đổi quyết định số 141/QD-DHCNTT. "
            "thay thế quyết định số 141/QD-DHCNTT."
        )
        result = _regex_amends(text)
        # Should appear only once
        normalised = [r.upper() for r in result]
        assert normalised.count("141/QD-DHCNTT") <= 1

    def test_ministry_thong_tu(self):
        text = "sửa đổi thông tư số 07/2020/TT-BGDDT ngày 20/3/2020"
        result = _regex_amends(text)
        assert any("07" in r for r in result), f"Got: {result}"

    def test_ocr_garbled_sua_doi(self):
        # MinerU may output 'sua doi' instead of 'sửa đổi' for scanned docs
        text = "sua doi khoan 3 dieu 5 Quyet dinh so 141/QD-DHCNTT ngay 10/1/2023"
        result = _regex_amends(text)
        assert any("141" in r for r in result), f"Got (OCR-garbled): {result}"

    def test_ocr_garbled_thay_the(self):
        # 'thay the' without diacritics, common in low-quality scans
        text = "thay the Thong bao so 05/TB-KHTC ngay 01/01/2024"
        result = _regex_amends(text)
        assert any("05" in r for r in result), f"Got (OCR-garbled): {result}"


# ---------------------------------------------------------------------------
# _has_implicit_amendment
# ---------------------------------------------------------------------------

class TestImplicitAmendment:
    def test_blanket_replacement(self):
        text = "Quyết định này thay thế toàn bộ các quy định trước đây về học vụ."
        assert _has_implicit_amendment(text) is True

    def test_het_hieu_luc(self):
        text = "Các văn bản trước đây hết hiệu lực kể từ ngày ký."
        assert _has_implicit_amendment(text) is True

    def test_no_implicit(self):
        text = "Thông báo về lễ tốt nghiệp. Không có sửa đổi gì."
        assert _has_implicit_amendment(text) is False

    def test_explicit_but_no_implicit(self):
        # Has explicit citation — implicit flag should still be False
        text = "Sửa đổi Quyết định số 141/QĐ-ĐHCNTT. Không có quy định nào khác."
        assert _has_implicit_amendment(text) is False


# ---------------------------------------------------------------------------
# _normalise_doc_ref and _merge_amends
# ---------------------------------------------------------------------------

class TestNormalise:
    def test_uppercase(self):
        assert _normalise_doc_ref("108/qd-dhcntt") == "108/QĐ-ĐHCNTT"

    def test_strips_whitespace(self):
        assert _normalise_doc_ref("  108/QĐ-ĐHCNTT  ") == "108/QĐ-ĐHCNTT"

    def test_no_slash_returns_none(self):
        assert _normalise_doc_ref("108") is None

    def test_too_long_returns_none(self):
        assert _normalise_doc_ref("x" * 90) is None

    def test_empty_returns_none(self):
        assert _normalise_doc_ref("") is None


class TestMergeAmends:
    def test_union(self):
        regex = ["108/QĐ-ĐHCNTT"]
        llm = ["141/TB-KHTC"]
        result = _merge_amends(regex, llm)
        assert "108/QĐ-ĐHCNTT" in result
        assert "141/TB-KHTC" in result

    def test_deduplication_across_sources(self):
        regex = ["108/QĐ-ĐHCNTT"]
        llm = ["108/qd-dhcntt"]  # same, different case
        result = _merge_amends(regex, llm)
        assert len(result) == 1

    def test_filters_invalid(self):
        regex = ["NOSLASH", "108/QĐ-ĐHCNTT"]
        llm = []
        result = _merge_amends(regex, llm)
        assert "NOSLASH" not in result
        assert "108/QĐ-ĐHCNTT" in result


# ---------------------------------------------------------------------------
# extract_from_header — integration with mocked LLM
# ---------------------------------------------------------------------------

def _make_llm_response(doc_number=None, amends=None, implicit=False):
    payload = {
        "document_number": doc_number,
        "amends_documents": amends or [],
        "implicit_amendment": implicit,
    }
    msg = MagicMock()
    msg.content = json.dumps(payload)
    return msg


class TestExtractFromHeader:
    @patch("agent.agents.header_extraction._get_llm")
    def test_simple_doc_number(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(doc_number="108/QĐ-ĐHCNTT")
        mock_get_llm.return_value = mock_llm

        result = extract_from_header(SAMPLE_HEADER_SIMPLE)
        assert result["document_number"] == "108/QĐ-ĐHCNTT"
        assert result["amends_documents"] == []
        assert result["amendment_confidence"] == "none"
        assert result["implicit_amendment_flag"] is False

    @patch("agent.agents.header_extraction._get_llm")
    def test_explicit_amends(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            doc_number="20/TB-KHTC",
            amends=["141/QD-DHCNTT"],
        )
        mock_get_llm.return_value = mock_llm

        result = extract_from_header(SAMPLE_HEADER_AMENDS)
        assert result["document_number"] == "20/TB-KHTC"
        assert "141/QĐ-ĐHCNTT" in result["amends_documents"]
        assert result["amendment_confidence"] == "high"

    @patch("agent.agents.header_extraction._get_llm")
    def test_implicit_amendment(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            doc_number="55/QD-DHCNTT",
            implicit=True,
        )
        mock_get_llm.return_value = mock_llm

        result = extract_from_header(SAMPLE_HEADER_BLANKET)
        assert result["document_number"] == "55/QĐ-ĐHCNTT"
        assert result["amends_documents"] == []
        assert result["implicit_amendment_flag"] is True
        assert result["amendment_confidence"] == "low"

    @patch("agent.agents.header_extraction._get_llm")
    def test_can_cu_not_counted_as_amend(self, mock_get_llm):
        # "Can cu Quyet dinh so 05/2018/QD-TTg" is a reference, not an amendment
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            doc_number="33/TB-CTSV",
            amends=[],
        )
        mock_get_llm.return_value = mock_llm

        result = extract_from_header(SAMPLE_HEADER_NO_AMENDS)
        assert result["amends_documents"] == []
        assert result["amendment_confidence"] == "none"

    @patch("agent.agents.header_extraction._get_llm")
    def test_llm_failure_falls_back_to_regex(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("connection refused")
        mock_get_llm.return_value = mock_llm

        # Even with LLM down, regex should still pull the header doc number
        result = extract_from_header(SAMPLE_HEADER_SIMPLE)
        # Regex finds "So: 108/QĐ-ĐHCNTT"
        assert result["document_number"] == "108/QĐ-ĐHCNTT"
        assert result["extraction_method_header"] == "header_regex_only"

    @patch("agent.agents.header_extraction._get_llm")
    def test_empty_text(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        result = extract_from_header("")
        assert result["document_number"] is None
        assert result["amends_documents"] == []
        # LLM should never be called for empty text
        mock_llm.invoke.assert_not_called()

    @patch("agent.agents.header_extraction._get_llm")
    def test_llm_doc_number_too_long_ignored(self, mock_get_llm):
        mock_llm = MagicMock()
        # LLM returns garbage long string for doc_number
        mock_llm.invoke.return_value = _make_llm_response(
            doc_number="X" * 100,
        )
        mock_get_llm.return_value = mock_llm

        result = extract_from_header(SAMPLE_HEADER_SIMPLE)
        # Should fall back to regex which finds 108/QĐ-ĐHCNTT
        assert result["document_number"] == "108/QĐ-ĐHCNTT"

    @patch("agent.agents.header_extraction._get_llm")
    def test_ministry_format_amends(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            doc_number="02/2022/TT-BGDDT",
            amends=["07/2020/TT-BGDDT"],
        )
        mock_get_llm.return_value = mock_llm

        result = extract_from_header(SAMPLE_HEADER_MINISTRY)
        assert result["document_number"] == "02/2022/TT-BGDĐT"
        assert "07/2020/TT-BGDĐT" in result["amends_documents"]
        assert result["amendment_confidence"] == "high"
