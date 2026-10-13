import json
import re
import unittest
from http.client import HTTPException
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from app.modules.connectivity.smoke import _NoRedirect, _request_json, SmokeError, run


class _Response:
    def __init__(self, status: int, payload: dict):
        self.status = status
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class SmokeTests(unittest.TestCase):
    def test_checks_existing_api_through_proxy_prefix(self):
        requests = []
        responses = [
            _Response(200, {"status": "ok", "service": "backend"}),
            _Response(200, {"backend": "ok", "ai_server": "ok"}),
            _Response(201, {"session_id": "sample-id"}),
            _Response(200, {"session_id": "sample-id", "ai_available": True}),
        ]

        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 3.0)
            requests.append(request)
            return responses.pop(0)

        with patch("app.modules.connectivity.smoke._open", side_effect=fake_urlopen):
            run("https://example.test/backend/", 3.0)

        self.assertFalse(responses)
        self.assertEqual(
            [request.full_url for request in requests],
            [
                "https://example.test/backend/health",
                "https://example.test/backend/api/v1/connectivity",
                "https://example.test/backend/api/v1/sessions",
                "https://example.test/backend/api/v1/sessions/sample-id/features",
            ],
        )
        self.assertEqual([request.get_method() for request in requests],
                         ["GET", "GET", "POST", "POST"])
        feature_window = json.loads(requests[-1].data)
        self.assertGreater(feature_window["window_end"], feature_window["window_start"])
        self.assertEqual(feature_window["touch"]["tap_count"], 6)

    def test_rejects_unavailable_ai_before_creating_session(self):
        responses = [
            _Response(200, {"status": "ok", "service": "backend"}),
            _Response(200, {"backend": "ok", "ai_server": "unreachable"}),
        ]
        with patch("app.modules.connectivity.smoke._open",
                   side_effect=lambda *_args, **_kwargs: responses.pop(0)):
            with self.assertRaisesRegex(SmokeError, "AI server is not reachable"):
                run("http://127.0.0.1:8000", 5.0)
        self.assertFalse(responses)

    def test_feature_failure_does_not_print_session_id(self):
        responses = [
            _Response(200, {"status": "ok", "service": "backend"}),
            _Response(200, {"backend": "ok", "ai_server": "ok"}),
            _Response(201, {"session_id": "private-session-id"}),
        ]

        def fake_open(*_args, **_kwargs):
            if responses:
                return responses.pop(0)
            raise URLError("connection lost")

        with patch("app.modules.connectivity.smoke._open", side_effect=fake_open):
            with self.assertRaises(SmokeError) as caught:
                run("https://example.test", 3.0)
        self.assertIn("{session_id}/features", str(caught.exception))
        self.assertNotIn("private-session-id", str(caught.exception))

    def test_request_failures_are_single_line_smoke_errors(self):
        failures = [
            (HTTPError("https://example.test/health", 502, "Bad Gateway", {}, None), "HTTP 502"),
            (TimeoutError("timed out"), "connection failed (TimeoutError)"),
            (HTTPException("disconnected"), "connection failed (HTTPException)"),
        ]
        for error, expected in failures:
            with self.subTest(error=type(error).__name__):
                with patch("app.modules.connectivity.smoke._open", side_effect=error):
                    with self.assertRaisesRegex(SmokeError, re.escape(expected)):
                        _request_json("https://example.test", "/health", 200, 3.0)

    def test_non_json_and_unexpected_status_fail_cleanly(self):
        with patch("app.modules.connectivity.smoke._open", return_value=_Response(201, {})):
            with self.assertRaisesRegex(SmokeError, "expected HTTP 200, got 201"):
                _request_json("https://example.test", "/health", 200, 3.0)
        response = _Response(200, {})
        response.read = lambda: b"not json"
        with patch("app.modules.connectivity.smoke._open", return_value=response):
            with self.assertRaisesRegex(SmokeError, "response is not JSON"):
                _request_json("https://example.test", "/health", 200, 3.0)

    def test_redirects_are_not_followed(self):
        request = Request("https://example.test/api/v1/sessions", method="POST", data=b"{}")
        self.assertIsNone(_NoRedirect().redirect_request(
            request, None, 302, "Found", {}, "https://example.test/elsewhere"
        ))


if __name__ == "__main__":
    unittest.main()
