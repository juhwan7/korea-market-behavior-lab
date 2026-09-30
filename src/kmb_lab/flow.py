from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

INVESTORS = ("individual", "foreign", "institution")


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _value(snapshot: dict[str, Any], market: str, investor: str) -> float | None:
    value = (((snapshot.get("markets") or {}).get(market) or {}).get("flows_100m_krw") or {}).get(investor)
    return float(value) if isinstance(value, (int, float)) else None


def analyze_flow_history(history: list[dict[str, Any]], *, max_snapshots: int = 300) -> dict[str, Any]:
    valid = [row for row in history if _time(row.get("at"))]
    valid.sort(key=lambda x: _time(x.get("at")) or datetime.min.replace(tzinfo=timezone.utc))
    valid = valid[-max_snapshots:]
    result: dict[str, Any] = {"snapshot_count": len(valid), "markets": {}}
    if not valid:
        return result
    for market in ("KOSPI", "KOSDAQ"):
        market_out: dict[str, Any] = {}
        for investor in INVESTORS:
            points = [(row, _value(row, market, investor)) for row in valid]
            points = [(row, value) for row, value in points if value is not None]
            current = points[-1][1] if points else None
            velocity = acceleration = None
            reversal = False
            if len(points) >= 2:
                a, b = points[-2], points[-1]
                ta, tb = _time(a[0].get("at")), _time(b[0].get("at"))
                minutes = max((tb - ta).total_seconds() / 60.0, 1.0) if ta and tb else None
                velocity = (b[1] - a[1]) / minutes if minutes else None
                reversal = (a[1] < 0 < b[1]) or (a[1] > 0 > b[1])
            if len(points) >= 3:
                p0, p1, p2 = points[-3], points[-2], points[-1]
                t0, t1, t2 = (_time(p[0].get("at")) for p in (p0, p1, p2))
                if t0 and t1 and t2:
                    v1 = (p1[1] - p0[1]) / max((t1 - t0).total_seconds()/60.0, 1.0)
                    v2 = (p2[1] - p1[1]) / max((t2 - t1).total_seconds()/60.0, 1.0)
                    acceleration = v2 - v1
            market_out[investor] = {
                "net_100m_krw": current,
                "velocity_100m_krw_per_min": velocity,
                "acceleration": acceleration,
                "reversal": reversal,
            }
        result["markets"][market] = market_out
    return result
