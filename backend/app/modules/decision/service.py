"""Judgment layer, shadow stage: run the rule table per window and ask Jev in the background.

judge() is synchronous and only changes the session state. observe() also records the window and, when
an experiment arm is on, schedules the Jev stages as a background task, so the /features response never
waits for Jev; the answers are attached to the window's record as they arrive (jev_deadline:
next_segment). Nothing here reaches the screen yet.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import logging
import time
from collections.abc import Sequence

from app.infrastructure.external.jev_client import JevClient
from app.infrastructure.external.jev_schemas import JevRequest, NoulAnswer, ScoreAnswer
from app.modules.decision.jev_questions import DEFAULT_STAGES, JevStage, StageInput
from app.modules.decision.repository import DecisionRepository
from app.modules.decision.rule_table import apply, decide, tick
from app.modules.decision.schemas import (
    PILOT_PARAMS, SCREEN_FLOW, STALE, Decision, DecisionParams, JevRecord, SessionState, WindowInput, WindowRecord,
)
from app.modules.sessions.schemas import FeatureWindowRequest

logger = logging.getLogger(__name__)


def steps_left(screen: str | None) -> int | None:
    """Screens left before the order ends, from the kiosk screen order; None for a screen not in it."""
    return len(SCREEN_FLOW) - 1 - SCREEN_FLOW.index(screen) if screen in SCREEN_FLOW else None


def window_input(window: FeatureWindowRequest, measurable: bool, situation: dict | None = None,
                 gaze: bool | None = None, previous_screen: str | None = None) -> WindowInput:
    """One rule-table line from a /features window.

    The contract's five touch counts fill what they can: presses, misses and backs. The screen id gives the steps
    left and, against the previous window's screen, whether the order moved forward (cart_progress). What the
    frontend does not send yet stays None (near-miss fixes, pause since the last press, options dialog), and the
    vision situation and gaze arrive only when the vision values are passed on (docs/Jev-Integration.md).
    """
    touch = window.touch
    # Progress is known only between two screens of the flow: with a screen id outside it (the voice API's
    # "menu_list", a new screen) or no window before, it is None, not "no progress". A window lost in between
    # (menu, then complete) is still a step forward.
    known = previous_screen in SCREEN_FLOW and window.screen_id in SCREEN_FLOW
    forward = known and SCREEN_FLOW.index(window.screen_id) > SCREEN_FLOW.index(previous_screen)
    return WindowInput(
        t=window.window_end.timestamp(), measurable=measurable, situation=situation, screen=window.screen_id,
        steps_left=steps_left(window.screen_id), gaze=gaze, misses_recent=touch.miss_tap_count,
        backs_recent=touch.back_count, taps_segment=touch.tap_count,
        progress_segment=forward if known else None,
    )


# No source: window times come from the frontend clock, which may run ahead of or behind the server's by a
# constant amount, so they are compared with each other, never with the server clock itself.
# Wide on purpose: tests and replays of recorded sessions feed windows faster than real time, and only a
# plainly wrong time (a clock a day off) has to be kept out.
CLOCK_JUMP_S = 600.0       # a window may end this much later than the server time passed since the last one
CLOCK_RESET_S = 60.0       # a window this far behind the mark means the mark was wrong (late windows are seconds late)


def log_task_failure(task: asyncio.Task) -> None:
    """A background Jev chain that died outside its own handling (a store error) is logged, never raised."""
    if not task.cancelled() and task.exception() is not None:
        logger.error("jev shadow task failed", exc_info=task.exception())


def answers_fit(questions: dict, answers: dict) -> bool:
    """True when every question asked has an answer of its own type, a choice among the options offered."""
    for name, question in questions.items():
        answer = answers.get(name)
        if answer is None or answer.type != question.get("type"):
            return False
        if answer.type == "choice" and answer.choice not in (question.get("criteria") or {}):
            return False
    return True


def stale_decision() -> Decision:
    """What judge() returns for a window out of the order of time (late, or jumped ahead): nothing changes."""
    return Decision("none", {}, reason="window out of time order (late, or its time jumped ahead); recorded only")


def recorded_answer(answer):
    """The validated answer as Jev gave it (docs 5 #6): a noul probability, or the whole choice / score answer."""
    return answer.noul if isinstance(answer, NoulAnswer) else answer.model_dump(mode="json")


def passed_answer(answer):
    """The short form a later stage reads (unchanged since the first shadow runs, so its questions stay the same)."""
    if isinstance(answer, NoulAnswer):
        return answer.noul
    if isinstance(answer, ScoreAnswer):
        return {"score": answer.score, "confidence": answer.confidence}
    return {"choice": answer.choice, "confidence": answer.confidence}


class DecisionService:
    def __init__(self, repository: DecisionRepository, params: DecisionParams = PILOT_PARAMS,
                 jev: JevClient | None = None, stages: Sequence[JevStage] = DEFAULT_STAGES, clock=time.perf_counter,
                 now=time.time):
        self._repository = repository
        self._params = params
        self._jev = jev
        self._stages = tuple(stages)   # Jev calls in order; each sees the answers before it (stackable)
        self._clock = clock
        self._now = now                # wall clock, to bound a window that claims to end in the future
        self._tasks: set[asyncio.Task] = set()
        self._in_flight: dict[str, asyncio.Task] = {}   # one Jev call chain per session at a time
        if self._stages and self._jev is None:
            # An arm set without a key would quietly run as arm A; say so once and mark every window no_client.
            logger.warning("JEV_STAGES=%s but no Jev client (JEV_API_KEY unset): the rule table runs alone",
                           ",".join(self.stage_names))

    @property
    def shadow(self) -> bool:
        """True when Jev is asked (a client and at least one stage); False = the rule table alone."""
        return self._jev is not None and bool(self._stages)

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(stage.name for stage in self._stages)

    def in_flight(self, session_id: str) -> bool:
        return session_id in self._in_flight

    def _input(self, session_id: str, window: FeatureWindowRequest, measurable: bool, situation, gaze) -> WindowInput:
        # The previous screen is the last judged window that ended no later than this one: for a late window,
        # the one before it in time, so its comparison row keeps the time order of the screens. Only windows
        # the table could act on count (measurable, a screen of the flow): when the window that crossed to the
        # next screen was not measurable, the next measurable one still shows the step forward and withdraws 4-2.
        t = window.window_end.timestamp()
        judged = [w for w in self._repository.windows(session_id) if w.jev != STALE and w.t <= t
                  and w.inputs.get("measurable") and w.inputs.get("screen") in SCREEN_FLOW]
        return window_input(window, measurable, situation, gaze, judged[-1].inputs.get("screen") if judged else None)

    def judge(self, session_id: str, window: FeatureWindowRequest, measurable: bool,
              situation: dict | None = None, gaze: bool | None = None) -> Decision:
        """Run the rule table on this window and store the new session state (no record, no Jev)."""
        inp = self._input(session_id, window, measurable, situation, gaze)
        decision, _, _ = self._judge(session_id, inp)
        return decision if decision is not None else stale_decision()

    def _judge(self, session_id: str, inp: WindowInput) -> tuple[Decision | None, SessionState, str | None]:
        """(decision, state before the decision, ask withdrawn for no response).

        Windows are judged in time order. When /features requests overlap and an earlier window's answer from
        ai-engine arrives after a later window was judged, that earlier window must not roll the session back
        (reopen a withdrawn support, undo a screen's progress): it changes nothing and the decision is None.
        """
        state = self._repository.state(session_id)
        now = self._now()
        if state.last_t is not None:
            behind = state.last_t - inp.t
            if 0 < behind <= CLOCK_RESET_S:
                return None, state, None                 # a late window
            # A window whose time jumped ahead of what the server saw pass (a bad request, a clock set
            # mid-session) is recorded only: judged, it would lapse an open ask at once and make every later
            # window "late". A steady offset between the two clocks never trips this.
            if behind <= 0 and state.last_now is not None and -behind > (now - state.last_now) + CLOCK_JUMP_S:
                return None, state, None
            # behind > CLOCK_RESET_S: the mark itself came from such a jump (the session's first window);
            # this window starts the order of time again.
        state, timed_out = tick(state, inp.t, self._params)      # an unanswered ask lapses first
        before = copy.deepcopy(state)
        state, decision = apply(state, decide(inp, state, self._params))
        state.last_t, state.last_now = inp.t, now
        self._repository.save_state(session_id, state)
        return decision, before, timed_out

    def observe(self, session_id: str, window: FeatureWindowRequest, measurable: bool,
                situation: dict | None = None, gaze: bool | None = None) -> Decision:
        """judge(), record the window, then ask Jev in the background when the arm is on and the window allows.

        One call chain per session at a time: while an answer is still on its way, the next window is recorded
        as skipped rather than asked; the window after it asks again. A window that ended before the session's
        last judged window is recorded as STALE: no state change, no Jev call.
        """
        inp = self._input(session_id, window, measurable, situation, gaze)
        history = self._repository.history(session_id)   # the windows before this one
        decision, before, timed_out = self._judge(session_id, inp)
        if decision is None:
            decision, why = stale_decision(), STALE
        elif not self.shadow:
            why = "no_client" if self._stages else "off"
        elif not measurable:
            why = "not_measurable"
        elif session_id in self._in_flight:
            why = "skipped_in_flight"
        else:
            why = "asked"
        record = WindowRecord(
            session_id, window.window_end, inp.t, dataclasses.asdict(inp),
            {"transition": decision.transition, "support": decision.support, "scene": decision.scene,
             "action": decision.action, "decision_id": decision.decision_id, "reason": decision.reason,
             "tag": decision.meta.get("tag"), "policy": decision.policy},
            self.stage_names, why, self._jev.model if self._jev else None, timed_out,
        )
        self._repository.add_window(record)
        if why == "asked":
            task = asyncio.create_task(self.ask_shadow(session_id, window, inp, decision, before, history, record))
            self._tasks.add(task)
            self._in_flight[session_id] = task
            task.add_done_callback(self._tasks.discard)
            task.add_done_callback(log_task_failure)
            task.add_done_callback(lambda done, sid=session_id: self._in_flight.pop(sid, None))
        return decision

    async def ask_shadow(self, session_id: str, window: FeatureWindowRequest, inp: WindowInput,
                         decision: Decision, state: SessionState | None = None,
                         history: list[dict] | None = None, window_record: WindowRecord | None = None,
                         ) -> list[JevRecord]:
        """The Jev stages in order, one call each; every stage sees the earlier answers. Only records are kept.

        state is the session state the rule table decided on (before the decision was applied), so a stage
        choosing a support sees the same candidates the table had. A stage that gets no answer leaves nothing
        for the next one; the next one still runs and its record names the missing stage. window_record is the
        record observe() made for this window: results go to it alone (a caller without it gets the last record
        that ended at this window's time).
        """
        assert self._jev is not None
        if state is None:
            state = self._repository.state(session_id)
        if window_record is None:
            window_record = self._repository.window_at(session_id, inp.t)

        def mark(stage_name: str, outcome: str, answers: dict | None = None) -> None:
            if window_record is not None:
                self._repository.attach(window_record, stage_name, outcome, answers)

        previous: dict[str, dict] = {}
        missing: list[str] = []
        records = []
        for stage in self._stages:
            questions: dict = {}
            started = self._clock()
            try:
                # The whole stage: building the question can fail as well as the call. Either way this stage
                # simply has no answer, the later stages still run and the window keeps its record.
                built = stage.build(StageInput(inp, state, decision, window.touch, dict(previous), list(history or [])))
                if built is None:
                    mark(stage.name, "skipped")
                    continue
                stage_state, questions = built
                response = await self._jev.ask(JevRequest(model=self._jev.model, state=stage_state, questions=questions))
            except Exception:
                # A shadow call must never surface.
                logger.exception("jev shadow %s crashed", stage.name)
                response = None
            latency_ms = round((self._clock() - started) * 1000)
            if response is not None and not answers_fit(questions, response.answers):
                # Answers that do not answer what was asked would spoil the record and the next stage's state.
                logger.warning("jev shadow %s answered something else than asked", stage.name)
                response = None
            if response is None:
                record = JevRecord(session_id, window.window_end, tuple(questions), self._jev.model, "no_answer",
                                   latency_ms, decision_id=decision.decision_id, stage=stage.name,
                                   previous_missing=tuple(missing))
                missing.append(stage.name)
                mark(stage.name, "no_answer")
            else:
                asked = {name: response.answers[name] for name in questions}   # an answer nobody asked for is dropped
                answers = {name: recorded_answer(answer) for name, answer in asked.items()}
                record = JevRecord(session_id, window.window_end, tuple(questions), self._jev.model, "answered",
                                   latency_ms, response.model, answers, response.usage.model_dump(),
                                   decision.decision_id, stage.name, tuple(missing))
                previous[stage.name] = {name: passed_answer(answer) for name, answer in asked.items()}
                mark(stage.name, "answered", answers)
            self._repository.add_record(record, window_record)
            records.append(record)
            logger.info("jev shadow %s %s: %.40s in %d ms (%d questions)", stage.name, record.outcome,
                        response.model if response else "-", latency_ms, len(questions))
        return records

    async def drain(self) -> None:
        """Wait for background Jev calls (tests, shutdown)."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
