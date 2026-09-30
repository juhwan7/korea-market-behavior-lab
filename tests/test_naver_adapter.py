import unittest
from unittest.mock import patch

from kmb_lab.adapters.naver_market import (
    normalize_index_basic,
    normalize_kospi200_futures,
    normalize_main_summary,
    normalize_program,
    normalize_sector_dispersion,
    fetch_sector_list,
    fetch_stock_daily,
    normalize_stock_bars,
    normalize_turnover_participation,
    top_turnover_candidates,
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

    def test_sector_dispersion_supports_current_v2_shape(self):
        payload = {"items": [
            {"no": "101", "name": "반도체", "changeRate": "1.25"},
            {"no": "102", "name": "화학", "changeRate": "-0.75"},
            {"no": "103", "name": "운송", "changeRate": "0.00"},
        ]}
        result = normalize_sector_dispersion(payload)
        self.assertEqual(result["sector_count"], 3)
        self.assertEqual(result["positive"], 1)
        self.assertEqual(result["negative"], 1)
        self.assertEqual(result["flat"], 1)
        self.assertEqual(result["strongest"][0]["code"], "101")

    def test_sector_fetch_prefers_current_stock_naver_endpoint(self):
        payload = {"items": [{"no": "101", "name": "반도체", "changeRate": "1.25"}]}
        with patch("kmb_lab.adapters.naver_market.request_json", return_value=payload) as request_json:
            result = fetch_sector_list()
        self.assertEqual(result, payload)
        self.assertIn("/api/stockSecurity/rankings/v2/domestic/industries", request_json.call_args.args[0])
        self.assertEqual(request_json.call_args.kwargs["params"]["period"], "daily")
    def test_top_turnover_candidates_are_sorted_and_labeled_for_validation(self):
        rows = [
            {"itemCode":"005930","stockName":"삼성전자","accumulatedTradingValueRaw":1000},
            {"itemCode":"000660","stockName":"SK하이닉스","accumulatedTradingValueRaw":3000},
            {"itemCode":"035420","stockName":"NAVER","accumulatedTradingValueRaw":2000},
        ]
        result = top_turnover_candidates(rows, "KOSPI", limit=2)
        self.assertEqual([row["code"] for row in result], ["000660", "035420"])
        self.assertEqual(result[0]["benchmark"], "KOSPI")
        self.assertEqual(result[0]["selection_reason"], "top_intraday_trading_value_common_stock_validation_sample")
    def test_top_turnover_candidates_exclude_non_common_products(self):
        rows = [
            {"itemCode":"005930","stockName":"삼성전자","accumulatedTradingValueRaw":1000},
            {"itemCode":"005935","stockName":"삼성전자우","accumulatedTradingValueRaw":9000},
            {"itemCode":"091160","stockName":"KODEX 반도체","accumulatedTradingValueRaw":8000},
            {"itemCode":"123456","stockName":"테스트스팩1호","accumulatedTradingValueRaw":7000},
        ]
        result = top_turnover_candidates(rows, "KOSPI", limit=10)
        self.assertEqual([row["code"] for row in result], ["005930"])
        self.assertEqual(result[0]["instrument_type"], "COMMON_STOCK_CANDIDATE")

    def test_turnover_participation_uses_directional_trading_value(self):
        rows = [
            {"accumulatedTradingValueRaw": "100000000000", "fluctuationsRatio": "2.0"},
            {"accumulatedTradingValueRaw": "50000000000", "fluctuationsRatio": "-1.0"},
            {"accumulatedTradingValueRaw": "10000000000", "fluctuationsRatio": "0.0"},
        ]
        result = normalize_turnover_participation(rows)
        self.assertEqual(result["stock_count"], 3)
        self.assertEqual(result["advance_decline_turnover_ratio"], 2.0)
        self.assertEqual(result["advance_directional_share"], 0.6667)

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

    def test_stock_history_requests_requested_count(self):
        payload = {"priceInfos": [
            {"localDate": "20260929", "openPrice": 10000, "highPrice": 11000, "lowPrice": 9900, "closePrice": 10500, "accumulatedTradingVolume": 1000}
        ]}
        with patch("kmb_lab.adapters.naver_market.request_json", return_value=payload) as request_json:
            rows = fetch_stock_daily("005930", page_size=260)
        self.assertEqual(len(rows), 1)
        self.assertEqual(request_json.call_args.kwargs["params"]["count"], 260)
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
