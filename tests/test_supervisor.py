import unittest

from kmb_lab.supervisor import is_blocking_handoff, progression_policy


class BlockingHandoffTests(unittest.TestCase):
    def test_not_connected_service_is_not_failure(self):
        from datetime import datetime, timezone
        from kmb_lab.supervisor import classify
        state = {"status": "PLANNED", "monitoring_mode": "NOT_CONNECTED", "last_success_at": None}
        self.assertEqual(classify(state, datetime.now(timezone.utc)), "NOT_CONNECTED")

    def test_on_demand_service_does_not_require_periodic_heartbeat(self):
        from datetime import datetime, timezone
        from kmb_lab.supervisor import classify
        state = {"status": "READY", "monitoring_mode": "ON_DEMAND", "last_success_at": None}
        self.assertEqual(classify(state, datetime.now(timezone.utc)), "READY")

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
