import asyncio
from copy import deepcopy
from datetime import datetime
import json
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.common.config.settings import Settings
from app.main import create_app

AsyncClient = httpx.AsyncClient

WINDOW = {
    "screen_id": "menu_list", "window_start": "2026-10-01T10:00:00Z",
    "window_end": "2026-10-01T10:00:03Z",
    "touch": {"tap_count": 6, "miss_tap_count": 3, "repeat_tap_count": 2,
              "back_count": 0, "dwell_ms": 3000},
}
SCORES = {"normal": 0.167, "touch_difficulty": 0.833, "navigation_difficulty": 0,
          "visual_difficulty": 0.056, "hesitation": 0.1}


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.mode = "normal"
        self.scores = SCORES

        async def handler(request):
            self.calls.append(request)
            if self.mode == "timeout":
                await asyncio.sleep(10)
            if self.mode == "down":
                raise httpx.ConnectError("offline", request=request)
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "ok", "service": "ai-server"})
            payload = json.loads(request.content)
            return httpx.Response(200, json={
                "session_id": payload["session_id"], "measurable": self.mode != "unmeasurable",
                "states": None if self.mode == "unmeasurable" else self.scores,
                "model_version": "dummy-0.1",
            })

        self.app = create_app(Settings(_env_file=None, ai_server_timeout_seconds=0.05))
        http = httpx.AsyncClient(base_url="http://ai-server:8001",
                                 transport=httpx.MockTransport(handler))
        patcher = patch("app.main.httpx.AsyncClient", return_value=http)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = self.enterContext(TestClient(self.app))

    def session(self):
        response = self.client.post("/api/v1/sessions")
        self.assertEqual(response.status_code, 201)
        return response.json()

    def features(self, session_id, window=None):
        return self.client.post(f"/api/v1/sessions/{session_id}/features",
                                json=WINDOW if window is None else window)

    def test_session_and_forwarding(self):
        session = self.session()
        self.assertIsNotNone(datetime.fromisoformat(session["started_at"]).tzinfo)
        self.assertNotEqual(session["session_id"], self.session()["session_id"])
        response = self.features(session["session_id"])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ai_available"])
        self.assertEqual(data["states"], SCORES)
        self.assertEqual(data["support"], {"preset": "none", "requires_confirmation": False,
                                           "decided_by": "rule_placeholder"})
        self.assertEqual(json.loads(self.calls[-1].content),
                         {"session_id": session["session_id"], **WINDOW})

    def test_connectivity_and_liveness_during_failure(self):
        self.assertEqual(self.client.get("/api/v1/connectivity").json(),
                         {"backend": "ok", "ai_server": "ok"})
        self.mode = "down"
        self.assertEqual(self.client.get("/api/v1/connectivity").json(),
                         {"backend": "ok", "ai_server": "unreachable"})
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_unknown_session_never_calls_ai(self):
        response = self.features("missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "session not found"})
        self.assertEqual(self.calls, [])

    def test_measurement_and_transport_failure_differ(self):
        session = self.session()["session_id"]
        for mode in ("unmeasurable", "down", "timeout"):
            with self.subTest(mode=mode):
                self.mode = mode
                response = self.features(session)
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["ai_available"], mode == "unmeasurable")
                self.assertIsNone(data["states"])
                self.assertEqual(data["model_version"],
                                 "dummy-0.1" if mode == "unmeasurable" else None)
                self.assertEqual(data["support"]["preset"], "none")

    def test_invalid_ai_scores_are_not_returned(self):
        session = self.session()["session_id"]
        for scores in ({"normal": 0.2}, {**SCORES, "normal": 1.1},
                       {**SCORES, "normal": "0.2"}, {**SCORES, "normal": True}):
            with self.subTest(scores=scores):
                self.scores = scores
                data = self.features(session).json()
                self.assertFalse(data["ai_available"])
                self.assertIsNone(data["states"])

    def test_invalid_features_rejected_before_ai(self):
        session = self.session()["session_id"]
        invalid = []
        for value in (-1, 1.5, True, "6"):
            window = deepcopy(WINDOW)
            window["touch"]["tap_count"] = value
            invalid.append(window)
        missing = deepcopy(WINDOW)
        del missing["touch"]["dwell_ms"]
        invalid.extend([missing, {**WINDOW, "window_start": "2026-10-01T10:00:00"},
                        {**WINDOW, "window_end": WINDOW["window_start"]},
                        {**WINDOW, "vision": {"face_detected": True, "confidence": 2}}])
        for window in invalid:
            with self.subTest(window=window):
                self.assertEqual(self.features(session, window).status_code, 422)
        self.assertEqual(self.calls, [])

    def test_optional_vision_and_cors_post(self):
        session = self.session()["session_id"]
        for vision in (None, {"face_detected": False, "confidence": 0}):
            self.assertEqual(self.features(session, {**WINDOW, "vision": vision}).status_code, 200)
        response = self.client.options("/api/v1/sessions", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")

    def test_sessions_do_not_leak_between_app_instances(self):
        session = self.session()["session_id"]
        other = create_app(Settings(_env_file=None))
        other_http = AsyncClient(base_url="http://ai-server:8001")
        with patch("app.main.httpx.AsyncClient", return_value=other_http):
            with TestClient(other) as client:
                self.assertEqual(client.post(f"/api/v1/sessions/{session}/features",
                                             json=WINDOW).status_code, 404)
