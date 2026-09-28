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
    if status in BAD_SERVICE_STATES:
        return "RECOVERY_REQUIRED"
    last = parse_time(service.get("last_success_at"))
    target = int(service.get("freshness_target_minutes", 10))
    if last is None:
        return "UNINITIALIZED"
    if now - last > timedelta(minutes=target):
        return "STALE"
    return "HEALTHY"


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
        results.append({
            "id": service["id"],
            "classification": classify(service, now),
            "owner": service["owner"],
            "secondary": service["secondary"],
            "emergency_fallback": service["emergency_fallback"],
        })

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
