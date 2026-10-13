from app.modules.ordering.schemas import Cart


class OrderingError(Exception):
    def __init__(self, status_code: int, code: str, detail: str, cart: Cart | None = None):
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.cart = cart.model_copy(deep=True) if cart is not None else None
