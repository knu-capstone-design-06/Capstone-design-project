from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from uuid import UUID, uuid4

from app.modules.voice.exceptions import IdempotencyKeyReused, RequestInProgress
from app.modules.voice.schemas import (
    ToolCall, VoiceErrorResponse, VoiceRequestStatus, VoiceStatus, VoiceTurn,
)

ACTIVE_STATUSES = {"accepted", "processing"}
# Proposed value: recent exchanges per session passed to the interpreter as context.
HISTORY_TURNS = 10


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
    """

    def __init__(self):
        self._records: dict[str, VoiceRecord] = {}
        self._keys: dict[tuple[str, UUID], str] = {}
        self._history: dict[str, deque[VoiceTurn]] = {}
        self._lock = Lock()

    def accept(
        self, session_id: str, key: UUID, fingerprint: str
    ) -> tuple[VoiceRecord, bool]:
        """Return (record, created). Replays with the same key do not create a request."""
        with self._lock:
            existing_id = self._keys.get((session_id, key))
            if existing_id is not None:
                existing = self._records[existing_id]
                if existing.fingerprint != fingerprint:
                    raise IdempotencyKeyReused()
                return existing, False
            if any(
                r.session_id == session_id and r.status in ACTIVE_STATUSES
                for r in self._records.values()
            ):
                raise RequestInProgress()
            record = VoiceRecord(
                request_id=f"vr_{uuid4().hex}", session_id=session_id,
                fingerprint=fingerprint, accepted_at=datetime.now(timezone.utc),
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
            record = self._records[request_id]
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
