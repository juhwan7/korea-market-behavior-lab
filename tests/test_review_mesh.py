import unittest

from kmb_lab.review_mesh import AGENTS, can_close, coverage, validate_review_item


def base_item(risk="CRITICAL", required=None):
    required = required or list(AGENTS)
    return {
        "review_id": "R1",
        "event_type": "code_change",
        "risk_level": risk,
        "owner": "AI-D",
        "required_reviewers": required,
        "optional_reviewers": [a for a in AGENTS if a not in required],
        "reviews": {
            a: {"result": "PASS" if a in required else "NOT_REQUIRED"}
            for a in AGENTS
        },
        "evidence": {
            "commit_sha": "0123456789abcdef0123456789abcdef01234567",
            "actions_result": "success:12345",
            "expected_state_verified": True,
        },
    }


class ReviewMeshTests(unittest.TestCase):
    def test_critical_requires_all_five(self):
        item = base_item()
        del item["reviews"]["AI-E"]
        self.assertTrue(validate_review_item(item))
        self.assertFalse(can_close(item))

    def test_low_can_close_with_owner_only(self):
        item = base_item("LOW", ["AI-D"])
        self.assertFalse(validate_review_item(item))
        self.assertTrue(can_close(item))
        self.assertEqual(coverage(item)["required"], ["AI-D"])

    def test_medium_requires_two_reviewers(self):
        item = base_item("MEDIUM", ["AI-D"])
        self.assertTrue(validate_review_item(item))
        self.assertFalse(can_close(item))

    def test_high_requires_three_reviewers(self):
        item = base_item("HIGH", ["AI-D", "AI-B"])
        self.assertTrue(validate_review_item(item))
        self.assertFalse(can_close(item))

    def test_optional_pending_is_rejected_to_prevent_review_storm(self):
        item = base_item("LOW", ["AI-D"])
        item["reviews"]["AI-A"]["result"] = "PENDING"
        self.assertTrue(validate_review_item(item))

    def test_required_fix_blocks_close(self):
        item = base_item("MEDIUM", ["AI-D", "AI-B"])
        item["reviews"]["AI-B"]["result"] = "FIX_REQUIRED"
        self.assertFalse(can_close(item))

    def test_external_evidence_required(self):
        item = base_item("LOW", ["AI-D"])
        item["evidence"]["expected_state_verified"] = False
        self.assertFalse(can_close(item))

    def test_substitution_is_visible_but_does_not_fake_pass(self):
        item = base_item("MEDIUM", ["AI-D", "AI-C"])
        item["reviews"]["AI-C"] = {"result": "PENDING", "substituted_by": "AI-B"}
        self.assertIn("AI-C", coverage(item)["covered"])
        self.assertFalse(can_close(item))


if __name__ == "__main__":
    unittest.main()
