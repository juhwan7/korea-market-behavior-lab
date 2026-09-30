from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from kmb_lab.http_client import HttpError, request_json, request_text

FRONT = "https://m.stock.naver.com/front-api"
STOCK_WEB = "https://stock.naver.com"
MOBILE_API = "https://m.stock.naver.com/api"
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


def fetch_kospi200_futures_price(page_size: int = 20) -> list[dict[str, Any]]:
    payload = request_json(
        f"{MOBILE_API}/index/FUT/price",
        params={"pageSize": min(max(1, page_size), 60), "page": 1},
        headers={"Referer": "https://m.stock.naver.com/domestic/index/FUT/total"},
    )
    if not isinstance(payload, list):
        raise HttpError("Naver FUT price returned non-list JSON")
    return [row for row in payload if isinstance(row, dict)]


def fetch_kospi200_futures_trend(bizdate: str | None = None) -> dict[str, Any]:
    params = {"bizdate": bizdate} if bizdate else None
    payload = request_json(
        f"{MOBILE_API}/index/FUT/trend",
        params=params,
        headers={"Referer": "https://m.stock.naver.com/domestic/index/FUT/total"},
    )
    row = payload[0] if isinstance(payload, list) and payload and isinstance(payload[0], dict) else payload
    if not isinstance(row, dict):
        raise HttpError("Naver FUT trend returned unexpected JSON")
    return row


def normalize_kospi200_futures(price_rows: list[dict[str, Any]], trend: dict[str, Any] | None = None) -> dict[str, Any]:
    if not price_rows:
        raise HttpError("Naver FUT price rows empty")
    latest = price_rows[0]
    price = _number(latest.get("closePrice"))
    change = _number(latest.get("compareToPreviousClosePrice"))
    if price is None:
        raise HttpError("Naver FUT latest close missing")
    previous = price - change if change is not None else None
    change_pct = _number(latest.get("fluctuationsRatio"))
    if change_pct is None and previous not in (None, 0):
        change_pct = (price / previous - 1.0) * 100.0

    trend = trend or {}
    flows = {
        "individual": _number(trend.get("personalValue") or trend.get("individualValue")),
        "foreign": _number(trend.get("foreignValue") or trend.get("foreignerValue")),
        "institution": _number(trend.get("institutionalValue") or trend.get("institutionValue")),
    }
    history = []
    for row in reversed(price_rows):
        close = _number(row.get("closePrice"))
        if close is None:
            continue
        history.append({
            "date": _date_text(row.get("localTradedAt")),
            "close": close,
            "change": _number(row.get("compareToPreviousClosePrice")),
            "change_pct": _number(row.get("fluctuationsRatio")),
        })
    return {
        "status": "CONNECTED_SECONDARY",
        "instrument": "KOSPI200 연결선물 (NAVER FUT)",
        "close": price,
        "previous_close": previous,
        "change": change,
        "change_pct": round(change_pct, 3) if isinstance(change_pct, (int, float)) else None,
        "as_of": latest.get("localTradedAt"),
        "investor_flow_100m_krw": flows,
        "flow_as_of": trend.get("bizdate"),
        "history": history,
        "open_interest": None,
        "source_id": SOURCE_ID,
        "source_kind": SOURCE_KIND,
        "source_url": f"{MOBILE_API}/index/FUT/price",
        "note": "무료 공개 보조 데이터입니다. KRX 공식 데이터가 연결되면 공식값을 우선합니다.",
    }


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


def fetch_market_universe(market: str, *, page_size: int = 100, max_pages: int = 35) -> list[dict[str, Any]]:
    """Fetch the public Naver market-cap list with intraday trading value fields.

    This is a secondary source used for turnover participation analysis. Pages
    stop as soon as Naver returns fewer rows than requested.
    """
    market = market.upper()
    if market not in {"KOSPI", "KOSDAQ"}:
        raise ValueError(f"unsupported market: {market}")
    rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        payload = request_json(
            f"{MOBILE_API}/stocks/marketValue/{market}",
            params={"page": page, "pageSize": page_size},
            headers={"Referer": f"https://m.stock.naver.com/domestic/{market.lower()}"},
        )
        stocks = payload.get("stocks") if isinstance(payload, dict) else None
        if not isinstance(stocks, list):
            raise HttpError(f"Naver marketValue {market} returned unexpected JSON")
        valid = [row for row in stocks if isinstance(row, dict)]
        rows.extend(valid)
        if len(valid) < page_size:
            break
    return rows



def top_turnover_candidates(rows: list[dict[str, Any]], market: str, *, limit: int = 6) -> list[dict[str, Any]]:
    """Select liquid symbols for model validation, not as investment recommendations."""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        code = str(row.get("itemCode") or row.get("stockCode") or row.get("code") or "").strip().upper()
        name = str(row.get("stockName") or row.get("itemName") or row.get("name") or code).strip()
        value = _number(
            row.get("accumulatedTradingValueRaw")
            or row.get("accumulatedTradingValue")
            or row.get("tradingValue")
        )
        if not code or code in seen or value is None or value <= 0:
            continue
        if not re.fullmatch(r"[0-9A-Z]{6}", code):
            continue
        seen.add(code)
        candidates.append({
            "code": code,
            "name": name or code,
            "benchmark": market.upper(),
            "trading_value_krw": round(float(value), 0),
            "selection_reason": "top_intraday_trading_value_validation_sample",
        })
    candidates.sort(key=lambda row: float(row["trading_value_krw"]), reverse=True)
    return candidates[:max(0, limit)]


def normalize_turnover_participation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    advance = decline = flat = total = 0.0
    valid_count = 0
    for row in rows:
        raw_value = (
            row.get("accumulatedTradingValueRaw")
            or row.get("accumulatedTradingValue")
            or row.get("tradingValue")
        )
        value = _number(raw_value)
        change_pct = _number(row.get("fluctuationsRatio") or row.get("changeRate"))
        if value is None or value < 0 or change_pct is None:
            continue
        valid_count += 1
        total += value
        if change_pct > 0:
            advance += value
        elif change_pct < 0:
            decline += value
        else:
            flat += value
    directional = advance + decline
    adv_share = advance / directional if directional > 0 else None
    ratio = advance / decline if decline > 0 else (None if advance <= 0 else 10.0)
    return {
        "evidence_state": "ESTIMATED" if valid_count else "UNKNOWN",
        "stock_count": valid_count,
        "total_trading_value_krw": round(total, 0) if valid_count else None,
        "advance_trading_value_krw": round(advance, 0) if valid_count else None,
        "decline_trading_value_krw": round(decline, 0) if valid_count else None,
        "flat_trading_value_krw": round(flat, 0) if valid_count else None,
        "advance_directional_share": round(adv_share, 4) if adv_share is not None else None,
        "advance_decline_turnover_ratio": round(ratio, 4) if ratio is not None else None,
        "source_id": SOURCE_ID,
        "source_kind": SOURCE_KIND,
        "method_note": "상승·하락 종목의 누적 거래대금을 합산한 장중 거래대금 참여도입니다.",
    }



def fetch_sector_list() -> Any:
    """Fetch a public domestic industry ranking with bounded fallbacks.

    Naver's old mobile front-api sector route started returning HTTP 400 in
    September 2026. Prefer the current stock.naver.com category APIs and keep
    the old route only as a final compatibility fallback.

    Every route here is an undocumented secondary source. The result must never
    be promoted to official KRX industry breadth.
    """
    attempts: list[str] = []
    candidates = [
        (
            f"{STOCK_WEB}/api/stockSecurity/rankings/v2/domestic/industries",
            {"sortType": "changeRate", "size": 100, "period": "daily"},
            {"Referer": f"{STOCK_WEB}/"},
        ),
        (
            f"{STOCK_WEB}/api/domestic/market/upjong/list",
            {"startIdx": 0, "pageSize": 100, "sortType": "changeRate"},
            {"Referer": f"{STOCK_WEB}/"},
        ),
        (
            f"{FRONT}/stock/sectors/all",
            {"nationType": "domestic", "sectorType": "upjong"},
            {"Referer": REFERER},
        ),
    ]
    for url, params, headers in candidates:
        try:
            payload = request_json(url, params=params, headers=headers)
        except HttpError as exc:
            attempts.append(str(exc))
            continue
        if isinstance(payload, (dict, list)):
            normalized = normalize_sector_dispersion(payload)
            if normalized.get("sector_count", 0) > 0:
                return payload
            attempts.append(f"{url}: response contained no normalizable sector rows")
        else:
            attempts.append(f"{url}: unexpected response type {type(payload).__name__}")
    raise HttpError("all public sector ranking fallbacks failed: " + " | ".join(attempts))


def normalize_sector_dispersion(payload: Any) -> dict[str, Any]:
    sectors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _iter_dicts(_payload(payload)):
        change = _number(row.get("fluctuationsRatio") or row.get("changeRate") or row.get("rate"))
        name = row.get("sectorName") or row.get("name") or row.get("itemName") or row.get("stockName")
        code = (
            row.get("sectorCode") or row.get("industryCode") or row.get("categoryCode")
            or row.get("code") or row.get("itemCode") or row.get("no")
        )
        if change is None or not name:
            continue
        key = str(code or name)
        if key in seen:
            continue
        seen.add(key)
        sectors.append({"code": code, "name": str(name), "change_pct": change})
    sectors.sort(key=lambda x: float(x["change_pct"]), reverse=True)
    positive = sum(1 for row in sectors if row["change_pct"] > 0)
    negative = sum(1 for row in sectors if row["change_pct"] < 0)
    flat = len(sectors) - positive - negative
    directional = positive + negative
    return {
        "evidence_state": "ESTIMATED" if sectors else "UNKNOWN",
        "sector_count": len(sectors),
        "positive": positive,
        "negative": negative,
        "flat": flat,
        "positive_directional_share": round(positive / directional, 4) if directional else None,
        "average_change_pct": round(sum(float(x["change_pct"]) for x in sectors) / len(sectors), 3) if sectors else None,
        "strongest": sectors[:8],
        "weakest": list(reversed(sectors[-8:])),
        "sectors": sectors,
        "source_id": SOURCE_ID,
        "source_kind": SOURCE_KIND,
        "method_note": "네이버 공개 업종지수의 상승·하락 확산도 프록시이며 KRX 공식 업종 구성종목 breadth가 아닙니다.",
    }


def _market_cap_krw(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raw = str(value or "").strip().replace(",", "").replace(" ", "")
    if not raw:
        return None
    total = 0.0
    matched = False
    trillion = re.search(r"([0-9]+(?:\.[0-9]+)?)조", raw)
    billion = re.search(r"([0-9]+(?:\.[0-9]+)?)억", raw)
    if trillion:
        total += float(trillion.group(1)) * 1_000_000_000_000
        matched = True
    if billion:
        total += float(billion.group(1)) * 100_000_000
        matched = True
    if matched:
        return total
    return _number(raw)


def normalize_size_participation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable: list[dict[str, float]] = []
    for row in rows:
        cap = _market_cap_krw(
            row.get("marketValueRaw") or row.get("marketValue") or
            row.get("marketCap") or row.get("marketCapitalization")
        )
        change = _number(row.get("fluctuationsRatio") or row.get("changeRate"))
        turnover = _number(
            row.get("accumulatedTradingValueRaw") or row.get("accumulatedTradingValue") or row.get("tradingValue")
        )
        if cap is None or cap <= 0 or change is None:
            continue
        usable.append({"cap": cap, "change": change, "turnover": max(0.0, turnover or 0.0)})
    if len(usable) < 30:
        return {"evidence_state": "UNKNOWN", "stock_count": len(usable), "reason": "시가총액 기준 유효 종목이 30개 미만입니다."}

    usable.sort(key=lambda x: x["cap"], reverse=True)
    n = len(usable)
    large_end = max(1, int(n * 0.20))
    mid_end = max(large_end + 1, int(n * 0.50))
    groups = {
        "large_proxy": usable[:large_end],
        "mid_proxy": usable[large_end:mid_end],
        "small_proxy": usable[mid_end:],
    }
    total_cap = sum(x["cap"] for x in usable)
    total_turnover = sum(x["turnover"] for x in usable)

    def summarize(group: list[dict[str, float]]) -> dict[str, Any]:
        adv = sum(1 for x in group if x["change"] > 0)
        dec = sum(1 for x in group if x["change"] < 0)
        flat = len(group) - adv - dec
        return {
            "stock_count": len(group),
            "advance": adv,
            "decline": dec,
            "flat": flat,
            "advance_share": round(adv / len(group), 4) if group else None,
            "average_change_pct": round(sum(x["change"] for x in group) / len(group), 3) if group else None,
            "market_cap_share": round(sum(x["cap"] for x in group) / total_cap, 4) if total_cap else None,
            "turnover_share": round(sum(x["turnover"] for x in group) / total_turnover, 4) if total_turnover else None,
        }

    return {
        "evidence_state": "ESTIMATED",
        "stock_count": n,
        "classification": "market_cap_rank_proxy_top20_mid30_bottom50",
        "segments": {name: summarize(group) for name, group in groups.items()},
        "source_id": SOURCE_ID,
        "source_kind": SOURCE_KIND,
        "method_note": "공식 KRX 대형/중형/소형 지수 분류가 아니라 시가총액 순위 상위20%·중간30%·하위50% 참여도 프록시입니다.",
    }


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
        (f"{CHART_API}/{code}", {"periodType": "dayCandle", "count": page_size}),
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
