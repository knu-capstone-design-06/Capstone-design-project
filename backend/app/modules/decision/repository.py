"""Process-local session state, window records and shadow Jev records; sessions idle past the retention are dropped.

Every judged window is a WindowRecord for the whole session (the experiment's comparison rows, docs 7.1);
the trajectory stage reads only the last HISTORY_WINDOWS of them.
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import Lock

from app.modules.decision.schemas import HISTORY_WINDOWS, JevRecord, SessionState, WindowRecord

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
        now = self._clock()
        self._touched[session_id] = now
        cutoff = now - self._retention
        for stale in [s for s, at in self._touched.items() if at < cutoff]:
            for store in (self._touched, self._states, self._records, self._windows):
                store.pop(stale, None)

    def state(self, session_id: str) -> SessionState:
        with self._lock:
            self._touch(session_id)
            return self._states.setdefault(session_id, SessionState())

    def save_state(self, session_id: str, state: SessionState) -> None:
        with self._lock:
            self._touch(session_id)
            self._states[session_id] = state

    def add_record(self, record: JevRecord) -> None:
        with self._lock:
            self._touch(record.session_id)
            self._records.setdefault(record.session_id, []).append(record)

    def records(self, session_id: str) -> list[JevRecord]:
        with self._lock:
            return list(self._records.get(session_id, []))

    def add_window(self, record: WindowRecord) -> None:
        with self._lock:
            self._touch(record.session_id)
            self._windows.setdefault(record.session_id, []).append(record)

    def attach(self, session_id: str, t: float, stage: str, outcome: str, answers: dict | None = None) -> None:
        """Add a stage's result to the window that ended at t, as it arrives."""
        with self._lock:
            for window in self._windows.get(session_id, ()):
                if window.t == t:
                    window.outcomes[stage] = outcome
                    if answers is not None:
                        window.answers[stage] = answers

    def windows(self, session_id: str) -> list[WindowRecord]:
        """Every judged window of the session, oldest first."""
        with self._lock:
            return list(self._windows.get(session_id, []))

    def history(self, session_id: str) -> list[dict]:
        """The last HISTORY_WINDOWS windows as plain summaries for the trajectory stage, oldest first."""
        with self._lock:
            recent = self._windows.get(session_id, [])[-HISTORY_WINDOWS:]
            return [{
                "t": w.t, "tag": w.decision.get("tag"), "screen": w.inputs.get("screen"), "measurable": w.inputs.get("measurable"),
                "decision": w.decision.get("transition"), "support": w.decision.get("support"),
                "touch": {"taps": w.inputs.get("taps_segment"), "misses": w.inputs.get("misses_recent"),
                          "backs": w.inputs.get("backs_recent")},
                **{stage: answers for stage, answers in w.answers.items()},
            } for w in recent]
