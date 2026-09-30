from __future__ import annotations

import math
from typing import Any


def _clip(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _bar(row: dict[str, Any]) -> dict[str, float]:
    close = float(row["close"]); open_ = float(row.get("open", close)); high = float(row.get("high", close)); low = float(row.get("low", close)); volume = float(row.get("volume", 0))
    high = max(high, open_, close); low = min(low, open_, close)
    return {"open": open_, "high": high, "low": low, "close": close, "volume": max(0.0, volume)}


def _close_position(b: dict[str, float]) -> float:
    span = max(b["high"] - b["low"], 1e-9)
    return _clip((b["close"] - b["low"]) / span, 0.0, 1.0)


def _upper_wick_ratio(b: dict[str, float]) -> float:
    span = max(b["high"] - b["low"], 1e-9)
    return _clip((b["high"] - max(b["open"], b["close"])) / span, 0.0, 1.0)


def _volume_profile(bars: list[dict[str, float]], buckets: int = 12) -> dict[str, Any]:
    lows = [b["low"] for b in bars]; highs = [b["high"] for b in bars]
    lo, hi = min(lows), max(highs)
    if hi <= lo:
        return {"poc": bars[-1]["close"], "value_area_low": lo, "value_area_high": hi}
    volumes = [0.0] * buckets
    for b in bars:
        price = (b["high"] + b["low"] + b["close"]) / 3.0
        idx = min(buckets - 1, int((price - lo) / (hi - lo) * buckets))
        volumes[idx] += b["volume"]
    total = sum(volumes)
    centers = [lo + (i + 0.5) * (hi - lo) / buckets for i in range(buckets)]
    poc_idx = max(range(buckets), key=lambda i: volumes[i])
    weighted = sorted(zip(centers, volumes))
    cumulative = 0.0; q25 = lo; q75 = hi
    for price, vol in weighted:
        cumulative += vol
        if total and cumulative >= total * .25 and q25 == lo: q25 = price
        if total and cumulative >= total * .75:
            q75 = price; break
    return {"poc": centers[poc_idx], "value_area_low": q25, "value_area_high": q75}


def analyze_smart_money(rows: list[dict[str, Any]], *, index_returns: list[float] | None = None) -> dict[str, Any]:
    if len(rows) < 20:
        return {"evidence_state": "UNKNOWN", "reason": "최소 20개 일봉이 필요합니다.", "sample_count": len(rows)}
    bars = [_bar(row) for row in rows[-80:]]
    closes = [b["close"] for b in bars]; vols = [b["volume"] for b in bars]
    prev_vol = _mean(vols[-25:-5]) or _mean(vols[:-5]) or 1.0
    recent_vol_ratio = _mean(vols[-5:]) / max(prev_vol, 1e-9)
    recent_ret = closes[-1] / closes[-6] - 1 if len(closes) >= 6 and closes[-6] else 0.0
    prior_high = max(b["high"] for b in bars[-25:-5]) if len(bars) >= 25 else max(b["high"] for b in bars[:-5])
    breakout = closes[-1] > prior_high

    absorption_hits = 0; distribution_hits = 0
    for b in bars[-10:]:
        vr = b["volume"] / max(prev_vol, 1e-9)
        cp = _close_position(b)
        ret = b["close"] / b["open"] - 1 if b["open"] else 0.0
        if vr >= 1.2 and cp >= .58 and ret > -.02:
            absorption_hits += 1
        if vr >= 1.2 and (cp <= .35 or _upper_wick_ratio(b) >= .42):
            distribution_hits += 1

    profile = _volume_profile(bars[-40:])
    cost_low, cost_high = profile["value_area_low"], profile["value_area_high"]
    absorption_score = _clip(absorption_hits / 4 * 100 + max(0.0, recent_ret) * 180)
    distribution_score = _clip(distribution_hits / 4 * 100 + max(0.0, recent_vol_ratio - 1.8) * 20)

    rs_score = 50.0
    if index_returns:
        stock_daily = [(closes[i] / closes[i-1] - 1) for i in range(max(1, len(closes)-len(index_returns)), len(closes))]
        comparable = min(len(stock_daily), len(index_returns))
        if comparable:
            excess = sum(stock_daily[-comparable:]) - sum(index_returns[-comparable:])
            rs_score = _clip(50 + excess * 250)
    external_demand = _clip(.45 * rs_score + .35 * _clip(50 + recent_ret * 350) + .20 * _clip(recent_vol_ratio * 35))

    net = absorption_score - distribution_score
    baseline_remaining = _clip(50 + net * .45) / 100.0
    uncertainty = .18 if len(bars) >= 60 else .28
    remaining_range = {
        "low": round(max(0.0, baseline_remaining - uncertainty), 3),
        "high": round(min(1.0, baseline_remaining + uncertainty), 3),
        "unit": "fraction_of_virtual_inventory_proxy",
    }
    model_votes = [absorption_score > 55, recent_ret > 0, rs_score > 55, breakout, distribution_score < 45]
    agreement = sum(bool(v) for v in model_votes)
    confidence = "medium" if len(bars) >= 40 and agreement in {1,2,3,4} else "low"
    if len(bars) >= 60 and agreement in {0,5}:
        confidence = "medium"

    if distribution_score >= 65 and distribution_score > absorption_score + 15:
        state = "DISTRIBUTION_RISK"
    elif breakout and absorption_score >= 55:
        state = "BREAKOUT_WITH_DEMAND"
    elif absorption_score >= 60 and absorption_score > distribution_score + 10:
        state = "ACCUMULATION_OR_ABSORPTION_CANDIDATE"
    else:
        state = "MIXED_OR_NEUTRAL"

    incentive = _clip(remaining_range["high"] * 45 + external_demand * .35 + (100-distribution_score) * .20)
    return {
        "evidence_state": "ESTIMATED",
        "state": state,
        "confidence": confidence,
        "sample_count": len(bars),
        "virtual_cost_range": {"low": round(cost_low, 2), "high": round(cost_high, 2), "poc": round(profile["poc"], 2), "label": "volume_profile_reference_not_account_cost"},
        "remaining_inventory_proxy": remaining_range,
        "accumulation_absorption_score": round(absorption_score, 1),
        "distribution_risk_score": round(distribution_score, 1),
        "external_demand_score": round(external_demand, 1),
        "additional_upside_incentive_proxy": round(incentive, 1),
        "recent_volume_ratio": round(recent_vol_ratio, 2),
        "recent_5d_return_pct": round(recent_ret * 100, 2),
        "breakout": breakout,
        "model_agreement": f"{agreement}/5",
        "counter_hypotheses": [
            "대량 거래는 동일 물량의 반복 회전일 수 있어 실제 보유량과 같지 않습니다.",
            "고점 거래 증가는 분배가 아니라 새로운 외부수요의 흡수일 수 있습니다.",
            "공개 일봉만으로 특정 주체의 실제 계좌·평단·의도를 식별할 수 없습니다.",
        ],
        "method_note": "가격 복원력·거래량 상대치·돌파·상대강도·거래량 프로파일을 독립적으로 결합한 가상 포지션 프록시입니다.",
    }


BULLISH_STATES = {"ACCUMULATION_OR_ABSORPTION_CANDIDATE", "BREAKOUT_WITH_DEMAND"}
BEARISH_STATES = {"DISTRIBUTION_RISK"}


def _benchmark_regime(date: str, benchmark_rows: list[dict[str, Any]] | None) -> str:
    if not benchmark_rows:
        return "UNKNOWN"
    closes = {
        str(row.get("date") or "")[:10]: float(row["close"])
        for row in benchmark_rows
        if row.get("date") and isinstance(row.get("close"), (int, float)) and float(row["close"]) > 0
    }
    dates = sorted(d for d in closes if d <= date)
    if len(dates) < 6:
        return "UNKNOWN"
    end, start = dates[-1], dates[-6]
    ret = closes[end] / closes[start] - 1.0
    if ret >= 0.02:
        return "UP"
    if ret <= -0.02:
        return "DOWN"
    return "SIDEWAYS"


def backtest_smart_money(
    rows: list[dict[str, Any]],
    *,
    benchmark_rows: list[dict[str, Any]] | None = None,
    forward_days: int = 5,
    min_history: int = 40,
    fees_bps: float = 15.0,
    slippage_bps: float = 20.0,
) -> dict[str, Any]:
    """Walk-forward validation of directional state labels.

    This evaluates only historically emitted directional states. It does not
    turn the result into a future probability. Costs are explicit assumptions.
    """
    if len(rows) < min_history + forward_days:
        return {
            "evidence_state": "UNKNOWN",
            "sample_count": 0,
            "reason": "walk-forward 평가에 필요한 과거 일봉이 부족합니다.",
        }

    events: list[dict[str, Any]] = []
    cost_pct = (float(fees_bps) + float(slippage_bps)) / 100.0
    for end in range(min_history - 1, len(rows) - forward_days):
        history = rows[: end + 1]
        signal = analyze_smart_money(history)
        state = signal.get("state")
        direction = 1 if state in BULLISH_STATES else -1 if state in BEARISH_STATES else 0
        if not direction:
            continue
        entry = float(rows[end]["close"])
        future = rows[end + 1 : end + 1 + forward_days]
        if entry <= 0 or len(future) < forward_days:
            continue
        exit_close = float(future[-1]["close"])
        highs = [float(row.get("high", row["close"])) for row in future]
        lows = [float(row.get("low", row["close"])) for row in future]
        if direction > 0:
            gross = (exit_close / entry - 1.0) * 100.0
            mfe = (max(highs) / entry - 1.0) * 100.0
            mae = (min(lows) / entry - 1.0) * 100.0
        else:
            gross = (entry / exit_close - 1.0) * 100.0
            mfe = (entry / min(lows) - 1.0) * 100.0
            mae = (entry / max(highs) - 1.0) * 100.0
        net = gross - cost_pct
        date = str(rows[end].get("date") or "")[:10]
        events.append({
            "date": date,
            "state": state,
            "direction": "BULLISH" if direction > 0 else "BEARISH",
            "regime": _benchmark_regime(date, benchmark_rows),
            "forward_days": forward_days,
            "gross_directional_return_pct": round(gross, 3),
            "net_after_cost_pct": round(net, 3),
            "mfe_pct": round(mfe, 3),
            "mae_pct": round(mae, 3),
            "gross_success": gross > 0,
            "net_success": net > 0,
        })

    if not events:
        return {
            "evidence_state": "UNKNOWN",
            "sample_count": 0,
            "reason": "과거 구간에서 검증할 방향성 상태가 발생하지 않았습니다.",
        }

    def summary(group: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(group)
        return {
            "sample_count": n,
            "gross_success_rate": round(sum(bool(e["gross_success"]) for e in group) / n, 4),
            "net_success_rate": round(sum(bool(e["net_success"]) for e in group) / n, 4),
            "avg_gross_directional_return_pct": round(_mean([float(e["gross_directional_return_pct"]) for e in group]), 3),
            "avg_net_after_cost_pct": round(_mean([float(e["net_after_cost_pct"]) for e in group]), 3),
            "avg_mfe_pct": round(_mean([float(e["mfe_pct"]) for e in group]), 3),
            "avg_mae_pct": round(_mean([float(e["mae_pct"]) for e in group]), 3),
            "worst_mae_pct": round(min(float(e["mae_pct"]) for e in group), 3),
        }

    by_state = {
        state: summary([e for e in events if e["state"] == state])
        for state in sorted({str(e["state"]) for e in events})
    }
    by_regime = {
        regime: summary([e for e in events if e["regime"] == regime])
        for regime in ("UP", "SIDEWAYS", "DOWN", "UNKNOWN")
        if any(e["regime"] == regime for e in events)
    }
    return {
        "evidence_state": "ESTIMATED",
        "sample_count": len(events),
        "forward_days": forward_days,
        "cost_assumption": {
            "evidence_state": "ASSUMPTION",
            "fees_bps": fees_bps,
            "slippage_bps": slippage_bps,
            "round_trip_total_bps": fees_bps + slippage_bps,
        },
        "overall": summary(events),
        "by_state": by_state,
        "by_regime": by_regime,
        "events": events[-80:],
        "method_note": "각 과거 시점에서 당시까지의 데이터만 사용해 상태를 재계산한 walk-forward 검증입니다. 성공률은 과거 방향 일치율이며 미래 확률이 아닙니다.",
    }
