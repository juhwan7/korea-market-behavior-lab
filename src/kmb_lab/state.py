from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVIDENCE_STATES = {"CONFIRMED", "ESTIMATED", "HYPOTHESIS", "UNKNOWN", "REJECTED"}
BAD_SERVICE_STATES = {"failed","stopped","paused","suspended","disabled","stale","timeout","cancelled","deployment_failed","data_stale","missing"}

def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z","+00:00"))

def atomic_json_write(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def canonical_is_newer(candidate_ts: str | None, canonical_ts: str | None) -> bool:
    candidate = parse_time(candidate_ts)
    current = parse_time(canonical_ts)
    if candidate is None:
        return False
    return current is None or candidate > current

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
