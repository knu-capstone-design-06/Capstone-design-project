from pydantic import ValidationError

from app.infrastructure.external.ai_client import AiServerClient
from app.infrastructure.external.ai_schemas import AnalyzeRequest
from app.modules.sessions.exceptions import SessionNotFound
from app.modules.sessions.repository import SessionRepository
from app.modules.sessions.schemas import (
    FeatureWindowRequest, FeatureWindowResponse, SessionCreateResponse, StateScores,
)


class SessionService:
    def __init__(self, repository: SessionRepository):
        self._repository = repository

    def create(self) -> SessionCreateResponse:
        return self._repository.create()

    async def analyze(
        self, session_id: str, window: FeatureWindowRequest, ai: AiServerClient
    ) -> FeatureWindowResponse:
        if not self._repository.exists(session_id):
            raise SessionNotFound()
        request = AnalyzeRequest(
            session_id=session_id, **window.model_dump(exclude_unset=True)
        )
        result = await ai.analyze(request)
        fallback = FeatureWindowResponse(session_id=session_id, ai_available=False)
        if result is None:
            return fallback
        try:
            states = StateScores.model_validate(result.states) if result.measurable else None
        except ValidationError:
            # Never reflect malformed or out-of-range scores into the UI.
            return fallback
        return FeatureWindowResponse(
            session_id=session_id, ai_available=True,
            states=states, model_version=result.model_version,
        )
