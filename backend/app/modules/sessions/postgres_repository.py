"""Persistent kiosk sessions; the browser never connects to PostgreSQL."""

from uuid import uuid4

from app.infrastructure.database.postgres import PostgresDatabase
from app.modules.sessions.repository import SessionRepository
from app.modules.sessions.schemas import SessionCreateResponse


class PostgresSessionRepository(SessionRepository):
    def __init__(self, database: PostgresDatabase):
        self._database = database

    def create(self) -> SessionCreateResponse:
        session_id = uuid4().hex
        with self._database.connect() as connection:
            row = connection.execute(
                "insert into kiosk.sessions (session_id) values (%s) "
                "returning session_id, started_at", (session_id,),
            ).fetchone()
            connection.execute(
                "insert into kiosk.carts (session_id) values (%s)", (session_id,),
            )
        return SessionCreateResponse.model_validate(row)

    def exists(self, session_id: str) -> bool:
        with self._database.connect() as connection:
            return connection.execute(
                "select exists(select 1 from kiosk.sessions where session_id = %s) as found",
                (session_id,),
            ).fetchone()["found"]
