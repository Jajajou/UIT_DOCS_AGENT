"""
Baseline Metrics - Legacy compatibility layer for TDCE framework.

Provides backward-compatible metric computation that matches the original
run_evaluation.py output format while adding TDCE metrics.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List


def _normalise(s: str) -> str:
    """Fold Vietnamese diacritics away, lower-case, and strip noise for comparison."""
    if not s:
        return ""
    s = s.lower()
    # Basic diacritic folding
    s = re.sub(r"[áàảãạăắằẳẵặâấầẩẫậ]", "a", s)
    s = re.sub(r"[éèẻẽẹêếềểễệ]", "e", s)
    s = re.sub(r"[íìỉĩị]", "i", s)
    s = re.sub(r"[óòỏõọôốồổỗộơớờởỡợ]", "o", s)
    s = re.sub(r"[úùủũụưứừửữự]", "u", s)
    s = re.sub(r"[ýỳỷỹỵ]", "y", s)
    s = re.sub(r"[đ]", "d", s)

    s = re.sub(r"\s+", " ", s)
    return s


def _found(text: str, doc_number: str) -> bool:
    """Return True if doc_number string appears in text (normalised, flexible separators)."""
    norm_text = _normalise(text)
    norm_dn = _normalise(doc_number)

    parts = re.split(r"[/\\-_]", norm_dn)
    pattern = r"[\s/\\-_]*".join([re.escape(p) for p in parts if p])

    try:
        return bool(re.search(pattern, norm_text, re.IGNORECASE))
    except re.error:
        return norm_dn in norm_text


def accuracy_at_1(text: str, expected_doc_numbers: List[str]) -> float:
    """1.0 if ANY expected doc number appears anywhere in the response."""
    for dn in expected_doc_numbers:
        if _found(text, dn):
            return 1.0
    return 0.0


def mrr(text: str, expected_doc_numbers: List[str]) -> float:
    """MRR over a single query: 1/rank if any expected doc found, else 0."""
    for i, dn in enumerate(expected_doc_numbers, start=1):
        if _found(text, dn):
            return 1.0 / i
    return 0.0


def ndcg_at_k(text: str, expected_doc_numbers: List[str], k: int = 3) -> float:
    """Approximate NDCG@k treating expected_doc_numbers as graded relevance 1/i."""
    dcg = 0.0
    ideal_dcg = 0.0

    for i, dn in enumerate(expected_doc_numbers[:k], start=1):
        rel = 1.0 if _found(text, dn) else 0.0
        dcg += rel / math.log2(i + 1)
        ideal_dcg += 1.0 / math.log2(i + 1)

    return (dcg / ideal_dcg) if ideal_dcg > 0 else 0.0


def confound_present(text: str, confounding_doc_numbers: List[str]) -> bool:
    """Check if any confounding document is mentioned."""
    for dn in confounding_doc_numbers:
        if _found(text, dn):
            return True
    return False


def compute_baseline_metrics(text: str, pair: Dict[str, Any]) -> Dict[str, float]:
    """
    Compute all baseline metrics for a single pair.

    Returns dict with keys: acc@1, mrr, ndcg@3, confound_present
    """
    expected = pair.get("expected_doc_numbers", [])
    confounding = pair.get("confounding_doc_numbers", [])

    return {
        "acc@1": accuracy_at_1(text, expected),
        "mrr": mrr(text, expected),
        "ndcg@3": ndcg_at_k(text, expected, k=3),
        "confound_present": 1.0 if confound_present(text, confounding) else 0.0
    }


def aggregate_metrics(results: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Aggregate metrics across multiple results.

    Returns dict with average values for each metric.
    """
    if not results:
        return {}

    metrics = ["acc@1", "mrr", "ndcg@3", "confound_present"]
    aggregated = {}

    for metric in metrics:
        values = [r.get(metric, 0.0) for r in results]
        aggregated[metric] = sum(values) / len(values)

    return aggregated


def compute_win_loss_tie(baseline_results: List[Dict[str, Any]],
                        system_results: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Compute win/loss/tie statistics comparing system to baseline.

    Returns dict with keys: wins, losses, ties, net_pct
    """
    baseline_by_id = {r["id"]: r for r in baseline_results}

    wins = losses = ties = 0

    for r in system_results:
        b = baseline_by_id.get(r["id"])
        if b is None:
            continue

        if r["acc@1"] > b["acc@1"]:
            wins += 1
        elif r["acc@1"] < b["acc@1"]:
            losses += 1
        else:
            ties += 1

    total = wins + losses + ties
    net_pct = (wins - losses) / total * 100 if total else 0

    return {
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "net_pct": net_pct
    }
