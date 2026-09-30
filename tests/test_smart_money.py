import unittest
from kmb_lab.smart_money import analyze_smart_money, backtest_smart_money
class SmartMoneyTests(unittest.TestCase):
    def bars(self, distribution=False):
        rows=[]
        price=100.0
        for i in range(60):
            vol=1000.0
            o=price
            if distribution and i>=55:
                h=price*1.08; l=price*.98; c=price*.995; vol=2600
            else:
                h=price*1.014; l=price*.997; c=price*1.012; vol=1600 if i>=50 else 1000
            rows.append({"date":f"2026-07-{(i%28)+1:02d}","open":o,"high":h,"low":l,"close":c,"volume":vol})
            price=c
        return rows
    def test_estimate_is_range_not_account_claim(self):
        r=analyze_smart_money(self.bars())
        self.assertEqual(r["evidence_state"],"ESTIMATED")
        self.assertIn("remaining_inventory_proxy",r)
        self.assertEqual(r["remaining_inventory_proxy"]["unit"],"fraction_of_virtual_inventory_proxy")
        self.assertIn("not_account_cost",r["virtual_cost_range"]["label"])
        self.assertNotIn("probability",r)
    def test_distribution_risk_rises_with_weak_high_volume_closes(self):
        a=analyze_smart_money(self.bars(False)); b=analyze_smart_money(self.bars(True))
        self.assertGreater(b["distribution_risk_score"],a["distribution_risk_score"])
    def test_walk_forward_backtest_uses_historical_states_only(self):
        rows = self.bars(False) + self.bars(False)[:20]
        result = backtest_smart_money(rows, forward_days=5, min_history=30)
        self.assertIn(result["evidence_state"], {"ESTIMATED", "UNKNOWN"})
        if result["evidence_state"] == "ESTIMATED":
            self.assertGreater(result["sample_count"], 0)
            self.assertIn("overall", result)
            self.assertEqual(result["cost_assumption"]["evidence_state"], "ASSUMPTION")
            self.assertNotIn("probability", result)

    def test_walk_forward_small_history_unknown(self):
        result = backtest_smart_money(self.bars()[:20], forward_days=5, min_history=30)
        self.assertEqual(result["evidence_state"], "UNKNOWN")
        self.assertEqual(result["sample_count"], 0)

    def test_small_sample_unknown(self):
        self.assertEqual(analyze_smart_money(self.bars()[:10])["evidence_state"],"UNKNOWN")
if __name__=='__main__': unittest.main()
