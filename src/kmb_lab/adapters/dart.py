from __future__ import annotations

from datetime import date
from typing import Any

from kmb_lab.http_client import HttpError, request_json

BASE = "https://opendart.fss.or.kr/api/list.json"
SOURCE_ID = "opendart"
SOURCE_KIND = "primary"


def _date_text(value: Any) -> str | None:
    raw = str(value or "").strip().replace("-", "")
    if len(raw) >= 8 and raw[:8].isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return None


def normalize_disclosures(payload: dict[str, Any]) -> list[dict[str, Any]]:
    status = str(payload.get("status") or "")
    if status == "013":
        return []
    if status != "000":
        raise HttpError(
            f"OpenDART list API failed status={status or 'UNKNOWN'} "
            f"message={payload.get('message') or 'UNKNOWN'}"
        )
    rows = payload.get("list") or []
    if not isinstance(rows, list):
        raise HttpError("OpenDART list API returned non-list disclosure payload")
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        receipt = str(row.get("rcept_no") or "").strip()
        report = str(row.get("report_nm") or "").strip()
        corp = str(row.get("corp_name") or "").strip()
        if not receipt or not report or not corp:
            continue
        output.append({
            "id": f"DART-{receipt}",
            "corp_code": row.get("corp_code"),
            "corp_name": corp,
            "stock_code": str(row.get("stock_code") or "").strip() or None,
            "report_name": report,
            "submitter": row.get("flr_nm"),
            "receipt_no": receipt,
            "receipt_date": _date_text(row.get("rcept_dt")),
            "remark": row.get("rm"),
            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}",
            "source_id": SOURCE_ID,
            "source_kind": SOURCE_KIND,
            "source_url": BASE,
            "official_source_available": True,
        })
    return output


def fetch_disclosures(*, api_key: str, begin_date: date, end_date: date, page_count: int = 100) -> list[dict[str, Any]]:
    if not api_key:
        raise HttpError("DART_API_KEY is not configured")
    payload = request_json(
        BASE,
        params={
            "crtfc_key": api_key,
            "bgn_de": begin_date.strftime("%Y%m%d"),
            "end_de": end_date.strftime("%Y%m%d"),
            "page_no": 1,
            "page_count": min(max(int(page_count), 1), 100),
            "sort": "date",
            "sort_mth": "desc",
        },
        headers={"Accept": "application/json"},
    )
    if not isinstance(payload, dict):
        raise HttpError("OpenDART list API returned non-object JSON")
    return normalize_disclosures(payload)
