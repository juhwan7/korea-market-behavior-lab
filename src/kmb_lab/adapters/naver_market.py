from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from kmb_lab.http_client import HttpError, request_json, request_text

FRONT = "https://m.stock.naver.com/front-api"
MAIN_SUMMARY = "https://finance.naver.com/main/mainSummary.naver"
LEGACY_STOCK = "https://m.stock.naver.com/api/stock"
CHART_API = "https://api.stock.naver.com/chart/domestic/item"
INDEX_CHART_API = "https://api.stock.naver.com/chart/domestic/index"
LEGACY_CHART = "https://api.finance.naver.com/siseJson.naver"
SOURCE_ID = "naver-finance-public"
SOURCE_KIND = "secondary"
REFERER = "https://stock.naver.com/"


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace(",", "").replace("%", "")
    if not raw or raw in {"-", "N/A", "null", "None"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def _payload(value: Any) -> Any:
    if isinstance(value, dict):
        if isinstance(value.get("message"), dict) and "result" in value["message"]:
            return value["message"]["result"]
        if "result" in value and len(value) <= 4:
            return value["result"]
    return value


def fetch_index_basic(code: str) -> dict[str, Any]:
    return request_json(
        f"{FRONT}/stock/domestic/basic",
        params={"code": code, "endType": "index"},
        headers={"Referer": REFERER},
    )


def fetch_main_summary() -> dict[str, Any]:
    payload = request_json(MAIN_SUMMARY, headers={"Referer": "https://finance.naver.com/"})
    if not isinstance(payload, dict):
        raise HttpError("Naver mainSummary returned non-object JSON")
    return payload


def fetch_market_trend() -> Any:
    return request_json(
        f"{FRONT}/market/tradingTrend/graphInfo",
        params={"periodType": "daily", "stockExchangeType": "KRX"},
        headers={"Referer": REFERER},
    )


def fetch_program_trend() -> Any:
    return fetch_main_summary()


def _legacy_chart_rows(code: str, page_size: int) -> list[dict[str, Any]]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=max(180, page_size * 3))
    text = request_text(
        LEGACY_CHART,
        params={
            "symbol": code,
            "requestType": 1,
            "startTime": start.strftime("%Y%m%d"),
            "endTime": end.strftime("%Y%m%d"),
            "timeframe": "day",
        },
        headers={"Referer": "https://finance.naver.com/"},
    )
    try:
        payload = ast.literal_eval(text.strip())
    except (ValueError, SyntaxError) as exc:
        raise HttpError(f"Naver legacy chart parse failed: {exc}") from exc
    if not isinstance(payload, list) or len(payload) < 2:
        return []
    header = [str(x).strip().lower() for x in payload[0]]
    aliases = {
        "날짜": "date", "date": "date",
        "시가": "open", "open": "open",
        "고가": "high", "high": "high",
        "저가": "low", "low": "low",
        "종가": "close", "close": "close",
        "거래량": "volume", "volume": "volume",
        "외국인소진율": "foreign_rate",
    }
    mapped = [aliases.get(x, x) for x in header]
    rows: list[dict[str, Any]] = []
    for raw in payload[1:]:
        if not isinstance(raw, (list, tuple)) or len(raw) < len(mapped):
            continue
        row = dict(zip(mapped, raw))
        close = _number(row.get("close"))
        volume = _number(row.get("volume"))
        if row.get("date") is None or close is None or volume is None:
            continue
        date = str(row["date"]).replace(".", "").replace("-", "")
        if len(date) == 8 and date.isdigit():
            date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        rows.append({
            "date": date[:10],
            "open": _number(row.get("open")) or close,
            "high": _number(row.get("high")) or close,
            "low": _number(row.get("low")) or close,
            "close": close,
            "volume": volume,
            "trading_value": None,
            "source_id": SOURCE_ID,
            "source_kind": SOURCE_KIND,
        })
    rows.sort(key=lambda item: item["date"])
    return rows[-page_size:]


def fetch_index_daily(code: str, page_size: int = 80) -> list[dict[str, Any]]:
    payload = request_json(
        f"{INDEX_CHART_API}/{code}",
        params={"periodType": "dayCandle", "count": page_size},
        headers={"Referer": REFERER},
    )
    rows = normalize_stock_bars(payload)
    if not rows:
        raise HttpError(f"Naver index history unavailable: {code}")
    return rows[-page_size:]


def fetch_stock_daily(code: str, page_size: int = 80) -> list[dict[str, Any]]:
    errors: list[str] = []
    json_candidates = [
        (f"{CHART_API}/{code}", {"periodType": "dayCandle"}),
        (f"{FRONT}/chart/domestic/stock/end", {"code": code, "chartInfoType": "item", "scriptChartType": "candleDay"}),
        (f"{LEGACY_STOCK}/{code}/price", {"pageSize": page_size, "page": 1}),
    ]
    for url, params in json_candidates:
        try:
            payload = request_json(url, params=params, headers={"Referer": REFERER})
            rows = normalize_stock_bars(payload)
            if rows:
                return rows[-page_size:]
            errors.append(f"{url}: empty normalized rows")
        except Exception as exc:
            errors.append(str(exc))
    try:
        rows = _legacy_chart_rows(code, page_size)
        if rows:
            return rows
        errors.append("legacy siseJson: empty normalized rows")
    except Exception as exc:
        errors.append(str(exc))
    raise HttpError("Naver stock history unavailable: " + " | ".join(errors))


def normalize_program(payload: Any) -> dict[str, Any]:
    """Normalize Naver KOSPI program trading amounts to 100M KRW.

    difference* = arbitrage program trading; biDifference* = non-arbitrage.
    Amount fields are KRW. Both consign and self accounts are included.
    """
    raw = payload if isinstance(payload, dict) else {}

    def amount(name: str) -> float:
        return float(_number(raw.get(name)) or 0.0)

    def side(prefix: str, side_name: str) -> float:
        return amount(f"{prefix}{side_name}ConsignAmount") + amount(f"{prefix}{side_name}SelfAmount")

    arbitrage_buy = side("difference", "Buy")
    arbitrage_sell = side("difference", "Sell")
    non_arbitrage_buy = side("biDifference", "Buy")
    non_arbitrage_sell = side("biDifference", "Sell")

    any_amount = any(
        key.endswith("Amount") and _number(value) is not None
        for key, value in raw.items()
    )
    if not any_amount:
        fallback = _number(
            raw.get("netBuyValue")
            or raw.get("netValue")
            or raw.get("programNetValue")
            or raw.get("allNetValue")
            or raw.get("totalNetValue")
        )
        return {
            "net_100m_krw": fallback,
            "arbitrage_net_100m_krw": None,
            "non_arbitrage_net_100m_krw": None,
            "source_id": SOURCE_ID,
            "source_kind": SOURCE_KIND,
            "raw_available": bool(raw),
        }

    arbitrage_net = arbitrage_buy - arbitrage_sell
    non_arbitrage_net = non_arbitrage_buy - non_arbitrage_sell
    total_net = arbitrage_net + non_arbitrage_net
    unit = 100_000_000.0
    return {
        "net_100m_krw": round(total_net / unit, 2),
        "arbitrage_net_100m_krw": round(arbitrage_net / unit, 2),
        "non_arbitrage_net_100m_krw": round(non_arbitrage_net / unit, 2),
        "arbitrage_buy_100m_krw": round(arbitrage_buy / unit, 2),
        "arbitrage_sell_100m_krw": round(arbitrage_sell / unit, 2),
        "non_arbitrage_buy_100m_krw": round(non_arbitrage_buy / unit, 2),
        "non_arbitrage_sell_100m_krw": round(non_arbitrage_sell / unit, 2),
        "as_of": raw.get("bizdate"),
        "source_id": SOURCE_ID,
        "source_kind": SOURCE_KIND,
        "raw_available": True,
    }


def normalize_index_basic(payload: Any, code: str) -> dict[str, Any]:
    source = _payload(payload)
    row = source if isinstance(source, dict) else next(_iter_dicts(source), {})
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    close = _number(row.get("closePrice") or row.get("currentPrice") or row.get("nowVal"))
    change = _number(row.get("compareToPreviousClosePrice") or row.get("compareToPreviousPrice"))
    change_pct = _number(row.get("fluctuationsRatio") or row.get("changeRate"))
    return {
        "code": code,
        "close": close,
        "change": change,
        "change_pct": change_pct,
        "trading_volume": _number(row.get("accumulatedTradingVolume") or row.get("tradingVolume")),
        "trading_value": _number(row.get("accumulatedTradingValue") or row.get("tradingValue")),
        "market_status": row.get("marketStatus") or row.get("marketStatusType"),
        "as_of": row.get("localTradedAt") or row.get("localDate") or now,
        "retrieved_at": now,
        "source_id": SOURCE_ID,
        "source_kind": SOURCE_KIND,
        "source_url": f"{FRONT}/stock/domestic/basic?code={code}&endType=index",
    }


def _market_row(rows: Any, code: str) -> dict[str, Any] | None:
    aliases = {
        code.upper(),
        {"KOSPI": "코스피", "KOSDAQ": "코스닥", "KPI200": "코스피200"}.get(code.upper(), code).upper(),
    }
    normalized_aliases = {a.replace(" ", "").upper() for a in aliases}
    for row in _iter_dicts(rows):
        candidates = [row.get(k) for k in ("itemCode", "code", "cd", "name", "itemName", "nm")]
        if any(
            str(v).replace(" ", "").upper() in normalized_aliases
            for v in candidates
            if v is not None
        ):
            return row
    return None


def _positional_row(rows: Any, position: int) -> dict[str, Any]:
    if isinstance(rows, list) and 0 <= position < len(rows) and isinstance(rows[position], dict):
        return rows[position]
    return {}


def normalize_main_summary(payload: Any) -> dict[str, Any]:
    root = _payload(payload)
    if not isinstance(root, dict):
        root = payload if isinstance(payload, dict) else {}
    item_rows = root.get("todayIndexItemList") or []
    trend_rows = root.get("todayIndexDealTrendList") or []
    program = root.get("kospiTrendProgram")
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result: dict[str, Any] = {"indices": {}, "program": program, "retrieved_at": now}

    # Naver has historically returned these lists in KOSPI/KOSDAQ/KPI200 order.
    # Some responses omit itemCode/name entirely, so positional fallback is
    # required; otherwise every flow becomes null and every breadth count zero.
    positions = {"KOSPI": 0, "KOSDAQ": 1, "KPI200": 2}
    for code in ("KOSPI", "KOSDAQ", "KPI200"):
        pos = positions[code]
        item = _market_row(item_rows, code) or _positional_row(item_rows, pos)
        trend = _market_row(trend_rows, code) or _positional_row(trend_rows, pos)
        flows = {
            "individual": _number(trend.get("personalValue") or trend.get("individualValue")),
            "foreign": _number(trend.get("foreignValue") or trend.get("foreignerValue")),
            "institution": _number(trend.get("institutionalValue") or trend.get("institutionValue")),
        }
        breadth = {
            "upper": int(_number(item.get("upperCnt")) or 0),
            "advance": int(_number(item.get("riseCnt")) or 0),
            "flat": int(_number(item.get("steadyCnt")) or 0),
            "decline": int(_number(item.get("fallCnt")) or 0),
            "lower": int(_number(item.get("lowerCnt")) or 0),
        }
        result["indices"][code] = {
            "flows_100m_krw": flows,
            "breadth": breadth,
            "as_of": trend.get("bizdate") or item.get("bizdate") or now,
            "source_id": SOURCE_ID,
            "source_kind": SOURCE_KIND,
            "source_url": MAIN_SUMMARY,
        }
    return result


def _date_text(value: Any) -> str:
    raw = str(value or "").strip()
    compact = raw.replace(".", "").replace("-", "").replace("/", "")
    if len(compact) >= 8 and compact[:8].isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    return raw[:10]


def normalize_stock_bars(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _iter_dicts(_payload(payload)):
        date = row.get("localTradedAt") or row.get("localDate") or row.get("date") or row.get("x")
        close = _number(row.get("closePrice") or row.get("close") or row.get("y"))
        open_ = _number(row.get("openPrice") or row.get("open"))
        high = _number(row.get("highPrice") or row.get("high"))
        low = _number(row.get("lowPrice") or row.get("low"))
        volume = _number(row.get("accumulatedTradingVolume") or row.get("tradingVolume") or row.get("volume"))
        if date is None or close is None or volume is None:
            continue
        key = _date_text(date)
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append({
            "date": key,
            "open": open_ if open_ is not None else close,
            "high": high if high is not None else close,
            "low": low if low is not None else close,
            "close": close,
            "volume": volume,
            "trading_value": _number(row.get("accumulatedTradingValue") or row.get("tradingValue")),
            "source_id": SOURCE_ID,
            "source_kind": SOURCE_KIND,
        })
    rows.sort(key=lambda item: item["date"])
    return rows
