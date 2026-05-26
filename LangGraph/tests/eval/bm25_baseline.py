import json
import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Any
import argparse

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    print("Error: rank-bm25 not installed. Run 'uv pip install rank-bm25'")
    sys.exit(1)

def normalize_doc_number(doc_num: str) -> str:
    if not doc_num:
        return ""
    # Strip whitespace, uppercase, - to /
    # Also remove common suffixes like .pdf if they leaked in
    doc_num = re.sub(r'\.pdf$', '', doc_num, flags=re.I)
    return doc_num.strip().upper().replace('-', '/')

def extract_doc_number_from_dirname(dirname: str) -> str:
    # Pattern: 108-qd-dhcntt_... -> 108/QD-DHCNTT
    segment = dirname.split('_')[0]
    
    # Handle patterns like 108-qd-dhcntt
    m = re.match(r'^([\d/-]+)-(.*)$', segment)
    if m:
        num = m.group(1).replace('-', '/')
        prefix = m.group(2).upper().replace('_', '-')
        return f"{num}/{prefix}"
    
    # Fallback for 01_2017_qd-ttg_... -> 01/2017/QD-TTG
    parts = dirname.split('_')
    nums = []
    prefix_parts = []
    for p in parts:
        if re.match(r'^\d+$', p):
            nums.append(p)
        elif p:
            # Check for alphabetic prefix (QD, TT, etc.)
            m_alpha = re.match(r'^([a-zA-Z-]+)', p)
            if m_alpha:
                prefix_parts.append(m_alpha.group(1).upper())
            break
    
    if nums and prefix_parts:
        return "/".join(nums) + "/" + "-".join(prefix_parts)
        
    return segment.upper().replace('-', '/')

def tokenize(text: str) -> List[str]:
    # Simple whitespace split + lowercase
    return re.findall(r'\w+', text.lower())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, default="bm25_results.json")
    args = parser.parse_args()

    # Base path for relative paths
    base_dir = Path("/Users/jajajou1778/UIT_DOCS_AGENT")
    corpus_dir = base_dir / "data/MinerU2.5_ocr_corrected"
    test_pairs_path = base_dir / "LangGraph/tests/eval/temporal_test_pairs_200.json"
    
    if not corpus_dir.exists():
        print(f"Error: Corpus directory not found: {corpus_dir}")
        return
    
    if not test_pairs_path.exists():
        print(f"Error: Test pairs not found at {test_pairs_path}")
        return

    print("Loading corpus...")
    corpus_docs = []
    corpus_doc_numbers = []
    
    for doc_dir in sorted(corpus_dir.iterdir()):
        if not doc_dir.is_dir():
            continue
        
        md_files = list(doc_dir.rglob("*.md"))
        if not md_files:
            continue
            
        md_file = md_files[0]
        try:
            content = md_file.read_text(encoding='utf-8')
            corpus_docs.append(tokenize(content))
            doc_num = normalize_doc_number(extract_doc_number_from_dirname(doc_dir.name))
            corpus_doc_numbers.append(doc_num)
        except Exception as e:
            print(f"Warning: Failed to read {md_file}: {e}")

    if not corpus_docs:
        print("Error: No documents found in corpus.")
        return

    print(f"Indexed {len(corpus_docs)} documents.")
    bm25 = BM25Okapi(corpus_docs)

    print(f"Loading test pairs from {test_pairs_path}...")
    with open(test_pairs_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        pairs = data.get('pairs', [])

    all_results = []
    
    print(f"Running evaluation on {len(pairs)} pairs...")
    for pair in pairs:
        query = pair['query']
        tokenized_query = tokenize(query)
        
        # Get scores and top indices
        scores = bm25.get_scores(tokenized_query)
        top_n = 10
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_n]
        
        retrieved_docs = [corpus_doc_numbers[i] for i in top_indices]
        expected_docs = [normalize_doc_number(d) for d in pair.get('expected_doc_numbers', [])]
        
        # accuracy@1
        is_correct = False
        top1_doc = ""
        if retrieved_docs:
            top1_doc = retrieved_docs[0]
            if top1_doc in expected_docs:
                is_correct = True
        
        all_results.append({
            "id": pair["id"],
            "type": pair.get("type", "general"),
            "accuracy@1": 1.0 if is_correct else 0.0,
            "bm25_top1_doc": top1_doc,
            "expected_doc_numbers": expected_docs,
            "retrieved_top10": retrieved_docs
        })

    # Compute averages
    avg_acc = sum(r["accuracy@1"] for r in all_results) / len(all_results) if all_results else 0
    
    # Group by type
    types = sorted(list(set(r["type"] for r in all_results)))
    by_type = {}
    
    print("\n=== BM25 Baseline Results ===")
    print(f"  accuracy@1: {avg_acc:.3f}")
    print("\n=== By Type ===")
    
    for t in types:
        subset = [r for r in all_results if r["type"] == t]
        type_acc = sum(r["accuracy@1"] for r in subset) / len(subset)
        by_type[t] = subset
        print(f"  {type_name if 'type_name' in locals() else t:20s}: acc={type_acc:.2f} n={len(subset)}")

    output_data = {
        "summary": {"accuracy@1": avg_acc, "ap@3": 0.0, "authority_score": None},
        "by_type": by_type,
        "results": all_results
    }
    
    output_path = Path("LangGraph/tests/eval") / args.output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {output_path}")

if __name__ == "__main__":
    main()
