from __future__ import annotations

import math
from typing import Any


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _avg(values: list[float | None]) -> float | None:
    usable = [float(v) for v in values if isinstance(v, (int, float))]
    return sum(usable) / len(usable) if usable else None


def breadth_score(breadth: dict[str, Any] | None) -> float | None:
    if not breadth:
        return None
    adv = float(breadth.get("advance") or 0) + float(breadth.get("upper") or 0)
    dec = float(breadth.get("decline") or 0) + float(breadth.get("lower") or 0)
    flat = float(breadth.get("flat") or 0)
    total = adv + dec + flat
    return adv / total * 100.0 if total > 0 else None


def market_strength(
    *,
    indices: dict[str, Any],
    breadth: dict[str, Any],
    flows: dict[str, Any] | None = None,
    program_net_100m_krw: float | None = None,
    turnover_ratio: float | None = None,
    sector_breadth: dict[str, Any] | None = None,
    size_participation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    price_changes = [((indices.get(code) or {}).get("change_pct")) for code in ("KOSPI", "KOSDAQ")]
    avg_change = _avg(price_changes)
    price = _clip(50 + avg_change * 12) if avg_change is not None else None
    b_scores = [breadth_score(breadth.get(code)) for code in ("KOSPI", "KOSDAQ")]
    bscore = _avg(b_scores)

    foreign_values: list[float] = []
    if flows:
        for market in ("KOSPI", "KOSDAQ"):
            value = ((((flows.get("markets") or {}).get(market) or {}).get("foreign") or {}).get("net_100m_krw"))
            if isinstance(value, (int, float)):
                foreign_values.append(float(value))
    foreign_net = sum(foreign_values) if foreign_values else None
    foreign = _clip(50 + 42 * math.tanh(foreign_net / 5000.0)) if foreign_net is not None else None
    program = _clip(50 + 42 * math.tanh(float(program_net_100m_krw) / 5000.0)) if isinstance(program_net_100m_krw, (int, float)) else None
    turnover = _clip(50 + (float(turnover_ratio) - 1.0) * 25) if isinstance(turnover_ratio, (int, float)) else None
    sector_share = (sector_breadth or {}).get("positive_directional_share")
    sector = _clip(float(sector_share) * 100.0) if isinstance(sector_share, (int, float)) else None

    components = {
        "price": price,
        "breadth": bscore,
        "turnover": turnover,
        "foreign_flow": foreign,
        "program": program,
        "sector_breadth": sector,
    }
    available = [v for v in components.values() if isinstance(v, (int, float))]
    composite = sum(available) / len(available) if len(available) >= 2 else None
    illusion: list[dict[str, str]] = []
    for code in ("KOSPI", "KOSDAQ"):
        change = (indices.get(code) or {}).get("change_pct")
        bs = breadth_score(breadth.get(code))
        if isinstance(change, (int, float)) and bs is not None:
            if change > 0.15 and bs < 40:
                illusion.append({"market": code, "type": "INDEX_UP_INTERNAL_WEAK", "explanation": "지수는 상승하지만 상승 종목 비중이 낮아 지수 강세가 시장 전체 강세를 뜻하지 않을 수 있습니다."})
            elif change < -0.15 and bs > 60:
                illusion.append({"market": code, "type": "INDEX_DOWN_INTERNAL_RESILIENT", "explanation": "지수는 하락하지만 상승 종목 비중이 높아 대형주 집중 하락 가능성을 함께 확인해야 합니다."})
    size_scores: dict[str, float | None] = {"large_proxy": None, "mid_proxy": None, "small_proxy": None}
    for segment in size_scores:
        values: list[float] = []
        for market in ("KOSPI", "KOSDAQ"):
            row = (((size_participation or {}).get(market) or {}).get("size_participation") or {})
            value = (((row.get("segments") or {}).get(segment) or {}).get("advance_share"))
            if isinstance(value, (int, float)):
                values.append(float(value) * 100.0)
        size_scores[segment] = _avg(values)

    return {
        "evidence_state": "ESTIMATED" if composite is not None else "UNKNOWN",
        "composite": round(composite, 1) if composite is not None else None,
        "coverage": {"available": len(available), "total": len(components)},
        "components": {k: (round(v, 1) if isinstance(v, (int, float)) else None) for k, v in components.items()},
        "size_participation": {k: (round(v, 1) if isinstance(v, (int, float)) else None) for k, v in size_scores.items()},
        "index_illusion": illusion,
        "method_note": "가용한 가격·시장폭·수급·프로그램·거래대금·업종확산 축을 분리해 표시합니다. 규모별 값은 시총순위 프록시로 별도 표시하며 합성점수에 중복 가중하지 않습니다.",
    }
