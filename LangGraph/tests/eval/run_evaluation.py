"""
Temporal-Aware Retrieval Ablation Evaluation

Runs ablation over frozen test pairs.
Conditions (v0.2.0 reranker ablation):
  Baseline-S       : USE_TEMPORAL_SCORING=false  USE_COHORT_BOOST=false  USE_AMENDMENT_OVERRIDE=false
  Baseline-T       : USE_TEMPORAL_SCORING=true   USE_COHORT_BOOST=false  USE_AMENDMENT_OVERRIDE=false
  System           : USE_TEMPORAL_SCORING=true   USE_COHORT_BOOST=true   USE_AMENDMENT_OVERRIDE=false
  System+Amend     : USE_TEMPORAL_SCORING=true   USE_COHORT_BOOST=true   USE_AMENDMENT_OVERRIDE=true

Conditions (v0.3.0 metadata routing):
  v0.3.0_No_Routing: v0.2.0 best config, routing disabled (control)
  v0.3.0_Full      : tri-mode routing enabled (COHORT/AMENDMENT/GENERAL paths)

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

from agent.graphs.query_graph import graph as query_graph

LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "http://localhost:2024")
RETRIEVAL_ASSISTANT_ID = os.getenv("RETRIEVAL_ASSISTANT_ID", "5bbc8364-e383-5087-8a2f-b6d27677f7a1")
REQUEST_TIMEOUT = 120
USE_LOCAL = os.getenv("USE_LOCAL", "true").lower() == "true"


ABLATION_CONFIGS: dict[str, dict[str, str]] = {
    "Baseline-S": {
        "USE_TEMPORAL_SCORING": "false",
        "USE_COHORT_BOOST": "false",
        "USE_AMENDMENT_OVERRIDE": "false",
        "USE_METADATA_ROUTING": "false",
        "description": "Pure semantic reranking",
    },
    "Baseline-T": {
        "USE_TEMPORAL_SCORING": "true",
        "USE_COHORT_BOOST": "false",
        "USE_AMENDMENT_OVERRIDE": "false",
        "USE_METADATA_ROUTING": "false",
        "description": "Temporal scoring, no cohort boost",
    },
    "System": {
        "USE_TEMPORAL_SCORING": "true",
        "USE_COHORT_BOOST": "true",
        "USE_AMENDMENT_OVERRIDE": "false",
        "USE_METADATA_ROUTING": "false",
        "description": "Full system (temporal + cohort)",
    },
    "System+Amend": {
        "USE_TEMPORAL_SCORING": "true",
        "USE_COHORT_BOOST": "true",
        "USE_AMENDMENT_OVERRIDE": "true",
        "USE_METADATA_ROUTING": "false",
        "description": "Full system + amendment override (v0.2.0, no routing)",
    },
    "v0.3.0_No_Routing": {
        "USE_TEMPORAL_SCORING": "true",
        "USE_COHORT_BOOST": "true",
        "USE_AMENDMENT_OVERRIDE": "true",
        "USE_METADATA_ROUTING": "false",
        "description": "v0.2.0 best — reranker-only, routing disabled",
    },
    "v0.3.0_Full": {
        "USE_TEMPORAL_SCORING": "true",
        "USE_COHORT_BOOST": "true",
        "USE_AMENDMENT_OVERRIDE": "true",
        "USE_METADATA_ROUTING": "true",
        "description": "v0.3.0 full tri-mode metadata routing",
    },
}


# ---------------------------------------------------------------------------
# Pipeline invocation
# ---------------------------------------------------------------------------

def set_env_for_config(config_name: str) -> None:
    cfg = ABLATION_CONFIGS[config_name]
    os.environ["USE_TEMPORAL_SCORING"] = cfg["USE_TEMPORAL_SCORING"]
    os.environ["USE_COHORT_BOOST"] = cfg["USE_COHORT_BOOST"]
    os.environ["USE_AMENDMENT_OVERRIDE"] = cfg.get("USE_AMENDMENT_OVERRIDE", "false")
    os.environ["USE_METADATA_ROUTING"] = cfg.get("USE_METADATA_ROUTING", "true")
    print(
        f"[CONFIG] temporal={os.environ['USE_TEMPORAL_SCORING']} "
        f"cohort={os.environ['USE_COHORT_BOOST']} "
        f"amendment={os.environ['USE_AMENDMENT_OVERRIDE']} "
        f"routing={os.environ['USE_METADATA_ROUTING']}"
    )


def call_pipeline(query: str, cohort_year: int | None, config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:  # noqa: ARG001
    """Call the LangGraph retrieval graph and return the state values dict.

    Includes exponential backoff retries for robustness.
    """
    max_retries = 3
    base_delay = 2

    for attempt in range(max_retries + 1):
        try:
            if USE_LOCAL:
                # Call graph locally
                inputs = {"messages": [{"type": "human", "content": query}]}
                
                from agent.config import set_config_overrides, reset_config_overrides
                
                # Default overrides if not provided
                if config_overrides is None:
                    config_overrides = {
                        "use_temporal_scoring": os.environ.get("USE_TEMPORAL_SCORING", "true").lower() == "true",
                        "use_cohort_boost": os.environ.get("USE_COHORT_BOOST", "true").lower() == "true",
                        "use_amendment_override": os.environ.get("USE_AMENDMENT_OVERRIDE", "false").lower() == "true",
                        "use_metadata_routing": os.environ.get("USE_METADATA_ROUTING", "true").lower() == "true"
                    }
                
                # Apply overrides in this thread/context
                token = set_config_overrides(config_overrides)
                try:
                    return query_graph.invoke(inputs)
                finally:
                    reset_config_overrides(token)

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

        except Exception as exc:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                print(f"[RETRY] Attempt {attempt + 1} failed: {exc}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"[ERROR] All {max_retries + 1} attempts failed for query: {query[:50]}...")
                raise exc


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def extract_text(state: dict[str, Any], include_raw: bool = False) -> str:
    """
    Flatten content for evaluation.
    
    By default (include_raw=False), this ONLY includes the final_answer and AI messages.
    This ensures that evaluation reflects what the user actually sees.
    
    If include_raw=True, it includes all retrieved and reranked data (for debugging).
    """
    parts: list[str] = []

    # 1. User-facing content (The ground truth for response evaluation)
    fa = state.get("final_answer", "") or ""
    if fa:
        parts.append(fa)

    messages = state.get("messages", [])
    for msg in messages:
        # Handle both object and dict forms
        m_type = getattr(msg, "type", None) or (msg.get("type") if isinstance(msg, dict) else None)
        m_content = getattr(msg, "content", "") or (msg.get("content", "") if isinstance(msg, dict) else "")
        
        if m_type == "ai":
            if isinstance(m_content, list):
                m_content = " ".join(
                    c.get("text", "") if isinstance(c, dict) else str(c)
                    for c in m_content
                )
            if m_content:
                parts.append(m_content)

    # 2. Raw retrieval data (ONLY for debugging or if specifically requested)
    if include_raw or (not parts): # Include raw if answer is empty to see what was retrieved
        # ...
        # Include reranked chunk content and entity descriptions.
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
    
    # Standardize separators in document numbers (e.g., 141/QD-DHCNTT -> 141/qd-dhcntt)
    # We keep the slash but remove other non-alphanumeric noise around it
    s = re.sub(r"\s+", " ", s)
    return s


def _found(text: str, doc_number: str) -> bool:
    """Return True if doc_number string appears in text (normalised, flexible separators)."""
    # Expected format: "141/QD-DHCNTT"
    # Normalise both
    norm_text = _normalise(text)
    norm_dn = _normalise(doc_number)
    
    # Create a regex that allows flexibility in separators
    # "141/qd-dhcntt" -> "141[\s/\\_\\-]*qd[\s/\\_\\-]*dhcntt"
    parts = re.split(r"[/\\_\\-]", norm_dn)
    pattern = r"[\s/\\_\\-]*".join([re.escape(p) for n, p in enumerate(parts) if p])
    
    try:
        # Check for word boundaries to avoid partial matches (like "14" matching "141")
        return bool(re.search(pattern, norm_text, re.IGNORECASE))
    except re.error:
        return norm_dn in norm_text


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
        if status == "MISS":
            print(f"      Expected: {expected}")
            print(f"      Snippet: {text[:300]}...")
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Temporal ablation evaluation")
    parser.add_argument("--pairs", default="tests/eval/temporal_test_pairs_100.json")
    parser.add_argument("--type", default=None, help="Filter by type: cohort_specific | amendment_sensitive | general")
    parser.add_argument("--split", default="test", choices=["test", "validation", "routing_test", "all"])
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
            result = eval_pair(pair, config_name, verbose=args.verbose)
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
