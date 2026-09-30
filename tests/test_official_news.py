import unittest

from kmb_lab.adapters.official_news import parse_feed
from kmb_lab.adapters.google_news import dedupe_and_cluster


RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss><channel>
<item>
<title>기준금리 관련 공식 발표</title>
<link>https://official.example/release/1</link>
<pubDate>Wed, 30 Sep 2026 01:00:00 GMT</pubDate>
</item>
</channel></rss>
"""


class OfficialNewsTests(unittest.TestCase):
    def test_official_rss_is_primary(self):
        feed = {
            "id": "bok-test",
            "publisher": "한국은행",
            "url": "https://official.example/rss",
            "category": "통화정책",
        }
        rows = parse_feed(RSS, feed=feed)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_type"], "PRIMARY")
        self.assertEqual(rows[0]["source_kind"], "primary")
        self.assertTrue(rows[0]["official_source_available"])
        self.assertEqual(rows[0]["source"], "한국은행")
        self.assertIn("rates", rows[0]["impact_channels"])

    def test_dedupe_prefers_primary_copy_of_same_headline(self):
        secondary = {
            "headline": "기준금리 관련 공식 발표",
            "title": "기준금리 관련 공식 발표",
            "url": "https://secondary.example/1",
            "published_at": "2026-09-30T01:10:00Z",
            "source": "언론사",
            "publisher": "언론사",
            "source_type": "SECONDARY",
            "official_source_available": False,
        }
        primary = {
            "headline": "기준금리 관련 공식 발표",
            "title": "기준금리 관련 공식 발표",
            "url": "https://official.example/1",
            "published_at": "2026-09-30T01:00:00Z",
            "source": "한국은행",
            "publisher": "한국은행",
            "source_type": "PRIMARY",
            "official_source_available": True,
        }
        unique, issues = dedupe_and_cluster([secondary, primary])
        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0]["source_type"], "PRIMARY")
        self.assertTrue(issues[0]["official_source_available"])


if __name__ == "__main__":
    unittest.main()
