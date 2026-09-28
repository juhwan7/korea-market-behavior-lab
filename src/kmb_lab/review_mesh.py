from __future__ import annotations

from typing import Any

AGENTS = ("AI-A", "AI-B", "AI-C", "AI-D", "AI-E")
OPEN_RESULTS = {"PENDING", "PASS", "PASS_WITH_NOTES", "FIX_REQUIRED", "REJECT", "UNKNOWN"}


def validate_review_item(item: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not item.get("review_id"):
        errors.append("missing review_id")
    if not item.get("event_type"):
        errors.append("missing event_type")

    reviews = item.get("reviews", {})
    if not isinstance(reviews, dict):
        return errors + ["reviews must be an object"]

    for agent in AGENTS:
        if agent not in reviews:
            errors.append(f"missing reviewer: {agent}")
            continue
        result = reviews[agent].get("result")
        if result not in OPEN_RESULTS:
            errors.append(f"{agent} invalid result")

    return errors


def coverage(item: dict[str, Any]) -> dict[str, Any]:
    reviews = item.get("reviews", {})
    covered: list[str] = []
    unresolved: list[str] = []

    for agent in AGENTS:
        review = reviews.get(agent, {})
        result = review.get("result")
        substitute = review.get("substituted_by")
        if result in {"PASS", "PASS_WITH_NOTES"} or substitute:
            covered.append(agent)
        else:
            unresolved.append(agent)

    return {
        "covered": covered,
        "unresolved": unresolved,
        "all_roles_covered": not unresolved,
    }


def can_close(item: dict[str, Any]) -> bool:
    if validate_review_item(item):
        return False
    reviews = item["reviews"]
    if any(reviews[a].get("result") in {"FIX_REQUIRED", "REJECT", "UNKNOWN", "PENDING"} for a in AGENTS):
        return False
    if not coverage(item)["all_roles_covered"]:
        return False
    evidence = item.get("evidence", {})
    return bool(evidence.get("commit_sha") and evidence.get("actions_result") and evidence.get("expected_state_verified"))
