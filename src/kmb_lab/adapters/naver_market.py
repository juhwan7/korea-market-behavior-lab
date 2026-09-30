from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from kmb_lab.http_client import HttpError, request_json

FRONT = "https://m.stock.naver.com/front-api"
MAIN_SUMMARY = "https://finance.naver.com/main/mainSummary.naver"
LEGACY_STOCK = "https://m.stock.naver.com/api/stock"
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
    # mainSummary currently exposes kospiTrendProgram. Keeping this function separate
    # lets us swap to a dedicated endpoint without changing pipeline contracts.
    return fetch_main_summary()


def fetch_stock_daily(code: str, page_size: int = 80) -> list[dict[str, Any]]:
    errors: list[str] = []
    candidates = [
        (f"{FRONT}/chart/domestic/stock/end", {"code": code, "chartInfoType": "item", "scriptChartType": "candleDay"}),
        (f"{LEGACY_STOCK}/{code}/price", {"pageSize": page_size, "page": 1}),
    ]
    for url, params in candidates:
        try:
            payload = request_json(url, params=params, headers={"Referer": REFERER})
            rows = normalize_stock_bars(payload)
            if rows:
                return rows[-page_size:]
        except Exception as exc:  # source fallback is intentional
            errors.append(str(exc))
    raise HttpError("Naver stock history unavailable: " + " | ".join(errors))


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
        "market_status": row.get("marketStatus") or row.get("marketStatusType"),
        "as_of": row.get("localTradedAt") or row.get("localDate") or now,
        "retrieved_at": now,
        "source_id": SOURCE_ID,
        "source_kind": SOURCE_KIND,
        "source_url": f"{FRONT}/stock/domestic/basic?code={code}&endType=index",
    }


def _market_row(rows: Any, code: str) -> dict[str, Any] | None:
    aliases = {code.upper(), {"KOSPI": "코스피", "KOSDAQ": "코스닥", "KPI200": "코스피200"}.get(code.upper(), code).upper()}
    for row in _iter_dicts(rows):
        candidates = [row.get(k) for k in ("itemCode", "code", "cd", "name", "itemName", "nm")]
        if any(str(v).replace(" ", "").upper() in {a.replace(" ", "") for a in aliases} for v in candidates if v is not None):
            return row
    return None


def normalize_main_summary(payload: Any) -> dict[str, Any]:
    root = _payload(payload)
    if not isinstance(root, dict):
        root = payload if isinstance(payload, dict) else {}
    item_rows = root.get("todayIndexItemList") or []
    trend_rows = root.get("todayIndexDealTrendList") or []
    program = root.get("kospiTrendProgram")
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result: dict[str, Any] = {"indices": {}, "program": program, "retrieved_at": now}
    for code in ("KOSPI", "KOSDAQ", "KPI200"):
        item = _market_row(item_rows, code) or {}
        trend = _market_row(trend_rows, code) or {}
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
        key = str(date)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "date": key[:10],
            "open": open_ if open_ is not None else close,
            "high": high if high is not None else close,
            "low": low if low is not None else close,
            "close": close,
            "volume": volume,
            "trading_value": _number(row.get("accumulatedTradingValue") or row.get("tradingValue")),
            "source_id": SOURCE_ID,
            "source_kind": SOURCE_KIND,
        })
    rows.sort(key=lambda x: x["date"])
    return rows
