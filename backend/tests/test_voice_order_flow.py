"""Voice ordering regressions with deterministic OpenAI responses."""

import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.common.config.settings import Settings
from app.main import create_app


VOICE_BODY = {
    "text": "아이스 아메리카노 한 잔 담아줘",
    "alternatives": [],
    "screen_id": "menu_list",
}


def completed_response():
    model_result = {
        "status": "completed",
        "reply_text": None,
        "tool_calls": [{
            "tool": "add_cart_item",
            "arguments": {"product_id": "americano", "temperature": "iced", "quantity": 1},
        }],
    }
    return httpx.Response(200, json={"choices": [{"message": {
        "content": json.dumps(model_result),
    }}]})


class VoiceOrderFlowTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            _env_file=None, openai_api_key="test-key", jev_api_key=None,
            openai_model="voice-test-model", openai_timeout_seconds=7.5,
            database_url=None, voice_execute_tools=True,
        )

    def test_voice_cart_replay_and_simulated_order(self):
        openai_requests = []

        def respond(request):
            openai_requests.append((request.url.path, json.loads(request.content)["model"]))
            return completed_response()

        def mock_openai_http(_key, timeout):
            return httpx.AsyncClient(
                base_url="https://api.openai.com/v1", timeout=timeout,
                transport=httpx.MockTransport(respond),
            )

        with patch("app.main.create_openai_http", side_effect=mock_openai_http) as factory:
            with TestClient(create_app(self.settings)) as client:
                factory.assert_called_once_with("test-key", 7.5)
                session = client.post("/api/v1/sessions")
                self.assertEqual(session.status_code, 201)
                base = f"/api/v1/sessions/{session.json()['session_id']}"
                voice_headers = {"Idempotency-Key": str(uuid4())}
                accepted = client.post(base + "/voice/requests", json=VOICE_BODY, headers=voice_headers)
                self.assertEqual(accepted.status_code, 202)
                request_id = accepted.json()["request_id"]
                result = client.get(base + "/voice/requests/" + request_id)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["status"], "completed")
                self.assertEqual(result.json()["actions"], ["cart_updated"])

                cart = client.get(base + "/cart")
                self.assertEqual(cart.status_code, 200)
                cart_data = cart.json()
                self.assertEqual(
                    [(item["product_id"], item["temperature"], item["quantity"])
                     for item in cart_data["items"]],
                    [("americano", "iced", 1)],
                )

                replay = client.post(base + "/voice/requests", json=VOICE_BODY, headers=voice_headers)
                self.assertEqual(replay.status_code, 202)
                self.assertEqual(replay.json()["request_id"], request_id)
                self.assertEqual(client.get(base + "/cart").json()["total_quantity"], 1)
                self.assertEqual(openai_requests, [("/v1/chat/completions", "voice-test-model")])

                order_headers = {"Idempotency-Key": str(uuid4())}
                order_body = {"expected_version": cart_data["version"]}
                order = client.post(base + "/orders", json=order_body, headers=order_headers)
                self.assertEqual(order.status_code, 201)
                self.assertEqual(order.json()["status"], "simulated")
                self.assertTrue(order.json()["order_number"])
                self.assertEqual(order.json()["items"], cart_data["items"])
                order_replay = client.post(base + "/orders", json=order_body, headers=order_headers)
                self.assertEqual(order_replay.status_code, 201)
                self.assertEqual(order_replay.json(), order.json())

                new_voice = client.post(
                    base + "/voice/requests", json=VOICE_BODY,
                    headers={"Idempotency-Key": str(uuid4())},
                )
                self.assertEqual(new_voice.status_code, 410)
                self.assertEqual(openai_requests, [("/v1/chat/completions", "voice-test-model")])

    def test_openai_http_failure_preserves_cart_and_new_utterance_can_recover(self):
        private_detail = "provider response body must stay private"

        for status_code in (401, 429, 503):
            with self.subTest(openai_status=status_code):
                responses = iter((
                    httpx.Response(status_code, json={"error": {"message": private_detail}}),
                    completed_response(),
                ))
                provider_requests = []

                def respond(request):
                    provider_requests.append(request.url.path)
                    return next(responses)

                openai = httpx.AsyncClient(
                    base_url="https://api.openai.com/v1", transport=httpx.MockTransport(respond),
                )
                with (
                    patch("app.main.create_openai_http", return_value=openai),
                    TestClient(create_app(self.settings)) as client,
                ):
                    session = client.post("/api/v1/sessions")
                    self.assertEqual(session.status_code, 201)
                    base = f"/api/v1/sessions/{session.json()['session_id']}"
                    cart_path = base + "/cart"
                    voice_path = base + "/voice/requests"
                    empty_cart = client.get(cart_path).json()
                    seeded = client.post(cart_path + "/items", headers={"Idempotency-Key": str(uuid4())}, json={
                        "expected_version": empty_cart["version"], "product_id": "americano",
                        "temperature": "hot", "quantity": 1,
                    })
                    self.assertEqual(seeded.status_code, 200)
                    cart_before = seeded.json()

                    original_headers = {"Idempotency-Key": str(uuid4())}
                    with self.assertLogs("app.infrastructure.external.openai_client", level="WARNING") as logs:
                        accepted = client.post(voice_path, json=VOICE_BODY, headers=original_headers)
                    self.assertEqual(accepted.status_code, 202)
                    self.assertNotIn(private_detail, "\n".join(logs.output))
                    result_path = f"{voice_path}/{accepted.json()['request_id']}"
                    failed = client.get(result_path)
                    self.assertEqual(failed.status_code, 200)
                    self.assertEqual(failed.json()["status"], "failed")
                    self.assertEqual(failed.json()["error"]["code"], "ai_unavailable")
                    self.assertEqual(failed.json()["actions"], [])
                    self.assertNotIn(private_detail, failed.text)
                    self.assertEqual(client.get(cart_path).json(), cart_before)

                    replay = client.post(voice_path, json=VOICE_BODY, headers=original_headers)
                    self.assertEqual(replay.status_code, 202)
                    self.assertEqual(replay.json(), accepted.json())
                    self.assertEqual(client.get(result_path).json(), failed.json())
                    self.assertEqual(provider_requests, ["/v1/chat/completions"])

                    retry = client.post(
                        voice_path, json=VOICE_BODY, headers={"Idempotency-Key": str(uuid4())},
                    )
                    self.assertEqual(retry.status_code, 202)
                    retry_id = retry.json()["request_id"]
                    self.assertNotEqual(retry_id, accepted.json()["request_id"])
                    recovered = client.get(f"{voice_path}/{retry_id}")
                    self.assertEqual(recovered.status_code, 200)
                    self.assertEqual(recovered.json()["status"], "completed")
                    self.assertEqual(recovered.json()["actions"], ["cart_updated"])
                    actual_cart = client.get(cart_path).json()
                    self.assertEqual(actual_cart["version"], cart_before["version"] + 1)
                    self.assertCountEqual(
                        [(item["product_id"], item["temperature"], item["quantity"])
                         for item in actual_cart["items"]],
                        [("americano", "hot", 1), ("americano", "iced", 1)],
                    )
                    self.assertEqual(provider_requests, ["/v1/chat/completions"] * 2)
