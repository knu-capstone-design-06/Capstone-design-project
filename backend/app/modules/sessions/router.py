from fastapi import APIRouter, Depends, HTTPException, Request

from app.infrastructure.external.ai_client import AiEngineClient, get_ai_engine_client
from app.modules.sessions.exceptions import SessionCompleted, SessionNotFound
from app.modules.sessions.schemas import (
    FeatureWindowRequest, FeatureWindowResponse, SessionCreateResponse, VisionWindowAccepted, VisionWindowRequest,
)
from app.modules.sessions.service import SessionService

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def get_session_service(request: Request) -> SessionService:
    return request.app.state.session_service


@router.post("", response_model=SessionCreateResponse, status_code=201)
def create_session(service: SessionService = Depends(get_session_service)):
    return service.create()


@router.post("/{session_id}/features", response_model=FeatureWindowResponse,
             responses={404: {"description": "session not found"},
                        410: {"description": "session expired"}})
async def features(
    session_id: str, window: FeatureWindowRequest,
    service: SessionService = Depends(get_session_service),
    ai: AiEngineClient = Depends(get_ai_engine_client),
):
    try:
        return await service.analyze(session_id, window, ai)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="session not found") from None
    except SessionCompleted:
        raise HTTPException(status_code=410, detail="session_expired") from None


@router.post("/{session_id}/vision-windows", response_model=VisionWindowAccepted, status_code=202,
             responses={404: {"description": "session not found"},
                        410: {"description": "session expired"},
                        422: {"description": "invalid window, or a body session_id other than the path's"}})
async def vision_windows(
    session_id: str, window: VisionWindowRequest,
    service: SessionService = Depends(get_session_service),
):
    """The AI engine's window (situation tags, gaze, face) for this session; read by its /features windows whose pairing
    span holds its end (DecisionService.paired_vision)."""
    if window.session_id is not None and window.session_id != session_id:
        raise HTTPException(status_code=422, detail="session_id does not match the path")
    try:
        return await service.receive_vision(session_id, window)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="session not found") from None
    except SessionCompleted:
        raise HTTPException(status_code=410, detail="session_expired") from None
