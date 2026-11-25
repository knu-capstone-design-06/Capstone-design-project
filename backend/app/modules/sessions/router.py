from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.infrastructure.external.ai_client import AiEngineClient, get_ai_engine_client
from app.modules.sessions.exceptions import SessionCompleted, SessionNotFound
from app.modules.sessions.schemas import (
    FeatureValidationError, FeatureWindowRequest, FeatureWindowResponse, SessionCreateResponse,
)
from app.modules.sessions.service import SessionService

class SessionRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                # Return field locations without echoing submitted values, including nonfinite numbers.
                detail = [
                    {key: issue[key] for key in ("loc", "msg", "type")} for issue in exc.errors()
                ]
                return JSONResponse(status_code=422, content={"detail": detail})

        return handle


router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"], route_class=SessionRoute)


def get_session_service(request: Request) -> SessionService:
    return request.app.state.session_service


@router.post("", response_model=SessionCreateResponse, status_code=201)
def create_session(service: SessionService = Depends(get_session_service)):
    return service.create()


@router.post("/{session_id}/features", response_model=FeatureWindowResponse,
             responses={404: {"description": "session not found"},
                        410: {"description": "session expired"},
                        422: {"model": FeatureValidationError}})
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
