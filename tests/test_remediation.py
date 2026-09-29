import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kmb_lab.remediation import (
    approval_level,
    classify_error,
    incident_fingerprint,
    scan_repository,
    summarize_failed_jobs,
    validate_registries,
)


class RemediationTests(unittest.TestCase):
    def seed(self, root: Path):
        reg = root / "data/ai/remediation"
        reg.mkdir(parents=True)
        (reg / "policy.json").write_text("{}", encoding="utf-8")
        (reg / "error-signatures.json").write_text('{"signatures":[]}', encoding="utf-8")
        (reg / "prevention-registry.json").write_text("{}", encoding="utf-8")
        (reg / "known-fixes.json").write_text(json.dumps({"fixes": [
            {"fix_id": "f1", "incident_family": "ACTION_FAILURE", "enabled": True,
             "execution_mode": "DETERMINISTIC", "success_rate": 1, "sample_count": 2}
        ]}), encoding="utf-8")
        (root / "data/system").mkdir(parents=True)
        (root / "data/system/services.json").write_text(json.dumps({"services": [
            {"id": "github-pages", "status": "UNKNOWN", "last_success_at": None, "owner": "D"}
        ]}), encoding="utf-8")
        (root / "data/ai/agents").mkdir(parents=True)
        for agent in ("ai-a", "ai-b", "ai-c", "ai-d", "ai-e"):
            (root / f"data/ai/agents/{agent}.json").write_text(
                json.dumps({"agent": agent.upper(), "status": "ACTIVE", "last_progress_at": None}),
                encoding="utf-8")
        (root / "data/ai/task-board.json").write_text('{"tasks":[]}', encoding="utf-8")
        (root / "data/ai/review-board.json").write_text('{"items":[]}', encoding="utf-8")
        (root / "data/ai/recovery-queue.json").write_text('{"incidents":[]}', encoding="utf-8")
        (root / "data/ai/events.jsonl").write_text("", encoding="utf-8")

    def test_fingerprint_normalizes_sha_and_ids(self):
        a = incident_fingerprint("pages", "ACTION_FAILURE", "sha abcdef1234567890 run 123456789 failed")
        b = incident_fingerprint("pages", "ACTION_FAILURE", "sha deadbeef12345678 run 987654321 failed")
        self.assertEqual(a, b)

    def test_classification_and_gate(self):
        self.assertEqual(classify_error("STALE_SHA"), "STALE_SHA")
        self.assertEqual(classify_error("invalid JSON parse"), "JSON_FAILURE")
        self.assertEqual(classify_error("OAuth permission required"), "EXTERNAL_PERMISSION_REQUIRED")
        self.assertEqual(approval_level("EXTERNAL_PERMISSION_REQUIRED"), "L3")

    def test_scan_detects_real_evidence_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.seed(root)
            result = scan_repository(root, now=datetime(2026, 9, 29, 6, tzinfo=timezone.utc))
            families = {x["family"] for x in result["issues"]}
            self.assertIn("SERVICE_TELEMETRY_UNINITIALIZED", families)
            self.assertIn("AGENT_STALE", families)

    def test_registry_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.seed(root)
            self.assertEqual(validate_registries(root), [])

    def test_registry_signature_is_used_by_classifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.seed(root)
            registry = root / "data/ai/remediation/error-signatures.json"
            registry.write_text(json.dumps({"signatures": [{
                "signature_id": "custom",
                "family": "DATA_STALE",
                "patterns": ["banana clock drift"]
            }]}), encoding="utf-8")
            self.assertEqual(
                classify_error("BANANA CLOCK DRIFT detected", root=root),
                "DATA_STALE",
            )

    def test_expired_recovery_lease_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.seed(root)
            services = root / "data/system/services.json"
            services.write_text(json.dumps({"services": [{
                "id": "github-pages",
                "status": "HEALTHY",
                "last_success_at": "2026-09-29T05:59:00Z",
                "owner": "D",
                "recovery_owner": "AI-D",
                "lease_until": "2026-09-29T05:30:00Z"
            }]}), encoding="utf-8")
            (root / "data/ai/writer-lease.json").write_text(
                '{"status":"FREE","writer":null,"lease_until":null}', encoding="utf-8")
            result = scan_repository(root, now=datetime(2026, 9, 29, 6, tzinfo=timezone.utc))
            self.assertIn("LEASE_EXPIRED", {x["family"] for x in result["issues"]})

    def test_planned_not_connected_service_is_not_fake_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.seed(root)
            services = root / "data/system/services.json"
            services.write_text(json.dumps({"services": [{
                "id": "market-data",
                "status": "PLANNED",
                "monitoring_mode": "NOT_CONNECTED",
                "last_success_at": None,
                "owner": "A"
            }]}), encoding="utf-8")
            result = scan_repository(root, now=datetime(2026, 9, 29, 6, tzinfo=timezone.utc))
            self.assertNotIn(
                "SERVICE_TELEMETRY_UNINITIALIZED",
                {x["family"] for x in result["issues"]},
            )

    def test_failed_job_summary_records_exact_step(self):
        rows = summarize_failed_jobs({"jobs": [{
            "id": 99,
            "name": "build",
            "conclusion": "failure",
            "steps": [
                {"number": 1, "name": "checkout", "conclusion": "success"},
                {"number": 2, "name": "Run tests", "conclusion": "failure"},
            ],
        }]})
        self.assertEqual(rows[0]["job"], "build")
        self.assertEqual(rows[0]["failed_steps"][0]["name"], "Run tests")

    def test_registry_validation_rejects_invalid_signature_regex(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.seed(root)
            path = root / "data/ai/remediation/error-signatures.json"
            path.write_text(json.dumps({"signatures": [{
                "family": "BROKEN",
                "patterns": ["("]
            }]}), encoding="utf-8")
            self.assertTrue(any("invalid regex" in x for x in validate_registries(root)))


if __name__ == "__main__":
    unittest.main()
