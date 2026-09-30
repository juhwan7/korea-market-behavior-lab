import unittest
from kmb_lab.adapters.naver_market import normalize_index_basic,normalize_main_summary,normalize_stock_bars
class NaverTests(unittest.TestCase):
    def test_basic_normalization(self):
        r=normalize_index_basic({"closePrice":"3,500.25","compareToPreviousClosePrice":"10.5","fluctuationsRatio":"0.30","localTradedAt":"2026-09-30T10:00:00+09:00"},"KOSPI")
        self.assertEqual(r["close"],3500.25); self.assertEqual(r["source_kind"],"secondary")
    def test_summary_flow_and_breadth(self):
        p={"message":{"result":{"todayIndexItemList":[{"itemCode":"KOSPI","riseCnt":500,"fallCnt":1000,"steadyCnt":20}],"todayIndexDealTrendList":[{"itemCode":"KOSPI","personalValue":"100","foreignValue":"-200","institutionalValue":"100"}],"kospiTrendProgram":{"netBuyValue":"-50"}}}}
        r=normalize_main_summary(p)["indices"]["KOSPI"]
        self.assertEqual(r["flows_100m_krw"]["foreign"],-200)
        self.assertEqual(r["breadth"]["advance"],500)
    def test_generic_stock_bars(self):
        p=[{"localTradedAt":"2026-09-29","openPrice":"10,000","highPrice":"11,000","lowPrice":"9,900","closePrice":"10,500","accumulatedTradingVolume":"1000"}]
        self.assertEqual(normalize_stock_bars(p)[0]["close"],10500)
if __name__=='__main__': unittest.main()
