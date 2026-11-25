"""Judgment layer, shadow stage: run the rule table per window and ask Jev in the background.

judge() is synchronous and only changes the session state. observe() also records the window and, when
an experiment arm is on, schedules the Jev stages as a background task, so the /features response never
waits for Jev; the answers are attached to the window's record as they arrive (jev_deadline:
next_segment). Nothing here reaches the screen unless the demonstration switch DECISION_SEND_SUPPORT puts
observe()'s decision in the /features answer (sessions/service.support_answer); Jev answers never do.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
import logging
import os
import time
import traceback
from collections.abc import Sequence
from datetime import datetime, timezone

from app.infrastructure.external.jev_client import JevClient
from app.infrastructure.external.jev_schemas import JevRequest, NoulAnswer, ScoreAnswer
from app.modules.decision.jev_questions import DEFAULT_STAGES, JevStage, StageInput
from app.modules.decision.repository import DecisionRepository
from app.modules.decision.rule_table import apply, decide, tick
from app.modules.decision.schemas import (
    CHANGE_EVENT, CHANGED, PILOT_PARAMS, SCREEN_FLOW, STALE, ChangeNote, Decision, DecisionParams, JevRecord,
    PairedVision, SessionState, VisionWindow, WindowInput, WindowRecord,
)
from app.modules.sessions.schemas import FeatureWindowRequest, SceneTag, VisionWindowRequest

logger = logging.getLogger(__name__)


def steps_left(screen: str | None) -> int | None:
    """Screens left before the order ends, from the kiosk screen order; None for a screen not in it."""
    return len(SCREEN_FLOW) - 1 - SCREEN_FLOW.index(screen) if screen in SCREEN_FLOW else None


def window_input(window: FeatureWindowRequest, measurable: bool, situation: dict | None = None,
                 gaze: bool | None = None, previous_screen: str | None = None,
                 between: Sequence[str] = (), options_open: bool | None = None,
                 pause_s: float | None = None, **extra) -> WindowInput:
    """One rule-table line from a /features window.

    The contract's five touch counts fill what they can: presses, misses and backs. The screen id gives the steps
    left and, against the previous window's screen, whether the order moved forward (cart_progress). The pause and
    the options dialog come from the order screen's pilot block under the demonstration switch only
    (sessions/service.interaction_inputs), None otherwise. The vision situation and gaze come from the AI engine
    window paired with it (paired_vision), None without one. extra: the further WindowInput fields the session
    service gives under the switch (cart_items, the scene-signal counts of this window) and the span sums
    DecisionService._input makes of them (fixes_recent, zoom_attempt); None otherwise, so near-miss fixes stay None
    without the switch.
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
        backs_recent=touch.back_count, pause_s=pause_s, taps_segment=touch.tap_count,
        progress_segment=forward if known else None, options_open=options_open, **extra,
    )


def change_events(scene_tags: Sequence[SceneTag]) -> list[str]:
    """The new-customer events of one engine window (2-2): the event ids main_user_changed@<frame> (CHANGE_EVENT) in
    the evidence of its user_changed tag when that tag is true, each once, in order. A true tag without such an item
    gives none and is not an event: without the engine's id the backend cannot tell a new change from the same change
    seen again in the next overlapping window. The engine's user_changed is true only with these events (vision
    situation.user_changed), so only another sender's body is left out this way."""
    ids: list[str] = []
    for tag in scene_tags:
        if tag.name == CHANGED and tag.status is True:
            ids += [e.event_id for e in tag.evidence if e.event_id.startswith(CHANGE_EVENT + "@") and e.event_id not in ids]
    return ids


def recent_signals(own: dict, earlier: Sequence[tuple[float, dict]], t: float, span_s: float) -> dict:
    """fixes_recent (4-1) and zoom_attempt (2-1) of the window ending at t: its own scene-signal counts (own:
    fixes_segment, zoom_attempts_segment) summed with those of the earlier windows' input lines ((end, inputs) in
    `earlier`) that ended in (t - span_s, t), span_s = touch_span_s (window-granular: a /features window counts whole
    when its end lies in the span; with the order screen's 1 s windows that is this window and the four before it,
    about (t - 5, t]). A sum is None when this window or any of those lacks the count (no block, a malformed one, or
    null). zoom_attempt is true for a sum of one or more."""
    span = [inputs for end, inputs in earlier if t - span_s < end < t]

    def total(key: str) -> int | None:
        counts = [own.get(key), *(inputs.get(key) for inputs in span)]
        return None if any(count is None for count in counts) else sum(counts)

    zooms = total("zoom_attempts_segment")
    return {"fixes_recent": total("fixes_segment"), "zoom_attempt": None if zooms is None else zooms >= 1}


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


def where(exc: BaseException) -> str:
    """file:line of the innermost frame an exception came from: enough to find a bug in our own code, without
    the exception's message, which may quote the state."""
    frames = traceback.extract_tb(exc.__traceback__)
    ours = [f for f in frames if f"{os.sep}app{os.sep}" in f.filename or "/app/" in f.filename] or frames
    return f"{os.path.basename(ours[-1].filename)}:{ours[-1].lineno}" if ours else "?"


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
    if state.first_press_t is not None:
        state.first_press_t += by
    for item in state.withdrawn:
        item["scope"] = scope(item.get("scope"))
    if state.held is not None:
        held = state.held
        state.held = dataclasses.replace(
            held, shown_t=held.shown_t + by, scope=scope(held.scope),
            decision=dataclasses.replace(held.decision, scope=scope(held.decision.scope)))
    return state


def pairing_after(window: FeatureWindowRequest) -> datetime:
    """The lower bound of a /features window's pairing span (after, end]: start - (end - start), so the span is this
    touch window and one more of its length before it. The one place the bound is made: paired_vision reads the AI
    engine windows that ended in the span, pressed_before the session's earlier touch windows."""
    start, end = window.window_start, window.window_end
    return start - (end - start)


def stale_decision() -> Decision:
    """What judge() returns for a window recorded only (late, or off the session's timeline): nothing changes."""
    return Decision("none", {}, reason="window late or off the session's timeline; recorded only")


def paired_record(vision: PairedVision | None) -> dict | None:
    """What a window record keeps of the AI engine windows it read: the latest one (its times, version), its face and
    its scene tags (no rule of table v0 reads them; the later rows will), and the end of the window the situation came
    from (the same end when the latest gave it)."""
    if vision is None:
        return None
    return {"window_start": vision.window_start, "window_end": vision.window_end, "received_at": vision.received_at,
            "model_version": vision.model_version, "face_seen": vision.face_seen, "scene_tags": vision.scene_tags,
            "situation_window_end": vision.situation_window_end}


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
                 now=time.monotonic, wall=lambda: datetime.now(timezone.utc)):
        self._repository = repository
        self._params = params
        self._jev = jev
        self._stages = tuple(stages)   # Jev calls in order; each sees the answers before it (stackable)
        self._clock = clock
        self._now = now                # server time passed between windows (monotonic), for the session's timeline
        self._wall = wall              # server UTC kept in the records, beside the frontend's window times
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

    def add_vision(self, session_id: str, window: VisionWindowRequest, received_at: datetime | None = None
                   ) -> ChangeNote | None:
        """Keep a window the AI engine posted for the session, for the /features windows that read it.

        A window whose user_changed tag is true also gives the session's new-customer events (2-2) right here, by the
        engine's event ids (change_events), when it arrives, not when a /features window pairs it: a window that falls
        in a stretch that is not measurable, or an engine that runs late, cannot lose it. Every id is remembered; a new
        id is an event only when the session's previous received engine window ended at or after the end of the
        first-press touch window (note_user_changed, which gets this window's end and the previous window's end for
        that). Returns what note_user_changed kept (the new ids and why they were only remembered), None when no id
        was new; the session service logs it.
        """
        obs = window.observations
        previous_end = self._repository.add_vision(VisionWindow(
            session_id, window.window_start, window.window_end, window.situation.model_dump(mode="json"),
            obs.gaze, obs.face_seen, [tag.model_dump(mode="json") for tag in obs.scene_tags], window.model_version,
            received_at or self._wall(),
        ))
        changes = change_events(obs.scene_tags)
        if not changes:
            return None
        return self._repository.note_user_changed(
            session_id, changes, window.window_end.timestamp(), None if previous_end is None else previous_end.timestamp())

    def paired_vision(self, session_id: str, window: FeatureWindowRequest) -> PairedVision | None:
        """The AI engine windows a /features window reads: those of the session that ended inside this touch window
        or the one before it, start - (end - start) < engine window end <= end. The latest of them gives the gaze, the
        face and the scene tags; the situation comes from the latest of them that names a tag, the latest one when
        none does (PairedVision).

        The order screen sends a touch window to the engine first and its /features request after the engine's answer
        (at most one tick of its transport later), and the engine answers after handing on the windows that touch
        window released when it can within its window interval, so the request of the same touch window usually reads
        the engine windows of its own stretch. One that arrives late is read by the next request while it still ends
        inside that request's pairing span. Handing on and reading are best effort: a window whose send ended in a
        failure may or may not have reached the backend, and a window replaced before it was sent or one that arrives
        after the pairing span is read by no request. The bound holds two 1 s segments (this stretch's and the one
        before), all kept: a tag that holds in the earlier one only is not
        lost behind a later `none`. The only tolerance is the touch window's own length; both times are on the kiosk
        PC's clock. The session's engine windows that ended at or before that bound are dropped. None: no such window
        (situation and gaze stay unknown, as without the engine). All windows in the bound are kept on the answer for
        the scene tags (PairedVision.scene_tag_states: true when any of them says true).
        """
        latest, named, inside = self._repository.pair_vision(session_id, pairing_after(window), window.window_end)
        return None if latest is None else PairedVision(latest, named, inside)

    def pressed_before(self, session_id: str, window: FeatureWindowRequest) -> bool:
        """Whether an earlier touch window of the session that held a tap or a back ended inside this window's pairing
        span: pairing_after(window) < its end < this window's end. The press evidence over the same span as the engine
        windows paired_vision gives this window (sessions/service.measurable_here, under the demonstration switch).

        The session's own recorded windows on its current timeline only, as the scene-signal sums in _input read
        them: judged windows of the current epoch, not those recorded only (STALE). Their input lines hold the taps
        (taps_segment) and backs (backs_recent), their record time t is their end. Called after place() and before
        observe() records this window: the epoch is the one this window is placed in (a window that confirms a clock
        move has started the new one), and this window is not among the records."""
        after, t = pairing_after(window).timestamp(), window.window_end.timestamp()
        epoch = self._repository.state(session_id).epoch
        return any(w.epoch == epoch and w.jev != STALE and after < w.t < t
                   and ((w.inputs.get("taps_segment") or 0) > 0 or (w.inputs.get("backs_recent") or 0) > 0)
                   for w in self._repository.windows(session_id))

    def _input(self, session_id: str, window: FeatureWindowRequest, measurable: bool, situation, gaze,
               options_open: bool | None = None, pause_s: float | None = None, **extra) -> WindowInput:
        # The previous screen is the last judged window that ended no later than this one: for a late window,
        # the one before it in time, so its comparison row keeps the time order of the screens. Only windows
        # the table could act on count (measurable, a screen of the flow): when the window that crossed to the
        # next screen was not measurable, the next measurable one still shows the step forward and withdraws 4-2.
        # The screens of the windows passed over since then go along, so a step forward they hide is still seen.
        # Times compare within one epoch only. The windows of earlier epochs came before this one whatever their
        # times say, so they stay ahead in the order they arrived: a screen change that falls on the clock move is
        # still seen (menu, clock moved, review), and the screen is not read from an earlier time of the old
        # timeline (review at 3000, clock set back, review at 1006: compared with that review, not with a menu at 1000).
        # The window the clock move was first seen on (the record just before an epoch's first one) was recorded
        # only, but it did come in order: its screen goes along like that of a window that was not measurable, so
        # a step back or forward that fell on it is not lost (review, clock moved on a menu window, review again).
        t = window.window_end.timestamp()
        epoch = self._repository.state(session_id).epoch
        recorded = self._repository.windows(session_id)
        crossed = {id(w) for w, after in zip(recorded, [w.epoch for w in recorded[1:]] + [epoch]) if after > w.epoch}
        windows = [w for w in recorded if w.jev != STALE or id(w) in crossed]
        judged = [w for w in windows if w.epoch < epoch] + [w for w in windows if w.epoch == epoch and w.t <= t]
        # The scene-signal sums read the judged windows of this epoch only: their times are on this one timeline.
        extra = {**extra, **recent_signals(
            extra, [(w.t, w.inputs) for w in judged if w.epoch == epoch and w.jev != STALE], t, self._params.touch_span_s)}
        seen = [i for i, w in enumerate(judged) if w.jev != STALE and w.inputs.get("measurable")
                and w.inputs.get("screen") in SCREEN_FLOW]
        if not seen:
            return window_input(window, measurable, situation, gaze, options_open=options_open, pause_s=pause_s,
                                **extra)
        return window_input(window, measurable, situation, gaze, judged[seen[-1]].inputs.get("screen"),
                            [w.inputs.get("screen") for w in judged[seen[-1] + 1:]], options_open, pause_s, **extra)

    def judge(self, session_id: str, window: FeatureWindowRequest, measurable: bool,
              situation: dict | None = None, gaze: bool | None = None) -> Decision:
        """Run the rule table on this window and store the new session state (no record, no Jev)."""
        placed = self._place(session_id, window.window_end.timestamp())
        inp = self._input(session_id, window, measurable, situation, gaze)
        return self._decide(session_id, inp)[0] if placed else stale_decision()

    def place(self, session_id: str, window: FeatureWindowRequest) -> bool:
        """_place ahead of observe(), for a caller that reads the session's timeline before the window is observed: the
        session service under the demonstration switch, so pressed_before reads the epoch this window is placed in.
        The result goes to observe(placed=...), which then does not place the window again: placed once either way."""
        return self._place(session_id, window.window_end.timestamp())

    def _place(self, session_id: str, t: float) -> bool:
        """Whether the window ending at t is judged (True) or recorded only (False). Called once per window.

        Windows are judged in time order. When /features requests overlap and an earlier window's answer from
        ai-engine arrives after a later window was judged, that earlier window must not roll the session back
        (reopen a withdrawn support, undo a screen's progress): it is recorded only.

        A window whose time is off the session's timeline in either direction (a bad request, a clock a day
        off) is recorded only as well: judged, it would lapse an open ask at once or send the session back.
        Only when the next window follows that one, two in a row on another timeline, has the frontend clock
        really moved: a new epoch starts, the times the session holds move with the clock, and that window is
        judged. One wrong time beyond CLOCK_JUMP_S in the middle of a session costs that window and no other.
        When the session's very first window is the wrong one it is judged (there is nothing to compare it
        with), the next window is the one recorded only, and the one after it starts a new epoch.

        A window recorded only leaves the session's supports and screens as they are and its screen is not
        read, with one exception: the window a clock move was first seen on did come in order, so once the
        move is confirmed its screen and situation tag are taken as those of a window that was not measurable
        (a screen change that fell on it still counts; nothing is opened or withdrawn by it).

        What this cannot tell apart, by choice of a wide band:
          - a wrong time inside the band is judged as it stands: one window 5 min ahead makes the next ones late
            until the clock passes it, and a clock corrected by less than the band does the same (set back
            2 min: about 2 min of windows recorded only; set ahead 5 min: an ask shown 2 s ago lapses);
          - two windows in a row each more than CLOCK_JUMP_S late read as a clock that moved back;
          - a late window more than CLOCK_JUMP_S late and one wrong time look the same, so neither's screen is read.
        A sequence number in the contract would need no timeline, band or epoch for the order of windows
        (docs/Jev-Integration.md 7.1); how long things have been shown would still be read from window times.
        """
        state = self._repository.state(session_id)
        now = self._now()
        if state.last_t is None or state.last_now is None:
            return True
        drift = (t - state.last_t) - (now - state.last_now)
        if abs(drift) <= CLOCK_JUMP_S:
            state.alt_t = state.alt_now = None
            self._repository.save_state(session_id, state)
            # False: a late window, or the same window sent again (an equal end time is not a second window).
            return t > state.last_t
        # A later window that continues the one before it. The same window sent twice is not a second one.
        follows = (state.alt_t is not None and t > state.alt_t
                   and abs((t - state.alt_t) - (now - state.alt_now)) <= CLOCK_JUMP_S)
        if not follows:
            state.alt_t, state.alt_now = t, now
            self._repository.save_state(session_id, state)
            return False                                 # off the timeline: wait for the next window
        crossed_t = state.alt_t
        state = moved(state, drift)                      # how long things have been shown stays the same
        state.epoch, state.alt_t, state.alt_now = state.epoch + 1, None, None
        # The window the move was first seen on came in order after all. Its cues stay unjudged, but the screen
        # it was on is where the session was: taken as a window that was not measurable, so a screen visit that
        # began or ended on it is not merged with the visit before the move.
        recorded = self._repository.windows(session_id)
        if recorded and recorded[-1].jev == STALE and recorded[-1].t == crossed_t:
            crossed = WindowInput(**{**recorded[-1].inputs, "measurable": False})
            state, _ = apply(state, decide(crossed, state, self._params))
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
                situation: dict | None = None, gaze: bool | None = None, ai: str | None = None,
                ai_model_version: str | None = None, received_at: datetime | None = None,
                vision: PairedVision | None = None, options_open: bool | None = None,
                pause_s: float | None = None, placed: bool | None = None, **extra) -> Decision:
        """judge(), record the window, then ask Jev in the background when the arm is on and the window allows.

        One call chain per session at a time: while an answer is still on its way, the next window is recorded
        as skipped rather than asked; the window after it asks again. A window that is late or off the
        session's timeline (_place) is recorded as STALE: no support or screen changes, no Jev call.
        vision is the AI engine windows the situation and gaze came from (paired_vision), kept on the record.
        options_open and pause_s come from the order screen's pilot block under the demonstration switch only, and
        so do the further input fields in extra (window_input). placed: place()'s result when the caller placed the
        window first (the demonstration switch); None places it here.
        """
        placed = self._place(session_id, window.window_end.timestamp()) if placed is None else placed
        inp = self._input(session_id, window, measurable, situation, gaze, options_open, pause_s, **extra)
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
            self.stage_names, why, self._jev.model if self._jev else None, timed_out, epoch=epoch, ai=ai,
            ai_model_version=ai_model_version, received_at=received_at or self._wall(),
            vision_window=paired_record(vision),
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
            started, reason, response = self._clock(), None, None
            request = None
            try:
                # The whole stage: building the question can fail as well as the call. Either way this stage
                # simply has no answer, the later stages still run and the window keeps its record. Building
                # covers the request too (a stage's wrong shape, a state that does not serialise): our fault,
                # not Jev's. Only the exception's type is logged: its message may quote the state.
                built = stage.build(StageInput(inp, state, decision, window.touch, dict(previous), list(history or [])))
                if built is not None:
                    stage_state, questions = built
                    request = JevRequest(model=self._jev.model, state=stage_state, questions=questions)
                    # The body must be valid JSON as sent (no NaN or infinity), or the call fails as if Jev did.
                    json.dumps(request.model_dump(mode="json"), allow_nan=False)
            except Exception as exc:
                # A shadow call must never surface.
                logger.error("jev shadow %s could not build its question (%s at %s)", stage.name,
                             type(exc).__name__, where(exc))
                built, reason, request = (), "build_error", None   # a request built before the failure is not sent
                # The names of questions built before the request failed stay on the record; nothing else does.
                questions = questions if isinstance(questions, dict) else {}
            if built is None:
                mark(stage.name, "skipped")
                continue
            if request is not None:
                try:
                    response = await self._jev.ask(request)
                except Exception as exc:
                    logger.error("jev shadow %s crashed (%s at %s)", stage.name, type(exc).__name__, where(exc))
                    response = None
                if response is None:
                    reason = "unavailable"
            latency_ms = round((self._clock() - started) * 1000)
            if response is not None and not answers_fit(questions, response.answers):
                # Answers that do not answer what was asked would spoil the record and the next stage's state.
                logger.warning("jev shadow %s answered something else than asked", stage.name)
                reason = "mismatch"
            if reason is not None:
                billed = response if reason == "mismatch" else None
                record = JevRecord(session_id, window.window_end, tuple(questions), self._jev.model, "no_answer",
                                   latency_ms, billed.model if billed else None, {},
                                   billed.usage.model_dump() if billed else None, decision.decision_id, stage.name,
                                   tuple(missing), reason, None if reason == "build_error" else self._wall())
                missing.append(stage.name)
                mark(stage.name, "no_answer")
            else:
                asked = {name: response.answers[name] for name in questions}   # an answer nobody asked for is dropped
                answers = {name: recorded_answer(answer) for name, answer in asked.items()}
                record = JevRecord(session_id, window.window_end, tuple(questions), self._jev.model, "answered",
                                   latency_ms, response.model, answers, response.usage.model_dump(),
                                   decision.decision_id, stage.name, tuple(missing), answered_at=self._wall())
                previous[stage.name] = {name: passed_answer(answer) for name, answer in asked.items()}
                mark(stage.name, "answered", answers)
            self._repository.add_record(record, window_record)
            records.append(record)
            logger.info("jev shadow %s %s%s: %.40s in %d ms (%d questions)", stage.name, record.outcome,
                        f" ({reason})" if reason else "", record.response_model or "-", latency_ms, len(questions))
        return records

    async def drain(self) -> None:
        """Wait for background Jev calls (tests, shutdown)."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
