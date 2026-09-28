import unittest

from kmb_lab.discovery import validate_candidate
from kmb_lab.quant import (
    conditional_probability,
    model_range,
    reconcile_model_ranges,
    validate_quant_candidate,
)


class DiscoveryEvidenceGateTests(unittest.TestCase):
    def test_confirmed_candidate_requires_non_empty_facts(self):
        candidate = {
            "evidence_state": "CONFIRMED",
            "observed_facts": [],
            "hypothesis": "x",
            "counter_hypotheses": ["y"],
            "invalidation_conditions": ["z"],
        }
        self.assertIn("CONFIRMED requires non-empty observed_facts", validate_candidate(candidate))


class QuantGateTests(unittest.TestCase):
    def test_hypothesis_cannot_enter_confirmed_quant_pipeline(self):
        candidate = {
            "evidence_state": "HYPOTHESIS",
            "observed_facts": [{"source_kind": "secondary"}],
        }
        errors = validate_quant_candidate(candidate)
        self.assertIn("quant input requires CONFIRMED evidence_state", errors)

    def test_no_sample_means_no_probability(self):
        result = conditional_probability(0, 0)
        self.assertEqual(result["evidence_state"], "UNKNOWN")
        self.assertIsNone(result["probability"])

    def test_conflicting_model_ranges_are_not_forced_into_one_number(self):
        results = [
            model_range("price_absorption", 10, 20),
            model_range("turnover_retention", 30, 40),
        ]
        combined = reconcile_model_ranges(results)
        self.assertEqual(combined["agreement"], "CONFLICT")
        self.assertIsNone(combined["consensus_range"])

    def test_overlapping_ranges_keep_only_shared_interval(self):
        results = [
            model_range("price_absorption", 10, 25),
            model_range("volume_profile", 20, 30),
        ]
        combined = reconcile_model_ranges(results)
        self.assertEqual(combined["agreement"], "OVERLAP")
        self.assertEqual(combined["consensus_range"], {"low": 20.0, "high": 25.0})


if __name__ == "__main__":
    unittest.main()
