"""
Header-based extraction for document_number and amends_documents.

WHY THIS APPROACH OVER RAG:
- Vietnamese official documents always put "So: XXX/QD-DHCNTT" in the header
  (top 200-400 chars), and amendment references in the "Can cu..." preamble
  (top 600-800 chars). RAG retrieval is probabilistic — it can return content
  chunks from page 4 that don't contain either field, causing extraction misses.
- document_number and amends_documents are POSITIONAL, not semantic. The answer
  is always in the first 2000 chars. Send that directly to the LLM.
- cohort_years and valid_dates are legitimately scattered — RAG stays for those.

OUTPUT SHAPE (merged back into DocumentMetadata):
    {
        "document_number": "108/QD-DHCNTT" | None,
        "amends_documents": ["141/TB-KHTC", ...],  # explicit citations
        "amendment_confidence": "high" | "low" | "none",
        "implicit_amendment_flag": True | False,  # blanket replacements
        "extraction_method_header": "header_llm" | "header_regex_only",
    }
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain.chat_models import init_chat_model

from agent.config import settings
from agent.utils import strip_think_tags

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Singleton LLM (same settings as metadata_rag_nodes)
# --------------------------------------------------------------------------- #
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = init_chat_model(
            model_provider="openai",
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.indexing_llm_model,
            streaming=False,
            temperature=0,
            model_kwargs={"tool_choice": "none"},
        )
    return _llm


# --------------------------------------------------------------------------- #
# Vietnamese amendment keyword patterns
#
# Design principle: OCR quality from MinerU is variable — diacritics are often
# dropped or garbled (e.g. "sua doi" instead of "sửa đổi", "so" instead of "số").
# Use .{0,2} wildcards on vowel+diacritic positions so the pattern survives OCR
# errors while still requiring the consonant skeleton of each keyword.
# The document NUMBER itself (141/QD-DHCNTT) is always ASCII — reliable anchor.
# --------------------------------------------------------------------------- #

# Capture group for document numbers: 141/QD-DHCNTT, 07/2020/TT-BGDDT
_DOC_NUM_CAP = r"(\d{1,4}/(?:\d{4}/)?[A-Z]{1,15}(?:-[A-Z]{1,20})+)"

# Amendment verb patterns — OCR-robust via .{0,2} on diacritics
_AMEND_VERB = (
    r"(?:"
    r"s.{0,2}a\s*[đd].{0,2}i"   # sửa đổi / sua doi / s?a d?i
    r"|thay\s*th.{0,2}"          # thay thế / thay the
    r"|b.{0,2}\s*sung"           # bổ sung / bo sung
    r"|h.{0,2}y\s*b.{0,2}"      # hủy bỏ / huy bo
    r"|b.{0,2}i\s*b.{0,2}"      # bãi bỏ / bai bo
    r")"
)

# Single consolidated pattern: amend_verb ... (up to 150 chars) ... so NNN/UPPER
# Stops at sentence boundary (.) so we don't cross into the next clause.
_AMEND_CITE_PATTERN = re.compile(
    _AMEND_VERB + r"[^.]{0,150}?[Ss].{0,2}[:\s]+" + _DOC_NUM_CAP,
    re.IGNORECASE,
)

# Keywords indicating IMPLICIT blanket replacements (no doc number cited).
# Listed with diacritics; also keep ASCII fallbacks for OCR-garbled docs.
_IMPLICIT_AMEND_KEYWORDS = [
    # Proper Vietnamese
    "thay thế các quy định trước",
    "thay thế toàn bộ",
    "thay thế cho các văn bản",
    "hết hiệu lực",
    "bãi bỏ các quy định trước",
    "không còn hiệu lực",
    "thay thế quy định cũ",
    # OCR-garbled ASCII fallbacks
    "thay the cac quy dinh truoc",
    "thay the toan bo",
    "het hieu luc",
    "bai bo cac quy dinh",
    "khong con hieu luc",
]

# Doc-number format for validation: digits / letters-dashes
_DOC_NUMBER_RE = re.compile(r"\d{1,4}/(?:\d{4}/)?[A-Z]{1,15}(?:-[A-Z]{1,20})+")

# Header line: "So: 108/QD-DHCNTT" — OCR may render as "So:", "Sô:", "S6:", etc.
# Use .{0,2} on the vowel so it handles "Số", "So", "Sô" uniformly.
_HEADER_DOC_NUMBER_RE = re.compile(
    r"[Ss].{0,2}\s*[:.]?\s*(\d{1,4}/(?:\d{4}/)?[A-Z]{1,15}(?:-[A-Z]{1,20})+)"
)

# --------------------------------------------------------------------------- #
# LLM PROMPT for header extraction
# --------------------------------------------------------------------------- #

_HEADER_PROMPT = """\
<|im_start|>system
Bạn là chuyên gia trích xuất thông tin văn bản pháp quy Việt Nam. Chỉ trả lời bằng JSON, không giải thích.
<|im_end|>
<|im_start|>user
Phân tích phần đầu văn bản sau và trích xuất:

1. **document_number**: Số hiệu chính thức (VD: "108/QD-DHCNTT", "20/TB-KHTC").
   - Nằm ở dòng bắt đầu bằng "Số:" hoặc góc trên trái.
   - KHÔNG lấy từ tên file. Trả về null nếu không tìm thấy.

2. **amends_documents**: Danh sách số hiệu các văn bản bị sửa đổi/thay thế/bãi bỏ.
   - Tìm các cụm: "sửa đổi ... số X", "thay thế ... số X", "bổ sung ... số X",
     "hủy bỏ ... số X", "bãi bỏ ... số X", "căn cứ ... số X" (chỉ khi có hành động sửa đổi/thay thế).
   - CHỈ lấy số hiệu có hành động rõ ràng. "Căn cứ" đơn thuần (không kèm sửa đổi) KHÔNG tính.
   - Trả về [] nếu không có.

3. **implicit_amendment**: true nếu văn bản có cụm từ như "thay thế toàn bộ quy định trước",
   "hết hiệu lực", "bãi bỏ quy định cũ" NHƯNG KHÔNG nêu số hiệu cụ thể. Ngược lại: false.

Phần đầu văn bản:
<header>
{header_text}
</header>

Trả về JSON duy nhất:
{{"document_number": "...", "amends_documents": [], "implicit_amendment": false}}
<|im_end|>
<|im_start|>assistant
"""


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def extract_from_header(doc_text: str, file_source: str = "") -> dict[str, Any]:
    """
    Extract document_number and amends_documents from the first 2000 chars.

    Returns a dict with keys:
        document_number         (str | None)
        amends_documents        (list[str])
        amendment_confidence    ("high" | "low" | "none")
        implicit_amendment_flag (bool)
        extraction_method_header ("header_llm" | "header_regex_only")
    """
    header_text = doc_text[:2000].strip()
    if not header_text:
        return _empty_result()

    # 1. Try regex-only fast path first — covers common patterns with certainty
    regex_doc_num = _regex_doc_number(header_text)
    regex_amends = _regex_amends(header_text)
    implicit_flag = _has_implicit_amendment(doc_text)  # scan full doc

    # 2. Always run LLM on the header to catch patterns regex misses
    llm_result = _llm_extract(header_text, file_source)

    # 3. Merge: prefer LLM doc_num if found, regex as fallback
    doc_num = llm_result.get("document_number") or regex_doc_num
    # Validate length — real doc numbers are short
    if doc_num and len(doc_num) > 80:
        doc_num = regex_doc_num

    # Merge amends: union of regex and LLM findings
    llm_amends = llm_result.get("amends_documents", [])
    combined_amends = _merge_amends(regex_amends, llm_amends)

    # Override implicit flag with LLM signal if set
    if llm_result.get("implicit_amendment"):
        implicit_flag = True

    # Confidence
    if combined_amends:
        amendment_confidence = "high"
    elif implicit_flag:
        amendment_confidence = "low"
    else:
        amendment_confidence = "none"

    method = "header_llm" if llm_result.get("_llm_ok") else "header_regex_only"

    logger.info(
        "[Header] doc_num=%r amends=%s implicit=%s confidence=%s via %s",
        doc_num, combined_amends, implicit_flag, amendment_confidence, method,
    )

    return {
        "document_number": doc_num,
        "amends_documents": combined_amends,
        "amendment_confidence": amendment_confidence,
        "implicit_amendment_flag": implicit_flag,
        "extraction_method_header": method,
    }


# --------------------------------------------------------------------------- #
# Private helpers
# --------------------------------------------------------------------------- #

def _regex_doc_number(text: str) -> str | None:
    """Extract 'So: 108/QD-DHCNTT' style header line."""
    m = _HEADER_DOC_NUMBER_RE.search(text[:600])
    if m:
        candidate = m.group(1).strip()
        # Must look like a real doc number: contains /
        if "/" in candidate and len(candidate) <= 80:
            return candidate
    return None


def _regex_amends(text: str) -> list[str]:
    """OCR-robust regex pass over header for explicit amendment citations."""
    found: list[str] = []
    for m in _AMEND_CITE_PATTERN.finditer(text):
        raw = m.group(1).upper().strip()
        if raw:
            found.append(raw)
    return list(dict.fromkeys(found))  # preserve order, deduplicate


def _has_implicit_amendment(doc_text: str) -> bool:
    """Scan full document for blanket-replacement language."""
    text_lower = doc_text.lower()
    return any(kw in text_lower for kw in _IMPLICIT_AMEND_KEYWORDS)


def _llm_extract(header_text: str, file_source: str) -> dict[str, Any]:
    """Call LLM on header. Returns parsed dict + _llm_ok flag."""
    try:
        prompt = _HEADER_PROMPT.format(header_text=header_text)
        response = _get_llm().invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        if not isinstance(content, str):
            content = str(content)
        content = strip_think_tags(content)

        # Parse first JSON object in response
        decoder = json.JSONDecoder()
        start = content.find("{")
        if start < 0:
            raise ValueError("No JSON object in LLM response")
        data, _ = decoder.raw_decode(content, start)

        # Validate doc_number
        doc_num = data.get("document_number")
        if doc_num and (len(doc_num) > 80 or not isinstance(doc_num, str)):
            doc_num = None
        data["document_number"] = doc_num

        # Validate amends list
        amends = data.get("amends_documents", [])
        if not isinstance(amends, list):
            amends = []
        data["amends_documents"] = [
            str(a).strip() for a in amends if a and isinstance(a, (str, int))
        ]

        data["_llm_ok"] = True
        return data

    except Exception as exc:
        logger.warning("[Header LLM] extraction failed: %s", exc)
        return {"_llm_ok": False}


def _merge_amends(regex: list[str], llm: list[str]) -> list[str]:
    """Union of regex and LLM amends, normalised, deduplicated."""
    combined = []
    seen: set[str] = set()
    for item in regex + llm:
        normalised = _normalise_doc_ref(item)
        if normalised and normalised not in seen:
            seen.add(normalised)
            combined.append(normalised)
    return combined


def _normalise_doc_ref(ref: str) -> str | None:
    """Upper-case, strip whitespace, basic sanity check."""
    if not ref:
        return None
    ref = ref.upper().strip()
    # Must contain a slash — bare numbers are noise
    if "/" not in ref:
        return None
    # Max length guard
    if len(ref) > 80:
        return None
    return ref


def _empty_result() -> dict[str, Any]:
    return {
        "document_number": None,
        "amends_documents": [],
        "amendment_confidence": "none",
        "implicit_amendment_flag": False,
        "extraction_method_header": "header_regex_only",
    }
