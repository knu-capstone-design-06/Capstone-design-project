"""Atomic process-local ordering state; replaced by DB storage in a later PR."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock

from app.modules.ordering.schemas import Cart, Order


@dataclass
class Replay:
    fingerprint: str
    response: Cart | Order


@dataclass
class SessionState:
    cart: Cart
    completed: bool = False


class OrderingRepository:
    def __init__(self):
        self.lock = RLock()
        self.states: dict[str, SessionState] = {}
        self.replays: dict[tuple[str, str], Replay] = {}

    def state(self, session_id: str) -> SessionState:
        if session_id not in self.states:
            self.states[session_id] = SessionState(Cart(
                session_id=session_id, version=0, items=[], total_quantity=0,
                total_amount=0, updated_at=datetime.now(timezone.utc),
            ))
        return self.states[session_id]

    def is_completed(self, session_id: str) -> bool:
        with self.lock:
            state = self.states.get(session_id)
            return state.completed if state is not None else False

    @contextmanager
    def completion_guard(self, session_id: str) -> Iterator[bool]:
        """Keep completion state stable while a related request is accepted."""
        with self.lock:
            state = self.states.get(session_id)
            yield state.completed if state is not None else False

    @contextmanager
    def transaction(self, session_id: str) -> Iterator[None]:
        """Apply several cart changes as one; an exception restores the cart and replays.

        Holds the lock for the whole block. Used by voice tool execution, where a
        request with several tool inputs must change the cart entirely or not at all.
        """
        with self.lock:
            state = self.state(session_id)
            cart = state.cart.model_copy(deep=True)
            keys = set(self.replays)
            try:
                yield
            except BaseException:
                state.cart = cart
                for key in set(self.replays) - keys:
                    del self.replays[key]
                raise

    def replay(self, session_id: str, key: str) -> Replay | None:
        return self.replays.get((session_id, key))

    def save(self, session_id: str, key: str, fingerprint: str, response: Cart | Order):
        self.replays[(session_id, key)] = Replay(fingerprint, response.model_copy(deep=True))
