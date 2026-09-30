import unittest

from kmb_lab.pages import CORE_SECTION_MARKERS, render_html
from kmb_lab.pages_korean import human_time, status_label
from kmb_lab.pages_v3 import render_pages


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

    def test_render_is_korean_multipage_and_all_agents_are_visible(self):
        pages = render_pages(self.sample_model())
        self.assertEqual(set(pages), {
            "index.html", "issues.html", "ai-research.html", "stocks.html",
            "smart-money.html", "news.html", "global.html", "lab.html", "system.html",
        })
        combined = "\n".join(pages.values())
        self.assertIn('lang="ko"', pages["index.html"])
        self.assertIn('data-kmb-section="cycle"', pages["index.html"])
        self.assertIn("AI 시장 추론", pages["ai-research.html"])
        for agent in ("AI-A", "AI-B", "AI-C", "AI-D", "AI-E"):
            self.assertIn(agent, combined)
        for marker in CORE_SECTION_MARKERS:
            self.assertIn(f'data-kmb-section="{marker}"', combined)

    def test_user_surface_avoids_raw_json_and_internal_assignments(self):
        pages = render_pages(self.sample_model())
        combined = "\n".join(pages.values())
        self.assertNotIn("[object Object]", combined)
        self.assertNotIn('"evidence_state"', combined)
        self.assertNotIn("production_eligible=", combined)
        self.assertNotIn("<pre>", combined)

    def test_ai_research_filters_include_status_and_topic(self):
        model = self.sample_model()
        model["research_timeline"] = [{
            "agent": "AI-A",
            "at": "2026-09-29T14:55:00+09:00",
            "title": "AI HBM 공급망 가설",
            "result": "HYPOTHESIS",
            "hypothesis": "AI 데이터센터 투자 확대가 HBM 수요로 이어질 가능성",
            "confirmed": ["HBM 공급 확대"],
            "unknown": ["실제 주문량"],
            "handoffs": ["AI-C 정량검증"],
            "related_sectors": ["반도체"],
        }]
        page = render_pages(model)["ai-research.html"]
        self.assertIn('id="research-status"', page)
        self.assertIn('id="research-topic"', page)
        self.assertIn('data-status="검증 중"', page)
        self.assertIn('data-topics="반도체|AI"', page)
        self.assertIn("연구 상태:", page)
        self.assertIn("주제:", page)

    def test_reduced_motion_is_supported(self):
        page = render_html(self.sample_model())
        self.assertIn("prefers-reduced-motion", page)


if __name__ == "__main__":
    unittest.main()
