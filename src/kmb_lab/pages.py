from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))
AGENTS = ("AI-A", "AI-B", "AI-C", "AI-D", "AI-E")
AGENT_FRESHNESS_MINUTES = 75
DEFAULT_PAGES_URL = "https://juhwan7.github.io/korea-market-behavior-lab/"
CORE_SECTION_MARKERS = ("market-issues", "today-news", "ai-news-analysis", "issue-timeline", "overview", "market", "market-strength", "flows", "futures-global", "news-issues", "smart-money", "cycle", "ai-workshop", "work-products", "agent-health", "activity", "review", "recovery", "actions", "research", "experiments")

MATERIAL_EXACT = {
    "data/ai/CURRENT_BRIEFING.md",
    "data/ai/review-board.json",
    "data/ai/recovery-queue.json",
    "data/ai/task-board.json",
    "data/ai/events.jsonl",
    "data/ai/unresolved-problems.jsonl",
    "data/ai/development-mix.json",
}
MATERIAL_PREFIXES = (
    "data/ai/agents/",
    "data/ai/candidates/",
    "data/ai/executions/",
    "data/system/",
    "data/market/",
    "data/news/",
    "data/discovery/",
    "data/research/",
    "data/audits/",
    "data/experiments/",
    "data/stocks/",
)
TIME_KEYS = (
    "generated_at", "updated_at", "last_progress_at", "last_success_at",
    "last_attempt_at", "reviewed_at", "resolved_at", "created_at", "at",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def kst_now_text() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def is_material_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return normalized in MATERIAL_EXACT or any(normalized.startswith(prefix) for prefix in MATERIAL_PREFIXES)


def iter_material_files(root: Path = ROOT) -> Iterable[Path]:
    for rel in sorted(MATERIAL_EXACT):
        path = root / rel
        if path.is_file():
            yield path
    for prefix in MATERIAL_PREFIXES:
        base = root / prefix
        if not base.exists():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            yield path


def material_fingerprint(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in iter_material_files(root):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def extract_times(value: Any) -> list[datetime]:
    found: list[datetime] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in TIME_KEYS:
                parsed = parse_time(item)
                if parsed:
                    found.append(parsed)
            found.extend(extract_times(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(extract_times(item))
    return found


def max_time_text(values: Iterable[Any]) -> str | None:
    parsed = [parse_time(v) for v in values]
    parsed = [v for v in parsed if v is not None]
    if not parsed:
        return None
    return max(parsed).astimezone(KST).isoformat(timespec="seconds")


def latest_agent_output(root: Path, agent: str) -> tuple[str | None, str]:
    candidates: list[tuple[datetime, str]] = []
    for event in load_jsonl(root / "data/ai/events.jsonl"):
        if str(event.get("agent", "")).upper() == agent:
            at = parse_time(event.get("at"))
            if at:
                candidates.append((at, str(event.get("summary") or event.get("type") or "event")))

    review = load_json(root / "data/ai/review-board.json", {})
    for item in review.get("items", []) if isinstance(review, dict) else []:
        row = (item.get("reviews") or {}).get(agent, {})
        at = parse_time(row.get("reviewed_at"))
        if at:
            candidates.append((at, f"review {item.get('review_id', 'UNKNOWN')}: {row.get('result', 'UNKNOWN')}"))

    candidate_dir = root / "data/ai/candidates" / agent.lower()
    if candidate_dir.exists():
        for path in candidate_dir.rglob("*.json"):
            payload = load_json(path, {})
            for at in extract_times(payload):
                candidates.append((at, f"candidate {path.name}"))

    if agent == "AI-B":
        audits = root / "data/audits"
        if audits.exists():
            for path in audits.glob("*.json"):
                payload = load_json(path, {})
                if str(payload.get("auditor", "")).upper() == agent:
                    at = parse_time(payload.get("generated_at"))
                    if at:
                        candidates.append((at, f"audit {path.name}"))

    if agent == "AI-A":
        for folder in ("data/research/candidates", "data/research/observations", "data/research/queue-items"):
            base = root / folder
            if not base.exists():
                continue
            for path in base.glob("*.json"):
                payload = load_json(path, {})
                text = json.dumps(payload, ensure_ascii=False)
                if "AI-A" not in text and '"A"' not in text:
                    continue
                for at in extract_times(payload):
                    candidates.append((at, f"research {path.name}"))

    if not candidates:
        return None, "No runtime output evidence"
    at, summary = max(candidates, key=lambda x: x[0])
    return at.astimezone(KST).isoformat(timespec="seconds"), summary


def freshness_label(value: Any, now: datetime, target_minutes: int = AGENT_FRESHNESS_MINUTES) -> str:
    parsed = parse_time(value)
    if parsed is None:
        return "MISSING"
    return "FRESH" if now - parsed <= timedelta(minutes=target_minutes) else "STALE"


def derive_agent_health(root: Path = ROOT, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or utc_now()
    tasks_payload = load_json(root / "data/ai/task-board.json", {})
    tasks = tasks_payload.get("tasks", []) if isinstance(tasks_payload, dict) else []
    recovery_payload = load_json(root / "data/ai/recovery-queue.json", {})
    incidents = recovery_payload.get("incidents", []) if isinstance(recovery_payload, dict) else []

    rows: list[dict[str, Any]] = []
    for agent in AGENTS:
        state = load_json(root / f"data/ai/agents/{agent.lower()}.json", {})
        declared = str(state.get("status", "UNKNOWN")).upper()
        heartbeat_at = state.get("heartbeat_at") or state.get("last_progress_at")
        output_at, output_summary = latest_agent_output(root, agent)
        heartbeat = freshness_label(heartbeat_at, now)
        output = freshness_label(output_at, now)
        owned_tasks = [
            t for t in tasks
            if str(t.get("owner", "")).upper() == agent
            and str(t.get("status", "")).upper() not in {"COMPLETED", "RESOLVED", "CLOSED"}
        ]
        active_incidents = [
            i for i in incidents
            if str(i.get("recovery_owner", "")).upper() == agent
            and str(i.get("status", "")).upper() not in {"RESOLVED", "RECOVERED", "CLOSED"}
        ]
        runtime_evidence = state.get("runtime_evidence") or {}
        runtime_enabled = runtime_evidence.get("enabled")
        if active_incidents:
            overall = "RECOVERING"
        elif runtime_enabled is False or declared in {"BLOCKED", "FAILED", "STOPPED", "DISABLED"}:
            overall = "BLOCKED"
        elif heartbeat == "FRESH" and output == "FRESH":
            overall = "ACTIVE"
        elif heartbeat == "FRESH" and runtime_enabled is True:
            overall = "OBSERVED"
        else:
            overall = "DEGRADED"
        if declared == "ACTIVE" and overall == "DEGRADED":
            execution = "STATE MISMATCH"
        elif overall == "OBSERVED":
            execution = "OBSERVED_NO_FRESH_OUTPUT"
        else:
            execution = overall
        last_execution = max_time_text([heartbeat_at, output_at])
        rows.append({
            "agent": agent,
            "declared": declared,
            "status": overall,
            "execution": execution,
            "heartbeat": heartbeat,
            "heartbeat_at": heartbeat_at,
            "output": output,
            "output_at": output_at,
            "workflow": "UNMAPPED",
            "queue": "ACTIVE" if owned_tasks else "NONE",
            "recovery": str(active_incidents[0].get("status", "RECOVERING")) if active_incidents else "NONE",
            "last_execution": last_execution or "UNKNOWN",
            "last_healthy": last_execution if overall == "ACTIVE" else "UNKNOWN",
            "current_task": state.get("current_task") or (owned_tasks[0].get("title") if owned_tasks else "UNKNOWN"),
            "last_result": output_summary,
            "next_expected": state.get("next_expected_at") or "UNKNOWN",
        })
    return rows


def github_json(repository: str, endpoint: str, token: str | None) -> Any:
    url = f"https://api.github.com/repos/{repository}/{endpoint.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "kmb-pages-generator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def workflow_evidence(repository: str | None, token: str | None, offline: bool) -> dict[str, Any]:
    if offline or not repository:
        return {"status": "OFFLINE", "latest": {}}
    try:
        payload = github_json(repository, "actions/runs?branch=main&per_page=100", token)
    except Exception as exc:
        return {"status": "UNKNOWN", "error": str(exc), "latest": {}}
    latest: dict[str, dict[str, Any]] = {}
    for run in payload.get("workflow_runs", []):
        name = str(run.get("name", "UNKNOWN"))
        if name not in latest:
            latest[name] = {
                "id": run.get("id"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "head_sha": run.get("head_sha"),
                "created_at": run.get("created_at"),
                "html_url": run.get("html_url"),
            }
    return {"status": "OK", "latest": latest}


def parse_briefing(path: Path) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"요약": []}
    current = "요약"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"요약": ["MISSING"]}
    for raw in lines:
        line = raw.strip()
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
        elif line.startswith("- "):
            sections.setdefault(current, []).append(line[2:].strip())
        elif line.startswith("Updated:"):
            sections.setdefault("Updated", []).append(line.split(":", 1)[1].strip())
    return sections


def market_model(root: Path) -> dict[str, Any]:
    payload = load_json(root / "data/market/summary.json", {})
    if not isinstance(payload, dict) or not payload:
        return {
            "KOSPI": "UNKNOWN", "KOSDAQ": "UNKNOWN", "거래대금": "UNKNOWN",
            "급등락": "UNKNOWN", "상대강도": "UNKNOWN", "주요 테마": "UNKNOWN",
            "대장주 변화": "UNKNOWN", "주요 뉴스/공시": "UNKNOWN",
            "Behavior Event": "UNKNOWN", "CONFIRMED": "UNKNOWN",
            "HYPOTHESIS": "UNKNOWN", "UNKNOWN": "NOT COLLECTED",
        }
    aliases = {
        "KOSPI": ("kospi", "KOSPI"), "KOSDAQ": ("kosdaq", "KOSDAQ"),
        "거래대금": ("turnover", "trading_value"), "급등락": ("movers", "volatility"),
        "상대강도": ("relative_strength",), "주요 테마": ("themes",),
        "대장주 변화": ("leaders",), "주요 뉴스/공시": ("news", "disclosures"),
        "Behavior Event": ("behavior_events",), "CONFIRMED": ("confirmed",),
        "HYPOTHESIS": ("hypothesis", "hypotheses"), "UNKNOWN": ("unknown",),
    }
    result: dict[str, Any] = {}
    for label, keys in aliases.items():
        value: Any = None
        for key in keys:
            if key in payload:
                value = payload[key]
                break
        result[label] = value if value not in (None, "", [], {}) else "UNKNOWN"
    return result


def intelligence_model(root: Path) -> dict[str, Any]:
    return {
        "current": load_json(root / "data/market/current.json", {}),
        "flows": load_json(root / "data/market/flows.json", {}),
        "futures": load_json(root / "data/market/futures.json", {}),
        "global": load_json(root / "data/market/global.json", {}),
        "strength": load_json(root / "data/market/strength.json", {}),
        "news": load_json(root / "data/news/current.json", {}),
        "issues": load_json(root / "data/news/issues.json", {}),
        "issue_digest": load_json(root / "data/news/issue-digest.json", {}),
        "smart_money": load_json(root / "data/stocks/smart-money.json", {}),
        "collector_status": load_json(root / "data/system/collector-status.json", {}),
        "development_mix": load_json(root / "data/ai/development-mix.json", {}),
        "unresolved": load_jsonl(root / "data/ai/unresolved-problems.jsonl"),
    }


def stringify(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def esc(value: Any) -> str:
    return html.escape(stringify(value))


def status_class(value: str) -> str:
    upper = value.upper()
    if upper in {"ACTIVE", "FRESH", "OK", "SUCCESS", "LIVE", "RECOVERED", "RESOLVED", "PASS"}:
        return "ok"
    if upper in {"DEGRADED", "RECOVERING", "STALE", "STATE MISMATCH", "PASS_WITH_NOTES", "REVIEWING"}:
        return "warn"
    if upper in {"BLOCKED", "FAILED", "FAILURE", "FIX_REQUIRED", "REJECT"}:
        return "bad"
    return "muted"



def _candidate_summary(payload: dict[str, Any], path: Path, root: Path) -> dict[str, Any]:
    major = payload.get("major_work") if isinstance(payload.get("major_work"), dict) else {}
    agent = str(payload.get("agent") or payload.get("auditor") or "UNKNOWN").upper()
    created = payload.get("created_at") or payload.get("generated_at")
    times = extract_times(payload)
    if not created and times:
        created = max(times).astimezone(KST).isoformat(timespec="seconds")
    title = (
        major.get("title") or payload.get("title") or payload.get("name")
        or major.get("hypothesis_id") or payload.get("id") or path.stem
    )
    result = major.get("result") or payload.get("verdict") or payload.get("status") or major.get("status") or "CANDIDATE"
    summary = major.get("summary") or payload.get("summary")
    if not summary:
        hypotheses = major.get("hypothesis") or payload.get("hypothesis")
        if isinstance(hypotheses, list) and hypotheses:
            summary = hypotheses[0]
        elif isinstance(hypotheses, str):
            summary = hypotheses
    handoffs = payload.get("handoffs") if isinstance(payload.get("handoffs"), list) else []
    next_work = payload.get("next_work") or payload.get("next_action")
    return {
        "id": major.get("hypothesis_id") or payload.get("id") or path.stem,
        "title": title,
        "agent": agent,
        "type": payload.get("type") or "CANDIDATE",
        "created_at": created,
        "updated_at": created,
        "status": "CANDIDATE",
        "result": result,
        "summary": summary or "상세 결과는 작업물 원문에서 확인할 수 있습니다.",
        "artifact_path": path.relative_to(root).as_posix(),
        "source_commit": payload.get("source_commit") or payload.get("commit_sha"),
        "handoffs": handoffs,
        "next_work": next_work,
        "verified": bool(payload.get("verified", False)),
        "related_issue_ids": payload.get("related_issue_ids") or major.get("related_issue_ids") or [],
    }


def work_products_model(root: Path) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    candidate_root = root / "data/ai/candidates"
    if candidate_root.exists():
        for path in candidate_root.rglob("*.json"):
            payload = load_json(path, {})
            if isinstance(payload, dict):
                products.append(_candidate_summary(payload, path, root))
    for path in (root / "data/audits").glob("*.json") if (root / "data/audits").exists() else []:
        payload = load_json(path, {})
        if not isinstance(payload, dict):
            continue
        products.append({
            "id": payload.get("id") or path.stem,
            "title": payload.get("title") or f"Evidence audit · {payload.get('verdict', 'UNKNOWN')}",
            "agent": str(payload.get("auditor") or "AI-B").upper(),
            "type": "AUDIT",
            "created_at": payload.get("generated_at"),
            "updated_at": payload.get("generated_at"),
            "status": "VERIFIED" if payload.get("verified") is True else "OUTPUT_CREATED",
            "result": payload.get("verdict") or payload.get("status") or "UNKNOWN",
            "summary": payload.get("summary") or "근거·출처 검증 작업",
            "artifact_path": path.relative_to(root).as_posix(),
            "source_commit": payload.get("source_commit") or payload.get("commit_sha"),
            "handoffs": payload.get("handoffs") or [],
            "next_work": payload.get("next_work") or payload.get("next_action"),
            "verified": bool(payload.get("verified", False)),
            "related_issue_ids": payload.get("related_issue_ids") or [],
        })
    products.sort(key=lambda row: parse_time(row.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return products


def execution_model(root: Path, agents: list[dict[str, Any]], products: list[dict[str, Any]]) -> dict[str, Any]:
    explicit: list[dict[str, Any]] = []
    execution_root = root / "data/ai/executions"
    if execution_root.exists():
        for path in execution_root.rglob("*.json"):
            if path.name == "latest.json":
                continue
            payload = load_json(path, {})
            if isinstance(payload, dict):
                row = dict(payload)
                row["artifact_path"] = path.relative_to(root).as_posix()
                explicit.append(row)
    explicit.sort(key=lambda row: parse_time(row.get("finished_at") or row.get("started_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    latest_products: dict[str, dict[str, Any]] = {}
    for item in products:
        agent = str(item.get("agent", "")).upper()
        if agent in AGENTS and agent not in latest_products:
            latest_products[agent] = item
    current = []
    for row in agents:
        agent = row["agent"]
        product = latest_products.get(agent)
        current.append({
            "agent": agent,
            "status": row.get("execution") or row.get("status"),
            "last_execution": row.get("last_execution"),
            "heartbeat_at": row.get("heartbeat_at"),
            "output_at": row.get("output_at"),
            "current_task": row.get("current_task"),
            "latest_output": product,
            "next_work": (product or {}).get("next_work"),
        })
    return {"explicit": explicit[:100], "current": current}

def build_model(root: Path, source_commit: str, repository: str | None, token: str | None, offline: bool) -> dict[str, Any]:
    review = load_json(root / "data/ai/review-board.json", {})
    recovery = load_json(root / "data/ai/recovery-queue.json", {})
    tasks = load_json(root / "data/ai/task-board.json", {})
    experiments = load_json(root / "data/experiments/registry.json", {})
    research = load_json(root / "data/research/research-queue.json", {})
    activity: list[dict[str, Any]] = []
    for event in load_jsonl(root / "data/ai/events.jsonl"):
        activity.append({"at": event.get("at"), "agent": event.get("agent", "SYSTEM"), "title": event.get("summary") or event.get("type") or "event", "detail": event})
    audits_dir = root / "data/audits"
    if audits_dir.exists():
        for path in audits_dir.glob("*.json"):
            payload = load_json(path, {})
            if isinstance(payload, dict) and payload.get("generated_at"):
                activity.append({"at": payload.get("generated_at"), "agent": payload.get("auditor", "AI-B"), "title": f"evidence audit · {payload.get('verdict', 'UNKNOWN')}", "detail": {"file": path.name, "findings": payload.get("findings", [])}})
    activity.sort(key=lambda item: parse_time(item.get("at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    agents = derive_agent_health(root)
    work_products = work_products_model(root)
    executions = execution_model(root, agents, work_products)
    intelligence = intelligence_model(root)
    intelligence["news_work_products"] = [p for p in work_products if p.get("related_issue_ids")]
    return {
        "generated_at": kst_now_text(),
        "source_commit": source_commit,
        "material_fingerprint": material_fingerprint(root),
        "repository": repository or "UNKNOWN",
        "freshness": {"label": "LIVE", "note": "generated from deployment material state"},
        "market": market_model(root),
        "intelligence": intelligence,
        "briefing": parse_briefing(root / "data/ai/CURRENT_BRIEFING.md"),
        "agents": agents,
        "activity": activity[:30],
        "work_products": work_products[:100],
        "executions": executions,
        "review": review, "recovery": recovery, "tasks": tasks,
        "experiments": experiments, "research": research,
        "workflows": workflow_evidence(repository, token, offline),
    }



def market_news_payload(model: dict[str, Any]) -> dict[str, Any]:
    intelligence = model.get("intelligence") or {}
    current = intelligence.get("news") or {}
    issue_doc = intelligence.get("issues") or {}
    digest = intelligence.get("issue_digest") or {}
    issues = issue_doc.get("issues") or []
    work = intelligence.get("news_work_products") or []
    return {
        "schema_version": 1,
        "generated_at": model.get("generated_at"),
        "source_commit": model.get("source_commit"),
        "latest_news_at": current.get("latest_news_at"),
        "latest_collection_at": current.get("collection_attempted_at") or current.get("generated_at"),
        "latest_issue_at": digest.get("latest_issue_at") or issue_doc.get("generated_at"),
        "collection_status": current.get("collection_status") or digest.get("collection_status") or "UNKNOWN",
        "sources_checked": current.get("sources_checked"),
        "issues": issues[:40],
        "news": (current.get("items") or [])[:80],
        "analysis_in_progress": work[:30],
        "strengthening": [x for x in issues if x.get("state") == "STRENGTHENING"][:20],
        "weakening": [x for x in issues if x.get("state") == "WEAKENING"][:20],
        "resolved": [x for x in issues if x.get("state") == "RESOLVED"][:20],
    }


def render_html(model: dict[str, Any]) -> str:
    """Render the Korean-first user UI while keeping raw canonical state internal."""
    from .pages_korean import render_korean_html
    return render_korean_html(model)

def generate(output_dir: Path, source_commit: str, repository: str | None, token: str | None, offline: bool) -> dict[str, Any]:
    model = build_model(ROOT, source_commit, repository, token, offline)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(render_html(model), encoding="utf-8")
    status = {"schema_version": 1, "generated_at": model["generated_at"], "source_commit": source_commit, "material_fingerprint": model["material_fingerprint"], "freshness": model["freshness"], "agents": model["agents"], "workflows": model["workflows"]}
    (output_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "ai-activity.json").write_text(json.dumps({"schema_version": 1, "generated_at": model["generated_at"], "source_commit": source_commit, "executions": model["executions"], "work_products": model["work_products"]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "market-news.json").write_text(json.dumps(market_news_payload(model), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status


def fetch_url_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "kmb-pages-verifier", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_url_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "kmb-pages-verifier", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8")


def inspect_live_pages(live_url: str, root: Path = ROOT, source_commit: str | None = None) -> dict[str, Any]:
    base = live_url.rstrip("/") + "/"
    current_fp = material_fingerprint(root)
    try:
        live = fetch_url_json(base + "status.json?ts=" + str(int(time.time())))
    except Exception as exc:
        return {"status": "PAGES_UNKNOWN", "reason": str(exc), "deploy_required": True}
    live_fp = live.get("material_fingerprint")
    live_sha = live.get("source_commit")
    if live_fp != current_fp:
        return {"status": "PAGES_STALE", "reason": "material fingerprint mismatch", "deploy_required": True, "live_source_commit": live_sha, "expected_source_commit": source_commit}
    if source_commit and live_sha != source_commit:
        return {"status": "LIVE_MATERIAL_MATCH_MAIN_AHEAD", "reason": "main SHA differs but no user-visible material state differs", "deploy_required": False, "live_source_commit": live_sha, "expected_source_commit": source_commit}
    return {"status": "LIVE", "deploy_required": False, "live_source_commit": live_sha, "generated_at": live.get("generated_at")}


def verify_live(live_url: str, source_commit: str, attempts: int, sleep_seconds: float) -> dict[str, Any]:
    base = live_url.rstrip("/") + "/"
    expected_fingerprint = material_fingerprint(ROOT)
    last_error = "not checked"
    for attempt in range(1, max(1, attempts) + 1):
        try:
            status = fetch_url_json(base + "status.json?ts=" + str(int(time.time())))
            page = fetch_url_text(base + "?ts=" + str(int(time.time())))
            market_news = fetch_url_json(base + "market-news.json?ts=" + str(int(time.time())))
            if status.get("source_commit") != source_commit:
                raise RuntimeError(f"status.json source_commit={status.get('source_commit')} expected={source_commit}")
            if not status.get("generated_at"):
                raise RuntimeError("status.json generated_at missing")
            if status.get("material_fingerprint") != expected_fingerprint:
                raise RuntimeError(
                    f"status.json material_fingerprint={status.get('material_fingerprint')} expected={expected_fingerprint}"
                )
            if market_news.get("source_commit") != source_commit:
                raise RuntimeError(f"market-news.json source_commit={market_news.get('source_commit')} expected={source_commit}")
            if not market_news.get("generated_at"):
                raise RuntimeError("market-news.json generated_at missing")
            if source_commit not in page:
                raise RuntimeError("index.html does not expose expected source commit")
            if expected_fingerprint not in page:
                raise RuntimeError("index.html does not expose expected material fingerprint")
            missing_sections = [
                marker for marker in CORE_SECTION_MARKERS
                if f'data-kmb-section="{marker}"' not in page
            ]
            if missing_sections:
                raise RuntimeError("index.html missing core sections: " + ",".join(missing_sections))
            result = {
                "status": "LIVE",
                "source_commit": status.get("source_commit"),
                "generated_at": status.get("generated_at"),
                "material_fingerprint": status.get("material_fingerprint"),
                "core_sections": "OK",
                "attempt": attempt,
            }
            print(json.dumps(result, ensure_ascii=False))
            return result
        except Exception as exc:
            last_error = str(exc)
            if attempt < attempts:
                time.sleep(max(0.0, sleep_seconds))
    raise SystemExit(f"live Pages verification failed: {last_error}")

def git_head() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "UNKNOWN"


def main() -> int:
    parser = argparse.ArgumentParser(description="KMB GitHub Pages generator and verifier")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--output-dir", default="web")
    gen.add_argument("--source-commit", default=None)
    gen.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    gen.add_argument("--offline", action="store_true")
    should = sub.add_parser("should-deploy")
    should.add_argument("--live-url", default=DEFAULT_PAGES_URL)
    should.add_argument("--source-commit", default=None)
    pre = sub.add_parser("preflight")
    pre.add_argument("--live-url", default=DEFAULT_PAGES_URL)
    pre.add_argument("--source-commit", default=None)
    pre.add_argument("--strict", action="store_true")
    verify = sub.add_parser("verify-live")
    verify.add_argument("--url", required=True)
    verify.add_argument("--source-commit", required=True)
    verify.add_argument("--attempts", type=int, default=12)
    verify.add_argument("--sleep-seconds", type=float, default=5.0)
    args = parser.parse_args()
    source_commit = getattr(args, "source_commit", None) or git_head()
    if args.command == "generate":
        print(json.dumps(generate(ROOT / args.output_dir, source_commit, args.repository, os.environ.get("GITHUB_TOKEN"), args.offline), ensure_ascii=False, indent=2))
        return 0
    if args.command == "should-deploy":
        result = inspect_live_pages(args.live_url, ROOT, source_commit)
        print("true" if result["deploy_required"] else "false")
        return 0
    if args.command == "preflight":
        result = inspect_live_pages(args.live_url, ROOT, source_commit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if args.strict and result["status"] in {"PAGES_STALE", "PAGES_UNKNOWN"} else 0
    if args.command == "verify-live":
        verify_live(args.url, args.source_commit, args.attempts, args.sleep_seconds)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
