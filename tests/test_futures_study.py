import unittest

from kmb_lab.pipeline import futures_study


class FuturesStudyTests(unittest.TestCase):
    def test_foreign_futures_buy_spot_sell_is_explicit_divergence(self):
        result = futures_study(
            {
                "KOSPI200_FUTURES": {
                    "change_pct": 0.8,
                    "basis_pct": 0.3,
                    "investor_flow_100m_krw": {"foreign": 7000},
                }
            },
            {"KPI200": {"change_pct": 0.2}},
            {"markets": {"KOSPI": {"foreign": {"net_100m_krw": -5000}}}},
            {"net_100m_krw": -1200},
            {"quotes": {"NASDAQ100_FUTURES": {"change_pct": 0.6}, "SOX": {"change_pct": -0.2}}},
        )
        states = {row["factor"]: row["state"] for row in result["observations"]}
        self.assertEqual(result["evidence_state"], "OBSERVED")
        self.assertEqual(states["futures_vs_spot"], "FUTURES_RELATIVELY_STRONG")
        self.assertEqual(states["foreign_spot_futures"], "FOREIGN_FUTURES_BUY_SPOT_SELL")
        self.assertEqual(states["program"], "PROGRAM_NET_SELL")
        text = " ".join(row["explanation"] for row in result["observations"])
        self.assertIn("Risk-on", text)
        self.assertIn("예측하지 않습니다", text)

    def test_empty_inputs_do_not_fabricate_interpretation(self):
        result = futures_study({}, {}, {}, {}, {})
        self.assertEqual(result["evidence_state"], "UNKNOWN")
        self.assertEqual(result["observations"], [])


if __name__ == "__main__":
    unittest.main()
