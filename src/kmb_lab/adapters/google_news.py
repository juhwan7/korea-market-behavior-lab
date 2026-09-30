from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import re
from collections import Counter
from difflib import SequenceMatcher
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
    scoped = query if "when:" in query.lower() else f"{query} when:1d"
    return BASE + "?" + urlencode({"q": scoped, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})


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



PROMO_TERMS = {
    "리딩방": 4, "수강생": 4, "무료체험": 4, "할인쿠폰": 4,
    "경품": 3, "증정": 3, "체험단": 3, "프로모션": 3,
    "기획전": 2, "세미나": 2, "설명회": 2, "이벤트": 1,
    "캠페인": 1, "혜택": 1, "출시기념": 2,
}
MARKET_FACT_TERMS = (
    "실적", "매출", "영업이익", "순이익", "수주", "계약", "공급계약",
    "투자", "증설", "공장", "인수", "합병", "m&a", "공시", "허가",
    "임상", "배당", "자사주", "증자", "감자", "제재", "과징금",
    "리콜", "파산", "회생", "채권발행", "유상증자", "무상증자",
)

LOW_INFORMATION_PATTERNS = (
    r"종목이 .{0,40}(?:상승|하락)한 이유는 무엇인가요",
    r"상한가 및 상승종목",
    r"오늘의 추천주",
    r"급등주 추천",
    r"종목추천",
)
GENERIC_EVENT_TOKENS = {
    "오늘", "관련", "시장", "증시", "주가", "코스피", "코스닥", "한국", "미국",
    "발표", "계획", "추진", "전망", "확대", "상승", "하락", "강세", "약세",
    "속도", "도약", "그룹", "억원", "조원", "종목", "뉴스", "기자",
}
ACTION_GROUPS = {
    "인수합병": ("인수", "취득", "합병", "경영권", "본계약", "품는다", "품고"),
    "투자증설": ("투자", "증설", "출자", "증자", "공장", "설비"),
    "실적": ("실적", "매출", "영업이익", "순이익", "적자", "흑자"),
    "계약수주": ("계약", "수주", "공급계약", "납품"),
    "정책규제": ("규제", "제재", "법안", "금지", "허가", "승인"),
    "금리채권": ("금리", "국채", "채권", "기준금리"),
}


def _normalized_headline(value: str) -> str:
    text = _headline_without_source(value).lower()
    text = re.sub(r"\([^)]*\)|\[[^]]*\]", " ", text)
    return re.sub(r"[^가-힣a-z0-9]+", " ", text).strip()


def _headline_similarity(a: str, b: str) -> float:
    na, nb = _normalized_headline(a), _normalized_headline(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def classify_content_quality(item: dict[str, Any]) -> dict[str, Any]:
    """Classify promotional/reprint risk without turning headlines into facts."""
    headline = str(item.get("headline") or item.get("title") or "")
    lower = headline.lower()
    primary = bool(item.get("official_source_available")) or str(item.get("source_type") or "").upper() == "PRIMARY"
    score = sum(weight for token, weight in PROMO_TERMS.items() if token in lower)
    factual = any(token in lower for token in MARKET_FACT_TERMS)
    low_information = any(re.search(pattern, headline, flags=re.IGNORECASE) for pattern in LOW_INFORMATION_PATTERNS)
    hard_promo = bool(not primary and score >= 3 and not factual)
    possible = bool(not primary and score > 0 and not factual)
    filtered = bool(not primary and (hard_promo or low_information))
    if primary:
        quality = "OFFICIAL_FACTUAL_OR_NOTICE"
    elif hard_promo:
        quality = "PROMOTIONAL"
    elif low_information:
        quality = "LOW_INFORMATION"
    elif possible:
        quality = "POSSIBLE_PROMOTION"
    else:
        quality = "EDITORIAL_OR_FACTUAL"
    return {
        "promotion_score": score,
        "content_quality": quality,
        "is_promotional": hard_promo,
        "is_low_information": low_information,
        "filter_from_market_feed": filtered,
        "market_fact_signal": factual,
    }


def _salient_tokens(title: str) -> set[str]:
    return {token for token in _tokens(title) if token not in GENERIC_EVENT_TOKENS and len(token) >= 2}


def _action_groups(title: str) -> set[str]:
    lower = title.lower()
    return {
        group for group, terms in ACTION_GROUPS.items()
        if any(term.lower() in lower for term in terms)
    }


def _cluster_match(item_tokens: set[str], item_title: str, cluster: dict[str, Any]) -> float:
    token_score = _similarity(item_tokens, cluster["_tokens"])
    title_score = max(
        (_headline_similarity(item_title, str(a.get("headline") or a.get("title") or "")) for a in cluster["articles"]),
        default=0.0,
    )
    common = len(item_tokens & cluster["_tokens"])
    item_salient = _salient_tokens(item_title)
    cluster_salient = set().union(*(
        _salient_tokens(str(a.get("headline") or a.get("title") or ""))
        for a in cluster["articles"]
    ))
    salient_common = len(item_salient & cluster_salient)
    item_actions = _action_groups(item_title)
    cluster_actions = set().union(*(
        _action_groups(str(a.get("headline") or a.get("title") or ""))
        for a in cluster["articles"]
    ))
    action_match = bool(item_actions & cluster_actions)

    if title_score >= 0.82 and common >= 2:
        return max(token_score, title_score)
    if token_score >= 0.30 and common >= 2:
        return token_score
    # Different wording can still describe one event when two uncommon core
    # tokens overlap, or one uncommon entity overlaps with the same action.
    if salient_common >= 2:
        return max(0.72, title_score)
    if salient_common >= 1 and action_match:
        return max(0.64, title_score)
    return 0.0


def _event_core_tokens(articles: list[dict[str, Any]]) -> list[str]:
    token_sets = [_tokens(str(a.get("headline") or a.get("title") or "")) for a in articles]
    if not token_sets:
        return []
    counts = Counter(token for tokens in token_sets for token in tokens)
    threshold = max(1, (len(token_sets) + 1) // 2)
    core = sorted(token for token, count in counts.items() if count >= threshold)
    if len(core) < 2:
        oldest = min(articles, key=lambda a: a.get("published_at") or a.get("observed_at") or "")
        core = sorted(_tokens(str(oldest.get("headline") or oldest.get("title") or "")))
    return core[:10]


def _independent_lineages(articles: list[dict[str, Any]]) -> tuple[int, int]:
    """Conservatively estimate independent origins; near-identical rewrites count once."""
    lineages: list[dict[str, Any]] = []
    for article in articles:
        source = str(article.get("source") or article.get("publisher") or "").strip()
        title = str(article.get("headline") or article.get("title") or "")
        primary = bool(article.get("official_source_available")) or str(article.get("source_type") or "").upper() == "PRIMARY"
        if primary:
            key = "primary:" + source.lower()
            if not any(row["key"] == key for row in lineages):
                lineages.append({"key": key, "title": title})
            continue
        matched = False
        for row in lineages:
            if not row["key"].startswith("primary:") and _headline_similarity(title, row["title"]) >= 0.90:
                matched = True
                break
        if not matched:
            lineages.append({"key": "secondary:" + (source.lower() or str(len(lineages))), "title": title})
    independent = len(lineages)
    return independent, max(0, len(articles) - independent)


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
    """Deduplicate, remove high-confidence promotion and cluster one real-world event.

    Raw article volume is never treated as independent confirmation. Official
    first-party material is preserved, while near-identical secondary rewrites
    are counted conservatively as one lineage.
    """
    enriched: list[dict[str, Any]] = []
    quality_filtered = 0
    for raw in items:
        item = dict(raw)
        quality = classify_content_quality(item)
        item.update(quality)
        if quality.get("filter_from_market_feed"):
            quality_filtered += 1
            continue
        enriched.append(item)

    candidates = sorted(enriched, key=lambda x: x.get("published_at") or "", reverse=True)
    by_title: dict[str, dict[str, Any]] = {}
    url_to_title: dict[str, str] = {}
    order: list[str] = []
    for item in candidates:
        key = re.sub(r"\W+", "", _normalized_headline(str(item.get("headline") or item.get("title", ""))))
        url = str(item.get("url", ""))
        if not key:
            continue
        existing_key = url_to_title.get(url) if url else None
        target_key = existing_key or key
        existing = by_title.get(target_key)
        if existing is None:
            by_title[target_key] = dict(item)
            order.append(target_key)
            if url:
                url_to_title[url] = target_key
            continue
        existing_primary = bool(existing.get("official_source_available")) or existing.get("source_type") == "PRIMARY"
        incoming_primary = bool(item.get("official_source_available")) or item.get("source_type") == "PRIMARY"
        if incoming_primary and not existing_primary:
            by_title[target_key] = dict(item)
        if url:
            url_to_title[url] = target_key
    unique = [by_title[key] for key in order if key in by_title]

    clusters: list[dict[str, Any]] = []
    for item in unique:
        title = str(item.get("headline") or item.get("title", ""))
        toks = _tokens(title)
        target = None
        best = 0.0
        for cluster in clusters:
            score = _cluster_match(toks, title, cluster)
            if score > best:
                best, target = score, cluster
        if target is not None and best > 0:
            target["articles"].append(item)
            target["_tokens"] |= toks
        else:
            clusters.append({"_tokens": set(toks), "articles": [item]})

    output: list[dict[str, Any]] = []
    for cluster in clusters:
        articles = cluster["articles"]
        # Prefer a primary source as the representative; otherwise use the newest.
        primary_articles = [
            a for a in articles
            if bool(a.get("official_source_available")) or str(a.get("source_type") or "").upper() == "PRIMARY"
        ]
        head = primary_articles[0] if primary_articles else articles[0]
        pubs = sorted({a.get("source") or a.get("publisher") for a in articles if a.get("source") or a.get("publisher")})
        independent_count, reprint_count = _independent_lineages(articles)
        core_tokens = _event_core_tokens(articles)
        fingerprint = _stable_id("|".join(core_tokens), prefix="ISSUE-FP-")
        issue_id = "GN-" + fingerprint.replace("ISSUE-FP-", "")
        latest_at = max((a.get("published_at") or a.get("observed_at") or "" for a in articles), default=None)
        first_at = min((a.get("published_at") or a.get("observed_at") or "" for a in articles), default=None)
        impact = classify_channels(str(head.get("headline") or head.get("title", "")))
        normalized_articles = []
        for article in articles[:20]:
            row = dict(article)
            row["cluster_id"] = issue_id
            normalized_articles.append(row)
        output.append({
            "issue_id": issue_id,
            "fingerprint": fingerprint,
            "event_core_tokens": core_tokens,
            "headline": head.get("headline") or head.get("title"),
            "first_seen_at": first_at,
            "latest_at": latest_at,
            "article_count": len(articles),
            "publisher_count": len(pubs),
            "independent_source_count": independent_count,
            "independent_publishers": independent_count,
            "reprint_count": reprint_count,
            "quality_filtered_count": quality_filtered,
            "publishers": pubs[:12],
            "official_source_available": any(bool(a.get("official_source_available")) for a in articles),
            "state": "NEW",
            "why_important": why_important(impact),
            "counterpoint": "기사 수와 동시 가격 움직임만으로 인과를 확정하지 않습니다. 재인용은 독립 근거로 중복 계산하지 않습니다.",
            "next_variables": list(dict.fromkeys((impact.get("related_markets") or []) + ["외국인 수급", "기관 수급"]))[:6],
            "history": [],
            **impact,
            "articles": normalized_articles,
        })
    output.sort(
        key=lambda x: (
            x.get("latest_at") or "",
            x.get("independent_source_count", 0),
            x.get("article_count", 0),
        ),
        reverse=True,
    )
    return unique, output
