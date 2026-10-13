from concurrent.futures import ThreadPoolExecutor
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.common.config.settings import Settings
from app.main import create_app
from app.modules.ordering.exceptions import OrderingError
from app.modules.ordering.repository import OrderingRepository
from app.modules.ordering.schemas import AddItemRequest
from app.modules.ordering.service import OrderingService
from app.modules.sessions.repository import SessionRepository


class OrderingApiTests(unittest.TestCase):
    def setUp(self):
        self.client = self.enterContext(TestClient(create_app(Settings(_env_file=None))))
        response = self.client.post("/api/v1/sessions")
        self.assertEqual(response.status_code, 201)
        self.session = response.json()["session_id"]
        self.base = f"/api/v1/sessions/{self.session}"

    @staticmethod
    def headers(key=None):
        return {"Idempotency-Key": key or str(uuid4())}

    def add(self, *, quantity=1, version=0, temperature="iced", key=None, product="americano"):
        return self.client.post(f"{self.base}/cart/items", headers=self.headers(key), json={
            "product_id": product, "temperature": temperature,
            "quantity": quantity, "expected_version": version,
        })

    def test_catalog_and_initial_cart(self):
        products = self.client.get("/api/v1/products")
        self.assertEqual(products.status_code, 200)
        data = products.json()
        self.assertEqual(data["currency"], "KRW")
        self.assertEqual(len(data["products"]), 17)
        self.assertEqual(data["products"][0]["product_id"], "americano")
        cart = self.client.get(f"{self.base}/cart")
        self.assertEqual(cart.status_code, 200)
        self.assertEqual(cart.json()["version"], 0)
        self.assertEqual(cart.json()["items"], [])

    def test_cross_origin_mutation_preflight(self):
        response = self.client.options(
            f"{self.base}/cart/items/item-1",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "content-type,idempotency-key",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("PATCH", response.headers["access-control-allow-methods"])
        self.assertIn("idempotency-key",
                      response.headers["access-control-allow-headers"].lower())

    def test_add_update_delete_and_version_conflict(self):
        key = str(uuid4())
        first = self.add(quantity=2, key=key)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["total_amount"], 7000)
        self.assertEqual(first.json(), self.add(quantity=2, key=key).json())
        reused = self.add(quantity=3, key=key)
        self.assertEqual((reused.status_code, reused.json()["code"]),
                         (409, "idempotency_key_reused"))
        different_query = self.client.post(
            f"{self.base}/cart/items?source=other", headers=self.headers(key),
            json={"product_id": "americano", "temperature": "iced",
                  "quantity": 2, "expected_version": 0},
        )
        self.assertEqual(different_query.json()["code"], "idempotency_key_reused")
        stale = self.add(version=0)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "cart_version_conflict")
        self.assertEqual(stale.json()["cart"]["version"], 1)
        merged = self.add(quantity=1, version=1)
        self.assertEqual(merged.json()["items"][0]["quantity"], 3)
        item_id = merged.json()["items"][0]["item_id"]
        changed = self.client.patch(f"{self.base}/cart/items/{item_id}",
                                    headers=self.headers(),
                                    json={"quantity": 4, "expected_version": 2})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["total_amount"], 14000)
        deleted = self.client.delete(f"{self.base}/cart/items/{item_id}",
                                     params={"expected_version": 3}, headers=self.headers())
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["version"], 4)
        self.assertEqual(deleted.json()["items"], [])

    def test_invalid_request_and_option_have_contract_error_shape(self):
        no_key = self.client.post(f"{self.base}/cart/items", json={
            "product_id": "americano", "temperature": "iced", "quantity": 1,
            "expected_version": 0,
        })
        self.assertEqual(no_key.json(), {"code": "invalid_request",
                                         "detail": "요청 형식이 올바르지 않습니다.", "cart": None})
        self.assertEqual(no_key.status_code, 422)
        self.assertEqual(self.add(quantity=True).json()["code"], "invalid_request")
        self.assertEqual(self.add(temperature=None).json()["code"], "invalid_option")
        self.assertEqual(self.add(product="sandwich", temperature="hot").json()["code"],
                         "invalid_option")
        self.assertEqual(self.add(product="unknown").json()["code"], "product_not_found")
        self.assertEqual(self.add(product="sandwich", temperature=None).status_code, 200)

    def test_quantity_limit_and_unknown_item(self):
        first = self.add(quantity=20)
        self.assertEqual(first.status_code, 200)
        exceeded = self.add(quantity=1, version=1)
        self.assertEqual(exceeded.status_code, 409)
        self.assertEqual(exceeded.json()["code"], "quantity_limit_exceeded")
        self.assertEqual(self.client.get(f"{self.base}/cart").json()["version"], 1)
        missing = self.client.patch(f"{self.base}/cart/items/missing", headers=self.headers(),
                                    json={"quantity": 1, "expected_version": 1})
        self.assertEqual((missing.status_code, missing.json()["code"]),
                         (404, "cart_item_not_found"))

    def test_order_replay_and_completed_session(self):
        empty = self.client.post(f"{self.base}/orders", headers=self.headers(),
                                 json={"expected_version": 0})
        self.assertEqual((empty.status_code, empty.json()["code"]), (409, "empty_cart"))
        self.assertEqual(self.add().status_code, 200)
        key = str(uuid4())
        first = self.client.post(f"{self.base}/orders", headers=self.headers(key),
                                 json={"expected_version": 1})
        self.assertEqual(first.status_code, 201)
        order = first.json()
        self.assertEqual(order["status"], "simulated")
        self.assertEqual(order["total_amount"], 3500)
        replay = self.client.post(f"{self.base}/orders", headers=self.headers(key),
                                  json={"expected_version": 1})
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.json(), order)
        after = self.client.get(f"{self.base}/cart")
        self.assertEqual((after.status_code, after.json()["code"]),
                         (410, "session_expired"))
        expired = self.add(version=2)
        self.assertEqual((expired.status_code, expired.json()["code"]),
                         (410, "session_expired"))

    def test_unknown_session(self):
        response = self.client.get("/api/v1/sessions/missing/cart")
        self.assertEqual((response.status_code, response.json()["code"]),
                         (404, "session_not_found"))


class OrderingConcurrencyTests(unittest.TestCase):
    def test_one_of_two_concurrent_writes_wins(self):
        sessions = SessionRepository()
        session_id = sessions.create().session_id
        service = OrderingService(sessions.exists, OrderingRepository())
        request = AddItemRequest(product_id="americano", temperature="iced",
                                 quantity=1, expected_version=0)

        def add(_):
            try:
                return service.add_item(session_id, str(uuid4()), request).version
            except OrderingError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(add, range(2)))
        self.assertCountEqual(outcomes, [1, "cart_version_conflict"])
