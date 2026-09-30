from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from kmb_lab.http_client import request_json

BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
SOURCE_ID = "yahoo-finance-chart"
SOURCE_KIND = "secondary"

SYMBOLS = {
    "NASDAQ100_FUTURES": "NQ=F",
    "SP500_FUTURES": "ES=F",
    "DOW_FUTURES": "YM=F",
    "SOX": "^SOX",
    "VIX": "^VIX",
    "DOLLAR_INDEX": "DX-Y.NYB",
    "USD_KRW": "KRW=X",
    "WTI": "CL=F",
    "BRENT": "BZ=F",
    "GOLD": "GC=F",
}


def fetch_chart(symbol: str, *, range_: str = "5d", interval: str = "5m") -> dict[str, Any]:
    return request_json(
        f"{BASE}/{quote(symbol, safe='=^.-')}",
        params={"range": range_, "interval": interval, "events": "div,splits"},
    )


def normalize_quote(payload: Any, symbol: str) -> dict[str, Any]:
    result = (((payload or {}).get("chart") or {}).get("result") or [None])[0] if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise ValueError(f"Yahoo chart missing result for {symbol}")
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quote_rows = (((result.get("indicators") or {}).get("quote") or [{}])[0])
    closes = quote_rows.get("close") or []
    latest_price = meta.get("regularMarketPrice")
    if latest_price is None:
        latest_price = next((v for v in reversed(closes) if v is not None), None)
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    change = latest_price - prev if isinstance(latest_price, (int, float)) and isinstance(prev, (int, float)) else None
    change_pct = (change / prev * 100.0) if change is not None and prev not in (None, 0) else None
    ts = meta.get("regularMarketTime") or (timestamps[-1] if timestamps else None)
    as_of = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z") if isinstance(ts, (int, float)) else None
    return {
        "symbol": symbol,
        "price": latest_price,
        "previous_close": prev,
        "change": change,
        "change_pct": change_pct,
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName") or meta.get("fullExchangeName"),
        "market_state": meta.get("marketState"),
        "as_of": as_of,
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_id": SOURCE_ID,
        "source_kind": SOURCE_KIND,
        "source_url": f"{BASE}/{symbol}",
    }


def fetch_global_board() -> dict[str, Any]:
    board: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for label, symbol in SYMBOLS.items():
        try:
            board[label] = normalize_quote(fetch_chart(symbol), symbol)
        except Exception as exc:
            errors[label] = str(exc)
    return {"quotes": board, "errors": errors}
