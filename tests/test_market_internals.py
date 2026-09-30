import unittest

from kmb_lab.adapters.naver_market import normalize_sector_dispersion, normalize_size_participation
from kmb_lab.market_strength import market_strength


class MarketInternalsTests(unittest.TestCase):
    def test_sector_dispersion(self):
        result = normalize_sector_dispersion([
            {"sectorCode":"001","sectorName":"반도체","fluctuationsRatio":"2.4"},
            {"sectorCode":"002","sectorName":"화학","fluctuationsRatio":"-1.2"},
            {"sectorCode":"003","sectorName":"로봇","fluctuationsRatio":"0.5"},
        ])
        self.assertEqual(result["evidence_state"], "ESTIMATED")
        self.assertEqual(result["positive"], 2)
        self.assertEqual(result["negative"], 1)
        self.assertEqual(result["strongest"][0]["name"], "반도체")

    def test_size_participation_is_explicit_proxy(self):
        rows=[]
        for i in range(100):
            rows.append({
                "marketValueRaw": 1000-i,
                "fluctuationsRatio": 1.0 if i < 20 else (-1.0 if i < 50 else 0.5),
                "accumulatedTradingValueRaw": 100+i,
            })
        result=normalize_size_participation(rows)
        self.assertEqual(result["evidence_state"], "ESTIMATED")
        self.assertEqual(result["classification"], "market_cap_rank_proxy_top20_mid30_bottom50")
        self.assertEqual(result["segments"]["large_proxy"]["advance_share"], 1.0)
        self.assertEqual(result["segments"]["mid_proxy"]["advance_share"], 0.0)
        self.assertEqual(result["segments"]["small_proxy"]["advance_share"], 1.0)

    def test_strength_exposes_sector_and_size_without_hiding_missing_axes(self):
        size_row={"size_participation":{"segments":{
            "large_proxy":{"advance_share":0.8},"mid_proxy":{"advance_share":0.5},"small_proxy":{"advance_share":0.3}
        }}}
        result=market_strength(
            indices={"KOSPI":{"change_pct":1.0},"KOSDAQ":{"change_pct":0.5}},
            breadth={"KOSPI":{"advance":700,"decline":300},"KOSDAQ":{"advance":900,"decline":600}},
            flows=None,
            sector_breadth={"positive_directional_share":0.75},
            size_participation={"KOSPI":size_row,"KOSDAQ":size_row},
        )
        self.assertEqual(result["components"]["sector_breadth"],75.0)
        self.assertEqual(result["size_participation"]["large_proxy"],80.0)
        self.assertEqual(result["size_participation"]["small_proxy"],30.0)


if __name__=="__main__":
    unittest.main()
