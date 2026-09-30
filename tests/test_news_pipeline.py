import unittest

from kmb_lab.adapters.google_news import parse_rss, dedupe_and_cluster, classify_channels
from kmb_lab.pipeline import _merge_issue_history, _is_recent_news_item, _enrich_issue_market_reactions

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
