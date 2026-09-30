from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any

from .adapters import google_news, krx, naver_market, yahoo_global
from .adapters.treasury import fetch_yield_curve, observation_for_maturity
from .development_mix import git_development_mix
from .flow import analyze_flow_history
from .market_strength import market_strength
from .smart_money import analyze_smart_money

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))


def now_text() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def upsert_unresolved(problem: dict[str, Any], *, root: Path = ROOT) -> None:
    path = root / "data/ai/unresolved-problems.jsonl"
    rows = load_jsonl(path)
    pid = problem["id"]
    existing = next((row for row in rows if row.get("id") == pid), None)
    stamp = now_text()
    if existing:
        first = existing.get("first_seen_at") or stamp
        attempts = list(existing.get("attempted_solutions") or [])
        for attempt in problem.get("attempted_solutions") or []:
            if attempt not in attempts:
                attempts.append(attempt)
        existing.update(problem)
        existing["first_seen_at"] = first
        existing["last_attempt_at"] = stamp
        existing["attempted_solutions"] = attempts[-20:]
    else:
        problem = dict(problem)
        problem.setdefault("first_seen_at", stamp)
        problem.setdefault("last_attempt_at", stamp)
        rows.append(problem)
    write_jsonl(path, rows)


def resolve_unresolved(problem_id: str, *, root: Path = ROOT, note: str = "automatically resolved") -> None:
    path = root / "data/ai/unresolved-problems.jsonl"
    rows = load_jsonl(path)
    changed = False
    for row in rows:
        if row.get("id") == problem_id and row.get("status") != "RESOLVED":
            row["status"] = "RESOLVED"
            row["resolved_at"] = now_text()
            row["resolution"] = note
            changed = True
    if changed:
        write_jsonl(path, rows)


def _program_net(program: Any) -> float | None:
    preferred = ("netBuyValue", "netValue", "programNetValue", "allNetValue", "totalNetValue", "totalValue")
    def walk(value: Any) -> float | None:
        if isinstance(value, dict):
            for key in preferred:
                raw = value.get(key)
                if raw not in (None, "", "-"):
                    try:
                        return float(str(raw).replace(",", ""))
                    except ValueError:
                        pass
            for child in value.values():
                found = walk(child)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in reversed(value):
                found = walk(child)
                if found is not None:
                    return found
        return None
    return walk(program)


def collect_domestic(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    errors: list[str] = []
    indices: dict[str, Any] = {}
    secondary_summary: dict[str, Any] = {"indices": {}, "program": None}
    for code in ("KOSPI", "KOSDAQ", "KPI200"):
        try:
            indices[code] = naver_market.normalize_index_basic(naver_market.fetch_index_basic(code), code)
        except Exception as exc:
            errors.append(f"naver-index-{code}:{exc}")
    try:
        secondary_summary = naver_market.normalize_main_summary(naver_market.fetch_main_summary())
    except Exception as exc:
        errors.append(f"naver-main-summary:{exc}")

    markets = {}
    breadth = {}
    for code in ("KOSPI", "KOSDAQ"):
        row = (secondary_summary.get("indices") or {}).get(code) or {}
        markets[code] = {"flows_100m_krw": row.get("flows_100m_krw") or {}, "source_kind": "secondary", "as_of": row.get("as_of")}
        breadth[code] = row.get("breadth") or {}

    auth_key = os.environ.get("KRX_AUTH_KEY")
    official: dict[str, Any] = {}
    if auth_key:
        try:
            official = krx.fetch_equity_market(auth_key=auth_key)
            for code in ("KOSPI", "KOSDAQ"):
                if official.get(code):
                    breadth[code] = official[code].get("breadth") or breadth.get(code) or {}
            resolve_unresolved("DATA-KRX-AUTH-KEY", root=root, note="KRX_AUTH_KEY available to collector")
        except Exception as exc:
            errors.append(f"krx-equity:{exc}")
            upsert_unresolved({
                "id": "DATA-KRX-RUNTIME", "owner": "AI-D", "problem": "KRX Open API request failed despite configured key",
                "root_cause": str(exc), "attempted_solutions": ["official KRX adapter request with configured AUTH_KEY"],
                "why_failed": str(exc), "required_external_action": None, "retry_condition": "next scheduled collector run",
                "do_not_repeat": "Do not mark KRX primary data CONNECTED until a successful response is persisted.",
                "related_files": ["src/kmb_lab/adapters/krx.py", "data/sources/registry.json"], "related_commits": [], "status": "OPEN",
            }, root=root)
    else:
        upsert_unresolved({
            "id": "DATA-KRX-AUTH-KEY", "owner": "USER", "problem": "KRX Open API primary data is not authenticated",
            "root_cause": "KRX Open API requires an AUTH_KEY and API use approval; no KRX_AUTH_KEY secret is available to the collector.",
            "attempted_solutions": ["implemented optional KRX adapter", "kept secondary public market feed as non-primary fallback"],
            "why_failed": "credential/application approval cannot be created by repository code",
            "required_external_action": "Apply for KRX Open API access and add repository secret KRX_AUTH_KEY.",
            "retry_condition": "KRX_AUTH_KEY becomes available", "do_not_repeat": "Do not repeatedly investigate public unauthenticated KRX endpoints as if they were authenticated Open API.",
            "related_files": ["src/kmb_lab/adapters/krx.py", ".github/workflows/market-fast-lane.yml"], "related_commits": [], "status": "USER_ACTION_REQUIRED",
        }, root=root)

    snapshot = {"at": now_text(), "markets": markets, "source": "naver-finance-public"}
    history_path = root / "data/market/flow-history.json"
    history = load_json(history_path, [])
    if not isinstance(history, list): history = []
    history.append(snapshot)
    cutoff = datetime.now(KST) - timedelta(days=3)
    trimmed = []
    for row in history[-400:]:
        try: dt = datetime.fromisoformat(str(row.get("at")).replace("Z", "+00:00")).astimezone(KST)
        except Exception: continue
        if dt >= cutoff: trimmed.append(row)
    write_json(history_path, trimmed)
    flow_analysis = analyze_flow_history(trimmed)
    flow_analysis.update({"as_of": snapshot["at"], "markets_raw": markets, "source_quality": "SECONDARY_UNLESS_KRX_PRIMARY_FIELDS_PRESENT"})
    program_net = _program_net(secondary_summary.get("program"))
    program = {"net_100m_krw": program_net, "raw_available": secondary_summary.get("program") is not None, "source_id": naver_market.SOURCE_ID, "source_kind": naver_market.SOURCE_KIND}
    return indices, breadth, {"flows": flow_analysis, "program": program, "official": official}, errors


def collect_futures(root: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    result: dict[str, Any] = {"KOSPI200_FUTURES": {"status": "NOT_CONNECTED"}}
    key = os.environ.get("KRX_AUTH_KEY")
    if key:
        try:
            result["KOSPI200_FUTURES"] = {"status": "CONNECTED_EOD_PRIMARY", **krx.fetch_kospi200_futures(auth_key=key)}
        except Exception as exc:
            errors.append(f"krx-kospi200-futures:{exc}")
    else:
        result["KOSPI200_FUTURES"] = {
            "status": "USER_ACTION_REQUIRED", "reason": "KRX_AUTH_KEY required for authoritative KOSPI200 futures feed",
            "source_kind": "primary_required",
        }
    return result, errors


def collect_global() -> tuple[dict[str, Any], list[str]]:
    board = yahoo_global.fetch_global_board()
    errors = [f"yahoo-{k}:{v}" for k, v in (board.get("errors") or {}).items()]
    yields: dict[str, Any] = {}
    try:
        rows = fetch_yield_curve(datetime.now(timezone.utc).year)
        if rows:
            latest = rows[-1]
            for maturity in ("2YEAR", "10YEAR", "2-YEAR", "10-YEAR"):
                if maturity in (latest.get("yields") or {}):
                    yields[maturity] = observation_for_maturity(latest, maturity)
    except Exception as exc:
        errors.append(f"treasury:{exc}")
    return {"quotes": board.get("quotes") or {}, "treasury": yields, "as_of": now_text(), "interpretation": global_interpretation(board.get("quotes") or {}, yields)}, errors


def global_interpretation(quotes: dict[str, Any], yields: dict[str, Any]) -> dict[str, Any]:
    nq = (quotes.get("NASDAQ100_FUTURES") or {}).get("change_pct")
    fx = (quotes.get("USD_KRW") or {}).get("change_pct")
    vix = (quotes.get("VIX") or {}).get("change_pct")
    signals = []
    if isinstance(nq, (int, float)):
        signals.append({"factor": "NASDAQ100_FUTURES", "direction": "supportive" if nq > .25 else "risk" if nq < -.25 else "neutral", "value": nq})
    if isinstance(fx, (int, float)):
        signals.append({"factor": "USD_KRW", "direction": "supportive" if fx < -.25 else "risk" if fx > .25 else "neutral", "value": fx})
    if isinstance(vix, (int, float)):
        signals.append({"factor": "VIX", "direction": "risk" if vix > 3 else "supportive" if vix < -3 else "neutral", "value": vix})
    support = sum(s["direction"] == "supportive" for s in signals); risk = sum(s["direction"] == "risk" for s in signals)
    label = "MIXED"
    if support >= 2 and risk == 0: label = "SUPPORTIVE_ENVIRONMENT"
    elif risk >= 2 and support == 0: label = "RISK_ENVIRONMENT"
    return {"evidence_state": "HYPOTHESIS", "label": label, "signals": signals, "note": "글로벌 지표 조합읅 한국시장 방향 예측이 아니라 환경 설명용이며 국내 수급·시장폭과 함께 봅니다."}


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_recent_news_item(item: dict[str, Any], *, now: datetime | None = None, hours: int = 36) -> bool:
    now = now or datetime.now(timezone.utc)
    published = _parse_dt(item.get("published_at"))
    if published is None:
        observed = _parse_dt(item.get("observed_at") or item.get("retrieved_at"))
        return observed is not None and now - observed <= timedelta(hours=hours)
    age = now - published
    return timedelta(minutes=-5) <= age <= timedelta(hours=hours)


def _issue_importance(issue: dict[str, Any], *, now: datetime) -> tuple[float, dict[str, Any]]:
    publishers = min(5, int(issue.get("independent_publishers") or 0))
    articles = min(8, int(issue.get("article_count") or 0))
    channels = min(4, len(issue.get("impact_channels") or []))
    official = 1 if issue.get("official_source_available") else 0
    latest = _parse_dt(issue.get("latest_at"))
    recency = 0
    if latest is not None:
        age = now - latest
        if age <= timedelta(hours=2):
            recency = 8
        elif age <= timedelta(hours=8):
            recency = 5
        elif age <= timedelta(hours=24):
            recency = 2
    score = publishers * 4 + articles * 1.5 + channels * 2 + official * 10 + recency
    return score, {
        "independent_source_component": publishers,
        "article_component": articles,
        "channel_component": channels,
        "official_source_component": official,
        "recency_component": recency,
        "market_reaction_component": "PENDING",
    }


def _merge_issue_history(current_issues: list[dict[str, Any]], previous_issues: list[dict[str, Any]], *, observed_at: str, collection_succeeded: bool) -> list[dict[str, Any]]:
    prior_map = {}
    for row in previous_issues:
        if not isinstance(row, dict):
            continue
        key = row.get("fingerprint") or row.get("issue_id") or str(row.get("headline", "")).strip().lower()
        prior_map[str(key)] = row

    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for issue in current_issues:
        key = str(issue.get("fingerprint") or issue.get("issue_id") or str(issue.get("headline", "")).strip().lower())
        seen.add(key)
        prior = prior_map.get(key)
        if prior:
            article_growth = int(issue.get("article_count") or 0) - int(prior.get("article_count") or 0)
            publisher_growth = int(issue.get("independent_publishers") or 0) - int(prior.get("independent_publishers") or 0)
            issue["state"] = "STRENGTHENING" if article_growth > 0 or publisher_growth > 0 else "PERSISTING"
            issue["first_seen_at"] = prior.get("first_seen_at") or issue.get("first_seen_at")
            history = list(prior.get("history") or [])
            issue["ai_analysis"] = dict(prior.get("ai_analysis") or {})
        else:
            issue["state"] = "NEW"
            history = []
            issue["ai_analysis"] = {}
        issue["last_updated_at"] = observed_at
        if not history or history[-1].get("state") != issue["state"]:
            history.append({
                "at": observed_at,
                "state": issue["state"],
                "reason": "독립 출처/기사 수와 현재 수집 결과를 직전 관측과 비교한 상태 변화입니다.",
            })
        issue["history"] = history[-20:]
        merged.append(issue)

    if collection_succeeded:
        now = _parse_dt(observed_at) or datetime.now(timezone.utc)
        for key, prior in prior_map.items():
            if key in seen:
                continue
            latest = _parse_dt(prior.get("latest_at") or prior.get("last_updated_at") or prior.get("first_seen_at"))
            if latest is None:
                continue
            age = now - latest
            if age > timedelta(hours=24):
                continue
            row = dict(prior)
            new_state = "WEAKENING" if age <= timedelta(hours=6) else "RESOLVED"
            if str(row.get("state")) != new_state:
                history = list(row.get("history") or [])
                history.append({
                    "at": observed_at,
                    "state": new_state,
                    "reason": "현재 수집 창에서 새 독립 근거가 추가되지 않아 상태를 낮췄습니다. 사건 자체의 소멸을 단정하는 의미는 아닙니다.",
                })
                row["history"] = history[-20:]
            row["state"] = new_state
            row["last_updated_at"] = observed_at
            merged.append(row)

    rank = {"STRENGTHENING": 5, "NEW": 4, "PERSISTING": 3, "WEAKENING": 2, "RESOLVED": 1}
    for row in merged:
        score, components = _issue_importance(row, now=_parse_dt(observed_at) or datetime.now(timezone.utc))
        row["importance_score"] = round(score, 2)
        row["importance_components"] = components
    merged.sort(
        key=lambda x: (
            rank.get(str(x.get("state")), 0),
            float(x.get("importance_score") or 0),
            x.get("latest_at") or "",
        ),
        reverse=True,
    )
    return merged


def collect_news(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    all_items: list[dict[str, Any]] = []
    errors: list[str] = []
    checked = list(google_news.DEFAULT_QUERIES)
    succeeded = 0
    for query in checked:
        try:
            rows = google_news.parse_rss(google_news.fetch_rss(query), query=query)
            all_items.extend([row for row in rows if _is_recent_news_item(row)])
            succeeded += 1
        except Exception as exc:
            errors.append(f"google-news:{query}:{exc}")

    unique, clustered = google_news.dedupe_and_cluster(all_items)
    observed_at = now_text()
    previous = load_json(root / "data/news/issues.json", {})
    previous_issues = previous.get("issues", []) if isinstance(previous, dict) else []
    issues = _merge_issue_history(
        clustered,
        previous_issues if isinstance(previous_issues, list) else [],
        observed_at=observed_at,
        collection_succeeded=succeeded > 0,
    )

    latest_news_at = max(
        (str(x.get("published_at") or x.get("observed_at") or "") for x in unique),
        default=None,
    ) or None
    collection_status = "HEALTHY" if succeeded == len(checked) else "PARTIAL" if succeeded > 0 else "FAILED"
    current = {
        "generated_at": observed_at,
        "collection_attempted_at": observed_at,
        "collection_status": collection_status,
        "sources_checked": len(checked),
        "queries_succeeded": succeeded,
        "queries_failed": len(checked) - succeeded,
        "raw_count": len(all_items),
        "deduplicated_count": len(unique),
        "count": len(unique),
        "latest_news_at": latest_news_at,
        "items": unique[:160],
        "source_quality": "SECONDARY_AGGREGATOR",
        "note": "기사 발견용 보조 소스입니다. 공식자료가 있는 사안은 1차 자료 확인 전 CONFIRMED로 승격하지 않습니다.",
    }
    issue_doc = {
        "generated_at": observed_at,
        "collection_status": collection_status,
        "count": len(issues),
        "issues": issues[:80],
        "note": "호재/악재 방향을 제목만으로 확정하지 않고 시장 반응·공식자료 확인 전에는 UNDETERMINED로 유지합니다.",
    }
    digest = {
        "generated_at": observed_at,
        "latest_news_at": latest_news_at,
        "latest_issue_at": max((str(x.get("last_updated_at") or x.get("latest_at") or "") for x in issues), default=None) or None,
        "collection_status": collection_status,
        "sources_checked": len(checked),
        "queries_succeeded": succeeded,
        "raw_news_count": len(all_items),
        "deduplicated_count": len(unique),
        "top_issues": issues[:10],
        "strengthening": [x for x in issues if x.get("state") == "STRENGTHENING"][:10],
        "weakening": [x for x in issues if x.get("state") == "WEAKENING"][:10],
        "resolved": [x for x in issues if x.get("state") == "RESOLVED"][:10],
    }

    if succeeded == 0:
        upsert_unresolved({
            "id": "NEWS-COLLECTION-FAILURE",
            "owner": "AI-D",
            "problem": "All configured market-news discovery queries failed in the latest collector run.",
            "root_cause": "See collector-status errors for per-query failures.",
            "attempted_solutions": ["Google News RSS discovery across configured fallback queries"],
            "why_failed": "No configured query returned a usable response in this run.",
            "required_external_action": None,
            "retry_condition": "next scheduled market-fast-lane run",
            "do_not_repeat": "Do not disable unrelated agents or market collectors for this LOCAL news-source failure.",
            "related_files": ["src/kmb_lab/adapters/google_news.py", "src/kmb_lab/pipeline.py"],
            "related_commits": [],
            "status": "OPEN",
        }, root=root)
    else:
        resolve_unresolved("NEWS-COLLECTION-FAILURE", root=root, note="At least one configured news query succeeded.")

    return current, issue_doc, digest, errors


def collect_smart_money(root: Path) -> tuple[dict[str, Any], list[str]]:
    config = load_json(root / "data/config/watchlist.json", {})
    items = config.get("items", []) if isinstance(config, dict) else []
    output: list[dict[str, Any]] = []; errors: list[str] = []
    for item in items[:30]:
        code = str(item.get("code") or "")
        if not code: continue
        try:
            bars = naver_market.fetch_stock_daily(code, page_size=80)
            analysis = analyze_smart_money(bars)
            output.append({"code": code, "name": item.get("name") or code, "as_of": bars[-1].get("date") if bars else None, "source_id": naver_market.SOURCE_ID, "source_kind": "secondary", **analysis})
        except Exception as exc:
            errors.append(f"smart-money-{code}:{exc}")
            output.append({"code": code, "name": item.get("name") or code, "evidence_state": "UNKNOWN", "reason": str(exc)})
    return {"generated_at": now_text(), "production_eligible": False, "model_status": "SHADOW", "items": output, "warning": "특정 실존 계좌의 보유량·평단·의도를 의미하지 않는 공개데이터 기반 가상 프록시입니다."}, errors


def build_summary(indices: dict[str, Any], breadth: dict[str, Any], flows: dict[str, Any], program: dict[str, Any], strength: dict[str, Any], news: dict[str, Any], official: dict[str, Any]) -> dict[str, Any]:
    def idx(code: str) -> str:
        row = indices.get(code) or {}
        if row.get("close") is None: return "UNKNOWN"
        pct = row.get("change_pct")
        return f"{row['close']:,.2f}" + (f" ({pct:+.2f}%)" if isinstance(pct, (int, float)) else "")
    foreign = ((((flows.get("markets") or {}).get("KOSPI") or {}).get("foreign") or {}).get("net_100m_krw"))
    themes = [i.get("related_sectors", []) for i in news.get("issues", [])[:8]]
    flat_themes = []
    for group in themes:
        for t in group:
            if t not in flat_themes: flat_themes.append(t)
    confirmed = []
    if official:
        for code, row in official.items():
            confirmed.append(f"KRX {code} {row.get('as_of')} 시장폭/거래대금 공식 일별자료 연결")
    hypotheses = [x.get("explanation") for x in strength.get("index_illusion", [])[:3]]
    unknown = []
    if not official: unknown.append("KRX 1차 시장 데이터는 인증키가 없어 미연결")
    return {
        "as_of": now_text(), "kospi": idx("KOSPI"), "kosdaq": idx("KOSDAQ"),
        "turnover": "KRX 공식값" if official else "실시간 공식 거래대금 미연결",
        "movers": strength.get("index_illusion") or "특이 지수 착시 없음",
        "relative_strength": f"시장체력 {strength.get('composite')}" if strength.get("composite") is not None else "UNKNOWN",
        "themes": flat_themes[:5] or "UNKNOWN", "leaders": "관심종목 분석 화면 참조",
        "news": [x.get("headline") for x in news.get("issues", [])[:3]],
        "behavior_events": strength.get("index_illusion") or [],
        "confirmed": confirmed or "공식 1차 시장자료 미연결",
        "hypotheses": hypotheses or "추가 확인 중",
        "unknown": unknown or [],
        "foreign_flow_100m_krw": foreign,
        "program_net_100m_krw": program.get("net_100m_krw"),
        "source_quality": "MIXED_PRIMARY_SECONDARY" if official else "SECONDARY_WITH_EXPLICIT_LIMITS",
    }


def run(root: Path = ROOT) -> dict[str, Any]:
    (root / "data/market").mkdir(parents=True, exist_ok=True)
    (root / "data/news").mkdir(parents=True, exist_ok=True)
    (root / "data/stocks").mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    indices, breadth, domestic, e = collect_domestic(root); errors += e
    futures, e = collect_futures(root); errors += e
    global_data, e = collect_global(); errors += e
    news_current, news_issues, news_digest, e = collect_news(root); errors += e
    smart_money, e = collect_smart_money(root); errors += e

    flow_analysis = domestic["flows"]; program = domestic["program"]
    strength = market_strength(indices=indices, breadth=breadth, flows=flow_analysis, program_net_100m_krw=program.get("net_100m_krw"))
    strength["as_of"] = now_text()
    strength["breadth"] = breadth

    current = {"generated_at": now_text(), "indices": indices, "breadth": breadth, "program": program, "source_quality": "MIXED"}
    summary = build_summary(indices, breadth, flow_analysis, program, strength, news_issues, domestic.get("official") or {})

    write_json(root / "data/market/current.json", current)
    write_json(root / "data/market/summary.json", summary)
    write_json(root / "data/market/flows.json", flow_analysis)
    write_json(root / "data/market/breadth.json", {"generated_at": now_text(), "markets": breadth})
    write_json(root / "data/market/futures.json", {"generated_at": now_text(), **futures})
    write_json(root / "data/market/global.json", global_data)
    write_json(root / "data/market/strength.json", strength)
    write_json(root / "data/news/current.json", news_current)
    write_json(root / "data/news/issues.json", news_issues)
    write_json(root / "data/news/issue-digest.json", news_digest)
    write_json(root / "data/stocks/smart-money.json", smart_money)
    write_json(root / "data/ai/development-mix.json", git_development_mix(24))

    status = {
        "generated_at": now_text(),
        "status": "HEALTHY" if not errors else "PARTIAL",
        "product_features": {
            "domestic_indices": bool(indices), "investor_flow": bool((flow_analysis.get("markets") or {})),
            "breadth": bool(breadth), "kospi200_futures": (futures.get("KOSPI200_FUTURES") or {}).get("status"),
            "global_futures": bool(global_data.get("quotes")), "news": news_current.get("count", 0),
            "news_collection": news_current.get("collection_status"), "news_latest_at": news_current.get("latest_news_at"),
            "market_strength": strength.get("evidence_state"), "smart_money": smart_money.get("model_status"),
        },
        "errors": errors[-40:],
    }
    write_json(root / "data/system/collector-status.json", status)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect and analyze KMB market intelligence")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    status = run(Path(args.root))
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
