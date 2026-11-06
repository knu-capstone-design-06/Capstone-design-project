"""Ordering invariants against an isolated, disposable PostgreSQL database.

Set TEST_DATABASE_URL only for a local test database prepared with the three
repository migrations and the demo catalog seed. Production Supabase is never
a test target.
"""

from concurrent.futures import ThreadPoolExecutor
import os
import unittest
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from app.infrastructure.database.postgres import PostgresDatabase
from app.modules.ordering.exceptions import OrderingError
from app.modules.ordering.postgres_repository import PostgresOrderingRepository
from app.modules.ordering.schemas import AddItemRequest, OrderRequest
from app.modules.ordering.service import OrderingService
from app.modules.sessions.postgres_repository import PostgresSessionRepository
from app.modules.voice.executor import OrderingCartExecutor, ToolExecutionFailed
from app.modules.voice.schemas import VoiceInterpretation


class LocalTestDatabase(PostgresDatabase):
    """The ephemeral CI service has no TLS; production PostgresDatabase requires it."""

    def connect(self):
        return psycopg.connect(
            self._url, row_factory=dict_row, connect_timeout=5,
            sslmode="disable", prepare_threshold=None,
        )


class PostgresOrderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ.get("TEST_DATABASE_URL")
        if not url:
            raise unittest.SkipTest("TEST_DATABASE_URL is not set")
        if urlsplit(url).hostname not in {"localhost", "127.0.0.1"}:
            raise RuntimeError("PostgreSQL integration tests require a local disposable DB")
        cls.database = LocalTestDatabase(url)
        cls.database.check()

    def setUp(self):
        self.sessions = PostgresSessionRepository(self.database)
        self.session_id = self.sessions.create().session_id
        self.repository = PostgresOrderingRepository(self.database)
        self.service = OrderingService(self.sessions.exists, self.repository)

    def _add(self, service=None, *, key=None):
        return (service or self.service).add_item(
            self.session_id, key or str(uuid4()),
            AddItemRequest(product_id="americano", temperature="iced",
                           quantity=1, expected_version=0),
        )

    def test_restart_reuses_cart_and_order_success_responses(self):
        add_key = str(uuid4())
        first_cart = self._add(key=add_key)
        restarted_repo = PostgresOrderingRepository(self.database)
        restarted = OrderingService(self.sessions.exists, restarted_repo)
        self.assertEqual(restarted.cart(self.session_id), first_cart)
        self.assertEqual(self._add(restarted, key=add_key), first_cart)

        order_key = str(uuid4())
        request = OrderRequest(expected_version=1)
        first_order = restarted.create_order(self.session_id, order_key, request)
        restarted_again = OrderingService(
            self.sessions.exists, PostgresOrderingRepository(self.database),
        )
        self.assertEqual(
            restarted_again.create_order(self.session_id, order_key, request), first_order,
        )
        with self.assertRaises(OrderingError) as raised:
            restarted_again.cart(self.session_id)
        self.assertEqual(raised.exception.code, "session_expired")

    def test_two_repository_instances_create_only_one_order(self):
        self._add()

        def place_order(_):
            service = OrderingService(
                self.sessions.exists, PostgresOrderingRepository(self.database),
            )
            try:
                service.create_order(
                    self.session_id, str(uuid4()), OrderRequest(expected_version=1),
                )
                return "created"
            except OrderingError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(place_order, range(2)))
        self.assertCountEqual(outcomes, ["created", "session_expired"])
        with self.database.connect() as connection:
            count = connection.execute(
                "select count(*) as count from kiosk.orders where session_id = %s",
                (self.session_id,),
            ).fetchone()["count"]
        self.assertEqual(count, 1)

    def test_failed_voice_tool_bundle_rolls_back_cart_and_replay(self):
        calls = VoiceInterpretation.model_validate({
            "status": "completed", "reply_text": None,
            "tool_calls": [
                {"tool": "add_cart_item", "arguments": {
                    "product_id": "americano", "temperature": "iced", "quantity": 1,
                }},
                {"tool": "remove_cart_item", "arguments": {
                    "product_id": "sandwich", "temperature": None,
                }},
            ],
        }).tool_calls
        executor = OrderingCartExecutor(self.service, self.repository)
        with self.assertRaises(ToolExecutionFailed):
            executor.execute(self.session_id, "vr_rollback", calls)
        self.assertEqual(self.service.cart(self.session_id).version, 0)
        self.assertEqual(self.service.cart(self.session_id).items, [])
        with self.database.connect() as connection:
            replay_count = connection.execute(
                "select count(*) as count from kiosk.order_request_replays "
                "where session_id = %s and request_key like %s",
                (self.session_id, "voice:vr_rollback:%"),
            ).fetchone()["count"]
        self.assertEqual(replay_count, 0)


if __name__ == "__main__":
    unittest.main()
