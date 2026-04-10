"""
Temporal-Aware Retrieval Ablation Evaluation

Runs 3-way ablation over frozen test pairs.
Conditions:
  Baseline-S : USE_TEMPORAL_SCORING=false  USE_COHORT_BOOST=false
  Baseline-T : USE_TEMPORAL_SCORING=true   USE_COHORT_BOOST=false
  System     : USE_TEMPORAL_SCORING=true   USE_COHORT_BOOST=true

Metrics:
  accuracy@1  — expected doc number appears in final answer
  MRR         — reciprocal rank of first expected doc in answer
  NDCG@3      — normalised discounted cumulative gain at 3
  win/loss/tie table vs Baseline-S

Usage:
    # Full test split, all 3 conditions:
    python tests/eval/run_evaluation.py --split test --all-configs

    # Validation split only (quick sanity):
    python tests/eval/run_evaluation.py --split validation --config System

    # Specific type:
    python tests/eval/run_evaluation.py --type amendment_sensitive --all-configs
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "src"))

LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "http://localhost:2024")
RETRIEVAL_ASSISTANT_ID = os.getenv("RETRIEVAL_ASSISTANT_ID", "5bbc8364-e383-5087-8a2f-b6d27677f7a1")
REQUEST_TIMEOUT = 180

ABLATION_CONFIGS: dict[str, dict[str, str]] = {
    "Baseline-S": {
        "USE_TEMPORAL_SCORING": "false",
        "USE_COHORT_BOOST": "false",
        "description": "Pure semantic reranking",
    },
    "Baseline-T": {
        "USE_TEMPORAL_SCORING": "true",
        "USE_COHORT_BOOST": "false",
        "description": "Temporal scoring, no cohort boost",
    },
    "System": {
        "USE_TEMPORAL_SCORING": "true",
        "USE_COHORT_BOOST": "true",
        "description": "Full system (temporal + cohort)",
    },
}


# ---------------------------------------------------------------------------
# Pipeline invocation
# ---------------------------------------------------------------------------

def set_env_for_config(config_name: str) -> None:
    cfg = ABLATION_CONFIGS[config_name]
    os.environ["USE_TEMPORAL_SCORING"] = cfg["USE_TEMPORAL_SCORING"]
    os.environ["USE_COHORT_BOOST"] = cfg["USE_COHORT_BOOST"]


def call_pipeline(query: str, cohort_year: int | None) -> dict[str, Any]:  # noqa: ARG001
    """Call the LangGraph retrieval graph and return the state values dict.

    cohort_year is embedded in the query text and extracted by Agent 1.
    It is accepted here for documentation/logging purposes only.
    """
    payload: dict[str, Any] = {
        "assistant_id": RETRIEVAL_ASSISTANT_ID,
        "input": {
            "messages": [{"type": "human", "content": query}]
        }
    }
    resp = requests.post(
        f"{LANGGRAPH_URL}/runs/wait",
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("values", data)


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def extract_text(state: dict[str, Any]) -> str:
    """
    Flatten retrieved content for evaluation.
    Includes: final_answer, AI messages, AND reranked chunk content.
    This allows evaluation even when Agent 3 routes to ask_followup.
    """
    parts: list[str] = []

    fa = state.get("final_answer", "") or ""
    if fa:
        parts.append(fa)

    for msg in state.get("messages", []):
        if msg.get("type") == "ai":
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") if isinstance(c, dict) else str(c)
                    for c in content
                )
            if content:
                parts.append(content)

    # Also include reranked chunk content and entity descriptions.
    # This is the primary signal for retrieval evaluation.
    for chunk_wrapper in state.get("reranked_chunks", []):
        chunk = chunk_wrapper[0] if isinstance(chunk_wrapper, list) else chunk_wrapper
        if isinstance(chunk, dict):
            parts.append(chunk.get("content", ""))

    for ent_wrapper in state.get("reranked_entities", []):
        ent = ent_wrapper[0] if isinstance(ent_wrapper, list) else ent_wrapper
        if isinstance(ent, dict):
            parts.append(ent.get("description", ""))
            parts.append(ent.get("entity_name", ""))

    for rel_wrapper in state.get("reranked_relationships", []):
        rel = rel_wrapper[0] if isinstance(rel_wrapper, list) else rel_wrapper
        if isinstance(rel, dict):
            parts.append(rel.get("description", ""))

    # Also include raw retrieved data (before reranking) for coverage
    for item in state.get("retrieved_chunks", []):
        if isinstance(item, dict):
            parts.append(item.get("content", ""))

    return " ".join(parts)


def _normalise(s: str) -> str:
    """Fold Vietnamese diacritics away and lower-case for comparison."""
    s = s.lower()
    s = re.sub(r"[áàảãạăắằẳẵặâấầẩẫậ]", "a", s)
    s = re.sub(r"[éèẻẽẹêếềểễệ]", "e", s)
    s = re.sub(r"[íìỉĩị]", "i", s)
    s = re.sub(r"[óòỏõọôốồổỗộơớờởỡợ]", "o", s)
    s = re.sub(r"[úùủũụưứừửữự]", "u", s)
    s = re.sub(r"[ýỳỷỹỵ]", "y", s)
    s = re.sub(r"[đ]", "d", s)
    return s


def _found(text: str, doc_number: str) -> bool:
    """Return True if doc_number string appears in text (normalised, flexible separators)."""
    needle = _normalise(doc_number.replace("/", r"[/\-_ ]*").replace("đ", "d"))
    try:
        return bool(re.search(needle, _normalise(text)))
    except re.error:
        return doc_number.lower() in text.lower()


def accuracy_at_1(text: str, expected_doc_numbers: list[str]) -> float:
    """1.0 if ANY expected doc number appears anywhere in the response."""
    for dn in expected_doc_numbers:
        if _found(text, dn):
            return 1.0
    return 0.0


def mrr(text: str, expected_doc_numbers: list[str]) -> float:
    """MRR over a single query: 1/rank if any expected doc found, else 0."""
    for i, dn in enumerate(expected_doc_numbers, start=1):
        if _found(text, dn):
            return 1.0 / i
    return 0.0


def ndcg_at_k(text: str, expected_doc_numbers: list[str], k: int = 3) -> float:
    """Approximate NDCG@k treating expected_doc_numbers as graded relevance 1/i."""
    dcg = 0.0
    ideal_dcg = 0.0
    found_count = 0
    for i, dn in enumerate(expected_doc_numbers[:k], start=1):
        rel = 1.0 if _found(text, dn) else 0.0
        dcg += rel / math.log2(i + 1)
        ideal_dcg += 1.0 / math.log2(i + 1)
        if rel:
            found_count += 1
    return (dcg / ideal_dcg) if ideal_dcg > 0 else 0.0


def confound_present(text: str, confounding_doc_numbers: list[str]) -> bool:
    for dn in confounding_doc_numbers:
        if _found(text, dn):
            return True
    return False


# ---------------------------------------------------------------------------
# Single-pair evaluation
# ---------------------------------------------------------------------------

def eval_pair(pair: dict[str, Any], config_name: str, verbose: bool = False) -> dict[str, Any]:
    query = pair["query"]
    cohort_year = pair.get("query_cohort_year")
    expected = pair.get("expected_doc_numbers", [])
    confounding = pair.get("confounding_doc_numbers", [])

    try:
        state = call_pipeline(query, cohort_year)
        text = extract_text(state)
        error = state.get("error")
        pipeline_ok = True
    except Exception as exc:
        text = ""
        error = str(exc)
        pipeline_ok = False

    acc1 = accuracy_at_1(text, expected)
    mrr_score = mrr(text, expected)
    ndcg3 = ndcg_at_k(text, expected, k=3)
    confound = confound_present(text, confounding)

    result = {
        "id": pair["id"],
        "type": pair["type"],
        "config": config_name,
        "query": query[:60],
        "cohort_year": cohort_year,
        "pipeline_ok": pipeline_ok,
        "error": error,
        "acc@1": acc1,
        "mrr": mrr_score,
        "ndcg@3": ndcg3,
        "confound_present": confound,
        "response_snippet": text[:200],
    }
    if verbose:
        status = "HIT" if acc1 == 1.0 else "MISS"
        conf_flag = " [CONFOUND]" if confound else ""
        print(f"    [{status}]{conf_flag} id={pair['id']} acc={acc1:.0f} "
              f"mrr={mrr_score:.2f} ndcg={ndcg3:.2f} — {query[:55]}")
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Temporal ablation evaluation")
    parser.add_argument("--pairs", default="tests/eval/temporal_test_pairs.json")
    parser.add_argument("--type", default=None, help="Filter by type: cohort_specific | amendment_sensitive | general")
    parser.add_argument("--split", default="test", choices=["test", "validation", "all"])
    parser.add_argument("--config", default=None, help="Single config name")
    parser.add_argument("--all-configs", action="store_true", help="Run all 3 ablation configs")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--out", default=None, help="Write JSON results to file")
    args = parser.parse_args()

    if args.all_configs:
        configs_to_run = list(ABLATION_CONFIGS.keys())
    elif args.config:
        configs_to_run = [args.config]
    else:
        configs_to_run = ["System"]

    with open(args.pairs) as f:
        data = json.load(f)

    pairs: list[dict[str, Any]] = data["pairs"]

    if args.split != "all":
        split_ids = set(data.get("split", {}).get(args.split, []))
        pairs = [p for p in pairs if p["id"] in split_ids]

    if args.type:
        pairs = [p for p in pairs if p.get("type") == args.type]

    print(f"Test pairs: {len(pairs)}  split={args.split}  configs={configs_to_run}")
    print()

    all_results: dict[str, list[dict[str, Any]]] = {}

    for config_name in configs_to_run:
        print(f"=== Config: {config_name} — {ABLATION_CONFIGS[config_name]['description']} ===")
        set_env_for_config(config_name)
        time.sleep(1)

        config_results = []
        for pair in pairs:
            result = eval_pair(pair, config_name, verbose=args.verbose or True)
            config_results.append(result)
            time.sleep(2)

        all_results[config_name] = config_results

        acc = sum(r["acc@1"] for r in config_results) / len(config_results)
        avg_mrr = sum(r["mrr"] for r in config_results) / len(config_results)
        avg_ndcg = sum(r["ndcg@3"] for r in config_results) / len(config_results)
        print(f"  acc@1={acc:.2%}  MRR={avg_mrr:.3f}  NDCG@3={avg_ndcg:.3f}")
        print()

    # Win/loss/tie table vs Baseline-S
    if "Baseline-S" in all_results and len(configs_to_run) > 1:
        print("=== WIN / LOSS / TIE vs Baseline-S ===")
        baseline_by_id = {r["id"]: r for r in all_results["Baseline-S"]}
        for config_name in configs_to_run:
            if config_name == "Baseline-S":
                continue
            wins = losses = ties = 0
            for r in all_results[config_name]:
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
            pct = (wins - losses) / total * 100 if total else 0
            print(f"  {config_name:12s}:  W={wins}  L={losses}  T={ties}  net={pct:+.0f}%")
        print()

    # Breakdown by type
    print("=== BREAKDOWN BY TYPE ===")
    pair_types = sorted({p.get("type", "unknown") for p in pairs})
    for t in pair_types:
        print(f"  [{t}]")
        for config_name in configs_to_run:
            subset = [r for r in all_results.get(config_name, []) if r["type"] == t]
            if not subset:
                continue
            acc = sum(r["acc@1"] for r in subset) / len(subset)
            print(f"    {config_name:12s}: acc@1={acc:.2%}  n={len(subset)}")
    print()

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"Results saved to {args.out}")


if __name__ == "__main__":
    main()
