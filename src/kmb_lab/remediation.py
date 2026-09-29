from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))

L3_TERMS = ("secret", "oauth", "billing", "payment", "credential", "force push",
            "destructive history", "권한 상승", "결제", "자격증명")
PATTERNS = (
    (r"stale[_ -]?sha|base sha.*mismatch", "STALE_SHA"),
    (r"merge conflict", "MERGE_CONFLICT"),
    (r"json.*(decode|parse)|invalid json", "JSON_FAILURE"),
    (r"schema.*(fail|invalid)", "SCHEMA_FAILURE"),
    (r"importerror|modulenotfounderror|cannot import", "IMPORT_FAILURE"),
    (r"rate.?limit|http 429", "RATE_LIMIT"),
    (r"timed? ?out|timeout", "ACTION_TIMEOUT"),
    (r"cancelled|canceled", "ACTION_CANCELLED"),
    (r"fingerprint mismatch|pages.*stale", "PAGE_STALE"),
    (r"write.*fail|no worktree change", "WRITE_FAILURE"),
    (r"test.*fail|assertionerror", "TEST_REGRESSION"),
)

def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default

def normalize_message(message: str) -> str:
    value = message.lower().strip()
    value = re.sub(r"\b[0-9a-f]{7,64}\b", "<sha>", value)
    value = re.sub(r"\b\d{5,}\b", "<id>", value)
    return re.sub(r"\s+", " ", value)[:500]

def incident_fingerprint(component: str, family: str, message: str) -> str:
    raw = "|".join((component.lower(), family.upper(), normalize_message(message)))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

def classify_error(message: str, component: str = "") -> str:
    text = (component + " " + message).lower()
    if any(term in text for term in L3_TERMS):
        return "EXTERNAL_PERMISSION_REQUIRED"
    for pattern, family in PATTERNS:
        if re.search(pattern, text, re.I):
            return family
    return "UNKNOWN_FAILURE"

def approval_level(family: str) -> str:
    if family == "EXTERNAL_PERMISSION_REQUIRED":
        return "L3"
    if family in {"ACTION_FAILURE", "ACTION_TIMEOUT", "ACTION_CANCELLED", "ACTION_STUCK",
                  "PAGE_STALE"}:
        return "L0"
    if family in {"WRITE_FAILURE", "STALE_SHA", "MERGE_CONFLICT", "JSON_FAILURE",
                  "SCHEMA_FAILURE", "IMPORT_FAILURE", "TEST_REGRESSION", "AGENT_STALE",
                  "HEARTBEAT_MISSING", "QUEUE_STALL", "REVIEW_STALE", "LEASE_EXPIRED",
                  "SERVICE_TELEMETRY_UNINITIALIZED"}:
        return "L1"
    return "L2"

def known_fixes(root: Path) -> list[dict[str, Any]]:
    payload = load_json(root / "data/ai/remediation/known-fixes.json", {})
    return payload.get("fixes", []) if isinstance(payload, dict) else []

def match_fix(family: str, root: Path) -> dict[str, Any] | None:
    rows = [r for r in known_fixes(root)
            if str(r.get("incident_family", "")).upper() == family.upper()
            and r.get("enabled", True)]
    if not rows:
        return None
    rows.sort(key=lambda r: (float(r.get("success_rate", 0)), int(r.get("sample_count", 0))),
              reverse=True)
    return rows[0]

def issue(component: str, family: str, message: str, root: Path, evidence: Any = None) -> dict[str, Any]:
    fix = match_fix(family, root)
    level = approval_level(family)
    return {
        "component": component, "family": family,
        "fingerprint": incident_fingerprint(component, family, message),
        "message": message, "approval_level": level,
        "auto_approved": level != "L3",
        "known_fix_id": fix.get("fix_id") if fix else None,
        "execution_mode": fix.get("execution_mode") if fix else "AI_REQUIRED",
        "evidence": evidence,
    }

def scan_json(root: Path) -> list[dict[str, Any]]:
    out = []
    for path in (root / "data").rglob("*.json") if (root / "data").exists() else []:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            out.append(issue(str(path.relative_to(root)), "JSON_FAILURE", str(exc), root))
    return out

def scan_services(root: Path) -> list[dict[str, Any]]:
    payload = load_json(root / "data/system/services.json", {})
    out = []
    for row in payload.get("services", []) if isinstance(payload, dict) else []:
        if str(row.get("status", "UNKNOWN")).upper() == "UNKNOWN" and not row.get("last_success_at"):
            out.append(issue(f"service:{row.get('id')}", "SERVICE_TELEMETRY_UNINITIALIZED",
                             "runtime state lacks evidence-backed last_success_at", root,
                             {"owner": row.get("owner")}))
    return out

def scan_agents(root: Path, now: datetime) -> list[dict[str, Any]]:
    try:
        from .pages import derive_agent_health
        rows = derive_agent_health(root, now=now)
    except Exception as exc:
        return [issue("agent-health", "UNKNOWN_FAILURE", str(exc), root)]
    return [issue(f"agent:{r.get('agent')}", "AGENT_STALE",
                  "ACTIVE declaration lacks fresh runtime heartbeat/output evidence", root,
                  {"execution": r.get("execution"), "last_execution": r.get("last_execution")})
            for r in rows if str(r.get("status", "")).upper() == "DEGRADED"]

def scan_tasks(root: Path, now: datetime, minutes: int = 90) -> list[dict[str, Any]]:
    payload = load_json(root / "data/ai/task-board.json", {})
    out = []
    for row in payload.get("tasks", []) if isinstance(payload, dict) else []:
        if str(row.get("status", "")).upper() not in {"IN_PROGRESS", "OPEN", "RUNNING", "VERIFICATION_PENDING"}:
            continue
        last = parse_time(row.get("last_progress_at") or row.get("started_at"))
        if last and now - last > timedelta(minutes=minutes):
            out.append(issue(f"task:{row.get('task_id')}", "QUEUE_STALL",
                             f"no progress for more than {minutes} minutes", root,
                             {"owner": row.get("owner"), "last_progress_at": row.get("last_progress_at")}))
    return out

def scan_reviews(root: Path, now: datetime, minutes: int = 120) -> list[dict[str, Any]]:
    payload = load_json(root / "data/ai/review-board.json", {})
    out = []
    for row in payload.get("items", []) if isinstance(payload, dict) else []:
        if str(row.get("status", "")).upper() not in {"OPEN", "REVIEWING"}:
            continue
        reviews = row.get("reviews") or {}
        pending = [a for a, v in reviews.items()
                   if str((v or {}).get("result", "PENDING")).upper() == "PENDING"]
        times = [parse_time(row.get("created_at"))] + [
            parse_time((v or {}).get("reviewed_at")) for v in reviews.values()
        ]
        times = [t for t in times if t]
        if pending and times and now - max(times) > timedelta(minutes=minutes):
            out.append(issue(f"review:{row.get('review_id')}", "REVIEW_STALE",
                             "pending roles: " + ",".join(pending), root,
                             {"pending": pending, "recovery_owner": row.get("recovery_owner")}))
    return out

def github_json(repository: str, endpoint: str, token: str | None) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "kmb-self-heal",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/{endpoint.lstrip('/')}", headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode())

def scan_actions(root: Path, repository: str | None, token: str | None, now: datetime):
    if not repository:
        return [], {"status": "NOT_REQUESTED"}
    try:
        payload = github_json(repository, "actions/runs?branch=main&per_page=50", token)
    except Exception as exc:
        return [], {"status": "UNAVAILABLE", "reason": str(exc)}
    latest = {}
    for run in payload.get("workflow_runs", []):
        latest.setdefault(str(run.get("name", "UNKNOWN")), run)
    out = []
    evidence = {}
    for name, run in latest.items():
        evidence[name] = {k: run.get(k) for k in
                          ("id", "status", "conclusion", "created_at", "updated_at", "run_attempt", "head_sha")}
        status = str(run.get("status") or "").lower()
        conclusion = str(run.get("conclusion") or "").lower()
        created = parse_time(run.get("created_at"))
        if status in {"queued", "in_progress", "waiting", "pending"} and created and now-created > timedelta(minutes=30):
            out.append(issue(f"workflow:{name}", "ACTION_STUCK", "non-terminal for >30 minutes",
                             root, evidence[name]))
        elif conclusion in {"failure", "timed_out", "cancelled", "canceled"}:
            fam = {"timed_out": "ACTION_TIMEOUT", "cancelled": "ACTION_CANCELLED",
                   "canceled": "ACTION_CANCELLED"}.get(conclusion, "ACTION_FAILURE")
            out.append(issue(f"workflow:{name}", fam, "latest conclusion=" + conclusion,
                             root, evidence[name]))
    return out, {"status": "OK", "latest": evidence}

def scan_repository(root: Path = ROOT, repository: str | None = None,
                    token: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    issues = []
    issues += scan_json(root)
    issues += scan_services(root)
    issues += scan_agents(root, current)
    issues += scan_tasks(root, current)
    issues += scan_reviews(root, current)
    action_issues, action_evidence = scan_actions(root, repository, token, current)
    issues += action_issues
    return {
        "schema_version": 1,
        "generated_at": current.astimezone(KST).isoformat(timespec="seconds"),
        "policy": {"AUTO_APPROVE_SAFE_FIX": True, "repair_first_review_immediately_after": True,
                   "l3_requires_human": True},
        "summary": {
            "total_issues": len(issues),
            "deterministic_auto_fixable": sum(
                1 for i in issues if i["auto_approved"] and i["execution_mode"] == "DETERMINISTIC"),
            "ai_auto_approved": sum(
                1 for i in issues if i["auto_approved"] and i["execution_mode"] != "DETERMINISTIC"),
            "human_required": sum(1 for i in issues if i["approval_level"] == "L3"),
        },
        "issues": issues,
        "workflow_evidence": action_evidence,
    }

def validate_registries(root: Path = ROOT) -> list[str]:
    errors = []
    for rel in (
        "data/ai/remediation/policy.json",
        "data/ai/remediation/known-fixes.json",
        "data/ai/remediation/error-signatures.json",
        "data/ai/remediation/prevention-registry.json",
    ):
        path = root / rel
        if not path.is_file():
            errors.append("missing remediation registry: " + rel)
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{rel}: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(rel + ": root must be object")
    return errors

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--output", default="data/system/remediation-snapshot.json")
    scan.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    scan.add_argument("--offline", action="store_true")
    sub.add_parser("validate")
    args = parser.parse_args()
    if args.command == "validate":
        errors = validate_registries()
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return 2 if errors else 0
    result = scan_repository(
        ROOT,
        repository=None if args.offline else args.repository,
        token=None if args.offline else os.environ.get("GITHUB_TOKEN"),
    )
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
