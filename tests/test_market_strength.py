import unittest
from kmb_lab.market_strength import market_strength
class StrengthTests(unittest.TestCase):
    def test_index_illusion(self):
        r=market_strength(indices={"KOSPI":{"change_pct":1.0},"KOSDAQ":{"change_pct":0.2}},breadth={"KOSPI":{"advance":300,"decline":700,"flat":10},"KOSDAQ":{"advance":800,"decline":700,"flat":20}},flows=None)
        self.assertEqual(r["evidence_state"],"ESTIMATED")
        self.assertTrue(any(x["type"]=="INDEX_UP_INTERNAL_WEAK" for x in r["index_illusion"]))
        self.assertIsNotNone(r["components"]["breadth"])
    def test_missing_does_not_fabricate(self):
        r=market_strength(indices={},breadth={},flows=None)
        self.assertEqual(r["evidence_state"],"UNKNOWN")
        self.assertIsNone(r["composite"])
if __name__=='__main__': unittest.main()
