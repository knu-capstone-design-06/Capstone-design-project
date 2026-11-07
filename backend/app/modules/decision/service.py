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
from app.infrastructure.external.jev_schemas import JevRequest, NoulAnswer
from app.modules.decision.jev_questions import DEFAULT_STAGES, JevStage, StageInput
from app.modules.decision.repository import DecisionRepository
from app.modules.decision.rule_table import apply, decide, tick
from app.modules.decision.schemas import (
    PILOT_PARAMS, SCREEN_FLOW, Decision, DecisionParams, JevRecord, SessionState, WindowInput, WindowRecord,
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
    forward = (previous_screen in SCREEN_FLOW and window.screen_id in SCREEN_FLOW
               and SCREEN_FLOW.index(window.screen_id) == SCREEN_FLOW.index(previous_screen) + 1)
    return WindowInput(
        t=window.window_end.timestamp(), measurable=measurable, situation=situation, screen=window.screen_id,
        steps_left=steps_left(window.screen_id), gaze=gaze, misses_recent=touch.miss_tap_count,
        backs_recent=touch.back_count, taps_segment=touch.tap_count,
        progress_segment=True if forward else (None if previous_screen is None else False),
    )


class DecisionService:
    def __init__(self, repository: DecisionRepository, params: DecisionParams = PILOT_PARAMS,
                 jev: JevClient | None = None, stages: Sequence[JevStage] = DEFAULT_STAGES, clock=time.perf_counter):
        self._repository = repository
        self._params = params
        self._jev = jev
        self._stages = tuple(stages)   # Jev calls in order; each sees the answers before it (stackable)
        self._clock = clock
        self._tasks: set[asyncio.Task] = set()
        self._in_flight: dict[str, asyncio.Task] = {}   # one Jev call chain per session at a time

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
        previous = self._repository.windows(session_id)
        return window_input(window, measurable, situation, gaze, previous[-1].inputs.get("screen") if previous else None)

    def judge(self, session_id: str, window: FeatureWindowRequest, measurable: bool,
              situation: dict | None = None, gaze: bool | None = None) -> Decision:
        """Run the rule table on this window and store the new session state (no record, no Jev)."""
        inp = self._input(session_id, window, measurable, situation, gaze)
        decision, _, _ = self._judge(session_id, inp)
        return decision

    def _judge(self, session_id: str, inp: WindowInput) -> tuple[Decision, SessionState, str | None]:
        """(decision, state before the decision, ask withdrawn for no response)."""
        state = self._repository.state(session_id)
        state, timed_out = tick(state, inp.t, self._params)      # an unanswered ask lapses first
        before = copy.deepcopy(state)
        state, decision = apply(state, decide(inp, state, self._params))
        self._repository.save_state(session_id, state)
        return decision, before, timed_out

    def observe(self, session_id: str, window: FeatureWindowRequest, measurable: bool,
                situation: dict | None = None, gaze: bool | None = None) -> Decision:
        """judge(), record the window, then ask Jev in the background when the arm is on and the window allows.

        One call chain per session at a time: while an answer is still on its way, the next window is recorded
        as skipped rather than asked; the window after it asks again.
        """
        inp = self._input(session_id, window, measurable, situation, gaze)
        history = self._repository.history(session_id)   # the windows before this one
        decision, before, timed_out = self._judge(session_id, inp)
        if not self.shadow:
            why = "off"
        elif not measurable:
            why = "not_measurable"
        elif session_id in self._in_flight:
            why = "skipped_in_flight"
        else:
            why = "asked"
        self._repository.add_window(WindowRecord(
            session_id, window.window_end, inp.t, dataclasses.asdict(inp),
            {"transition": decision.transition, "support": decision.support, "scene": decision.scene,
             "action": decision.action, "decision_id": decision.decision_id, "reason": decision.reason,
             "tag": decision.meta.get("tag"), "policy": decision.policy},
            self.stage_names, why, self._jev.model if self._jev else None, timed_out,
        ))
        if why == "asked":
            task = asyncio.create_task(self.ask_shadow(session_id, window, inp, decision, before, history))
            self._tasks.add(task)
            self._in_flight[session_id] = task
            task.add_done_callback(self._tasks.discard)
            task.add_done_callback(lambda done, sid=session_id: self._in_flight.pop(sid, None))
        return decision

    async def ask_shadow(self, session_id: str, window: FeatureWindowRequest, inp: WindowInput,
                         decision: Decision, state: SessionState | None = None,
                         history: list[dict] | None = None) -> list[JevRecord]:
        """The Jev stages in order, one call each; every stage sees the earlier answers. Only records are kept.

        state is the session state the rule table decided on (before the decision was applied), so a stage
        choosing a support sees the same candidates the table had. A stage that gets no answer leaves nothing
        for the next one; the next one still runs and its record names the missing stage.
        """
        assert self._jev is not None
        if state is None:
            state = self._repository.state(session_id)
        previous: dict[str, dict] = {}
        missing: list[str] = []
        records = []
        for stage in self._stages:
            built = stage.build(StageInput(inp, state, decision, window.touch, dict(previous), list(history or [])))
            if built is None:
                self._repository.attach(session_id, inp.t, stage.name, "skipped")
                continue
            stage_state, questions = built
            request = JevRequest(model=self._jev.model, state=stage_state, questions=questions)
            started = self._clock()
            try:
                response = await self._jev.ask(request)
            except Exception:
                # A shadow call must never surface: whatever broke, this stage simply has no answer.
                logger.exception("jev shadow %s crashed", stage.name)
                response = None
            latency_ms = round((self._clock() - started) * 1000)
            if response is None:
                record = JevRecord(session_id, window.window_end, tuple(questions), self._jev.model, "no_answer",
                                   latency_ms, decision_id=decision.decision_id, stage=stage.name,
                                   previous_missing=tuple(missing))
                missing.append(stage.name)
                self._repository.attach(session_id, inp.t, stage.name, "no_answer")
            else:
                answers = {
                    name: answer.noul if isinstance(answer, NoulAnswer)
                    else {"choice": getattr(answer, "choice", None), "confidence": answer.confidence}
                    for name, answer in response.answers.items()
                }
                record = JevRecord(session_id, window.window_end, tuple(questions), self._jev.model, "answered",
                                   latency_ms, response.model, answers, response.usage.model_dump(),
                                   decision.decision_id, stage.name, tuple(missing))
                previous[stage.name] = answers
                self._repository.attach(session_id, inp.t, stage.name, "answered", answers)
            self._repository.add_record(record)
            records.append(record)
            logger.info("jev shadow %s %s: %s in %d ms (%d questions)", stage.name, record.outcome,
                        response.model if response else "-", latency_ms, len(questions))
        return records

    async def drain(self) -> None:
        """Wait for background Jev calls (tests, shutdown)."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
