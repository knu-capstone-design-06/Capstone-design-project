import unittest

from fastapi.testclient import TestClient

from app.main import create_app


# Request/response examples of contract/backend-ai.openapi.yaml.
REQUEST = {
    "session_id": "3f2c9a0e7b1d4c5e8f6a2b1c0d9e8f7a",
    "screen_id": "menu_list",
    "window_start": "2026-10-01T10:00:00Z",
    "window_end": "2026-10-01T10:00:03Z",
    "touch": {
        "tap_count": 6, "miss_tap_count": 3, "repeat_tap_count": 2,
        "back_count": 0, "dwell_ms": 3000,
    },
    "vision": {
        "face_detected": True, "face_size_ratio": 0.35,
        "assistive_device": False, "confidence": 0.9,
    },
}
RESPONSE = {
    "session_id": REQUEST["session_id"],
    "measurable": True,
    "states": {
        "normal": 0.167, "touch_difficulty": 0.833,
        "navigation_difficulty": 0, "visual_difficulty": 0.056,
        "hesitation": 0.1,
    },
    "model_version": "dummy-0.1",
}
NOT_MEASURABLE = {**RESPONSE, "measurable": False, "states": None}
NO_TOUCH = {
    "tap_count": 0, "miss_tap_count": 0, "repeat_tap_count": 0,
    "back_count": 0, "dwell_ms": 3000,
}


class AnalyzeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def analyze(self, payload):
        return self.client.post("/v1/analyze", json=payload)

    def test_contract_example(self):
        response = self.analyze(REQUEST)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), RESPONSE)

    def test_vision_absent_or_null_is_still_judged_from_touch(self):
        for omitted in (True, False):
            payload = {**REQUEST, "vision": None}
            if omitted:
                del payload["vision"]
            with self.subTest(omitted=omitted):
                self.assertEqual(self.analyze(payload).json(), RESPONSE)

    def test_face_without_touch_is_still_judged(self):
        self.assertEqual(self.analyze({**REQUEST, "touch": NO_TOUCH}).json(), RESPONSE)

    def test_nothing_to_judge_is_not_measurable(self):
        no_face = {**REQUEST["vision"], "face_detected": False}
        for vision in (None, no_face):
            with self.subTest(vision=vision):
                response = self.analyze({**REQUEST, "touch": NO_TOUCH, "vision": vision})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), NOT_MEASURABLE)

    def test_echoes_session_id(self):
        body = self.analyze({**REQUEST, "session_id": "another-session"}).json()
        self.assertEqual(body["session_id"], "another-session")

    def test_scores_stay_in_contract_range(self):
        states = self.analyze(REQUEST).json()["states"]
        self.assertEqual(set(states), {
            "normal", "touch_difficulty", "navigation_difficulty",
            "visual_difficulty", "hesitation",
        })
        for score in states.values():
            self.assertTrue(0 <= score <= 1)

    def test_invalid_requests_are_rejected(self):
        touch, vision = REQUEST["touch"], REQUEST["vision"]
        missing_touch = {k: v for k, v in REQUEST.items() if k != "touch"}
        invalid = {
            "missing touch": missing_touch,
            "missing touch field": {**REQUEST, "touch": {"tap_count": 1}},
            "negative count": {**REQUEST, "touch": {**touch, "tap_count": -1}},
            "count as string": {**REQUEST, "touch": {**touch, "tap_count": "6"}},
            "ratio above 1": {**REQUEST, "vision": {**vision, "face_size_ratio": 1.5}},
            "confidence missing": {**REQUEST, "vision": {"face_detected": True}},
            "flag as string": {**REQUEST, "vision": {**vision, "face_detected": "true"}},
            "no timezone": {**REQUEST, "window_start": "2026-10-01T10:00:00"},
        }
        for name, payload in invalid.items():
            with self.subTest(name):
                self.assertEqual(self.analyze(payload).status_code, 422)


if __name__ == "__main__":
    unittest.main()
