import unittest
from kmb_lab.adapters.krx import summarize_equity_rows,select_kospi200_futures
class KrxTests(unittest.TestCase):
    def test_breadth_from_official_rows(self):
        rows=[{"CMPPREVDD_PRC":"10","ACC_TRDVAL":"100","MKTCAP":"1000"},{"CMPPREVDD_PRC":"-2","ACC_TRDVAL":"200","MKTCAP":"900"},{"CMPPREVDD_PRC":"0","ACC_TRDVAL":"30","MKTCAP":"100"}]
        r=summarize_equity_rows(rows,"KOSPI","20260929")
        self.assertEqual(r["breadth"],{"advance":1,"decline":1,"flat":1})
        self.assertEqual(r["source_kind"],"primary")
    def test_select_kospi200_futures_excludes_mini(self):
        rows=[{"PROD_NM":"코스피 200 선물","ISU_NM":"K200","ACC_TRDVOL":"100"},{"PROD_NM":"미니 코스피 200 선물","ISU_NM":"MINI","ACC_TRDVOL":"999"}]
        self.assertEqual(len(select_kospi200_futures(rows)),1)
if __name__=='__main__': unittest.main()
