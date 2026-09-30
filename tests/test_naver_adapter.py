import unittest

from kmb_lab.adapters.naver_market import (
    normalize_index_basic,
    normalize_kospi200_futures,
    normalize_main_summary,
    normalize_program,
    normalize_stock_bars,
)


class NaverTests(unittest.TestCase):
    def test_basic_normalization(self):
        r = normalize_index_basic(
            {
                "closePrice": "3,500.25",
                "compareToPreviousClosePrice": "10.5",
                "fluctuationsRatio": "0.30",
                "accumulatedTradingVolume": "123,456",
                "accumulatedTradingValue": "987,654,321",
                "localTradedAt": "2026-09-30T10:00:00+09:00",
            },
            "KOSPI",
        )
        self.assertEqual(r["close"], 3500.25)
        self.assertEqual(r["trading_volume"], 123456)
        self.assertEqual(r["trading_value"], 987654321)
        self.assertEqual(r["source_kind"], "secondary")

    def test_summary_flow_and_breadth_with_explicit_code(self):
        p = {
            "message": {
                "result": {
                    "todayIndexItemList": [
                        {"itemCode": "KOSPI", "riseCnt": 500, "fallCnt": 1000, "steadyCnt": 20}
                    ],
                    "todayIndexDealTrendList": [
                        {
                            "itemCode": "KOSPI",
                            "personalValue": "100",
                            "foreignValue": "-200",
                            "institutionalValue": "100",
                        }
                    ],
                    "kospiTrendProgram": {"netBuyValue": "-50"},
                }
            }
        }
        r = normalize_main_summary(p)["indices"]["KOSPI"]
        self.assertEqual(r["flows_100m_krw"]["foreign"], -200)
        self.assertEqual(r["breadth"]["advance"], 500)

    def test_summary_uses_documented_positional_fallback(self):
        p = {
            "message": {
                "result": {
                    "todayIndexItemList": [
                        {"riseCnt": 510, "fallCnt": 390, "steadyCnt": 25},
                        {"riseCnt": 820, "fallCnt": 640, "steadyCnt": 35},
                        {"riseCnt": 90, "fallCnt": 110, "steadyCnt": 5},
                    ],
                    "todayIndexDealTrendList": [
                        {"personalValue": "150", "foreignValue": "-220", "institutionalValue": "70"},
                        {"personalValue": "-80", "foreignValue": "120", "institutionalValue": "-40"},
                        {"personalValue": "10", "foreignValue": "-15", "institutionalValue": "5"},
                    ],
                }
            }
        }
        r = normalize_main_summary(p)["indices"]
        self.assertEqual(r["KOSPI"]["flows_100m_krw"]["foreign"], -220)
        self.assertEqual(r["KOSDAQ"]["flows_100m_krw"]["foreign"], 120)
        self.assertEqual(r["KOSDAQ"]["breadth"]["advance"], 820)
        self.assertEqual(r["KPI200"]["breadth"]["decline"], 110)

    def test_kospi200_futures_secondary_normalization(self):
        price_rows = [{
            "localTradedAt": "2026-09-30",
            "closePrice": "1,086.25",
            "compareToPreviousClosePrice": "5.50",
            "fluctuationsRatio": "0.51",
        }]
        trend = {
            "bizdate": "20260930",
            "personalValue": "-120",
            "foreignValue": "350",
            "institutionalValue": "-230",
        }
        result = normalize_kospi200_futures(price_rows, trend)
        self.assertEqual(result["status"], "CONNECTED_SECONDARY")
        self.assertEqual(result["close"], 1086.25)
        self.assertEqual(result["investor_flow_100m_krw"]["foreign"], 350)

    def test_program_normalization_sums_arbitrage_and_non_arbitrage(self):
        raw = {
            "differenceBuyConsignAmount": 178846184885,
            "differenceBuySelfAmount": 5594262325,
            "differenceSellConsignAmount": 236017483275,
            "differenceSellSelfAmount": 2825198040,
            "biDifferenceBuyConsignAmount": 2702407317889,
            "biDifferenceBuySelfAmount": 11301313667,
            "biDifferenceSellConsignAmount": 3125066980094,
            "biDifferenceSellSelfAmount": 7198649934,
            "bizdate": 20260930,
        }
        result = normalize_program(raw)
        self.assertAlmostEqual(result["arbitrage_net_100m_krw"], -544.02, places=2)
        self.assertAlmostEqual(result["non_arbitrage_net_100m_krw"], -4185.57, places=2)
        self.assertAlmostEqual(result["net_100m_krw"], -4729.59, places=2)

    def test_generic_stock_bars_support_current_chart_payload(self):
        p = {
            "priceInfos": [
                {
                    "localDate": "20260929",
                    "openPrice": 10000,
                    "highPrice": 11000,
                    "lowPrice": 9900,
                    "closePrice": 10500,
                    "accumulatedTradingVolume": 1000,
                }
            ]
        }
        row = normalize_stock_bars(p)[0]
        self.assertEqual(row["date"], "2026-09-29")
        self.assertEqual(row["close"], 10500)


if __name__ == "__main__":
    unittest.main()
