import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.common.config.settings import Settings
from app.infrastructure.external.openai_client import OpenAiClient
from app.main import create_app
from app.modules.voice.interpreter import OpenAiVoiceInterpreter, StubVoiceInterpreter
from app.modules.voice.exceptions import VoiceSessionCompleted
from app.modules.voice.repository import HISTORY_TURNS, VoiceRepository
from app.modules.voice.schemas import (
    MenuItem, VoiceErrorResponse, VoiceInterpretation, VoiceRequestCreate, VoiceTurn,
)

BODY = {
    "text": "아이스 아메리카노 두 개 담아줘",
    "alternatives": [{"text": "아이스 아메리카노 두 개 담아줘", "confidence": 0.91}],
    "screen_id": "menu_list",
}
MENU = [
    MenuItem(product_id="americano", name="아메리카노", available=True,
             temperatures=["iced", "hot"]),
    MenuItem(product_id="sandwich", name="에그 샌드위치", available=True, temperatures=[]),
    MenuItem(product_id="latte", name="카페 라떼", available=False, temperatures=["hot"]),
]
ADD_AMERICANO = {"tool": "add_cart_item",
                 "arguments": {"product_id": "americano", "temperature": "iced", "quantity": 2}}
CONFIRM = "아이스 아메리카노 2잔 담을까요?"


def call(tool, product_id, temperature, quantity=None):
    arguments = {"product_id": product_id, "temperature": temperature}
    if quantity is not None:
        arguments["quantity"] = quantity
    return {"tool": tool, "arguments": arguments}


def interpretation(*tool_calls, reply_text=None):
    if not reply_text:
        status = "completed"
    else:
        status = "needs_confirmation" if tool_calls else "needs_clarification"
    return VoiceInterpretation.model_validate(
        {"status": status, "tool_calls": list(tool_calls), "reply_text": reply_text}
    )


class FakeInterpreter:
    def __init__(self):
        self.result = interpretation(ADD_AMERICANO)
        self.calls = 0
        self.menus = []
        self.histories = []

    async def interpret(self, request, menu, history):
        self.calls += 1
        self.menus.append(menu)
        self.histories.append(history)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class VoiceApiTests(unittest.TestCase):
    def setUp(self):
        self.interpreter = FakeInterpreter()
        for target, value in (("app.main.build_voice_interpreter", self.interpreter),
                              ("app.main.menu_from_products", MENU)):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        app = create_app(Settings(_env_file=None, openai_api_key=None))
        self.client = self.enterContext(TestClient(app))
        self.session_id = self.client.post("/api/v1/sessions").json()["session_id"]

    def post(self, body=None, key=None, session_id=None):
        return self.client.post(
            f"/api/v1/sessions/{session_id or self.session_id}/voice/requests",
            json=BODY if body is None else body,
            headers={"Idempotency-Key": key or str(uuid4())},
        )

    def say(self, text, session_id=None):
        body = {**BODY, "text": text, "alternatives": []}
        return self.post(body=body, session_id=session_id).json()["request_id"]

    def status(self, request_id, session_id=None):
        return self.client.get(
            f"/api/v1/sessions/{session_id or self.session_id}/voice/requests/{request_id}"
        )

    def complete_order(self):
        base = f"/api/v1/sessions/{self.session_id}"
        added = self.client.post(f"{base}/cart/items", json={
            "product_id": "americano", "temperature": "iced",
            "quantity": 1, "expected_version": 0,
        }, headers={"Idempotency-Key": str(uuid4())})
        self.assertEqual(added.status_code, 200)
        ordered = self.client.post(f"{base}/orders", json={"expected_version": 1},
                                   headers={"Idempotency-Key": str(uuid4())})
        self.assertEqual(ordered.status_code, 201)

    def test_accepts_and_returns_tool_calls_without_claiming_changes(self):
        response = self.post()
        self.assertEqual(response.status_code, 202)
        accepted = response.json()
        self.assertEqual(accepted["status"], "accepted")
        self.assertTrue(accepted["request_id"].startswith("vr_"))
        # TestClient runs background tasks before returning the response.
        self.assertEqual(self.status(accepted["request_id"]).json(), {
            "request_id": accepted["request_id"], "status": "completed",
            "reply_text": None, "tool_calls": [ADD_AMERICANO], "actions": [], "error": None,
        })
        self.assertEqual(self.interpreter.menus, [MENU])

    def test_needs_clarification_is_reported(self):
        question = "라떼는 아이스, 따뜻한 것 중 무엇으로 할까요?"
        self.interpreter.result = interpretation(reply_text=question)
        body = self.status(self.post().json()["request_id"]).json()
        self.assertEqual(body["status"], "needs_clarification")
        self.assertEqual(body["reply_text"], question)
        self.assertEqual(body["tool_calls"], [])

    def test_needs_confirmation_returns_proposal_and_short_question(self):
        self.interpreter.result = interpretation(ADD_AMERICANO, reply_text=CONFIRM)
        body = self.status(self.post().json()["request_id"]).json()
        self.assertEqual(body["status"], "needs_confirmation")
        self.assertEqual(body["reply_text"], CONFIRM)
        self.assertEqual(body["tool_calls"], [ADD_AMERICANO])
        self.assertEqual(body["actions"], [])

    def test_confirmation_answer_is_read_with_previous_proposal(self):
        proposal = interpretation(ADD_AMERICANO, reply_text=CONFIRM)
        self.interpreter.result = proposal
        self.say("아이스 아메리카노 두 개")
        self.interpreter.result = interpretation(ADD_AMERICANO)
        body = self.status(self.say("네")).json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["tool_calls"], [ADD_AMERICANO])
        first, second = self.interpreter.histories
        self.assertEqual(first, [])
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].request.text, "아이스 아메리카노 두 개")
        self.assertEqual(second[0].result, proposal)

    def test_history_is_per_session_and_limited(self):
        for index in range(HISTORY_TURNS + 2):
            self.say(f"발화 {index}")
        other = self.client.post("/api/v1/sessions").json()["session_id"]
        self.say("다른 손님", session_id=other)
        self.say("마지막")
        self.assertEqual(self.interpreter.histories[-2], [])  # other session starts empty
        history = self.interpreter.histories[-1]
        self.assertEqual(len(history), HISTORY_TURNS)
        self.assertEqual(history[0].request.text, "발화 2")
        self.assertEqual(history[-1].request.text, f"발화 {HISTORY_TURNS + 1}")

    def test_failed_requests_stay_out_of_history(self):
        self.interpreter.result = None
        self.say("실패할 요청")
        self.interpreter.result = interpretation(call("add_cart_item", "mocha", "iced", 1))
        self.say("메뉴에 없는 요청")
        self.interpreter.result = interpretation(ADD_AMERICANO)
        self.say("아메리카노")
        self.say("다음")
        self.assertEqual([t.request.text for t in self.interpreter.histories[-1]], ["아메리카노"])

    def test_ignored_speech_is_reported_without_reply_or_history(self):
        self.interpreter.result = VoiceInterpretation(status="ignored", tool_calls=[], reply_text=None)
        body = self.status(self.say("너 뭐 먹을래?")).json()
        self.assertEqual(body["status"], "ignored")
        self.assertEqual((body["reply_text"], body["tool_calls"], body["actions"]), (None, [], []))
        self.interpreter.result = interpretation(ADD_AMERICANO)
        self.say("아메리카노")
        self.say("다음")
        self.assertEqual([t.request.text for t in self.interpreter.histories[-1]], ["아메리카노"])

    def test_tool_calls_on_menu_are_kept_in_order(self):
        valid = [
            call("update_cart_item", "sandwich", None, 3),
            call("remove_cart_item", "latte", "hot"),  # unavailable items can still leave the cart
        ]
        self.interpreter.result = interpretation(*valid)
        request_id = self.say("샌드위치 세 개로 바꾸고 라떼는 빼 주세요")
        self.assertEqual(self.status(request_id).json()["tool_calls"], valid)

    def test_tool_calls_off_menu_are_rejected(self):
        for bad in (
            call("add_cart_item", "mocha", "iced", 1),     # not on menu
            call("add_cart_item", "latte", "hot", 1),      # unavailable
            call("add_cart_item", "sandwich", "hot", 1),   # no temperature for food
            call("remove_cart_item", "latte", "iced"),     # temperature not allowed
        ):
            for reply_text in (None, "담을까요?"):  # completed and proposals alike
                self.interpreter.result = interpretation(ADD_AMERICANO, bad, reply_text=reply_text)
                body = self.status(self.post().json()["request_id"]).json()
                self.assertEqual(body["status"], "failed", bad)
                self.assertEqual(body["tool_calls"], [])

    def test_drink_without_temperature_becomes_temperature_question(self):
        for reply_text in (None, "담을까요?"):  # completed and proposals alike
            self.interpreter.result = interpretation(
                call("add_cart_item", "americano", None, 2), reply_text=reply_text)
            body = self.status(self.post().json()["request_id"]).json()
            self.assertEqual(body["status"], "needs_clarification")
            self.assertEqual(body["tool_calls"], [])
            self.assertIn("아메리카노", body["reply_text"])
            self.assertIsNone(body["error"])

    def test_single_allowed_temperature_is_filled_in(self):
        self.interpreter.result = interpretation(call("remove_cart_item", "latte", None))
        body = self.status(self.say("라떼 빼 주세요")).json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["tool_calls"], [call("remove_cart_item", "latte", "hot")])

    def test_temperature_question_is_kept_for_the_next_answer(self):
        self.interpreter.result = interpretation(call("add_cart_item", "americano", None, 1))
        self.say("아메리카노 하나")
        self.interpreter.result = interpretation(call("add_cart_item", "americano", "iced", 1))
        body = self.status(self.say("아이스로요")).json()
        self.assertEqual(body["status"], "completed")
        previous = self.interpreter.histories[-1]
        self.assertEqual(len(previous), 1)
        self.assertEqual(previous[0].request.text, "아메리카노 하나")
        self.assertEqual(previous[0].result.status, "needs_clarification")

    def test_bare_yes_after_a_question_repeats_the_question(self):
        question = "카페 라떼는 아이스, 따뜻한 것 중 무엇으로 할까요?"
        self.interpreter.result = interpretation(reply_text=question)
        self.say("카페라떼 하나요")
        self.interpreter.result = interpretation(call("add_cart_item", "americano", "hot", 1))
        body = self.status(self.say("네.")).json()
        self.assertEqual(body["status"], "needs_clarification")
        self.assertEqual(body["reply_text"], question)
        self.assertEqual(self.interpreter.calls, 1, "질문을 다시 할 때는 OpenAI를 부르지 않음")

    def test_yes_after_a_proposal_still_reaches_the_interpreter(self):
        self.interpreter.result = interpretation(ADD_AMERICANO, reply_text=CONFIRM)
        self.say("아메리카노 두 잔")
        self.interpreter.result = interpretation(ADD_AMERICANO)
        body = self.status(self.say("네")).json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(self.interpreter.calls, 2)

    def test_first_bare_answer_in_a_session_sends_no_tool_calls(self):
        self.interpreter.result = interpretation(ADD_AMERICANO)  # the model made one up
        body = self.status(self.say("네")).json()
        self.assertEqual(body["status"], "needs_clarification")
        self.assertEqual(body["tool_calls"], [])
        self.assertEqual(body["reply_text"], "어떤 메뉴를 주문할까요?")

    def test_temperature_only_answer_without_a_question_sends_no_tool_calls(self):
        self.interpreter.result = interpretation(call("add_cart_item", "americano", "hot", 1))
        body = self.status(self.say("따뜻한 걸로요")).json()
        self.assertEqual(body["status"], "needs_clarification")
        self.assertEqual(body["tool_calls"], [])

    def test_product_named_earlier_in_the_session_is_kept(self):
        self.interpreter.result = interpretation(ADD_AMERICANO)
        self.say("아이스 아메리카노 두 잔")
        self.interpreter.result = interpretation(call("update_cart_item", "americano", "iced", 3))
        body = self.status(self.say("하나 더요")).json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["tool_calls"], [call("update_cart_item", "americano", "iced", 3)])

    def test_bare_yes_after_a_completed_order_asks_without_calling_openai(self):
        self.interpreter.result = interpretation(ADD_AMERICANO)
        self.say("아이스 아메리카노 두 잔")
        body = self.status(self.say("네")).json()
        self.assertEqual(body["status"], "needs_clarification")
        self.assertEqual(body["tool_calls"], [])
        self.assertEqual(self.interpreter.calls, 1, "다시 담지 않도록 OpenAI를 부르지 않음")

    def test_answer_to_a_general_menu_question_still_has_to_name_a_product(self):
        self.say("네")  # stored as "어떤 메뉴를 주문할까요?"
        self.interpreter.result = interpretation(call("add_cart_item", "americano", "hot", 1))
        body = self.status(self.say("따뜻한 걸로요")).json()
        self.assertEqual(body["status"], "needs_clarification")
        self.assertEqual(body["tool_calls"], [])

    def test_other_product_than_the_one_named_is_not_sent(self):
        self.interpreter.result = interpretation(ADD_AMERICANO)
        self.say("아이스 아메리카노 두 잔")
        self.interpreter.result = interpretation(call("add_cart_item", "sandwich", None, 1))
        body = self.status(self.say("따뜻한 걸로요")).json()
        self.assertEqual(body["status"], "needs_clarification")
        self.assertEqual(body["tool_calls"], [])

    def test_ai_unavailable_and_crash_become_failed(self):
        for result in (None, RuntimeError("boom")):
            self.interpreter.result = result
            request_id = self.post().json()["request_id"]
            body = self.status(request_id).json()
            self.assertEqual(body["status"], "failed")
            self.assertEqual(body["error"]["code"], "ai_unavailable")
            self.assertNotIn("boom", json.dumps(body, ensure_ascii=False))
            self.assertEqual(body["actions"], [])

    def test_same_key_replays_without_reprocessing(self):
        key = str(uuid4())
        first = self.post(key=key)
        second = self.post(key=key)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(self.interpreter.calls, 1)

    def test_same_key_with_different_body_is_rejected(self):
        key = str(uuid4())
        self.post(key=key)
        response = self.post(body={**BODY, "text": "라떼 하나"}, key=key)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "idempotency_key_reused")

    def test_completed_session_replays_old_voice_request_but_rejects_new_one(self):
        key = str(uuid4())
        first = self.post(key=key)
        self.assertEqual(first.status_code, 202)
        self.complete_order()

        replay = self.post(key=key)
        self.assertEqual(replay.status_code, 202)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(self.interpreter.calls, 1)
        self.assertEqual(self.status(first.json()["request_id"]).status_code, 200)
        changed = self.post(body={**BODY, "text": "라떼 하나"}, key=key)
        self.assertEqual((changed.status_code, changed.json()["code"]),
                         (409, "idempotency_key_reused"))
        new = self.post()
        self.assertEqual(new.status_code, 410)
        self.assertEqual(new.json(), {
            "code": "session_expired", "detail": "새 이용 세션을 시작해 주세요.",
        })
        self.assertEqual(VoiceErrorResponse.model_validate(new.json()).code,
                         "session_expired")
        response_schema = self.client.get("/openapi.json").json()["components"]["schemas"]
        self.assertIn("session_expired",
                      response_schema["VoiceErrorResponse"]["properties"]["code"]["enum"])

    def test_completed_session_returns_410_before_in_progress_for_new_key(self):
        service = self.client.app.state.voice_service
        old_key = uuid4()
        old, _ = service.accept(self.session_id, old_key,
                                VoiceRequestCreate.model_validate(BODY))
        self.complete_order()
        self.assertEqual(self.post().status_code, 410)
        replay = self.post(key=str(old_key))
        self.assertEqual(replay.status_code, 202)
        self.assertEqual(replay.json(), old.model_dump(mode="json"))
        self.assertEqual(self.status(old.request_id).json()["status"], "accepted")

    def test_second_request_while_processing_is_rejected(self):
        # Simulate an unfinished request by accepting without running the background task.
        service = self.client.app.state.voice_service
        service.accept(self.session_id, uuid4(), VoiceRequestCreate.model_validate(BODY))
        response = self.post()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "request_in_progress")

    def test_unknown_session_and_request(self):
        response = self.post(session_id="missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "session_not_found")
        self.assertEqual(self.status("vr_x", session_id="missing").json()["code"],
                         "session_not_found")
        response = self.status("vr_missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "voice_request_not_found")

    def test_request_from_other_session_is_hidden(self):
        request_id = self.post().json()["request_id"]
        other = self.client.post("/api/v1/sessions").json()["session_id"]
        self.assertEqual(self.status(request_id, session_id=other).status_code, 404)

    def test_invalid_requests_use_contract_error_shape(self):
        cases = [
            {**BODY, "text": "   "},
            {**BODY, "text": "가" * 501},
            {**BODY, "alternatives": [{"text": "a", "confidence": 1.5}]},
            {**BODY, "alternatives": [{"text": "a", "confidence": None}] * 6},
            {**BODY, "screen_id": None},
            {k: v for k, v in BODY.items() if k != "screen_id"},
        ]
        for body in cases:
            response = self.post(body=body)
            self.assertEqual(response.status_code, 422, body)
            self.assertEqual(response.json()["code"], "invalid_request")
        response = self.post(key="not-a-uuid")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "invalid_request")
        self.assertEqual(self.interpreter.calls, 0)

    def test_null_confidence_is_allowed(self):
        body = {**BODY, "alternatives": [{"text": "라떼", "confidence": None}]}
        self.assertEqual(self.post(body=body).status_code, 202)


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
        self.repository = VoiceRepository(retention=timedelta(hours=1), clock=lambda: self.now)

    def accept(self, session_id="s1", key=None):
        return self.repository.accept(session_id, key or uuid4(), "fingerprint")

    def test_old_requests_keys_and_idle_context_are_dropped(self):
        key = uuid4()
        record, _ = self.accept(key=key)
        self.repository.update(record.request_id, "completed",
                               tool_calls=interpretation(ADD_AMERICANO).tool_calls)
        self.repository.append_turn("s1", VoiceTurn(
            request=VoiceRequestCreate.model_validate(BODY), result=interpretation(ADD_AMERICANO)))

        self.now += timedelta(minutes=59)
        self.assertEqual(self.accept(key=key)[1], False)  # still a replay within retention
        self.assertEqual(len(self.repository.history("s1")), 1)

        self.now += timedelta(minutes=2)
        self.accept(session_id="s2")  # any request triggers cleanup
        self.assertIsNone(self.repository.get("s1", record.request_id))
        self.assertEqual(self.repository.history("s1"), [])
        self.assertEqual(self.accept(key=key)[1], True)  # the old key starts a new request

    def test_update_after_cleanup_is_ignored(self):
        record, _ = self.accept()
        self.now += timedelta(hours=2)
        self.accept(session_id="s2")
        self.repository.update(record.request_id, "completed")  # must not raise
        self.assertIsNone(self.repository.get("s1", record.request_id))

    def test_expired_key_in_completed_session_is_treated_as_new_request(self):
        key = uuid4()
        record, _ = self.repository.accept("s1", key, "fingerprint")
        self.now += timedelta(hours=1, seconds=1)
        with self.assertRaises(VoiceSessionCompleted):
            self.repository.accept("s1", key, "fingerprint", is_completed=lambda: True)
        self.assertIsNone(self.repository.get("s1", record.request_id))


class MissingTemperatureTests(unittest.TestCase):
    def test_sold_out_drink_without_temperature_is_still_rejected(self):
        from app.modules.voice.service import ask_for_missing_temperature, matches_menu

        menu = [MenuItem(product_id="americano", name="아메리카노", available=False,
                         temperatures=["iced", "hot"])]
        result = ask_for_missing_temperature(
            interpretation(call("add_cart_item", "americano", None, 1)), menu)
        self.assertEqual(result.status, "completed")
        self.assertFalse(matches_menu(result, menu))


class NamedProductTests(unittest.TestCase):
    LATTES = [
        MenuItem(product_id="latte", name="카페 라떼", available=True, temperatures=["iced", "hot"]),
        MenuItem(product_id="vanilla", name="바닐라 라떼", available=True, temperatures=["iced", "hot"]),
    ]

    def check(self, text, *tool_calls, history=()):
        from app.modules.voice.service import require_named_products

        request = VoiceRequestCreate(text=text, alternatives=[], screen_id="menu_list")
        return require_named_products(interpretation(*tool_calls), request, list(history), self.LATTES)

    def test_full_name_keeps_the_named_latte(self):
        result = self.check("따뜻한 바닐라 라떼 두 잔", call("add_cart_item", "vanilla", "hot", 2))
        self.assertEqual(result.status, "completed")


class PromptVersionTests(unittest.TestCase):
    def test_current_prompt_explains_every_status(self):
        from app.modules.voice import interpreter

        self.assertEqual(interpreter.PROMPT_VERSION, "interpret_v3")
        prompt = interpreter._PROMPT_PATH.read_text(encoding="utf-8")
        for status in ("completed", "needs_confirmation", "needs_clarification", "ignored"):
            self.assertIn(f"- {status}:", prompt)


    def test_current_prompt_asks_temperature_and_does_not_invent_answers(self):
        from app.modules.voice import interpreter

        prompt = interpreter._PROMPT_PATH.read_text(encoding="utf-8")
        self.assertIn("temperature를 null로 두지 않는다", prompt)
        self.assertIn("상품을 지어내지 않는다", prompt)


class MenuFromProductsTests(unittest.TestCase):
    def test_ordering_catalog_becomes_interpreter_menu(self):
        from app.modules.ordering.catalog import PRODUCTS
        from app.modules.voice.service import menu_from_products

        menu = menu_from_products(PRODUCTS)
        self.assertEqual(len(menu), len(PRODUCTS))
        americano = next(item for item in menu if item.product_id == "americano")
        self.assertEqual(americano, MENU[0])
        sandwich = next(item for item in menu if item.product_id == "sandwich")
        self.assertEqual(sandwich.temperatures, [])


class DefaultWiringTests(unittest.TestCase):
    def request_status(self, client):
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        base = f"/api/v1/sessions/{session_id}/voice/requests"
        request_id = client.post(
            base, json=BODY, headers={"Idempotency-Key": str(uuid4())}
        ).json()["request_id"]
        return client.get(f"{base}/{request_id}").json()

    def test_empty_menu_skips_the_interpreter(self):
        interpreter = FakeInterpreter()
        with patch("app.main.build_voice_interpreter", return_value=interpreter),                 patch("app.main.PRODUCTS", ()):
            app = create_app(Settings(_env_file=None, openai_api_key=None))
            with TestClient(app) as client:
                body = self.request_status(client)
        self.assertEqual(interpreter.calls, 0)
        self.assertEqual(body["status"], "failed")
        self.assertEqual(body["error"]["code"], "ai_unavailable")
        self.assertIn("메뉴", body["error"]["detail"])

    def test_app_without_key_uses_stub_question(self):
        app = create_app(Settings(_env_file=None, openai_api_key=None))
        with TestClient(app) as client:
            self.assertIsInstance(
                client.app.state.voice_service._interpreter, StubVoiceInterpreter
            )
            body = self.request_status(client)
        self.assertEqual(body["status"], "needs_clarification")
        self.assertEqual(body["tool_calls"], [])


def openai_response(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def openai_output(**fields):
    output = {"status": "completed", "tool_calls": [ADD_AMERICANO], "reply_text": None, **fields}
    return lambda request: openai_response(json.dumps(output, ensure_ascii=False))


class OpenAiInterpreterTests(unittest.IsolatedAsyncioTestCase):
    async def interpret(self, handler, timeout=1.0, history=()):
        async with httpx.AsyncClient(
            base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handler)
        ) as http:
            interpreter = OpenAiVoiceInterpreter(OpenAiClient(http, "test-model", timeout))
            return await interpreter.interpret(
                VoiceRequestCreate.model_validate(BODY), MENU, list(history)
            )

    async def test_sends_menu_and_parses_tool_calls(self):
        seen = {}

        def handler(request):
            seen["path"] = request.url.path
            seen["payload"] = json.loads(request.content)
            return openai_output()(request)

        result = await self.interpret(handler)
        self.assertEqual(result.model_dump()["tool_calls"], [ADD_AMERICANO])
        self.assertEqual(seen["path"], "/v1/chat/completions")
        payload = seen["payload"]
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertTrue(payload["response_format"]["json_schema"]["strict"])
        user = json.loads(payload["messages"][-1]["content"])
        self.assertEqual(set(user), {"text", "alternatives", "screen_id", "menu"})
        self.assertEqual([item["product_id"] for item in user["menu"]],
                         ["americano", "sandwich", "latte"])

    async def test_previous_turns_are_sent_in_order(self):
        seen = {}

        def handler(request):
            seen["messages"] = json.loads(request.content)["messages"]
            return openai_output()(request)

        proposal = interpretation(ADD_AMERICANO, reply_text=CONFIRM)
        turn = VoiceTurn(
            request=VoiceRequestCreate.model_validate({**BODY, "text": "아아 두 개"}),
            result=proposal,
        )
        await self.interpret(handler, history=[turn])
        messages = seen["messages"]
        self.assertEqual([m["role"] for m in messages], ["system", "user", "assistant", "user"])
        previous = json.loads(messages[1]["content"])
        self.assertEqual(previous["text"], "아아 두 개")
        self.assertNotIn("menu", previous)
        self.assertEqual(json.loads(messages[2]["content"])["status"], "needs_confirmation")
        self.assertIn("menu", json.loads(messages[3]["content"]))

    async def test_confirmation_output_is_parsed(self):
        result = await self.interpret(
            openai_output(status="needs_confirmation", reply_text=CONFIRM)
        )
        self.assertEqual(result.status, "needs_confirmation")
        self.assertEqual(result.reply_text, CONFIRM)

    async def test_ignored_output_is_parsed(self):
        result = await self.interpret(openai_output(status="ignored", tool_calls=[]))
        self.assertEqual((result.status, result.tool_calls, result.reply_text), ("ignored", [], None))

    async def test_failures_return_none(self):
        async def slow(request):
            await asyncio.sleep(1)
            return openai_response("{}")

        def offline(request):
            raise httpx.ConnectError("offline", request=request)

        handlers = [
            lambda r: httpx.Response(500),
            offline,
            lambda r: openai_response("not json"),
            lambda r: openai_response("[]"),
            lambda r: httpx.Response(200, json={"choices": []}),
            openai_output(status="ready"),
            openai_output(tool_calls=[]),                       # completed without calls
            openai_output(reply_text="질문"),                    # completed with a question
            openai_output(status="needs_clarification"),        # question missing
            openai_output(status="needs_confirmation"),         # confirmation text missing
            openai_output(status="needs_confirmation", tool_calls=[], reply_text="담을까요?"),
            openai_output(status="needs_confirmation", reply_text="가" * 61),  # too long
            openai_output(status="needs_clarification", tool_calls=[], reply_text="  "),
            openai_output(status="ignored"),                    # ignored with calls
            openai_output(status="ignored", tool_calls=[], reply_text="네?"),  # ignored with text
            openai_output(tool_calls=[{**ADD_AMERICANO, "tool": "pay"}]),
            openai_output(tool_calls=[call("add_cart_item", "americano", "iced", 21)]),
            openai_output(tool_calls=[call("update_cart_item", "americano", "iced", 0)]),
            openai_output(tool_calls=[{"tool": "add_cart_item", "arguments": {
                **ADD_AMERICANO["arguments"], "item_id": "x"}}]),
        ]
        for handler in handlers:
            self.assertIsNone(await self.interpret(handler))
        self.assertIsNone(await self.interpret(slow, timeout=0.05))


if __name__ == "__main__":
    unittest.main()
