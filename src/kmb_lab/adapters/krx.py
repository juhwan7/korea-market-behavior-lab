from __future__ import annotations

from datetime import date, timedelta, datetime, timezone
import os
from typing import Any

from kmb_lab.http_client import HttpError, request_json

BASE = "https://data-dbg.krx.co.kr/svc/apis"
SOURCE_ID = "krx-openapi"
SOURCE_KIND = "primary"


def fetch_api(category: str, api_id: str, bas_dd: str, *, auth_key: str | None = None) -> list[dict[str, Any]]:
    key = auth_key or os.environ.get("KRX_AUTH_KEY")
    if not key:
        raise HttpError("KRX_AUTH_KEY is not configured")
    payload = request_json(
        f"{BASE}/{category}/{api_id}",
        params={"basDd": bas_dd},
        headers={"AUTH_KEY": key, "Accept": "application/json"},
    )
    if not isinstance(payload, dict):
        raise HttpError("KRX returned non-object JSON")
    rows = payload.get("OutBlock_1") or payload.get("output") or payload.get("result") or []
    if not isinstance(rows, list):
        raise HttpError("KRX response does not contain a row list")
    return [row for row in rows if isinstance(row, dict)]


def latest_available(category: str, api_id: str, *, start: date | None = None, lookback_days: int = 10, auth_key: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    current = start or datetime.now(timezone.utc).date()
    errors: list[str] = []
    for delta in range(lookback_days + 1):
        day = current - timedelta(days=delta)
        if day.weekday() >= 5:
            continue
        bas_dd = day.strftime("%Y%m%d")
        try:
            rows = fetch_api(category, api_id, bas_dd, auth_key=auth_key)
            if rows:
                return bas_dd, rows
        except Exception as exc:
            errors.append(f"{bas_dd}:{exc}")
            if "KRX_AUTH_KEY" in str(exc):
                break
    raise HttpError("no KRX rows found: " + " | ".join(errors[-3:]))


def _num(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value in (None, "", "-"):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def summarize_equity_rows(rows: list[dict[str, Any]], market: str, bas_dd: str) -> dict[str, Any]:
    advance = decline = flat = 0
    trading_value = market_cap = 0.0
    for row in rows:
        diff = _num(row, "CMPPREVDD_PRC")
        if diff is not None:
            if diff > 0: advance += 1
            elif diff < 0: decline += 1
            else: flat += 1
        trading_value += _num(row, "ACC_TRDVAL") or 0.0
        market_cap += _num(row, "MKTCAP") or 0.0
    return {
        "market": market,
        "as_of": bas_dd,
        "breadth": {"advance": advance, "decline": decline, "flat": flat},
        "trading_value_krw": trading_value,
        "market_cap_krw": market_cap,
        "issues": len(rows),
        "source_id": SOURCE_ID,
        "source_kind": SOURCE_KIND,
        "source_url": "https://openapi.krx.co.kr/",
    }


def fetch_equity_market(*, auth_key: str | None = None) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for market, api_id in (("KOSPI", "stk_bydd_trd"), ("KOSDAQ", "ksq_bydd_trd")):
        day, rows = latest_available("sto", api_id, auth_key=auth_key)
        output[market] = summarize_equity_rows(rows, market, day)
    return output


def select_kospi200_futures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        name = " ".join(str(row.get(k) or "") for k in ("PROD_NM", "ISU_NM", "MKT_NM")).lower()
        normalized = name.replace(" ", "")
        if ("코스피200" in normalized or "kospi200" in normalized) and "미니" not in normalized and "mini" not in normalized:
            selected.append(row)
    return selected


def fetch_kospi200_futures(*, auth_key: str | None = None) -> dict[str, Any]:
    day, rows = latest_available("drv", "fut_bydd_trd", auth_key=auth_key)
    selected = select_kospi200_futures(rows)
    if not selected:
        raise HttpError(f"KRX futures returned no KOSPI200 rows for {day}")
    selected.sort(key=lambda r: _num(r, "ACC_TRDVOL") or 0.0, reverse=True)
    row = selected[0]
    return {
        "as_of": day,
        "instrument": row.get("ISU_NM") or row.get("ISU_CD"),
        "close": _num(row, "TDD_CLSPRC"),
        "spot": _num(row, "SPOT_PRC"),
        "basis": ((_num(row, "TDD_CLSPRC") or 0) - (_num(row, "SPOT_PRC") or 0)) if _num(row, "TDD_CLSPRC") is not None and _num(row, "SPOT_PRC") is not None else None,
        "volume": _num(row, "ACC_TRDVOL"),
        "trading_value": _num(row, "ACC_TRDVAL"),
        "open_interest": _num(row, "ACC_OPNINT_QTY"),
        "source_id": SOURCE_ID,
        "source_kind": SOURCE_KIND,
        "source_url": "https://openapi.krx.co.kr/",
    }
