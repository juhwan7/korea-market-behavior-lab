import unittest

from kmb_lab.adapters.bok_ecos import normalize_daily_indicators


class BokEcosAdapterTests(unittest.TestCase):
    def test_normalize_official_public_page_indicators(self):
        raw = """
        <div>원/달러 1,355.20 09.30 13:00</div>
        <div>국고채(3년) 4.21 09.30 마감</div>
        <div>코스피 6,842.37 09.30 13:00</div>
        <div>코스닥 856.46 09.30 13:00</div>
        """
        result = normalize_daily_indicators(raw)
        self.assertEqual(result["status"], "CONNECTED_PRIMARY")
        self.assertEqual(result["source_kind"], "primary")
        self.assertEqual(result["indicators"]["USD_KRW"]["value"], 1355.20)
        self.assertEqual(result["indicators"]["KOREA_3Y"]["value"], 4.21)
        self.assertEqual(result["indicators"]["KOSPI"]["value"], 6842.37)

    def test_missing_values_are_not_fabricated(self):
        result = normalize_daily_indicators("<html><body>자료 갱신 중</body></html>")
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["indicators"], {})


if __name__ == "__main__":
    unittest.main()
