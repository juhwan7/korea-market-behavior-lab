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
AGENT_FRESHNESS_MINUTES = 60
DEFAULT_PAGES_URL = "https://juhwan7.github.io/korea-market-behavior-lab/"

MATERIAL_EXACT = {
    "data/ai/CURRENT_BRIEFING.md",
    "data/ai/review-board.json",
    "data/ai/recovery-queue.json",
    "data/ai/task-board.json",
    "data/ai/events.jsonl",
}
MATERIAL_PREFIXES = (
    "data/ai/agents/",
    "data/system/",
    "data/market/",
    "data/news/",
    "data/discovery/",
    "data/research/",
    "data/audits/",
    "data/experiments/",
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
        if active_incidents:
            overall = "RECOVERING"
        elif declared in {"BLOCKED", "FAILED", "STOPPED", "DISABLED"}:
            overall = "BLOCKED"
        elif heartbeat == "FRESH" and output == "FRESH":
            overall = "ACTIVE"
        else:
            overall = "DEGRADED"
        execution = "STATE MISMATCH" if declared == "ACTIVE" and overall == "DEGRADED" else overall
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
    return {
        "generated_at": kst_now_text(),
        "source_commit": source_commit,
        "material_fingerprint": material_fingerprint(root),
        "repository": repository or "UNKNOWN",
        "freshness": {"label": "LIVE", "note": "generated from deployment material state"},
        "market": market_model(root),
        "briefing": parse_briefing(root / "data/ai/CURRENT_BRIEFING.md"),
        "agents": derive_agent_health(root),
        "activity": activity[:30],
        "review": review, "recovery": recovery, "tasks": tasks,
        "experiments": experiments, "research": research,
        "workflows": workflow_evidence(repository, token, offline),
    }


def render_html(model: dict[str, Any]) -> str:
    briefing = model["briefing"]
    important = [
        ("지금 가장 중요한 시장 변화", briefing.get("지금 가장 중요한 시장 변화", ["UNKNOWN"])),
        ("지금 가장 중요한 시스템 문제", briefing.get("현재 문제", ["UNKNOWN"])),
        ("현재 진행 중", briefing.get("현재 진행 중", ["UNKNOWN"])),
        ("최근 성공", briefing.get("최근 성공", ["UNKNOWN"])),
        ("현재 recovery", briefing.get("현재 recovery", ["UNKNOWN"])),
        ("다음 우선순위", briefing.get("다음 우선순위", ["UNKNOWN"])),
    ]
    briefing_html = "".join(f'<article class="card"><h3>{esc(title)}</h3><ul>' + "".join(f"<li>{esc(item)}</li>" for item in (items or ["UNKNOWN"])) + "</ul></article>" for title, items in important)
    market_html = "".join(f'<article class="metric"><span>{esc(label)}</span><strong>{esc(value)}</strong></article>' for label, value in model["market"].items())

    agent_rows = []
    for row in model["agents"]:
        agent_rows.append("<tr>" + f"<td><strong>{esc(row['agent'])}</strong><small>{esc(row['declared'])}</small></td>" + f"<td><span class='badge {status_class(row['status'])}'>{esc(row['status'])}</span></td>" + f"<td><span class='badge {status_class(row['execution'])}'>{esc(row['execution'])}</span></td>" + f"<td>{esc(row['heartbeat'])}<small>{esc(row['heartbeat_at'] or 'UNKNOWN')}</small></td>" + f"<td>{esc(row['output'])}<small>{esc(row['output_at'] or 'UNKNOWN')}</small></td>" + f"<td>{esc(row['workflow'])}</td><td>{esc(row['queue'])}</td><td>{esc(row['recovery'])}</td></tr>")

    agent_details = "".join("<details class='card'><summary>" + f"<strong>{esc(row['agent'])}</strong> · {esc(row['status'])} · {esc(row['current_task'])}</summary>" + f"<p><b>Last execution:</b> {esc(row['last_execution'])}</p><p><b>Last healthy:</b> {esc(row['last_healthy'])}</p><p><b>Last result:</b> {esc(row['last_result'])}</p><p><b>Next expected:</b> {esc(row['next_expected'])}</p></details>" for row in model["agents"])

    activity_html = "".join("<details class='activity'><summary>" + f"<time>{esc(item.get('at') or 'UNKNOWN')}</time> <b>{esc(item.get('agent'))}</b> {esc(item.get('title'))}</summary><pre>{esc(item.get('detail'))}</pre></details>" for item in model["activity"]) or "<p class='empty'>활동 증거가 없습니다.</p>"

    review_html = ""
    for item in model["review"].get("items", []) if isinstance(model["review"], dict) else []:
        reviews = item.get("reviews", {})
        review_badges = " ".join(f"<span class='badge {status_class(str((reviews.get(agent) or {}).get('result','PENDING')))}'>{esc(agent)} {esc((reviews.get(agent) or {}).get('result','PENDING'))}</span>" for agent in AGENTS)
        review_html += "<details class='card'><summary>" + f"<strong>{esc(item.get('title','Material event'))}</strong> · {esc(item.get('status','UNKNOWN'))}</summary>" + f"<p>{review_badges}</p><p><b>Recovery owner:</b> {esc(item.get('recovery_owner','UNKNOWN'))}</p><p><b>Commit:</b> {esc((item.get('evidence') or {}).get('commit_sha','UNKNOWN'))}</p><p><b>Actions:</b> {esc((item.get('evidence') or {}).get('actions_result','UNKNOWN'))}</p><p><b>Expected state:</b> {esc((item.get('evidence') or {}).get('expected_state_verified','UNKNOWN'))}</p><p><b>현재 병목:</b> {esc(item.get('next_action','UNKNOWN'))}</p></details>"
    if not review_html:
        review_html = "<p class='empty'>OPEN/REVIEWING material event가 없습니다.</p>"

    incidents = model["recovery"].get("incidents", []) if isinstance(model["recovery"], dict) else []
    recovery_html = "".join("<details class='card'><summary>" + f"<span class='badge {status_class(str(i.get('status','UNKNOWN')))}'>{esc(i.get('status','UNKNOWN'))}</span> <strong>{esc(i.get('incident_id','UNKNOWN'))}</strong></summary>" + f"<p><b>Recovery Owner:</b> {esc(i.get('recovery_owner','UNKNOWN'))}</p><p><b>Root cause:</b> {esc(i.get('root_cause','UNKNOWN'))}</p><p><b>Resolution commit:</b> {esc(i.get('resolution_commit','UNKNOWN'))}</p><p><b>Prevention:</b> {esc(i.get('prevention','UNKNOWN'))}</p></details>" for i in incidents[-12:]) or "<p class='empty'>Recovery 기록이 없습니다.</p>"

    workflow_latest = model["workflows"].get("latest", {}) if isinstance(model["workflows"], dict) else {}
    workflow_html = "".join("<article class='card compact'>" + f"<h3>{esc(name)}</h3><p><span class='badge {status_class(str(run.get('conclusion') or run.get('status') or 'UNKNOWN'))}'>{esc(run.get('conclusion') or run.get('status') or 'UNKNOWN')}</span></p><p>SHA {esc(str(run.get('head_sha') or 'UNKNOWN')[:12])}</p><p>{esc(run.get('created_at') or 'UNKNOWN')}</p></article>" for name, run in workflow_latest.items()) or "<p class='empty'>Workflow runtime evidence unavailable.</p>"

    research_items = model["research"].get("items", []) if isinstance(model["research"], dict) else []
    research_html = "".join("<details class='card'><summary>" + f"<strong>{esc(item.get('title',item.get('id','Research')))}</strong> · {esc(item.get('status','UNKNOWN'))}</summary><p>{esc(item.get('reason',''))}</p><p><b>Evidence:</b> {esc(item.get('evidence_state','UNKNOWN'))}</p></details>" for item in research_items[:20]) or "<p class='empty'>Research queue is empty.</p>"

    exp_items = model["experiments"].get("experiments", []) if isinstance(model["experiments"], dict) else []
    exp_html = "".join("<details class='card'><summary>" + f"<strong>{esc(item.get('name',item.get('id','Experiment')))}</strong> · {esc(item.get('status','UNKNOWN'))}</summary><p>sample_count={esc(item.get('sample_count','UNKNOWN'))} · production_eligible={esc(item.get('production_eligible','UNKNOWN'))}</p><p>{esc(item.get('failure_condition',''))}</p></details>" for item in exp_items[:20]) or "<p class='empty'>Experiments are not available.</p>"

    source_short = str(model["source_commit"])[:12]
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="kmb-source-commit" content="{esc(model['source_commit'])}"><meta name="kmb-generated-at" content="{esc(model['generated_at'])}">
<title>KMB · Korea Market Behavior Lab</title>
<style>
:root{{--bg:#f4f6f8;--card:#fff;--line:#e5e7eb;--text:#111827;--muted:#64748b;--ok:#0f766e;--okbg:#ecfdf5;--warn:#a16207;--warnbg:#fffbeb;--bad:#b91c1c;--badbg:#fef2f2}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:1240px;margin:auto;padding:20px}}header{{position:sticky;top:0;z-index:3;background:rgba(244,246,248,.94);backdrop-filter:blur(12px);padding:14px 0 10px;border-bottom:1px solid var(--line);margin-bottom:18px}}h1{{font-size:clamp(24px,4vw,38px);margin:6px 0}}h2{{margin:30px 0 12px;font-size:20px}}h3{{margin:0 0 10px;font-size:15px}}p,li{{line-height:1.55}}small{{display:block;color:var(--muted);margin-top:4px}}ul{{padding-left:20px;margin:8px 0}}.meta{{display:flex;gap:8px;flex-wrap:wrap;color:var(--muted);font-size:13px}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}.metric-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}}.card,.metric,.activity{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}}.metric span{{display:block;color:var(--muted);font-size:12px;margin-bottom:7px}}.metric strong{{display:block;overflow-wrap:anywhere}}.badge{{display:inline-block;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:700;background:#f1f5f9;color:#475569;margin:2px}}.badge.ok{{background:var(--okbg);color:var(--ok)}}.badge.warn{{background:var(--warnbg);color:var(--warn)}}.badge.bad{{background:var(--badbg);color:var(--bad)}}.badge.muted{{background:#f1f5f9;color:#64748b}}.table-wrap{{background:#fff;border:1px solid var(--line);border-radius:14px;overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:820px}}th,td{{padding:12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top;font-size:13px}}th{{background:#f8fafc}}details{{margin-bottom:10px}}summary{{cursor:pointer;line-height:1.5}}.activity summary{{display:grid;grid-template-columns:170px 70px 1fr;gap:8px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f8fafc;padding:12px;border-radius:10px;font-size:12px}}.empty,.section-note{{color:var(--muted)}}.section-note{{font-size:13px;margin-top:-6px}}.mobile-health{{display:none}}
@media(max-width:860px){{.grid{{grid-template-columns:1fr 1fr}}.metric-grid{{grid-template-columns:1fr 1fr}}}}@media(max-width:640px){{main{{padding:12px}}header{{position:static}}.grid,.metric-grid{{grid-template-columns:1fr}}.table-wrap{{display:none}}.mobile-health{{display:block}}.activity summary{{grid-template-columns:1fr}}.card,.metric,.activity{{padding:14px}}}}
</style></head>
<body data-source-commit="{esc(model['source_commit'])}"><main><header><div class="meta"><span class="badge ok">{esc(model['freshness']['label'])}</span><span>Updated {esc(model['generated_at'])}</span><span>Source {esc(source_short)}</span></div><h1>Korea Market Behavior Lab</h1><p>시장 상태와 5-AI 운영 상태를 같은 화면에서 확인하는 운영 대시보드. 없는 데이터는 생성하지 않고 UNKNOWN/MISSING으로 표시합니다.</p></header>
<h2>지금 핵심</h2><div class="grid">{briefing_html}</div>
<h2>시장 상태</h2><p class="section-note">시장 canonical data가 아직 연결되지 않은 항목은 NOT COLLECTED/UNKNOWN입니다.</p><div class="metric-grid">{market_html}</div>
<h2>5-AI Health Matrix</h2><p class="section-note">repository의 ACTIVE 문자열보다 heartbeat/output 증거를 우선합니다. per-agent workflow가 매핑되지 않으면 UNMAPPED입니다.</p><div class="table-wrap"><table><thead><tr><th>Agent</th><th>Status</th><th>Execution</th><th>Heartbeat</th><th>Output</th><th>Workflow</th><th>Queue</th><th>Recovery</th></tr></thead><tbody>{''.join(agent_rows)}</tbody></table></div><div class="mobile-health">{agent_details}</div>
<h2>최근 AI 활동</h2>{activity_html}
<h2>Five-AI Review Mesh</h2>{review_html}
<h2>Recovery</h2>{recovery_html}
<h2>GitHub Actions</h2><div class="grid">{workflow_html}</div>
<h2>Research</h2>{research_html}
<h2>Experiments</h2>{exp_html}
<footer class="meta" style="margin:30px 0 12px">Generated from canonical repository data · material fingerprint {esc(model['material_fingerprint'][:16])}</footer>
</main></body></html>"""


def generate(output_dir: Path, source_commit: str, repository: str | None, token: str | None, offline: bool) -> dict[str, Any]:
    model = build_model(ROOT, source_commit, repository, token, offline)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(render_html(model), encoding="utf-8")
    status = {"schema_version": 1, "generated_at": model["generated_at"], "source_commit": source_commit, "material_fingerprint": model["material_fingerprint"], "freshness": model["freshness"], "agents": model["agents"], "workflows": model["workflows"]}
    (output_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    last_error = "not checked"
    for attempt in range(1, max(1, attempts) + 1):
        try:
            status = fetch_url_json(base + "status.json?ts=" + str(int(time.time())))
            page = fetch_url_text(base + "?ts=" + str(int(time.time())))
            if status.get("source_commit") != source_commit:
                raise RuntimeError(f"status.json source_commit={status.get('source_commit')} expected={source_commit}")
            if not status.get("generated_at"):
                raise RuntimeError("status.json generated_at missing")
            if source_commit not in page:
                raise RuntimeError("index.html does not expose expected source commit")
            result = {"status": "LIVE", "source_commit": status.get("source_commit"), "generated_at": status.get("generated_at"), "attempt": attempt}
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
