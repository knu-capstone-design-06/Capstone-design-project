import asyncio
import json
import unittest
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
        service.observe("s1", feature_window(back_count=1), measurable=True)
        await asyncio.sleep(0)  # let the first call start
        service.observe("s1", feature_window(back_count=2), measurable=True)   # skipped: s1 is in flight
        service.observe("s2", feature_window(back_count=3), measurable=True)   # another session is not held back
        self.assertTrue(service.in_flight("s1"))
        gate.set()
        await service.drain()
        self.assertEqual(sorted(calls), [1, 3])
        self.assertFalse(service.in_flight("s1"))
        service.observe("s1", feature_window(back_count=4), measurable=True)   # asked again once free
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
        """Two windows ending at the same time: the one skipped while the first call is in flight gets no answer."""
        gate = asyncio.Event()
        calls = []

        async def slow(request):
            calls.append(1)
            await gate.wait()
            return httpx.Response(200, json=RESPONSE)

        service = self.service(slow)
        service.observe("s1", feature_window(), measurable=True)
        await asyncio.sleep(0)
        service.observe("s1", feature_window(), measurable=True)   # same end time, recorded as skipped
        gate.set()
        await service.drain()
        asked, skipped = self.repository.windows("s1")
        self.assertEqual(len(calls), 1)
        self.assertEqual((asked.jev, asked.outcomes), ("asked", {"state_scores": "answered"}))
        self.assertEqual((skipped.jev, skipped.outcomes, skipped.answers), ("skipped_in_flight", {}, {}))

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
        self.assertEqual((scores.stage, scores.outcome, scores.previous_missing), ("state_scores", "answered", ("broken",)))
        self.assertEqual(self.repository.windows("s1")[0].outcomes, {"broken": "no_answer", "state_scores": "answered"})

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
            service.observe("s1", feature_window(back_count=1 if i == 0 else 0), measurable=True)
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
            return httpx.Response(200, json={"session_id": payload["session_id"], "measurable": True, "states": self.SCORES, "model_version": "dummy-0.1"})

        app = create_app(Settings(_env_file=None, openai_api_key=None, jev_api_key="jev-secret-value", jev_stages="state_scores"))
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
                    self.assertEqual(client.app.state.decision_repository.windows(session_id)[0].jev, "asked")
        body.pop("session_id")
        return body

    def test_measurable_response_is_identical_with_the_layer_and_when_it_raises(self):
        expected = {"ai_available": True, "states": self.SCORES, "model_version": "dummy-0.1",
                    "support": {"preset": "none", "requires_confirmation": False, "decided_by": "rule_placeholder"}}
        self.assertEqual(self.features("with_layer"), expected)
        self.assertEqual(self.features("raise"), expected)


class FeaturesEndpointTests(unittest.TestCase):
    BODY = {"screen_id": "menu", "window_start": "2026-11-04T10:00:00Z", "window_end": "2026-11-04T10:00:02Z",
            "touch": {"tap_count": 1, "miss_tap_count": 0, "repeat_tap_count": 0, "back_count": 1, "dwell_ms": 3000}}

    def test_jev_stages_off_keeps_the_app_up_with_the_rule_table_alone(self):
        settings = Settings(_env_file=None, openai_api_key=None, jev_api_key="jev-secret-value", jev_stages="off", ai_engine_url="http://127.0.0.1:9")
        with TestClient(create_app(settings)) as client:
            self.assertFalse(client.app.state.decision_service.shadow)
            self.assertEqual(client.app.state.decision_service.stage_names, ())

    def test_the_response_is_unchanged_while_the_table_runs_beside_it(self):
        for key in (None, "jev-secret-value"):
            with self.subTest(jev_key=bool(key)):
                settings = Settings(_env_file=None, openai_api_key=None, jev_api_key=key, ai_engine_url="http://127.0.0.1:9",
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
