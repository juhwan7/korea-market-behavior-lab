from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

BASE_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
SOURCE_ID = "us-treasury"
SOURCE_KIND = "primary"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_yield_curve_xml(xml_text: str, retrieved_at: str) -> list[dict[str, Any]]:
    """Parse Treasury's Atom/XML yield-curve feed without assuming namespace prefixes."""
    root = ET.fromstring(xml_text)
    rows: list[dict[str, Any]] = []
    for entry in root.iter():
        if _local(entry.tag) != "entry":
            continue
        props = next((node for node in entry.iter() if _local(node.tag) == "properties"), None)
        if props is None:
            continue
        values = {_local(child.tag): (child.text or "").strip() for child in props}
        date = values.get("NEW_DATE")
        if not date:
            continue
        yields: dict[str, float] = {}
        for key, value in values.items():
            if not key.startswith("BC_") or not value:
                continue
            try:
                yields[key.removeprefix("BC_")] = float(value)
            except ValueError:
                continue
        rows.append({"date": date[:10], "yields": yields, "retrieved_at": retrieved_at})
    return rows


def fetch_yield_curve(year: int, timeout: int = 20) -> list[dict[str, Any]]:
    url = f"{BASE_URL}?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
    request = Request(url, headers={"User-Agent": "korea-market-behavior-lab/0.1"})
    with urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return parse_yield_curve_xml(payload, retrieved_at)


def observation_for_maturity(row: dict[str, Any], maturity: str) -> dict[str, Any]:
    value = row.get("yields", {}).get(maturity)
    if value is None:
        raise KeyError(f"missing Treasury maturity: {maturity}")
    return {
        "metric": f"U.S. Treasury {maturity} par yield",
        "value": value,
        "unit": "percent",
        "as_of": row["date"],
        "retrieved_at": row["retrieved_at"],
        "source_id": SOURCE_ID,
        "source_kind": SOURCE_KIND,
        "source_url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
    }
