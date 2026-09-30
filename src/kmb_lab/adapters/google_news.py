from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Any
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

from kmb_lab.http_client import request_text

BASE = "https://news.google.com/rss/search"
SOURCE_ID = "google-news-rss"
SOURCE_KIND = "secondary_aggregator"
DEFAULT_QUERIES = (
    "한국 증시 코스피 코스닥 외국인 수급",
    "반도체 AI HBM 삼성전자 SK하이닉스",
    "미국 증시 나스닥 연준 금리 국채",
    "유가 원달러 환율 지정학 리스크",
)
STOP = {"관련", "대한", "오늘", "증시", "시장", "주식", "한국", "미국", "속보", "단독", "기자", "뉴스"}


def build_url(query: str) -> str:
    return BASE + "?" + urlencode({"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})


def fetch_rss(query: str) -> str:
    return request_text(build_url(query), headers={"Accept": "application/rss+xml,application/xml,text/xml,*/*"})


def parse_rss(xml_text: str, *, query: str = "") -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    rows: list[dict[str, Any]] = []
    retrieved = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published_raw = (item.findtext("pubDate") or "").strip()
        source_node = item.find("source")
        publisher = ((source_node.text or "").strip() if source_node is not None else "")
        try:
            published = parsedate_to_datetime(published_raw).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            published = None
        if not title or not link:
            continue
        rows.append({
            "title": title,
            "url": link,
            "publisher": publisher,
            "published_at": published,
            "retrieved_at": retrieved,
            "query": query,
            "source_id": SOURCE_ID,
            "source_kind": SOURCE_KIND,
            "official": False,
        })
    return rows


def _tokens(title: str) -> set[str]:
    clean = re.sub(r"\s+-\s+[^-]{1,40}$", "", title)
    words = re.findall(r"[가-힣A-Za-z0-9]{2,}", clean.lower())
    return {w for w in words if w not in STOP}


def _similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def classify_channels(title: str) -> dict[str, Any]:
    text = title.lower()
    channels: list[str] = []
    sectors: list[str] = []
    countries: list[str] = []
    if any(k in text for k in ("반도체", "hbm", "엔비디아", "nvidia", "삼성전자", "sk하이닉스")):
        channels += ["semiconductor", "growth_beta"]
        sectors += ["반도체"]
    if any(k in text for k in ("연준", "fed", "금리", "국채")):
        channels += ["rates", "valuation"]
        countries += ["US"]
    if any(k in text for k in ("환율", "원달러", "달러", "usd/krw")):
        channels += ["fx", "foreign_flow"]
        countries += ["KR", "US"]
    if any(k in text for k in ("유가", "wti", "브렌트", "원유")):
        channels += ["energy", "inflation"]
        sectors += ["정유", "화학", "운송"]
    if any(k in text for k in ("전쟁", "공격", "제재", "호르무즈", "중동")):
        channels += ["geopolitics", "risk_premium"]
    if any(k in text for k in ("수출 규제", "수출통제", "관세")):
        channels += ["trade_policy", "supply_chain"]
    return {
        "market_bias": "UNDETERMINED",
        "impact_channels": sorted(set(channels)),
        "related_sectors": sorted(set(sectors)),
        "related_countries": sorted(set(countries)),
        "reason": "방향성은 제목 키워드만으로 확정하지 않고 가격·수급 반응과 공식자료로 추가 검증합니다.",
    }


def dedupe_and_cluster(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    unique: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for item in sorted(items, key=lambda x: x.get("published_at") or "", reverse=True):
        key = re.sub(r"\W+", "", str(item.get("title", "")).lower())
        url = str(item.get("url", ""))
        if url in seen_urls or key in seen_titles:
            continue
        seen_urls.add(url); seen_titles.add(key); unique.append(item)

    clusters: list[dict[str, Any]] = []
    for item in unique:
        toks = _tokens(str(item.get("title", "")))
        target = None
        best = 0.0
        for cluster in clusters:
            sim = _similarity(toks, cluster["_tokens"])
            if sim > best:
                best, target = sim, cluster
        if target is not None and best >= 0.34:
            target["articles"].append(item)
            target["_tokens"] |= toks
        else:
            clusters.append({"_tokens": set(toks), "articles": [item]})

    output: list[dict[str, Any]] = []
    for idx, cluster in enumerate(clusters):
        articles = cluster["articles"]
        pubs = sorted({a.get("publisher") for a in articles if a.get("publisher")})
        head = articles[0]
        impact = classify_channels(str(head.get("title", "")))
        output.append({
            "issue_id": f"GN-{idx+1:03d}",
            "headline": head.get("title"),
            "latest_at": max((a.get("published_at") or "" for a in articles), default=None),
            "article_count": len(articles),
            "independent_publishers": len(pubs),
            "publishers": pubs[:8],
            "state": "NEW",
            **impact,
            "articles": articles[:10],
        })
    output.sort(key=lambda x: (x.get("latest_at") or "", x.get("article_count", 0)), reverse=True)
    return unique, output
