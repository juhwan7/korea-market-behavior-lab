from __future__ import annotations

from typing import Any

WINDOWS = (1, 3, 5, 20)


def _close_map(rows: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in rows:
        date = str(row.get("date") or row.get("localDate") or "")[:10]
        value = row.get("close")
        if date and isinstance(value, (int, float)) and float(value) > 0:
            out[date] = float(value)
    return out


def relative_strength(
    stock_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    *,
    windows: tuple[int, ...] = WINDOWS,
) -> dict[str, Any]:
    """Compare stock return with a benchmark on aligned trading dates.

    This is descriptive relative performance, not a prediction or buy/sell score.
    """
    stock = _close_map(stock_rows)
    benchmark = _close_map(benchmark_rows)
    dates = sorted(set(stock) & set(benchmark))
    if len(dates) < 2:
        return {
            "evidence_state": "UNKNOWN",
            "reason": "종목과 벤치마크의 겹치는 거래일이 부족합니다.",
            "aligned_days": len(dates),
            "windows": {},
        }

    latest = dates[-1]
    metrics: dict[str, Any] = {}
    for window in windows:
        if len(dates) <= window:
            metrics[str(window)] = {
                "stock_return_pct": None,
                "benchmark_return_pct": None,
                "excess_return_pct": None,
                "state": "UNKNOWN",
            }
            continue
        start = dates[-(window + 1)]
        s0, s1 = stock[start], stock[latest]
        b0, b1 = benchmark[start], benchmark[latest]
        stock_ret = (s1 / s0 - 1.0) * 100.0
        bench_ret = (b1 / b0 - 1.0) * 100.0
        excess = stock_ret - bench_ret
        if excess >= 2.0:
            state = "STRONGER"
        elif excess <= -2.0:
            state = "WEAKER"
        else:
            state = "SIMILAR"
        metrics[str(window)] = {
            "start_date": start,
            "end_date": latest,
            "stock_return_pct": round(stock_ret, 2),
            "benchmark_return_pct": round(bench_ret, 2),
            "excess_return_pct": round(excess, 2),
            "state": state,
        }

    usable = [m for m in metrics.values() if isinstance(m.get("excess_return_pct"), (int, float))]
    weighted = []
    weights = {"1": 1.0, "3": 1.5, "5": 2.0, "20": 2.5}
    for key, metric in metrics.items():
        excess = metric.get("excess_return_pct")
        if isinstance(excess, (int, float)):
            weighted.append((float(excess), weights.get(key, 1.0)))
    weighted_excess = (
        sum(value * weight for value, weight in weighted) / sum(weight for _, weight in weighted)
        if weighted
        else None
    )
    if weighted_excess is None:
        overall = "UNKNOWN"
    elif weighted_excess >= 1.5:
        overall = "STRONGER"
    elif weighted_excess <= -1.5:
        overall = "WEAKER"
    else:
        overall = "SIMILAR"

    return {
        "evidence_state": "ESTIMATED" if usable else "UNKNOWN",
        "as_of": latest,
        "aligned_days": len(dates),
        "overall_state": overall,
        "weighted_excess_return_pct": round(weighted_excess, 2) if weighted_excess is not None else None,
        "windows": metrics,
        "method_note": "같은 거래일의 종목·벤치마크 종가 수익률을 1·3·5·20거래일로 비교한 기술적 상대강도입니다. 미래 수익률 확률을 의미하지 않습니다.",
    }
