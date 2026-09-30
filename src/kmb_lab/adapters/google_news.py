from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import re
from typing import Any
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

from kmb_lab.http_client import request_text

BASE = "https://news.google.com/rss/search"
SOURCE_ID = "google-news-rss"
SOURCE_KIND = "secondary_aggregator"

# Broad market coverage. These are discovery queries, not importance votes.
DEFAULT_QUERIES = (
    "한국 증시 코스피 코스닥 외국인 기관 수급",
    "삼성전자 SK하이닉스 반도체 HBM AI",
    "자동차 현대차 기아 로봇 스마트팩토리",
    "바이오 제약 임상 허가 한국 증시",
    "방산 조선 원전 수주 한국 기업",
    "2차전지 배터리 리튬 전기차 한국",
    "금융 은행 증권 보험 정책 한국",
    "한국 정부 정책 공시 DART 기업 실적",
    "미국 증시 나스닥 S&P500 다우 엔비디아 반도체",
    "연준 Fed 미국 국채 금리 달러 환율",
    "유가 WTI 브렌트 금 VIX 원달러",
    "중국 일본 유럽 증시 경기 부양",
    "중동 지정학 호르무즈 제재 전쟁",
    "관세 무역분쟁 수출통제 공급망",
)

STOP = {
    "관련", "대한", "오늘", "증시", "시장", "주식", "한국", "미국",
    "속보", "단독", "기자", "뉴스", "종합", "오전", "오후",
}


def build_url(query: str) -> str:
    return BASE + "?" + urlencode({"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})


def fetch_rss(query: str) -> str:
    return request_text(build_url(query), headers={"Accept": "application/rss+xml,application/xml,text/xml,*/*"})


def _stable_id(*parts: str, prefix: str) -> str:
    raw = "\x1f".join(str(p or "").strip().lower() for p in parts)
    return prefix + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _headline_without_source(title: str) -> str:
    return re.sub(r"\s+-\s+[^-]{1,60}$", "", title).strip()


def _tokens(title: str) -> set[str]:
    clean = _headline_without_source(title)
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
    markets: list[str] = []
    stocks: list[str] = []
    topics: list[str] = []

    if any(k in text for k in ("반도체", "hbm", "엔비디아", "nvidia", "삼성전자", "sk하이닉스")):
        channels += ["semiconductor", "growth_beta"]
        sectors += ["반도체"]
        markets += ["KOSPI", "NASDAQ"]
        topics += ["반도체"]
    if "삼성전자" in text:
        stocks += ["삼성전자"]
    if "sk하이닉스" in text or "하이닉스" in text:
        stocks += ["SK하이닉스"]
    if any(k in text for k in ("자동차", "현대차", "기아", "전기차")):
        sectors += ["자동차"]
        markets += ["KOSPI"]
        topics += ["자동차"]
        if "현대차" in text:
            stocks += ["현대차"]
        if "기아" in text:
            stocks += ["기아"]
    if any(k in text for k in ("바이오", "제약", "임상", "신약")):
        sectors += ["바이오"]
        markets += ["KOSDAQ", "KOSPI"]
        topics += ["바이오"]
    if any(k in text for k in ("방산", "조선", "원전")):
        topics += ["산업수주"]
        markets += ["KOSPI"]
        if "방산" in text:
            sectors += ["방산"]
        if "조선" in text:
            sectors += ["조선"]
        if "원전" in text:
            sectors += ["원전"]
    if any(k in text for k in ("2차전지", "배터리", "리튬")):
        sectors += ["2차전지"]
        markets += ["KOSPI", "KOSDAQ"]
        topics += ["2차전지"]
    if any(k in text for k in ("연준", "fed", "금리", "국채")):
        channels += ["rates", "valuation"]
        countries += ["US"]
        markets += ["NASDAQ", "S&P500", "KOSPI", "KOSDAQ"]
        topics += ["금리"]
    if any(k in text for k in ("환율", "원달러", "달러", "usd/krw")):
        channels += ["fx", "foreign_flow"]
        countries += ["KR", "US"]
        markets += ["USD/KRW", "KOSPI"]
        topics += ["환율"]
    if any(k in text for k in ("유가", "wti", "브렌트", "원유")):
        channels += ["energy", "inflation"]
        sectors += ["정유", "화학", "운송"]
        markets += ["WTI", "KOSPI"]
        topics += ["에너지"]
    if any(k in text for k in ("전쟁", "공격", "제재", "호르무즈", "중동", "지정학")):
        channels += ["geopolitics", "risk_premium"]
        markets += ["KOSPI", "NASDAQ", "WTI"]
        topics += ["지정학"]
    if any(k in text for k in ("수출 규제", "수출통제", "관세", "무역분쟁")):
        channels += ["trade_policy", "supply_chain"]
        markets += ["KOSPI", "NASDAQ"]
        topics += ["무역정책"]
    if any(k in text for k in ("중국", "상하이", "홍콩")):
        countries += ["CN"]
        markets += ["CHINA"]
    if any(k in text for k in ("일본", "닛케이", "엔화")):
        countries += ["JP"]
        markets += ["JAPAN"]

    return {
        "market_bias": "UNDETERMINED",
        "impact_channels": sorted(set(channels)),
        "related_sectors": sorted(set(sectors)),
        "related_countries": sorted(set(countries)),
        "related_markets": sorted(set(markets)),
        "related_stocks": sorted(set(stocks)),
        "topic": " · ".join(sorted(set(topics))) if topics else "시장일반",
        "reason": "방향성은 제목 키워드만으로 확정하지 않고 가격·수급 반응과 공식자료로 추가 검증합니다.",
    }


def why_important(classification: dict[str, Any]) -> str:
    channels = set(classification.get("impact_channels") or [])
    if "rates" in channels:
        return "장기금리 변화는 성장주 할인율과 글로벌 위험선호에 영향을 줄 수 있어 선물·환율·외국인 수급과 함께 확인해야 합니다."
    if "geopolitics" in channels:
        return "지정학 변화는 유가·환율·위험프리미엄을 통해 국내 증시에 전달될 수 있어 실제 가격 반응을 추가 확인해야 합니다."
    if "semiconductor" in channels:
        return "반도체는 국내 지수 비중이 커서 업종 상대강도와 외국인 수급이 지수 체감과 달라지는지 확인할 필요가 있습니다."
    if "fx" in channels:
        return "원·달러 변화는 외국인 수급과 수입비용에 연결될 수 있어 지수·선물과 동행 여부를 확인해야 합니다."
    if "energy" in channels:
        return "에너지 가격 변화는 물가·운송비·정유/화학 마진에 서로 다른 영향을 줄 수 있어 업종별 반응을 분리해야 합니다."
    return "시장 영향 가능성이 있는 뉴스이므로 관련 지수·섹터·수급이 실제로 반응하는지 확인할 필요가 있습니다."


def parse_rss(xml_text: str, *, query: str = "") -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    rows: list[dict[str, Any]] = []
    observed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
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
        classification = classify_channels(title)
        article_id = _stable_id(link, title, prefix="NEWS-")
        rows.append({
            "id": article_id,
            "headline": _headline_without_source(title),
            "title": title,
            "published_at": published,
            "observed_at": observed,
            "retrieved_at": observed,
            "source": publisher or "Google News RSS",
            "publisher": publisher,
            "source_type": "SECONDARY",
            "source_id": SOURCE_ID,
            "source_kind": SOURCE_KIND,
            "url": link,
            "query": query,
            "cluster_id": None,
            "official_source_available": False,
            **classification,
        })
    return rows


def dedupe_and_cluster(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    unique: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for item in sorted(items, key=lambda x: x.get("published_at") or "", reverse=True):
        key = re.sub(r"\W+", "", str(item.get("headline") or item.get("title", "")).lower())
        url = str(item.get("url", ""))
        if url in seen_urls or key in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(key)
        unique.append(dict(item))

    clusters: list[dict[str, Any]] = []
    for item in unique:
        toks = _tokens(str(item.get("headline") or item.get("title", "")))
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
    for cluster in clusters:
        articles = cluster["articles"]
        pubs = sorted({a.get("source") or a.get("publisher") for a in articles if a.get("source") or a.get("publisher")})
        head = articles[0]
        fingerprint_tokens = sorted(cluster["_tokens"])[:12]
        fingerprint = _stable_id("|".join(fingerprint_tokens), prefix="ISSUE-FP-")
        issue_id = "GN-" + fingerprint.replace("ISSUE-FP-", "")
        latest_at = max((a.get("published_at") or a.get("observed_at") or "" for a in articles), default=None)
        first_at = min((a.get("published_at") or a.get("observed_at") or "" for a in articles), default=None)
        impact = classify_channels(str(head.get("headline") or head.get("title", "")))
        normalized_articles = []
        for article in articles[:10]:
            row = dict(article)
            row["cluster_id"] = issue_id
            normalized_articles.append(row)
        output.append({
            "issue_id": issue_id,
            "fingerprint": fingerprint,
            "headline": head.get("headline") or head.get("title"),
            "first_seen_at": first_at,
            "latest_at": latest_at,
            "article_count": len(articles),
            "independent_publishers": len(pubs),
            "publishers": pubs[:8],
            "official_source_available": any(bool(a.get("official_source_available")) for a in articles),
            "state": "NEW",
            "why_important": why_important(impact),
            "counterpoint": "뉴스 제목과 동시 가격 움직임만으로 인과를 확정할 수 없습니다.",
            "next_variables": list(dict.fromkeys((impact.get("related_markets") or []) + ["외국인 수급", "기관 수급"]))[:6],
            "history": [],
            **impact,
            "articles": normalized_articles,
        })
    output.sort(key=lambda x: (x.get("latest_at") or "", x.get("article_count", 0), x.get("independent_publishers", 0)), reverse=True)
    return unique, output
