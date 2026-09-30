import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from kmb_lab.adapters.google_news import parse_rss, dedupe_and_cluster, classify_channels
from kmb_lab.pipeline import _merge_issue_history, _is_recent_news_item, _enrich_issue_market_reactions, collect_news

XML='''<rss><channel><item><title>반도체 수출 규제 논의 - A신문</title><link>https://a</link><pubDate>Wed, 30 Sep 2026 01:00:00 GMT</pubDate><source>A신문</source></item><item><title>반도체 수출 규제 논의 확대 - B뉴스</title><link>https://b</link><pubDate>Wed, 30 Sep 2026 01:02:00 GMT</pubDate><source>B뉴스</source></item></channel></rss>'''

class NewsTests(unittest.TestCase):
    def test_rss_normalized_schema_and_cluster(self):
        items=parse_rss(XML,query="반도체")
        self.assertEqual(len(items),2)
        self.assertTrue(items[0]["id"].startswith("NEWS-"))
        self.assertTrue(items[0]["headline"])
        self.assertTrue(items[0]["observed_at"])
        self.assertEqual(items[0]["source_type"],"SECONDARY")
        self.assertIn("KOSPI",items[0]["related_markets"])

        unique,issues=dedupe_and_cluster(items)
        self.assertEqual(len(unique),2)
        self.assertEqual(issues[0]["market_bias"],"UNDETERMINED")
        self.assertIn("semiconductor",issues[0]["impact_channels"])
        self.assertTrue(issues[0]["why_important"])
        self.assertTrue(issues[0]["fingerprint"])
        self.assertEqual(issues[0]["issue_id"], dedupe_and_cluster(items)[1][0]["issue_id"])
        self.assertTrue(all(a["cluster_id"] == issues[0]["issue_id"] for a in issues[0]["articles"]))

    def test_promotional_secondary_news_is_filtered(self):
        items = [
            {
                "headline": "주식 리딩방 무료체험 이벤트 경품 증정",
                "title": "주식 리딩방 무료체험 이벤트 경품 증정",
                "url": "https://promo.example/1",
                "published_at": "2026-09-30T01:00:00Z",
                "source": "홍보매체",
                "publisher": "홍보매체",
                "source_type": "SECONDARY",
                "official_source_available": False,
            },
            {
                "headline": "삼성전자 HBM 공급계약 확대",
                "title": "삼성전자 HBM 공급계약 확대",
                "url": "https://news.example/2",
                "published_at": "2026-09-30T01:01:00Z",
                "source": "A신문",
                "publisher": "A신문",
                "source_type": "SECONDARY",
                "official_source_available": False,
            },
        ]
        unique, issues = dedupe_and_cluster(items)
        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0]["headline"], "삼성전자 HBM 공급계약 확대")
        self.assertEqual(len(issues), 1)

    def test_reprints_are_not_counted_as_independent_confirmation(self):
        items = [
            {
                "headline": "삼성전자 HBM 생산 확대 계획 발표",
                "title": "삼성전자 HBM 생산 확대 계획 발표",
                "url": "https://a.example/1",
                "published_at": "2026-09-30T01:00:00Z",
                "source": "A신문",
                "publisher": "A신문",
                "source_type": "SECONDARY",
                "official_source_available": False,
            },
            {
                "headline": "삼성전자 HBM 생산 확대 계획 발표",
                "title": "삼성전자 HBM 생산 확대 계획 발표 - B뉴스",
                "url": "https://b.example/2",
                "published_at": "2026-09-30T01:02:00Z",
                "source": "B뉴스",
                "publisher": "B뉴스",
                "source_type": "SECONDARY",
                "official_source_available": False,
            },
        ]
        unique, issues = dedupe_and_cluster(items)
        self.assertEqual(len(unique), 1)
        self.assertEqual(issues[0]["independent_source_count"], 1)

    def test_semantic_continuity_preserves_issue_identity(self):
        prior = {
            "issue_id": "GN-stable",
            "fingerprint": "ISSUE-FP-stable",
            "headline": "삼성전자 HBM 생산 확대 계획",
            "event_core_tokens": ["삼성전자", "hbm", "생산", "확대"],
            "latest_at": "2026-09-30T01:00:00Z",
            "first_seen_at": "2026-09-30T00:50:00Z",
            "article_count": 2,
            "independent_source_count": 1,
            "independent_publishers": 1,
            "history": [],
        }
        current = {
            "issue_id": "GN-new",
            "fingerprint": "ISSUE-FP-new",
            "headline": "삼성 HBM 생산능력 확대 계획 발표",
            "event_core_tokens": ["삼성", "hbm", "생산능력", "확대", "계획"],
            "latest_at": "2026-09-30T01:10:00Z",
            "first_seen_at": "2026-09-30T01:05:00Z",
            "article_count": 3,
            "independent_source_count": 2,
            "independent_publishers": 2,
            "history": [],
        }
        merged = _merge_issue_history(
            [current], [prior],
            observed_at="2026-09-30T01:11:00Z",
            collection_succeeded=True,
        )
        row = next(x for x in merged if x["headline"].startswith("삼성"))
        self.assertEqual(row["issue_id"], "GN-stable")
        self.assertEqual(row["fingerprint"], "ISSUE-FP-stable")
        self.assertEqual(row["state"], "STRENGTHENING")
        self.assertEqual(row["identity_match"], "SEMANTIC_CONTINUITY")

    def test_old_search_result_is_not_current_news(self):
        self.assertFalse(_is_recent_news_item({
            "published_at":"1995-02-18T08:00:00Z",
            "observed_at":"2026-09-30T03:00:00Z"
        }, now=__import__("datetime").datetime(2026,9,30,3,0,tzinfo=__import__("datetime").timezone.utc)))

    def test_no_keyword_sentiment_claim(self):
        r=classify_channels("유가 급등과 금리 변화")
        self.assertEqual(r["market_bias"],"UNDETERMINED")

    def test_issue_market_reaction_is_observation_not_causality(self):
        issue_doc={"issues":[{
            "issue_id":"GN-r","first_seen_at":"2026-09-30T01:00:00Z",
            "importance_components":{"market_reaction_component":"PENDING"}
        }]}
        snapshots=[
            {
                "at":"2026-09-30T00:50:00Z",
                "indices":{"KOSPI":{"close":100.0,"foreign_net_100m_krw":-100.0},"KOSDAQ":{"close":200.0,"foreign_net_100m_krw":50.0}},
                "futures":{"close":300.0,"basis":1.0,"foreign_net_100m_krw":-20.0},
                "global":{"NASDAQ100_FUTURES":{"price":1000.0},"USD_KRW":{"price":1400.0},"WTI":{"price":70.0},"VIX":{"price":20.0}},
            },
            {
                "at":"2026-09-30T01:40:00Z",
                "indices":{"KOSPI":{"close":101.0,"foreign_net_100m_krw":-150.0},"KOSDAQ":{"close":198.0,"foreign_net_100m_krw":20.0}},
                "futures":{"close":303.0,"basis":1.5,"foreign_net_100m_krw":10.0},
                "global":{"NASDAQ100_FUTURES":{"price":1005.0},"USD_KRW":{"price":1398.0},"WTI":{"price":71.0},"VIX":{"price":19.5}},
            },
        ]
        result=_enrich_issue_market_reactions(issue_doc,snapshots)["issues"][0]["market_reaction"]
        self.assertEqual(result["evidence_state"],"OBSERVED")
        self.assertEqual(result["interpretation_state"],"CORRELATION_ONLY")
        self.assertAlmostEqual(result["axes"]["KOSPI"]["price_return_pct"],1.0)
        self.assertEqual(result["axes"]["KOSPI"]["foreign_flow_change_100m_krw"],-50.0)

    def test_isolated_official_feed_failure_is_persisted_without_killing_news(self):
        feed = {"id":"fsc-press","publisher":"금융위원회","url":"https://example.invalid/rss","category":"보도자료"}
        with TemporaryDirectory() as tmp, \
             patch("kmb_lab.pipeline.google_news.DEFAULT_QUERIES", ("반도체",)), \
             patch("kmb_lab.pipeline.google_news.fetch_rss", return_value=XML), \
             patch("kmb_lab.pipeline._is_recent_news_item", return_value=True), \
             patch("kmb_lab.pipeline.official_news.OFFICIAL_FEEDS", (feed,)), \
             patch("kmb_lab.pipeline.official_news.fetch_feed", side_effect=RuntimeError("timeout")):
            current, issues, digest, errors = collect_news(Path(tmp))
            self.assertEqual(current["collection_status"], "PARTIAL")
            self.assertGreater(current["count"], 0)
            self.assertTrue(any("official-news:fsc-press:timeout" in row for row in errors))
            ledger = Path(tmp, "data/ai/unresolved-problems.jsonl").read_text(encoding="utf-8").splitlines()
            rows = [json.loads(line) for line in ledger if line.strip()]
            problem = next(row for row in rows if row["id"] == "NEWS-OFFICIAL-FSC_PRESS")
            self.assertEqual(problem["status"], "OPEN")
            self.assertIn("retry", problem["do_not_repeat"].lower())

    def test_issue_history_strengthening_then_weakening(self):
        base={
            "issue_id":"GN-x","fingerprint":"fp-x","headline":"금리 이슈",
            "latest_at":"2026-09-30T01:00:00Z","first_seen_at":"2026-09-30T00:50:00Z",
            "article_count":1,"independent_publishers":1,"history":[]
        }
        current=dict(base)
        current.update({"article_count":2,"independent_publishers":2,"latest_at":"2026-09-30T01:05:00Z"})
        strengthened=_merge_issue_history([current],[base],observed_at="2026-09-30T01:06:00Z",collection_succeeded=True)
        self.assertEqual(strengthened[0]["state"],"STRENGTHENING")

        weakened=_merge_issue_history([],strengthened,observed_at="2026-09-30T02:00:00Z",collection_succeeded=True)
        self.assertEqual(weakened[0]["state"],"WEAKENING")

if __name__=='__main__':
    unittest.main()
