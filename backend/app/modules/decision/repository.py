"""Process-local session state, window records and shadow Jev records; sessions idle past the retention are dropped.

Every judged window is a WindowRecord for the whole session (the experiment's comparison rows, docs 7.1);
the trajectory stage reads only the last HISTORY_WINDOWS of them.
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import Lock

from app.modules.decision.schemas import (
    HISTORY_SCORES, HISTORY_STAGES, HISTORY_WINDOWS, STALE, JevRecord, SessionState, WindowRecord,
)

RETENTION = timedelta(hours=1)   # as the voice context (voice/repository.py): records live as long as the session's talk


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionRepository:
    def __init__(self, retention: timedelta = RETENTION, clock: Callable[[], datetime] = utc_now):
        self._states: dict[str, SessionState] = {}
        self._records: dict[str, list[JevRecord]] = {}
        self._windows: dict[str, list[WindowRecord]] = {}
        self._touched: dict[str, datetime] = {}
        self._retention = retention
        self._clock = clock
        self._lock = Lock()

    def _touch(self, session_id: str) -> None:
        """Drop the sessions idle past the retention, this one included, and only then mark this one as used:
        a session coming back after the retention starts fresh, as it would after another session's access."""
        now = self._clock()
        cutoff = now - self._retention
        for stale in [s for s, at in self._touched.items() if at < cutoff]:
            for store in (self._touched, self._states, self._records, self._windows):
                store.pop(stale, None)
        self._touched[session_id] = now

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
            if window is not None and not self._holds(window):
                return False
            self._touch(record.session_id)
            self._records.setdefault(record.session_id, []).append(record)
            return True

    def records(self, session_id: str) -> list[JevRecord]:
        with self._lock:
            return list(self._records.get(session_id, []))

    def add_window(self, record: WindowRecord) -> None:
        with self._lock:
            self._touch(record.session_id)
            self._windows.setdefault(record.session_id, []).append(record)

    def attach(self, window: WindowRecord, stage: str, outcome: str, answers: dict | None = None) -> None:
        """Add a stage's result to this one window record, as it arrives (never to another window that ended at
        the same time, such as one recorded as skipped while this call was in flight)."""
        with self._lock:
            if not self._holds(window):
                return   # the session expired while the call was in flight
            window.outcomes[stage] = outcome
            if answers is not None:
                window.answers[stage] = answers

    def window_at(self, session_id: str, t: float) -> WindowRecord | None:
        """The last window of the session recorded as ending at t (for callers that did not keep the record)."""
        with self._lock:
            return next((w for w in reversed(self._windows.get(session_id, [])) if w.t == t), None)

    def windows(self, session_id: str) -> list[WindowRecord]:
        """Every window of the session in the order it was recorded. Judged windows are in time order; a window
        recorded as STALE arrived after a later one and may end before the record ahead of it."""
        with self._lock:
            return list(self._windows.get(session_id, []))

    def history(self, session_id: str) -> list[dict]:
        """The last HISTORY_WINDOWS judged windows as plain summaries for the trajectory stage, oldest first.

        Only HISTORY_STAGES answers ride along, and of them only the HISTORY_SCORES (the five state scores, not the
        rule table's own question asked in the same call); STALE windows are left out.
        """
        with self._lock:
            judged = [w for w in self._windows.get(session_id, []) if w.jev != STALE]
            return [{
                "t": w.t, "tag": w.decision.get("tag"), "screen": w.inputs.get("screen"), "measurable": w.inputs.get("measurable"),
                "decision": w.decision.get("transition"), "support": w.decision.get("support"),
                "touch": {"taps": w.inputs.get("taps_segment"), "misses": w.inputs.get("misses_recent"),
                          "backs": w.inputs.get("backs_recent")},
                **{stage: {name: value for name, value in w.answers[stage].items() if name in HISTORY_SCORES}
                   for stage in HISTORY_STAGES if stage in w.answers},
            } for w in judged[-HISTORY_WINDOWS:]]
