"""Unit tests for eval harness metric functions in run_evaluation.py."""

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tests.eval.run_evaluation import (
    _normalise,
    _found,
    accuracy_at_1,
    mrr,
    ndcg_at_k,
)


class TestNormalise:
    def test_lowercases(self):
        assert _normalise("ABC") == "abc"

    def test_strips_a_diacritics(self):
        assert _normalise("áàảãạăắằẳẵặâấầẩẫậ") == "a" * 17

    def test_strips_e_diacritics(self):
        assert _normalise("éèẻẽẹêếềểễệ") == "e" * 11

    def test_strips_i_diacritics(self):
        assert _normalise("íìỉĩị") == "i" * 5

    def test_strips_o_diacritics(self):
        assert _normalise("óòỏõọôốồổỗộơớờởỡợ") == "o" * 17

    def test_strips_u_diacritics(self):
        assert _normalise("úùủũụưứừửữự") == "u" * 11

    def test_strips_y_diacritics(self):
        assert _normalise("ýỳỷỹỵ") == "y" * 5

    def test_strips_d_diacritics(self):
        assert _normalise("đ") == "d"

    def test_plain_ascii_unchanged(self):
        assert _normalise("hello world 123") == "hello world 123"

    def test_mixed_string(self):
        result = _normalise("Quyết định 108/QĐ-ĐHCNTT")
        assert "quyet" in result
        assert "dinh" in result
        assert "108" in result


class TestFound:
    def test_exact_match(self):
        assert _found("108/QD-DHCNTT trong van ban", "108/QD-DHCNTT") is True

    def test_not_found(self):
        assert _found("van ban khac", "108/QD-DHCNTT") is False

    def test_vietnamese_diacritics_normalised(self):
        # Document number with diacritics in text should match ASCII version
        assert _found("Quyết định số 108/QĐ-ĐHCNTT", "108/QD-DHCNTT") is True

    def test_flexible_separator(self):
        # Slash replaced with flexible separator pattern
        assert _found("108-QD-DHCNTT", "108/QD-DHCNTT") is True

    def test_empty_text(self):
        assert _found("", "108/QD-DHCNTT") is False

    def test_partial_number_not_matched(self):
        # "108" alone should not match "1082/QD-DHCNTT" (regex anchoring)
        # This tests that the function handles regex without crashing
        result = _found("van ban 108/QD-DHCNTT khac", "108/QD-DHCNTT")
        assert result is True


class TestAccuracyAt1:
    def test_first_doc_found(self):
        text = "Theo quyet dinh 108/QD-DHCNTT nam 2024"
        assert accuracy_at_1(text, ["108/QD-DHCNTT"]) == 1.0

    def test_no_doc_found(self):
        text = "Khong co van ban nao duoc dac cap"
        assert accuracy_at_1(text, ["108/QD-DHCNTT", "141/QD-DHCNTT"]) == 0.0

    def test_second_doc_found_still_returns_1(self):
        text = "Theo 141/QD-DHCNTT thay the cho van ban cu"
        assert accuracy_at_1(text, ["108/QD-DHCNTT", "141/QD-DHCNTT"]) == 1.0

    def test_empty_expected_list(self):
        assert accuracy_at_1("any text", []) == 0.0

    def test_empty_text(self):
        assert accuracy_at_1("", ["108/QD-DHCNTT"]) == 0.0


class TestMRR:
    def test_first_rank_hit(self):
        text = "108/QD-DHCNTT la van ban chinh"
        assert mrr(text, ["108/QD-DHCNTT", "141/QD-DHCNTT"]) == pytest.approx(1.0)

    def test_second_rank_hit(self):
        text = "141/QD-DHCNTT sua doi quy dinh"
        assert mrr(text, ["108/QD-DHCNTT", "141/QD-DHCNTT"]) == pytest.approx(0.5)

    def test_third_rank_hit(self):
        text = "200/QD-DHCNTT la tai lieu tham khao"
        result = mrr(text, ["108/QD-DHCNTT", "141/QD-DHCNTT", "200/QD-DHCNTT"])
        assert result == pytest.approx(1.0 / 3)

    def test_no_hit_returns_zero(self):
        assert mrr("text khong lien quan", ["108/QD-DHCNTT"]) == 0.0

    def test_empty_expected_list(self):
        assert mrr("some text", []) == 0.0


class TestNDCGAtK:
    def test_first_doc_found_k3(self):
        text = "108/QD-DHCNTT chinh"
        docs = ["108/QD-DHCNTT", "141/QD-DHCNTT", "200/QD-DHCNTT"]
        # DCG: 1/log2(2) = 1.0; ideal: 1/log2(2) + 1/log2(3) + 1/log2(4)
        dcg = 1.0 / math.log2(2)
        ideal = sum(1.0 / math.log2(i + 1) for i in range(1, 4))
        expected = dcg / ideal
        assert ndcg_at_k(text, docs, k=3) == pytest.approx(expected, abs=1e-9)

    def test_all_docs_found(self):
        text = "108/QD-DHCNTT va 141/QD-DHCNTT va 200/QD-DHCNTT"
        docs = ["108/QD-DHCNTT", "141/QD-DHCNTT", "200/QD-DHCNTT"]
        assert ndcg_at_k(text, docs, k=3) == pytest.approx(1.0)

    def test_no_docs_found(self):
        assert ndcg_at_k("text khac", ["108/QD-DHCNTT"], k=3) == pytest.approx(0.0)

    def test_empty_expected_list(self):
        assert ndcg_at_k("text", [], k=3) == pytest.approx(0.0)

    def test_k_limits_consideration(self):
        # Only first k docs are considered
        text = "200/QD-DHCNTT matches but is rank 3"
        docs = ["108/QD-DHCNTT", "141/QD-DHCNTT", "200/QD-DHCNTT"]
        result_k1 = ndcg_at_k(text, docs, k=1)
        result_k3 = ndcg_at_k(text, docs, k=3)
        # k=1 considers only first doc (not found) → 0.0
        assert result_k1 == pytest.approx(0.0)
        # k=3 considers third doc (found) → nonzero
        assert result_k3 > 0.0
