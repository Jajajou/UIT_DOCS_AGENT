"""
Gemini + Google Search grounding baseline.
Runs synchronously (Batch API doesn't support grounding tools).

Usage:
    GEMINI_API_KEY=xxx python gemini_search_baseline.py
    GEMINI_API_KEY=xxx python gemini_search_baseline.py --limit 20 --workers 3
"""
import json
import os
import re
import sys
import time
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: google-genai not installed. Run: uv pip install google-genai")
    sys.exit(1)

SYSTEM_PROMPT = (
    "Bạn là trợ lý tư vấn về quy định, quy chế của Trường Đại học Công nghệ Thông tin - "
    "ĐHQG TP.HCM (UIT). Khi trả lời, hãy liệt kê số hiệu văn bản/quyết định cụ thể liên quan "
    "(ví dụ: 108/QĐ-ĐHCNTT, 141/QĐ-ĐHCNTT, 09/2022/TT-BGDĐT). "
    "Nếu không biết số hiệu, hãy nói rõ."
)


def normalize_doc_number(doc_num: str) -> str:
    if not doc_num:
        return ""
    doc_num = re.sub(r'\.pdf$', '', doc_num, flags=re.I)
    doc_num = doc_num.strip().upper()
    doc_num = doc_num.replace('Đ', 'D').replace('đ', 'd')
    doc_num = doc_num.replace('-', '/').replace('_', '/')
    doc_num = re.sub(r'/+', '/', doc_num)
    return doc_num


def doc_number_in_response(response_text: str, expected_docs: list) -> bool:
    response_norm = response_text.upper()
    response_norm = response_norm.replace('Đ', 'D').replace('đ', 'd')
    response_norm = response_norm.replace('-', '/').replace('_', '/')
    response_norm = re.sub(r'/+', '/', response_norm)
    for expected in expected_docs:
        norm = normalize_doc_number(expected)
        if not norm:
            continue
        parts = norm.split('/')
        if len(parts) >= 2:
            short_match = '/'.join(parts[:2])
            if short_match in response_norm or norm in response_norm:
                return True
        else:
            if norm in response_norm:
                return True
    return False


def run_single(client, model: str, pair: dict, retry: int = 3) -> dict:
    expected_docs = [normalize_doc_number(d) for d in pair.get('expected_doc_numbers', [])]
    query = pair['query']

    for attempt in range(retry):
        try:
            response = client.models.generate_content(
                model=model,
                contents=query,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.1,
                    max_output_tokens=2048,
                ),
            )
            text = response.text or ""
            is_correct = doc_number_in_response(text, expected_docs)
            return {
                "id": pair["id"],
                "type": pair.get("type", "general"),
                "accuracy@1": 1.0 if is_correct else 0.0,
                "expected_doc_numbers": expected_docs,
                "response_snippet": text[:400],
            }
        except Exception as e:
            if attempt < retry - 1:
                time.sleep(2 ** attempt)
            else:
                return {
                    "id": pair["id"],
                    "type": pair.get("type", "general"),
                    "accuracy@1": 0.0,
                    "expected_doc_numbers": expected_docs,
                    "response_snippet": f"ERROR: {e}",
                }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="gemini_search_results.json")
    parser.add_argument("--model", default="gemini-2.5-flash")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("Error: GEMINI_API_KEY not set.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    base_dir = Path("/Users/jajajou1778/UIT_DOCS_AGENT")
    test_pairs_path = base_dir / "LangGraph/tests/eval/temporal_test_pairs_200.json"
    output_path = base_dir / "LangGraph/tests/eval" / args.output

    with open(test_pairs_path, encoding='utf-8') as f:
        data = json.load(f)
    pairs = data.get('pairs', [])
    if args.limit:
        pairs = pairs[:args.limit]

    print(f"Running {len(pairs)} pairs with {args.model} + Google Search, workers={args.workers}")

    all_results = []
    done = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_single, client, args.model, p): p for p in pairs}
        for fut in as_completed(futures):
            result = fut.result()
            all_results.append(result)
            done += 1
            status = "OK" if result["accuracy@1"] == 1.0 else "FAIL"
            if done % 10 == 0 or done == len(pairs):
                correct_so_far = sum(r["accuracy@1"] for r in all_results)
                print(f"  [{done}/{len(pairs)}] running acc={correct_so_far/done:.3f}  last={status} id={result['id']}")

    correct = sum(r["accuracy@1"] for r in all_results)
    avg_acc = correct / len(all_results) if all_results else 0.0

    by_type: dict = {}
    for r in all_results:
        by_type.setdefault(r['type'], []).append(r['accuracy@1'])

    print(f"\n=== Gemini + Search Baseline ({args.model}) ===")
    print(f"  accuracy@1: {avg_acc:.3f}  ({int(correct)}/{len(all_results)})")
    print("\n=== By Type ===")
    for t, vals in sorted(by_type.items()):
        print(f"  {t:30s}: {sum(vals)/len(vals):.3f}  n={len(vals)}")

    output_data = {
        "summary": {"accuracy@1": avg_acc, "model": args.model + "+search", "n_pairs": len(all_results)},
        "by_type": {t: {"accuracy@1": sum(v)/len(v), "n": len(v)} for t, v in by_type.items()},
        "results": all_results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
