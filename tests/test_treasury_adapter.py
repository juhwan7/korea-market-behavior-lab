import unittest

from kmb_lab.adapters.treasury import observation_for_maturity, parse_yield_curve_xml


FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">
  <entry><content type="application/xml"><m:properties>
    <d:NEW_DATE>2026-09-25T00:00:00</d:NEW_DATE>
    <d:BC_10YEAR>5.17</d:BC_10YEAR>
    <d:BC_20YEAR>5.54</d:BC_20YEAR>
    <d:BC_30YEAR>5.49</d:BC_30YEAR>
  </m:properties></content></entry>
</feed>"""


class TreasuryAdapterTests(unittest.TestCase):
    def test_parse_preserves_date_and_independent_maturities(self):
        rows = parse_yield_curve_xml(FIXTURE, "2026-09-28T12:05:00Z")
        self.assertEqual(rows[0]["date"], "2026-09-25")
        self.assertEqual(rows[0]["yields"]["30YEAR"], 5.49)
        self.assertEqual(rows[0]["yields"]["20YEAR"], 5.54)

    def test_observation_has_primary_provenance(self):
        row = parse_yield_curve_xml(FIXTURE, "2026-09-28T12:05:00Z")[0]
        obs = observation_for_maturity(row, "30YEAR")
        self.assertEqual(obs["source_id"], "us-treasury")
        self.assertEqual(obs["source_kind"], "primary")
        self.assertEqual(obs["as_of"], "2026-09-25")
        self.assertEqual(obs["value"], 5.49)


if __name__ == "__main__":
    unittest.main()
