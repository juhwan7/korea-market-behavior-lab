from __future__ import annotations

from typing import Any

SOURCE_STATES = {"PLANNED", "ADAPTER_READY", "SHADOW", "CONNECTED"}
REQUIRED_PROVENANCE = {"source_id", "source_url", "source_kind", "as_of", "retrieved_at"}


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
        if source.get("status") not in SOURCE_STATES:
            errors.append(f"sources[{idx}] invalid status")
        if source.get("kind") != "primary":
            errors.append(f"sources[{idx}] must be primary")
        if source.get("status") == "CONNECTED":
            if not source.get("adapter"):
                errors.append(f"sources[{idx}] CONNECTED requires adapter")
            if not source.get("validation"):
                errors.append(f"sources[{idx}] CONNECTED requires validation")
    return errors


def validate_observation_provenance(observation: dict[str, Any]) -> list[str]:
    missing = sorted(REQUIRED_PROVENANCE - set(observation))
    return [f"missing provenance fields: {missing}"] if missing else []
