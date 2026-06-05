"""
No-RAG baseline using Gemini Batch API (50% cheaper, async).
Submits all 200 pairs as a JSONL batch job, polls until done, evaluates results.

Usage:
    # Full flow: submit + poll + evaluate
    GEMINI_API_KEY=xxx python gemini_no_rag_baseline.py

    # Submit only, print job name, exit
    GEMINI_API_KEY=xxx python gemini_no_rag_baseline.py --submit-only

    # Resume existing job (skip submit)
    GEMINI_API_KEY=xxx python gemini_no_rag_baseline.py --job-name batches/xxx

    # Dry run: build JSONL only, don't upload
    GEMINI_API_KEY=xxx python gemini_no_rag_baseline.py --dry-run
"""
import json
import os
import re
import sys
import time
import argparse
from pathlib import Path

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

COMPLETED_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}


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


def build_jsonl(pairs: list, jsonl_path: Path, model: str) -> None:
    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for pair in pairs:
            record = {
                "key": str(pair["id"]),
                "request": {
                    "model": f"models/{model}",
                    "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                    "contents": [{"role": "user", "parts": [{"text": pair["query"]}]}],
                    "generationConfig": {
                        "maxOutputTokens": 4096,
                        "temperature": 0.1,
                    },
                },
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"JSONL written: {jsonl_path} ({len(pairs)} requests)")


def evaluate_results(client, batch_job, pairs: list, output_path: Path, model: str) -> None:
    pair_map = {str(p["id"]): p for p in pairs}
    all_results = []
    correct = 0

    # Download result JSONL from dest file
    dest_file = batch_job.dest.file_name
    print(f"Downloading results from: {dest_file}")
    result_bytes = client.files.download(file=dest_file)
    lines = result_bytes.decode('utf-8').strip().split('\n')

    for line in lines:
        if not line.strip():
            continue
        entry = json.loads(line)
        key = entry.get("key", "")
        pair = pair_map.get(key)
        if not pair:
            continue

        expected_docs = [normalize_doc_number(d) for d in pair.get('expected_doc_numbers', [])]
        pair_type = pair.get('type', 'general')

        response_text = ""
        try:
            candidates = entry["response"]["candidates"]
            parts = candidates[0]["content"]["parts"]
            response_text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError):
            pass

        is_correct = doc_number_in_response(response_text, expected_docs)
        if is_correct:
            correct += 1

        all_results.append({
            "id": pair["id"],
            "type": pair_type,
            "accuracy@1": 1.0 if is_correct else 0.0,
            "expected_doc_numbers": expected_docs,
            "response_snippet": response_text[:400],
        })

    avg_acc = correct / len(all_results) if all_results else 0.0

    by_type: dict = {}
    for r in all_results:
        by_type.setdefault(r['type'], []).append(r['accuracy@1'])

    print(f"\n=== No-RAG Baseline ({model}) ===")
    print(f"  accuracy@1: {avg_acc:.3f}  ({correct}/{len(all_results)})")
    print("\n=== By Type ===")
    for t, vals in sorted(by_type.items()):
        print(f"  {t:30s}: {sum(vals)/len(vals):.3f}  n={len(vals)}")

    output_data = {
        "summary": {"accuracy@1": avg_acc, "model": model, "n_pairs": len(all_results)},
        "by_type": {t: {"accuracy@1": sum(v)/len(v), "n": len(v)} for t, v in by_type.items()},
        "results": all_results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="gemini_no_rag_results.json")
    parser.add_argument("--model", default="gemini-2.5-flash")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--submit-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--job-name", default=None)
    parser.add_argument("--poll-interval", type=int, default=30)
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("Error: GEMINI_API_KEY not set.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    base_dir = Path("/Users/jajajou1778/UIT_DOCS_AGENT")
    test_pairs_path = base_dir / "LangGraph/tests/eval/temporal_test_pairs_200.json"
    jsonl_path = base_dir / "LangGraph/tests/eval/gemini_batch_input.jsonl"
    output_path = base_dir / "LangGraph/tests/eval" / args.output

    with open(test_pairs_path, encoding='utf-8') as f:
        data = json.load(f)
    pairs = data.get('pairs', [])
    if args.limit:
        pairs = pairs[:args.limit]

    job_name = args.job_name

    if not job_name:
        build_jsonl(pairs, jsonl_path, args.model)

        if args.dry_run:
            print("Dry run done. JSONL created, not submitted.")
            return

        print("Uploading JSONL...")
        uploaded_file = client.files.upload(
            file=jsonl_path,
            config=types.UploadFileConfig(
                display_name="gemini_no_rag_eval",
                mime_type="application/jsonl",
            ),
        )
        print(f"Uploaded: {uploaded_file.name}")

        batch_job = client.batches.create(
            model=f"models/{args.model}",
            src=uploaded_file.name,
            config={"display_name": "no_rag_baseline_eval"},
        )
        job_name = batch_job.name
        print(f"Batch job submitted: {job_name}")

        if args.submit_only:
            print(f"\nResume later with: --job-name {job_name}")
            return

    # Poll
    print(f"Polling {job_name} every {args.poll_interval}s ...")
    while True:
        batch_job = client.batches.get(name=job_name)
        state = batch_job.state.name
        print(f"  state={state}")
        if state in COMPLETED_STATES:
            break
        time.sleep(args.poll_interval)

    if batch_job.state.name != "JOB_STATE_SUCCEEDED":
        print(f"Job ended with state={batch_job.state.name}. Exiting.")
        sys.exit(1)

    evaluate_results(client, batch_job, pairs, output_path, args.model)


if __name__ == "__main__":
    main()
