from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from kmb_lab.http_client import HttpError, request_json

API_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"
SOURCE_ID = "bok-ecos-open-api"
SOURCE_KIND = "primary"

SERIES: dict[str, dict[str, str]] = {
    "USD_KRW": {
        "stat_code": "731Y001",
        "item_code": "0000001",
        "cycle": "D",
        "label": "원/미국달러(매매기준율)",
    },
    "KOREA_3Y": {
        "stat_code": "817Y002",
        "item_code": "010200000",
        "cycle": "D",
        "label": "국고채(3년)",
    },
}


def normalize_search(payload: dict[str, Any], *, indicator_key: str) -> list[dict[str, Any]]:
    result = payload.get("RESULT")
    if isinstance(result, dict) and result.get("CODE"):
        raise HttpError(f"ECOS error {result.get('CODE')}: {result.get('MESSAGE') or 'UNKNOWN'}")
    block = payload.get("StatisticSearch")
    if not isinstance(block, dict):
        raise HttpError("ECOS StatisticSearch payload is missing")
    rows = block.get("row") or []
    if not isinstance(rows, list):
        raise HttpError("ECOS StatisticSearch row is not a list")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = row.get("DATA_VALUE")
        try:
            value = float(str(raw).replace(",", ""))
        except (TypeError, ValueError):
            continue
        normalized.append({
            "indicator": indicator_key,
            "value": value,
            "time": row.get("TIME"),
            "unit": row.get("UNIT_NAME"),
            "item_name": row.get("ITEM_NAME1") or SERIES.get(indicator_key, {}).get("label"),
            "stat_code": row.get("STAT_CODE") or SERIES.get(indicator_key, {}).get("stat_code"),
            "source_id": SOURCE_ID,
            "source_kind": SOURCE_KIND,
        })
    normalized.sort(key=lambda x: str(x.get("time") or ""))
    return normalized


def fetch_series(
    *,
    indicator_key: str,
    api_key: str | None = None,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    spec = SERIES[indicator_key]
    key = (api_key or "").strip() or "sample"
    limit = 10 if key == "sample" else 100
    url = (
        f"{API_BASE}/{key}/json/kr/1/{limit}/"
        f"{spec['stat_code']}/{spec['cycle']}/"
        f"{start_date:%Y%m%d}/{end_date:%Y%m%d}/{spec['item_code']}"
    )
    payload = request_json(url, headers={"Accept": "application/json"}, timeout=12, retries=1)
    if not isinstance(payload, dict):
        raise HttpError("ECOS StatisticSearch returned non-object JSON")
    return normalize_search(payload, indicator_key=indicator_key)


def fetch_daily_indicators(api_key: str | None = None) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    # The public sample credential is capped, so use a narrow window that still
    # spans weekends/short holidays while remaining below ten typical sessions.
    start = today - timedelta(days=12)
    observed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    indicators: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for key in SERIES:
        try:
            rows = fetch_series(indicator_key=key, api_key=api_key, start_date=start, end_date=today)
        except Exception as exc:
            errors[key] = str(exc)
            continue
        if not rows:
            errors[key] = "no rows returned"
            continue
        latest = rows[-1]
        indicators[key] = {
            "value": latest["value"],
            "as_of_text": latest.get("time"),
            "unit": latest.get("unit"),
            "item_name": latest.get("item_name"),
            "observed_at": observed,
            "source_id": SOURCE_ID,
            "source_kind": SOURCE_KIND,
            "source_url": API_BASE,
        }
    status = "CONNECTED_PRIMARY" if indicators else "FAILED"
    return {
        "generated_at": observed,
        "status": status,
        "indicators": indicators,
        "errors": errors,
        "source_id": SOURCE_ID,
        "source_kind": SOURCE_KIND,
        "source_url": API_BASE,
        "credential_mode": "configured" if (api_key or "").strip() else "sample_demo",
        "method_note": (
            "한국은행 ECOS 공식 Open API StatisticSearch를 사용합니다. 별도 키가 없으면 sample 인증으로 "
            "최신 소수 행만 조회하며, 조회 실패 항목은 임의 값으로 채우지 않습니다."
        ),
    }
