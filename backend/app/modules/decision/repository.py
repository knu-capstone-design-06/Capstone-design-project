"""Process-local session state, window records, shadow Jev records and the AI engine's windows; sessions idle past
the retention are dropped.

Every judged window is a WindowRecord for the whole session (the experiment's comparison rows, docs 7.1);
the trajectory stage reads only the last HISTORY_WINDOWS of them.
"""

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from threading import Lock

from app.modules.decision.schemas import (
    HISTORY_SCORES, HISTORY_STAGES, HISTORY_WINDOWS, NO_FIRST_PRESS, NO_PREVIOUS_WINDOW, NOT_AFTER_PREVIOUS,
    PREVIOUS_BEFORE_PRESS, STALE, TAGS, ChangeNote, JevRecord, SessionState, VisionWindow, WindowRecord,
)

RETENTION = timedelta(hours=1)   # as the voice context (voice/repository.py): records live as long as the session's talk


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionRepository:
    def __init__(self, retention: timedelta = RETENTION, clock: Callable[[], datetime] = utc_now):
        self._states: dict[str, SessionState] = {}
        self._records: dict[str, list[JevRecord]] = {}
        self._windows: dict[str, list[WindowRecord]] = {}
        self._vision: dict[str, list[VisionWindow]] = {}
        self._vision_after: dict[str, datetime] = {}   # the latest touch window's pairing bound (pair_vision's `after`)
        self._vision_last: dict[str, datetime] = {}    # the end of the engine window received last (kept when pruned)
        self._touched: dict[str, datetime] = {}
        self._retention = retention
        self._clock = clock
        self._lock = Lock()

    def _expire(self) -> datetime:
        """Drop the sessions idle past the retention. Every read and write calls it first, so nothing of an
        expired session is read or written back, whichever access comes first after the retention."""
        now = self._clock()
        cutoff = now - self._retention
        for stale in [s for s, at in self._touched.items() if at < cutoff]:
            for store in (self._touched, self._states, self._records, self._windows, self._vision,
                          self._vision_after, self._vision_last):
                store.pop(stale, None)
        return now

    def _touch(self, session_id: str) -> None:
        """Expire idle sessions, this one included, and only then mark this one as used: a session coming back
        after the retention starts fresh, as it would after another session's access."""
        self._touched[session_id] = self._expire()

    def _holds(self, window: WindowRecord) -> bool:
        return any(w is window for w in self._windows.get(window.session_id, ()))

    def state(self, session_id: str) -> SessionState:
        with self._lock:
            self._touch(session_id)
            return self._states.setdefault(session_id, SessionState())

    def save_state(self, session_id: str, state: SessionState) -> None:
        with self._lock:
            self._touch(session_id)
            self._states[session_id] = state

    def add_record(self, record: JevRecord, window: WindowRecord | None = None) -> bool:
        """Keep a shadow call's record. With the window it answered, only while that window is still kept: an
        answer arriving after its session expired does not bring the session back."""
        with self._lock:
            self._expire()   # before the window check: an expired session's window is no longer held
            if window is not None and not self._holds(window):
                return False
            self._touch(record.session_id)
            self._records.setdefault(record.session_id, []).append(record)
            return True

    def records(self, session_id: str) -> list[JevRecord]:
        with self._lock:
            self._expire()
            return list(self._records.get(session_id, []))

    def add_window(self, record: WindowRecord) -> None:
        with self._lock:
            self._touch(record.session_id)
            self._windows.setdefault(record.session_id, []).append(record)

    def add_vision(self, window: VisionWindow) -> datetime | None:
        """Keep one AI engine window of the session, in the order it arrived. Returns the end of the session's engine
        window received before it (None for the session's first), for the new-customer rule (note_user_changed).

        An engine post is not a use of the session: it expires idle sessions first and does not refresh this
        session's idle time, so a session whose order screen stopped still expires under the retention while the
        engine keeps posting (a session not used before is marked once, so its windows expire too). The windows a
        later /features window can no longer read are pruned on arrival: those that ended at or before the latest
        touch window's pairing bound (pair_vision), the new one included. The end of the window received last is kept
        apart from that pruning.
        """
        with self._lock:
            now = self._expire()
            session_id = window.session_id
            self._touched.setdefault(session_id, now)
            after = self._vision_after.get(session_id)
            kept = [w for w in self._vision.get(session_id, []) if after is None or w.window_end > after]
            if after is None or window.window_end > after:
                kept.append(window)
            self._vision[session_id] = kept
            previous = self._vision_last.get(session_id)
            self._vision_last[session_id] = window.window_end
            return previous

    def note_user_changed(self, session_id: str, event_ids: Sequence[str], window_end: float,
                          previous_end: float | None) -> ChangeNote | None:
        """Keep the new-customer events of an engine window whose user_changed tag is true, by the engine's event ids
        (DecisionService.change_events). window_end = the end of that engine window (its segment); previous_end = the
        end of the session's engine window received before it (add_vision), None for the first; all epoch seconds on the
        kiosk PC's clock like SessionState.first_press_t. Called when the window arrives (DecisionService.add_vision),
        so a window that no touch window reads, or one in a stretch that is not measurable, still counts.

        Every id is remembered for the session (SessionState.user_changed_seen), also before the first press and before
        the session's first /features window: one change stays true through about three overlapping engine windows with
        the same id, and an id the session already has is that change seen again, no new event.

        "After the first press" is meant in time. A new id becomes pending (user_changed_pending) only when the session
        has had its first press when this window arrives, AND the previous received engine window ended at or after the
        end of the touch window that held the first press (previous_end >= first_press_t), AND this window ended after
        it (window_end > previous_end). Otherwise the id is only remembered, and a later window that brings it again
        changes nothing.

        Why this is exact: the previous received window did not carry the id (else the session would already have it),
        and its tag looked back over the engine's situation window ending at its own end; this window carries the id;
        so the change lies after the previous window's end, whatever was lost in between. When that end is at or after
        the end of the first-press touch window, the change surely came after the first press. A change before the
        previous window's end is impossible by this argument. A change whose previous window ended before the end of
        the first-press window (inside it, or earlier with windows lost since) may have come before the first press:
        its id is only remembered. So are the ids of a session's first engine window (no previous one) and those that
        arrive before the /features window with the first press is judged. Counting such an id could open 2-2 over the
        newcomer's own cart; missing a 2-2 is the milder error (no dialog).

        An engine post: the session's idle time is not refreshed; a session without a state yet gets one (marked once
        like add_vision, so it still expires). Returns the new ids and, when they were only remembered, which condition
        failed (ChangeNote); None when no id was new."""
        with self._lock:
            now = self._expire()
            self._touched.setdefault(session_id, now)
            state = self._states.setdefault(session_id, SessionState())
            new = [e for e in dict.fromkeys(event_ids) if e not in state.user_changed_seen]
            if not new:
                return None
            state.user_changed_seen.extend(new)
            if not state.first_press or state.first_press_t is None:
                reason = NO_FIRST_PRESS
            elif previous_end is None:
                reason = NO_PREVIOUS_WINDOW
            elif previous_end < state.first_press_t:
                reason = PREVIOUS_BEFORE_PRESS
            elif not window_end > previous_end:
                reason = NOT_AFTER_PREVIOUS
            else:
                reason = None
                state.user_changed_pending.extend(new)
            return ChangeNote(tuple(new), reason)

    def vision(self, session_id: str) -> list[VisionWindow]:
        """The AI engine windows of the session still kept, in the order they arrived."""
        with self._lock:
            self._expire()
            return list(self._vision.get(session_id, []))

    def pair_vision(self, session_id: str, after: datetime, until: datetime
                    ) -> tuple[VisionWindow | None, VisionWindow | None, tuple[VisionWindow, ...]]:
        """(latest, named, inside) of the session's AI engine windows that ended in (after, until]: the latest one, the
        latest one whose situation names a tag (TAGS), or the latest one again when none does, and all of them (later
        arrivals first). Of two with the same end, the one that arrived last. The session's windows that ended at or
        before `after` are dropped first; the latest `after` is kept for add_vision's pruning (an earlier touch window
        arriving late does not lower it)."""
        with self._lock:
            # A /features window is a use of the session (its judgment touches it right after); marked here once so
            # the kept bound always expires with the session.
            self._touched.setdefault(session_id, self._expire())
            bound = self._vision_after.get(session_id)
            self._vision_after[session_id] = after if bound is None else max(bound, after)
            if session_id not in self._vision:
                return None, None, ()
            kept = self._vision[session_id] = [w for w in self._vision[session_id] if w.window_end > after]
            inside = [w for w in reversed(kept) if w.window_end <= until]   # later arrivals first
            if not inside:
                return None, None, ()
            latest = max(inside, key=lambda w: w.window_end)
            named = [w for w in inside if w.situation.get("name") in TAGS]
            return latest, max(named, key=lambda w: w.window_end) if named else latest, tuple(inside)

    def attach(self, window: WindowRecord, stage: str, outcome: str, answers: dict | None = None) -> None:
        """Add a stage's result to this one window record, as it arrives (never to another window that ended at
        the same time, such as one recorded as skipped while this call was in flight)."""
        with self._lock:
            self._expire()
            if not self._holds(window):
                return   # the session expired while the call was in flight
            window.outcomes[stage] = outcome
            if answers is not None:
                window.answers[stage] = answers

    def window_at(self, session_id: str, t: float) -> WindowRecord | None:
        """The last window of the session recorded as ending at t (for callers that did not keep the record)."""
        with self._lock:
            self._expire()
            return next((w for w in reversed(self._windows.get(session_id, [])) if w.t == t), None)

    def windows(self, session_id: str) -> list[WindowRecord]:
        """Every window of the session in the order it was recorded. Judged windows are in time order; a window
        recorded as STALE was recorded only (it arrived after a later one, or its time was off the session's
        timeline) and may end before the record ahead of it."""
        with self._lock:
            self._expire()
            return list(self._windows.get(session_id, []))

    def history(self, session_id: str, epoch: int | None = None) -> list[dict]:
        """The last HISTORY_WINDOWS judged windows as plain summaries for the trajectory stage, oldest first.

        Only HISTORY_STAGES answers ride along, and of them only the HISTORY_SCORES (the five state scores, not the
        rule table's own question asked in the same call); STALE windows are left out.
        """
        with self._lock:
            self._expire()
            # epoch: the windows since the frontend clock last moved only; their times are on one timeline.
            judged = [w for w in self._windows.get(session_id, []) if w.jev != STALE
                      and (epoch is None or w.epoch == epoch)]
            return [{
                "t": w.t, "tag": w.decision.get("tag"), "screen": w.inputs.get("screen"), "measurable": w.inputs.get("measurable"),
                "decision": w.decision.get("transition"), "support": w.decision.get("support"),
                "touch": {"taps": w.inputs.get("taps_segment"), "misses": w.inputs.get("misses_recent"),
                          "backs": w.inputs.get("backs_recent")},
                **{stage: {name: value for name, value in w.answers[stage].items() if name in HISTORY_SCORES}
                   for stage in HISTORY_STAGES if stage in w.answers},
            } for w in judged[-HISTORY_WINDOWS:]]
