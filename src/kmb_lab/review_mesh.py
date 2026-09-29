from __future__ import annotations

import re
from typing import Any

AGENTS = ("AI-A", "AI-B", "AI-C", "AI-D", "AI-E")
OPEN_RESULTS = {"PENDING", "PASS", "PASS_WITH_NOTES", "FIX_REQUIRED", "REJECT", "UNKNOWN", "NOT_REQUIRED"}
RISK_REVIEWERS = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 5,
}
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ACTIONS_SUCCESS_RE = re.compile(r"^success:[1-9][0-9]*$")


def required_reviewers(item: dict[str, Any]) -> tuple[str, ...]:
    explicit = item.get("required_reviewers")
    if isinstance(explicit, list) and explicit:
        return tuple(a for a in explicit if a in AGENTS)
    risk = str(item.get("risk_level", "CRITICAL")).upper()
    if risk == "CRITICAL":
        return AGENTS
    owner = str(item.get("owner", "")).upper()
    if owner in AGENTS:
        return (owner,)
    return AGENTS


def validate_review_item(item: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not item.get("review_id"):
        errors.append("missing review_id")
    if not item.get("event_type"):
        errors.append("missing event_type")

    reviews = item.get("reviews", {})
    if not isinstance(reviews, dict):
        return errors + ["reviews must be an object"]

    required = required_reviewers(item)
    if not required:
        errors.append("required_reviewers must contain at least one known agent")
    risk = str(item.get("risk_level", "CRITICAL")).upper()
    minimum = RISK_REVIEWERS.get(risk)
    if minimum is None:
        errors.append("invalid risk_level")
    elif len(required) < minimum:
        errors.append(f"{risk} requires at least {minimum} reviewer(s)")

    for agent in required:
        if agent not in reviews:
            errors.append(f"missing required reviewer: {agent}")
            continue
        result = reviews[agent].get("result")
        if result not in OPEN_RESULTS - {"NOT_REQUIRED"}:
            errors.append(f"{agent} invalid required result")

    for agent, review in reviews.items():
        if agent not in AGENTS:
            errors.append(f"unknown reviewer: {agent}")
            continue
        result = review.get("result")
        if result not in OPEN_RESULTS:
            errors.append(f"{agent} invalid result")
        if agent not in required and result == "PENDING":
            errors.append(f"optional reviewer must not remain PENDING: {agent}")

    return errors


def coverage(item: dict[str, Any]) -> dict[str, Any]:
    reviews = item.get("reviews", {})
    required = required_reviewers(item)
    covered: list[str] = []
    unresolved: list[str] = []

    for agent in required:
        review = reviews.get(agent, {})
        result = review.get("result")
        substitute = review.get("substituted_by")
        if result in {"PASS", "PASS_WITH_NOTES"} or substitute:
            covered.append(agent)
        else:
            unresolved.append(agent)

    return {
        "required": list(required),
        "covered": covered,
        "unresolved": unresolved,
        "all_roles_covered": not unresolved,
    }


def valid_external_evidence(evidence: dict[str, Any]) -> bool:
    commit_sha = evidence.get("commit_sha")
    actions_result = evidence.get("actions_result")
    expected_state_verified = evidence.get("expected_state_verified")
    return bool(
        isinstance(commit_sha, str)
        and COMMIT_SHA_RE.fullmatch(commit_sha)
        and isinstance(actions_result, str)
        and ACTIONS_SUCCESS_RE.fullmatch(actions_result)
        and expected_state_verified is True
    )


def can_close(item: dict[str, Any]) -> bool:
    if validate_review_item(item):
        return False
    reviews = item["reviews"]
    required = required_reviewers(item)
    if any(reviews[a].get("result") in {"FIX_REQUIRED", "REJECT", "UNKNOWN", "PENDING"} for a in required):
        return False
    if not coverage(item)["all_roles_covered"]:
        return False
    return valid_external_evidence(item.get("evidence", {}))
