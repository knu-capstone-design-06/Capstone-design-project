from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.serve_large_button_fixture import create_fixture_app


WINDOW = {
    "screen_id": "menu",
    "window_start": "2026-11-24T12:00:00Z",
    "window_end": "2026-11-24T12:00:02Z",
    "touch": {"tap_count": 0, "miss_tap_count": 0, "repeat_tap_count": 0,
              "back_count": 0, "dwell_ms": 0},
}


class LargeButtonFixtureTests(unittest.TestCase):
    def setUp(self):
        dist = Path(self.enterContext(TemporaryDirectory()))
        (dist / "index.html").write_text("<h1>Kiosk fixture</h1>", encoding="utf-8")
        self.client = self.enterContext(TestClient(create_fixture_app(dist)))
        created = self.client.post("/backend/api/v1/sessions")
        self.assertEqual(created.status_code, 201, created.text)
        self.session_id = created.json()["session_id"]
        self.session_url = f"/backend/api/v1/sessions/{self.session_id}"

    def features(self, **overrides):
        return self.client.post(f"{self.session_url}/features", json={**WINDOW, **overrides})

    def add_item(self):
        response = self.client.post(f"{self.session_url}/cart/items",
                                    headers={"Idempotency-Key": str(uuid4())}, json={
            "product_id": "americano", "temperature": "iced", "quantity": 1, "expected_version": 0,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_serves_build_and_offers_only_on_menu_with_cart_items(self):
        self.assertIn("<h1>Kiosk fixture</h1>", self.client.get("/").text)
        empty_window = self.features()
        self.assertEqual(empty_window.status_code, 200, empty_window.text)
        self.assertEqual(empty_window.json()["support"]["preset"], "none")

        cart = self.add_item()
        menu_window = self.features()
        self.assertEqual(menu_window.status_code, 200, menu_window.text)
        result = menu_window.json()
        self.assertEqual(result["session_id"], self.session_id)
        self.assertTrue(result["ai_available"])
        self.assertEqual(result["support"], {
            "preset": "large_button", "requires_confirmation": True, "decided_by": "rule_placeholder",
        })
        review_window = self.features(screen_id="review")
        self.assertEqual(review_window.status_code, 200, review_window.text)
        self.assertEqual(review_window.json()["support"]["preset"], "none")
        self.assertEqual(self.client.get(f"{self.session_url}/cart").json(), cart)

    def test_preserves_window_validation_and_session_errors(self):
        cart = self.add_item()
        invalid = self.features(window_end=WINDOW["window_start"])
        self.assertEqual(invalid.status_code, 422, invalid.text)
        missing = self.client.post("/backend/api/v1/sessions/missing/features", json=WINDOW)
        self.assertEqual(missing.status_code, 404, missing.text)

        ordered = self.client.post(f"{self.session_url}/orders",
                                   headers={"Idempotency-Key": str(uuid4())},
                                   json={"expected_version": cart["version"]})
        self.assertEqual(ordered.status_code, 201, ordered.text)
        expired = self.features()
        self.assertEqual(expired.status_code, 410, expired.text)
        self.assertEqual(expired.json(), {"detail": "session_expired"})
