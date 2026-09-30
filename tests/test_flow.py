import unittest

from kmb_lab.flow import analyze_flow_history


class FlowTests(unittest.TestCase):
    def test_velocity_acceleration_reversal_and_windows(self):
        h = [
            {"at":"2026-09-30T09:30:00+09:00","markets":{"KOSPI":{"flows_100m_krw":{"foreign":-500,"individual":400,"institution":100}}}},
            {"at":"2026-09-30T10:00:00+09:00","markets":{"KOSPI":{"flows_100m_krw":{"foreign":-1200,"individual":900,"institution":300}}}},
            {"at":"2026-09-30T10:30:00+09:00","markets":{"KOSPI":{"flows_100m_krw":{"foreign":-1800,"individual":1300,"institution":500}}}},
            {"at":"2026-09-30T11:00:00+09:00","markets":{"KOSPI":{"flows_100m_krw":{"foreign":200,"individual":-50,"institution":-150}}}},
        ]
        r = analyze_flow_history(h)["markets"]["KOSPI"]["foreign"]
        self.assertEqual(r["net_100m_krw"], 200)
        self.assertTrue(r["reversal"])
        self.assertIsNotNone(r["velocity_100m_krw_per_min"])
        self.assertIsNotNone(r["acceleration"])
        self.assertEqual(r["window_changes_100m_krw"]["30m"], 2000)
        self.assertEqual(r["window_changes_100m_krw"]["60m"], 1400)
        self.assertEqual(r["window_changes_100m_krw"]["session"], 700)
        self.assertEqual(r["pace_state"], "NET_BUYING_STRENGTHENING")

    def test_negative_net_with_positive_recent_change_is_selling_easing(self):
        h = [
            {"at":"2026-09-30T13:00:00+09:00","markets":{"KOSPI":{"flows_100m_krw":{"foreign":-9000}}}},
            {"at":"2026-09-30T13:15:00+09:00","markets":{"KOSPI":{"flows_100m_krw":{"foreign":-9500}}}},
            {"at":"2026-09-30T13:30:00+09:00","markets":{"KOSPI":{"flows_100m_krw":{"foreign":-9200}}}},
            {"at":"2026-09-30T13:45:00+09:00","markets":{"KOSPI":{"flows_100m_krw":{"foreign":-8800}}}},
        ]
        r = analyze_flow_history(h)["markets"]["KOSPI"]["foreign"]
        self.assertEqual(r["pace_state"], "NET_SELLING_EASING")
        self.assertGreater(r["window_velocity_100m_krw_per_min"]["30m"], 0)


if __name__ == "__main__":
    unittest.main()
