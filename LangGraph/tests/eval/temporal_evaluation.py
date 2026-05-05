"""
Temporal Document Chain Evaluation (TDCE) Framework

Evaluates the system's ability to handle temporal chains and amendment relationships
with 6 specialized metrics beyond basic accuracy@1.

TDCE Metrics:
1. Amendment Precision@k (AP@k) - Correct amendment document selection
2. Temporal Cascade Hit Rate - Chain traversal success
3. Authority Resolution Score - Choosing correct authority level
4. Cohort Coverage Rate - Targeting right cohort boundaries
5. Amendment Recall@k - Capturing all relevant amendments
6. Temporal Displacement Rate - Avoiding temporal confusion

Usage:
    python tests/eval/temporal_evaluation.py --config System
    python tests/eval/temporal_evaluation.py --config v0.3.0_Full --verbose
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import psycopg2
except ImportError:
    psycopg2 = None

from run_evaluation import extract_text, call_pipeline, accuracy_at_1

# Add src to path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Re-use existing pipeline infrastructure
from agent.config import settings


class TemporalEvaluationRunner:
    """Main runner for TDCE framework with 6 specialized temporal metrics."""

    def __init__(self, config_name: str, verbose: bool = False, mock_mode: bool = False):
        self.config_name = config_name
        self.verbose = verbose
        self.mock_mode = mock_mode
        self.db_conn = None
        self.amendment_chains = self._load_amendment_chains()

    def __del__(self):
        if self.db_conn:
            try:
                self.db_conn.close()
            except Exception:
                pass

    def _get_db_connection(self) -> Any:
        """Get PostgreSQL connection for amendment metadata."""
        if self.mock_mode:
            return None

        if not psycopg2:
            raise ImportError("psycopg2 not available")

        if not self.db_conn:
            try:
                self.db_conn = psycopg2.connect(
                    host=os.getenv('POSTGRES_HOST', 'localhost'),
                    port=os.getenv('POSTGRES_PORT', '5432'),
                    database=os.getenv('POSTGRES_DB', 'lightrag'),
                    user=os.getenv('POSTGRES_USER', 'lightrag'),
                    password=os.getenv('POSTGRES_PASSWORD', 'lightrag123'),
                    connect_timeout=5
                )
            except Exception as e:
                print(f"[WARN] Database connection failed: {e}. Using static chains.")
                return None
        return self.db_conn

    def _load_amendment_chains(self) -> Dict[str, Dict[str, Any]]:
        """Load document amendment relationships from database."""
        if self.mock_mode:
            return self._load_static_chains()

        try:
            conn = self._get_db_connection()
            if not conn:
                return self._load_static_chains()
                
            cur = conn.cursor()

            # Build amendment chains
            cur.execute("""
                SELECT document_number, doc_id, amends_documents, amended_by,
                       cohort_years, valid_from, valid_until
                FROM lightrag_doc_status
                WHERE amends_documents IS NOT NULL OR amended_by IS NOT NULL
            """)

            chains = {}
            for row in cur.fetchall():
                doc_num, doc_id, amends, amended_by, cohorts, valid_from, valid_until = row
                chains[doc_num] = {
                    'doc_id': doc_id,
                    'amends_documents': json.loads(amends) if amends else [],
                    'amended_by': json.loads(amended_by) if amended_by else [],
                    'cohort_years': json.loads(cohorts) if cohorts else [],
                    'valid_from': str(valid_from) if valid_from else None,
                    'valid_until': str(valid_until) if valid_until else None
                }

            cur.close()
            return chains

        except Exception as e:
            print(f"[WARN] Failed to load chains from DB: {e}. Using static chains.")
            return self._load_static_chains()

    def _load_static_chains(self) -> Dict[str, Dict[str, Any]]:
        """Load static amendment chains from JSON file (fallback)."""
        chains_file = Path(__file__).parent / "amendment_chains.json"
        if chains_file.exists():
            with open(chains_file) as f:
                return json.load(f)
        return {}

    # ------------------------------------------------------------------------
    # TDCE Metrics Implementation
    # ------------------------------------------------------------------------

    def amendment_precision_at_k(self, response: str, expected_doc_numbers: List[str],
                                 k: int = 5) -> float:
        """
        Amendment Precision@k - Quality of amendment chain selection.

        Scores documents that correctly identify the latest revision in an
        amendment chain, penalizing selection of superseded versions.
        """
        if not expected_doc_numbers:
            return 0.0

        # Build amendment graphs for expected docs
        expected_chains = set()
        for doc_num in expected_doc_numbers:
            if doc_num in self.amendment_chains:
                # Follow amendment chain upward
                chain = [doc_num]
                visited = set([doc_num])

                # Find amended_by relationships
                for amended_by in self.amendment_chains[doc_num]['amended_by']:
                    if amended_by not in visited:
                        chain.append(amended_by)
                        visited.add(amended_by)

                expected_chains.update(chain)

        if not expected_chains:
            return accuracy_at_1(response, expected_doc_numbers)

        # Count correct amendment selections
        correct_hits = 0
        for doc_num in expected_doc_numbers:
            if doc_num in expected_chains and self._normalise_mentions(response, doc_num):
                correct_hits += 1

        return correct_hits / min(k, len(expected_doc_numbers))

    def temporal_cascade_hit_rate(self, response: str, expected_doc_numbers: List[str]) -> float:
        """
        Temporal Cascade Hit Rate - Success in chain traversal.

        Measures whether the system can follow amendment chains correctly,
        including cases where the expected answer is NOT the latest document.
        """
        if not expected_doc_numbers:
            return 0.0

        # For amendment chains, check if ANY document in the chain is mentioned
        mentioned_chains = set()

        for doc_num in expected_doc_numbers:
            if doc_num in self.amendment_chains:
                # Build complete chain including ancestors
                chain = self._get_amendment_chain(doc_num)

                # Check if any document in chain is mentioned
                for chain_doc in chain:
                    if self._normalise_mentions(response, chain_doc):
                        mentioned_chains.add(doc_num)
                        break

        return 1.0 if mentioned_chains else 0.0

    def authority_resolution_score(self, response: str, expected_doc_numbers: List[str],
                                 pair_type: str) -> float:
        """
        Authority Resolution Score - Choosing correct authority level.

        Measures the system's ability to select the appropriate authority
        level among colliding documents (local vs central, UIT-specific vs DHQG).
        """
        authority_map = {
            'authority_collision': 1.0,
            'local_vs_system': 1.0,
            'notice_override': 0.8,
            'amendment_boundary': 0.6,
            'general': 0.4
        }

        base_confidence = authority_map.get(pair_type, 0.5)

        if accuracy_at_1(response, expected_doc_numbers) > 0:
            return base_confidence

        # Penalty for authority resolution failures
        authority_indicators = [
            'ĐH-CNTT', 'UIT', 'ĐHQG', 'Bo GDĐT', 'Bộ Giáo dục',
            'Trường ĐH', 'TĐT', 'Khoa', 'Ban', 'Phòng'
        ]

        # Check for inappropriate authority mentions
        lower_score = 1.0
        for doc_num in expected_doc_numbers:
            if self._is_uit_specific(doc_num) and self._mentions_higher_authority(response):
                lower_score *= 0.5
            elif self._is_higher_authority(doc_num) and self._mentions_local_authority(response):
                lower_score *= 0.7

        return base_confidence * lower_score

    def cohort_coverage_rate(self, response: str, query_cohort_year: Optional[int],
                           expected_doc_numbers: List[str]) -> float:
        """
        Cohort Coverage Rate - Targeting right cohort boundaries.

        Measures the system's accuracy in selecting documents for specific
        cohort years vs universal rules. Evaluates the documents actually mentioned
        in the response against the query's cohort year.
        """
        if not query_cohort_year:
            return accuracy_at_1(response, expected_doc_numbers)

        mentioned_matching_cohort = 0
        total_mentioned = 0

        for doc_num, info in self.amendment_chains.items():
            if self._normalise_mentions(response, doc_num):
                total_mentioned += 1
                cohorts = info.get('cohort_years', [])
                # Match if no specific cohorts (universal) or cohort explicitly listed
                if not cohorts or query_cohort_year in cohorts:
                    mentioned_matching_cohort += 1

        if total_mentioned == 0:
            # Fallback to whether they got the exact expected document
            return accuracy_at_1(response, expected_doc_numbers)

        return mentioned_matching_cohort / total_mentioned

    def amendment_recall_at_k(self, response: str, expected_doc_numbers: List[str],
                             k: int = 3) -> float:
        """
        Amendment Recall@k - Capturing all relevant amendments.

        Measures how well the system retrieves related amendment documents
        beyond the primary expected answer.
        """
        if not expected_doc_numbers:
            return 0.0

        related_amendments = set()

        for doc_num in expected_doc_numbers:
            if doc_num in self.amendment_chains:
                # Add amending documents
                related_amendments.update(self.amendment_chains[doc_num]['amended_by'] or [])

                # Add documents this one amends
                related_amendments.update(self.amendment_chains[doc_num]['amends_documents'] or [])

        if not related_amendments:
            return accuracy_at_1(response, expected_doc_numbers)

        # Count how many related amendments are mentioned
        found_amendments = 0
        for amendment in related_amendments:
            if self._normalise_mentions(response, amendment):
                found_amendments += 1

        return found_amendments / min(k, len(related_amendments))

    def temporal_displacement_rate(self, response: str, expected_doc_numbers: List[str],
                                 query_cohort_year: Optional[int]) -> float:
        """
        Temporal Displacement Rate - Avoiding temporal confusion.

        Measures the rate at which the system incorrectly selects documents
        from the wrong temporal context (expired, future, or wrong cohort).
        """
        wrong_temporal_mentions = 0

        if not expected_doc_numbers:
            return 0.0

        # Find active temporal boundaries for expected docs
        active_boundaries = set()

        for doc_num in expected_doc_numbers:
            if doc_num in self.amendment_chains:
                doc_info = self.amendment_chains[doc_num]

                # Check if document is active for query cohort
                cohort_years = doc_info.get('cohort_years', [])
                if cohort_years and query_cohort_year and query_cohort_year not in cohort_years:
                    continue

                active_boundaries.add(doc_num)

        if not active_boundaries:
            return 0.0

        # Find all historical and future versions
        all_versions = set()
        for doc_num in expected_doc_numbers:
            if doc_num in self.amendment_chains:
                family = self._get_full_amendment_family(doc_num)
                all_versions.update(family)

        # Count displacement (wrong version mentions)
        mentioned_wrong = 0
        total_mentioned = 0

        for doc_num in all_versions:
            if self._normalise_mentions(response, doc_num):
                total_mentioned += 1
                if doc_num not in active_boundaries:
                    mentioned_wrong += 1

        if total_mentioned == 0:
            return 0.0

        return mentioned_wrong / total_mentioned

    # ------------------------------------------------------------------------
    # Evaluation helper methods
    # ------------------------------------------------------------------------

    def _normalise_mentions(self, response: str, doc_num: str) -> bool:
        """Check if document number is mentioned in response."""
        from run_evaluation import _found
        return _found(response, doc_num)

    def _get_amendment_chain(self, doc_num: str) -> List[str]:
        """Get complete amendment chain including this document and all upwards."""
        chain = [doc_num]

        def _add_upstream(doc: str):
            if doc not in self.amendment_chains:
                return

            for amended_by in self.amendment_chains[doc]['amended_by'] or []:
                if amended_by not in chain:
                    chain.append(amended_by)
                    _add_upstream(amended_by)

        _add_upstream(doc_num)
        return chain

    def _get_full_amendment_family(self, doc_num: str) -> List[str]:
        """Get all documents in the same amendment chain (both past and future)."""
        family = [doc_num]
        
        def _explore(doc: str):
            if doc not in self.amendment_chains:
                return
            
            # Future versions
            for amended_by in self.amendment_chains[doc]['amended_by'] or []:
                if amended_by not in family:
                    family.append(amended_by)
                    _explore(amended_by)
            
            # Past versions
            for amends in self.amendment_chains[doc]['amends_documents'] or []:
                if amends not in family:
                    family.append(amends)
                    _explore(amends)
                    
        _explore(doc_num)
        return family

    def _is_uit_specific(self, doc_num: str) -> bool:
        """Check if document is UIT-specific vs higher authority."""
        uit_patterns = [
            r'.*\/QD[\\-_]?DHCNTT.*',
            r'.*\/QD[\\-_]?UIT.*',
            r'.*UIT.*',
            r'.*ĐH-CNTT.*'
        ]

        for pattern in uit_patterns:
            if re.match(pattern, doc_num, re.IGNORECASE):
                return True
        return False

    def _is_higher_authority(self, doc_num: str) -> bool:
        """Check if document comes from higher authority (Bo, DHQG)."""
        higher_patterns = [
            r'.*\/QĐ\-BGDDT.*',
            r'.*\/QD\-DHQG.*',
            r'.*Bộ.*',
            r'.*Trường D[HC].*'
        ]

        for pattern in higher_patterns:
            if re.match(pattern, doc_num, re.IGNORECASE):
                return True
        return False

    def _mentions_higher_authority(self, response: str) -> bool:
        """Check response mentions higher authority without context."""
        higher_terms = ['bộ giáo dục', 'dhqg', 'đại học quốc gia', 'trường đại học']
        return any(term in response.lower() for term in higher_terms)

    def _mentions_local_authority(self, response: str) -> bool:
        """Check response mentions local authority without context."""
        local_terms = ['uit', 'trường công nghệ thông tin', 'đh-cntt']
        return any(term in response.lower() for term in local_terms)

    def evaluate_pair(self, pair: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Compute TDCE metrics for a single evaluation pair."""
        response = extract_text(state)

        query = pair["query"]
        expected_docs = pair.get("expected_doc_numbers", [])
        query_cohort = pair.get("query_cohort_year")
        pair_type = pair.get("type", "general")

        if self.verbose:
            print(f"Evaluating: {pair['id']} - {pair_type}")

        # Compute all TDCE metrics
        tdce_metrics = {
            "ap@3": self.amendment_precision_at_k(response, expected_docs, k=3),
            "cascade_hit_rate": self.temporal_cascade_hit_rate(response, expected_docs),
            "authority_score": self.authority_resolution_score(response, expected_docs, pair_type),
            "cohort_coverage": self.cohort_coverage_rate(response, query_cohort, expected_docs),
            "ar@3": self.amendment_recall_at_k(response, expected_docs, k=3),
            "displacement_rate": self.temporal_displacement_rate(response, expected_docs, query_cohort)
        }

        return tdce_metrics


def main():
    """Main runner for TDCE evaluation."""
    import argparse

    parser = argparse.ArgumentParser(description="Temporal Document Chain Evaluation (TDCE)")
    parser.add_argument("--pairs", default=None)
    parser.add_argument("--config", default="System")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--output", default=None)
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (no LLM calls)")
    parser.add_argument("--workers", type=int, default=3, help="Number of concurrent workers")

    args = parser.parse_args()

    # Determine pairs path
    pairs_path = args.pairs
    if not pairs_path:
        # Default relative to script
        pairs_path = Path(__file__).parent / "temporal_test_pairs_100.json"
    
    # Load test pairs
    with open(pairs_path) as f:
        data = json.load(f)

    pairs = data["pairs"]

    # Initialize runner
    runner = TemporalEvaluationRunner(args.config, args.verbose, mock_mode=args.mock)

    # Import existing evaluation config
    from run_evaluation import set_env_for_config, ABLATION_CONFIGS
    
    if args.config in ABLATION_CONFIGS:
        set_env_for_config(args.config)
        config_overrides = {
            "use_temporal_scoring": os.environ.get("USE_TEMPORAL_SCORING", "true").lower() == "true",
            "use_cohort_boost": os.environ.get("USE_COHORT_BOOST", "true").lower() == "true",
            "use_amendment_override": os.environ.get("USE_AMENDMENT_OVERRIDE", "false").lower() == "true",
            "use_metadata_routing": os.environ.get("USE_METADATA_ROUTING", "true").lower() == "true"
        }
    else:
        print(f"[WARN] Unknown config {args.config}. Using defaults.")
        config_overrides = None

    print(f"=== TDCE Framework - {args.config} {'[MOCK]' if args.mock else ''} ===")
    print(f"Pairs: {len(pairs)}, Workers: {args.workers}")

    all_results = []

    def process_pair(pair):
        try:
            if args.mock:
                # Return dummy state for metric logic testing
                state = {
                    "final_answer": f"According to document {pair.get('expected_doc_numbers', ['unknown'])[0]}...",
                    "messages": [{"type": "ai", "content": f"Resolved via {pair.get('type')}"}]
                }
            else:
                # Simulate pipeline call (existing infrastructure with retries)
                state = call_pipeline(pair["query"], pair.get("query_cohort_year"), config_overrides=config_overrides)

            # Compute standard metrics
            response = extract_text(state)
            acc1 = accuracy_at_1(response, pair.get("expected_doc_numbers", []))

            # Compute TDCE metrics
            tdce_metrics = runner.evaluate_pair(pair, state)

            result = {
                "id": pair["id"],
                "type": pair.get("type", "general"),
                "config": args.config,
                "accuracy@1": acc1,
                **tdce_metrics
            }
            return result

        except Exception as e:
            if args.verbose:
                print(f"  {pair['id']:2d}: ERROR - {e}")
            return {
                "id": pair["id"],
                "type": pair.get("type", "general"),
                "config": args.config,
                "accuracy@1": 0.0,
                **{k: 0.0 for k in ["ap@3", "cascade_hit_rate", "authority_score",
                                   "cohort_coverage", "ar@3", "displacement_rate"]},
                "error": str(e)
            }

    # Execute concurrently
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_pair, pair): pair for pair in pairs}
        
        for future in as_completed(futures):
            result = future.result()
            all_results.append(result)
            
            if args.verbose:
                p_id = result["id"]
                acc1 = result["accuracy@1"]
                print(f"  {p_id:2d}: acc={acc1:.2f} AP@3={result['ap@3']:.2f} "
                      f"Cascade={result['cascade_hit_rate']:.2f} "
                      f"Authority={result['authority_score']:.2f}")

    # Sort results by ID for consistency
    all_results.sort(key=lambda x: x["id"])

    # Compute averages
    if all_results:
        avg_metrics = {metric: sum(r.get(metric, 0.0) for r in all_results) / len(all_results)
                       for metric in ["accuracy@1", "ap@3", "cascade_hit_rate",
                                     "authority_score", "cohort_coverage", "ar@3", "displacement_rate"]}
    else:
        avg_metrics = {}

    print("\n=== TDCE Summary ===")
    for metric, avg in avg_metrics.items():
        print(f"  {metric:20s}: {avg:.3f}")

    # Group by type
    types = sorted(list(set(r["type"] for r in all_results)))
    print("\n=== By Type ===")
    for type_name in types:
        subset = [r for r in all_results if r["type"] == type_name]
        if not subset: continue
        avg_acc = sum(r["accuracy@1"] for r in subset) / len(subset)
        avg_ap3 = sum(r["ap@3"] for r in subset) / len(subset)
        print(f"  {type_name:20s}: acc={avg_acc:.2f} ap@3={avg_ap3:.2f} n={len(subset)}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({
                "summary": avg_metrics,
                "by_type": {t: [r for r in all_results if r["type"] == t]
                           for t in types},
                "results": all_results
            }, f, ensure_ascii=False, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()