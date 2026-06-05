"""
Naive RAG baseline using LightRAG /query endpoint with mode='naive'.
Sends all 200 pairs directly to LightRAG (vector similarity only, no graph, no reranker).
LightRAG uses its own configured LLM to generate answers.

Usage:
    python naive_rag_baseline.py [--limit N] [--workers N] [--url URL]
"""
import json
import os
import re
import sys
import time
import argparse
import concurrent.futures
from pathlib import Path

LIGHTRAG_URL = os.getenv("LIGHTRAG_URL", "http://localhost:9622")
LIGHTRAG_API_KEY = os.getenv("LIGHTRAG_API_KEY", "HPgDYKcqJX6mufX3FMTQoeXzoVDZKfovUKFVAwSG")

SYSTEM_PROMPT = (
    "Bạn là trợ lý tư vấn về quy định, quy chế của Trường Đại học Công nghệ Thông tin - "
    "ĐHQG TP.HCM (UIT). Khi trả lời, hãy liệt kê số hiệu văn bản/quyết định cụ thể liên quan "
    "(ví dụ: 108/QĐ-ĐHCNTT, 141/QĐ-ĐHCNTT, 09/2022/TT-BGDĐT). "
    "Nếu không biết số hiệu, hãy nói rõ."
)


def normalize_doc_number(doc_num: str) -> str:
    if not doc_num:
        return ""
    s = doc_num.upper().strip()
    # Normalize Vietnamese chars
    replacements = {
        "QĐ": "QD", "ĐHCNTT": "DHCNTT", "ĐHQG": "DHQG",
        "Đ": "D", "đ": "D",
    }
    for src, dst in replacements.items():
        s = s.replace(src, dst)
    # Remove spaces around slashes and dashes
    s = re.sub(r"\s*[-/]\s*", lambda m: m.group().strip(), s)
    return s


def doc_number_in_response(response_text: str, expected_docs: list) -> bool:
    if not expected_docs or not response_text:
        return False
    text_norm = normalize_doc_number(response_text)
    for expected in expected_docs:
        normalized = normalize_doc_number(expected)
        if normalized and normalized in text_norm:
            return True
    return False


def query_lightrag(url: str, query: str, top_k: int = 10) -> str:
    import urllib.request
    payload = json.dumps({
        "query": query,
        "mode": "naive",
        "top_k": top_k,
        "system_prompt": SYSTEM_PROMPT,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/query",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": LIGHTRAG_API_KEY,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("response", "")


def process_pair(pair: dict, lightrag_url: str = LIGHTRAG_URL) -> dict:
    query = pair["query"]
    expected_docs = [normalize_doc_number(d) for d in pair.get("expected_doc_numbers", [])]
    try:
        response_text = query_lightrag(lightrag_url, query)
        is_correct = doc_number_in_response(response_text, expected_docs)
    except Exception as e:
        response_text = f"ERROR: {e}"
        is_correct = False

    return {
        "id": pair["id"],
        "type": pair.get("type", "unknown"),
        "query": query,
        "expected_doc_numbers": expected_docs,
        "response": response_text[:500],
        "correct": is_correct,
    }


def main():
    parser = argparse.ArgumentParser(description="Naive RAG baseline via LightRAG")
    parser.add_argument("--limit", type=int, default=None, help="Limit pairs for testing")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent workers")
    parser.add_argument("--url", default=LIGHTRAG_URL, help="LightRAG base URL")
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()

    lightrag_url = args.url

    base_dir = Path(__file__).parent.parent.parent.parent
    pairs_path = base_dir / "LangGraph/tests/eval/temporal_test_pairs_200.json"
    output_path = Path(args.output) if args.output else Path(__file__).parent / "naive_rag_results.json"

    with open(pairs_path, encoding="utf-8") as f:
        data = json.load(f)
    pairs = data.get("pairs", [])
    if args.limit:
        pairs = pairs[: args.limit]

    print(f"Running naive RAG baseline on {len(pairs)} pairs ({args.workers} workers)...")
    t0 = time.time()

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_pair, p, lightrag_url): p for p in pairs}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            result = fut.result()
            results.append(result)
            status = "OK" if result["correct"] else "FAIL"
            print(f"  [{i}/{len(pairs)}] {status} id={result['id']} type={result['type']}")

    # Sort by id for consistent output
    results.sort(key=lambda r: r["id"])

    # Compute accuracy by type
    correct_total = sum(1 for r in results if r["correct"])
    avg_acc = correct_total / len(results) if results else 0.0

    by_type: dict = {}
    for r in results:
        t = r["type"]
        by_type.setdefault(t, {"correct": 0, "total": 0})
        by_type[t]["total"] += 1
        if r["correct"]:
            by_type[t]["correct"] += 1

    elapsed = time.time() - t0
    print(f"\n=== Naive RAG Baseline (LightRAG mode=naive) ===")
    print(f"  accuracy@1: {avg_acc:.3f}  ({correct_total}/{len(results)})")
    print(f"  elapsed:    {elapsed:.1f}s")
    print(f"\n=== By Type ===")
    for t, counts in sorted(by_type.items()):
        acc = counts["correct"] / counts["total"]
        print(f"  {t:<30}: {acc:.3f}  n={counts['total']}")

    output = {
        "summary": {
            "accuracy@1": avg_acc,
            "model": "lightrag-naive",
            "n_pairs": len(results),
            "correct": correct_total,
            "elapsed_s": elapsed,
        },
        "by_type": {
            t: {"accuracy": c["correct"] / c["total"], "n": c["total"], "correct": c["correct"]}
            for t, c in by_type.items()
        },
        "results": results,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
