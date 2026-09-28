import unittest
from datetime import datetime, timedelta, timezone

from kmb_lab.state import canonical_is_newer
from kmb_lab.supervisor import classify


class StateTests(unittest.TestCase):
    def test_canonical_time_must_move_forward(self):
        self.assertTrue(canonical_is_newer("2026-09-28T10:10:00Z", "2026-09-28T10:00:00Z"))
        self.assertFalse(canonical_is_newer("2026-09-28T09:59:00Z", "2026-09-28T10:00:00Z"))

    def test_explicit_failure_requires_recovery(self):
        now = datetime.now(timezone.utc)
        service = {"status": "failed", "freshness_target_minutes": 10, "last_success_at": now.isoformat()}
        self.assertEqual(classify(service, now), "RECOVERY_REQUIRED")

    def test_old_success_is_stale(self):
        now = datetime.now(timezone.utc)
        service = {
            "status": "healthy",
            "freshness_target_minutes": 10,
            "last_success_at": (now - timedelta(minutes=11)).isoformat(),
        }
        self.assertEqual(classify(service, now), "STALE")


if __name__ == "__main__":
    unittest.main()
