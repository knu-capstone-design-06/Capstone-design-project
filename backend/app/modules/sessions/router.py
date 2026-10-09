from fastapi import APIRouter, Depends, HTTPException, Request

from app.infrastructure.external.ai_client import AiServerClient, get_ai_server_client
from app.modules.sessions.exceptions import SessionNotFound
from app.modules.sessions.schemas import (
    FeatureWindowRequest, FeatureWindowResponse, SessionCreateResponse,
)
from app.modules.sessions.service import SessionService

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def get_session_service(request: Request) -> SessionService:
    return request.app.state.session_service


@router.post("", response_model=SessionCreateResponse, status_code=201)
def create_session(service: SessionService = Depends(get_session_service)):
    return service.create()


@router.post("/{session_id}/features", response_model=FeatureWindowResponse,
             responses={404: {"description": "session not found"}})
async def features(
    session_id: str, window: FeatureWindowRequest,
    service: SessionService = Depends(get_session_service),
    ai: AiServerClient = Depends(get_ai_server_client),
):
    try:
        return await service.analyze(session_id, window, ai)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="session not found") from None
