from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .state import BAD_SERVICE_STATES, atomic_json_write, parse_time, utc_now

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "data/system/services.json"

def classify(service: dict, now: datetime) -> str:
    status = str(service.get("status","UNKNOWN")).lower()
    if status in BAD_SERVICE_STATES:
        return "RECOVERY_REQUIRED"
    last = parse_time(service.get("last_success_at"))
    target = int(service.get("freshness_target_minutes",10))
    if last is None:
        return "UNINITIALIZED"
    if now - last > timedelta(minutes=target):
        return "STALE"
    return "HEALTHY"

def inspect() -> dict:
    state = json.loads(SERVICES.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    results = []
    for service in state["services"]:
        results.append({"id":service["id"],"classification":classify(service,now),"owner":service["owner"],"secondary":service["secondary"],"emergency_fallback":service["emergency_fallback"]})
    return {"checked_at":utc_now(),"services":results}

def write_snapshot(path: Path | None = None) -> dict:
    result = inspect()
    atomic_json_write(path or ROOT / "data/system/health-snapshot.json", result)
    return result

if __name__ == "__main__":
    print(json.dumps(write_snapshot(), ensure_ascii=False, indent=2))
