from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .state import BAD_SERVICE_STATES, atomic_json_write, parse_time, utc_now

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "data/system/services.json"
HANDOFFS = ROOT / "data/ai/handoffs"

BLOCKING_HANDOFF_STATES = {
    "BLOCKED",
    "BLOCKED_BY_EXTERNAL_WRITE_GUARD",
    "WRITE_FAILED",
    "SAFETY_GUARD_BLOCKED",
    "STALE_SHA",
    "CONFLICT",
    "TIMEOUT",
    "FAILED",
    "MISSING",
    "UNAPPLIED",
    "VERIFICATION_PENDING",
    "HUMAN_REQUIRED",
}


def classify(service: dict, now: datetime) -> str:
    status = str(service.get("status", "UNKNOWN")).lower()
    mode = str(service.get("monitoring_mode", "CONTINUOUS")).upper()
    if status in BAD_SERVICE_STATES:
        return "RECOVERY_REQUIRED"
    if mode == "NOT_CONNECTED":
        return "NOT_CONNECTED"
    if mode in {"ON_DEMAND", "EVENT_DRIVEN"}:
        if status == "healthy":
            return "HEALTHY"
        return "READY"
    if mode == "DERIVED":
        return "EVIDENCE_PENDING"
    last = parse_time(service.get("last_success_at"))
    target = int(service.get("freshness_target_minutes", 10))
    if last is None:
        return "EVIDENCE_PENDING"
    if now - last > timedelta(minutes=target):
        return "STALE"
    return "HEALTHY"


def derive_ai_heartbeat(root: Path, now: datetime, target_minutes: int) -> dict[str, Any]:
    """Derive agent observability without confusing stale repository evidence with a dead scheduler."""
    rows: list[dict[str, Any]] = []
    for agent in ("AI-A", "AI-B", "AI-C", "AI-D", "AI-E"):
        path = root / f"data/ai/agents/{agent.lower()}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rows.append({
                "agent": agent,
                "heartbeat_at": None,
                "runtime_last_run_time": None,
                "effective_evidence_at": None,
                "state": "MISSING",
            })
            continue

        heartbeat = parse_time(payload.get("heartbeat_at"))
        runtime = payload.get("runtime_evidence") if isinstance(payload.get("runtime_evidence"), dict) else {}
        runtime_last = parse_time(runtime.get("last_run_time"))
        candidates = [value for value in (heartbeat, runtime_last) if value]
        effective = max(candidates) if candidates else None

        if effective is None:
            state = "MISSING"
        elif now - effective > timedelta(minutes=target_minutes):
            state = "EVIDENCE_STALE"
        else:
            state = "FRESH"

        rows.append({
            "agent": agent,
            "heartbeat_at": heartbeat.isoformat() if heartbeat else None,
            "runtime_last_run_time": runtime_last.isoformat() if runtime_last else None,
            "effective_evidence_at": effective.isoformat() if effective else None,
            "state": state,
        })

    missing = [row["agent"] for row in rows if row["state"] == "MISSING"]
    stale = [row["agent"] for row in rows if row["state"] == "EVIDENCE_STALE"]
    if missing:
        classification = "EVIDENCE_PENDING"
    elif stale:
        classification = "OBSERVABILITY_STALE"
    else:
        classification = "HEALTHY"

    times = [parse_time(row["effective_evidence_at"]) for row in rows if row["effective_evidence_at"]]
    times = [value for value in times if value]
    return {
        "classification": classification,
        "evidence_source": "max(agent heartbeat_at, persisted scheduler runtime_evidence.last_run_time)",
        "oldest_evidence_at": min(times).isoformat() if times else None,
        "missing_agents": missing,
        "stale_evidence_agents": stale,
        "interpretation": (
            "OBSERVABILITY_STALE means repository runtime evidence is old; it does not by itself prove "
            "the scheduled automation is disabled or dead. Actual scheduler runtime remains authoritative."
        ),
        "agents": rows,
    }


def is_blocking_handoff(payload: dict[str, Any]) -> bool:
    return str(payload.get("status", "")).upper() in BLOCKING_HANDOFF_STATES


def inspect_handoffs() -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not HANDOFFS.exists():
        return blockers

    for path in sorted(HANDOFFS.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            blockers.append({
                "file": str(path.relative_to(ROOT)),
                "status": "INVALID_HANDOFF_JSON",
                "reason": str(exc),
                "scope": "LOCAL",
            })
            continue

        if is_blocking_handoff(payload):
            blockers.append({
                "file": str(path.relative_to(ROOT)),
                "agent": payload.get("agent"),
                "status": payload.get("status"),
                "applied": payload.get("applied"),
                "scope": payload.get("scope", "LOCAL"),
            })
    return blockers


def progression_policy(blockers: list[dict[str, Any]]) -> dict[str, Any]:
    global_blockers = [b for b in blockers if str(b.get("scope", "LOCAL")).upper() == "GLOBAL_STOP"]
    return {
        "recovery_required": bool(blockers),
        "dependent_progression_allowed": not blockers,
        "independent_work_allowed": True,
        "global_stop_required": bool(global_blockers),
        "global_blockers": global_blockers,
    }


def inspect() -> dict:
    state = json.loads(SERVICES.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    results = []
    for service in state["services"]:
        row = {
            "id": service["id"],
            "classification": classify(service, now),
            "owner": service["owner"],
            "secondary": service["secondary"],
            "emergency_fallback": service["emergency_fallback"],
        }
        if str(service.get("monitoring_mode", "")).upper() == "DERIVED" and service.get("id") == "ai-heartbeat":
            row.update(derive_ai_heartbeat(
                ROOT,
                now,
                int(service.get("freshness_target_minutes", 75)),
            ))
        results.append(row)

    blockers = inspect_handoffs()
    policy = progression_policy(blockers)
    return {
        "checked_at": utc_now(),
        "services": results,
        "blocking_handoffs": blockers,
        **policy,
    }


def write_snapshot(path: Path | None = None) -> dict:
    result = inspect()
    atomic_json_write(path or ROOT / "data/system/health-snapshot.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero only when a GLOBAL_STOP blocker exists",
    )
    args = parser.parse_args()

    result = write_snapshot()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and result["global_stop_required"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
