from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KoreaMarketBehaviorLab/1.0; +https://github.com/juhwan7/korea-market-behavior-lab)",
    "Accept": "application/json,text/plain,*/*",
}


class HttpError(RuntimeError):
    pass


def _decode_body(response: Any, raw: bytes) -> str:
    if str(response.headers.get("Content-Encoding", "")).lower() == "gzip":
        raw = gzip.decompress(raw)
    charset = response.headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset)
    except (LookupError, UnicodeDecodeError):
        return raw.decode("utf-8", errors="replace")


def request_text(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    method: str = "GET",
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
    retries: int = 2,
) -> str:
    if params:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
        url += ("&" if "?" in url else "?") + query
    merged = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    body: bytes | None = None
    if json_body is not None:
        body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        merged.setdefault("Content-Type", "application/json")
    last: Exception | None = None
    for attempt in range(max(0, retries) + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=merged, method=method.upper())
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return _decode_body(response, response.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            retryable = not isinstance(exc, urllib.error.HTTPError) or exc.code in {408, 425, 429, 500, 502, 503, 504}
            if attempt >= retries or not retryable:
                break
            time.sleep(min(2.0, 0.35 * (2**attempt)))
    raise HttpError(f"request failed: {url}: {last}")


def request_json(url: str, **kwargs: Any) -> Any:
    text = request_text(url, **kwargs)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HttpError(f"invalid JSON from {url}: {exc}") from exc
