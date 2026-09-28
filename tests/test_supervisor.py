import unittest

from kmb_lab.supervisor import is_blocking_handoff


class BlockingHandoffTests(unittest.TestCase):
    def test_blocked_handoff_stops_progression(self):
        self.assertTrue(is_blocking_handoff({"status": "BLOCKED_BY_EXTERNAL_WRITE_GUARD"}))

    def test_verification_pending_stops_progression(self):
        self.assertTrue(is_blocking_handoff({"status": "VERIFICATION_PENDING"}))

    def test_human_required_remains_visible_as_blocking(self):
        self.assertTrue(is_blocking_handoff({"status": "HUMAN_REQUIRED"}))

    def test_recovered_handoff_allows_progression(self):
        self.assertFalse(is_blocking_handoff({"status": "RECOVERED_AND_APPLIED"}))


if __name__ == "__main__":
    unittest.main()
