"""
Extract clause-level amendment mappings from Vietnamese legal document body.

Vietnamese amendment docs have structure:
  Điều 1. Sửa đổi khoản 2 Điều 5 Quyết định 141/QĐ-ĐHCNTT như sau: ...
  Điều 2. Bổ sung Điều 7a vào Quyết định 141/QĐ-ĐHCNTT: ...
  Điều 3. Bãi bỏ Điều 12, Điều 15 của Quyết định 141/QĐ-ĐHCNTT.

Returns structured list of {source_clause_id, target_doc_number,
target_clause_id, amendment_type} for each action clause found.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Patterns
# ------------------------------------------------------------------ #

# Clause boundary marker (same as clause_chunker)
_DIEU_SPLIT = re.compile(
    r'^(?:Điều|Dieu|ĐIỀU)\s+(\d+[a-z]?)\s*[.:]',
    re.MULTILINE | re.IGNORECASE,
)

# Amendment action verbs (OCR-robust)
_ACTION_PATTERNS = {
    "replace_partial": re.compile(
        r's.{0,2}a\s*[đd].{0,2}i',
        re.IGNORECASE,
    ),
    "supplement": re.compile(
        r'b.{0,2}\s*sung',
        re.IGNORECASE,
    ),
    "repeal": re.compile(
        r'(?:b.{0,2}i\s*b.{0,2}|h.{0,2}y\s*b.{0,2})',
        re.IGNORECASE,
    ),
    "replace_full": re.compile(
        r'thay\s*th.{0,2}',
        re.IGNORECASE,
    ),
}

# Target clause reference inside a clause body: "Điều 5", "khoản 2 Điều 10", "Điều 7a"
_TARGET_CLAUSE_RE = re.compile(
    r'(?:[Kk]ho.{0,2}n\s+\d+\s+)?(?:[Đđ]i.{0,2}u|Dieu|DIEU)\s+(\d+[a-z]?)',
    re.IGNORECASE,
)

# Explicit doc-number reference inside clause body
_DOC_NUM_RE = re.compile(
    r'(\d{1,4}/(?:\d{4}/)?[A-Z]{1,15}(?:-[A-Z]{1,20})+)',
)


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def extract_clause_amendments(
    doc_text: str,
    amends_documents: list[str],
) -> list[dict[str, Any]]:
    """
    Parse amendment doc body and return clause-level amendment mappings.

    Args:
        doc_text: Full document text.
        amends_documents: Doc-level amends list (from header extraction).
            Used as fallback when a clause doesn't cite the target doc explicitly.

    Returns:
        List of dicts with keys:
            source_clause_id  (str)  e.g. "Điều 1"
            target_doc_number (str | None)  e.g. "141/QĐ-ĐHCNTT"
            target_clause_id  (str | None)  e.g. "Điều 5"
            amendment_type    (str)  replace_partial | supplement | repeal | replace_full
    """
    if not doc_text or not amends_documents:
        return []

    clauses = _split_into_clauses(doc_text)
    results: list[dict[str, Any]] = []

    # Default target doc: if only one doc in amends_documents, all actions target it
    default_target = amends_documents[0] if len(amends_documents) == 1 else None

    for clause_id, clause_body in clauses:
        action_type = _detect_action(clause_body)
        if action_type is None:
            continue

        # Target clause: first Điều reference in the action line/body
        target_clause = _extract_target_clause(clause_body)

        # Target doc: explicit citation in clause body, else default
        target_doc = _extract_target_doc(clause_body, amends_documents) or default_target

        if target_doc is None:
            logger.debug(
                "[ClauseAmend] %s: action=%s but no target_doc found, skipping",
                clause_id, action_type,
            )
            continue

        results.append({
            "source_clause_id": clause_id,
            "target_doc_number": target_doc,
            "target_clause_id": target_clause,
            "amendment_type": action_type,
        })

    logger.info(
        "[ClauseAmend] Found %d clause-level amendment mappings", len(results)
    )
    return results


# ------------------------------------------------------------------ #
# Private helpers
# ------------------------------------------------------------------ #

def _split_into_clauses(doc_text: str) -> list[tuple[str, str]]:
    """Split doc text into (clause_id, clause_body) pairs."""
    matches = list(_DIEU_SPLIT.finditer(doc_text))
    if not matches:
        return []

    clauses = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(doc_text)
        clause_id = f"Điều {m.group(1)}"
        clause_body = doc_text[start:end].strip()
        clauses.append((clause_id, clause_body))
    return clauses


def _detect_action(clause_body: str) -> str | None:
    """Return amendment_type string if clause is an amendment action, else None."""
    # Check only first 300 chars (action verb always in heading/first line)
    head = clause_body[:300]
    for action_type, pattern in _ACTION_PATTERNS.items():
        if pattern.search(head):
            return action_type
    return None


def _extract_target_clause(clause_body: str) -> str | None:
    """Extract first target clause reference from clause body."""
    # Skip past "Điều N." (≈8 chars) to avoid re-matching the source clause marker
    skip = clause_body.find(".") + 1
    if skip <= 0:
        skip = 8
    m = _TARGET_CLAUSE_RE.search(clause_body, skip)
    if m:
        return f"Điều {m.group(1)}"
    return None


def _extract_target_doc(clause_body: str, amends_documents: list[str]) -> str | None:
    """Return doc number if explicitly cited in clause_body and matches known amends list."""
    found = _DOC_NUM_RE.findall(clause_body)
    for raw in found:
        candidate = raw.upper().strip()
        # Match against known amends (partial match handles normalisation differences)
        for known in amends_documents:
            if candidate in known or known in candidate:
                return known
    return None
