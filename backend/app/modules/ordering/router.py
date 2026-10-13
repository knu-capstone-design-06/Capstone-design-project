from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.modules.ordering.exceptions import OrderingError
from app.modules.ordering.schemas import (
    AddItemRequest, Cart, Order, OrderApiError, OrderRequest, ProductList,
    UpdateItemRequest,
)
from app.modules.ordering.service import OrderingService


class OrderRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request):
            try:
                return await handler(request)
            except OrderingError as exc:
                body = OrderApiError(code=exc.code, detail=exc.detail, cart=exc.cart)
                return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(body))
            except RequestValidationError:
                body = OrderApiError(code="invalid_request", detail="요청 형식이 올바르지 않습니다.")
                return JSONResponse(status_code=422, content=jsonable_encoder(body))

        return handle


router = APIRouter(prefix="/api/v1", route_class=OrderRoute)
Key = Annotated[UUID, Header(alias="Idempotency-Key")]


def get_ordering_service(request: Request) -> OrderingService:
    return OrderingService(
        request.app.state.session_service.exists,
        request.app.state.ordering_repository,
    )


@router.get("/products", response_model=ProductList, tags=["products"])
def products(service: OrderingService = Depends(get_ordering_service)):
    return service.products()


@router.get("/sessions/{session_id}/cart", response_model=Cart, tags=["cart"])
def get_cart(session_id: str, service: OrderingService = Depends(get_ordering_service)):
    return service.cart(session_id)


@router.post("/sessions/{session_id}/cart/items", response_model=Cart, tags=["cart"])
def add_item(session_id: str, request: AddItemRequest, key: Key, http_request: Request,
             service: OrderingService = Depends(get_ordering_service)):
    return service.add_item(session_id, str(key), request, http_request.url.query)


@router.patch("/sessions/{session_id}/cart/items/{item_id}", response_model=Cart, tags=["cart"])
def update_item(session_id: str, item_id: str, request: UpdateItemRequest, key: Key,
                http_request: Request,
                service: OrderingService = Depends(get_ordering_service)):
    return service.update_item(session_id, item_id, str(key), request, http_request.url.query)


@router.delete("/sessions/{session_id}/cart/items/{item_id}", response_model=Cart, tags=["cart"])
def delete_item(session_id: str, item_id: str, key: Key, http_request: Request,
                expected_version: Annotated[int, Query(ge=0)],
                service: OrderingService = Depends(get_ordering_service)):
    return service.delete_item(session_id, item_id, str(key), expected_version,
                               http_request.url.query)


@router.post("/sessions/{session_id}/orders", response_model=Order,
             status_code=201, tags=["orders"])
def create_order(session_id: str, request: OrderRequest, key: Key, http_request: Request,
                 service: OrderingService = Depends(get_ordering_service)):
    return service.create_order(session_id, str(key), request, http_request.url.query)
