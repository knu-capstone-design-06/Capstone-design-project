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
                 gaze: bool | None = None, previous_screen: str | None = None,
                 between: Sequence[str] = ()) -> WindowInput:
    """One rule-table line from a /features window.

    The contract's five touch counts fill what they can: presses, misses and backs. The screen id gives the steps
    left and, against the previous window's screen, whether the order moved forward (cart_progress). What the
    frontend does not send yet stays None (near-miss fixes, pause since the last press, options dialog), and the
    vision situation and gaze arrive only when the vision values are passed on (docs/Jev-Integration.md).
    """
    touch = window.touch
    # Progress is known only between two screens of the flow: with a screen id outside it (the voice API's
    # "menu_list", a new screen) or no window before, it is None, not "no progress". A window lost in between
    # (menu, then complete) is still a step forward. `between` holds the screens of the windows since
    # previous_screen that were not measurable: as in the vision chain, one step forward anywhere on the way
    # is progress (review, back to the menu unseen, review again).
    known = previous_screen in SCREEN_FLOW and window.screen_id in SCREEN_FLOW
    path = [SCREEN_FLOW.index(s) for s in (previous_screen, *between, window.screen_id) if s in SCREEN_FLOW]
    forward = known and any(later > earlier for earlier, later in zip(path, path[1:]))
    return WindowInput(
        t=window.window_end.timestamp(), measurable=measurable, situation=situation, screen=window.screen_id,
        steps_left=steps_left(window.screen_id), gaze=gaze, misses_recent=touch.miss_tap_count,
        backs_recent=touch.back_count, taps_segment=touch.tap_count,
        progress_segment=forward if known else None,
    )


# No source. Window times come from the frontend clock, which may run ahead of or behind the server's by a
# constant amount. The last judged window and the server time it was judged at give the session's timeline;
# a window is on it when its time is within this of where the server time passed puts it. Wide on purpose:
# tests and replays of recorded sessions feed windows faster than real time, and only a plainly wrong time
# (a clock a day off, a clock set mid-session) has to be told apart.
CLOCK_JUMP_S = 600.0


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


def moved(state: SessionState, by: float) -> SessionState:
    """The state with every time it holds moved onto the timeline the frontend clock jumped to.

    A scope carries the time its tag or screen visit began, and a withdrawn support is not opened again in
    the same scope: the scopes move too, or the same visit would read as a new one and reopen what was withdrawn.
    """
    def scope(value):
        if value is not None and len(value) == 3 and isinstance(value[2], (int, float)):
            return (value[0], value[1], value[2] + by)
        return value

    state = copy.deepcopy(state)
    if state.tag_since is not None:
        state.tag_since += by
    if state.screen_since is not None:
        state.screen_since += by
    for item in state.withdrawn:
        item["scope"] = scope(item.get("scope"))
    if state.held is not None:
        held = state.held
        state.held = dataclasses.replace(
            held, shown_t=held.shown_t + by, scope=scope(held.scope),
            decision=dataclasses.replace(held.decision, scope=scope(held.decision.scope)))
    return state


def stale_decision() -> Decision:
    """What judge() returns for a window recorded only (late, or off the session's timeline): nothing changes."""
    return Decision("none", {}, reason="window late or off the session's timeline; recorded only")


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
                 now=time.monotonic):
        self._repository = repository
        self._params = params
        self._jev = jev
        self._stages = tuple(stages)   # Jev calls in order; each sees the answers before it (stackable)
        self._clock = clock
        self._now = now                # server time passed between windows (monotonic), for the session's timeline
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
        # The screens of the windows passed over since then go along, so a step forward they hide is still seen.
        # Times compare within one epoch only: after the frontend clock moved, the windows before it are left out.
        t = window.window_end.timestamp()
        epoch = self._repository.state(session_id).epoch
        judged = [w for w in self._repository.windows(session_id) if w.jev != STALE and w.epoch == epoch and w.t <= t]
        seen = [i for i, w in enumerate(judged) if w.inputs.get("measurable") and w.inputs.get("screen") in SCREEN_FLOW]
        if not seen:
            return window_input(window, measurable, situation, gaze)
        return window_input(window, measurable, situation, gaze, judged[seen[-1]].inputs.get("screen"),
                            [w.inputs.get("screen") for w in judged[seen[-1] + 1:]])

    def judge(self, session_id: str, window: FeatureWindowRequest, measurable: bool,
              situation: dict | None = None, gaze: bool | None = None) -> Decision:
        """Run the rule table on this window and store the new session state (no record, no Jev)."""
        placed = self._place(session_id, window.window_end.timestamp())
        inp = self._input(session_id, window, measurable, situation, gaze)
        return self._decide(session_id, inp)[0] if placed else stale_decision()

    def _place(self, session_id: str, t: float) -> bool:
        """Whether the window ending at t is judged (True) or recorded only (False). Called once per window.

        Windows are judged in time order. When /features requests overlap and an earlier window's answer from
        ai-engine arrives after a later window was judged, that earlier window must not roll the session back
        (reopen a withdrawn support, undo a screen's progress): it is recorded only.

        A window whose time is off the session's timeline in either direction (a bad request, a clock a day
        off) is recorded only as well: judged, it would lapse an open ask at once or send the session back.
        Only when the next window follows that one, two in a row on another timeline, has the frontend clock
        really moved: a new epoch starts, the times the session holds move with the clock, and that window is
        judged. A wrong time beyond CLOCK_JUMP_S costs that window and no other.

        What this cannot tell apart, by choice of a wide band: a wrong time inside the band is judged as it
        stands (a window 5 min ahead makes the next ones late until the clock passes it), and two windows in a
        row each more than CLOCK_JUMP_S late read as a clock that moved back.
        """
        state = self._repository.state(session_id)
        now = self._now()
        if state.last_t is None or state.last_now is None:
            return True
        drift = (t - state.last_t) - (now - state.last_now)
        if abs(drift) <= CLOCK_JUMP_S:
            state.alt_t = state.alt_now = None
            return t >= state.last_t                     # False: a late window
        follows = (state.alt_t is not None and t >= state.alt_t
                   and abs((t - state.alt_t) - (now - state.alt_now)) <= CLOCK_JUMP_S)
        if not follows:
            state.alt_t, state.alt_now = t, now
            return False                                 # off the timeline: wait for the next window
        state = moved(state, drift)                      # how long things have been shown stays the same
        state.epoch, state.alt_t, state.alt_now = state.epoch + 1, None, None
        state.last_t, state.last_now = state.last_t + drift, state.last_now
        self._repository.save_state(session_id, state)
        return True

    def _decide(self, session_id: str, inp: WindowInput) -> tuple[Decision, SessionState, str | None]:
        """(decision, state before the decision, ask withdrawn for no response) of a window _place let through."""
        state = self._repository.state(session_id)
        state, timed_out = tick(state, inp.t, self._params)      # an unanswered ask lapses first
        before = copy.deepcopy(state)
        state, decision = apply(state, decide(inp, state, self._params))
        state.last_t, state.last_now = inp.t, self._now()
        self._repository.save_state(session_id, state)
        return decision, before, timed_out

    def _judge(self, session_id: str, inp: WindowInput) -> tuple[Decision | None, SessionState, str | None]:
        """_place and _decide for a ready input line (tests): (None, state, None) when it is recorded only."""
        if not self._place(session_id, inp.t):
            return None, self._repository.state(session_id), None
        return self._decide(session_id, inp)

    def observe(self, session_id: str, window: FeatureWindowRequest, measurable: bool,
                situation: dict | None = None, gaze: bool | None = None) -> Decision:
        """judge(), record the window, then ask Jev in the background when the arm is on and the window allows.

        One call chain per session at a time: while an answer is still on its way, the next window is recorded
        as skipped rather than asked; the window after it asks again. A window that is late or off the
        session's timeline (_place) is recorded as STALE: no state change, no Jev call.
        """
        placed = self._place(session_id, window.window_end.timestamp())
        inp = self._input(session_id, window, measurable, situation, gaze)
        epoch = self._repository.state(session_id).epoch
        # The windows before this one, of this epoch only (not those from before the frontend clock moved).
        history = self._repository.history(session_id, epoch)
        decision, before, timed_out = self._decide(session_id, inp) if placed else (None, None, None)
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
            self.stage_names, why, self._jev.model if self._jev else None, timed_out, epoch=epoch,
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
