import unittest

from kmb_lab.adapters.google_news import parse_rss, dedupe_and_cluster, classify_channels
from kmb_lab.pipeline import _merge_issue_history

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

    def test_no_keyword_sentiment_claim(self):
        r=classify_channels("유가 급등과 금리 변화")
        self.assertEqual(r["market_bias"],"UNDETERMINED")

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
