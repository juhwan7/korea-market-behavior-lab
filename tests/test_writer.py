import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kmb_lab import writer


class CanonicalWriterTests(unittest.TestCase):
    def test_rejects_workflow_target(self):
        payload = {
            "patch_id": "p1",
            "agent": "AI-C",
            "target": ".github/workflows/x.yml",
            "candidate_path": "data/ai/candidates/ai-c/x.yml",
            "change_type": "create",
            "reason": "test",
            "dependencies": [],
            "tests": [],
            "rollback": "delete created file",
            "status": "READY",
        }
        self.assertTrue(writer.validate_manifest(payload))

    def test_requires_agent_candidate_namespace(self):
        payload = {
            "patch_id": "p1",
            "agent": "AI-C",
            "target": "src/kmb_lab/example.py",
            "candidate_path": "data/ai/candidates/ai-a/example.py",
            "change_type": "create",
            "reason": "test",
            "dependencies": [],
            "tests": [],
            "rollback": "delete created file",
            "status": "READY",
        }
        errors = writer.validate_manifest(payload)
        self.assertTrue(any("candidate_path" in error for error in errors))

    def test_modify_rejects_stale_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            target = root / "src/example.txt"
            target.write_text("old", encoding="utf-8")
            candidate = root / "data/ai/candidates/ai-c/example.txt"
            candidate.parent.mkdir(parents=True)
            candidate.write_text("new", encoding="utf-8")
            manifest = root / "data/ai/patches/p.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({
                "patch_id": "p1",
                "agent": "AI-C",
                "target": "src/example.txt",
                "candidate_path": "data/ai/candidates/ai-c/example.txt",
                "change_type": "modify",
                "base_sha": "deadbeef",
                "reason": "test",
                "dependencies": [],
                "tests": [],
                "rollback": "restore old blob",
                "status": "READY",
            }), encoding="utf-8")
            with patch.object(writer, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "STALE_SHA"):
                    writer.apply_manifest("data/ai/patches/p.json")


if __name__ == "__main__":
    unittest.main()
