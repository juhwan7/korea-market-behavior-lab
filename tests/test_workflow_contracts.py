import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class WorkflowContractTests(unittest.TestCase):
    def test_pages_display_layer_includes_korean_renderer_and_all_pages_tests(self):
        text=(ROOT/".github/workflows/pages.yml").read_text(encoding="utf-8")
        self.assertIn("pages(_korean)?", text)
        self.assertIn("tests/test_pages.*", text)

    def test_self_heal_retries_only_first_failed_attempt(self):
        text=(ROOT/".github/workflows/self-heal.yml").read_text(encoding="utf-8")
        self.assertIn("run_attempt == 1", text)
        self.assertIn("rerun-failed-jobs", text)
        self.assertIn("Repeated failure is escalated", text)

    def test_self_heal_watches_core_workflows(self):
        text=(ROOT/".github/workflows/self-heal.yml").read_text(encoding="utf-8")
        for name in ("system-check","pages","canonical-writer"):
            self.assertIn(name,text)

if __name__=="__main__":
    unittest.main()
