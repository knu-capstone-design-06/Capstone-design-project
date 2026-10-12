import hashlib
import logging
from collections.abc import Callable
from uuid import UUID

from app.modules.voice.exceptions import VoiceRequestNotFound, VoiceSessionNotFound
from app.modules.voice.interpreter import VoiceInterpreter
from app.modules.voice.repository import VoiceRepository
from app.modules.voice.schemas import (
    AddCartItemCall, MenuItem, VoiceErrorResponse, VoiceInterpretation,
    VoiceRequestAccepted, VoiceRequestCreate, VoiceRequestStatus, VoiceTurn,
)

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "지금은 음성 주문이 어려워요. 화면을 눌러 주문해 주세요."


def empty_menu() -> list[MenuItem]:
    """Placeholder until the backend product API exists."""
    return []


def matches_menu(result: VoiceInterpretation, menu: list[MenuItem]) -> bool:
    """Reject tool inputs naming unknown products, unavailable additions or invalid temperatures."""
    products = {item.product_id: item for item in menu}
    for call in result.tool_calls:
        item = products.get(call.arguments.product_id)
        if item is None:
            return False
        if isinstance(call, AddCartItemCall) and not item.available:
            return False
        temperature = call.arguments.temperature
        if (temperature is None) != (not item.temperatures):
            return False
        if temperature is not None and temperature not in item.temperatures:
            return False
    return True


class VoiceService:
    def __init__(
        self, session_exists: Callable[[str], bool], repository: VoiceRepository,
        interpreter: VoiceInterpreter, menu_provider: Callable[[], list[MenuItem]],
    ):
        self._session_exists = session_exists
        self._repository = repository
        self._interpreter = interpreter
        self._menu_provider = menu_provider

    def accept(
        self, session_id: str, key: UUID, request: VoiceRequestCreate
    ) -> tuple[VoiceRequestAccepted, bool]:
        """Return (accepted, created). Only a newly created request is processed."""
        if not self._session_exists(session_id):
            raise VoiceSessionNotFound()
        fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        record, created = self._repository.accept(session_id, key, fingerprint)
        accepted = VoiceRequestAccepted(
            request_id=record.request_id, accepted_at=record.accepted_at
        )
        return accepted, created

    async def process(
        self, session_id: str, request_id: str, request: VoiceRequestCreate
    ) -> None:
        self._repository.update(request_id, "processing")
        try:
            menu = self._menu_provider()
            history = self._repository.history(session_id)
            result = await self._interpreter.interpret(request, menu, history)
            if result is not None and not matches_menu(result, menu):
                logger.warning("voice interpretation rejected (not on menu)")
                result = None
        except Exception:
            # A voice failure must not affect touch ordering; record it as unavailable.
            logger.exception("voice interpretation crashed")
            result = None
        if result is None:
            # Failed exchanges stay out of the context so later turns read cleanly.
            self._repository.update(
                request_id, "failed", FALLBACK_REPLY,
                error=VoiceErrorResponse(code="ai_unavailable", detail="외부 AI를 사용할 수 없습니다."),
            )
            return
        self._repository.append_turn(session_id, VoiceTurn(request=request, result=result))
        # tool_calls are MCP inputs (a proposal when needs_confirmation); nothing has
        # been changed here, so actions stay empty.
        self._repository.update(request_id, result.status, result.reply_text, result.tool_calls)

    def get(self, session_id: str, request_id: str) -> VoiceRequestStatus:
        if not self._session_exists(session_id):
            raise VoiceSessionNotFound()
        status = self._repository.get(session_id, request_id)
        if status is None:
            raise VoiceRequestNotFound()
        return status
