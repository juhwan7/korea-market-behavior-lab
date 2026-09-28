import json
import tempfile
import unittest
from pathlib import Path

from kmb_lab import memory


class SharedMemoryTests(unittest.TestCase):
    def _seed(self, root: Path):
        for rel in memory.REQUIRED_MEMORY_PATHS:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if rel.endswith(".jsonl"):
                path.write_text('{"ok": true}\n', encoding="utf-8")
            elif rel.endswith(".md"):
                path.write_text("# briefing\n", encoding="utf-8")
            elif rel.endswith("task-board.json"):
                path.write_text(json.dumps({"tasks": [{"task_id": "t1"}]}), encoding="utf-8")
            elif rel.endswith("writer-lease.json"):
                path.write_text(json.dumps({
                    "role_order": ["AI-D", "AI-E", "AI-B"],
                    "status": "FREE",
                    "writer": None,
                }), encoding="utf-8")
            else:
                path.write_text("{}", encoding="utf-8")

    def test_valid_shared_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            self.assertEqual(memory.validate_shared_memory(root), [])

    def test_duplicate_task_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            (root / "data/ai/task-board.json").write_text(
                json.dumps({"tasks": [{"task_id": "t1"}, {"task_id": "t1"}]}),
                encoding="utf-8",
            )
            errors = memory.validate_shared_memory(root)
            self.assertTrue(any("duplicate task_id" in error for error in errors))

    def test_bad_jsonl_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            (root / "data/ai/events.jsonl").write_text("{bad}\n", encoding="utf-8")
            errors = memory.validate_shared_memory(root)
            self.assertTrue(any("events.jsonl" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
