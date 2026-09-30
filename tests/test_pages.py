import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

from kmb_lab.pages import CORE_SECTION_MARKERS, derive_agent_health, is_material_path, material_fingerprint, verify_live, work_products_model, execution_model


class PagesTests(unittest.TestCase):
    def test_material_path_contract(self):
        self.assertTrue(is_material_path("data/ai/agents/ai-a.json"))
        self.assertTrue(is_material_path("data/ai/CURRENT_BRIEFING.md"))
        self.assertTrue(is_material_path("data/ai/candidates/ai-b/audit.json"))
        self.assertTrue(is_material_path("data/ai/executions/ai-b/run.json"))
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

    def test_fresh_scheduler_runtime_without_output_is_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data/ai/agents").mkdir(parents=True)
            (root / "data/ai/agents/ai-a.json").write_text(json.dumps({
                "agent": "AI-A", "status": "ACTIVE",
                "heartbeat_at": "2026-09-29T06:00:00Z",
                "runtime_evidence": {"enabled": True, "last_run_time": "2026-09-29T06:00:00Z"}
            }), encoding="utf-8")
            (root / "data/ai/task-board.json").write_text('{"tasks":[]}', encoding="utf-8")
            (root / "data/ai/recovery-queue.json").write_text('{"incidents":[]}', encoding="utf-8")
            (root / "data/ai/review-board.json").write_text('{"items":[]}', encoding="utf-8")
            (root / "data/ai/events.jsonl").write_text("", encoding="utf-8")
            rows = derive_agent_health(root, now=datetime(2026, 9, 29, 6, 30, tzinfo=timezone.utc))
            ai_a = next(row for row in rows if row["agent"] == "AI-A")
            self.assertEqual(ai_a["status"], "OBSERVED")
            self.assertEqual(ai_a["execution"], "OBSERVED_NO_FRESH_OUTPUT")

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


    def test_candidate_becomes_visible_work_product_without_becoming_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "data/ai/candidates/ai-b/audit.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "agent": "AI-B",
                "type": "AUDIT",
                "created_at": "2026-09-30T01:00:00Z",
                "major_work": {"title": "인과관계 반증", "result": "FIX_REQUIRED", "summary": "시간순서 오류 가능성"},
                "next_work": "AI-C 정량검증"
            }), encoding="utf-8")
            rows = work_products_model(root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["agent"], "AI-B")
            self.assertEqual(rows[0]["status"], "CANDIDATE")
            self.assertFalse(rows[0]["verified"])
            self.assertEqual(rows[0]["result"], "FIX_REQUIRED")

    def test_execution_model_separates_runtime_from_latest_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agents = [{
                "agent": "AI-B", "execution": "OBSERVED_NO_FRESH_OUTPUT",
                "status": "OBSERVED", "last_execution": "2026-09-30T01:10:00Z",
                "heartbeat_at": "2026-09-30T01:10:00Z", "output_at": None,
                "current_task": "근거 검증"
            }]
            products = [{
                "agent": "AI-B", "title": "이전 감사", "updated_at": "2026-09-30T00:30:00Z",
                "next_work": "새 주장 검증"
            }]
            model = execution_model(root, agents, products)
            current = model["current"][0]
            self.assertEqual(current["status"], "OBSERVED_NO_FRESH_OUTPUT")
            self.assertEqual(current["latest_output"]["title"], "이전 감사")
            self.assertNotEqual(current["last_execution"], current["latest_output"]["updated_at"])

    def test_verify_live_requires_fingerprint_and_core_sections(self):
        sha = "a" * 40
        fingerprint = "f" * 64
        page = sha + fingerprint + "".join(
            f' data-kmb-section="{marker}"' for marker in CORE_SECTION_MARKERS
        )
        with patch("kmb_lab.pages.material_fingerprint", return_value=fingerprint), \
             patch("kmb_lab.pages.fetch_url_json", return_value={
                 "source_commit": sha,
                 "generated_at": "2026-09-29T12:00:00+09:00",
                 "material_fingerprint": fingerprint,
             }), \
             patch("kmb_lab.pages.fetch_url_text", return_value=page):
            result = verify_live("https://example.invalid/", sha, 1, 0)
        self.assertEqual(result["status"], "LIVE")
        self.assertEqual(result["material_fingerprint"], fingerprint)
        self.assertEqual(result["core_sections"], "OK")

    def test_verify_live_rejects_wrong_fingerprint(self):
        sha = "b" * 40
        with patch("kmb_lab.pages.material_fingerprint", return_value="expected"), \
             patch("kmb_lab.pages.fetch_url_json", return_value={
                 "source_commit": sha,
                 "generated_at": "2026-09-29T12:00:00+09:00",
                 "material_fingerprint": "wrong",
             }), \
             patch("kmb_lab.pages.fetch_url_text", return_value=sha):
            with self.assertRaises(SystemExit):
                verify_live("https://example.invalid/", sha, 1, 0)

if __name__ == "__main__":
    unittest.main()
