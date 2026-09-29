import unittest

from kmb_lab.pages import CORE_SECTION_MARKERS, render_html
from kmb_lab.pages_korean import human_time, status_label


class KoreanPagesTests(unittest.TestCase):
    def sample_model(self):
        return {
            "generated_at": "2026-09-29T15:00:00+09:00",
            "source_commit": "a" * 40,
            "material_fingerprint": "f" * 64,
            "freshness": {"label": "LIVE"},
            "briefing": {
                "지금 가장 중요한 시장 변화": ["공식 시장 데이터 연결을 확인 중입니다."],
                "현재 문제": ["실시간 상태 연결을 개선 중입니다."],
                "다음 우선순위": ["공식 데이터 출처를 추가 확인합니다."],
            },
            "market": {"KOSPI": "UNKNOWN", "Behavior Event": "UNKNOWN"},
            "agents": [
                {"agent": "AI-A", "status": "ACTIVE", "last_execution": "2026-09-29T14:58:00+09:00", "last_result": "candidate sample", "current_task": "market discovery"},
                {"agent": "AI-B", "status": "DEGRADED", "last_execution": None, "last_result": "No runtime output evidence", "current_task": "UNKNOWN"},
                {"agent": "AI-C", "status": "ACTIVE", "last_execution": "2026-09-29T14:57:00+09:00", "last_result": "review sample", "current_task": "UNKNOWN"},
                {"agent": "AI-D", "status": "ACTIVE", "last_execution": "2026-09-29T14:59:00+09:00", "last_result": "Pages deploy", "current_task": "Make GitHub Pages follow material canonical state"},
                {"agent": "AI-E", "status": "ACTIVE", "last_execution": "2026-09-29T14:56:00+09:00", "last_result": "review sample", "current_task": "UNKNOWN"},
            ],
            "activity": [{"at": "2026-09-29T14:59:00+09:00", "agent": "AI-D", "title": "Pages deploy verification", "detail": {"status": "SUCCESS"}}],
            "review": {"items": []},
            "recovery": {"incidents": []},
            "tasks": {"tasks": []},
            "experiments": {"experiments": [{"id": "EXP-C-001", "name": "Virtual Position Range Contract v0", "status": "SHADOW", "sample_count": 0, "production_eligible": False}]},
            "research": {"items": []},
            "workflows": {"latest": {"pages": {"conclusion": "success", "created_at": "2026-09-29T14:59:00+09:00", "head_sha": "a" * 40, "id": 123}}},
        }

    def test_status_labels_are_user_friendly_korean(self):
        self.assertEqual(status_label("ACTIVE"), "정상 작동 중")
        self.assertEqual(status_label("STATE MISMATCH"), "표시 상태와 실제 실행 증거가 다름")
        self.assertEqual(status_label("SHADOW"), "실전 반영 전 검증 중")

    def test_human_time(self):
        self.assertEqual(human_time("2026-09-29T14:57:00+09:00", "2026-09-29T15:00:00+09:00"), "3분 전")

    def test_render_contains_korean_cycle_and_all_agents(self):
        page = render_html(self.sample_model())
        self.assertIn('lang="ko"', page)
        self.assertIn('data-kmb-section="cycle"', page)
        self.assertIn("5개 AI 연구 순환", page)
        for agent in ("AI-A", "AI-B", "AI-C", "AI-D", "AI-E"):
            self.assertIn(agent, page)
        for marker in CORE_SECTION_MARKERS:
            self.assertIn(f'data-kmb-section="{marker}"', page)

    def test_user_surface_avoids_raw_json_and_internal_assignments(self):
        page = render_html(self.sample_model())
        self.assertNotIn("[object Object]", page)
        self.assertNotIn('"evidence_state"', page)
        self.assertNotIn("production_eligible=", page)
        self.assertNotIn("<pre>", page)
        self.assertIn("아직 사용하지 않음", page)

    def test_reduced_motion_is_supported(self):
        page = render_html(self.sample_model())
        self.assertIn("prefers-reduced-motion", page)


if __name__ == "__main__":
    unittest.main()
