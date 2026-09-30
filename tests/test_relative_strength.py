import unittest

from kmb_lab.relative_strength import relative_strength


class RelativeStrengthTests(unittest.TestCase):
    def rows(self, start: float, daily: float, n: int = 30):
        price = start
        out = []
        for i in range(n):
            out.append({"date": f"2026-08-{i+1:02d}", "close": price})
            price *= 1 + daily
        return out

    def test_stronger_stock_has_positive_excess(self):
        result = relative_strength(self.rows(100, 0.01), self.rows(100, 0.002))
        self.assertEqual(result["evidence_state"], "ESTIMATED")
        self.assertEqual(result["overall_state"], "STRONGER")
        self.assertGreater(result["windows"]["20"]["excess_return_pct"], 0)

    def test_weaker_stock_is_detected(self):
        result = relative_strength(self.rows(100, -0.004), self.rows(100, 0.003))
        self.assertEqual(result["overall_state"], "WEAKER")
        self.assertLess(result["windows"]["5"]["excess_return_pct"], 0)

    def test_missing_overlap_is_unknown(self):
        result = relative_strength(
            [{"date": "2026-09-01", "close": 100}],
            [{"date": "2026-09-02", "close": 100}],
        )
        self.assertEqual(result["evidence_state"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
