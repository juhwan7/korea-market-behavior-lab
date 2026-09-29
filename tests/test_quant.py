import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from kmb_lab.discovery import validate_candidate
from kmb_lab.quant import conditional_probability, model_range, reconcile_model_ranges, validate_quant_candidate


def valid_fact():
    return {
        "source_id": "krx",
        "source_url": "https://data.krx.co.kr/",
        "source_kind": "primary",
        "as_of": "2026-09-29T06:00:00Z",
        "retrieved_at": "2026-09-29T06:01:00Z",
    }


class DiscoveryEvidenceGateTests(unittest.TestCase):
    def test_confirmed_candidate_requires_non_empty_facts(self):
        candidate = {"evidence_state": "CONFIRMED", "observed_facts": [], "hypothesis": "x", "counter_hypotheses": ["y"], "invalidation_conditions": ["z"]}
        self.assertIn("CONFIRMED requires non-empty observed_facts", validate_candidate(candidate))


class QuantGateTests(unittest.TestCase):
    def test_hypothesis_cannot_enter_confirmed_quant_pipeline(self):
        candidate = {"evidence_state": "HYPOTHESIS", "observed_facts": [{"source_kind": "secondary"}]}
        self.assertIn("quant input requires CONFIRMED evidence_state", validate_quant_candidate(candidate))

    @patch("kmb_lab.sources.datetime")
    def test_valid_primary_provenance_passes(self, dt):
        dt.now.return_value = datetime(2026, 9, 29, 7, 0, tzinfo=timezone.utc)
        dt.fromisoformat.side_effect = datetime.fromisoformat
        candidate = {"evidence_state": "CONFIRMED", "observed_facts": [valid_fact()]}
        self.assertEqual(validate_quant_candidate(candidate), [])

    def test_missing_provenance_is_rejected(self):
        candidate = {"evidence_state": "CONFIRMED", "observed_facts": [{"source_kind": "primary"}]}
        self.assertTrue(any("missing provenance fields" in e for e in validate_quant_candidate(candidate)))

    def test_invalid_timestamp_is_rejected(self):
        fact = valid_fact(); fact["as_of"] = "not-a-time"
        errors = validate_quant_candidate({"evidence_state": "CONFIRMED", "observed_facts": [fact]})
        self.assertTrue(any("invalid as_of timestamp" in e for e in errors))

    def test_as_of_after_retrieved_at_is_rejected(self):
        fact = valid_fact(); fact["as_of"] = "2026-09-29T06:02:00Z"
        errors = validate_quant_candidate({"evidence_state": "CONFIRMED", "observed_facts": [fact]})
        self.assertTrue(any("as_of must not be after retrieved_at" in e for e in errors))

    def test_future_retrieved_at_is_rejected(self):
        fact = valid_fact(); fact["retrieved_at"] = "2999-01-01T00:00:00Z"
        errors = validate_quant_candidate({"evidence_state": "CONFIRMED", "observed_facts": [fact]})
        self.assertTrue(any("retrieved_at must not be in the future" in e for e in errors))

    def test_no_sample_means_no_probability(self):
        result = conditional_probability(0, 0)
        self.assertEqual(result["evidence_state"], "UNKNOWN")
        self.assertIsNone(result["probability"])

    def test_conflicting_model_ranges_are_not_forced_into_one_number(self):
        combined = reconcile_model_ranges([model_range("price_absorption", 10, 20), model_range("turnover_retention", 30, 40)])
        self.assertEqual(combined["agreement"], "CONFLICT")
        self.assertIsNone(combined["consensus_range"])

    def test_overlapping_ranges_keep_only_shared_interval(self):
        combined = reconcile_model_ranges([model_range("price_absorption", 10, 25), model_range("volume_profile", 20, 30)])
        self.assertEqual(combined["agreement"], "OVERLAP")
        self.assertEqual(combined["consensus_range"], {"low": 20.0, "high": 25.0})


if __name__ == "__main__":
    unittest.main()
