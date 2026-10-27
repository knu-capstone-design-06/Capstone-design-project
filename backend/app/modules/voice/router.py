from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.modules.voice.exceptions import VoiceError
from app.modules.voice.schemas import (
    VoiceErrorResponse, VoiceRequestAccepted, VoiceRequestCreate, VoiceRequestStatus,
)
from app.modules.voice.service import VoiceService


def _error(status_code: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "detail": detail})


class VoiceRoute(APIRoute):
    """Returns the voice contract's {code, detail} errors for this router only."""

    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError:
                return _error(422, "invalid_request", "요청 형식이 올바르지 않습니다.")
            except VoiceError as exc:
                return _error(exc.status_code, exc.code, exc.detail)

        return route_handler


router = APIRouter(prefix="/api/v1/sessions", tags=["voice"], route_class=VoiceRoute)
ERRORS = {status: {"model": VoiceErrorResponse} for status in (404, 409, 410, 422)}


def get_voice_service(request: Request) -> VoiceService:
    return request.app.state.voice_service


@router.post("/{session_id}/voice/requests", response_model=VoiceRequestAccepted,
             status_code=202, responses=ERRORS)
def create_voice_request(
    session_id: str, body: VoiceRequestCreate, background: BackgroundTasks,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    service: VoiceService = Depends(get_voice_service),
):
    accepted, created = service.accept(session_id, idempotency_key, body)
    if created:
        background.add_task(service.process, session_id, accepted.request_id, body)
    return accepted


@router.get("/{session_id}/voice/requests/{request_id}", response_model=VoiceRequestStatus,
            responses={404: {"model": VoiceErrorResponse}})
def get_voice_request(
    session_id: str, request_id: str, service: VoiceService = Depends(get_voice_service),
):
    return service.get(session_id, request_id)
