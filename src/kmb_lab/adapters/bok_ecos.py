from __future__ import annotations

from datetime import datetime, timezone
import html
import re
from typing import Any

from kmb_lab.http_client import request_text

BASE = "https://ecos.bok.or.kr/"
SOURCE_ID = "bok-ecos-public-page"
SOURCE_KIND = "primary"

LABELS: dict[str, tuple[str, ...]] = {
    "USD_KRW": ("원/달러", "원달러", "미달러"),
    "KOREA_3Y": ("국고채(3년)", "국고채 3년", "국고채3년"),
    "KOSPI": ("코스피", "KOSPI"),
    "KOSDAQ": ("코스닥", "KOSDAQ"),
}


def _plain_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def _find_value(text: str, aliases: tuple[str, ...]) -> tuple[float | None, str | None]:
    for alias in aliases:
        pattern = re.compile(
            re.escape(alias) + r".{0,80}?([+-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?|[+-]?\d+(?:\.\d+)?)",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if not match:
            continue
        try:
            value = float(match.group(1).replace(",", ""))
        except ValueError:
            continue
        tail = text[match.end():match.end() + 100]
        asof = re.search(r"\b(\d{2}\.\d{2}(?:\s+\d{2}:\d{2}|\s*마감)?)\b", tail)
        return value, asof.group(1) if asof else None
    return None, None


def normalize_daily_indicators(raw_html: str) -> dict[str, Any]:
    text = _plain_text(raw_html)
    observed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    indicators: dict[str, Any] = {}
    for key, aliases in LABELS.items():
        value, as_of_text = _find_value(text, aliases)
        if value is None:
            continue
        indicators[key] = {
            "value": value,
            "as_of_text": as_of_text,
            "observed_at": observed,
            "source_id": SOURCE_ID,
            "source_kind": SOURCE_KIND,
            "source_url": BASE,
        }
    return {
        "generated_at": observed,
        "status": "CONNECTED_PRIMARY" if indicators else "PARTIAL",
        "indicators": indicators,
        "source_id": SOURCE_ID,
        "source_kind": SOURCE_KIND,
        "source_url": BASE,
        "method_note": (
            "한국은행 ECOS 공개 화면에서 직접 관측한 지표입니다. 화면에 표시된 기준시각을 함께 보존하며, "
            "파싱하지 못한 항목은 임의 값으로 채우지 않습니다."
        ),
    }


def fetch_daily_indicators() -> dict[str, Any]:
    raw = request_text(BASE, headers={"Accept": "text/html,application/xhtml+xml,*/*"}, timeout=10, retries=1)
    return normalize_daily_indicators(raw)
