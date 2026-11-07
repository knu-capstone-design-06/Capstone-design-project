import logging

from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.infrastructure.external.ai_client import AiEngineClient
from app.infrastructure.external.ai_schemas import AnalyzeRequest
from app.modules.decision.service import DecisionService
from app.modules.ordering.repository import OrderingRepository
from app.modules.sessions.exceptions import SessionCompleted, SessionNotFound
from app.modules.sessions.repository import SessionRepository
from app.modules.sessions.schemas import (
    FeatureWindowRequest, FeatureWindowResponse, SessionCreateResponse, StateScores,
)


logger = logging.getLogger(__name__)


class SessionService:
    def __init__(self, repository: SessionRepository, ordering: OrderingRepository,
                 decision: DecisionService | None = None):
        self._repository = repository
        self._ordering = ordering
        # Shadow judgment layer: runs beside the response and never changes it (docs/Jev-Integration.md).
        self._decision = decision

    def exists(self, session_id: str) -> bool:
        return self._repository.exists(session_id)

    def create(self) -> SessionCreateResponse:
        return self._repository.create()

    async def analyze(
        self, session_id: str, window: FeatureWindowRequest, ai: AiEngineClient
    ) -> FeatureWindowResponse:
        if not await run_in_threadpool(self._repository.exists, session_id):
            raise SessionNotFound()
        if await run_in_threadpool(self._ordering.is_completed, session_id):
            raise SessionCompleted()
        request = AnalyzeRequest(
            session_id=session_id, **window.model_dump(exclude_unset=True)
        )
        result = await ai.analyze(request)
        # An order may complete while the AI request is in flight.
        if await run_in_threadpool(self._ordering.is_completed, session_id):
            raise SessionCompleted()
        if self._decision is not None:
            try:
                self._decision.observe(session_id, window, measurable=result is not None and result.measurable)
            except Exception:
                # The judgment layer is in shadow mode: a failure there must not touch the response.
                logger.exception("decision layer failed; response unchanged")
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
