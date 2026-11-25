import asyncio
import json
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient

from app.common.config.settings import Settings
from app.infrastructure.external.jev_client import JevClient
from app.main import create_app
from app.modules.decision.jev_questions import STATE_QUESTIONS, shadow_questions, shadow_state
from app.modules.decision.repository import DecisionRepository
from app.modules.decision.rule_table import apply, decide, jev_request, react, tick
from app.modules.decision.schemas import (
    AROUND, BIG, BUSY, HIGHLIGHT, HISTORY_SCORES, NOTICE, PILOT_PARAMS, QUEUE, STALE, WAIT, SessionState, WindowInput,
    WindowRecord,
)
from app.modules.decision.service import DecisionService, window_input
from app.modules.sessions.schemas import FeatureWindowRequest, StateScores

P = PILOT_PARAMS
T0 = datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)


def situation(name, events=("yaw_sweep_offscreen@1", "dwell_no_touch@0"), quality_ok=True):
    return {"name": name, "evidence": [{"event_id": e} for e in events], "confidence": {"events": len(events), "quality_ok": quality_ok}}


def window(t=10.0, measurable=True, **fields):
    return WindowInput(t=t, measurable=measurable, screen="menu", steps_left=2, **fields)


def run(state, *inputs):
    """decide + apply window by window; returns (state, decisions)."""
    decisions = []
    for inp in inputs:
        state, decision = apply(state, decide(inp, state, P))
        decisions.append(decision)
    return state, decisions


class RuleTableTests(unittest.TestCase):
    """The port must behave like ai-engine's rule_table_v0 on the four scenes."""

    def test_a_back_opens_the_highlight_with_a_fit_question_and_progress_withdraws_it(self):
        state, (opened, kept, withdrawn) = run(
            SessionState(),
            window(10.0, backs_recent=1, gaze=True),
            window(12.0, backs_recent=0),
            window(14.0, progress_segment=True),
        )
        self.assertEqual((opened.transition, opened.support, opened.action, opened.decision_id), ("open", HIGHLIGHT, "apply", "d0001"))
        self.assertEqual(opened.form(), ("none", False))
        self.assertEqual(opened.policy["kind"], None, "a fit question needs a known situation; none was judged")
        self.assertIsNone(opened.jev_request)
        self.assertEqual((kept.transition, kept.decision_id), ("keep", "d0001"))
        self.assertEqual((withdrawn.transition, withdrawn.reason), ("withdraw", "withdraw condition cart_progress"))
        self.assertIsNone(state.held)
        self.assertEqual(state.withdrawn[0]["support"], HIGHLIGHT)

    def test_a_known_situation_adds_the_fit_question_in_the_vision_field_names(self):
        _, (opened,) = run(SessionState(), window(10.0, backs_recent=1, gaze=True, situation=situation(AROUND)))
        self.assertEqual(opened.policy["kind"], "fit")
        request = opened.jev_request
        self.assertEqual(set(request), {"state", "questions"})
        self.assertEqual(request["state"]["situation"], {"tag": AROUND, "evidence": {"dwell_no_touch": 1, "yaw_sweep_offscreen": 1}, "dropped_cues": []})
        self.assertEqual(request["state"]["touch"]["backs_recent"], 1)
        self.assertEqual(request["state"]["vision"], {"facing_screen": True, "looking_around": True})
        self.assertEqual(list(request["questions"]), ["proposal_fits"])
        self.assertEqual(request["questions"]["proposal_fits"]["instructions"]["proposed_support"]["name"], HIGHLIGHT)

    def test_a_pause_needs_the_lowered_threshold_only_with_vision(self):
        _, (none, opened) = run(SessionState(), window(10.0, pause_s=5.0), window(12.0, pause_s=5.0, gaze=True))
        self.assertEqual(none.transition, "none")
        self.assertEqual((opened.transition, opened.support, opened.cues["pause_min_s"]), ("open", HIGHLIGHT, P.lost_pause_s_vision))

    def test_companion_opens_the_wait_with_the_hold_timer_and_touch_resumes_withdraws(self):
        state, (opened, kept, withdrawn) = run(
            SessionState(),
            window(10.0, situation=situation(BUSY)),
            window(11.0, measurable=False),
            window(12.0, taps_segment=1),
        )
        self.assertEqual((opened.support, opened.action, opened.session_signal), (WAIT, "wait", {"name": "hold_timer"}))
        self.assertEqual((kept.transition, kept.session_signal), ("keep", None), "a kept wait signals only in a measurable window")
        self.assertEqual(withdrawn.transition, "withdraw")

    def test_people_behind_opens_the_notice_or_the_choice_beside_a_tremor_row(self):
        _, (notice,) = run(SessionState(), window(10.0, situation=situation(QUEUE)))
        self.assertEqual((notice.support, notice.policy["kind"], notice.form()), (NOTICE, "fit", ("step_guide", False)))
        _, (choice,) = run(SessionState(), window(10.0, situation=situation(QUEUE), fixes_recent=2, gaze=True))
        self.assertEqual((choice.support, choice.policy["kind"]), (NOTICE, "choice"))
        self.assertEqual(list(choice.jev_request["questions"]), ["queue_support"])
        self.assertEqual(set(choice.jev_request["questions"]["queue_support"]["criteria"]), {NOTICE, "defer_big_button_question"})

    def test_tremor_asks_for_big_buttons_and_a_refusal_keeps_it_closed(self):
        state, (asked,) = run(SessionState(), window(10.0, fixes_recent=2, gaze=True, situation=situation(AROUND)))
        self.assertEqual((asked.support, asked.action, asked.form()), (BIG, "propose", ("large_button", True)))
        state = react(state, "refuse", decision_id=asked.decision_id)
        self.assertEqual(state.refused, [BIG])
        _, (again,) = run(state, window(12.0, fixes_recent=3, gaze=True))
        self.assertNotEqual(again.support, BIG)
        # Without a gaze the criterion is raised and no Jev question is asked.
        _, (raised,) = run(SessionState(), window(10.0, fixes_recent=3))
        self.assertEqual((raised.support, raised.policy["ask_jev"], raised.cues["raised"]), (BIG, False, True))

    def test_an_unanswered_ask_is_withdrawn_after_no_response(self):
        state, (asked,) = run(SessionState(), window(10.0, fixes_recent=2, gaze=True))
        state, withdrawn = tick(state, 10.0 + P.no_response_s, P)
        self.assertEqual(withdrawn, asked.decision_id)
        self.assertEqual(state.withdrawn[0]["reason"], "no_response")

    def test_an_unknown_situation_continues_the_previous_tag(self):
        state, (opened, kept) = run(
            SessionState(), window(10.0, situation=situation(BUSY)), window(11.0, situation={"name": "unknown"}),
        )
        self.assertEqual((kept.transition, kept.meta["tag"], kept.meta["situation_known"]), ("keep", BUSY, False))


class ShadowQuestionTests(unittest.TestCase):
    def test_one_state_question_per_contract_score(self):
        self.assertEqual(set(STATE_QUESTIONS), set(StateScores.model_fields))
        self.assertTrue(all(q["type"] == "noul" for q in STATE_QUESTIONS.values()))

    def test_the_decision_question_joins_the_state_questions(self):
        _, (opened,) = run(SessionState(), window(10.0, backs_recent=1, gaze=True, situation=situation(AROUND)))
        self.assertEqual(set(shadow_questions(opened)), set(STATE_QUESTIONS) | {"proposal_fits"})
        _, (none,) = run(SessionState(), window(10.0))
        self.assertEqual(set(shadow_questions(none)), set(STATE_QUESTIONS))

    def test_the_state_keeps_the_rule_table_names_and_adds_the_raw_touch_counts(self):
        request = FeatureWindowRequest(screen_id="menu", window_start=T0, window_end=T0 + timedelta(seconds=2),
                                       touch={"tap_count": 4, "miss_tap_count": 3, "repeat_tap_count": 2, "back_count": 1, "dwell_ms": 12000})
        inp = window_input(request, measurable=True)
        state = shadow_state(inp, SessionState(), request.touch)
        self.assertEqual(state["touch"], {"misses_recent": 3, "fixes_recent": None, "backs_recent": 1, "pause_s": None,
                                          "tap_count": 4, "miss_tap_count": 3, "repeat_tap_count": 2, "back_count": 1, "dwell_ms": 12000})
        self.assertEqual(state["screen"], {"name": "menu", "steps_left": 2}, "menu -> review -> complete")
        self.assertEqual(state["situation"]["tag"], None)
        self.assertEqual(json.dumps(state), json.dumps(json.loads(json.dumps(state))), "plain JSON only")


    def test_a_touch_field_the_contract_adds_later_does_not_reach_the_jev_state(self):
        class Extended(type(feature_window().touch)):
            interaction: dict | None = None

        touch = Extended(tap_count=4, miss_tap_count=3, repeat_tap_count=2, back_count=1, dwell_ms=12000,
                         interaction={"visit_id": "v1", "ui_settings": {"large_button": True}})
        state = shadow_state(window_input(feature_window(), measurable=True), SessionState(), touch)
        self.assertEqual(set(state["touch"]), {"misses_recent", "fixes_recent", "backs_recent", "pause_s", "tap_count",
                                               "miss_tap_count", "repeat_tap_count", "back_count", "dwell_ms"})
        self.assertNotIn("visit_id", json.dumps(state))


RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {name: {"type": "noul", "noul": 0.5} for name in STATE_QUESTIONS} | {"proposal_fits": {"type": "noul", "noul": 0.8}},
    "usage": {"input_tokens": 900, "output_tokens": 98},
}


def feature_window(back_count=1):
    return FeatureWindowRequest(screen_id="menu", window_start=T0, window_end=T0 + timedelta(seconds=2),
                                touch={"tap_count": 1, "miss_tap_count": 0, "repeat_tap_count": 0, "back_count": back_count, "dwell_ms": 3000})


def ending_at(seconds, screen="menu", back_count=0, tap_count=1):
    """A two-second /features window ending `seconds` after T0."""
    return FeatureWindowRequest(screen_id=screen, window_start=T0 + timedelta(seconds=seconds - 2), window_end=T0 + timedelta(seconds=seconds),
                                touch={"tap_count": tap_count, "miss_tap_count": 0, "repeat_tap_count": 0, "back_count": back_count, "dwell_ms": 1000})


class DecisionServiceTests(unittest.IsolatedAsyncioTestCase):
    def service(self, handler):
        self.http = httpx.AsyncClient(base_url="https://api.typesafe.ai", transport=httpx.MockTransport(handler))
        self.repository = DecisionRepository()
        return DecisionService(self.repository, P, JevClient(self.http, "jev-1.13.0", 3.0))

    async def asyncTearDown(self):
        if getattr(self, "http", None) is not None:
            await self.http.aclose()

    async def test_observe_runs_the_table_and_records_the_shadow_answer_in_the_background(self):
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=RESPONSE)

        service = self.service(handler)
        decision = service.observe("s1", feature_window(), measurable=True)
        self.assertEqual((decision.transition, decision.support), ("open", HIGHLIGHT))
        self.assertEqual(self.repository.records("s1"), [], "the response does not wait for Jev")
        await service.drain()
        (record,) = self.repository.records("s1")
        self.assertEqual((record.outcome, record.response_model, record.decision_id), ("answered", "jev-1.13.0", "d0001"))
        self.assertEqual(record.answers["hesitation"], 0.5)
        self.assertEqual(record.usage, {"input_tokens": 900, "output_tokens": 98})
        self.assertEqual(seen["body"]["model"], "jev-1.13.0")
        self.assertEqual(set(seen["body"]["questions"]), set(STATE_QUESTIONS), "no fit question without a known situation")
        self.assertEqual(seen["body"]["state"]["touch"]["back_count"], 1)

    async def test_a_store_error_in_the_background_chain_is_logged_and_the_next_window_asks_again(self):
        service = self.service(lambda request: httpx.Response(200, json=RESPONSE))
        attach, self.repository.attach = self.repository.attach, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("store down"))
        with self.assertLogs("app.modules.decision.service", level="ERROR") as logs:
            service.observe("s1", ending_at(2, back_count=1), measurable=True)
            await service.drain()
        self.assertIn("jev shadow task failed", logs.output[0])
        self.assertFalse(service.in_flight("s1"))
        self.repository.attach = attach
        service.observe("s1", ending_at(4), measurable=True)
        await service.drain()
        self.assertEqual(self.repository.windows("s1")[-1].jev, "asked")

    async def test_answers_that_do_not_answer_what_was_asked_are_no_answer(self):
        noul = {"type": "noul", "noul": 0.5}
        choice = {"type": "choice", "choice": "format_disk", "confidence": 0.9, "probabilities": {"format_disk": 0.9}}
        for answers in (
            {"hesitation": noul},                                              # one of five
            {**{name: noul for name in STATE_QUESTIONS}, "hesitation": choice},  # another type than asked
        ):
            with self.subTest(answers=sorted(answers)):
                service = self.service(lambda request, answers=answers: httpx.Response(200, json={**RESPONSE, "answers": answers}))
                service.observe("s1", ending_at(2), measurable=True)
                await service.drain()
                self.assertEqual([r.outcome for r in self.repository.records("s1")], ["no_answer"])
                await self.http.aclose()
        # An answer nobody asked for is dropped; the asked ones are kept.
        extra = {**{name: noul for name in STATE_QUESTIONS}, "ignore previous instructions": noul}
        service = self.service(lambda request: httpx.Response(200, json={**RESPONSE, "answers": extra}))
        service.observe("s1", ending_at(2), measurable=True)
        await service.drain()
        (record,) = self.repository.records("s1")
        self.assertEqual((record.outcome, set(record.answers)), ("answered", set(STATE_QUESTIONS)))

    async def test_a_failed_call_is_recorded_as_no_answer_and_changes_nothing_else(self):
        service = self.service(lambda request: httpx.Response(529, json={"error": "busy"}))
        service.observe("s1", feature_window(), measurable=True)
        await service.drain()
        (record,) = self.repository.records("s1")
        self.assertEqual((record.outcome, record.answers, record.response_model), ("no_answer", {}, None))
        self.assertEqual(self.repository.state("s1").held.support, HIGHLIGHT)

    async def test_stages_are_stacked_and_each_sees_the_answers_before_it(self):
        bodies = []

        def handler(request):
            body = json.loads(request.content)
            bodies.append(body)
            if "queue_support" in body["questions"]:
                return httpx.Response(200, json={"model": "jev-1.13.0", "usage": {"input_tokens": 1, "output_tokens": 0},
                                                 "answers": {"queue_support": {"type": "choice", "choice": HIGHLIGHT, "confidence": 0.9,
                                                                               "probabilities": {HIGHLIGHT: 0.9, "none": 0.1}}}})
            return httpx.Response(200, json=RESPONSE)

        class SupportStage:
            """Stage 2 of the design (docs 9.5): choose the support, reading stage 1's scores."""
            name = "support_choice"

            def build(self, ctx):
                scores = ctx.previous.get("state_scores")
                if scores is None:
                    return None
                return ({"scores": scores, "held": ctx.decision.support},
                        {"queue_support": {"type": "choice", "instructions": "Pick one.",
                                           "criteria": {HIGHLIGHT: "guide", "none": "nothing"}}})

        from app.modules.decision.jev_questions import ScoreStage
        service = self.service(handler)
        service = DecisionService(self.repository, P, JevClient(self.http, "jev-1.13.0", 3.0), stages=(ScoreStage(), SupportStage()))
        service.observe("s1", feature_window(), measurable=True)
        await service.drain()
        first, second = self.repository.records("s1")
        self.assertEqual((first.stage, second.stage), ("state_scores", "support_choice"))
        # The record keeps the validated answer whole (docs 5 #6), probabilities included.
        self.assertEqual(second.answers["queue_support"], {"type": "choice", "choice": HIGHLIGHT, "confidence": 0.9,
                                                           "probabilities": {HIGHLIGHT: 0.9, "none": 0.1}})
        self.assertEqual(self.repository.windows("s1")[0].answers["support_choice"], second.answers)
        self.assertEqual(bodies[1]["state"]["scores"]["hesitation"], 0.5, "stage 2 read stage 1's answers")
        self.assertNotIn("jev", bodies[0]["state"], "stage 1 has nothing before it")

    async def test_one_call_per_session_at_a_time(self):
        gate = asyncio.Event()
        calls = []

        async def slow(request):
            calls.append(json.loads(request.content)["state"]["touch"]["back_count"])
            await gate.wait()
            return httpx.Response(200, json=RESPONSE)

        service = self.service(slow)
        service.observe("s1", ending_at(2, back_count=1), measurable=True)
        await asyncio.sleep(0)  # let the first call start
        service.observe("s1", ending_at(4, back_count=2), measurable=True)   # skipped: s1 is in flight
        service.observe("s2", ending_at(2, back_count=3), measurable=True)   # another session is not held back
        self.assertTrue(service.in_flight("s1"))
        gate.set()
        await service.drain()
        self.assertEqual(sorted(calls), [1, 3])
        self.assertFalse(service.in_flight("s1"))
        service.observe("s1", ending_at(6, back_count=4), measurable=True)   # asked again once free
        await service.drain()
        self.assertEqual(sorted(calls), [1, 3, 4])

    async def test_no_client_or_not_measurable_asks_nothing(self):
        service = DecisionService(DecisionRepository(), P, None)
        self.assertFalse(service.shadow)
        service.observe("s1", feature_window(), measurable=True)
        calls = []
        service = self.service(lambda request: calls.append(1) or httpx.Response(200, json=RESPONSE))
        service.observe("s2", feature_window(), measurable=False)
        await service.drain()
        self.assertEqual(calls, [])

    async def test_a_late_window_is_recorded_without_rolling_the_session_back(self):
        """Overlapping /features requests: the 4 s window's ai-engine answer arrives after the 6 s window's
        (backend and vision reviews of #77). In time order it is open, keep, withdraw; the late window must not
        reopen the withdrawn highlight under a new id."""
        calls = []
        service = self.service(lambda request: calls.append(1) or httpx.Response(200, json=RESPONSE))
        opened = service.observe("s1", ending_at(2, back_count=1), measurable=True)
        await service.drain()
        withdrawn = service.observe("s1", ending_at(6, screen="review"), measurable=True)
        await service.drain()
        late = service.observe("s1", ending_at(4, back_count=1), measurable=True)
        await service.drain()
        self.assertEqual((opened.transition, withdrawn.transition, late.transition), ("open", "withdraw", "none"))
        state = self.repository.state("s1")
        self.assertIsNone(state.held, "the withdrawn highlight stays withdrawn")
        self.assertEqual(state.next_id, 2, "no new decision id was handed out")
        self.assertEqual(state.last_t, (T0 + timedelta(seconds=6)).timestamp())
        rows = self.repository.windows("s1")
        self.assertEqual([r.jev for r in rows], ["asked", "asked", STALE])
        self.assertEqual(rows[-1].inputs["backs_recent"], 1, "the late window is still a comparison row")
        self.assertEqual(len(calls), 2, "Jev is not asked about a late window")
        self.assertEqual(len(self.repository.history("s1")), 2, "the trajectory reads judged windows only")
        # The next window reads its previous screen from the last judged window (review), not the late one.
        service.observe("s1", ending_at(8, screen="complete"), measurable=True)
        self.assertIs(self.repository.windows("s1")[-1].inputs["progress_segment"], True)

    async def test_an_answer_goes_to_its_own_window_only(self):
        """The window skipped while the first call is in flight, and a resend of the first, get no answer."""
        gate = asyncio.Event()
        calls = []

        async def slow(request):
            calls.append(1)
            await gate.wait()
            return httpx.Response(200, json=RESPONSE)

        service = self.service(slow)
        service.observe("s1", ending_at(2, back_count=1), measurable=True)
        await asyncio.sleep(0)
        service.observe("s1", ending_at(2, back_count=1), measurable=True)   # the same window sent again
        service.observe("s1", ending_at(4), measurable=True)                 # skipped: s1 is in flight
        gate.set()
        await service.drain()
        asked, resent, skipped = self.repository.windows("s1")
        self.assertEqual(len(calls), 1)
        self.assertEqual((asked.jev, asked.outcomes), ("asked", {"state_scores": "answered"}))
        self.assertEqual((resent.jev, resent.outcomes, resent.answers), (STALE, {}, {}))
        self.assertEqual((skipped.jev, skipped.outcomes, skipped.answers), ("skipped_in_flight", {}, {}))

    async def test_a_window_sent_twice_is_judged_and_asked_about_once(self):
        # Review of the whole PR (381425f): an equal end time was judged again, opened its row's keep a second
        # time and asked Jev twice. #95: a resent window never yields a second proposal.
        calls = []

        async def handler(request):
            calls.append(1)
            return httpx.Response(200, json=RESPONSE)

        service = self.service(handler)
        for _ in range(2):
            service.observe("s1", ending_at(2, back_count=1), measurable=True)
            await service.drain()
        first, again = self.repository.windows("s1")
        self.assertEqual((first.jev, first.decision["transition"]), ("asked", "open"))
        self.assertEqual(again.jev, STALE)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.repository.state("s1").last_t, first.t)

    async def test_a_stage_that_fails_before_the_call_has_no_answer_and_the_next_stage_runs(self):
        from app.modules.decision.jev_questions import ScoreStage

        class BrokenStage:
            name = "broken"

            def build(self, ctx):
                raise RuntimeError("question could not be built")

        self.service(lambda request: httpx.Response(200, json=RESPONSE))
        service = DecisionService(self.repository, P, JevClient(self.http, "jev-1.13.0", 3.0), stages=(BrokenStage(), ScoreStage()))
        with self.assertLogs("app.modules.decision.service", "ERROR"):
            service.observe("s1", feature_window(), measurable=True)
            await service.drain()
        broken, scores = self.repository.records("s1")
        self.assertEqual((broken.stage, broken.outcome, broken.questions), ("broken", "no_answer", ()))
        self.assertEqual((broken.reason, scores.reason), ("build_error", None))
        self.assertIsNone(broken.answered_at, "no call was made")
        self.assertEqual((scores.stage, scores.outcome, scores.previous_missing), ("state_scores", "answered", ("broken",)))
        self.assertEqual(self.repository.windows("s1")[0].outcomes, {"broken": "no_answer", "state_scores": "answered"})

    async def test_a_question_that_cannot_be_sent_is_a_build_error_and_its_state_is_not_logged(self):
        # Round 2 of the self-review: a stage of the wrong shape killed the whole chain, and a state that does
        # not serialise read as a Jev outage with the state's contents in the log.
        from app.modules.decision.jev_questions import ScoreStage

        class WrongShape:
            name = "wrong_shape"

            def build(self, ctx):
                return {"a": 1}, {}, "extra"

        class Unsendable:
            name = "unsendable"

            def build(self, ctx):
                return {"secret_field_name": {1, 2}}, {"q": {"type": "noul", "description": "?"}}

        class NotJson:
            name = "not_json"

            def build(self, ctx):
                return {"score": float("nan")}, {"q": {"type": "noul", "description": "?"}}

        self.service(lambda request: httpx.Response(200, json=RESPONSE))
        jev = JevClient(self.http, "jev-1.13.0", 3.0)
        asked = []
        real_ask = jev.ask

        async def ask(request):
            asked.append(set(request.questions))   # counted before httpx, which itself refuses a NaN body
            return await real_ask(request)

        jev.ask = ask
        service = DecisionService(self.repository, P, jev, stages=(WrongShape(), Unsendable(), NotJson(), ScoreStage()))
        with self.assertLogs("app.modules.decision.service", "INFO") as logs:
            service.observe("s1", feature_window(), measurable=True)
            await service.drain()
        wrong, unsendable, not_json, scores = self.repository.records("s1")
        self.assertEqual([(r.stage, r.outcome, r.reason) for r in (wrong, unsendable, not_json)],
                         [("wrong_shape", "no_answer", "build_error"), ("unsendable", "no_answer", "build_error"),
                          ("not_json", "no_answer", "build_error")])
        self.assertEqual((wrong.questions, unsendable.questions), ((), ("q",)), "the names built before the failure")
        self.assertEqual((scores.outcome, scores.previous_missing), ("answered", ("wrong_shape", "unsendable", "not_json")))
        self.assertNotIn("secret_field_name", "\n".join(logs.output))
        self.assertTrue(any("(ValidationError at service.py:" in line for line in logs.output), "where our code failed")
        self.assertEqual(len(asked), 1, "only state_scores was asked: a request built before its failure is not sent")
        self.assertNotIn("q", asked[0])
        self.assertEqual(self.repository.windows("s1")[0].outcomes,
                         {"wrong_shape": "no_answer", "unsendable": "no_answer", "not_json": "no_answer",
                          "state_scores": "answered"})

    async def test_no_answer_says_why_so_a_jev_fault_is_not_counted_as_a_wrong_answer(self):
        # Convention 7 (system fault apart from the rest), #95 (Jev outage, wrong answer, deadline).
        wrong = {**RESPONSE, "answers": {**RESPONSE["answers"], "normal": {"type": "choice", "choice": "x", "confidence": 0.5, "probabilities": {"x": 1.0}}}}
        cases = {
            "http 500": (lambda request: httpx.Response(500, json={}), "unavailable", None, None),
            "timeout": (None, "unavailable", None, None),
            "wrong answer type": (lambda request: httpx.Response(200, json=wrong), "mismatch", "jev-1.13.0",
                                  RESPONSE["usage"]),
        }
        for name, (handler, reason, model, usage) in cases.items():
            with self.subTest(name):
                if handler is None:
                    def handler(request):
                        raise httpx.ReadTimeout("slow")
                service = self.service(handler)
                service.observe("s1", feature_window(), measurable=True)
                await service.drain()
                (record,) = self.repository.records("s1")
                self.assertEqual((record.outcome, record.reason, record.answers), ("no_answer", reason, {}))
                self.assertEqual((record.response_model, record.usage), (model, usage), "billed tokens are kept")
                self.assertIsNotNone(record.answered_at)

    async def test_records_carry_server_times_and_versions(self):
        from app.modules.decision.schemas import QUESTIONS_VERSION, RULES_VERSION

        wall = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
        self.service(lambda request: httpx.Response(200, json=RESPONSE))
        service = DecisionService(self.repository, P, JevClient(self.http, "jev-1.13.0", 3.0), wall=lambda: wall)
        service.observe("s1", feature_window(), measurable=True, ai="ok", ai_model_version="dummy-0.1")
        await service.drain()
        (window,), (record,) = self.repository.windows("s1"), self.repository.records("s1")
        self.assertEqual((window.received_at, window.ai_model_version, window.rules_version),
                         (wall, "dummy-0.1", RULES_VERSION))
        self.assertEqual((record.answered_at, record.questions_version, record.reason), (wall, QUESTIONS_VERSION, None))

    async def test_stages_without_a_client_warn_and_are_marked_apart_from_off(self):
        from app.modules.decision.jev_questions import ScoreStage

        repository = DecisionRepository()
        with self.assertLogs("app.modules.decision.service", "WARNING") as logs:
            service = DecisionService(repository, P, None, stages=(ScoreStage(),))
        self.assertIn("JEV_STAGES=state_scores", logs.output[0])
        service.observe("s1", feature_window(), measurable=True)
        self.assertEqual(repository.windows("s1")[0].jev, "no_client")


class StageArmTests(unittest.IsolatedAsyncioTestCase):
    """The experiment arms: rule table alone, one Jev stage, two stacked stages (docs 7, 9.5)."""

    def test_jev_stages_setting_builds_the_chain_or_turns_jev_off(self):
        from app.modules.decision.jev_questions import build_stages

        self.assertEqual(Settings(_env_file=None).jev_stages, "off", "a key alone never starts paid calls")
        self.assertEqual(build_stages(Settings(_env_file=None, jev_api_key="jev-secret-value").jev_stages), ())
        self.assertEqual([s.name for s in build_stages("state_scores")], ["state_scores"])
        self.assertEqual([s.name for s in build_stages(" State_Scores , SUPPORT_CHOICE ")], ["state_scores", "support_choice"])
        self.assertEqual(build_stages("OFF"), ())
        self.assertEqual([s.name for s in build_stages(" state_scores , support_choice ")], ["state_scores", "support_choice"])
        self.assertEqual(build_stages("off"), ())
        self.assertEqual(build_stages(""), ())
        with self.assertRaises(ValueError):
            build_stages("state_scores,guess")
        with self.assertRaises(ValueError):
            build_stages("state_scores,state_scores")

    async def test_off_arm_runs_the_rule_table_and_never_asks_even_with_a_client(self):
        calls = []
        http = httpx.AsyncClient(base_url="https://api.typesafe.ai", transport=httpx.MockTransport(lambda r: calls.append(1) or httpx.Response(200, json=RESPONSE)))
        repository = DecisionRepository()
        service = DecisionService(repository, P, JevClient(http, "jev-1.13.0", 3.0), stages=())
        self.assertFalse(service.shadow)
        decision = service.observe("s1", feature_window(), measurable=True)
        await service.drain()
        await http.aclose()
        self.assertEqual((decision.support, calls, repository.records("s1")), (HIGHLIGHT, [], []))

    async def test_support_choice_stage_offers_the_allowed_candidates_and_none(self):
        from app.modules.decision.jev_questions import SupportChoiceStage, ScoreStage

        bodies = []

        def handler(request):
            body = json.loads(request.content)
            bodies.append(body)
            if "support_choice" in body["questions"]:
                return httpx.Response(200, json={"model": "jev-1.13.0", "usage": {"input_tokens": 1, "output_tokens": 0},
                                                 "answers": {"support_choice": {"type": "choice", "choice": "none", "confidence": 0.6,
                                                                                "probabilities": {HIGHLIGHT: 0.4, "none": 0.6}}}})
            return httpx.Response(200, json=RESPONSE)

        http = httpx.AsyncClient(base_url="https://api.typesafe.ai", transport=httpx.MockTransport(handler))
        repository = DecisionRepository()
        service = DecisionService(repository, P, JevClient(http, "jev-1.13.0", 3.0), stages=(ScoreStage(), SupportChoiceStage(P)))
        self.assertEqual(service.stage_names, ("state_scores", "support_choice"))
        # A back press: the highlight row is the only candidate.
        service.observe("s1", feature_window(back_count=1), measurable=True)
        await service.drain()
        self.assertEqual([r.stage for r in repository.records("s1")], ["state_scores", "support_choice"])
        choice = bodies[1]["questions"]["support_choice"]
        self.assertEqual(list(choice["criteria"]), [HIGHLIGHT, "none"])
        self.assertEqual(bodies[1]["state"]["candidates"], [HIGHLIGHT])
        self.assertEqual(bodies[1]["state"]["jev"]["state_scores"]["hesitation"], 0.5)
        self.assertEqual(repository.records("s1")[1].answers["support_choice"]["choice"], "none")
        # A quiet window opens no row: stage 2 is skipped, stage 1 still runs.
        service.observe("s2", feature_window(back_count=0), measurable=True)
        await service.drain()
        await http.aclose()
        self.assertEqual([r.stage for r in repository.records("s2")], ["state_scores"])


class TrajectoryStageTests(unittest.IsolatedAsyncioTestCase):
    async def test_next_difficulty_reads_the_previous_windows_with_their_scores(self):
        from app.modules.decision.jev_questions import NextDifficultyStage, ScoreStage

        bodies = []

        def handler(request):
            body = json.loads(request.content)
            bodies.append(body)
            if "next_difficulty" in body["questions"]:
                return httpx.Response(200, json={"model": "jev-1.13.0", "usage": {"input_tokens": 1, "output_tokens": 0},
                                                 "answers": {"next_difficulty": {"type": "choice", "choice": "navigation_difficulty", "confidence": 0.7,
                                                                                 "probabilities": {"navigation_difficulty": 0.7, "none": 0.3}}}})
            return httpx.Response(200, json=RESPONSE)

        http = httpx.AsyncClient(base_url="https://api.typesafe.ai", transport=httpx.MockTransport(handler))
        repository = DecisionRepository()
        service = DecisionService(repository, P, JevClient(http, "jev-1.13.0", 3.0), stages=(ScoreStage(), NextDifficultyStage()))
        # First window: no trajectory yet, the forecast stage is skipped.
        service.observe("s1", feature_window(back_count=0), measurable=True)
        await service.drain()
        self.assertEqual([r.stage for r in repository.records("s1")], ["state_scores"])
        # Second window, two seconds later: the forecast sees the first window with its scores.
        later = FeatureWindowRequest(screen_id="menu", window_start=T0 + timedelta(seconds=2), window_end=T0 + timedelta(seconds=4),
                                     touch={"tap_count": 0, "miss_tap_count": 0, "repeat_tap_count": 0, "back_count": 1, "dwell_ms": 5000})
        service.observe("s1", later, measurable=True)
        await service.drain()
        self.assertEqual([r.stage for r in repository.records("s1")][-2:], ["state_scores", "next_difficulty"])
        forecast = bodies[-1]
        (first,) = forecast["state"]["history"]
        self.assertEqual((first["t_offset_s"], first["screen"], first["decision"], first["touch"]["backs"]), (-2.0, "menu", "none", 0))
        self.assertEqual(first["state_scores"]["hesitation"], 0.5, "the earlier window carries its stage-1 scores")
        self.assertNotIn("t", first)
        self.assertEqual(forecast["state"]["jev"]["state_scores"]["normal"], 0.5, "and this window's own scores are beside it")
        self.assertEqual(repository.records("s1")[-1].answers["next_difficulty"]["choice"], "navigation_difficulty")
        # Third window: the second one carries its stage-1 scores but not its own forecast (docs 9.6).
        service.observe("s1", ending_at(6), measurable=True)
        await service.drain()
        older, newer = bodies[-1]["state"]["history"]
        self.assertEqual(newer["state_scores"]["hesitation"], 0.5)
        self.assertNotIn("next_difficulty", newer, "a forecast never reads the forecasts before it")
        # The trajectory sees at most HISTORY_WINDOWS windows; every window stays in the session's records.
        from app.modules.decision.schemas import HISTORY_WINDOWS
        for i in range(HISTORY_WINDOWS + 3):
            service.observe("s1", ending_at(8 + 2 * i), measurable=False)   # remembered, not asked
        await http.aclose()
        self.assertEqual(len(repository.history("s1")), HISTORY_WINDOWS)
        self.assertEqual(len(repository.windows("s1")), HISTORY_WINDOWS + 6)


    async def test_the_forecast_after_a_clock_set_back_carries_this_timelines_windows_only(self):
        from app.modules.decision.jev_questions import NextDifficultyStage

        states = []

        def handler(request):
            states.append(json.loads(request.content)["state"])
            return httpx.Response(200, json={"model": "jev-1.13.0", "usage": {"input_tokens": 1, "output_tokens": 0},
                                             "answers": {"next_difficulty": {"type": "choice", "choice": "none", "confidence": 0.7,
                                                                             "probabilities": {"none": 1.0}}}})

        http = httpx.AsyncClient(base_url="https://api.typesafe.ai", transport=httpx.MockTransport(handler))
        clock = {"now": 1000.0}
        service = DecisionService(DecisionRepository(), P, JevClient(http, "jev-1.13.0", 3.0), stages=(NextDifficultyStage(),),
                                  now=lambda: clock["now"])
        for seconds in (1000, 1002, 3000, 1008, 1010, 1012):       # 3000: 2,000 s pass; then the clock is set back
            clock["now"] += 1998.0 if seconds == 3000 else 2.0
            service.observe("s1", ending_at(seconds), measurable=True)
            await service.drain()
        await http.aclose()
        self.assertEqual([[h["t_offset_s"] for h in state["history"]] for state in states],
                         [[-2.0], [-1998.0, -2000.0][::-1], [-2.0]],
                         "1010 has no window of its timeline before it and is not asked; 1012 sees 1010 only")


class ObservationTests(unittest.TestCase):
    """What the Jev state asserts, and what the backend fills from the screen id (vision review of #77)."""

    def test_an_unknown_or_missing_situation_asserts_nothing_about_looking_around(self):
        from app.modules.decision.rule_table import jev_state

        for sit, expected in [(None, (None, None)), ({"name": "unknown"}, (None, None)),
                              (situation(BUSY), (BUSY, False)), (situation(AROUND), (AROUND, True))]:
            with self.subTest(situation=sit):
                state = jev_state(window(10.0, situation=sit), SessionState())
                self.assertEqual((state["situation"]["tag"], state["vision"]["looking_around"]), expected)

    def test_screen_order_gives_steps_left_and_progress_withdraws_the_highlight(self):
        repository = DecisionRepository()
        service = DecisionService(repository, P, None)

        def at(seconds, screen, back_count=0):
            return FeatureWindowRequest(screen_id=screen, window_start=T0 + timedelta(seconds=seconds - 2), window_end=T0 + timedelta(seconds=seconds),
                                        touch={"tap_count": 1, "miss_tap_count": 0, "repeat_tap_count": 0, "back_count": back_count, "dwell_ms": 1000})

        opened = service.observe("s1", at(2, "menu", back_count=1), measurable=True)
        self.assertEqual((opened.transition, opened.support, opened.execution["steps_left"]), ("open", HIGHLIGHT, 2))
        withdrawn = service.observe("s1", at(4, "review"), measurable=True)
        self.assertEqual((withdrawn.transition, withdrawn.reason), ("withdraw", "withdraw condition cart_progress"))
        done = service.observe("s1", at(6, "complete"), measurable=True)
        self.assertEqual((done.transition, done.meta["screen"]), ("none", "complete"))
        inputs = [w.inputs for w in repository.windows("s1")]
        self.assertEqual([i["steps_left"] for i in inputs], [2, 1, 0])
        self.assertEqual([i["progress_segment"] for i in inputs], [None, True, True])
        # A back to the menu is not progress; an unknown screen id gives no steps.
        back = service.observe("s1", at(8, "menu"), measurable=True)
        self.assertIs(repository.windows("s1")[-1].inputs["progress_segment"], False)
        self.assertIsNone(service.observe("s1", at(10, "menu_list"), measurable=True).execution.get("steps_left"))

    def test_progress_is_unknown_outside_the_screen_flow_and_a_skipped_screen_is_still_forward(self):
        repository = DecisionRepository()
        service = DecisionService(repository, P, None)
        # The voice API's ids are not the flow's: nothing is asserted about progress between them.
        service.observe("s1", ending_at(2, "menu_list"), measurable=True)
        service.observe("s1", ending_at(4, "order_review"), measurable=True)
        service.observe("s1", ending_at(6, "menu"), measurable=True)
        self.assertEqual([w.inputs["progress_segment"] for w in repository.windows("s1")], [None, None, None])
        # The review window was lost (a skipped request): menu, then complete, is progress and withdraws 4-2.
        opened = service.observe("s2", ending_at(2, "menu", back_count=1), measurable=True)
        self.assertEqual((opened.transition, opened.support), ("open", HIGHLIGHT))
        jumped = service.observe("s2", ending_at(4, "complete"), measurable=True)
        self.assertIs(repository.windows("s2")[-1].inputs["progress_segment"], True)
        self.assertEqual(jumped.transition, "withdraw")

    def timed(self):
        """A service on a server clock the test moves: 2 s pass before every window unless told otherwise."""
        repository, clock = DecisionRepository(), {"now": 1000.0}
        service = DecisionService(repository, P, None, now=lambda: clock["now"])

        def send(seconds, screen="menu", back_count=0, passed=2.0):
            clock["now"] += passed
            return service.observe("s1", ending_at(seconds, screen, back_count), measurable=True)

        return repository, send

    def stale(self, repository):
        return [w.jev == STALE for w in repository.windows("s1")]

    def test_a_late_window_never_sends_the_session_back_however_late(self):
        # Reviews of #77: the session went on to 124 s; the window that ended at 2 s arrives after it.
        repository, send = self.timed()
        send(120), send(122, "review"), send(124, "review")
        late = send(2, back_count=1)
        self.assertEqual((late.transition, self.stale(repository)), ("none", [False, False, False, True]))
        self.assertEqual(repository.state("s1").last_t, T0.timestamp() + 124)
        self.assertIsNone(repository.state("s1").held, "the back on the late window opens nothing")
        self.assertEqual([h["t"] - T0.timestamp() for h in repository.history("s1")], [120, 122, 124])

    def test_one_wrong_time_costs_that_window_only(self):
        for wrong in (86400, -86400):      # a day ahead, a day behind
            with self.subTest(wrong=wrong):
                repository, send = self.timed()
                send(2), send(4), send(wrong + 6)
                opened = send(8, back_count=1)
                send(10), send(12, "review")
                self.assertEqual(self.stale(repository), [False, False, True, False, False, False])
                self.assertEqual((opened.transition, opened.support), ("open", HIGHLIGHT))
                self.assertEqual(repository.state("s1").last_t, T0.timestamp() + 12)

    def test_a_wrong_first_window_does_not_shut_out_the_session_or_stay_in_the_history(self):
        repository, send = self.timed()
        send(86400)                                       # the very first window is a day ahead
        send(4)                                           # off that timeline: recorded, waiting for the next
        opened = send(6, back_count=1)                    # follows it: the session's times move here
        send(8)
        self.assertEqual(self.stale(repository), [False, True, False, False])
        self.assertEqual((opened.transition, opened.support), ("open", HIGHLIGHT))
        history = repository.history("s1", repository.state("s1").epoch)
        self.assertEqual([h["t"] - T0.timestamp() for h in history], [6, 8], "the day-ahead window is not shown to Jev")

    def test_a_clock_set_during_the_session_is_followed_from_the_second_window_on(self):
        repository, send = self.timed()
        send(2), send(4, back_count=1)                    # 4-2 opens
        send(1806), send(1808), send(1810), send(1812, "review")     # the frontend clock was set 30 min ahead
        self.assertEqual(self.stale(repository), [False, False, True, False, False, False])
        self.assertEqual(repository.windows("s1")[-1].decision["transition"], "withdraw", "progress still withdraws 4-2")
        state = repository.state("s1")
        self.assertEqual((state.last_t, state.epoch), (T0.timestamp() + 1812, 1))
        self.assertEqual([h["t"] - T0.timestamp() for h in repository.history("s1", state.epoch)], [1808, 1810, 1812])

    def test_a_clock_set_back_leaves_the_windows_before_it_out_of_the_history_and_the_previous_screen(self):
        # Review of #77: after the clock moves back, the two timelines overlap in time; only the epoch tells them apart.
        repository, send = self.timed()
        send(1000, "menu"), send(3000, "review", back_count=1, passed=2000)     # 4-2 opens on the review screen
        send(1004, "review"), send(1006, "review"), send(1008, "review")        # the clock was set back by 2,000 s
        self.assertEqual(self.stale(repository), [False, False, True, False, False])
        state = repository.state("s1")
        self.assertEqual((state.last_t, state.epoch), (T0.timestamp() + 1008, 1))
        self.assertEqual([h["t"] - T0.timestamp() for h in repository.history("s1", state.epoch)], [1006, 1008],
                         "not the window at 1000 of the timeline before")
        moved_on = repository.windows("s1")[-2]
        self.assertIs(moved_on.inputs["progress_segment"], False,
                      "compared with the review window just before it, not with the menu window of the timeline before")
        self.assertEqual(repository.windows("s1")[-1].decision["transition"], "keep", "the screen did not change: 4-2 stays")

    def test_a_screen_change_that_falls_on_the_clock_move_is_still_progress(self):
        repository, send = self.timed()
        send(2), send(4, back_count=1)                                        # 4-2 opens on the menu
        send(1806, "review"), send(1808, "review"), send(1810, "review")      # the clock moved ahead while the screen changed
        self.assertEqual(self.stale(repository), [False, False, True, False, False])
        crossed = repository.windows("s1")[-2]
        self.assertIs(crossed.inputs["progress_segment"], True, "menu before the move, review after it")
        self.assertEqual(crossed.decision["transition"], "withdraw", "progress withdraws 4-2 as it does without a clock move")

    def test_a_step_back_on_the_window_the_clock_move_was_seen_on_is_still_seen(self):
        # The window the move is first seen on is recorded only, but it came in order: its screen counts on the way.
        for start, moved_to in ((2, 1804), (3000, 1002)):          # the clock set ahead, the clock set back
            with self.subTest(moved_to=moved_to):
                repository, send = self.timed()
                send(start, "review", back_count=1)                                  # 4-2 opens on the review screen
                send(moved_to, "menu"), send(moved_to + 2, "review"), send(moved_to + 4, "review")
                self.assertEqual(self.stale(repository), [False, True, False, False])
                again = repository.windows("s1")[-2]
                self.assertIs(again.inputs["progress_segment"], True, "review, back to the menu on the recorded window, review")
                self.assertEqual(again.decision["transition"], "withdraw", "as without a clock move")

    def test_a_visit_that_fell_on_the_window_the_clock_move_was_seen_on_ends_the_visit_before_it(self):
        repository, send = self.timed()
        send(2), send(4, back_count=1)                                # 4-2 opens on the menu
        send(1806, "review")                                          # the clock moved ahead; recorded only
        back = send(1808, "menu")                                     # menu, review (recorded only), menu again
        self.assertEqual((back.transition, repository.windows("s1")[-1].inputs["progress_segment"]), ("withdraw", True))
        again = send(1810, "menu", back_count=1)
        self.assertEqual((again.transition, again.support), ("open", HIGHLIGHT),
                         "a new visit of the menu: what was withdrawn in the visit before the move can open again")

    def test_two_wrong_times_apart_or_unrelated_are_not_a_clock_move(self):
        repository, send = self.timed()
        send(2), send(4), send(86406), send(8), send(10), send(86412)       # two wrong times, on-timeline windows between
        self.assertEqual(self.stale(repository), [False, False, True, False, False, True])
        send(14), send(-86400 + 16), send(86418), send(20)                   # a day behind, then a day ahead: unrelated
        send(90022), send(90010), send(26)                                   # two off the timeline, the second before the first
        self.assertEqual(self.stale(repository)[6:], [False, True, True, False, True, True, False])
        self.assertEqual((repository.state("s1").epoch, repository.state("s1").last_t), (0, T0.timestamp() + 26))

    def test_an_ask_shown_before_the_clock_moved_lapses_after_it_and_stays_withdrawn_in_the_same_visit(self):
        repository, clock = DecisionRepository(), {"now": 1000.0}
        service = DecisionService(repository, P, None, now=lambda: clock["now"])

        def judge(t, passed=2.0, **cues):
            clock["now"] += passed
            return service._judge("s1", window(float(t), gaze=True, **cues))

        self.assertEqual(judge(2, fixes_recent=2)[0].support, BIG)
        self.assertIsNone(judge(1804, fixes_recent=2)[0], "the clock moved 30 min ahead: recorded only")
        kept = judge(1806, fixes_recent=2)[0]
        self.assertEqual(kept.transition, "keep", "shown for 6 s: not lapsed by the move")
        self.assertEqual(kept.scope, repository.state("s1").held.scope, "the kept decision names the scope on the new timeline")
        decision, _, lapsed = judge(1812, passed=6.0, fixes_recent=2)
        self.assertEqual((lapsed, decision.transition), ("d0001", "none"), "lapsed at 12 s; the same visit: not asked again")

    def test_a_tag_scope_moves_with_the_clock(self):
        repository, clock = DecisionRepository(), {"now": 1000.0}
        service = DecisionService(repository, P, None, now=lambda: clock["now"])

        def judge(t, **cues):
            clock["now"] += 2.0
            return service._judge("s1", window(float(t), situation=situation(QUEUE), **cues))[0]

        self.assertEqual(judge(2).support, NOTICE)
        self.assertEqual(judge(4, progress_segment=True).transition, "withdraw")
        self.assertIsNone(judge(1806))
        self.assertEqual(judge(1808).transition, "none", "the same tag on the same screen: the withdrawn notice stays withdrawn")

    def test_the_same_window_sent_twice_is_not_a_clock_move(self):
        repository, send = self.timed()
        send(2), send(4), send(86406), send(86406)                    # one wrong time, sent again
        self.assertEqual((self.stale(repository), repository.state("s1").epoch), ([False, False, True, True], 0))
        send(8)
        self.assertEqual((self.stale(repository)[-1], repository.state("s1").last_t), (False, T0.timestamp() + 8))

    def test_the_screen_of_a_late_or_wrong_time_window_is_not_read(self):
        # Only the window a confirmed clock move was first seen on lends its screen; any other recorded-only window does not.
        for odd in (4, 86404):                                        # late; a day ahead
            with self.subTest(odd=odd):
                repository, send = self.timed()
                send(2), send(6, "review", back_count=1)              # 4-2 opens on the review screen
                send(odd, "menu")                                     # recorded only: not "back to the menu"
                kept = send(8, "review")
                self.assertEqual((kept.transition, repository.windows("s1")[-1].inputs["progress_segment"]), ("keep", False))

    def test_the_band_is_ten_minutes_either_side(self):
        repository, send = self.timed()
        send(2), send(590, passed=0.0), send(1192, passed=0.0)        # 588 s ahead of the server time passed, then 602 s
        self.assertEqual(self.stale(repository), [False, False, True])

    def test_judge_leaves_a_late_window_unjudged(self):
        repository = DecisionRepository()
        service = DecisionService(repository, P, None)
        service.judge("s1", ending_at(10), measurable=True)
        late = service.judge("s1", ending_at(4, back_count=1), measurable=True)
        self.assertEqual((late.transition, repository.state("s1").held, repository.state("s1").last_t),
                         ("none", None, T0.timestamp() + 10))

    def test_the_clock_candidate_is_stored_not_only_changed_in_place(self):
        import copy

        class CopyingRepository(DecisionRepository):                  # as a database-backed store would hand out the state
            def state(self, session_id):
                return copy.deepcopy(super().state(session_id))

        repository, clock = CopyingRepository(), {"now": 1000.0}
        service = DecisionService(repository, P, None, now=lambda: clock["now"])
        for seconds in (2, 4, 1806, 1808, 90000, 1812, 90004):        # a clock move; then two wrong times apart
            clock["now"] += 2.0
            service.observe("s1", ending_at(seconds), measurable=True)
        self.assertEqual((self.stale(repository), repository.state("s1").epoch),
                         ([False, False, True, False, True, False, True], 1))

    def test_only_the_window_the_move_was_seen_on_lends_its_screen_to_the_state(self):
        repository, clock = DecisionRepository(), {"now": 1000.0}
        service = DecisionService(repository, P, None, now=lambda: clock["now"])

        def step(call, seconds, screen="menu"):
            clock["now"] += 2.0
            return call("s1", ending_at(seconds, screen), measurable=True)

        step(service.observe, 2), step(service.observe, 6), step(service.observe, 4, "review")   # the last record: a late window
        step(service.judge, 5000), step(service.judge, 5002)          # the clock moves, seen through judge(): no record of it
        state = repository.state("s1")
        self.assertEqual((state.epoch, state.screen_last), (1, "menu"))
        self.assertLess(state.screen_since, T0.timestamp() + 5000, "the menu visit goes on: the late review window is not the crossed one")

    def test_a_support_withdrawn_before_the_clock_moved_is_not_reopened_in_the_same_visit(self):
        repository, clock = DecisionRepository(), {"now": 1000.0}
        service = DecisionService(repository, P, None, now=lambda: clock["now"])

        def judge(t, passed=2.0, **cues):
            clock["now"] += passed
            decision, _, _ = service._judge("s1", window(float(t), gaze=True, **cues))
            return decision

        asked = judge(2, fixes_recent=2)
        self.assertEqual((asked.transition, asked.support), ("open", BIG))
        self.assertEqual(judge(100, passed=98, fixes_recent=2).transition, "none", "the ask lapsed unanswered; not asked again")
        self.assertIsNone(judge(1904, fixes_recent=2), "the clock moved 30 min ahead: recorded only")
        again = judge(1906, fixes_recent=2)
        self.assertEqual(again.transition, "none", "the same visit of the same screen: the withdrawn ask stays withdrawn")
        self.assertEqual(repository.state("s1").withdrawn[0]["scope"][2], 2.0 + 1802.0)

    def test_times_of_what_is_shown_move_with_the_clock(self):
        from app.modules.decision.service import moved

        repository, send = self.timed()
        send(2), send(4, back_count=1)
        before = repository.state("s1")
        after = moved(before, 1800.0)
        self.assertEqual(after.held.shown_t - before.held.shown_t, 1800.0)
        self.assertEqual(after.screen_since - before.screen_since, 1800.0)
        self.assertEqual(before.held.shown_t, T0.timestamp() + 4, "the stored state is not changed in place")

    def test_a_frontend_clock_steadily_off_keeps_the_order_of_late_windows(self):
        for skew in (0, 30, -30, 3600):
            with self.subTest(skew=skew):
                repository, send = self.timed()
                for seconds in (2, 6, 4, 8):     # the window ending at 4 arrives late
                    send(seconds + skew)
                self.assertEqual(self.stale(repository), [False, False, True, False])

    def test_a_replay_faster_than_real_time_is_on_the_timeline(self):
        repository, send = self.timed()
        for seconds in range(2, 400, 2):
            send(seconds, passed=0.001)
        self.assertNotIn(True, self.stale(repository))

    def test_progress_hidden_by_a_window_that_was_not_measurable_is_seen_either_way(self):
        repository = DecisionRepository()
        service = DecisionService(repository, P, None)
        opened = service.observe("s3", ending_at(2, "review", back_count=1), measurable=True)
        self.assertEqual((opened.transition, opened.support), ("open", HIGHLIGHT))
        service.observe("s3", ending_at(4, "menu"), measurable=False)        # back to the menu, unseen
        again = service.observe("s3", ending_at(6, "review"), measurable=True)
        self.assertEqual((again.transition, repository.windows("s3")[-1].inputs["progress_segment"]), ("withdraw", True))

    def test_answers_fit_checks_names_types_and_the_options_offered(self):
        from app.infrastructure.external.jev_schemas import JevResponse
        from app.modules.decision.service import answers_fit

        questions = {"support_choice": {"type": "choice", "criteria": {"none": "x", "large_button": "y"}}}

        def answers(choice):
            return JevResponse.model_validate({"model": "m", "usage": {"input_tokens": 1, "output_tokens": 1}, "answers": {
                "support_choice": {"type": "choice", "choice": choice, "confidence": 0.9, "probabilities": {choice: 0.9}}}}).answers

        self.assertTrue(answers_fit(questions, answers("large_button")))
        self.assertFalse(answers_fit(questions, answers("format_disk")), "the right type, a choice nobody offered")
        self.assertFalse(answers_fit({**questions, "other": {"type": "noul"}}, answers("none")), "a question left unanswered")

    def test_progress_shows_on_the_next_measurable_window_when_the_crossing_one_was_not(self):
        repository = DecisionRepository()
        service = DecisionService(repository, P, None)
        opened = service.observe("s1", ending_at(2, "menu", back_count=1), measurable=True)
        self.assertEqual((opened.transition, opened.support), ("open", HIGHLIGHT))
        kept = service.observe("s1", ending_at(4, "review"), measurable=False)     # ai-engine timed out once
        self.assertEqual(kept.transition, "keep")
        withdrawn = service.observe("s1", ending_at(6, "review"), measurable=True)
        self.assertEqual((withdrawn.transition, repository.windows("s1")[-1].inputs["progress_segment"]), ("withdraw", True))
        # A screen id outside the flow in between does not hide the step either.
        service.observe("s2", ending_at(2, "menu", back_count=1), measurable=True)
        service.observe("s2", ending_at(4, "menu_list"), measurable=True)
        self.assertEqual(service.observe("s2", ending_at(6, "review"), measurable=True).transition, "withdraw")

    def test_an_unanswered_ask_lapses_before_the_next_window_is_judged(self):
        repository = DecisionRepository()
        service = DecisionService(repository, P, None)
        quiet = service.judge("s1", feature_window(back_count=0), measurable=True, situation=situation(AROUND))
        self.assertEqual(quiet.transition, "none", "no fixes_recent from the contract: no ask yet")
        # Put an ask in place the way 4-1 would, on the same clock as the /features windows (T0 + 2 s).
        shown = T0.timestamp() + 2
        state, (ask,) = run(repository.state("s1"), window(shown, fixes_recent=2, gaze=True))
        repository.save_state("s1", state)
        # One second short of no_response_s the ask stays; at no_response_s it lapses before the window is judged.
        service.observe("s1", ending_at(2 + P.no_response_s - 1, tap_count=0), measurable=True)
        self.assertIsNone(repository.windows("s1")[-1].timed_out)
        self.assertEqual(repository.state("s1").held.decision_id, ask.decision_id)
        service.observe("s1", ending_at(2 + P.no_response_s, tap_count=0), measurable=True)
        record = repository.windows("s1")[-1]
        self.assertEqual(record.timed_out, ask.decision_id)
        self.assertEqual(repository.state("s1").withdrawn[-1]["reason"], "no_response")

    def test_allowed_supports_match_what_the_table_would_open(self):
        from app.modules.decision.rule_table import WHAT, allowed_supports

        # Nothing held: the rows that open, options included.
        self.assertEqual(allowed_supports(window(10.0, situation=situation(QUEUE), fixes_recent=2, gaze=True), SessionState(), P),
                         [NOTICE, "defer_big_button_question", BIG])
        self.assertEqual(allowed_supports(window(10.0, situation=situation(BUSY)), SessionState(), P), [WAIT])
        self.assertIn(WAIT, WHAT)
        # An open ask stays: the table keeps, so there is nothing to choose.
        state, (asked,) = run(SessionState(), window(10.0, fixes_recent=2, gaze=True))
        self.assertEqual(asked.action, "propose")
        self.assertEqual(allowed_supports(window(12.0, backs_recent=1), state, P), [])
        # A 3-2 wait displaces the open 4-1 ask, but the 4-2 highlight ranked behind it cannot (keep): each row
        # is checked with the same transition rule, so only the wait is offered (wdragon92 review of #77).
        companion_back = window(12.0, situation=situation(BUSY), backs_recent=1)
        self.assertEqual((decide(companion_back, state, P).transition, decide(companion_back, state, P).support), ("replace", WAIT))
        self.assertEqual(allowed_supports(companion_back, state, P), [WAIT])
        # A held 3-1 notice with 4-1 and 4-2 together: the ask may replace the notice, the highlight may not.
        state, (notice,) = run(SessionState(), window(10.0, situation=situation(QUEUE)))
        self.assertEqual(notice.support, NOTICE)
        self.assertEqual(allowed_supports(window(12.0, situation=situation(QUEUE), fixes_recent=2, gaze=True, backs_recent=1), state, P), [BIG])
        # A withdraw window offers nothing either.
        state, (opened,) = run(SessionState(), window(10.0, backs_recent=1))
        self.assertEqual(allowed_supports(window(12.0, progress_segment=True), state, P), [])


class WindowRecordTests(unittest.IsolatedAsyncioTestCase):
    """Every window is a comparison row, in every arm, for the whole session (backend review P2 of #77)."""

    async def test_rule_only_arm_records_every_window_with_inputs_and_decision(self):
        repository = DecisionRepository()
        service = DecisionService(repository, P, None, stages=())
        for i in range(8):
            service.observe("s1", ending_at(2 + 2 * i, back_count=1 if i == 0 else 0), measurable=True)
        rows = repository.windows("s1")
        self.assertEqual(len(rows), 8)
        self.assertEqual({r.jev for r in rows}, {"off"})
        self.assertEqual((rows[0].decision["transition"], rows[0].decision["support"], rows[0].decision["decision_id"]), ("open", HIGHLIGHT, "d0001"))
        self.assertEqual(rows[0].inputs["backs_recent"], 1)
        self.assertEqual(rows[7].decision["transition"], "keep")
        self.assertEqual(rows[0].stages, ())

    async def test_asked_skipped_and_missing_stages_are_marked_on_the_window(self):
        gate = asyncio.Event()
        calls = []

        async def handler(request):
            body = json.loads(request.content)
            calls.append(list(body["questions"]))
            await gate.wait()
            if "support_choice" in body["questions"]:
                return httpx.Response(200, json={"model": "jev-1.13.0", "usage": {"input_tokens": 1, "output_tokens": 0},
                                                 "answers": {"support_choice": {"type": "choice", "choice": "none", "confidence": 0.6,
                                                                                "probabilities": {HIGHLIGHT: 0.4, "none": 0.6}}}})
            return httpx.Response(529, json={"error": "busy"})   # stage 1 fails

        from app.modules.decision.jev_questions import ScoreStage, SupportChoiceStage
        http = httpx.AsyncClient(base_url="https://api.typesafe.ai", transport=httpx.MockTransport(handler))
        repository = DecisionRepository()
        service = DecisionService(repository, P, JevClient(http, "jev-1.13.0", 3.0), stages=(ScoreStage(), SupportChoiceStage(P)))
        service.observe("s1", feature_window(back_count=1), measurable=True)
        await asyncio.sleep(0)
        later = FeatureWindowRequest(screen_id="menu", window_start=T0 + timedelta(seconds=2), window_end=T0 + timedelta(seconds=4),
                                     touch={"tap_count": 1, "miss_tap_count": 0, "repeat_tap_count": 0, "back_count": 0, "dwell_ms": 3000})
        service.observe("s1", later, measurable=True)   # while stage 1 is in flight
        gate.set()
        await service.drain()
        await http.aclose()
        first, second = repository.windows("s1")
        self.assertEqual((first.jev, first.stages, first.model), ("asked", ("state_scores", "support_choice"), "jev-1.13.0"))
        self.assertEqual(first.outcomes, {"state_scores": "no_answer", "support_choice": "answered"})
        self.assertEqual(first.answers["support_choice"]["support_choice"]["choice"], "none")
        self.assertEqual(second.jev, "skipped_in_flight")
        self.assertEqual(second.outcomes, {})
        choice_record = repository.records("s1")[-1]
        self.assertEqual((choice_record.stage, choice_record.previous_missing), ("support_choice", ("state_scores",)))


class ResponseInvarianceTests(unittest.TestCase):
    """The /features response with a measurable ai-engine answer is the same with the layer, without it, and when it raises."""

    BODY = {"screen_id": "menu", "window_start": "2026-11-04T10:00:00Z", "window_end": "2026-11-04T10:00:02Z",
            "touch": {"tap_count": 1, "miss_tap_count": 0, "repeat_tap_count": 0, "back_count": 1, "dwell_ms": 3000}}
    SCORES = {"normal": 0.2, "touch_difficulty": 0.5, "navigation_difficulty": 0.1, "visual_difficulty": 0.1, "hesitation": 0.1}

    def features(self, decision_patch=None):
        from unittest.mock import patch

        async def handler(request):
            if request.url.path == "/v1/systemone":   # the patched client class is also the Jev client's
                return httpx.Response(200, json=RESPONSE)
            payload = json.loads(request.content)
            self.ai_engine_called_at = datetime.now(timezone.utc)
            await asyncio.sleep(0.02)   # the round trip: a stamp taken after it is later than this one
            return httpx.Response(200, json={"session_id": payload["session_id"], "measurable": True, "states": self.SCORES, "model_version": "dummy-0.1"})

        app = create_app(Settings(_env_file=None, decision_send_support=False, openai_api_key=None, jev_api_key="jev-secret-value", jev_stages="state_scores"))
        real_client = httpx.AsyncClient   # app.main.httpx is this module: keep the class before patching it
        with patch("app.main.httpx.AsyncClient",
                   side_effect=lambda **kw: real_client(base_url="http://ai-engine:8001", transport=httpx.MockTransport(handler))), \
                TestClient(app) as client:
            session_id = client.post("/api/v1/sessions").json()["session_id"]
            if decision_patch == "raise":
                with patch.object(DecisionService, "observe", side_effect=RuntimeError("decision boom")):
                    body = client.post(f"/api/v1/sessions/{session_id}/features", json=self.BODY).json()
            else:
                body = client.post(f"/api/v1/sessions/{session_id}/features", json=self.BODY).json()
                if decision_patch == "with_layer":
                    (record,) = client.app.state.decision_repository.windows(session_id)
                    self.assertEqual((record.jev, record.ai, record.ai_model_version), ("asked", "ok", "dummy-0.1"))
                    self.assertLessEqual(record.received_at, self.ai_engine_called_at,
                                         "stamped when /features got the window, before the ai-engine round trip")
        body.pop("session_id")
        return body

    def test_measurable_response_is_identical_with_the_layer_and_when_it_raises(self):
        expected = {"ai_available": True, "states": self.SCORES, "model_version": "dummy-0.1",
                    "support": {"preset": "none", "requires_confirmation": False, "decided_by": "rule_placeholder"}}
        self.assertEqual(self.features("with_layer"), expected)
        self.assertEqual(self.features("raise"), expected)

    def post_windows(self, *states_per_window, measurable=True):
        """POST one /features window per entry (2 s apart), ai-engine answering measurable=true with those states.

        Returns the bodies, the decision repository's window records and state, and the Jev requests made."""
        from unittest.mock import patch

        jev_calls, answers = [], list(states_per_window)

        async def handler(request):
            if request.url.path == "/v1/systemone":
                jev_calls.append(request)
                return httpx.Response(200, json=RESPONSE)
            payload = json.loads(request.content)
            return httpx.Response(200, json={"session_id": payload["session_id"], "measurable": measurable,
                                             "states": answers.pop(0), "model_version": "dummy-0.1"})

        app = create_app(Settings(_env_file=None, decision_send_support=False, openai_api_key=None, jev_api_key="jev-secret-value",
                                  jev_stages="state_scores"))
        real_client = httpx.AsyncClient
        bodies = []
        with patch("app.main.httpx.AsyncClient",
                   side_effect=lambda **kw: real_client(base_url="http://ai-engine:8001",
                                                        transport=httpx.MockTransport(handler))), \
                TestClient(app) as client:
            session_id = client.post("/api/v1/sessions").json()["session_id"]
            for i in range(len(states_per_window)):
                end = datetime(2026, 11, 4, 10, 0, 2 + 2 * i, tzinfo=timezone.utc)
                body = {**self.BODY, "window_start": (end - timedelta(seconds=2)).isoformat(),
                        "window_end": end.isoformat()}
                bodies.append(client.post(f"/api/v1/sessions/{session_id}/features", json=body).json())
            repository = client.app.state.decision_repository
            records, state = repository.windows(session_id), repository.state(session_id)
        return bodies, records, state, jev_calls

    INVALID = (("out of range", {**SCORES, "normal": 1.5}), ("missing", {"normal": 0.5}),
               ("not a number", {**SCORES, "normal": "high"}))

    def test_scores_the_response_rejects_reach_the_table_as_a_window_that_was_not_measurable(self):
        # Review of #77 (bb, 2aeb780): measurable=true with scores out of range or missing gave ai_available=false,
        # yet the table opened highlight_next_action on the window and asked Jev.
        for name, states in self.INVALID:
            with self.subTest(name):
                (body,), (record,), state, jev_calls = self.post_windows(states)
                self.assertEqual((body["ai_available"], body["states"]), (False, None))
                self.assertEqual((record.inputs["measurable"], record.ai), (False, "invalid_scores"))
                self.assertNotEqual(record.jev, "asked")
                self.assertIsNone(state.held, "no row opened on the window")
                self.assertEqual(jev_calls, [], "Jev is not asked about it")

    def test_rejected_scores_keep_a_support_already_held(self):
        # The same window while a support is held: nothing withdrawn, nothing asked (the open one asked once).
        for name, states in self.INVALID:
            with self.subTest(name):
                bodies, records, state, jev_calls = self.post_windows(self.SCORES, states)
                self.assertEqual([b["ai_available"] for b in bodies], [True, False])
                self.assertEqual([(r.decision["transition"], r.ai) for r in records],
                                 [("open", "ok"), ("keep", "invalid_scores")])
                self.assertEqual((state.held.support, state.held.decision_id),
                                 (records[0].decision["support"], records[0].decision["decision_id"]))
                self.assertEqual(len(jev_calls), 1)

    def test_a_window_ai_engine_could_not_measure_is_recorded_apart_from_rejected_scores(self):
        (body,), (record,), state, jev_calls = self.post_windows(None, measurable=False)
        self.assertEqual((body["ai_available"], body["states"]), (True, None))
        self.assertEqual((record.inputs["measurable"], record.ai), (False, "unmeasurable"))
        self.assertEqual(jev_calls, [])


class FeaturesEndpointTests(unittest.TestCase):
    BODY = {"screen_id": "menu", "window_start": "2026-11-04T10:00:00Z", "window_end": "2026-11-04T10:00:02Z",
            "touch": {"tap_count": 1, "miss_tap_count": 0, "repeat_tap_count": 0, "back_count": 1, "dwell_ms": 3000}}

    def test_jev_stages_off_keeps_the_app_up_with_the_rule_table_alone(self):
        settings = Settings(_env_file=None, decision_send_support=False, openai_api_key=None, jev_api_key="jev-secret-value", jev_stages="off", ai_engine_url="http://127.0.0.1:9")
        with TestClient(create_app(settings)) as client:
            self.assertFalse(client.app.state.decision_service.shadow)
            self.assertEqual(client.app.state.decision_service.stage_names, ())

    def test_the_response_is_unchanged_while_the_table_runs_beside_it(self):
        for key in (None, "jev-secret-value"):
            with self.subTest(jev_key=bool(key)):
                settings = Settings(_env_file=None, decision_send_support=False, openai_api_key=None, jev_api_key=key, ai_engine_url="http://127.0.0.1:9",
                                    jev_stages="state_scores" if key else "off")
                with TestClient(create_app(settings)) as client:
                    session_id = client.post("/api/v1/sessions").json()["session_id"]
                    body = client.post(f"/api/v1/sessions/{session_id}/features", json=self.BODY).json()
                    # ai-engine is unreachable here: the fallback response, as before this module.
                    self.assertEqual(body, {"session_id": session_id, "ai_available": False, "states": None, "model_version": None,
                                            "support": {"preset": "none", "requires_confirmation": False, "decided_by": "rule_placeholder"}})
                    state = client.app.state.decision_repository.state(session_id)
                    self.assertEqual(state.screen_last, "menu", "the table saw the window (not measurable: no row)")
                    self.assertIsNone(state.held)
                    self.assertIs(client.app.state.decision_service.shadow, key is not None)
                    (record,) = client.app.state.decision_repository.windows(session_id)
                    self.assertEqual(record.ai, "unavailable", "ai-engine down: a system fault, not unmeasurable")


    def test_shutdown_waits_for_a_jev_call_still_on_its_way(self):
        async def slow(request):
            await asyncio.sleep(0.2)
            return httpx.Response(200, json=RESPONSE)

        def jev_http(api_key, base_url, timeout_seconds):
            return httpx.AsyncClient(base_url="https://api.typesafe.ai", transport=httpx.MockTransport(slow))

        settings = Settings(_env_file=None, decision_send_support=False, openai_api_key=None, jev_api_key="jev-secret-value", jev_stages="state_scores",
                            ai_engine_url="http://127.0.0.1:9")
        with unittest.mock.patch("app.main.create_jev_http", jev_http):
            with TestClient(create_app(settings)) as client:
                service, repository = client.app.state.decision_service, client.app.state.decision_repository
                client.portal.call(lambda: service.observe("s1", ending_at(2, back_count=1), measurable=True))
                self.assertEqual(repository.records("s1"), [], "the call is still on its way")
        self.assertEqual([r.outcome for r in repository.records("s1")], ["answered"], "the lifespan drained it")


class RetentionTests(unittest.IsolatedAsyncioTestCase):
    """Sessions idle past the retention start fresh, whoever touches the repository first (backend review of #77)."""

    def repository(self):
        self.now = [T0]
        return DecisionRepository(clock=lambda: self.now[0])

    def used_session(self, repository, session_id="s1"):
        state = repository.state(session_id)
        state.next_id = 7
        repository.save_state(session_id, state)
        repository.add_window(WindowRecord(session_id, T0, T0.timestamp(), {"screen": "menu"}, {}, (), "off"))

    def test_the_same_session_coming_back_after_the_retention_starts_fresh(self):
        repository = self.repository()
        self.used_session(repository)
        self.now[0] = T0 + timedelta(hours=2)
        self.assertEqual(repository.state("s1").next_id, 1, "no other session touched the repository in between")
        self.assertEqual(repository.windows("s1"), [])

    def test_another_sessions_access_expires_an_idle_session(self):
        repository = self.repository()
        self.used_session(repository)
        self.now[0] = T0 + timedelta(hours=2)
        repository.state("s2")
        self.assertEqual(repository.windows("s1"), [])

    def test_the_retention_boundary(self):
        from app.modules.decision.repository import RETENTION

        repository = self.repository()
        self.used_session(repository)
        self.now[0] = T0 + RETENTION                        # exactly the retention: still kept
        self.assertEqual(repository.state("s1").next_id, 7)
        self.now[0] = T0 + 2 * RETENTION + timedelta(seconds=1)   # idle one second past it since that access
        self.assertEqual(repository.state("s1").next_id, 1)

    async def test_an_answer_arriving_after_the_session_expired_does_not_bring_it_back(self):
        gate = asyncio.Event()

        async def slow(request):
            await gate.wait()
            return httpx.Response(200, json=RESPONSE)

        http = httpx.AsyncClient(base_url="https://api.typesafe.ai", transport=httpx.MockTransport(slow))
        repository = self.repository()
        service = DecisionService(repository, P, JevClient(http, "jev-1.13.0", 3.0))
        service.observe("s1", feature_window(), measurable=True)
        await asyncio.sleep(0)
        self.now[0] = T0 + timedelta(hours=2)
        repository.state("s2")                               # expires s1 while its call is in flight
        gate.set()
        await service.drain()
        await http.aclose()
        self.assertEqual((repository.records("s1"), repository.windows("s1")), ([], []))
        self.assertEqual(repository.state("s1").next_id, 1)

    def test_the_first_window_after_the_retention_reads_no_previous_screen_or_history(self):
        """Expiry comes before the reads of observe(): no previous screen (no progress) and no history."""
        repository = self.repository()
        service = DecisionService(repository, P, None, stages=())
        service.observe("s1", ending_at(2), measurable=True)                    # menu
        self.now[0] = T0 + timedelta(hours=2)                                   # nothing else touches the repository
        self.assertEqual(repository.history("s1"), [], "the trajectory stage reads history before the judgment")
        service.observe("s1", ending_at(4, screen="review"), measurable=True)   # would be menu -> review progress
        (first,) = repository.windows("s1")
        self.assertIsNone(first.inputs["progress_segment"], "an expired session has no previous screen")

    def test_judge_after_the_retention_reads_no_previous_screen(self):
        repository = self.repository()
        service = DecisionService(repository, P, None, stages=())
        service.observe("s1", ending_at(2), measurable=True)                    # menu
        self.now[0] = T0 + timedelta(hours=2)
        inp = service._input("s1", ending_at(4, screen="review"), True, None, None)
        self.assertIsNone(inp.progress_segment)

    async def test_an_answer_after_expiry_with_no_access_in_between_is_not_recorded(self):
        gate = asyncio.Event()

        async def slow(request):
            await gate.wait()
            return httpx.Response(200, json=RESPONSE)

        http = httpx.AsyncClient(base_url="https://api.typesafe.ai", transport=httpx.MockTransport(slow))
        repository = self.repository()
        service = DecisionService(repository, P, JevClient(http, "jev-1.13.0", 3.0))
        service.observe("s1", feature_window(), measurable=True)
        await asyncio.sleep(0)
        self.now[0] = T0 + timedelta(hours=2)                # s1 expires; no other access before the answer
        gate.set()
        await service.drain()
        await http.aclose()
        self.assertEqual((repository.records("s1"), repository.windows("s1")), ([], []))


class HistoryContentTests(unittest.IsolatedAsyncioTestCase):
    def test_the_trajectory_carries_the_five_state_scores_only(self):
        from app.modules.decision.jev_questions import STATE_QUESTIONS

        self.assertEqual(set(HISTORY_SCORES), set(STATE_QUESTIONS))
        repository = DecisionRepository()
        record = WindowRecord("s1", T0, T0.timestamp(), {"screen": "menu"}, {"transition": "open"}, ("state_scores",), "asked")
        repository.add_window(record)
        scores = {name: 0.5 for name in STATE_QUESTIONS}
        repository.attach(record, "state_scores", "answered", {**scores, "proposal_fits": 0.8,
                                                                 "queue_support": {"type": "choice", "choice": NOTICE}})
        (row,) = repository.history("s1")
        self.assertEqual(row["state_scores"], scores, "the rule table's own question stays out")

    async def test_a_late_window_reads_its_previous_screen_from_the_window_before_it_in_time(self):
        """menu 2 s, review 6 s, then review 4 s arriving late: in time order menu -> review is progress."""
        repository = DecisionRepository()
        service = DecisionService(repository, P, None, stages=())
        service.observe("s1", ending_at(2, back_count=1), measurable=True)
        service.observe("s1", ending_at(6, screen="review"), measurable=True)
        service.observe("s1", ending_at(4, screen="review"), measurable=True)
        late = repository.windows("s1")[-1]
        self.assertEqual(late.jev, STALE)
        self.assertIs(late.inputs["progress_segment"], True)
