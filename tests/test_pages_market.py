import unittest
from kmb_lab.pages_market import render_market_intelligence
class PagesMarketTests(unittest.TestCase):
    def test_sections_and_no_fake_account_claim(self):
        html=render_market_intelligence({"strength":{"components":{"price":60},"coverage":{"available":1,"total":5}},"flows":{},"futures":{"KOSPI200_FUTURES":{"status":"USER_ACTION_REQUIRED","reason":"key"}},"global":{"quotes":{},"interpretation":{}},"issues":{"issues":[]},"smart_money":{"items":[]},"unresolved":[],"development_mix":{}})
        for marker in ("market-strength","flows","futures-global","news-issues","smart-money"):
            self.assertIn(f'data-kmb-section="{marker}"',html)
        self.assertIn("실제 특정 계좌",html)
if __name__=='__main__': unittest.main()
