import unittest
import json
from pathlib import Path
import sys

# Add src to path
ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests/eval"))

from temporal_evaluation import TemporalEvaluationRunner

class TestTDCEMetrics(unittest.TestCase):
    def setUp(self):
        # Initialize runner in mock mode with a simple static chain
        self.runner = TemporalEvaluationRunner(config_name="Test", mock_mode=True)
        # Mock amendment chains for testing
        self.runner.amendment_chains = {
            "101/QD": {
                "amended_by": ["102/QD"],
                "amends_documents": [],
                "cohort_years": [2015, 2016]
            },
            "102/QD": {
                "amended_by": [],
                "amends_documents": ["101/QD"],
                "cohort_years": [2017, 2018]
            }
        }

    def test_amendment_precision(self):
        # Case: Returns the latest document in the chain
        response = "As per 102/QD, students must..."
        expected = ["102/QD"]
        score = self.runner.amendment_precision_at_k(response, expected)
        self.assertEqual(score, 1.0)

        # Case: Returns a superseded document
        response = "As per 101/QD, students must..."
        expected = ["102/QD"] # We expected the latest
        score = self.runner.amendment_precision_at_k(response, expected)
        # 101 is in the chain of 102, so it might be partially accepted or penalized
        # Current implementation: checks if doc_num is in expected_chains and mentioned
        self.assertEqual(score, 0.0) # Correct: 101 != 102

    def test_cohort_coverage(self):
        # Case: Correct cohort match
        response = "Rules for K2015 are in 101/QD"
        expected = ["101/QD"]
        score = self.runner.cohort_coverage_rate(response, 2015, expected)
        self.assertEqual(score, 1.0)

        # Case: Incorrect cohort (K2017 should use 102/QD)
        response = "Rules for K2017 are in 101/QD"
        expected = ["102/QD"]
        score = self.runner.cohort_coverage_rate(response, 2017, expected)
        # If response doesn't mention expected 102/QD, accuracy_at_1 returns 0
        self.assertEqual(score, 0.0)

    def test_displacement_rate(self):
        # Case: Mentions both current and expired versions (Displacement!)
        # 102/QD is active for 2018, 101/QD is expired.
        response = "See 102/QD and the old 101/QD"
        expected = ["102/QD"]
        rate = self.runner.displacement_rate = self.runner.temporal_displacement_rate(response, expected, 2018)
        # versions = {101, 102}. active = {102}. 
        # mentions = {101, 102}. wrong = {101}. 
        # total_mentioned = 2. rate = 0.5
        self.assertEqual(rate, 0.5)

if __name__ == '__main__':
    unittest.main()
