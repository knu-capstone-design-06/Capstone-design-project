import hashlib
import logging
from collections import Counter
from collections.abc import Callable, Iterable
from uuid import UUID

from app.modules.ordering.repository import OrderingRepository
from app.modules.voice.exceptions import VoiceRequestNotFound, VoiceSessionNotFound
from app.modules.voice.interpreter import VoiceInterpreter
from app.modules.voice.repository import VoiceRepository
from app.modules.voice.schemas import (
    AddCartItemCall, MenuItem, VoiceErrorResponse, VoiceInterpretation,
    VoiceRequestAccepted, VoiceRequestCreate, VoiceRequestStatus, VoiceTurn,
)

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "지금은 음성 주문이 어려워요. 화면을 눌러 주문해 주세요."
# Answers that accept a proposal but cannot pick an option such as a temperature.
BARE_YES = {"네", "넵", "예", "응", "어", "그래", "그래요", "좋아요", "맞아요"}


def is_bare_yes(text: str) -> bool:
    return "".join(ch for ch in text if ch.isalnum()) in BARE_YES


def menu_from_products(products: Iterable[object]) -> list[MenuItem]:
    """Keep only the product fields the interpreter needs (e.g. the ordering catalog)."""
    fields = MenuItem.model_fields.keys()
    return [
        MenuItem.model_validate({name: getattr(product, name) for name in fields})
        for product in products
    ]


def ask_for_missing_temperature(result: VoiceInterpretation, menu: list[MenuItem]) -> VoiceInterpretation:
    """Turn a drink without a temperature into a question instead of a failure.

    The model sometimes sends temperature null for products sold iced and hot even
    though the prompt says to ask. A single allowed temperature is filled in.
    """
    products = {item.product_id: item for item in menu}
    calls = []
    for call in result.tool_calls:
        item = products.get(call.arguments.product_id)
        if (item is None or call.arguments.temperature is not None or not item.temperatures
                or (isinstance(call, AddCartItemCall) and not item.available)):
            calls.append(call)  # left for matches_menu, which rejects unsold additions
            continue
        if len(item.temperatures) > 1:
            return VoiceInterpretation(
                status="needs_clarification", tool_calls=[],
                reply_text=f"{item.name}, 따뜻한 것과 아이스 중 무엇으로 할까요?",
            )
        calls.append(call.model_copy(update={
            "arguments": call.arguments.model_copy(update={"temperature": item.temperatures[0]}),
        }))
    return result.model_copy(update={"tool_calls": calls})


ASK_MENU_REPLY = "어떤 메뉴를 주문할까요?"
PENDING = {"needs_confirmation", "needs_clarification"}


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def require_named_products(
    result: VoiceInterpretation, request: VoiceRequestCreate, history: list[VoiceTurn],
    menu: list[MenuItem],
) -> VoiceInterpretation:
    """Send tool inputs only for products named in this conversation.

    A short answer such as "네" or "따뜻한 걸로요" must not become an order the
    model made up, nor swap in another product. A product is named when its full name
    or a word only its name has appears in what the customer said (this utterance,
    its recognition alternatives, earlier utterances such as the base of "하나 더")
    or in a question the kiosk asked about it ("카페 라떼는 아이스, 따뜻한 것 중
    무엇으로 할까요?"). A word several names share ("라떼") is not enough; the
    kiosk asks which one. A general "어떤 메뉴를 주문할까요?" names nothing.
    """
    if not result.tool_calls:
        return result
    said = [_compact(request.text), *(_compact(item.text) for item in request.alternatives)]
    for turn in history:
        said.append(_compact(turn.request.text))
        if turn.result.reply_text:
            said.append(_compact(turn.result.reply_text))
    words = {item.product_id: [w for w in map(_compact, item.name.split()) if len(w) >= 2] for item in menu}
    uses = Counter(word for item_words in words.values() for word in set(item_words))
    names = {item.product_id: item.name for item in menu}
    for call in result.tool_calls:
        product_id = call.arguments.product_id
        keys = [_compact(names.get(product_id, "")), *(w for w in words.get(product_id, []) if uses[w] == 1)]
        if any(key and key in text for key in keys for text in said):
            continue
        shared = [w for w in words.get(product_id, []) if uses[w] > 1 and any(w in text for text in said)]
        reply = f"{max(shared, key=len)} 중 어떤 메뉴로 할까요?" if shared else ASK_MENU_REPLY
        return VoiceInterpretation(status="needs_clarification", tool_calls=[], reply_text=reply)
    return result


def matches_menu(
    result: VoiceInterpretation, menu: list[MenuItem], allow_missing_temperature: bool = False,
) -> bool:
    """Reject tool inputs naming unknown products, unavailable additions or invalid temperatures.

    allow_missing_temperature lets a drink without a temperature through, to be asked later.
    """
    products = {item.product_id: item for item in menu}
    for call in result.tool_calls:
        item = products.get(call.arguments.product_id)
        if item is None:
            return False
        if isinstance(call, AddCartItemCall) and not item.available:
            return False
        temperature = call.arguments.temperature
        if temperature is None and item.temperatures and allow_missing_temperature:
            continue
        if (temperature is None) != (not item.temperatures):
            return False
        if temperature is not None and temperature not in item.temperatures:
            return False
    return True


class VoiceService:
    def __init__(
        self, session_exists: Callable[[str], bool], repository: VoiceRepository,
        interpreter: VoiceInterpreter, menu_provider: Callable[[], list[MenuItem]],
        ordering: OrderingRepository,
    ):
        self._session_exists = session_exists
        self._repository = repository
        self._interpreter = interpreter
        self._menu_provider = menu_provider
        self._ordering = ordering

    def accept(
        self, session_id: str, key: UUID, request: VoiceRequestCreate
    ) -> tuple[VoiceRequestAccepted, bool]:
        """Return (accepted, created). Only a newly created request is processed."""
        if not self._session_exists(session_id):
            raise VoiceSessionNotFound()
        fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        # Keep completion stable through insertion; existing keys replay first.
        with self._ordering.completion_guard(session_id) as completed:
            record, created = self._repository.accept(
                session_id, key, fingerprint,
                is_completed=lambda: completed,
            )
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
            if not menu:
                # Nothing can be ordered, so do not spend an OpenAI call on it.
                self._repository.update(
                    request_id, "failed", FALLBACK_REPLY,
                    error=VoiceErrorResponse(
                        code="ai_unavailable", detail="판매 메뉴가 연결되지 않아 음성 해석을 하지 않았습니다.",
                    ),
                )
                return
            history = self._repository.history(session_id)
            last = history[-1].result if history else None
            if last is not None and last.status == "needs_clarification" and is_bare_yes(request.text):
                # "네" cannot answer "아이스, 따뜻한 것 중 무엇으로?"; ask again instead of guessing.
                result = last
            elif (last is None or last.status not in PENDING) and is_bare_yes(request.text):
                # Nothing was proposed, so "네" must not repeat or invent an order.
                result = VoiceInterpretation(status="needs_clarification", tool_calls=[], reply_text=ASK_MENU_REPLY)
            else:
                result = await self._interpreter.interpret(request, menu, history)
            if result is not None and not matches_menu(result, menu, allow_missing_temperature=True):
                logger.warning("voice interpretation rejected (not on menu)")
                result = None
            if result is not None:
                # Check named products before asking about a temperature, so the kiosk
                # never asks about a drink the customer did not mention.
                result = require_named_products(result, request, history, menu)
                result = ask_for_missing_temperature(result, menu)
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
        if result.status != "ignored":
            # Speech not meant for the kiosk would only confuse later turns.
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
