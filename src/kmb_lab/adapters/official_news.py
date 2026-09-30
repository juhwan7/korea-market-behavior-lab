from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
from typing import Any
import xml.etree.ElementTree as ET

from kmb_lab.http_client import request_text
from kmb_lab.adapters.google_news import classify_channels

SOURCE_KIND = "primary"

# No-key first-party feeds verified from the institutions' own RSS service pages.
OFFICIAL_FEEDS: tuple[dict[str, str], ...] = (
    {
        "id": "bok-press",
        "publisher": "한국은행",
        "url": "https://www.bok.or.kr/portal/bbs/B0000552/news.rss?menuNo=200690",
        "category": "보도자료",
    },
    {
        "id": "bok-monetary-policy",
        "publisher": "한국은행",
        "url": "https://www.bok.or.kr/portal/bbs/P0000559/news.rss?menuNo=200690",
        "category": "통화정책",
    },
    {
        "id": "bok-economic-statistics",
        "publisher": "한국은행",
        "url": "https://www.bok.or.kr/portal/bbs/B0000501/news.rss?menuNo=201264",
        "category": "경제통계",
    },
    {
        "id": "bok-financial-market-daily",
        "publisher": "한국은행",
        "url": "https://www.bok.or.kr/portal/bbs/B0000348/news.rss?menuNo=201109",
        "category": "금융외환시장",
    },
    {
        "id": "fsc-press",
        "publisher": "금융위원회",
        "url": "https://www.fsc.go.kr/about/fsc_bbs_rss/?fid=0111",
        "category": "보도자료",
    },
    {
        "id": "fsc-explanation",
        "publisher": "금융위원회",
        "url": "https://www.fsc.go.kr/about/fsc_bbs_rss/?fid=0112",
        "category": "보도설명",
    },
)


def _stable_id(*parts: str) -> str:
    raw = "\x1f".join(str(part or "").strip().lower() for part in parts)
    return "OFFICIAL-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _text(node: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        found = node.find(name)
        if found is not None and found.text:
            return found.text.strip()
        # Atom/RSS namespaces vary across public-sector publishers.
        for child in node:
            if child.tag.rsplit("}", 1)[-1].lower() == name.lower() and child.text:
                return child.text.strip()
    return ""


def _link(node: ET.Element) -> str:
    direct = _text(node, ("link",))
    if direct:
        return direct
    for child in node:
        if child.tag.rsplit("}", 1)[-1].lower() == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
    return ""


def _parse_time(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        pass
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def fetch_feed(feed: dict[str, str]) -> str:
    return request_text(
        feed["url"],
        headers={"Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*"},
    )


def parse_feed(xml_text: str, *, feed: dict[str, str]) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    observed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    nodes = list(root.findall(".//item"))
    if not nodes:
        nodes = [
            node for node in root.iter()
            if node.tag.rsplit("}", 1)[-1].lower() == "entry"
        ]

    rows: list[dict[str, Any]] = []
    for node in nodes:
        title = _text(node, ("title",))
        link = _link(node)
        published_raw = _text(node, ("pubDate", "published", "updated", "date"))
        published = _parse_time(published_raw)
        if not title or not link:
            continue
        classification = classify_channels(title)
        rows.append({
            "id": _stable_id(feed["id"], link, title),
            "headline": title,
            "title": title,
            "published_at": published,
            "observed_at": observed,
            "retrieved_at": observed,
            "source": feed["publisher"],
            "publisher": feed["publisher"],
            "source_type": "PRIMARY",
            "source_id": feed["id"],
            "source_kind": SOURCE_KIND,
            "url": link,
            "query": f"official:{feed['category']}",
            "cluster_id": None,
            "official_source_available": True,
            "official_category": feed["category"],
            **classification,
        })
    return rows
