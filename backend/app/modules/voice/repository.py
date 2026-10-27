from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import UUID, uuid4

from app.modules.voice.exceptions import (
    IdempotencyKeyReused, RequestInProgress, VoiceSessionCompleted,
)
from app.modules.voice.schemas import (
    ToolCall, VoiceErrorResponse, VoiceRequestStatus, VoiceStatus, VoiceTurn,
)

ACTIVE_STATUSES = {"accepted", "processing"}
# Proposed value: recent exchanges per session passed to the interpreter as context.
HISTORY_TURNS = 10
# Proposed value: requests, idempotency keys and idle session context are dropped after this.
RETENTION = timedelta(hours=1)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class VoiceRecord:
    request_id: str
    session_id: str
    fingerprint: str
    accepted_at: datetime
    status: VoiceStatus = "accepted"
    reply_text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    error: VoiceErrorResponse | None = None

    def to_status(self) -> VoiceRequestStatus:
        return VoiceRequestStatus(
            request_id=self.request_id, status=self.status, reply_text=self.reply_text,
            tool_calls=list(self.tool_calls), actions=list(self.actions), error=self.error,
        )


class VoiceRepository:
    """Process-local voice request storage, reset on application restart.

    Request records keep a fingerprint only. Recognized text is kept solely in the
    per-session context (last HISTORY_TURNS exchanges) and is never logged.
    Everything older than the retention period is dropped on the next request.
    """

    def __init__(
        self, retention: timedelta = RETENTION, clock: Callable[[], datetime] = utc_now
    ):
        self._records: dict[str, VoiceRecord] = {}
        self._keys: dict[tuple[str, UUID], str] = {}
        self._history: dict[str, deque[VoiceTurn]] = {}
        self._last_turn_at: dict[str, datetime] = {}
        self._retention = retention
        self._clock = clock
        self._lock = Lock()

    def _prune(self, now: datetime) -> None:
        cutoff = now - self._retention
        expired = {rid for rid, r in self._records.items() if r.accepted_at < cutoff}
        for rid in expired:
            del self._records[rid]
        self._keys = {k: rid for k, rid in self._keys.items() if rid not in expired}
        for session_id in [s for s, at in self._last_turn_at.items() if at < cutoff]:
            del self._last_turn_at[session_id]
            self._history.pop(session_id, None)

    def accept(
        self, session_id: str, key: UUID, fingerprint: str,
        is_completed: Callable[[], bool] | None = None,
    ) -> tuple[VoiceRecord, bool]:
        """Return (record, created). Replays with the same key do not create a request."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            existing_id = self._keys.get((session_id, key))
            if existing_id is not None:
                existing = self._records[existing_id]
                if existing.fingerprint != fingerprint:
                    raise IdempotencyKeyReused()
                return existing, False
            if is_completed is not None and is_completed():
                raise VoiceSessionCompleted()
            if any(
                r.session_id == session_id and r.status in ACTIVE_STATUSES
                for r in self._records.values()
            ):
                raise RequestInProgress()
            record = VoiceRecord(
                request_id=f"vr_{uuid4().hex}", session_id=session_id,
                fingerprint=fingerprint, accepted_at=now,
            )
            self._records[record.request_id] = record
            self._keys[(session_id, key)] = record.request_id
            return record, True

    def get(self, session_id: str, request_id: str) -> VoiceRequestStatus | None:
        with self._lock:
            record = self._records.get(request_id)
            if record is None or record.session_id != session_id:
                return None
            return record.to_status()

    def update(
        self, request_id: str, status: VoiceStatus, reply_text: str | None = None,
        tool_calls: list[ToolCall] | None = None, error: VoiceErrorResponse | None = None,
    ) -> None:
        with self._lock:
            record = self._records.get(request_id)
            if record is None:  # dropped by retention while processing
                return
            record.status = status
            record.reply_text = reply_text
            record.tool_calls = list(tool_calls or [])
            record.error = error

    def history(self, session_id: str) -> list[VoiceTurn]:
        with self._lock:
            return list(self._history.get(session_id, ()))

    def append_turn(self, session_id: str, turn: VoiceTurn) -> None:
        with self._lock:
            self._history.setdefault(session_id, deque(maxlen=HISTORY_TURNS)).append(turn)
            self._last_turn_at[session_id] = self._clock()
