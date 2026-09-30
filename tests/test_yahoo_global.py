import unittest
from kmb_lab.adapters.yahoo_global import normalize_quote
class YahooTests(unittest.TestCase):
    def test_chart_normalization(self):
        p={"chart":{"result":[{"meta":{"regularMarketPrice":101.0,"chartPreviousClose":100.0,"regularMarketTime":1790730000,"currency":"USD"},"timestamp":[1790730000],"indicators":{"quote":[{"close":[101.0]}]}}],"error":None}}
        r=normalize_quote(p,"NQ=F")
        self.assertAlmostEqual(r["change_pct"],1.0)
        self.assertEqual(r["source_kind"],"secondary")
if __name__=='__main__': unittest.main()
