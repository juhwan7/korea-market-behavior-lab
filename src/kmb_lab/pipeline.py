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


def collect_news(root: Path) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    all_items: list[dict[str, Any]] = []; errors: list[str] = []
    for query in google_news.DEFAULT_QUERIES:
        try:
            all_items.extend(google_news.parse_rss(google_news.fetch_rss(query), query=query))
        except Exception as exc:
            errors.append(f"google-news:{query}:{exc}")
    unique, issues = google_news.dedupe_and_cluster(all_items)
    previous = load_json(root / "data/news/issues.json", {})
    previous_issues = previous.get("issues", []) if isinstance(previous, dict) else []
    prior_map = {str(x.get("headline", "")).strip().lower(): x for x in previous_issues if isinstance(x, dict)}
    for issue in issues:
        prior = prior_map.get(str(issue.get("headline", "")).strip().lower())
        if prior:
            if issue.get("article_count", 0) > prior.get("article_count", 0): issue["state"] = "STRENGTHENING"
            else: issue["state"] = "PERSISTING"
    current = {"generated_at": now_text(), "count": len(unique), "items": unique[:120], "source_quality": "SECONDARY_AGGREGATOR"}
    issue_doc = {"generated_at": now_text(), "count": len(issues), "issues": issues[:40], "note": "호재/악재 방향읅 제목만으로 확정하지 않고 시장 반응·공식자료 확인 전에는 UNDETERMINED로 유지합니다."}
    return current, issue_doc, errors


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
    news_current, news_issues, e = collect_news(root); errors += e
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
    write_json(root / "data/stocks/smart-money.json", smart_money)
    write_json(root / "data/ai/development-mix.json", git_development_mix(24))

    status = {
        "generated_at": now_text(),
        "status": "HEALTHY" if not errors else "PARTIAL",
        "product_features": {
            "domestic_indices": bool(indices), "investor_flow": bool((flow_analysis.get("markets") or {})),
            "breadth": bool(breadth), "kospi200_futures": (futures.get("KOSPI200_FUTURES") or {}).get("status"),
            "global_futures": bool(global_data.get("quotes")), "news": news_current.get("count", 0),
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
