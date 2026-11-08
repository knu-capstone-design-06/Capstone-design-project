"""Regression for voice-to-simulated-order with a deterministic OpenAI response."""

import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.common.config.settings import Settings
from app.main import create_app


class VoiceOrderFlowTests(unittest.TestCase):
    def test_voice_cart_replay_and_simulated_order(self):
        openai_requests = []
        model_response = {
            "status": "completed",
            "reply_text": None,
            "tool_calls": [{
                "tool": "add_cart_item",
                "arguments": {"product_id": "americano", "temperature": "iced", "quantity": 1},
            }],
        }

        def respond(request):
            openai_requests.append((request.url.path, json.loads(request.content)["model"]))
            return httpx.Response(200, json={"choices": [{"message": {
                "content": json.dumps(model_response),
            }}]})

        def mock_openai_http(_key, timeout):
            return httpx.AsyncClient(
                base_url="https://api.openai.com/v1", timeout=timeout,
                transport=httpx.MockTransport(respond),
            )

        settings = Settings(
            _env_file=None, openai_api_key="test-key", jev_api_key=None,
            openai_model="voice-test-model", openai_timeout_seconds=7.5,
            database_url=None, voice_execute_tools=True,
        )
        with patch("app.main.create_openai_http", side_effect=mock_openai_http) as factory:
            with TestClient(create_app(settings)) as client:
                factory.assert_called_once_with("test-key", 7.5)
                session = client.post("/api/v1/sessions")
                self.assertEqual(session.status_code, 201)
                base = f"/api/v1/sessions/{session.json()['session_id']}"
                voice_body = {
                    "text": "아이스 아메리카노 한 잔 담아줘",
                    "alternatives": [], "screen_id": "menu_list",
                }
                voice_headers = {"Idempotency-Key": str(uuid4())}
                accepted = client.post(base + "/voice/requests", json=voice_body, headers=voice_headers)
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

                replay = client.post(base + "/voice/requests", json=voice_body, headers=voice_headers)
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
                    base + "/voice/requests", json=voice_body,
                    headers={"Idempotency-Key": str(uuid4())},
                )
                self.assertEqual(new_voice.status_code, 410)
                self.assertEqual(openai_requests, [("/v1/chat/completions", "voice-test-model")])
