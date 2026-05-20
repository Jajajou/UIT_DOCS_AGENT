import json
import sys
import numpy as np
from pathlib import Path
from typing import List

def aggregate(file_paths: List[str]):
    all_summaries = []
    by_type_data = {} # type -> list of run_type_acc
    type_counts = {}  # type -> n (number of pairs)
    
    # Sort file paths to ensure deterministic order (first file for metadata)
    file_paths = sorted(file_paths)
    
    for path in file_paths:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                all_summaries.append(data['summary'])
                
                for t, results in data.get('by_type', {}).items():
                    if t not in by_type_data:
                        by_type_data[t] = []
                        type_counts[t] = len(results)
                    
                    # Compute averages for this run for this type
                    if results:
                        run_type_acc = np.mean([r.get('accuracy@1', 0.0) for r in results])
                        by_type_data[t].append(run_type_acc)
        except Exception as e:
            print(f"Warning: Failed to process {path}: {e}")

    if not all_summaries:
        print("No valid results found.")
        return

    metrics = ["accuracy@1", "ap@3", "authority_score"]
    
    report_lines = []
    report_lines.append("| Metric          | Mean  | Std   |")
    report_lines.append("|-----------------|-------|-------|")
    
    for m in metrics:
        vals = [s.get(m, 0.0) for s in all_summaries]
        mean = np.mean(vals)
        std = np.std(vals)
        report_lines.append(f"| {m:15s} | {mean:.3f} | {std:.3f} |")
    
    report_lines.append("")
    report_lines.append("| Type                | Mean acc@1 | n  |")
    report_lines.append("|---------------------|------------|----|")
    
    for t in sorted(by_type_data.keys()):
        vals = by_type_data[t]
        mean = np.mean(vals)
        n = type_counts[t]
        report_lines.append(f"| {t:19s} | {mean:.3f}      | {n:2d} |")

    report_content = "\n".join(report_lines)
    print(report_content)
    
    output_path = Path(file_paths[0]).parent / "aggregate_report.md"
    output_path.write_text(report_content, encoding='utf-8')
    print(f"\nReport saved to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python aggregate_results.py results_*.json")
    else:
        # Expand wildcards if shell didn't do it (e.g. if passed as a single string)
        import glob
        expanded_paths = []
        for arg in sys.argv[1:]:
            if '*' in arg:
                expanded_paths.extend(glob.glob(arg))
            else:
                expanded_paths.append(arg)
        
        if not expanded_paths:
            print("No files found matching patterns.")
        else:
            aggregate(expanded_paths)
