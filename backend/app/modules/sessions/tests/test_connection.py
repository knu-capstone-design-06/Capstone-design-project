import asyncio
from copy import deepcopy
from datetime import datetime
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.common.config.settings import Settings
from app.main import create_app
from app.modules.sessions.exceptions import SessionCompleted
from app.modules.sessions.schemas import FeatureWindowRequest

AsyncClient = httpx.AsyncClient

WINDOW = {
    "screen_id": "menu_list", "window_start": "2026-10-01T10:00:00Z",
    "window_end": "2026-10-01T10:00:03Z",
    "touch": {"tap_count": 6, "miss_tap_count": 3, "repeat_tap_count": 2,
              "back_count": 0, "dwell_ms": 3000},
}
SCORES = {"normal": 0.167, "touch_difficulty": 0.833, "navigation_difficulty": 0,
          "visual_difficulty": 0.056, "hesitation": 0.1}
INTERACTION = {
    "schema_version": "touch-interaction-pilot-v1",
    "visit_id": "test-visit",
    "window_sequence": 1,
    "outside_tap_ratio": None,
    "outside_nearest_distance_mean_px": 3.5,
    "outside_nearest_distance_sample_count": 1,
    "pointer_cancel_count": 0,
    "pointer_interrupted_count": 1,
    "scroll_event_count": 2,
    "category_change_count": 1,
    "options_open_count": 0,
    "options_close_count": 1,
    "screen_transition_count": 1,
    "screen_revisit_count": None,
    "cart_change_count": 0,
    "selection_change_count": None,
    "ui_settings_change_count": 1,
    "voice_state_change_count": 2,
    "since_last_input_ms": None,
    "order_busy_ms": 0,
    "options_open": None,
    "order_busy": False,
    "voice_enabled": None,
    "microphone_active": None,
    "voice_processing": None,
    "voice_auto_off": None,
    "ui_settings": {"large_text": False, "large_button": True, "simple_screen": False,
                    "step_guide": False, "low_screen": True, "high_contrast": False},
}


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
                return httpx.Response(200, json={"status": "ok", "service": "ai-engine"})
            payload = json.loads(request.content)
            return httpx.Response(200, json={
                "session_id": payload["session_id"], "measurable": self.mode != "unmeasurable",
                "states": None if self.mode == "unmeasurable" else self.scores,
                "model_version": "dummy-0.1",
            })

        self.app = create_app(Settings(_env_file=None, ai_engine_timeout_seconds=0.05))
        http = httpx.AsyncClient(base_url="http://ai-engine:8001",
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
                         {"backend": "ok", "ai_engine": "ok"})
        self.mode = "down"
        self.assertEqual(self.client.get("/api/v1/connectivity").json(),
                         {"backend": "ok", "ai_engine": "unreachable"})
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_interaction_is_preserved_for_decision_and_excluded_from_internal_request(self):
        session = self.session()["session_id"]
        baseline = self.features(session).json()
        full = {**INTERACTION, "voice_phase": "speaking", "voice_speaking": True,
                "voice_busy": True, "voice_busy_ms": 150, "since_last_input_excluding_system_busy_ms": None}
        decision = self.app.state.decision_service
        with patch.object(decision, "observe", wraps=decision.observe) as observe:
            for values in (None, INTERACTION, full):
                with self.subTest(values=values):
                    response = self.features(session, {
                        **WINDOW, "touch": {**WINDOW["touch"], "interaction": values},
                    })
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json(), baseline)
                    forwarded = observe.call_args.args[1]
                    self.assertEqual(forwarded.touch.model_dump(exclude_unset=True)["interaction"], values)
                    self.assertEqual(json.loads(self.calls[-1].content), {"session_id": session, **WINDOW})
            self.assertEqual(observe.call_count, 3)

    def test_invalid_interaction_reports_fields_without_calling_ai_or_decision(self):
        session = self.session()["session_id"]
        cases = [
            ({**INTERACTION, "schema_version": "touch-interaction-v2"}, ["schema_version"], "literal_error"),
            ({key: value for key, value in INTERACTION.items() if key != "visit_id"}, ["visit_id"], "missing"),
            ({**INTERACTION, "visit_id": ""}, ["visit_id"], "string_too_short"),
            ({**INTERACTION, "unexpected": True}, ["unexpected"], "extra_forbidden"),
            ({**INTERACTION, "ui_settings": {**INTERACTION["ui_settings"], "unexpected": True}},
             ["ui_settings", "unexpected"], "extra_forbidden"),
            ({**INTERACTION, "order_busy": None}, ["order_busy"], "bool_type"),
            ({**INTERACTION, "pointer_cancel_count": True}, ["pointer_cancel_count"], "int_type"),
            ({**INTERACTION, "outside_tap_ratio": 1.1}, ["outside_tap_ratio"], "less_than_equal"),
            ({**INTERACTION, "voice_busy_ms": -1}, ["voice_busy_ms"], "greater_than_equal"),
        ]
        with patch.object(self.app.state.decision_service, "observe") as observe:
            for values, location, error_type in cases:
                with self.subTest(location=location, error_type=error_type):
                    response = self.features(session, {
                        **WINDOW, "touch": {**WINDOW["touch"], "interaction": values},
                    })
                    self.assertEqual(response.status_code, 422, response.text)
                    issue, = response.json()["detail"]
                    self.assertEqual(set(issue), {"loc", "msg", "type"})
                    self.assertEqual(issue["loc"], ["body", "touch", "interaction", *location])
                    self.assertEqual(issue["type"], error_type)
            observe.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_nonfinite_interaction_input_returns_422_without_echoing_value(self):
        session = self.session()["session_id"]
        window = {**WINDOW, "touch": {**WINDOW["touch"], "interaction": {
            **INTERACTION, "outside_nearest_distance_mean_px": float("nan"),
        }}}
        response = self.client.post(f"/api/v1/sessions/{session}/features",
                                    content=json.dumps(window), headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 422, response.text)
        issue, = response.json()["detail"]
        self.assertEqual(issue["loc"], ["body", "touch", "interaction", "outside_nearest_distance_mean_px"])
        self.assertEqual(set(issue), {"loc", "msg", "type"})
        self.assertEqual(self.calls, [])

    def test_unknown_session_never_calls_ai(self):
        response = self.features("missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "session not found"})
        self.assertEqual(self.calls, [])

    def test_completed_session_rejects_new_features_before_ai_call(self):
        session = self.session()["session_id"]
        base = f"/api/v1/sessions/{session}"
        added = self.client.post(f"{base}/cart/items", json={
            "product_id": "americano", "temperature": "iced",
            "quantity": 1, "expected_version": 0,
        }, headers={"Idempotency-Key": str(uuid4())})
        self.assertEqual(added.status_code, 200)
        ordered = self.client.post(f"{base}/orders", json={"expected_version": 1},
                                   headers={"Idempotency-Key": str(uuid4())})
        self.assertEqual(ordered.status_code, 201)

        response = self.features(session)
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json(), {"detail": "session_expired"})
        self.assertEqual(self.calls, [])

    def test_feature_result_arriving_after_order_completion_is_rejected(self):
        session = self.session()["session_id"]
        service = self.app.state.session_service
        ordering = self.app.state.ordering_repository

        class CompletingAi:
            async def analyze(self, request):
                with ordering.lock:
                    ordering.state(session).completed = True
                return None

        with self.assertRaises(SessionCompleted):
            asyncio.run(service.analyze(
                session, FeatureWindowRequest.model_validate(WINDOW), CompletingAi(),
            ))

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
        other_http = AsyncClient(base_url="http://ai-engine:8001")
        with patch("app.main.httpx.AsyncClient", return_value=other_http):
            with TestClient(other) as client:
                self.assertEqual(client.post(f"/api/v1/sessions/{session}/features",
                                             json=WINDOW).status_code, 404)
