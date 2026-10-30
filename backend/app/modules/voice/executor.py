"""Runs MCP-shaped cart tool inputs against the ordering service, all or nothing.

The voice module does not own the cart. main.py builds the executor with the ordering
service so the tool inputs reuse the same product, version and idempotency checks as
touch ordering (decision 2026-10-29: tool_calls run inside the backend, no MCP server).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, get_args

from app.modules.ordering.exceptions import OrderingError
from app.modules.ordering.repository import OrderingRepository
from app.modules.ordering.schemas import AddItemRequest, Cart, UpdateItemRequest
from app.modules.ordering.service import OrderingService
from app.modules.voice.schemas import (
    AddCartItemCall, RemoveCartItemCall, ToolCall, UpdateCartItemCall, VoiceErrorCode,
    VoiceErrorResponse,
)

KNOWN_CODES = set(get_args(VoiceErrorCode))

# Short enough for the kiosk; the error code carries the detail for the frontend.
EXECUTION_REPLIES = {
    "cart_item_not_found": "장바구니에 그 상품이 없어요. 화면을 확인해 주세요.",
    "quantity_limit_exceeded": "한 상품은 20개까지 담을 수 있어요.",
    "product_unavailable": "지금은 주문할 수 없는 상품이에요.",
    "cart_version_conflict": "장바구니가 바뀌었어요. 내용을 확인해 주세요.",
    "session_expired": "주문이 끝난 세션이에요. 새로 시작해 주세요.",
}
FALLBACK_EXECUTION_REPLY = "장바구니에 담지 못했어요. 화면을 눌러 주문해 주세요."


class ToolExecutionFailed(Exception):
    """One tool input was refused by the ordering service; nothing was changed."""

    def __init__(self, error: VoiceErrorResponse, reply_text: str):
        super().__init__(error.detail)
        self.error = error
        self.reply_text = reply_text


class CartExecutor(Protocol):
    def execute(self, session_id: str, request_id: str, calls: Sequence[ToolCall]) -> Cart: ...


@dataclass
class OrderingCartExecutor:
    """Applies tool inputs in the order spoken inside one ordering transaction."""

    service: OrderingService
    repository: OrderingRepository

    def execute(self, session_id: str, request_id: str, calls: Sequence[ToolCall]) -> Cart:
        try:
            with self.repository.transaction(session_id):
                cart = self.service.cart(session_id)
                for index, call in enumerate(calls):
                    # One key per tool input: a replayed voice request never runs twice.
                    cart = self._apply(session_id, f"voice:{request_id}:{index}", cart, call)
                return cart
        except OrderingError as error:
            code = error.code if error.code in KNOWN_CODES else "ai_unavailable"
            raise ToolExecutionFailed(
                VoiceErrorResponse(code=code, detail=error.detail),
                EXECUTION_REPLIES.get(code, FALLBACK_EXECUTION_REPLY),
            ) from error

    def _apply(self, session_id: str, key: str, cart: Cart, call: ToolCall) -> Cart:
        arguments = call.arguments
        if isinstance(call, AddCartItemCall):
            return self.service.add_item(session_id, key, AddItemRequest(
                expected_version=cart.version, product_id=arguments.product_id,
                temperature=arguments.temperature, quantity=arguments.quantity,
            ))
        item = next((item for item in cart.items if item.product_id == arguments.product_id
                     and item.temperature == arguments.temperature), None)
        if item is None:
            raise OrderingError(404, "cart_item_not_found", "장바구니 항목을 찾을 수 없습니다.")
        if isinstance(call, UpdateCartItemCall):
            return self.service.update_item(session_id, item.item_id, key, UpdateItemRequest(
                expected_version=cart.version, quantity=arguments.quantity,
            ))
        assert isinstance(call, RemoveCartItemCall)
        return self.service.delete_item(session_id, item.item_id, key, cart.version)
