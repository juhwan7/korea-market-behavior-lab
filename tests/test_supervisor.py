import unittest

from kmb_lab.supervisor import is_blocking_handoff, progression_policy


class BlockingHandoffTests(unittest.TestCase):
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
