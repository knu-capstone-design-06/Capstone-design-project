import asyncio
import json
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.common.config.settings import Settings
from app.infrastructure.external.ai_client import AiServerClient
from app.infrastructure.external.ai_schemas import AnalyzeRequest
from app.main import create_app


REQUEST = {
    "session_id": "3f2c9a0e7b1d4c5e8f6a2b1c0d9e8f7a",
    "screen_id": "menu_list",
    "window_start": "2026-10-01T10:00:00Z",
    "window_end": "2026-10-01T10:00:03Z",
    "touch": {
        "tap_count": 6, "miss_tap_count": 3, "repeat_tap_count": 2,
        "back_count": 0, "dwell_ms": 3000,
    },
    "vision": {
        "face_detected": True, "face_size_ratio": 0.35,
        "assistive_device": False, "confidence": 0.9,
    },
}
RESPONSE = {
    "session_id": REQUEST["session_id"],
    "measurable": True,
    "states": {
        "normal": 0.167, "touch_difficulty": 0.833,
        "navigation_difficulty": 0, "visual_difficulty": 0.056,
        "hesitation": 0.1,
    },
    "model_version": "dummy-0.1",
}


class AiClientTests(unittest.IsolatedAsyncioTestCase):
    async def call_analyze(self, handler, payload=None, timeout=2.0):
        async with httpx.AsyncClient(
            base_url="http://ai-server:8001",
            transport=httpx.MockTransport(handler),
        ) as http:
            client = AiServerClient(http, timeout)
            return await client.analyze(AnalyzeRequest.model_validate(
                REQUEST if payload is None else payload
            ))

    async def test_success_preserves_features_and_scores(self):
        def handler(request):
            self.assertEqual(str(request.url), "http://ai-server:8001/v1/analyze")
            self.assertEqual(request.method, "POST")
            self.assertEqual(json.loads(request.content), REQUEST)
            self.assertEqual(request.extensions["timeout"]["read"], 2.0)
            return httpx.Response(200, json=RESPONSE)

        result = await self.call_analyze(handler)
        self.assertEqual(result.model_dump(), RESPONSE)

    async def test_optional_vision_absent_or_null(self):
        for omitted in (True, False):
            payload = {**REQUEST, "vision": None}
            if omitted:
                del payload["vision"]

            def handler(request):
                self.assertEqual(json.loads(request.content), payload)
                return httpx.Response(200, json=RESPONSE)

            self.assertIsNotNone(await self.call_analyze(handler, payload))

    async def test_not_measurable_is_not_a_transport_failure(self):
        for include_states in (True, False):
            response = {**RESPONSE, "measurable": False, "states": None}
            if not include_states:
                del response["states"]
            result = await self.call_analyze(
                lambda _: httpx.Response(200, json=response)
            )
            self.assertFalse(result.measurable)
            self.assertIsNone(result.states)

    async def test_http_errors_and_redirects_do_not_retry(self):
        for status in (302, 422, 500, 503):
            with self.subTest(status=status):
                calls = []

                def handler(request):
                    calls.append(request)
                    return httpx.Response(status, headers={"Location": "http://other"})

                self.assertIsNone(await self.call_analyze(handler))
                self.assertEqual(len(calls), 1)

    async def test_transport_errors_return_no_judgment(self):
        for error in (httpx.ConnectError, httpx.ReadTimeout):
            def handler(request):
                raise error("simulated", request=request)

            self.assertIsNone(await self.call_analyze(handler))

    async def test_total_deadline(self):
        cancelled = asyncio.Event()

        async def handler(request):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()
            return httpx.Response(200, json=RESPONSE)

        self.assertIsNone(await asyncio.wait_for(
            self.call_analyze(handler, timeout=0.02), timeout=1
        ))
        self.assertTrue(cancelled.is_set())

    async def test_invalid_responses_return_no_judgment(self):
        invalid = [
            httpx.Response(200, content=b"not json"),
            httpx.Response(200, json=[]),
            httpx.Response(200, json={**RESPONSE, "session_id": "other-session"}),
            httpx.Response(200, json={**RESPONSE, "states": None}),
            httpx.Response(200, json={**RESPONSE, "states": {}}),
            httpx.Response(200, json={**RESPONSE, "measurable": False}),
            httpx.Response(200, json={**RESPONSE, "measurable": "true"}),
        ]
        for response in invalid:
            with self.subTest(response=response.content):
                self.assertIsNone(await self.call_analyze(lambda _: response))

    async def test_caller_cancellation_propagates(self):
        started = asyncio.Event()

        async def handler(request):
            started.set()
            await asyncio.sleep(10)
            return httpx.Response(200, json=RESPONSE)

        task = asyncio.create_task(self.call_analyze(handler))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_ai_health(self):
        for payload, expected in (
            ({"status": "ok", "service": "ai-server"}, True),
            ({"status": "ok", "service": "backend"}, False),
        ):
            def handler(request):
                self.assertEqual(request.method, "GET")
                self.assertEqual(request.url.path, "/health")
                return httpx.Response(200, json=payload)

            async with httpx.AsyncClient(
                base_url="http://ai-server:8001", transport=httpx.MockTransport(handler)
            ) as http:
                self.assertEqual((await AiServerClient(http).health()) is not None, expected)


class IntegrationTests(unittest.TestCase):
    def test_lifespan_owns_connection_and_health_remains_local(self):
        http = httpx.AsyncClient(base_url="http://ai-server:8001")
        application = create_app(Settings(_env_file=None))
        with patch("app.main.httpx.AsyncClient", return_value=http):
            with TestClient(application) as client:
                self.assertIsInstance(application.state.ai_server_client, AiServerClient)
                self.assertEqual(client.get("/health").json(), {
                    "status": "ok", "service": "backend",
                })
                self.assertEqual(client.get("/openapi.json").status_code, 200)
                self.assertFalse(http.is_closed)
        self.assertTrue(http.is_closed)
        self.assertFalse(hasattr(application.state, "ai_server_client"))

    def test_invalid_settings(self):
        for url in ("ftp://ai-server", "http://ai-server/path", "http://user:pass@ai-server"):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None, ai_server_url=url)
        for timeout in (0, -1, float("inf"), float("nan")):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None, ai_server_timeout_seconds=timeout)

    def test_window_requires_timezone_and_positive_duration(self):
        for override in (
            {"window_start": "2026-10-01T10:00:00"},
            {"window_end": REQUEST["window_start"]},
        ):
            with self.assertRaises(ValidationError):
                AnalyzeRequest.model_validate({**REQUEST, **override})


if __name__ == "__main__":
    unittest.main()
