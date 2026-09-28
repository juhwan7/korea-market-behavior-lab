import unittest

from kmb_lab.review_mesh import AGENTS, can_close, coverage, validate_review_item


def base_item():
    return {
        "review_id": "R1",
        "event_type": "code_change",
        "reviews": {a: {"result": "PASS"} for a in AGENTS},
        "evidence": {
            "commit_sha": "abc",
            "actions_result": "success",
            "expected_state_verified": True,
        },
    }


class ReviewMeshTests(unittest.TestCase):
    def test_all_five_required(self):
        item = base_item()
        del item["reviews"]["AI-E"]
        self.assertTrue(validate_review_item(item))
        self.assertFalse(can_close(item))

    def test_fix_required_blocks_close(self):
        item = base_item()
        item["reviews"]["AI-B"]["result"] = "FIX_REQUIRED"
        self.assertFalse(can_close(item))

    def test_external_evidence_required(self):
        item = base_item()
        item["evidence"]["expected_state_verified"] = False
        self.assertFalse(can_close(item))

    def test_all_pass_can_close(self):
        self.assertTrue(can_close(base_item()))

    def test_substitution_is_visible_but_does_not_fake_pass(self):
        item = base_item()
        item["reviews"]["AI-C"] = {"result": "PENDING", "substituted_by": "AI-B"}
        self.assertIn("AI-C", coverage(item)["covered"])
        self.assertFalse(can_close(item))


if __name__ == "__main__":
    unittest.main()
