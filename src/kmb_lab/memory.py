from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_MEMORY_PATHS = [
    "data/ai/CURRENT_BRIEFING.md",
    "data/ai/shared-state.json",
    "data/ai/task-board.json",
    "data/ai/recovery-queue.json",
    "data/ai/writer-lease.json",
    "data/ai/events.jsonl",
    "data/ai/decisions.jsonl",
    "data/ai/lessons-learned.jsonl",
    "data/ai/failed-attempts.jsonl",
    "data/ai/successful-patterns.jsonl",
    "data/ai/agents/ai-a.json",
    "data/ai/agents/ai-b.json",
    "data/ai/agents/ai-c.json",
    "data/ai/agents/ai-d.json",
    "data/ai/agents/ai-e.json",
]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def validate_jsonl(path: Path, *, root: Path | None = None) -> list[str]:
    base = root or ROOT
    errors: list[str] = []
    label = _display_path(path, base)
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{label}:{lineno}: {exc.msg}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{label}:{lineno}: JSONL entry must be an object")
    return errors


def validate_shared_memory(root: Path | None = None) -> list[str]:
    base = root or ROOT
    errors: list[str] = []

    for rel in REQUIRED_MEMORY_PATHS:
        path = base / rel
        if not path.is_file():
            errors.append(f"missing shared-memory file: {rel}")

    task_path = base / "data/ai/task-board.json"
    if task_path.is_file():
        payload = _load_json(task_path)
        ids = [task.get("task_id") for task in payload.get("tasks", [])]
        if any(not task_id for task_id in ids):
            errors.append("task-board contains task without task_id")
        if len(ids) != len(set(ids)):
            errors.append("task-board contains duplicate task_id")

    lease_path = base / "data/ai/writer-lease.json"
    if lease_path.is_file():
        lease = _load_json(lease_path)
        if lease.get("role_order") != ["AI-D", "AI-E", "AI-B"]:
            errors.append("writer lease role_order must be AI-D, AI-E, AI-B")
        status = lease.get("status")
        if status not in {"FREE", "HELD"}:
            errors.append("writer lease status must be FREE or HELD")
        if status == "HELD" and not lease.get("writer"):
            errors.append("HELD writer lease requires writer")

    for rel in REQUIRED_MEMORY_PATHS:
        if rel.endswith(".jsonl"):
            path = base / rel
            if path.is_file():
                errors.extend(validate_jsonl(path, root=base))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    errors = validate_shared_memory()
    print(json.dumps({"errors": errors, "ok": not errors}, ensure_ascii=False, indent=2))
    if args.strict and errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
