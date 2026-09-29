import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kmb_lab.pages import derive_agent_health, is_material_path, material_fingerprint


class PagesTests(unittest.TestCase):
    def test_material_path_contract(self):
        self.assertTrue(is_material_path("data/ai/agents/ai-a.json"))
        self.assertTrue(is_material_path("data/ai/CURRENT_BRIEFING.md"))
        self.assertTrue(is_material_path("data/system/services.json"))
        self.assertTrue(is_material_path("data/research/research-queue.json"))
        self.assertFalse(is_material_path("data/ai/failed-attempts.jsonl"))
        self.assertFalse(is_material_path("docs/notes.md"))

    def test_active_string_without_runtime_evidence_is_degraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data/ai/agents").mkdir(parents=True)
            (root / "data/ai/agents/ai-a.json").write_text(json.dumps({"agent": "AI-A", "status": "ACTIVE", "last_progress_at": None}), encoding="utf-8")
            (root / "data/ai/task-board.json").write_text('{"tasks":[]}', encoding="utf-8")
            (root / "data/ai/recovery-queue.json").write_text('{"incidents":[]}', encoding="utf-8")
            (root / "data/ai/review-board.json").write_text('{"items":[]}', encoding="utf-8")
            (root / "data/ai/events.jsonl").write_text("", encoding="utf-8")
            rows = derive_agent_health(root, now=datetime(2026, 9, 29, 1, 0, tzinfo=timezone.utc))
            ai_a = next(row for row in rows if row["agent"] == "AI-A")
            self.assertEqual(ai_a["status"], "DEGRADED")
            self.assertEqual(ai_a["execution"], "STATE MISMATCH")
            self.assertEqual(ai_a["heartbeat"], "MISSING")
            self.assertEqual(ai_a["output"], "MISSING")

    def test_material_fingerprint_changes_with_visible_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "data/ai/CURRENT_BRIEFING.md"
            path.parent.mkdir(parents=True)
            path.write_text("A", encoding="utf-8")
            before = material_fingerprint(root)
            path.write_text("B", encoding="utf-8")
            after = material_fingerprint(root)
            self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
