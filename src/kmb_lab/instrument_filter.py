from __future__ import annotations

import re
from typing import Any

ETF_BRANDS = (
    "KODEX", "TIGER", "ACE", "RISE", "SOL", "PLUS", "HANARO",
    "KOSEF", "TIMEFOLIO", "ARIRANG", "KBSTAR", "WOORI", "FOCUS",
)

TYPE_KEYS = (
    "security_type", "securityType", "instrument_type", "instrumentType",
    "stock_class", "stockClass", "stock_type", "stockType",
    "item_type", "itemType", "stockEndType", "stock_end_type",
)

PREFERRED_RE = re.compile(
    r"(?:우선주|전환우|[0-9]*우(?:B|C)?|우(?:B|C)?)$",
    re.IGNORECASE,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def instrument_name(row: dict[str, Any]) -> str:
    return _text(
        row.get("stockName")
        or row.get("itemName")
        or row.get("name")
        or row.get("korName")
    )


def classify_instrument(row: dict[str, Any]) -> str:
    """Classify listed instruments for the stock-analysis universe.

    The classifier is intentionally conservative for explicit non-common-stock
    products. Unknown six-digit Korean equity rows are treated as ordinary
    stock candidates only when no exclusion signal is present.
    """
    raw_types = " ".join(_text(row.get(key)) for key in TYPE_KEYS).upper()
    name = instrument_name(row)
    upper = name.upper()
    compact = re.sub(r"\s+", "", upper)

    if "ETN" in raw_types or "ETN" in upper:
        return "ETN"
    if "ETF" in raw_types or "ETF" in upper:
        return "ETF"
    if "SPAC" in raw_types or "스팩" in name or "기업인수목적" in name or re.search(r"\bSPAC\b", upper):
        return "SPAC"
    if "REIT" in raw_types or "리츠" in name or "REIT" in upper:
        return "REIT"
    if "우선" in raw_types or "PREFERRED" in raw_types or PREFERRED_RE.search(compact):
        return "PREFERRED"
    if any(token in upper for token in ("인버스", "INVERSE", "레버리지", "LEVERAGE", "선물인버스")):
        return "STRUCTURED"
    if any(compact.startswith(brand) for brand in ETF_BRANDS):
        return "ETF"

    # Explicit ordinary-equity hints take precedence.
    if any(token in raw_types for token in ("보통주", "COMMON", "주권", "EQUITY")):
        return "COMMON_STOCK"

    code = _text(row.get("itemCode") or row.get("stockCode") or row.get("code")).upper()
    if re.fullmatch(r"[0-9A-Z]{6}", code) and name:
        return "COMMON_STOCK_CANDIDATE"
    return "UNKNOWN"


def is_excluded_instrument(row: dict[str, Any]) -> bool:
    return classify_instrument(row) in {
        "ETF", "ETN", "SPAC", "PREFERRED", "REIT", "STRUCTURED",
    }


def is_stock_analysis_eligible(row: dict[str, Any]) -> bool:
    return classify_instrument(row) in {"COMMON_STOCK", "COMMON_STOCK_CANDIDATE"}
