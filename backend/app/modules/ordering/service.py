import json
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from app.modules.ordering.catalog import PRODUCTS
from app.modules.ordering.exceptions import OrderingError
from app.modules.ordering.repository import OrderingRepository, SessionState
from app.modules.ordering.schemas import (
    AddItemRequest, Cart, CartItem, Order, OrderRequest, Product, ProductList,
    UpdateItemRequest,
)


class OrderingService:
    def __init__(self, session_exists: Callable[[str], bool], repository: OrderingRepository):
        self._session_exists = session_exists
        self._repository = repository
        self._products = {product.product_id: product for product in PRODUCTS}

    def products(self) -> ProductList:
        return ProductList(products=[product.model_copy(deep=True) for product in PRODUCTS])

    def _state(self, session_id: str) -> SessionState:
        if not self._session_exists(session_id):
            raise OrderingError(404, "session_not_found", "세션을 찾을 수 없습니다.")
        return self._repository.state(session_id)

    def cart(self, session_id: str) -> Cart:
        with self._repository.lock:
            state = self._state(session_id)
            if state.completed:
                raise OrderingError(410, "session_expired", "새 이용 세션을 시작해 주세요.")
            return state.cart.model_copy(deep=True)

    @staticmethod
    def _fingerprint(method: str, path: str, payload: dict, query: str = "") -> str:
        return json.dumps([method, path, query, payload], sort_keys=True, separators=(",", ":"))

    def _prepare(self, session_id: str, key: str, fingerprint: str,
                 expected_version: int) -> tuple[SessionState, Cart | Order | None]:
        state = self._state(session_id)
        replay = self._repository.replay(session_id, key)
        if replay is not None:
            if replay.fingerprint != fingerprint:
                raise OrderingError(409, "idempotency_key_reused",
                                    "같은 중복 방지 키에 다른 요청을 사용할 수 없습니다.")
            return state, replay.response.model_copy(deep=True)
        if state.completed:
            raise OrderingError(410, "session_expired", "새 이용 세션을 시작해 주세요.")
        if state.cart.version != expected_version:
            raise OrderingError(409, "cart_version_conflict",
                                "장바구니가 변경되었습니다. 최신 내용을 확인해 주세요.",
                                state.cart)
        return state, None

    @staticmethod
    def _snapshot(cart: Cart, items: list[CartItem]) -> Cart:
        return Cart(
            session_id=cart.session_id, version=cart.version + 1,
            items=items, total_quantity=sum(item.quantity for item in items),
            total_amount=sum(item.line_amount for item in items),
            updated_at=datetime.now(timezone.utc),
        )

    def _product(self, product_id: str) -> Product:
        product = self._products.get(product_id)
        if product is None:
            raise OrderingError(404, "product_not_found", "상품을 찾을 수 없습니다.")
        if not product.available:
            raise OrderingError(409, "product_unavailable", "현재 주문할 수 없는 상품입니다.")
        return product

    def add_item(self, session_id: str, key: str, request: AddItemRequest,
                 query: str = "") -> Cart:
        fingerprint = self._fingerprint("POST", "cart/items", request.model_dump(), query)
        with self._repository.lock:
            state, replay = self._prepare(session_id, key, fingerprint, request.expected_version)
            if replay is not None:
                return replay
            product = self._product(request.product_id)
            if request.temperature not in product.temperatures and not (
                request.temperature is None and not product.temperatures
            ):
                raise OrderingError(422, "invalid_option", "이 상품에서 선택할 수 없는 온도입니다.")
            items = [item.model_copy(deep=True) for item in state.cart.items]
            existing = next((item for item in items if item.product_id == product.product_id
                             and item.temperature == request.temperature), None)
            quantity = request.quantity + (existing.quantity if existing else 0)
            if quantity > 20:
                raise OrderingError(409, "quantity_limit_exceeded",
                                    "장바구니 항목의 수량 한도를 초과했습니다.", state.cart)
            if existing is None:
                items.append(CartItem(
                    item_id=uuid4().hex, product_id=product.product_id, name=product.name,
                    temperature=request.temperature, quantity=quantity,
                    unit_price=product.unit_price, line_amount=product.unit_price * quantity,
                ))
            else:
                existing.quantity = quantity
                existing.unit_price = product.unit_price
                existing.line_amount = product.unit_price * quantity
            cart = self._snapshot(state.cart, items)
            state.cart = cart
            self._repository.save(session_id, key, fingerprint, cart)
            return cart.model_copy(deep=True)

    def update_item(self, session_id: str, item_id: str, key: str,
                    request: UpdateItemRequest, query: str = "") -> Cart:
        fingerprint = self._fingerprint("PATCH", f"cart/items/{item_id}",
                                        request.model_dump(), query)
        with self._repository.lock:
            state, replay = self._prepare(session_id, key, fingerprint, request.expected_version)
            if replay is not None:
                return replay
            items = [item.model_copy(deep=True) for item in state.cart.items]
            item = next((item for item in items if item.item_id == item_id), None)
            if item is None:
                raise OrderingError(404, "cart_item_not_found", "장바구니 항목을 찾을 수 없습니다.")
            product = self._product(item.product_id)
            item.quantity = request.quantity
            item.unit_price = product.unit_price
            item.line_amount = item.unit_price * item.quantity
            cart = self._snapshot(state.cart, items)
            state.cart = cart
            self._repository.save(session_id, key, fingerprint, cart)
            return cart.model_copy(deep=True)

    def delete_item(self, session_id: str, item_id: str, key: str,
                    expected_version: int, query: str = "") -> Cart:
        fingerprint = self._fingerprint("DELETE", f"cart/items/{item_id}",
                                        {"expected_version": expected_version}, query)
        with self._repository.lock:
            state, replay = self._prepare(session_id, key, fingerprint, expected_version)
            if replay is not None:
                return replay
            if not any(item.item_id == item_id for item in state.cart.items):
                raise OrderingError(404, "cart_item_not_found", "장바구니 항목을 찾을 수 없습니다.")
            items = [item.model_copy(deep=True) for item in state.cart.items if item.item_id != item_id]
            cart = self._snapshot(state.cart, items)
            state.cart = cart
            self._repository.save(session_id, key, fingerprint, cart)
            return cart.model_copy(deep=True)

    def create_order(self, session_id: str, key: str, request: OrderRequest,
                     query: str = "") -> Order:
        fingerprint = self._fingerprint("POST", "orders", request.model_dump(), query)
        with self._repository.lock:
            state, replay = self._prepare(session_id, key, fingerprint, request.expected_version)
            if replay is not None:
                return replay
            cart = state.cart
            if not cart.items:
                raise OrderingError(409, "empty_cart", "빈 장바구니로 주문할 수 없습니다.", cart)
            for item in cart.items:
                product = self._product(item.product_id)
                if item.temperature not in product.temperatures and not (
                    item.temperature is None and not product.temperatures
                ):
                    raise OrderingError(422, "invalid_option", "이 상품에서 선택할 수 없는 온도입니다.")
            order = Order(
                order_id=uuid4().hex, order_number=f"SIM-{uuid4().hex.upper()}",
                session_id=session_id, items=[item.model_copy(deep=True) for item in cart.items],
                total_quantity=cart.total_quantity, total_amount=cart.total_amount,
                created_at=datetime.now(timezone.utc),
            )
            state.cart = self._snapshot(cart, [])
            state.completed = True
            self._repository.save(session_id, key, fingerprint, order)
            return order.model_copy(deep=True)
