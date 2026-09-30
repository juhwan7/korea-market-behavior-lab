import unittest

from kmb_lab.adapters.dart import normalize_disclosures
from kmb_lab.http_client import HttpError


class DartAdapterTests(unittest.TestCase):
    def test_normalize_primary_disclosure(self):
        rows = normalize_disclosures({"status":"000","list":[{
            "corp_code":"00126380","corp_name":"삼성전자","stock_code":"005930",
            "report_nm":"주요사항보고서","rcept_no":"20260930000123",
            "flr_nm":"삼성전자","rcept_dt":"20260930","rm":""
        }]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_kind"], "primary")
        self.assertEqual(rows[0]["receipt_date"], "2026-09-30")
        self.assertIn("20260930000123", rows[0]["url"])

    def test_no_data_status_is_empty(self):
        self.assertEqual(normalize_disclosures({"status":"013","message":"조회된 데이타가 없습니다."}), [])

    def test_error_status_raises(self):
        with self.assertRaises(HttpError):
            normalize_disclosures({"status":"010","message":"등록되지 않은 키"})


if __name__ == "__main__":
    unittest.main()
