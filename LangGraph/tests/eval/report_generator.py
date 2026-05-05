"""
TDCE Report Generator - Creates detailed reports for Temporal Document Chain Evaluation results.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from pathlib import Path


def generate_detailed_report(results: List[Dict[str, Any]], output_path: str) -> None:
    """
    Generate detailed TDCE report with all metrics and breakdowns.

    Args:
        results: List of evaluation results from TemporalEvaluationRunner
        output_path: Path to save the report
    """
    # Compute overall metrics
    overall_metrics = _compute_overall_metrics(results)

    # Compute metrics by type
    metrics_by_type = _compute_metrics_by_type(results)

    # Generate report content
    report = {
        "summary": {
            "total_pairs": len(results),
            "overall_metrics": overall_metrics
        },
        "by_type": metrics_by_type,
        "detailed_results": results
    }

    # Save report
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"TDCE report saved to {output_path}")


def _compute_overall_metrics(results: List[Dict[str, Any]]) -> Dict[str, float]:
    """Compute average metrics across all results."""
    if not results:
        return {}

    # Define all TDCE metrics
    tdce_metrics = [
        "accuracy@1", "ap@3", "cascade_hit_rate", "authority_score",
        "cohort_coverage", "ar@3", "displacement_rate"
    ]

    metrics = {}
    for metric in tdce_metrics:
        values = [r.get(metric, 0.0) for r in results]
        metrics[metric] = sum(values) / len(values)

    return metrics


def _compute_metrics_by_type(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Break down metrics by pair type."""
    types = set(r["type"] for r in results)
    breakdown = {}

    for type_name in types:
        type_results = [r for r in results if r["type"] == type_name]
        if type_results:
            metrics = _compute_overall_metrics(type_results)
            breakdown[type_name] = {
                "count": len(type_results),
                "metrics": metrics
            }

    return breakdown


def generate_comparison_report(baseline_results: List[Dict[str, Any]],
                              system_results: List[Dict[str, Any]],
                              output_path: str) -> None:
    """
    Generate comparison report between baseline and system configurations.

    Args:
        baseline_results: Results from baseline configuration
        system_results: Results from system configuration
        output_path: Path to save the comparison report
    """
    # Compute metrics for both
    baseline_metrics = _compute_overall_metrics(baseline_results)
    system_metrics = _compute_overall_metrics(system_results)

    # Compute win/loss/tie
    wlt = _compute_win_loss_tie(baseline_results, system_results)

    # Generate comparison
    comparison = {
        "baseline": baseline_metrics,
        "system": system_metrics,
        "comparison": {
            "win_loss_tie": wlt,
            "improvements": {
                metric: system_metrics.get(metric, 0) - baseline_metrics.get(metric, 0)
                for metric in baseline_metrics.keys()
            }
        }
    }

    # Add type breakdowns
    comparison["by_type"] = {
        "baseline": _compute_metrics_by_type(baseline_results),
        "system": _compute_metrics_by_type(system_results)
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)

    print(f"TDCE comparison report saved to {output_path}")


def _compute_win_loss_tie(baseline_results: List[Dict[str, Any]],
                         system_results: List[Dict[str, Any]]) -> Dict[str, int]:
    """Compute win/loss/tie statistics."""
    baseline_by_id = {r["id"]: r for r in baseline_results}

    wins = losses = ties = 0

    for r in system_results:
        b = baseline_by_id.get(r["id"])
        if b is None:
            continue

        if r["accuracy@1"] > b["accuracy@1"]:
            wins += 1
        elif r["accuracy@1"] < b["accuracy@1"]:
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