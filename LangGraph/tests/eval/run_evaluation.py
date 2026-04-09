"""
Cohort-Aware Retrieval Evaluation

Runs evaluation against frozen cohort-specific test pairs.
Supports three configs for ablation: semantic_only, temporal_only, cohort_aware.

Usage:
    python tests/eval/run_evaluation.py \
        --pairs tests/eval/temporal_test_pairs.json \
        --type cohort_specific \
        --configs semantic_only temporal_only cohort_aware
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure src is on path
ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "src"))


# ---------------------------------------------------------------------------
# Evaluation Config
# ---------------------------------------------------------------------------

CONFIGS = {
    "semantic_only": {
        "use_cohort_boost": False,
        "recency_weight": 0.0,
        "description": "Pure semantic score (baseline)"
    },
    "temporal_only": {
        "use_cohort_boost": False,
        "recency_weight": 0.3,
        "description": "Semantic + temporal, no cohort"
    },
    "cohort_aware": {
        "use_cohort_boost": True,
        "recency_weight": 0.3,
        "description": "Semantic + temporal + cohort (full system)"
    }
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_pairs(pairs_path: str, pair_type: Optional[str]) -> List[Dict[str, Any]]:
    with open(pairs_path) as f:
        data = json.load(f)
    pairs = data["pairs"]
    if pair_type:
        pairs = [p for p in pairs if p.get("type") == pair_type]
    return pairs


def check_response(response: str, expected_contains: List[str], expected_not_contains: List[str]) -> bool:
    """
    Simple string-match evaluation.
    Returns True if all expected_contains strings are found (case-insensitive)
    and none of expected_not_contains appear.
    """
    response_lower = response.lower()
    for token in expected_contains:
        if token.lower() not in response_lower:
            return False
    for token in expected_not_contains:
        if token.lower() in response_lower:
            return False
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run cohort-aware retrieval evaluation")
    parser.add_argument("--pairs", required=True, help="Path to test pairs JSON file")
    parser.add_argument("--type", default="cohort_specific", help="Filter by pair type")
    parser.add_argument(
        "--configs", nargs="+", default=["cohort_aware"],
        choices=list(CONFIGS.keys()),
        help="Evaluation configs to run"
    )
    parser.add_argument("--split", default="test", choices=["test", "validation", "all"])
    args = parser.parse_args()

    pairs = load_pairs(args.pairs, args.type)

    # Apply split filter
    if args.split != "all":
        with open(args.pairs) as f:
            data = json.load(f)
        split_ids = set(data.get("split", {}).get(args.split, []))
        pairs = [p for p in pairs if p["id"] in split_ids]

    print(f"Loaded {len(pairs)} pairs (split={args.split}, type={args.type})")
    print()

    results: Dict[str, Dict[str, Any]] = {}

    for config_name in args.configs:
        config = CONFIGS[config_name]
        print(f"Config: {config_name} — {config['description']}")
        print("-" * 60)

        correct = 0
        total = len(pairs)

        for pair in pairs:
            query = pair["query"]
            cohort_year = pair.get("query_cohort_year")
            expected_contains = pair.get("expected_contains", [])
            expected_not_contains = pair.get("expected_not_contains", [])

            # TODO: wire to actual graph invocation
            # For now, placeholder — replace with real pipeline call
            response = f"[PLACEHOLDER] Query: {query}"

            passed = check_response(response, expected_contains, expected_not_contains)
            if passed:
                correct += 1

            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] id={pair['id']} cohort={cohort_year} — {query[:60]}")

        accuracy = correct / total if total > 0 else 0.0
        results[config_name] = {"accuracy": accuracy, "correct": correct, "total": total}
        print(f"  accuracy@1: {accuracy:.2%} ({correct}/{total})")
        print()

    # Summary
    print("=" * 60)
    print("ABLATION SUMMARY")
    print("=" * 60)
    for config_name, res in results.items():
        print(f"  {config_name:20s}: {res['accuracy']:.2%}")

    # TODO: add McNemar's test between cohort_aware and best baseline
    # from statsmodels.stats.contingency_tables import mcnemar


if __name__ == "__main__":
    main()
