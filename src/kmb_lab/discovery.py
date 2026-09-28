from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

VALID_EVIDENCE = {"CONFIRMED", "ESTIMATED", "HYPOTHESIS", "UNKNOWN", "REJECTED"}
REQUIRED_FACT_FIELDS = {"metric", "value", "as_of", "source_kind", "source_url"}

@dataclass(frozen=True)
class DiscoveryCandidate:
    candidate_id: str
    title: str
    evidence_state: str
    observed_facts: tuple[dict, ...]
    hypothesis: str
    counter_hypotheses: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    required_primary_sources: tuple[str, ...]

def validate_candidate(candidate: dict) -> list[str]:
    errors: list[str] = []
    if candidate.get("evidence_state") not in VALID_EVIDENCE:
        errors.append("invalid evidence_state")
    if candidate.get("evidence_state") == "CONFIRMED":
        facts = candidate.get("observed_facts", [])
        if not facts:
            errors.append("CONFIRMED requires non-empty observed_facts")
        elif any(f.get("source_kind") != "primary" for f in facts):
            errors.append("CONFIRMED requires primary-source facts")
    for idx, fact in enumerate(candidate.get("observed_facts", [])):
        missing = REQUIRED_FACT_FIELDS - set(fact)
        if missing:
            errors.append(f"observed_facts[{idx}] missing: {sorted(missing)}")
    if not candidate.get("hypothesis"):
        errors.append("hypothesis is required")
    if not candidate.get("counter_hypotheses"):
        errors.append("counter_hypotheses are required")
    if not candidate.get("invalidation_conditions"):
        errors.append("invalidation_conditions are required")
    return errors

def rank_candidate(candidate: dict) -> int:
    # Priority is about research value, never probability that the hypothesis is true.
    score = 0
    score += min(len(candidate.get("observed_facts", [])), 5) * 2
    score += min(len(candidate.get("required_primary_sources", [])), 4)
    score += 2 if candidate.get("market_scope") == "market-wide" else 0
    score += 2 if candidate.get("needs_cross_market_validation") else 0
    return score
