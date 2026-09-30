import unittest
from kmb_lab.pages_market import render_market_intelligence

class PagesMarketTests(unittest.TestCase):
    def test_sections_news_provenance_and_no_fake_account_claim(self):
        html=render_market_intelligence({
            "strength":{"components":{"price":60},"coverage":{"available":1,"total":5}},
            "flows":{},
            "futures":{"KOSPI200_FUTURES":{"status":"USER_ACTION_REQUIRED","reason":"key"}},
            "global":{"quotes":{},"interpretation":{}},
            "news":{
                "generated_at":"2026-09-30T03:00:00Z",
                "collection_attempted_at":"2026-09-30T03:00:00Z",
                "collection_status":"HEALTHY",
                "sources_checked":4,
                "latest_news_at":"2026-09-30T02:58:00Z",
                "items":[{
                    "headline":"반도체 공급망 뉴스","source":"A신문","source_type":"SECONDARY",
                    "url":"https://example.com/a","published_at":"2026-09-30T02:58:00Z",
                    "topic":"반도체","related_markets":["KOSPI"],"related_sectors":["반도체"],
                    "reason":"가격과 수급 반응 추가 확인"
                }]
            },
            "issues":{"generated_at":"2026-09-30T03:00:00Z","issues":[{
                "issue_id":"GN-1","headline":"반도체 공급망 뉴스","state":"STRENGTHENING",
                "market_bias":"UNDETERMINED","latest_at":"2026-09-30T02:58:00Z",
                "article_count":2,"independent_publishers":2,"publishers":["A신문","B뉴스"],
                "why_important":"반도체 지수 영향 확인 필요","impact_channels":["semiconductor"],
                "related_markets":["KOSPI"],"related_sectors":["반도체"],"next_variables":["외국인 수급"],
                "history":[{"at":"2026-09-30T03:00:00Z","state":"STRENGTHENING","reason":"독립 출처 증가"}],
                "articles":[{"headline":"반도체 공급망 뉴스","source":"A신문","url":"https://example.com/a"}]
            }]},
            "issue_digest":{"collection_status":"HEALTHY","sources_checked":4},
            "news_work_products":[],
            "smart_money":{"items":[]},"unresolved":[],"development_mix":{}
        })
        for marker in ("market-issues","today-news","ai-news-analysis","issue-timeline","market-strength","flows","futures-global","news-issues","smart-money"):
            self.assertIn(f'data-kmb-section="{marker}"',html)
        self.assertIn("왜 중요한가",html)
        self.assertIn("A신문",html)
        self.assertIn("강화",html)
        self.assertIn("실제 특정 계좌",html)

    def test_empty_news_is_explicit_not_fabricated(self):
        html=render_market_intelligence({"news":{},"issues":{},"issue_digest":{},"strength":{},"flows":{},"futures":{},"global":{},"smart_money":{}})
        self.assertIn("현재 확인된 핵심 시장 이슈가 없습니다.",html)
        self.assertIn("임의의 뉴스를 만들지 않습니다",html)

if __name__=='__main__':
    unittest.main()
