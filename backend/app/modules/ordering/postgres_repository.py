"""Transactional Cart, order and idempotency storage in the private kiosk schema."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock, local

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.infrastructure.database.postgres import PostgresDatabase
from app.modules.ordering.catalog import PRODUCTS
from app.modules.ordering.repository import OrderingRepository, Replay, SessionState
from app.modules.ordering.schemas import Cart, CartItem, Order, Product


@dataclass
class _Unit:
    session_id: str
    connection: Connection
    state: SessionState
    replays: dict[str, Replay] = field(default_factory=dict)


class PostgresOrderingRepository(OrderingRepository):
    """Lock one session while one touch or multi-tool voice mutation runs.

    A request uses one DB transaction. Nested voice tool calls share that
    transaction, so a later failed tool leaves neither Cart changes nor replay
    records behind. A transaction-scoped advisory lock serializes processes
    without granting UPDATE on the session table to the backend role.
    """

    def __init__(self, database: PostgresDatabase):
        self._database = database
        self.lock = RLock()
        self._local = local()

    def _unit(self) -> _Unit | None:
        return getattr(self._local, "unit", None)

    @staticmethod
    def _load_state(connection: Connection, session_id: str) -> SessionState:
        cart_row = connection.execute(
            "select version, updated_at from kiosk.carts where session_id = %s",
            (session_id,),
        ).fetchone()
        item_rows = connection.execute(
            "select item_id, product_id, name, temperature, quantity, unit_price, "
            "line_amount from kiosk.cart_items where session_id = %s order by position",
            (session_id,),
        ).fetchall()
        items = [CartItem.model_validate(row) for row in item_rows]
        completed = connection.execute(
            "select exists(select 1 from kiosk.orders where session_id = %s) as completed",
            (session_id,),
        ).fetchone()["completed"]
        cart = Cart(
            session_id=session_id,
            version=cart_row["version"] if cart_row else 0,
            items=items,
            total_quantity=sum(item.quantity for item in items),
            total_amount=sum(item.line_amount for item in items),
            updated_at=cart_row["updated_at"] if cart_row else datetime.now(timezone.utc),
        )
        return SessionState(cart=cart, completed=completed)

    def state(self, session_id: str) -> SessionState:
        unit = self._unit()
        if unit is not None:
            if unit.session_id != session_id:
                raise RuntimeError("Nested ordering operations must use the same session")
            return unit.state
        # A GET must not combine a cart version from before another process's
        # commit with item rows from after it. Use the same session lock as writes.
        with self.transaction(session_id):
            unit = self._unit()
            assert unit is not None
            return unit.state

    def is_completed(self, session_id: str) -> bool:
        unit = self._unit()
        if unit is not None and unit.session_id == session_id:
            return unit.state.completed
        with self._database.connect() as connection:
            return connection.execute(
                "select exists(select 1 from kiosk.orders where session_id = %s) as completed",
                (session_id,),
            ).fetchone()["completed"]

    @contextmanager
    def completion_guard(self, session_id: str) -> Iterator[bool]:
        with self.transaction(session_id):
            yield self.state(session_id).completed

    @contextmanager
    def transaction(self, session_id: str) -> Iterator[None]:
        with self.lock:
            current = self._unit()
            if current is not None:
                if current.session_id != session_id:
                    raise RuntimeError("Nested ordering operations must use the same session")
                yield
                return
            with self._database.connect() as connection:
                connection.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (session_id,),
                )
                self._local.unit = _Unit(
                    session_id, connection, self._load_state(connection, session_id),
                )
                try:
                    yield
                    unit = self._unit()
                    if unit is not None and unit.replays:
                        self._write(unit)
                finally:
                    del self._local.unit

    @staticmethod
    def _read_replay(connection: Connection, session_id: str, key: str) -> Replay | None:
        row = connection.execute(
            "select fingerprint, response_kind, response_body "
            "from kiosk.order_request_replays where session_id = %s and request_key = %s",
            (session_id, key),
        ).fetchone()
        if row is None:
            return None
        model = Cart if row["response_kind"] == "cart" else Order
        return Replay(row["fingerprint"], model.model_validate(row["response_body"]))

    def replay(self, session_id: str, key: str) -> Replay | None:
        unit = self._unit()
        if unit is not None and unit.session_id == session_id:
            return unit.replays.get(key) or self._read_replay(unit.connection, session_id, key)
        with self._database.connect() as connection:
            return self._read_replay(connection, session_id, key)

    def save(self, session_id: str, key: str, fingerprint: str, response: Cart | Order):
        unit = self._unit()
        if unit is None or unit.session_id != session_id:
            raise RuntimeError("Order changes require a repository transaction")
        unit.replays[key] = Replay(fingerprint, response.model_copy(deep=True))

    @staticmethod
    def _write(unit: _Unit) -> None:
        connection, cart, session_id = unit.connection, unit.state.cart, unit.session_id
        connection.execute(
            "insert into kiosk.carts (session_id, version, updated_at) values (%s, %s, %s) "
            "on conflict (session_id) do update set version = excluded.version, "
            "updated_at = excluded.updated_at",
            (session_id, cart.version, cart.updated_at),
        )
        connection.execute("delete from kiosk.cart_items where session_id = %s", (session_id,))
        for position, item in enumerate(cart.items):
            connection.execute(
                "insert into kiosk.cart_items "
                "(item_id, session_id, position, product_id, name, temperature, quantity, unit_price) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (item.item_id, session_id, position, item.product_id, item.name,
                 item.temperature, item.quantity, item.unit_price),
            )
        for replay in unit.replays.values():
            if not isinstance(replay.response, Order):
                continue
            order = replay.response
            connection.execute(
                "insert into kiosk.orders "
                "(order_id, order_number, session_id, status, currency, total_quantity, total_amount, created_at) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (order.order_id, order.order_number, session_id, order.status, order.currency,
                 order.total_quantity, order.total_amount, order.created_at),
            )
            for position, item in enumerate(order.items):
                connection.execute(
                    "insert into kiosk.order_items "
                    "(order_id, item_id, position, product_id, name, temperature, quantity, unit_price) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (order.order_id, item.item_id, position, item.product_id, item.name,
                     item.temperature, item.quantity, item.unit_price),
                )
        for key, replay in unit.replays.items():
            connection.execute(
                "insert into kiosk.order_request_replays "
                "(session_id, request_key, fingerprint, response_kind, response_body) "
                "values (%s, %s, %s, %s, %s)",
                (session_id, key, replay.fingerprint,
                 "order" if isinstance(replay.response, Order) else "cart",
                 Jsonb(replay.response.model_dump(mode="json"))),
            )

    def products(self) -> list[Product]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "select product_id, name, category, description, unit_price, available, "
                "temperatures from kiosk.products",
            ).fetchall()
        rank = {product.product_id: index for index, product in enumerate(PRODUCTS)}
        return [Product.model_validate(row) for row in sorted(
            rows, key=lambda row: (rank.get(row["product_id"], len(rank)), row["product_id"]),
        )]

    def product(self, product_id: str) -> Product | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "select product_id, name, category, description, unit_price, available, "
                "temperatures from kiosk.products where product_id = %s", (product_id,),
            ).fetchone()
        return Product.model_validate(row) if row is not None else None
