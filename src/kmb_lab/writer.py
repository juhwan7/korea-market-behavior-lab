from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

ALLOWED_TARGET_PREFIXES = ("src/", "tests/", "docs/", "data/", "web/")
FORBIDDEN_TARGET_PREFIXES = (
    ".github/",
    "data/ai/candidates/",
    "data/ai/patches/",
)
REQUIRED_FIELDS = {
    "patch_id",
    "agent",
    "target",
    "candidate_path",
    "change_type",
    "reason",
    "dependencies",
    "tests",
    "rollback",
    "status",
}


def _safe_repo_path(raw: str) -> Path:
    if not isinstance(raw, str) or not raw or raw.startswith("/"):
        raise ValueError("path must be a non-empty repository-relative path")
    path = (ROOT / raw).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError("path escapes repository root") from exc
    return path


def git_blob_sha_bytes(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()


def git_blob_sha(path: Path) -> str:
    return git_blob_sha_bytes(path.read_bytes())


def validate_manifest(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(payload))
    if missing:
        errors.append(f"missing fields: {missing}")
        return errors

    if payload.get("status") != "READY":
        errors.append("status must be READY")

    agent = str(payload.get("agent", "")).lower()
    if agent not in {"ai-a", "ai-b", "ai-c", "ai-d", "ai-e"}:
        errors.append("agent must be AI-A..AI-E")

    target = str(payload.get("target", ""))
    if not target.startswith(ALLOWED_TARGET_PREFIXES):
        errors.append("target is outside allowed prefixes")
    if target.startswith(FORBIDDEN_TARGET_PREFIXES):
        errors.append("target is a protected coordination path")
    if ".." in Path(target).parts:
        errors.append("target must not contain parent traversal")

    candidate = str(payload.get("candidate_path", ""))
    expected_prefix = f"data/ai/candidates/{agent}/"
    if not candidate.startswith(expected_prefix):
        errors.append(f"candidate_path must be inside {expected_prefix}")
    if ".." in Path(candidate).parts:
        errors.append("candidate_path must not contain parent traversal")

    if payload.get("change_type") not in {"create", "modify"}:
        errors.append("change_type must be create or modify")

    if not isinstance(payload.get("tests"), list):
        errors.append("tests must be a list")
    if not isinstance(payload.get("dependencies"), list):
        errors.append("dependencies must be a list")

    return errors


def apply_manifest(manifest_path: str) -> dict[str, str]:
    manifest = _safe_repo_path(manifest_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    errors = validate_manifest(payload)
    if errors:
        raise ValueError("; ".join(errors))

    target = _safe_repo_path(payload["target"])
    candidate = _safe_repo_path(payload["candidate_path"])
    if not candidate.is_file():
        raise FileNotFoundError(f"candidate file missing: {payload['candidate_path']}")

    change_type = payload["change_type"]
    base_sha = payload.get("base_sha")

    if change_type == "create":
        if target.exists():
            raise ValueError("create target already exists")
    else:
        if not target.is_file():
            raise FileNotFoundError(f"modify target missing: {payload['target']}")
        if not isinstance(base_sha, str) or not base_sha:
            raise ValueError("modify requires base_sha")
        actual_sha = git_blob_sha(target)
        if actual_sha != base_sha:
            raise ValueError(f"STALE_SHA expected={base_sha} actual={actual_sha}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(candidate.read_bytes())

    return {
        "patch_id": payload["patch_id"],
        "target": payload["target"],
        "candidate_path": payload["candidate_path"],
        "result": "APPLIED_TO_WORKTREE",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    args = parser.parse_args()
    result = apply_manifest(args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
