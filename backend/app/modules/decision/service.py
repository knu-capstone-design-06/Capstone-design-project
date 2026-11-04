"""Judgment layer, shadow stage: run the rule table per window and ask Jev in the background.

judge() is synchronous and only changes the session state. observe() also schedules the Jev call
as a background task, so the /features response never waits for Jev; the answer is recorded for the
next window (jev_deadline: next_segment). Nothing here reaches the screen yet.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from collections.abc import Sequence

from app.infrastructure.external.jev_client import JevClient
from app.infrastructure.external.jev_schemas import JevRequest, NoulAnswer
from app.modules.decision.jev_questions import DEFAULT_STAGES, JevStage, StageInput
from app.modules.decision.repository import DecisionRepository
from app.modules.decision.rule_table import apply, decide
from app.modules.decision.schemas import (
    PILOT_PARAMS, Decision, DecisionParams, JevRecord, SessionState, WindowInput,
)
from app.modules.sessions.schemas import FeatureWindowRequest

logger = logging.getLogger(__name__)


def window_input(window: FeatureWindowRequest, measurable: bool, situation: dict | None = None,
                 gaze: bool | None = None) -> WindowInput:
    """One rule-table line from a /features window.

    The contract's five touch counts fill what they can: presses, misses and backs. What the frontend does not
    send yet stays None (near-miss fixes, pause since the last press, options dialog, screen progress), and
    the vision situation and gaze arrive only when the vision extension lands (docs/Jev-Integration.md).
    """
    touch = window.touch
    return WindowInput(
        t=window.window_end.timestamp(), measurable=measurable, situation=situation, screen=window.screen_id,
        gaze=gaze, misses_recent=touch.miss_tap_count, backs_recent=touch.back_count, taps_segment=touch.tap_count,
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
        self._in_flight: dict[str, asyncio.Task] = {}   # one Jev call per session at a time

    @property
    def shadow(self) -> bool:
        """True when Jev is asked (a client and at least one stage); False = the rule table alone."""
        return self._jev is not None and bool(self._stages)

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(stage.name for stage in self._stages)

    def in_flight(self, session_id: str) -> bool:
        return session_id in self._in_flight

    def judge(self, session_id: str, window: FeatureWindowRequest, measurable: bool,
              situation: dict | None = None, gaze: bool | None = None) -> Decision:
        """Run the rule table on this window and store the new session state."""
        inp = window_input(window, measurable, situation, gaze)
        state, decision = apply(self._repository.state(session_id), decide(inp, self._repository.state(session_id), self._params))
        self._repository.save_state(session_id, state)
        return decision

    def observe(self, session_id: str, window: FeatureWindowRequest, measurable: bool,
                situation: dict | None = None, gaze: bool | None = None) -> Decision:
        """judge(), then ask Jev in the background when a client exists and the window is measurable.

        One call per session at a time: while an answer is still on its way, the next window is not
        asked (its record would arrive out of order and say nothing new); the window after it asks again.
        """
        inp = window_input(window, measurable, situation, gaze)
        # The stages judge the window the rule table saw: the state before this decision was applied.
        before = copy.deepcopy(self._repository.state(session_id))
        history = self._repository.history(session_id)   # the windows before this one
        decision = self.judge(session_id, window, measurable, situation, gaze)
        self._repository.add_window(session_id, {
            "t": inp.t, "tag": decision.meta.get("tag"), "screen": inp.screen, "measurable": measurable,
            "decision": decision.transition, "support": decision.support,
            "touch": {"taps": inp.taps_segment, "misses": inp.misses_recent, "backs": inp.backs_recent},
        })
        if self.shadow and measurable and session_id not in self._in_flight:
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
        for the next one (it still runs, without that input).
        """
        assert self._jev is not None
        if state is None:
            state = self._repository.state(session_id)
        previous: dict[str, dict] = {}
        records = []
        for stage in self._stages:
            built = stage.build(StageInput(inp, state, decision, window.touch, dict(previous), list(history or [])))
            if built is None:
                continue
            stage_state, questions = built
            request = JevRequest(model=self._jev.model, state=stage_state, questions=questions)
            started = self._clock()
            response = await self._jev.ask(request)
            latency_ms = round((self._clock() - started) * 1000)
            if response is None:
                record = JevRecord(session_id, window.window_end, tuple(questions), self._jev.model, "no_answer",
                                   latency_ms, decision_id=decision.decision_id, stage=stage.name)
            else:
                answers = {
                    name: answer.noul if isinstance(answer, NoulAnswer)
                    else {"choice": getattr(answer, "choice", None), "confidence": answer.confidence}
                    for name, answer in response.answers.items()
                }
                record = JevRecord(session_id, window.window_end, tuple(questions), self._jev.model, "answered",
                                   latency_ms, response.model, answers, response.usage.model_dump(),
                                   decision.decision_id, stage.name)
                previous[stage.name] = answers
                # Later windows' trajectory stages read this window's answers from the history.
                self._repository.attach(session_id, inp.t, {stage.name: answers})
            self._repository.add_record(record)
            records.append(record)
            logger.info("jev shadow %s %s: %s in %d ms (%d questions)", stage.name, record.outcome,
                        response.model if response else "-", latency_ms, len(questions))
        return records

    async def drain(self) -> None:
        """Wait for background Jev calls (tests, shutdown)."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
