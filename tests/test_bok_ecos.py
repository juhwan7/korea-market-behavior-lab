import unittest

from kmb_lab.adapters.bok_ecos import normalize_search
from kmb_lab.http_client import HttpError


class BokEcosAdapterTests(unittest.TestCase):
    def test_normalize_official_ecos_rows(self):
        payload = {"StatisticSearch":{"row":[
            {"STAT_CODE":"731Y001","ITEM_NAME1":"원/미국달러(매매기준율)","UNIT_NAME":"원","TIME":"20260929","DATA_VALUE":"1,355.20"},
            {"STAT_CODE":"731Y001","ITEM_NAME1":"원/미국달러(매매기준율)","UNIT_NAME":"원","TIME":"20260930","DATA_VALUE":"1352.70"},
        ]}}
        rows=normalize_search(payload,indicator_key="USD_KRW")
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[-1]["value"],1352.70)
        self.assertEqual(rows[-1]["source_kind"],"primary")
        self.assertEqual(rows[-1]["time"],"20260930")

    def test_ecos_error_is_not_fabricated(self):
        with self.assertRaises(HttpError):
            normalize_search({"RESULT":{"CODE":"ERROR-100","MESSAGE":"bad request"}},indicator_key="USD_KRW")


if __name__=="__main__":
    unittest.main()
