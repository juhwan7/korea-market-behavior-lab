import unittest
from kmb_lab.adapters.google_news import parse_rss,dedupe_and_cluster,classify_channels
XML='''<rss><channel><item><title>반도체 수출 규제 논의 - A신문</title><link>https://a</link><pubDate>Wed, 30 Sep 2026 01:00:00 GMT</pubDate><source>A신문</source></item><item><title>반도체 수출 규제 논의 확대 - B뉴스</title><link>https://b</link><pubDate>Wed, 30 Sep 2026 01:02:00 GMT</pubDate><source>B뉴스</source></item></channel></rss>'''
class NewsTests(unittest.TestCase):
    def test_rss_and_cluster(self):
        items=parse_rss(XML,query="반도체")
        self.assertEqual(len(items),2)
        unique,issues=dedupe_and_cluster(items)
        self.assertEqual(len(unique),2)
        self.assertEqual(issues[0]["market_bias"],"UNDETERMINED")
        self.assertIn("semiconductor",issues[0]["impact_channels"])
    def test_no_keyword_sentiment_claim(self):
        r=classify_channels("유가 급등과 금리 변화")
        self.assertEqual(r["market_bias"],"UNDETERMINED")
if __name__=='__main__': unittest.main()
