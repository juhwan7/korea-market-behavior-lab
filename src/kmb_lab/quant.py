from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .sources import validate_observation_provenance

PRIMARY = "primary"
CONFIRMED = "CONFIRMED"
ESTIMATED = "ESTIMATED"
UNKNOWN = "UNKNOWN"

SUPPORTED_POSITION_MODELS = {
    "price_absorption",
    "turnover_retention",
    "relative_strength_accumulation",
    "breakout_cost",
    "volume_profile",
}


def validate_quant_candidate(candidate: dict[str, Any]) -> list[str]:
    """Return reasons a discovery candidate cannot be used as confirmed quant input."""
    errors: list[str] = []
    if candidate.get("evidence_state") != CONFIRMED:
        errors.append("quant input requires CONFIRMED evidence_state")

    facts = candidate.get("observed_facts") or []
    if not facts:
        errors.append("quant input requires non-empty observed_facts")
    else:
        for idx, fact in enumerate(facts):
            if fact.get("source_kind") != PRIMARY:
                errors.append("quant input requires primary-source observed_facts")
            for error in validate_observation_provenance(fact):
                errors.append(f"observed_facts[{idx}] provenance: {error}")

    return errors


def model_range(model: str, low: float, high: float, *, confidence: str = "low") -> dict[str, Any]:
    """Create one independent model result without converting turnover into ownership."""
    if model not in SUPPORTED_POSITION_MODELS:
        raise ValueError(f"unsupported model: {model}")
    if low < 0 or high < 0 or low > high:
        raise ValueError("range must satisfy 0 <= low <= high")
    return {"model": model, "evidence_state": ESTIMATED, "range": {"low": low, "high": high}, "confidence": confidence}


def reconcile_model_ranges(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Preserve disagreement. Only expose an overlap range when every model overlaps."""
    if not results:
        return {"evidence_state": UNKNOWN, "agreement": "NO_MODELS", "consensus_range": None, "models": []}
    lows = [float(item["range"]["low"]) for item in results]
    highs = [float(item["range"]["high"]) for item in results]
    overlap_low, overlap_high = max(lows), min(highs)
    if overlap_low <= overlap_high:
        return {"evidence_state": ESTIMATED, "agreement": "OVERLAP", "consensus_range": {"low": overlap_low, "high": overlap_high}, "models": results}
    return {"evidence_state": ESTIMATED, "agreement": "CONFLICT", "consensus_range": None, "models": results}


def estimate_residual_position(prior_range: dict[str, float], added_range: dict[str, float], distributed_range: dict[str, float]) -> dict[str, Any]:
    """Interval arithmetic for a virtual residual position; never represents a real account."""
    low = max(0.0, float(prior_range["low"]) + float(added_range["low"]) - float(distributed_range["high"]))
    high = max(0.0, float(prior_range["high"]) + float(added_range["high"]) - float(distributed_range["low"]))
    if low > high:
        low = high
    return {"evidence_state": ESTIMATED, "label": "virtual_position_model", "residual_range": {"low": low, "high": high}}


def conditional_probability(success_count: int, sample_count: int, *, mfe: float | None = None, mae: float | None = None, fees_bps: float | None = None, slippage_bps: float | None = None, regime: str | None = None) -> dict[str, Any]:
    """Return UNKNOWN when no real sample exists instead of inventing a probability."""
    if sample_count <= 0:
        return {"evidence_state": UNKNOWN, "probability": None, "sample_count": 0, "reason": "no validated historical sample"}
    if success_count < 0 or success_count > sample_count:
        raise ValueError("success_count must be between 0 and sample_count")
    return {"evidence_state": ESTIMATED, "probability": success_count / sample_count, "success_count": success_count, "sample_count": sample_count, "mfe": mfe, "mae": mae, "fees_bps": fees_bps, "slippage_bps": slippage_bps, "regime": regime}
