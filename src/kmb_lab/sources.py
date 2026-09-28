from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

SOURCE_STATES = {"PLANNED", "ADAPTER_READY", "SHADOW", "CONNECTED"}
REQUIRED_PROVENANCE = {"source_id", "source_url", "source_kind", "as_of", "retrieved_at"}
IMPLEMENTED_SOURCE_STATES = {"ADAPTER_READY", "SHADOW", "CONNECTED"}


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        if len(raw) == 10:
            return datetime.combine(date.fromisoformat(raw), datetime.min.time(), tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_source_registry(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()

    for idx, source in enumerate(payload.get("sources", [])):
        source_id = source.get("id")
        if not source_id:
            errors.append(f"sources[{idx}] missing id")
        elif source_id in seen:
            errors.append(f"duplicate source id: {source_id}")
        else:
            seen.add(source_id)

        status = source.get("status")
        if status not in SOURCE_STATES:
            errors.append(f"sources[{idx}] invalid status")

        if source.get("kind") != "primary":
            errors.append(f"sources[{idx}] must be primary")

        # Once a source claims implementation readiness, both executable
        # adapter evidence and validation evidence must exist. PLANNED may
        # intentionally omit them.
        if status in IMPLEMENTED_SOURCE_STATES:
            if not source.get("adapter"):
                errors.append(f"sources[{idx}] {status} requires adapter")
            if not source.get("validation"):
                errors.append(f"sources[{idx}] {status} requires validation")

    return errors


def validate_observation_provenance(
    observation: dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[str]:
    missing = sorted(REQUIRED_PROVENANCE - set(observation))
    if missing:
        return [f"missing provenance fields: {missing}"]

    errors: list[str] = []
    as_of = _parse_datetime(observation.get("as_of"))
    retrieved_at = _parse_datetime(observation.get("retrieved_at"))
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    if as_of is None:
        errors.append("invalid as_of timestamp")
    if retrieved_at is None:
        errors.append("invalid retrieved_at timestamp")

    if as_of is not None and retrieved_at is not None and as_of > retrieved_at:
        errors.append("as_of must not be after retrieved_at")

    if retrieved_at is not None and retrieved_at > current:
        errors.append("retrieved_at must not be in the future")

    return errors
