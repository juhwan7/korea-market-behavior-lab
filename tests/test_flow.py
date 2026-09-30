import unittest
from kmb_lab.flow import analyze_flow_history
class FlowTests(unittest.TestCase):
    def test_velocity_acceleration_and_reversal(self):
        h=[
            {"at":"2026-09-30T09:30:00+09:00","markets":{"KOSPI":{"flows_100m_krw":{"foreign":-500,"individual":400,"institution":100}}}},
            {"at":"2026-09-30T10:00:00+09:00","markets":{"KOSPI":{"flows_100m_krw":{"foreign":-1200,"individual":900,"institution":300}}}},
            {"at":"2026-09-30T11:00:00+09:00","markets":{"KOSPI":{"flows_100m_krw":{"foreign":200,"individual":-50,"institution":-150}}}},
        ]
        r=analyze_flow_history(h)["markets"]["KOSPI"]["foreign"]
        self.assertEqual(r["net_100m_krw"],200)
        self.assertTrue(r["reversal"])
        self.assertIsNotNone(r["velocity_100m_krw_per_min"])
        self.assertIsNotNone(r["acceleration"])
if __name__=='__main__': unittest.main()
