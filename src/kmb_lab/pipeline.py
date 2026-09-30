from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any

from .adapters import bok_ecos, dart, google_news, krx, naver_market, official_news, yahoo_global
from .adapters.treasury import fetch_yield_curve, observation_for_maturity
from .development_mix import git_development_mix
from .flow import analyze_flow_history
from .market_strength import market_strength
from .relative_strength import relative_strength
from .smart_money import analyze_smart_money, backtest_smart_money

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


def _has_flow_values(flow_analysis: dict[str, Any]) -> bool:
    for market in ("KOSPI", "KOSDAQ"):
        investors = ((flow_analysis.get("markets") or {}).get(market) or {})
        for investor in ("individual", "foreign", "institution"):
            value = ((investors.get(investor) or {}).get("net_100m_krw"))
            if isinstance(value, (int, float)):
                return True
    return False


def _has_breadth_values(breadth: dict[str, Any]) -> bool:
    for market in ("KOSPI", "KOSDAQ"):
        row = breadth.get(market) or {}
        total = sum(
            int(row.get(key) or 0)
            for key in ("upper", "advance", "flat", "decline", "lower")
        )
        if total > 0:
            return True
    return False


def _sync_service_status(
    root: Path,
    *,
    news: dict[str, Any],
    indices: dict[str, Any],
    breadth: dict[str, Any],
    flows: dict[str, Any],
    global_data: dict[str, Any],
    official: dict[str, Any],
    turnover: dict[str, Any],
) -> None:
    path = root / "data/system/services.json"
    payload = load_json(path, {"schema_version": 2, "services": []})
    if not isinstance(payload, dict):
        payload = {"schema_version": 2, "services": []}
    services = payload.get("services")
    if not isinstance(services, list):
        services = []

    stamp = now_text()
    by_id = {str(row.get("id")): row for row in services if isinstance(row, dict)}

    news_row = by_id.get("news-fast-lane")
    if news_row is not None:
        collection = str(news.get("collection_status") or "UNKNOWN")
        news_row["monitoring_mode"] = "SCHEDULED"
        news_row["last_attempt_at"] = stamp
        if int(news.get("count") or 0) > 0 and collection in {"HEALTHY", "PARTIAL"}:
            news_row["status"] = "HEALTHY" if collection == "HEALTHY" else "PARTIAL"
            news_row["last_success_at"] = stamp
            news_row["note"] = (
                "Scheduled Google News RSS discovery is producing normalized current news. "
                "It remains a secondary discovery feed; official-source verification is separate."
            )
        else:
            news_row["status"] = "FAILED" if collection == "FAILED" else "PARTIAL"
            news_row["note"] = "Scheduled news collection ran but no usable current items were produced."

    market_row = by_id.get("market-data")
    if market_row is not None:
        has_indices = any(
            isinstance((indices.get(code) or {}).get("close"), (int, float))
            for code in ("KOSPI", "KOSDAQ")
        )
        has_global = bool(global_data.get("quotes"))
        has_flow = _has_flow_values(flows)
        has_breadth = _has_breadth_values(breadth)
        has_turnover = (turnover.get("combined") or {}).get("evidence_state") == "ESTIMATED"
        market_row["monitoring_mode"] = "SCHEDULED"
        market_row["last_attempt_at"] = stamp
        if has_indices or has_global:
            market_row["last_success_at"] = stamp
            market_row["status"] = (
                "HEALTHY"
                if has_indices and has_global and has_flow and has_breadth and has_turnover and bool(official)
                else "PARTIAL"
            )
            missing = []
            if not official:
                missing.append("KRX primary")
            if not has_flow:
                missing.append("investor flow")
            if not has_breadth:
                missing.append("breadth")
            if not has_turnover:
                missing.append("turnover participation")
            market_row["note"] = (
                "Scheduled market collector is active."
                + (f" Remaining gaps: {', '.join(missing)}." if missing else " Core configured market axes are populated.")
            )
        else:
            market_row["status"] = "FAILED"
            market_row["note"] = "Scheduled market collector ran without usable domestic index or global quote output."

    payload["generated_at"] = stamp
    payload["services"] = services
    write_json(path, payload)


def _program_numeric_leaves(program: Any) -> dict[str, float]:
    leaves: dict[str, float] = {}

    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value[:20]):
                walk(child, f"{path}[{index}]")
        elif value not in (None, "", "-"):
            try:
                leaves[path] = float(str(value).replace(",", ""))
            except (TypeError, ValueError):
                return

    walk(program)
    return dict(list(leaves.items())[:80])


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



def collect_disclosures(root: Path) -> tuple[dict[str, Any], list[str]]:
    key = os.environ.get("DART_API_KEY")
    stamp = now_text()
    if not key:
        upsert_unresolved({
            "id": "DATA-DART-API-KEY", "owner": "USER",
            "problem": "OpenDART official disclosure feed is not authenticated",
            "root_cause": "OpenDART disclosure search requires a certification key; DART_API_KEY is not available to the workflow.",
            "attempted_solutions": ["implemented OpenDART list adapter and validation tests", "kept news fast lane independent from DART credentials"],
            "why_failed": "a user-issued API key cannot be created by repository code",
            "required_external_action": "Issue an OpenDART API key and add repository secret DART_API_KEY.",
            "retry_condition": "DART_API_KEY becomes available",
            "do_not_repeat": "Do not scrape DART pages as if they were the authenticated OpenDART API; keep secondary news running independently.",
            "related_files": ["src/kmb_lab/adapters/dart.py", ".github/workflows/market-fast-lane.yml"],
            "related_commits": [], "status": "USER_ACTION_REQUIRED",
        }, root=root)
        return {"generated_at": stamp, "status": "USER_ACTION_REQUIRED", "count": 0, "items": [],
                "source_id": dart.SOURCE_ID, "source_kind": dart.SOURCE_KIND,
                "reason": "DART_API_KEY is not configured"}, []
    today = datetime.now(KST).date()
    try:
        items = dart.fetch_disclosures(api_key=key, begin_date=today-timedelta(days=3), end_date=today, page_count=100)
        resolve_unresolved("DATA-DART-API-KEY", root=root, note="DART_API_KEY available and official disclosure request succeeded")
        resolve_unresolved("DATA-DART-RUNTIME", root=root, note="OpenDART request recovered")
        return {"generated_at": stamp, "status": "CONNECTED_PRIMARY", "count": len(items), "items": items,
                "source_id": dart.SOURCE_ID, "source_kind": dart.SOURCE_KIND, "source_url": dart.BASE}, []
    except Exception as exc:
        upsert_unresolved({
            "id": "DATA-DART-RUNTIME", "owner": "AI-D",
            "problem": "OpenDART official disclosure request failed with a configured key",
            "root_cause": str(exc), "attempted_solutions": ["official OpenDART list API request with configured DART_API_KEY"],
            "why_failed": str(exc), "required_external_action": None, "retry_condition": "next scheduled collector run",
            "do_not_repeat": "Do not mark DART CONNECTED_PRIMARY until a successful API response is persisted.",
            "related_files": ["src/kmb_lab/adapters/dart.py", "data/news/disclosures.json"],
            "related_commits": [], "status": "OPEN",
        }, root=root)
        return {"generated_at": stamp, "status": "FAILED", "count": 0, "items": [],
                "source_id": dart.SOURCE_ID, "source_kind": dart.SOURCE_KIND, "reason": str(exc)}, [f"dart:{exc}"]


def collect_bok_official(root: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        result = bok_ecos.fetch_daily_indicators(os.environ.get("ECOS_API_KEY"))
    except Exception as exc:
        upsert_unresolved({
            "id": "DATA-BOK-ECOS-RUNTIME", "owner": "AI-D",
            "problem": "Bank of Korea ECOS official ECOS StatisticSearch request failed",
            "root_cause": str(exc), "attempted_solutions": ["official ECOS StatisticSearch API with configured-or-sample credential"],
            "why_failed": str(exc), "required_external_action": None, "retry_condition": "next scheduled collector run",
            "do_not_repeat": "Do not replace a failed official read with fabricated values; retain the secondary market feed separately.",
            "related_files": ["src/kmb_lab/adapters/bok_ecos.py", "data/market/bok-official.json"],
            "related_commits": [], "status": "OPEN",
        }, root=root)
        return {"generated_at": now_text(), "status": "FAILED", "indicators": {},
                "source_id": bok_ecos.SOURCE_ID, "source_kind": bok_ecos.SOURCE_KIND, "reason": str(exc)}, [f"bok-ecos:{exc}"]
    if result.get("status") == "CONNECTED_PRIMARY":
        resolve_unresolved("DATA-BOK-ECOS-RUNTIME", root=root, note="official ECOS StatisticSearch indicators parsed successfully")
        resolve_unresolved("DATA-BOK-ECOS-PARSE", root=root, note="official ECOS StatisticSearch indicators parsed successfully")
        return result, []
    upsert_unresolved({
        "id": "DATA-BOK-ECOS-PARSE", "owner": "AI-A",
        "problem": "Bank of Korea ECOS API was reachable but configured indicator series produced no usable rows",
        "root_cause": "The configured ECOS series returned no usable numeric rows.",
        "attempted_solutions": ["ECOS StatisticSearch series for USD/KRW and Korean 3Y"],
        "why_failed": result.get("reason") or "no configured indicators were found in rendered HTML",
        "required_external_action": None, "retry_condition": "next scheduled run or ECOS series/API repair",
        "do_not_repeat": "Do not invent official values from secondary quotes; preserve ECOS API and secondary quote separation.",
        "related_files": ["src/kmb_lab/adapters/bok_ecos.py", "data/market/bok-official.json"],
        "related_commits": [], "status": "OPEN",
    }, root=root)
    return result, []


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
    raw_program = secondary_summary.get("program")
    program = naver_market.normalize_program(raw_program)
    return indices, breadth, {"flows": flow_analysis, "program": program, "official": official}, errors


def collect_turnover(root: Path) -> tuple[dict[str, Any], list[str]]:
    """Collect market-wide advancing/declining trading-value participation.

    During the Korean regular session the full public market-cap lists are
    paged. Outside the session the last valid snapshot is retained rather than
    spending requests on unchanged closed-market data.
    """
    errors: list[str] = []
    path = root / "data/market/turnover.json"
    now = datetime.now(KST)
    in_session = now.weekday() < 5 and (
        (now.hour > 9 or (now.hour == 9 and now.minute >= 0))
        and (now.hour < 15 or (now.hour == 15 and now.minute <= 40))
    )
    previous = load_json(path, {})
    if not in_session and isinstance(previous, dict) and (previous.get("markets") or {}):
        reused = dict(previous)
        reused["collection_status"] = "REUSED_CLOSED_MARKET"
        reused["last_checked_at"] = now_text()
        return reused, errors

    markets: dict[str, Any] = {}
    for market in ("KOSPI", "KOSDAQ"):
        try:
            rows = naver_market.fetch_market_universe(market)
            markets[market] = naver_market.normalize_turnover_participation(rows)
            markets[market]["size_participation"] = naver_market.normalize_size_participation(rows)
            markets[market]["top_trading_value_candidates"] = naver_market.top_turnover_candidates(
                rows, market, limit=6
            )
        except Exception as exc:
            errors.append(f"naver-turnover-{market}:{exc}")
            markets[market] = {"evidence_state": "UNKNOWN", "reason": str(exc)}

    valid = [row for row in markets.values() if row.get("evidence_state") == "ESTIMATED"]
    advance = sum(float(row.get("advance_trading_value_krw") or 0) for row in valid)
    decline = sum(float(row.get("decline_trading_value_krw") or 0) for row in valid)
    flat = sum(float(row.get("flat_trading_value_krw") or 0) for row in valid)
    total = sum(float(row.get("total_trading_value_krw") or 0) for row in valid)
    directional = advance + decline
    ratio = advance / decline if decline > 0 else (10.0 if advance > 0 else None)
    return {
        "generated_at": now_text(),
        "collection_status": "HEALTHY" if len(valid) == 2 else "PARTIAL" if valid else "FAILED",
        "markets": markets,
        "combined": {
            "evidence_state": "ESTIMATED" if valid else "UNKNOWN",
            "stock_count": sum(int(row.get("stock_count") or 0) for row in valid),
            "total_trading_value_krw": round(total, 0) if valid else None,
            "advance_trading_value_krw": round(advance, 0) if valid else None,
            "decline_trading_value_krw": round(decline, 0) if valid else None,
            "flat_trading_value_krw": round(flat, 0) if valid else None,
            "advance_directional_share": round(advance / directional, 4) if directional > 0 else None,
            "advance_decline_turnover_ratio": round(ratio, 4) if ratio is not None else None,
        },
        "source_id": naver_market.SOURCE_ID,
        "source_kind": naver_market.SOURCE_KIND,
        "method_note": "상승·하락 종목별 누적 거래대금을 전 종목 공개 목록에서 합산합니다. 공식 KRX 값과 동일하게 취급하지 않습니다.",
    }, errors



def collect_sector_breadth(root: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        result = naver_market.normalize_sector_dispersion(naver_market.fetch_sector_list())
        if result.get("evidence_state") == "ESTIMATED":
            resolve_unresolved("DATA-SECTOR-BREADTH", root=root, note="secondary sector dispersion feed recovered")
            return {"generated_at": now_text(), **result}, []
        raise RuntimeError(result.get("reason") or "sector list normalized without usable rows")
    except Exception as exc:
        upsert_unresolved({
            "id": "DATA-SECTOR-BREADTH", "owner": "AI-A",
            "problem": "Sector dispersion feed is unavailable or its public schema changed",
            "root_cause": str(exc), "attempted_solutions": ["Naver public domestic industry-index list with schema-tolerant normalization"],
            "why_failed": str(exc), "required_external_action": None, "retry_condition": "next scheduled collector run or endpoint schema repair",
            "do_not_repeat": "Do not fabricate sector breadth; keep the core market-strength axes running without this optional diagnostic.",
            "related_files": ["src/kmb_lab/adapters/naver_market.py", "data/market/sector-breadth.json"],
            "related_commits": [], "status": "OPEN",
        }, root=root)
        return {"generated_at": now_text(), "evidence_state": "UNKNOWN", "sectors": [], "reason": str(exc),
                "source_id": naver_market.SOURCE_ID, "source_kind": naver_market.SOURCE_KIND}, [f"sector-breadth:{exc}"]


def collect_futures(root: Path, indices: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    result: dict[str, Any] = {"KOSPI200_FUTURES": {"status": "NOT_CONNECTED"}}
    key = os.environ.get("KRX_AUTH_KEY")
    if key:
        try:
            primary = krx.fetch_kospi200_futures(auth_key=key)
            result["KOSPI200_FUTURES"] = {"status": "CONNECTED_EOD_PRIMARY", **primary}
            return result, errors
        except Exception as exc:
            errors.append(f"krx-kospi200-futures:{exc}")

    # Keep the user-facing futures screen useful even before KRX credentials
    # are available. This fallback is explicitly secondary and never promoted
    # to official/CONFIRMED KRX evidence.
    try:
        price_rows = naver_market.fetch_kospi200_futures_price(page_size=20)
        trend = naver_market.fetch_kospi200_futures_trend()
        secondary = naver_market.normalize_kospi200_futures(price_rows, trend)
        spot = ((indices or {}).get("KPI200") or {}).get("close")
        if isinstance(secondary.get("close"), (int, float)) and isinstance(spot, (int, float)):
            secondary["spot_kpi200"] = spot
            secondary["basis"] = round(float(secondary["close"]) - float(spot), 2)
            secondary["basis_pct"] = round((float(secondary["close"]) / float(spot) - 1.0) * 100.0, 3) if spot else None
        secondary["official_status"] = "KRX_AUTH_KEY_AVAILABLE" if key else "USER_ACTION_REQUIRED"
        secondary["official_reason"] = None if key else "KRX_AUTH_KEY required for authoritative KOSPI200 futures feed"
        result["KOSPI200_FUTURES"] = secondary
    except Exception as exc:
        errors.append(f"naver-kospi200-futures:{exc}")
        result["KOSPI200_FUTURES"] = {
            "status": "USER_ACTION_REQUIRED" if not key else "FAILED",
            "reason": "KRX official futures unavailable and secondary FUT fallback failed",
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
    return {"evidence_state": "HYPOTHESIS", "label": label, "signals": signals, "note": "글로벌 지표 조합은 한국시장 방향 예측이 아니라 환경 설명용이며 국내 수급·시장폭과 함께 봅니다."}



def futures_study(
    futures: dict[str, Any],
    indices: dict[str, Any],
    flows: dict[str, Any],
    program: dict[str, Any],
    global_data: dict[str, Any],
) -> dict[str, Any]:
    """Explain observable futures/spot/flow relationships without predicting direction."""
    k200 = futures.get("KOSPI200_FUTURES") or {}
    spot = indices.get("KPI200") or {}
    kospi_flow = ((flows.get("markets") or {}).get("KOSPI") or {}).get("foreign") or {}
    foreign_spot = kospi_flow.get("net_100m_krw")
    foreign_futures = (k200.get("investor_flow_100m_krw") or {}).get("foreign")
    program_net = program.get("net_100m_krw")
    observations: list[dict[str, Any]] = []

    fut_change = k200.get("change_pct")
    spot_change = spot.get("change_pct")
    if isinstance(fut_change, (int, float)) and isinstance(spot_change, (int, float)):
        gap = round(float(fut_change) - float(spot_change), 3)
        if gap > 0.15:
            state = "FUTURES_RELATIVELY_STRONG"
            explanation = "KOSPI200 선물의 등락률이 현물 KOSPI200보다 높습니다. 선물이 상대적으로 강하지만 이것만으로 현물 상승을 예측하지 않습니다."
        elif gap < -0.15:
            state = "FUTURES_RELATIVELY_WEAK"
            explanation = "KOSPI200 선물의 등락률이 현물 KOSPI200보다 낮습니다. 선물이 상대적으로 약하지만 이것만으로 현물 하락을 예측하지 않습니다."
        else:
            state = "FUTURES_SPOT_ALIGNED"
            explanation = "KOSPI200 선물과 현물의 당일 등락률 차이가 크지 않습니다."
        observations.append({
            "factor": "futures_vs_spot",
            "state": state,
            "value": gap,
            "unit": "percentage_point",
            "explanation": explanation,
        })

    basis_pct = k200.get("basis_pct")
    if isinstance(basis_pct, (int, float)):
        state = "POSITIVE_BASIS" if basis_pct > 0.05 else "NEGATIVE_BASIS" if basis_pct < -0.05 else "NEAR_FLAT_BASIS"
        explanation = (
            "선물이 현물보다 높은 콘탱고형 베이시스입니다. 배당·금리·잔존만기 영향을 받으므로 강세 신호로 단독 해석하지 않습니다."
            if state == "POSITIVE_BASIS"
            else "선물이 현물보다 낮은 백워데이션형 베이시스입니다. 헤지·수급·만기 요인을 함께 확인해야 합니다."
            if state == "NEGATIVE_BASIS"
            else "선물과 현물 가격 차이가 작은 구간입니다."
        )
        observations.append({
            "factor": "basis",
            "state": state,
            "value": round(float(basis_pct), 3),
            "unit": "percent",
            "explanation": explanation,
        })

    if isinstance(foreign_futures, (int, float)) and isinstance(foreign_spot, (int, float)):
        if foreign_futures > 0 and foreign_spot < 0:
            state = "FOREIGN_FUTURES_BUY_SPOT_SELL"
            explanation = "외국인이 선물은 순매수하지만 KOSPI 현물은 순매도 중입니다. 선물 매수만 보고 시장 전체 Risk-on으로 해석하면 안 되는 괴리입니다."
        elif foreign_futures < 0 and foreign_spot > 0:
            state = "FOREIGN_FUTURES_SELL_SPOT_BUY"
            explanation = "외국인이 현물은 순매수하지만 선물은 순매도 중입니다. 현물 매수와 지수 헤지가 함께 나타나는지 추가 확인이 필요합니다."
        elif foreign_futures > 0 and foreign_spot > 0:
            state = "FOREIGN_BUY_ALIGNED"
            explanation = "외국인 현물·선물 방향이 모두 순매수입니다. 다만 시장폭과 프로그램 수급이 동반되는지 함께 봐야 합니다."
        elif foreign_futures < 0 and foreign_spot < 0:
            state = "FOREIGN_SELL_ALIGNED"
            explanation = "외국인 현물·선물 방향이 모두 순매도입니다. 매도 압력이 시장폭과 거래대금으로 확산되는지 함께 확인해야 합니다."
        else:
            state = "FOREIGN_FLOW_MIXED"
            explanation = "외국인 현물·선물 방향성이 뚜렷하게 일치하지 않습니다."
        observations.append({
            "factor": "foreign_spot_futures",
            "state": state,
            "foreign_futures_100m_krw": float(foreign_futures),
            "foreign_spot_100m_krw": float(foreign_spot),
            "explanation": explanation,
        })

    if isinstance(program_net, (int, float)):
        state = "PROGRAM_NET_BUY" if program_net > 0 else "PROGRAM_NET_SELL" if program_net < 0 else "PROGRAM_FLAT"
        observations.append({
            "factor": "program",
            "state": state,
            "value_100m_krw": float(program_net),
            "explanation": (
                "프로그램 순매수가 현물 수급을 보조하고 있습니다. 차익·비차익 구성을 함께 확인합니다."
                if program_net > 0
                else "프로그램 순매도가 현물 수급에 부담을 주고 있습니다. 차익·비차익 구성을 함께 확인합니다."
                if program_net < 0
                else "프로그램 순매수·순매도 방향이 중립에 가깝습니다."
            ),
        })

    quotes = global_data.get("quotes") or {}
    nq = (quotes.get("NASDAQ100_FUTURES") or {}).get("change_pct")
    sox = (quotes.get("SOX") or {}).get("change_pct")
    if isinstance(nq, (int, float)) or isinstance(sox, (int, float)):
        observations.append({
            "factor": "us_tech_context",
            "state": "OBSERVED_CONTEXT",
            "nasdaq100_futures_change_pct": nq,
            "sox_change_pct": sox,
            "explanation": "Nasdaq100 선물은 현재 선행시장, SOX는 최근 미국 현물 세션의 반도체 환경을 보여주는 보조 관측치입니다. 서로 다른 시점의 지표를 같은 실시간 신호처럼 합치지 않습니다.",
        })

    return {
        "evidence_state": "OBSERVED" if observations else "UNKNOWN",
        "observations": observations,
        "method_note": "현물·선물·베이시스·외국인 수급·프로그램·미국 기술주 환경을 분리해 설명합니다. 관측 관계이지 향후 방향 예측이나 특정 주체의 의도 판정이 아닙니다.",
    }


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
    """Keep issue lifecycle identity stable even when a cluster headline drifts.

    Exact fingerprint remains the first key. If it changes because another
    article enters the cluster, a conservative semantic headline match can
    inherit the previous issue ID. This prevents repeated NEW resets without
    claiming that weakly similar stories are the same event.
    """
    prior_map: dict[str, dict[str, Any]] = {}
    prior_rows: list[tuple[str, dict[str, Any]]] = []
    for row in previous_issues:
        if not isinstance(row, dict):
            continue
        key = str(row.get("fingerprint") or row.get("issue_id") or str(row.get("headline", "")).strip().lower())
        prior_map[key] = row
        prior_rows.append((key, row))

    seen_prior: set[str] = set()
    merged: list[dict[str, Any]] = []
    for issue in current_issues:
        current_key = str(issue.get("fingerprint") or issue.get("issue_id") or str(issue.get("headline", "")).strip().lower())
        prior_key = current_key if current_key in prior_map and current_key not in seen_prior else None
        prior = prior_map.get(prior_key) if prior_key else None

        if prior is None:
            current_headline = str(issue.get("headline") or "")
            current_tokens = set(issue.get("event_core_tokens") or [])
            best: tuple[float, str, dict[str, Any]] | None = None
            for candidate_key, candidate in prior_rows:
                if candidate_key in seen_prior:
                    continue
                previous_headline = str(candidate.get("headline") or "")
                title_score = google_news._headline_similarity(current_headline, previous_headline)
                previous_tokens = set(candidate.get("event_core_tokens") or [])
                token_score = (
                    len(current_tokens & previous_tokens) / max(1, len(current_tokens | previous_tokens))
                    if current_tokens and previous_tokens else 0.0
                )
                score = max(title_score, token_score)
                # Require strong title continuity or a strong core-token overlap.
                if title_score >= 0.76 or token_score >= 0.60:
                    if best is None or score > best[0]:
                        best = (score, candidate_key, candidate)
            if best is not None:
                _, prior_key, prior = best
                issue["identity_match"] = "SEMANTIC_CONTINUITY"
                issue["generated_fingerprint"] = issue.get("fingerprint")
                if prior.get("issue_id"):
                    issue["issue_id"] = prior.get("issue_id")
                if prior.get("fingerprint"):
                    issue["fingerprint"] = prior.get("fingerprint")

        if prior is not None and prior_key is not None:
            seen_prior.add(prior_key)
            article_growth = int(issue.get("article_count") or 0) - int(prior.get("article_count") or 0)
            publisher_growth = int(issue.get("independent_source_count") or issue.get("independent_publishers") or 0) - int(prior.get("independent_source_count") or prior.get("independent_publishers") or 0)
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
        for key, prior in prior_rows:
            if key in seen_prior:
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

def _market_snapshot(
    *,
    indices: dict[str, Any],
    breadth: dict[str, Any],
    flows: dict[str, Any],
    program: dict[str, Any],
    futures: dict[str, Any],
    global_data: dict[str, Any],
    strength: dict[str, Any],
    turnover: dict[str, Any],
) -> dict[str, Any]:
    def foreign(market: str) -> float | None:
        value = ((((flows.get("markets") or {}).get(market) or {}).get("foreign") or {}).get("net_100m_krw"))
        return float(value) if isinstance(value, (int, float)) else None

    fut = futures.get("KOSPI200_FUTURES") or {}
    quotes = global_data.get("quotes") or {}
    return {
        "at": now_text(),
        "indices": {
            code: {
                "close": (indices.get(code) or {}).get("close"),
                "change_pct": (indices.get(code) or {}).get("change_pct"),
                "breadth": breadth.get(code) or {},
                "foreign_net_100m_krw": foreign(code) if code in {"KOSPI", "KOSDAQ"} else None,
            }
            for code in ("KOSPI", "KOSDAQ", "KPI200")
        },
        "program_net_100m_krw": program.get("net_100m_krw"),
        "futures": {
            "close": fut.get("close"),
            "change_pct": fut.get("change_pct"),
            "basis": fut.get("basis"),
            "foreign_net_100m_krw": (fut.get("investor_flow_100m_krw") or {}).get("foreign"),
            "source_kind": fut.get("source_kind"),
        },
        "global": {
            key: {
                "price": (quotes.get(key) or {}).get("price"),
                "change_pct": (quotes.get(key) or {}).get("change_pct"),
            }
            for key in ("NASDAQ100_FUTURES", "SP500_FUTURES", "SOX", "VIX", "USD_KRW", "WTI")
        },
        "market_strength": strength.get("composite"),
        "turnover_advance_share": ((turnover.get("combined") or {}).get("advance_directional_share")),
    }


def _append_market_snapshot(root: Path, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    path = root / "data/market/intraday-snapshots.json"
    payload = load_json(path, {"snapshots": []})
    rows = payload.get("snapshots", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    rows.append(snapshot)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    kept: list[dict[str, Any]] = []
    for row in rows[-1200:]:
        at = _parse_dt(row.get("at")) if isinstance(row, dict) else None
        if at is not None and at >= cutoff:
            kept.append(row)
    write_json(path, {
        "generated_at": now_text(),
        "retention_days": 7,
        "count": len(kept),
        "snapshots": kept,
    })
    return kept


def _pct_between(before: Any, after: Any) -> float | None:
    if not isinstance(before, (int, float)) or not isinstance(after, (int, float)) or float(before) == 0:
        return None
    return round((float(after) / float(before) - 1.0) * 100.0, 3)


def _enrich_issue_market_reactions(
    issue_doc: dict[str, Any],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    issues = issue_doc.get("issues") or []
    parsed = [(row, _parse_dt(row.get("at"))) for row in snapshots if isinstance(row, dict)]
    parsed = [(row, at) for row, at in parsed if at is not None]
    parsed.sort(key=lambda pair: pair[1])

    for issue in issues:
        event_at = _parse_dt(issue.get("first_seen_at") or issue.get("latest_at"))
        if event_at is None:
            issue["market_reaction"] = {"evidence_state": "UNKNOWN", "reason": "이슈 기준시각을 해석할 수 없습니다."}
            continue
        before_candidates = [(row, at) for row, at in parsed if at <= event_at and event_at - at <= timedelta(minutes=90)]
        after_candidates = [(row, at) for row, at in parsed if at >= event_at + timedelta(minutes=20) and at - event_at <= timedelta(hours=2)]
        if not before_candidates or not after_candidates:
            issue["market_reaction"] = {
                "evidence_state": "PENDING",
                "event_at": event_at.isoformat(),
                "reason": "이슈 전후 90분/2시간 범위의 10분 시장 스냅샷이 아직 충분하지 않습니다.",
            }
            continue
        before, before_at = before_candidates[-1]
        after, after_at = after_candidates[-1]

        axes: dict[str, Any] = {}
        for code in ("KOSPI", "KOSDAQ"):
            b = ((before.get("indices") or {}).get(code) or {})
            a = ((after.get("indices") or {}).get(code) or {})
            axes[code] = {
                "price_return_pct": _pct_between(b.get("close"), a.get("close")),
                "foreign_flow_change_100m_krw": (
                    round(float(a["foreign_net_100m_krw"]) - float(b["foreign_net_100m_krw"]), 2)
                    if isinstance(a.get("foreign_net_100m_krw"), (int, float))
                    and isinstance(b.get("foreign_net_100m_krw"), (int, float))
                    else None
                ),
            }
        bf = before.get("futures") or {}
        af = after.get("futures") or {}
        axes["KOSPI200_FUTURES"] = {
            "price_return_pct": _pct_between(bf.get("close"), af.get("close")),
            "basis_change": (
                round(float(af["basis"]) - float(bf["basis"]), 3)
                if isinstance(af.get("basis"), (int, float)) and isinstance(bf.get("basis"), (int, float))
                else None
            ),
            "foreign_flow_change_100m_krw": (
                round(float(af["foreign_net_100m_krw"]) - float(bf["foreign_net_100m_krw"]), 2)
                if isinstance(af.get("foreign_net_100m_krw"), (int, float))
                and isinstance(bf.get("foreign_net_100m_krw"), (int, float))
                else None
            ),
        }
        for key in ("NASDAQ100_FUTURES", "USD_KRW", "WTI", "VIX"):
            b = ((before.get("global") or {}).get(key) or {})
            a = ((after.get("global") or {}).get(key) or {})
            axes[key] = {"price_return_pct": _pct_between(b.get("price"), a.get("price"))}

        observed = sum(
            1 for values in axes.values()
            for value in values.values()
            if isinstance(value, (int, float))
        )
        issue["market_reaction"] = {
            "evidence_state": "OBSERVED" if observed else "UNKNOWN",
            "interpretation_state": "CORRELATION_ONLY",
            "event_at": event_at.isoformat(),
            "before_at": before_at.isoformat(),
            "after_at": after_at.isoformat(),
            "window_minutes": round((after_at - before_at).total_seconds() / 60.0, 1),
            "axes": axes,
            "note": "뉴스 시각 전후 시장 변화의 관측치이며 뉴스가 가격 변화를 일으켰다는 인과관계 증거가 아닙니다.",
        }
        components = issue.get("importance_components")
        if isinstance(components, dict):
            components["market_reaction_component"] = "OBSERVED" if observed else "UNKNOWN"
    return issue_doc


def _refresh_issue_digest_reactions(digest: dict[str, Any], issue_doc: dict[str, Any]) -> dict[str, Any]:
    issues = issue_doc.get("issues") or []
    by_id = {row.get("issue_id"): row for row in issues if isinstance(row, dict)}
    for key in ("top_issues", "strengthening", "weakening", "resolved"):
        updated = []
        for row in digest.get(key) or []:
            updated.append(by_id.get(row.get("issue_id"), row))
        digest[key] = updated
    return digest


def collect_news(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    all_items: list[dict[str, Any]] = []
    errors: list[str] = []

    checked = list(google_news.DEFAULT_QUERIES)
    succeeded = 0
    secondary_items = 0
    for query in checked:
        try:
            rows = google_news.parse_rss(google_news.fetch_rss(query), query=query)
            recent = [row for row in rows if _is_recent_news_item(row)]
            all_items.extend(recent)
            secondary_items += len(recent)
            succeeded += 1
        except Exception as exc:
            errors.append(f"google-news:{query}:{exc}")

    official_checked = len(official_news.OFFICIAL_FEEDS)
    official_succeeded = 0
    official_items = 0
    for feed in official_news.OFFICIAL_FEEDS:
        feed_id = str(feed.get("id") or "unknown")
        problem_id = "NEWS-OFFICIAL-" + feed_id.upper().replace("-", "_")
        try:
            rows = official_news.parse_feed(official_news.fetch_feed(feed), feed=feed)
            recent = [row for row in rows if _is_recent_news_item(row)]
            all_items.extend(recent)
            official_items += len(recent)
            official_succeeded += 1
            resolve_unresolved(problem_id, root=root, note=f"{feed_id} official feed recovered on scheduled collection")
        except Exception as exc:
            errors.append(f"official-news:{feed_id}:{exc}")
            upsert_unresolved({
                "id": problem_id,
                "owner": "AI-D",
                "problem": f"Official news feed {feed_id} failed while other news collection may remain available.",
                "root_cause": str(exc),
                "attempted_solutions": [
                    "use the institution-published official RSS endpoint",
                    "keep the failing official feed isolated from secondary/other official feeds",
                ],
                "why_failed": str(exc),
                "required_external_action": None,
                "retry_condition": "next scheduled market-fast-lane run",
                "do_not_repeat": "Do not replace the official feed with an unverified source or block the whole news fast lane; retry this source independently.",
                "related_files": ["src/kmb_lab/adapters/official_news.py", "src/kmb_lab/pipeline.py"],
                "related_commits": [],
                "status": "OPEN",
            }, root=root)

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
    total_success = succeeded + official_succeeded
    total_checked = len(checked) + official_checked
    collection_status = "HEALTHY" if total_success == total_checked else "PARTIAL" if total_success > 0 else "FAILED"
    current = {
        "generated_at": observed_at,
        "collection_attempted_at": observed_at,
        "collection_status": collection_status,
        "sources_checked": total_checked,
        "queries_succeeded": succeeded,
        "queries_failed": len(checked) - succeeded,
        "official_sources_checked": official_checked,
        "official_sources_succeeded": official_succeeded,
        "official_sources_failed": official_checked - official_succeeded,
        "official_items_count": official_items,
        "secondary_items_count": secondary_items,
        "raw_count": len(all_items),
        "deduplicated_count": len(unique),
        "count": len(unique),
        "latest_news_at": latest_news_at,
        "items": unique[:160],
        "source_quality": "MIXED_PRIMARY_SECONDARY" if official_items else "SECONDARY_AGGREGATOR",
        "note": "한국은행·금융위원회 공식 RSS는 PRIMARY로, Google News RSS는 SECONDARY discovery로 구분합니다. 동일 제목 중복 시 공식자료를 우선 보존합니다.",
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
        "sources_checked": total_checked,
        "queries_succeeded": succeeded,
        "official_sources_succeeded": official_succeeded,
        "official_items_count": official_items,
        "raw_news_count": len(all_items),
        "deduplicated_count": len(unique),
        "top_issues": issues[:10],
        "strengthening": [x for x in issues if x.get("state") == "STRENGTHENING"][:10],
        "weakening": [x for x in issues if x.get("state") == "WEAKENING"][:10],
        "resolved": [x for x in issues if x.get("state") == "RESOLVED"][:10],
    }

    if total_success == 0:
        upsert_unresolved({
            "id": "NEWS-COLLECTION-FAILURE",
            "owner": "AI-D",
            "problem": "All configured secondary discovery queries and official news feeds failed in the latest collector run.",
            "root_cause": "See collector-status errors for per-query failures.",
            "attempted_solutions": ["Google News RSS discovery", "Bank of Korea official RSS", "Financial Services Commission official RSS"],
            "why_failed": "No configured news source returned a usable response in this run.",
            "required_external_action": None,
            "retry_condition": "next scheduled market-fast-lane run",
            "do_not_repeat": "Do not disable unrelated agents or market collectors for this LOCAL news-source failure.",
            "related_files": ["src/kmb_lab/adapters/google_news.py", "src/kmb_lab/pipeline.py"],
            "related_commits": [],
            "status": "OPEN",
        }, root=root)
    else:
        resolve_unresolved("NEWS-COLLECTION-FAILURE", root=root, note="At least one configured official or secondary news source succeeded.")

    return current, issue_doc, digest, errors



def _model_validation_universe(root: Path, turnover: dict[str, Any] | None = None, *, limit: int = 16) -> list[dict[str, Any]]:
    """Combine explicit research symbols with liquid current-market validation samples."""
    config = load_json(root / "data/config/watchlist.json", {})
    configured = config.get("items", []) if isinstance(config, dict) else []
    output: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in configured:
        code = str(item.get("code") or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        output.append({
            **item,
            "code": code,
            "benchmark": str(item.get("benchmark") or "KOSPI").upper(),
            "selection_reason": item.get("selection_reason") or "configured_research_watchlist",
        })

    for market in ("KOSPI", "KOSDAQ"):
        row = ((turnover or {}).get("markets") or {}).get(market) or {}
        for item in row.get("top_trading_value_candidates") or []:
            code = str(item.get("code") or "").strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            output.append({
                "code": code,
                "name": item.get("name") or code,
                "benchmark": market,
                "selection_reason": "top_intraday_trading_value_validation_sample",
                "trading_value_krw": item.get("trading_value_krw"),
            })
            if len(output) >= limit:
                return output
    return output[:limit]


def collect_relative_strength(root: Path, turnover: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str]]:
    items = _model_validation_universe(root, turnover)
    errors: list[str] = []
    benchmark_cache: dict[str, list[dict[str, Any]]] = {}
    output: list[dict[str, Any]] = []

    for item in items[:30]:
        code = str(item.get("code") or "")
        if not code:
            continue
        benchmark = str(item.get("benchmark") or "KOSPI").upper()
        try:
            if benchmark not in benchmark_cache:
                benchmark_cache[benchmark] = naver_market.fetch_index_daily(benchmark, page_size=80)
            stock_rows = naver_market.fetch_stock_daily(code, page_size=80)
            analysis = relative_strength(stock_rows, benchmark_cache[benchmark])
            output.append({
                "code": code,
                "name": item.get("name") or code,
                "benchmark": benchmark,
                "source_id": naver_market.SOURCE_ID,
                "source_kind": naver_market.SOURCE_KIND,
                **analysis,
            })
        except Exception as exc:
            errors.append(f"relative-strength-{code}:{exc}")
            output.append({
                "code": code,
                "name": item.get("name") or code,
                "benchmark": benchmark,
                "evidence_state": "UNKNOWN",
                "reason": str(exc),
            })

    output.sort(
        key=lambda row: (
            isinstance(row.get("weighted_excess_return_pct"), (int, float)),
            float(row.get("weighted_excess_return_pct") or -9999),
        ),
        reverse=True,
    )
    return {
        "generated_at": now_text(),
        "items": output,
        "method_note": "관심종목과 지정 벤치마크의 같은 거래일 종가를 정렬해 1·3·5·20거래일 상대수익률을 계산합니다.",
    }, errors


def _aggregate_smart_backtests(items: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [item for item in items if (item.get("backtest") or {}).get("evidence_state") == "ESTIMATED"]
    total = sum(int((item.get("backtest") or {}).get("sample_count") or 0) for item in valid)
    if total <= 0:
        return {"evidence_state": "UNKNOWN", "sample_count": 0, "reason": "검증 가능한 방향성 상태 표본이 아직 없습니다."}

    def weighted(field: str) -> float | None:
        pairs = []
        for item in valid:
            bt = item.get("backtest") or {}
            n = int(bt.get("sample_count") or 0)
            value = (bt.get("overall") or {}).get(field)
            if n > 0 and isinstance(value, (int, float)):
                pairs.append((float(value), n))
        return round(sum(v*n for v,n in pairs) / sum(n for _,n in pairs), 4) if pairs else None

    return {
        "evidence_state": "ESTIMATED",
        "sample_count": total,
        "gross_success_rate": weighted("gross_success_rate"),
        "net_success_rate": weighted("net_success_rate"),
        "avg_gross_directional_return_pct": weighted("avg_gross_directional_return_pct"),
        "avg_net_after_cost_pct": weighted("avg_net_after_cost_pct"),
        "avg_mfe_pct": weighted("avg_mfe_pct"),
        "avg_mae_pct": weighted("avg_mae_pct"),
        "cost_assumption": {
            "evidence_state": "ASSUMPTION",
            "fees_bps": 15.0,
            "slippage_bps": 20.0,
            "round_trip_total_bps": 35.0,
        },
        "method_note": "관심종목별 walk-forward 방향성 검증을 표본수로 가중 집계합니다. 과거 검증률은 미래 확률이 아닙니다.",
    }


def _sync_smart_money_experiment(root: Path, aggregate: dict[str, Any]) -> None:
    path = root / "data/experiments/registry.json"
    registry = load_json(path, {"schema_version": 1, "champions": {}, "challengers": {}, "experiments": []})
    if not isinstance(registry, dict):
        registry = {"schema_version": 1, "champions": {}, "challengers": {}, "experiments": []}
    challengers = registry.setdefault("challengers", {})
    challengers["smart_money_behavior_v0"] = {
        "owner": "AI-C",
        "status": "SHADOW",
        "production_eligible": False,
        "implementation": "src/kmb_lab/smart_money.py",
        "purpose": "Validate accumulation/absorption, breakout-demand and distribution-risk state labels with walk-forward historical samples.",
        "sample_count": int(aggregate.get("sample_count") or 0),
        "performance": aggregate if aggregate.get("evidence_state") == "ESTIMATED" else None,
        "required_before_promotion": [
            "larger multi-regime historical sample",
            "primary-source market data where available",
            "out-of-sample stability",
            "fees/slippage sensitivity",
            "AI-B evidence audit",
        ],
    }
    experiments = registry.setdefault("experiments", [])
    exp = next((row for row in experiments if row.get("id") == "EXP-C-002"), None)
    payload = {
        "id": "EXP-C-002",
        "name": "Smart Money Behavior Walk-Forward v0",
        "owner": "AI-C",
        "status": "SHADOW",
        "sample_count": int(aggregate.get("sample_count") or 0),
        "performance": aggregate if aggregate.get("evidence_state") == "ESTIMATED" else None,
        "production_eligible": False,
        "failure_condition": "look-ahead leakage, fabricated probability, or promotion without out-of-sample/primary-source audit",
    }
    if exp is None:
        experiments.append(payload)
    else:
        exp.update(payload)
    registry["updated_at"] = now_text()
    write_json(path, registry)


def collect_smart_money(root: Path, turnover: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str]]:
    items = _model_validation_universe(root, turnover)
    output: list[dict[str, Any]] = []
    errors: list[str] = []
    benchmark_cache: dict[str, list[dict[str, Any]]] = {}

    for item in items[:30]:
        code = str(item.get("code") or "")
        if not code:
            continue
        benchmark = str(item.get("benchmark") or "KOSPI").upper()
        try:
            bars = naver_market.fetch_stock_daily(code, page_size=260)
            analysis = analyze_smart_money(bars)
            benchmark_rows: list[dict[str, Any]] | None = None
            try:
                if benchmark not in benchmark_cache:
                    benchmark_cache[benchmark] = naver_market.fetch_index_daily(benchmark, page_size=260)
                benchmark_rows = benchmark_cache[benchmark]
            except Exception as exc:
                errors.append(f"smart-money-benchmark-{benchmark}:{exc}")
            backtest = backtest_smart_money(bars, benchmark_rows=benchmark_rows)
            output.append({
                "code": code,
                "name": item.get("name") or code,
                "benchmark": benchmark,
                "as_of": bars[-1].get("date") if bars else None,
                "source_id": naver_market.SOURCE_ID,
                "source_kind": "secondary",
                **analysis,
                "validation": {
                    "evidence_state": backtest.get("evidence_state"),
                    "sample_count": backtest.get("sample_count"),
                    "overall": backtest.get("overall"),
                    "by_state": backtest.get("by_state"),
                    "by_regime": backtest.get("by_regime"),
                    "cost_assumption": backtest.get("cost_assumption"),
                    "method_note": backtest.get("method_note"),
                    "reason": backtest.get("reason"),
                },
                "backtest": backtest,
            })
        except Exception as exc:
            errors.append(f"smart-money-{code}:{exc}")
            output.append({"code": code, "name": item.get("name") or code, "evidence_state": "UNKNOWN", "reason": str(exc)})

    aggregate = _aggregate_smart_backtests(output)
    _sync_smart_money_experiment(root, aggregate)
    return {
        "generated_at": now_text(),
        "production_eligible": False,
        "model_status": "SHADOW",
        "validation": aggregate,
        "items": output,
        "warning": "특정 실존 계좌의 보유량·평단·의도를 의미하지 않는 공개데이터 기반 가상 프록시입니다.",
    }, errors


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
        "turnover": (
            "KRX 공식값"
            if official
            else (
                f"공개 보조 전종목 거래대금 {float(((strength.get('turnover_detail') or {}).get('combined') or {}).get('total_trading_value_krw'))/1e12:.2f}조원 · "
                f"상승 방향 비중 {float(((strength.get('turnover_detail') or {}).get('combined') or {}).get('advance_directional_share'))*100:.1f}%"
                if isinstance((((strength.get("turnover_detail") or {}).get("combined") or {}).get("total_trading_value_krw")), (int, float))
                and isinstance((((strength.get("turnover_detail") or {}).get("combined") or {}).get("advance_directional_share")), (int, float))
                else "거래대금 참여도 수집 중"
            )
        ),
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
    turnover, e = collect_turnover(root); errors += e
    sector_breadth, e = collect_sector_breadth(root); errors += e
    futures, e = collect_futures(root, indices); errors += e
    global_data, e = collect_global(); errors += e
    bok_official, e = collect_bok_official(root); errors += e
    global_data["bok_official"] = bok_official
    news_current, news_issues, news_digest, e = collect_news(root); errors += e
    disclosures, e = collect_disclosures(root); errors += e
    smart_money, e = collect_smart_money(root, turnover); errors += e
    relative_strength_data, e = collect_relative_strength(root, turnover); errors += e

    flow_analysis = domestic["flows"]; program = domestic["program"]
    futures["study"] = futures_study(futures, indices, flow_analysis, program, global_data)
    turnover_ratio = ((turnover.get("combined") or {}).get("advance_decline_turnover_ratio"))
    strength = market_strength(
        indices=indices,
        breadth=breadth,
        flows=flow_analysis,
        program_net_100m_krw=program.get("net_100m_krw"),
        turnover_ratio=turnover_ratio,
        sector_breadth=sector_breadth,
        size_participation=turnover.get("markets") or {},
    )
    strength["as_of"] = now_text()
    strength["breadth"] = breadth
    strength["turnover_detail"] = turnover
    strength["sector_breadth_detail"] = sector_breadth

    snapshots = _append_market_snapshot(root, _market_snapshot(
        indices=indices,
        breadth=breadth,
        flows=flow_analysis,
        program=program,
        futures=futures,
        global_data=global_data,
        strength=strength,
        turnover=turnover,
    ))
    news_issues = _enrich_issue_market_reactions(news_issues, snapshots)
    news_digest = _refresh_issue_digest_reactions(news_digest, news_issues)

    current = {"generated_at": now_text(), "indices": indices, "breadth": breadth, "program": program, "source_quality": "MIXED"}
    summary = build_summary(indices, breadth, flow_analysis, program, strength, news_issues, domestic.get("official") or {})

    write_json(root / "data/market/current.json", current)
    write_json(root / "data/market/summary.json", summary)
    write_json(root / "data/market/flows.json", flow_analysis)
    write_json(root / "data/market/breadth.json", {"generated_at": now_text(), "markets": breadth})
    write_json(root / "data/market/futures.json", {"generated_at": now_text(), **futures})
    write_json(root / "data/market/global.json", global_data)
    write_json(root / "data/market/bok-official.json", bok_official)
    write_json(root / "data/market/turnover.json", turnover)
    write_json(root / "data/market/sector-breadth.json", sector_breadth)
    write_json(root / "data/market/strength.json", strength)
    write_json(root / "data/news/current.json", news_current)
    write_json(root / "data/news/disclosures.json", disclosures)
    write_json(root / "data/news/issues.json", news_issues)
    write_json(root / "data/news/issue-digest.json", news_digest)
    write_json(root / "data/stocks/smart-money.json", smart_money)
    write_json(root / "data/stocks/smart-money-backtest.json", {
        "generated_at": smart_money.get("generated_at"),
        "model_status": smart_money.get("model_status"),
        "validation": smart_money.get("validation"),
        "items": [
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "benchmark": item.get("benchmark"),
                "backtest": item.get("backtest"),
            }
            for item in (smart_money.get("items") or [])
        ],
    })
    write_json(root / "data/stocks/relative-strength.json", relative_strength_data)
    write_json(root / "data/ai/development-mix.json", git_development_mix(24))

    _sync_service_status(
        root,
        news=news_current,
        indices=indices,
        breadth=breadth,
        flows=flow_analysis,
        global_data=global_data,
        official=domestic.get("official") or {},
        turnover=turnover,
    )

    smart_items = smart_money.get("items") or []
    smart_estimated = sum(
        1 for item in smart_items
        if isinstance(item, dict) and item.get("evidence_state") == "ESTIMATED"
    )
    status = {
        "generated_at": now_text(),
        "status": "HEALTHY" if not errors else "PARTIAL",
        "product_features": {
            "domestic_indices": any(
                isinstance((indices.get(code) or {}).get("close"), (int, float))
                for code in ("KOSPI", "KOSDAQ")
            ),
            "investor_flow": _has_flow_values(flow_analysis),
            "breadth": _has_breadth_values(breadth),
            "kospi200_futures": (futures.get("KOSPI200_FUTURES") or {}).get("status"),
            "global_futures": bool(global_data.get("quotes")),
            "bok_official": bok_official.get("status"),
            "dart_disclosures": disclosures.get("status"),
            "dart_disclosure_count": disclosures.get("count", 0),
            "news": news_current.get("count", 0),
            "news_collection": news_current.get("collection_status"),
            "news_latest_at": news_current.get("latest_news_at"),
            "market_strength": strength.get("evidence_state"),
            "turnover": (turnover.get("combined") or {}).get("evidence_state"),
            "turnover_stock_count": (turnover.get("combined") or {}).get("stock_count"),
            "sector_breadth": sector_breadth.get("evidence_state"),
            "sector_count": sector_breadth.get("sector_count", 0),
            "size_participation": any(
                (((row or {}).get("size_participation") or {}).get("evidence_state") == "ESTIMATED")
                for row in (turnover.get("markets") or {}).values()
            ),
            "smart_money": smart_money.get("model_status"),
            "smart_money_estimated_items": smart_estimated,
            "smart_money_backtest_samples": ((smart_money.get("validation") or {}).get("sample_count") or 0),
            "relative_strength_items": sum(
                1 for item in (relative_strength_data.get("items") or [])
                if isinstance(item, dict) and item.get("evidence_state") == "ESTIMATED"
            ),
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
