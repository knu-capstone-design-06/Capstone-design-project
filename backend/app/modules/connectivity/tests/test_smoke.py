import json
import unittest
from unittest.mock import patch

from app.modules.connectivity.smoke import SmokeError, run


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

        with patch("app.modules.connectivity.smoke.urlopen", side_effect=fake_urlopen):
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
        with patch("app.modules.connectivity.smoke.urlopen",
                   side_effect=lambda *_args, **_kwargs: responses.pop(0)):
            with self.assertRaisesRegex(SmokeError, "AI server is not reachable"):
                run("http://127.0.0.1:8000", 5.0)
        self.assertFalse(responses)


if __name__ == "__main__":
    unittest.main()
