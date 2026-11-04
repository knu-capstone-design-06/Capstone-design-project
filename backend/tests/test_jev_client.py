import asyncio
import json
import unittest

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.common.config.settings import Settings
from app.infrastructure.external.jev_client import JEV_BASE_URL, JevClient, create_jev_http
from app.infrastructure.external.jev_schemas import JevRequest, JevResponse
from app.main import create_app


# The shape ai-engine's rule table builds (jev_request): names and numbers only.
REQUEST = {
    "model": "jev-latest",
    "state": {
        "situation": {"tag": "touch_difficulty", "evidence": {"miss": 3}, "dropped_cues": []},
        "screen": {"name": "menu_list", "steps_left": 2},
        "touch": {"misses_recent": 3, "fixes_recent": 1, "backs_recent": 0, "pause_s": 4.5},
        "vision": {"facing_screen": True, "looking_around": False},
        "session": {"active": [], "held": None, "refused": [], "withdrawn": []},
    },
    "questions": {
        "proposal_fits": {
            "type": "noul",
            "instructions": {"proposed_support": {"name": "big_button", "what": "Enlarge the buttons."},
                             "question": "Does `proposed_support` fit the user?"},
            "criteria": {"true": "The user misses buttons.", "false": "The user taps accurately."},
        },
    },
}
RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {"proposal_fits": {"type": "noul", "noul": 0.83}},
    "usage": {"input_tokens": 210, "output_tokens": 0},
}
CHOICE_RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {"queue_support": {
        "type": "choice", "choice": "remaining_steps_notice", "confidence": 0.7,
        "probabilities": {"remaining_steps_notice": 0.7, "defer_big_button_question": 0.3},
    }},
    "usage": {"input_tokens": 300, "output_tokens": 0},
}


class JevClientTests(unittest.IsolatedAsyncioTestCase):
    async def ask(self, handler, payload=None, model="jev-1.13.0", timeout=3.0):
        async with httpx.AsyncClient(
            base_url=JEV_BASE_URL, headers={"Authorization": "Bearer test-key"},
            transport=httpx.MockTransport(handler),
        ) as http:
            return await JevClient(http, model, timeout).ask(
                JevRequest.model_validate(REQUEST if payload is None else payload))

    async def test_sends_the_question_with_the_configured_model_and_key(self):
        def handler(request):
            self.assertEqual(str(request.url), "https://api.typesafe.ai/v1/systemone")
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.headers["Authorization"], "Bearer test-key")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "jev-1.13.0", "the alias in the request is replaced")
            self.assertEqual(body["state"], REQUEST["state"])
            self.assertEqual(body["questions"], REQUEST["questions"])
            self.assertEqual(request.extensions["timeout"]["read"], 3.0)
            return httpx.Response(200, json=RESPONSE)

        answer = await self.ask(handler)
        self.assertIsInstance(answer, JevResponse)
        self.assertEqual(answer.model, "jev-1.13.0")
        self.assertEqual(answer.answers["proposal_fits"].noul, 0.83)
        self.assertEqual(answer.usage.input_tokens, 210)

    async def test_choice_answer_is_parsed(self):
        answer = await self.ask(lambda request: httpx.Response(200, json=CHOICE_RESPONSE))
        choice = answer.answers["queue_support"]
        self.assertEqual((choice.type, choice.choice, choice.confidence), ("choice", "remaining_steps_notice", 0.7))
        self.assertEqual(choice.probabilities["defer_big_button_question"], 0.3)

    async def test_http_errors_give_none(self):
        for status in (400, 401, 413, 422, 429, 500, 529):
            with self.subTest(status=status):
                with self.assertLogs("app.infrastructure.external.jev_client", level="WARNING") as logs:
                    answer = await self.ask(lambda request, status=status: httpx.Response(status, json={"error": "x"}))
                self.assertIsNone(answer)
                self.assertIn(f"HTTP {status}", logs.output[0])
                self.assertNotIn("touch_difficulty", "".join(logs.output), "state is not logged")

    async def test_timeout_and_connection_errors_give_none(self):
        async def slow(request):
            await asyncio.sleep(0.2)
            return httpx.Response(200, json=RESPONSE)

        self.assertIsNone(await self.ask(slow, timeout=0.05))

        def broken(request):
            raise httpx.ConnectError("refused")

        self.assertIsNone(await self.ask(broken))

    async def test_malformed_answers_give_none(self):
        cases = {
            "not json": "not json",
            "no answers": {"model": "jev-1.13.0", "answers": {}, "usage": {"input_tokens": 1, "output_tokens": 0}},
            "probability out of range": {**RESPONSE, "answers": {"proposal_fits": {"type": "noul", "noul": 1.5}}},
            "unknown type": {**RESPONSE, "answers": {"proposal_fits": {"type": "guess", "noul": 0.5}}},
            "no usage": {"model": "jev-1.13.0", "answers": RESPONSE["answers"]},
        }
        for name, body in cases.items():
            with self.subTest(case=name):
                response = (httpx.Response(200, text=body) if isinstance(body, str)
                            else httpx.Response(200, json=body))
                self.assertIsNone(await self.ask(lambda request, response=response: response))

    def test_request_shape_is_checked_before_sending(self):
        with self.assertRaises(ValidationError):
            JevRequest.model_validate({**REQUEST, "questions": {}})
        with self.assertRaises(ValidationError):
            JevRequest.model_validate({**REQUEST, "extra": 1})

    def test_http_client_sends_the_key_only_to_the_configured_origin(self):
        http = create_jev_http("secret", "https://api.typesafe.ai", 3.0)
        self.assertEqual(http.headers["Authorization"], "Bearer secret")
        self.assertEqual(str(http.base_url), "https://api.typesafe.ai")
        self.assertFalse(http.trust_env)
        self.assertFalse(http.follow_redirects)


class JevSettingsTests(unittest.TestCase):
    def test_defaults_do_not_call_jev(self):
        settings = Settings(_env_file=None)
        self.assertIsNone(settings.jev_api_key)
        self.assertEqual(settings.jev_api_url, "https://api.typesafe.ai")
        self.assertEqual(settings.jev_model, "jev-1.13.0")
        self.assertEqual(settings.jev_timeout_seconds, 3.0)

    def test_key_is_a_secret_and_url_must_be_an_origin(self):
        settings = Settings(_env_file=None, jev_api_key="jev-secret-value", jev_api_url="https://example.test/")
        self.assertNotIn("jev-secret-value", repr(settings))
        self.assertEqual(settings.jev_api_url, "https://example.test")
        for bad in ("api.typesafe.ai", "https://api.typesafe.ai/v1", "https://user:pw@api.typesafe.ai"):
            with self.subTest(url=bad), self.assertRaises(ValidationError):
                Settings(_env_file=None, jev_api_url=bad)
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, jev_timeout_seconds=0)

    def test_app_builds_a_client_only_with_a_key(self):
        with TestClient(create_app(Settings(_env_file=None, openai_api_key=None))) as client:
            self.assertIsNone(client.app.state.jev_client)
        with TestClient(create_app(Settings(_env_file=None, openai_api_key=None, jev_api_key="k", jev_model="jev-1.14.0"))) as client:
            self.assertIsInstance(client.app.state.jev_client, JevClient)
            self.assertEqual(client.app.state.jev_client.model, "jev-1.14.0")
