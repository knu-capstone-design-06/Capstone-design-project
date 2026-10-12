from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from app.modules.sessions.schemas import SessionCreateResponse


class SessionRepository:
    """Process-local connection-test storage, reset on application restart."""

    def __init__(self):
        self._sessions: dict[str, SessionCreateResponse] = {}
        self._lock = Lock()

    def create(self) -> SessionCreateResponse:
        session = SessionCreateResponse(
            session_id=uuid4().hex, started_at=datetime.now(timezone.utc)
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session.model_copy()

    def exists(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._sessions
