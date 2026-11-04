"""Process-local session state and shadow Jev records; sessions idle past the retention are dropped."""

from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import Lock

from app.modules.decision.schemas import JevRecord, SessionState

RETENTION = timedelta(hours=1)
# Recent windows kept per session for the trajectory stages (2 s windows: about ten seconds).
HISTORY_WINDOWS = 5


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionRepository:
    def __init__(self, retention: timedelta = RETENTION, clock: Callable[[], datetime] = utc_now):
        self._states: dict[str, SessionState] = {}
        self._records: dict[str, list[JevRecord]] = {}
        self._history: dict[str, deque] = {}
        self._touched: dict[str, datetime] = {}
        self._retention = retention
        self._clock = clock
        self._lock = Lock()

    def _touch(self, session_id: str) -> None:
        now = self._clock()
        self._touched[session_id] = now
        cutoff = now - self._retention
        for stale in [s for s, at in self._touched.items() if at < cutoff]:
            self._touched.pop(stale, None)
            self._states.pop(stale, None)
            self._records.pop(stale, None)
            self._history.pop(stale, None)

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

    def add_window(self, session_id: str, summary: dict) -> None:
        """Remember one judged window (tag, screen, decision, touch counts; scores arrive later)."""
        with self._lock:
            self._touch(session_id)
            self._history.setdefault(session_id, deque(maxlen=HISTORY_WINDOWS)).append(dict(summary))

    def attach(self, session_id: str, t: float, extra: dict) -> None:
        """Add late results (Jev scores) to the remembered window that ended at t."""
        with self._lock:
            for summary in self._history.get(session_id, ()):
                if summary.get("t") == t:
                    summary.update(extra)

    def history(self, session_id: str) -> list[dict]:
        """The remembered windows, oldest first, as copies."""
        with self._lock:
            return [dict(summary) for summary in self._history.get(session_id, ())]
