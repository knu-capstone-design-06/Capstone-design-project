"""Check the deployed backend's existing HTTP and internal AI connection.

Run from backend/: python -m app.modules.connectivity.smoke --base-url URL
The URL may include a proxy prefix such as /backend.
"""

import argparse
from http.client import HTTPException
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class SmokeError(Exception):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def _open(request: Request, timeout: float):
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


def _base_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError as exc:
        raise SmokeError("base URL is invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SmokeError("base URL must be an HTTP(S) origin with an optional path")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise SmokeError("base URL has an invalid port") from exc
    return value.rstrip("/")


def _request_json(
    base: str, path: str, expected_status: int, timeout: float,
    payload: dict | None = None, *, display_path: str | None = None,
) -> dict:
    label = display_path or path
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        base + path,
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    try:
        with _open(request, timeout=timeout) as response:
            status = response.status
            raw = response.read()
    except HTTPError as exc:
        raise SmokeError(f"{label}: HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError, HTTPException) as exc:
        raise SmokeError(f"{label}: connection failed ({type(exc).__name__})") from exc
    if status != expected_status:
        raise SmokeError(f"{label}: expected HTTP {expected_status}, got {status}")
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SmokeError(f"{label}: response is not JSON") from exc
    if not isinstance(result, dict):
        raise SmokeError(f"{label}: response must be a JSON object")
    return result


def run(base_url: str, timeout: float) -> None:
    if not math.isfinite(timeout) or timeout <= 0:
        raise SmokeError("timeout must be a finite number greater than zero")
    base = _base_url(base_url)

    health = _request_json(base, "/health", 200, timeout)
    if health.get("status") != "ok" or health.get("service") != "backend":
        raise SmokeError("/health: unexpected backend response")

    connectivity = _request_json(base, "/api/v1/connectivity", 200, timeout)
    if connectivity.get("backend") != "ok" or connectivity.get("ai_server") != "ok":
        raise SmokeError("/api/v1/connectivity: AI server is not reachable")

    session = _request_json(base, "/api/v1/sessions", 201, timeout, {})
    session_id = session.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise SmokeError("/api/v1/sessions: missing session_id")

    end = datetime.now(timezone.utc)
    start = end - timedelta(seconds=3)
    window = {
        "screen_id": "menu_list",
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "touch": {
            "tap_count": 6,
            "miss_tap_count": 3,
            "repeat_tap_count": 2,
            "back_count": 0,
            "dwell_ms": 3000,
        },
    }
    result = _request_json(
        base, f"/api/v1/sessions/{quote(session_id, safe='')}/features", 200, timeout, window,
        display_path="/api/v1/sessions/{session_id}/features",
    )
    if result.get("session_id") != session_id or result.get("ai_available") is not True:
        raise SmokeError("feature request did not return an available AI result")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    try:
        run(args.base_url, args.timeout)
    except SmokeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: backend health, AI connectivity, session creation and feature delivery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
