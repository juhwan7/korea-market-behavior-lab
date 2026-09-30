from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def _window_change(points: list[tuple[dict[str, Any], float]], minutes: int) -> tuple[float | None, float | None]:
    """Return cumulative-flow change and average velocity inside a recent window."""
    if len(points) < 2:
        return None, None
    latest_row, latest_value = points[-1]
    latest_at = _time(latest_row.get("at"))
    if latest_at is None:
        return None, None
    cutoff = latest_at - timedelta(minutes=minutes)
    candidates = [(row, value) for row, value in points[:-1] if (_time(row.get("at")) or latest_at) >= cutoff]
    if not candidates:
        return None, None
    first_row, first_value = candidates[0]
    first_at = _time(first_row.get("at"))
    if first_at is None:
        return None, None
    elapsed = (latest_at - first_at).total_seconds() / 60.0
    if elapsed <= 0:
        return None, None
    change = latest_value - first_value
    return round(change, 2), round(change / elapsed, 3)


def _session_change(points: list[tuple[dict[str, Any], float]]) -> float | None:
    """Compare with the first valid observation from the latest observation's local date."""
    if len(points) < 2:
        return None
    latest_at = _time(points[-1][0].get("at"))
    if latest_at is None:
        return None
    same_day = []
    for row, value in points:
        at = _time(row.get("at"))
        if at is not None and at.astimezone(latest_at.tzinfo).date() == latest_at.date():
            same_day.append((row, value))
    if len(same_day) < 2:
        return None
    return round(same_day[-1][1] - same_day[0][1], 2)


def _pace_state(net: float | None, recent_velocity: float | None) -> str:
    if net is None or recent_velocity is None:
        return "UNKNOWN"
    if net < 0:
        if recent_velocity < 0:
            return "NET_SELLING_WORSENING"
        if recent_velocity > 0:
            return "NET_SELLING_EASING"
        return "NET_SELLING_STABLE"
    if net > 0:
        if recent_velocity > 0:
            return "NET_BUYING_STRENGTHENING"
        if recent_velocity < 0:
            return "NET_BUYING_EASING"
        return "NET_BUYING_STABLE"
    return "NEUTRAL"


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
                    v1 = (p1[1] - p0[1]) / max((t1 - t0).total_seconds() / 60.0, 1.0)
                    v2 = (p2[1] - p1[1]) / max((t2 - t1).total_seconds() / 60.0, 1.0)
                    acceleration = v2 - v1

            window_changes: dict[str, float | None] = {}
            window_velocities: dict[str, float | None] = {}
            for window in (10, 30, 60):
                change, avg_velocity = _window_change(points, window)
                window_changes[f"{window}m"] = change
                window_velocities[f"{window}m"] = avg_velocity
            window_changes["session"] = _session_change(points)
            recent_velocity = window_velocities.get("30m")
            if recent_velocity is None and isinstance(velocity, (int, float)):
                recent_velocity = round(float(velocity), 3)

            market_out[investor] = {
                "net_100m_krw": current,
                "velocity_100m_krw_per_min": round(velocity, 3) if isinstance(velocity, (int, float)) else None,
                "acceleration": round(acceleration, 3) if isinstance(acceleration, (int, float)) else None,
                "reversal": reversal,
                "window_changes_100m_krw": window_changes,
                "window_velocity_100m_krw_per_min": window_velocities,
                "pace_state": _pace_state(current, recent_velocity),
            }
        result["markets"][market] = market_out

    result["method_note"] = (
        "순매수 누적값의 최근 10·30·60분 변화와 장중 첫 관측 대비 변화를 계산합니다. "
        "pace_state는 누적 순매수 부호와 최근 30분 변화 방향을 설명하며 매수·매도 주체의 의도를 확정하지 않습니다."
    )
    return result
