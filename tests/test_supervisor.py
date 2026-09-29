import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kmb_lab.supervisor import (
    classify,
    derive_ai_heartbeat,
    is_blocking_handoff,
    progression_policy,
)


class BlockingHandoffTests(unittest.TestCase):
    def test_not_connected_service_is_not_failure(self):
        state = {"status": "PLANNED", "monitoring_mode": "NOT_CONNECTED", "last_success_at": None}
        self.assertEqual(classify(state, datetime.now(timezone.utc)), "NOT_CONNECTED")

    def test_on_demand_service_does_not_require_periodic_heartbeat(self):
        state = {"status": "READY", "monitoring_mode": "ON_DEMAND", "last_success_at": None}
        self.assertEqual(classify(state, datetime.now(timezone.utc)), "READY")

    def test_event_driven_pages_do_not_become_stale_from_old_deploy_time(self):
        state = {
            "status": "HEALTHY",
            "monitoring_mode": "EVENT_DRIVEN",
            "last_success_at": "2026-09-28T00:00:00Z",
            "freshness_target_minutes": 15,
        }
        now = datetime(2026, 9, 29, 7, 30, tzinfo=timezone.utc)
        self.assertEqual(classify(state, now), "HEALTHY")

    def test_ai_heartbeat_is_derived_from_agent_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data/ai/agents").mkdir(parents=True)
            for agent in ("ai-a", "ai-b", "ai-c", "ai-d", "ai-e"):
                (root / f"data/ai/agents/{agent}.json").write_text(
                    json.dumps({"heartbeat_at": "2026-09-29T07:20:00Z"}),
                    encoding="utf-8",
                )
            result = derive_ai_heartbeat(
                root,
                datetime(2026, 9, 29, 7, 30, tzinfo=timezone.utc),
                75,
            )
            self.assertEqual(result["classification"], "HEALTHY")
            self.assertEqual(result["stale_evidence_agents"], [])
            self.assertEqual(result["missing_agents"], [])

    def test_ai_heartbeat_marks_only_actual_stale_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data/ai/agents").mkdir(parents=True)
            for agent in ("ai-a", "ai-b", "ai-c", "ai-d", "ai-e"):
                heartbeat = "2026-09-29T05:00:00Z" if agent == "ai-a" else "2026-09-29T07:20:00Z"
                (root / f"data/ai/agents/{agent}.json").write_text(
                    json.dumps({"heartbeat_at": heartbeat}),
                    encoding="utf-8",
                )
            result = derive_ai_heartbeat(
                root,
                datetime(2026, 9, 29, 7, 30, tzinfo=timezone.utc),
                75,
            )
            self.assertEqual(result["classification"], "OBSERVABILITY_STALE")
            self.assertEqual(result["stale_evidence_agents"], ["AI-A"])

    def test_runtime_evidence_can_be_newer_than_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data/ai/agents").mkdir(parents=True)
            for agent in ("ai-a", "ai-b", "ai-c", "ai-d", "ai-e"):
                (root / f"data/ai/agents/{agent}.json").write_text(
                    json.dumps({
                        "heartbeat_at": "2026-09-29T05:00:00Z",
                        "runtime_evidence": {"last_run_time": "2026-09-29T07:20:00Z"},
                    }),
                    encoding="utf-8",
                )
            result = derive_ai_heartbeat(
                root,
                datetime(2026, 9, 29, 7, 30, tzinfo=timezone.utc),
                75,
            )
            self.assertEqual(result["classification"], "HEALTHY")
            self.assertEqual(result["stale_evidence_agents"], [])
            self.assertIn("scheduler runtime", result["evidence_source"])

    def test_blocked_handoff_stops_dependent_progression(self):
        self.assertTrue(is_blocking_handoff({"status": "BLOCKED_BY_EXTERNAL_WRITE_GUARD"}))

    def test_verification_pending_stops_dependent_progression(self):
        self.assertTrue(is_blocking_handoff({"status": "VERIFICATION_PENDING"}))

    def test_human_required_remains_visible_as_blocking(self):
        self.assertTrue(is_blocking_handoff({"status": "HUMAN_REQUIRED"}))

    def test_recovered_handoff_allows_progression(self):
        self.assertFalse(is_blocking_handoff({"status": "RECOVERED_AND_APPLIED"}))

    def test_local_blocker_does_not_stop_independent_work(self):
        policy = progression_policy([{"status": "FAILED", "scope": "LOCAL"}])
        self.assertTrue(policy["recovery_required"])
        self.assertFalse(policy["dependent_progression_allowed"])
        self.assertTrue(policy["independent_work_allowed"])
        self.assertFalse(policy["global_stop_required"])

    def test_global_stop_is_explicit(self):
        policy = progression_policy([{"status": "FAILED", "scope": "GLOBAL_STOP"}])
        self.assertTrue(policy["global_stop_required"])


if __name__ == "__main__":
    unittest.main()
