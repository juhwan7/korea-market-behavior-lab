import unittest
from datetime import datetime, timezone

from kmb_lab.sources import validate_observation_provenance, validate_source_registry


class SourceContractTests(unittest.TestCase):
    def test_adapter_ready_requires_adapter_and_validation(self):
        payload = {"sources": [{"id": "x", "kind": "primary", "status": "ADAPTER_READY", "adapter": None, "validation": None}]}
        errors = validate_source_registry(payload)
        self.assertTrue(any("adapter" in error for error in errors))
        self.assertTrue(any("validation" in error for error in errors))

    def test_provenance_rejects_as_of_after_retrieval(self):
        obs = {
            "source_id": "x", "source_url": "https://example.com", "source_kind": "primary",
            "as_of": "2026-09-29", "retrieved_at": "2026-09-28T12:00:00Z"
        }
        errors = validate_observation_provenance(obs, now=datetime(2026, 9, 28, 13, tzinfo=timezone.utc))
        self.assertTrue(any("as_of" in error for error in errors))

    def test_provenance_rejects_future_retrieval(self):
        obs = {
            "source_id": "x", "source_url": "https://example.com", "source_kind": "primary",
            "as_of": "2026-09-28", "retrieved_at": "2026-09-28T14:00:00Z"
        }
        errors = validate_observation_provenance(obs, now=datetime(2026, 9, 28, 13, tzinfo=timezone.utc))
        self.assertTrue(any("future" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
