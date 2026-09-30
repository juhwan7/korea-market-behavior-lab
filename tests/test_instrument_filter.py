import unittest

from kmb_lab.instrument_filter import (
    classify_instrument,
    is_excluded_instrument,
    is_stock_analysis_eligible,
)


class InstrumentFilterTests(unittest.TestCase):
    def test_common_stock_is_eligible(self):
        row = {"itemCode": "005930", "stockName": "삼성전자"}
        self.assertEqual(classify_instrument(row), "COMMON_STOCK_CANDIDATE")
        self.assertTrue(is_stock_analysis_eligible(row))
        self.assertFalse(is_excluded_instrument(row))

    def test_preferred_share_is_excluded(self):
        row = {"itemCode": "005935", "stockName": "삼성전자우"}
        self.assertEqual(classify_instrument(row), "PREFERRED")
        self.assertFalse(is_stock_analysis_eligible(row))

    def test_etf_is_excluded(self):
        row = {"itemCode": "091160", "stockName": "KODEX 반도체"}
        self.assertEqual(classify_instrument(row), "ETF")
        self.assertTrue(is_excluded_instrument(row))

    def test_etn_is_excluded(self):
        row = {"itemCode": "530123", "stockName": "삼성 인버스 2X WTI원유 선물 ETN"}
        self.assertEqual(classify_instrument(row), "ETN")

    def test_spac_is_excluded(self):
        row = {"itemCode": "123456", "stockName": "미래에셋비전스팩10호"}
        self.assertEqual(classify_instrument(row), "SPAC")

    def test_reit_is_excluded(self):
        row = {"itemCode": "293940", "stockName": "신한알파리츠"}
        self.assertEqual(classify_instrument(row), "REIT")

    def test_explicit_type_is_used(self):
        row = {
            "itemCode": "123456",
            "stockName": "테스트상품",
            "instrumentType": "ETF",
        }
        self.assertEqual(classify_instrument(row), "ETF")


if __name__ == "__main__":
    unittest.main()
