"""The AI engine's windows reach the backend (POST /sessions/{id}/vision-windows) and are kept for the session."""

import asyncio
import json
import logging
import os
import threading
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.common.config.settings import Settings
from app.main import create_app
from app.modules.decision.repository import RETENTION, DecisionRepository
from app.modules.decision.rule_table import apply, decide
from app.modules.decision.service import DecisionService
from app.modules.decision.schemas import (
    AROUND, BIG, BUSY, HIGHLIGHT, NOTICE, PILOT_PARAMS, QUEUE, STALE, WAIT, SessionState, WindowInput,
)
from app.modules.sessions.schemas import FeatureWindowRequest, VisionWindowRequest
from app.modules.sessions.service import SessionService

RealAsyncClient = httpx.AsyncClient   # kept before any test patches app.main.httpx.AsyncClient

# The body the engine's sender posts: the example of contract/ai-backend.openapi.json (from the vision README's real
# output of its synthetic rows, with two of the evidence items and two of the six scene tags it shows).
CONTRACT = Path(__file__).resolve().parents[5] / "contract" / "ai-backend.openapi.json"
ENGINE_WINDOW = json.loads(CONTRACT.read_text(encoding="utf-8"))[
    "paths"]["/api/v1/sessions/{session_id}/vision-windows"]["post"]["requestBody"]["content"]["application/json"][
    "example"]


def engine_window(session_id, **changes):
    return {**deepcopy(ENGINE_WINDOW), "session_id": session_id, **changes}


class VisionWindowEntryTests(unittest.TestCase):
    def setUp(self):
        settings = Settings(_env_file=None, openai_api_key=None, ai_engine_url="http://127.0.0.1:9")
        self.client = self.enterContext(TestClient(create_app(settings)))
        self.repository = self.client.app.state.decision_repository

    def session(self):
        return self.client.post("/api/v1/sessions").json()["session_id"]

    def post(self, session_id, body):
        return self.client.post(f"/api/v1/sessions/{session_id}/vision-windows", json=body)

    def test_the_engine_window_is_acknowledged_and_kept_for_the_session(self):
        session_id = self.session()
        response = self.post(session_id, engine_window(session_id))
        self.assertEqual((response.status_code, response.json()), (202, {"status": "accepted"}))
        (kept,) = self.repository.vision(session_id)
        self.assertEqual((kept.window_start, kept.window_end),
                         (datetime(2027, 1, 15, 8, 0, 1, 700000, tzinfo=timezone.utc),
                          datetime(2027, 1, 15, 8, 0, 2, 700000, tzinfo=timezone.utc)))
        self.assertEqual(kept.situation, ENGINE_WINDOW["situation"], "the shape the rule table reads, as sent")
        self.assertEqual((kept.gaze, kept.face_seen), (True, True))
        self.assertEqual(kept.scene_tags, ENGINE_WINDOW["observations"]["scene_tags"])
        self.assertEqual(kept.model_version, ENGINE_WINDOW["model_version"])
        self.assertIsNotNone(kept.received_at.tzinfo)

    def test_the_body_may_leave_out_its_session_id_and_other_keys_are_not_read(self):
        # The engine sends no `detectors` (review row 13): the model does not carry it; a key it does not know is
        # ignored, as for every request model here.
        session_id = self.session()
        body = engine_window(session_id, detectors={"heads": "yes"})
        del body["session_id"]
        self.assertEqual(self.post(session_id, body).status_code, 202)
        (kept,) = self.repository.vision(session_id)
        self.assertFalse(hasattr(kept, "detectors"))

    def test_an_unknown_situation_without_gaze_is_kept_as_sent(self):
        session_id = self.session()
        body = engine_window(session_id, situation={"name": "unknown", "evidence": [], "confidence": "unknown"})
        body["observations"].update(gaze=None, face_seen=False)
        self.assertEqual(self.post(session_id, body).status_code, 202)
        (kept,) = self.repository.vision(session_id)
        self.assertEqual((kept.situation["name"], kept.situation["confidence"], kept.gaze, kept.face_seen),
                         ("unknown", "unknown", None, False))

    def test_unknown_and_completed_sessions_are_refused_as_features_refuses_them(self):
        response = self.post("missing", engine_window("missing"))
        self.assertEqual((response.status_code, response.json()), (404, {"detail": "session not found"}))
        session_id = self.session()
        base = f"/api/v1/sessions/{session_id}"
        self.assertEqual(self.client.post(f"{base}/cart/items", json={
            "product_id": "americano", "temperature": "iced", "quantity": 1, "expected_version": 0,
        }, headers={"Idempotency-Key": str(uuid4())}).status_code, 200)
        self.assertEqual(self.client.post(f"{base}/orders", json={"expected_version": 1},
                                          headers={"Idempotency-Key": str(uuid4())}).status_code, 201)
        response = self.post(session_id, engine_window(session_id))
        self.assertEqual((response.status_code, response.json()), (410, {"detail": "session_expired"}))
        self.assertEqual((self.repository.vision("missing"), self.repository.vision(session_id)), ([], []))

    def test_invalid_windows_are_refused_and_not_kept(self):
        session_id = self.session()

        def changed(path, value):
            body = engine_window(session_id)
            *parents, last = path
            target = body
            for key in parents:
                target = target[key]
            if value is KeyError:
                del target[last]
            else:
                target[last] = value
            return body

        invalid = {
            "end not after start": changed(("window_end",), ENGINE_WINDOW["window_start"]),
            "no time zone": changed(("window_start",), "2027-01-15T08:00:01.700"),
            "gaze as text": changed(("observations", "gaze"), "yes"),
            "gaze as a number": changed(("observations", "gaze"), 1),
            "no face_seen": changed(("observations", "face_seen"), KeyError),
            "no observations": changed(("observations",), KeyError),
            "no situation name": changed(("situation", "name"), KeyError),
            "empty situation name": changed(("situation", "name"), ""),
            "evidence without event_id": changed(("situation", "evidence"), [{"obs": "yaw_deg", "value": 1.0}]),
            "negative event count": changed(("situation", "confidence"), {"events": -1, "quality_ok": True}),
            "confidence as other text": changed(("situation", "confidence"), "high"),
            "scene tag status": changed(("observations", "scene_tags"), [{"name": "phone_use", "status": "maybe"}]),
            "no model_version": changed(("model_version",), KeyError),
        }
        for name, body in invalid.items():
            with self.subTest(name):
                self.assertEqual(self.post(session_id, body).status_code, 422)
        response = self.post(session_id, engine_window("another-session"))
        self.assertEqual((response.status_code, response.json()),
                         (422, {"detail": "session_id does not match the path"}))
        self.assertEqual(self.repository.vision(session_id), [])

    def test_the_windows_of_two_sessions_are_kept_apart(self):
        first, second = self.session(), self.session()
        self.post(first, engine_window(first))
        self.post(second, engine_window(second, model_version="other"))
        self.assertEqual([w.model_version for w in self.repository.vision(first)], [ENGINE_WINDOW["model_version"]])
        self.assertEqual([w.model_version for w in self.repository.vision(second)], ["other"])


class Sessions:
    def __init__(self):
        self.threads = []

    def exists(self, session_id):
        self.threads.append(threading.get_ident())
        return True


class Ordering:
    def __init__(self):
        self.threads = []

    def is_completed(self, session_id):
        self.threads.append(threading.get_ident())
        return False


class VisionWindowServiceTests(unittest.TestCase):
    WINDOW = VisionWindowRequest.model_validate(ENGINE_WINDOW)

    def test_session_checks_run_outside_the_event_loop(self):
        sessions, ordering, repository = Sessions(), Ordering(), DecisionRepository()
        service = SessionService(sessions, ordering, decision=DecisionService(repository, PILOT_PARAMS, None, stages=()))

        async def run():
            return threading.get_ident(), await service.receive_vision("s1", self.WINDOW)

        loop_thread, answer = asyncio.run(run())
        self.assertEqual(answer.status, "accepted")
        self.assertEqual((len(sessions.threads), len(ordering.threads)), (1, 1))
        self.assertTrue(all(t != loop_thread for t in sessions.threads + ordering.threads))
        self.assertEqual(len(repository.vision("s1")), 1)

    def test_without_a_judgment_layer_the_window_is_acknowledged_only(self):
        service = SessionService(Sessions(), Ordering())
        self.assertEqual(asyncio.run(service.receive_vision("s1", self.WINDOW)).status, "accepted")


class VisionWindowRetentionTests(unittest.TestCase):
    """The engine's windows live as long as the session's other decision records (repository RETENTION)."""

    T0 = datetime(2027, 1, 15, 8, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.now = [self.T0]
        self.repository = DecisionRepository(clock=lambda: self.now[0])
        self.service = DecisionService(self.repository, PILOT_PARAMS, None, stages=())
        self.service.add_vision("s1", VisionWindowRequest.model_validate(ENGINE_WINDOW))

    def test_kept_up_to_the_retention_and_dropped_after_it(self):
        self.now[0] = self.T0 + RETENTION
        self.assertEqual(len(self.repository.vision("s1")), 1, "exactly the retention: still kept")
        self.now[0] = self.T0 + RETENTION + timedelta(seconds=1)
        self.assertEqual(self.repository.vision("s1"), [])

    def test_another_sessions_access_expires_them(self):
        self.now[0] = self.T0 + 2 * RETENTION
        self.repository.state("s2")
        self.assertEqual(self.repository.vision("s1"), [])

    def test_the_session_expires_while_the_engine_keeps_posting_and_its_windows_stay_bounded(self):
        # Review row 4: the order screen's last /features window at T0, then engine posts only, a quarter of the
        # retention apart (the test's pace, no product value). Posts do not refresh the idle time.
        step = RETENTION / 4
        self.service.observe("s1", FeatureWindowRequest.model_validate(touch_body(0, 2, backs=1)), measurable=True)
        kept = []
        for k in range(1, 13):
            self.now[0] = self.T0 + k * step
            self.service.add_vision("s1", VisionWindowRequest.model_validate(ENGINE_WINDOW))
            kept.append(len(self.repository.vision("s1")))
            if k == 5:
                self.assertEqual(self.repository.windows("s1"), [], "idle past the retention: the record is gone")
        # Never more than the posts of one retention (plus the one at T0); each expiry starts the count again.
        self.assertEqual(kept, [2, 3, 4, 5, 1, 2, 3, 4, 5, 1, 2, 3])


T = datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc)
PLACEHOLDER_SUPPORT = {"preset": "none", "requires_confirmation": False, "decided_by": "rule_placeholder"}
SCORES = {"normal": 0.167, "touch_difficulty": 0.833, "navigation_difficulty": 0.0, "visual_difficulty": 0.056,
          "hesitation": 0.1}


def at(seconds):
    return T + timedelta(seconds=seconds)


def touch_body(start_s, end_s, taps=1, backs=0, screen="menu", interaction=None):
    body = {"screen_id": screen, "window_start": at(start_s).isoformat(), "window_end": at(end_s).isoformat(),
            "touch": {"tap_count": taps, "miss_tap_count": 0, "repeat_tap_count": 0, "back_count": backs,
                      "dwell_ms": 1000}}
    if interaction is not None:
        body["touch"]["interaction"] = interaction
    return body


def interaction_block(**changes):
    """touch.interaction with every key frontend interactionFeatures.ts sends (schema touch-interaction-pilot-v1):
    the options dialog open, no input for 9.5 s of which 8 s outside system waits, voice idle, microphone off."""
    block = {
        "schema_version": "touch-interaction-pilot-v1", "visit_id": "visit-1", "window_sequence": 5,
        "outside_tap_ratio": None, "outside_nearest_distance_mean_px": None, "outside_nearest_distance_sample_count": 0,
        "pointer_cancel_count": 0, "pointer_interrupted_count": 0, "scroll_event_count": 0, "category_change_count": 0,
        "options_open_count": 0, "options_close_count": 0, "screen_transition_count": 0, "screen_revisit_count": 0,
        "cart_change_count": 0, "selection_change_count": 0, "ui_settings_change_count": 0,
        "voice_state_change_count": 0, "since_last_input_ms": 9500, "order_busy_ms": 0, "options_open": True,
        "order_busy": False, "voice_enabled": True, "microphone_active": False, "voice_processing": False,
        "voice_phase": "idle", "voice_speaking": False, "voice_busy": False, "voice_busy_ms": 0,
        "since_last_input_excluding_system_busy_ms": 8000, "voice_auto_off": None,
        "ui_settings": {"large_text": False, "large_button": False, "simple_screen": False, "step_guide": False,
                        "low_screen": False, "high_contrast": False},
    }
    return {**block, **changes}


def engine_body(session_id, end_s, name=AROUND, gaze=True, face_seen=True, model_version=None):
    """An engine window for the one-second segment ending end_s after T (the sender's segment_s)."""
    body = engine_window(session_id, window_start=at(end_s - 1).isoformat(), window_end=at(end_s).isoformat())
    body["situation"]["name"] = name
    body["observations"].update(gaze=gaze, face_seen=face_seen)
    if model_version is not None:
        body["model_version"] = model_version
    return body


class PairingTests(unittest.TestCase):
    """Which engine window a /features window reads: start - (end - start) < engine end <= end, the latest one."""

    def setUp(self):
        self.repository = DecisionRepository()
        self.service = DecisionService(self.repository, PILOT_PARAMS, None, stages=())

    def add(self, *ends_s, session_id="s1", model_version=None):
        for end_s in ends_s:
            self.service.add_vision(session_id, VisionWindowRequest.model_validate(
                engine_body(session_id, end_s, model_version=model_version)))

    def paired(self, start_s, end_s, session_id="s1"):
        return self.service.paired_vision(session_id, FeatureWindowRequest.model_validate(touch_body(start_s, end_s)))

    def paired_end(self, start_s, end_s, session_id="s1"):
        paired = self.paired(start_s, end_s, session_id)
        return None if paired is None else (paired.window_end - T).total_seconds()

    def kept_ends(self, session_id="s1"):
        return [(w.window_end - T).total_seconds() for w in self.repository.vision(session_id)]

    def test_the_edges_of_the_interval(self):
        # The touch window 2..4 s reads the engine windows that ended in (0, 4]; one millisecond either side.
        for end_s, expected in ((0.0, None), (0.001, 0.001), (4.0, 4.0), (4.001, None)):
            with self.subTest(engine_end=end_s):
                self.setUp()
                self.add(end_s)
                self.assertEqual(self.paired_end(2.0, 4.0), expected)

    def test_windows_at_or_before_the_bound_are_dropped_and_later_ones_kept(self):
        self.add(-1.0, 0.0, 1.0, 5.0)
        self.assertEqual(self.paired_end(2.0, 4.0), 1.0)
        self.assertEqual(self.kept_ends(), [1.0, 5.0], "the one read stays; the one ahead waits for its window")
        self.assertEqual(self.paired_end(4.0, 6.0), 5.0)
        self.assertEqual(self.kept_ends(), [5.0])

    def test_the_latest_end_is_read_and_of_equal_ends_the_last_arrived(self):
        self.add(3.0, 2.0)
        self.assertEqual(self.paired_end(2.0, 4.0), 3.0, "by end time, not by arrival")
        self.add(3.0, model_version="again")
        self.assertEqual(self.paired(2.0, 4.0).model_version, "again")

    def test_the_tolerance_is_the_touch_windows_own_length(self):
        self.add(0.5)
        self.assertEqual(self.paired_end(3.0, 6.0), 0.5, "a 3 s touch window reads back to 0 s")
        self.setUp()
        self.add(3.5)
        self.assertIsNone(self.paired_end(5.0, 6.0), "a 1 s touch window reads back to 4 s only")

    def test_a_window_the_latest_touch_window_can_no_longer_read_is_not_kept(self):
        # Review row 4: pruned on arrival by the latest touch window's own bound (no other number).
        self.add(3.0)
        self.assertEqual(self.paired_end(2.0, 4.0), 3.0)      # bound 0 s
        self.add(0.0, 0.5)                                   # late arrivals: at the bound, and after it
        self.assertEqual(self.kept_ends(), [3.0, 0.5])
        self.assertEqual(self.paired_end(4.0, 6.0), 3.0)      # bound 2 s drops 0.5
        self.paired_end(1.0, 3.0)                             # a late touch window does not lower the bound
        self.add(1.5, 2.5)
        self.assertEqual(self.kept_ends(), [3.0, 2.5])

    def test_a_window_of_another_session_is_not_read(self):
        self.add(3.0, session_id="other")
        self.assertIsNone(self.paired_end(2.0, 4.0))
        self.assertEqual(self.kept_ends("other"), [3.0])

    def test_no_engine_window_reads_nothing(self):
        self.assertIsNone(self.paired(2.0, 4.0))

    def add_named(self, end_s, name, gaze=True, face_seen=True):
        self.service.add_vision("s1", VisionWindowRequest.model_validate(engine_body("s1", end_s, name, gaze, face_seen)))

    def test_a_tag_of_the_earlier_window_is_not_lost_behind_a_later_none(self):
        # The laptop run's r3: one touch window released two segments; the tag held in the earlier one only.
        self.add_named(3.0, QUEUE, gaze=False, face_seen=False)
        self.add_named(4.0, "none")
        paired = self.paired(2.0, 4.0)
        self.assertEqual((paired.situation["name"], paired.situation_window_end), (QUEUE, at(3)))
        self.assertEqual(paired.situation, self.repository.vision("s1")[0].situation, "with its evidence and confidence")
        self.assertEqual((paired.window_end, paired.gaze, paired.face_seen), (at(4), True, True),
                         "gaze and face from the latest window")

    def test_a_tag_of_the_latest_window_wins(self):
        self.add_named(3.0, QUEUE)
        self.add_named(4.0, BUSY)
        paired = self.paired(2.0, 4.0)
        self.assertEqual((paired.situation["name"], paired.situation_window_end), (BUSY, at(4)))

    def test_of_two_earlier_tags_the_fresher_one_is_read(self):
        self.add_named(2.5, BUSY)
        self.add_named(3.0, QUEUE)
        self.add_named(4.0, "none")
        self.assertEqual(self.paired(2.0, 4.0).situation["name"], QUEUE)

    def test_with_no_tag_named_the_latest_windows_situation_stands(self):
        self.add_named(3.0, "none")
        self.add_named(4.0, "unknown")
        paired = self.paired(2.0, 4.0)
        self.assertEqual((paired.situation["name"], paired.situation_window_end), ("unknown", at(4)))

    def test_a_tag_outside_the_bound_is_not_used(self):
        self.add_named(0.0, QUEUE)                     # at the bound of the touch window 2..4 s
        self.add_named(3.0, "none")
        paired = self.paired(2.0, 4.0)
        self.assertEqual((paired.situation["name"], paired.situation_window_end), ("none", at(3)))


class PressSpanTests(unittest.TestCase):
    """Which earlier touch windows lend their press to a /features window (DecisionService.pressed_before, read under
    the demonstration switch): judged windows of the session's current timeline with a tap or a back that ended in its
    pairing span, start - (end - start) < earlier end < end, the span of the engine windows it reads."""

    def setUp(self):
        self.repository, self.clock = DecisionRepository(), {"now": 1000.0}
        self.service = DecisionService(self.repository, PILOT_PARAMS, None, stages=(), now=lambda: self.clock["now"])

    def observe(self, start_s, end_s, session_id="s1", passed=1.0, **touch):
        """Record a /features window as the session service does; the server clock moves `passed` before it."""
        self.clock["now"] += passed
        self.service.observe(session_id, FeatureWindowRequest.model_validate(touch_body(start_s, end_s, **touch)),
                             measurable=True)

    def pressed_before(self, start_s, end_s, session_id="s1"):
        window = FeatureWindowRequest.model_validate(touch_body(start_s, end_s, taps=0))
        return self.service.pressed_before(session_id, window)

    def test_the_edges_of_the_span(self):
        # The touch window 12..13 s reads back to 11 s; an earlier window must also end before 13 s.
        for end_s, expected in ((11.0, False), (11.001, True), (12.0, True), (13.0, False), (13.5, False)):
            with self.subTest(press_window_end=end_s):
                self.setUp()
                self.observe(end_s - 1, end_s)
                self.assertEqual(self.pressed_before(12.0, 13.0), expected)

    def test_a_back_counts_as_a_tap_does_and_only_the_sessions_own_windows_count(self):
        self.observe(11, 12, taps=0, backs=1)
        self.assertTrue(self.pressed_before(12, 13))
        self.setUp()
        self.observe(11, 12, taps=0)
        self.observe(11, 12, session_id="other")
        self.assertFalse(self.pressed_before(12, 13), "no press of its own; another session's press")

    def test_a_window_recorded_only_does_not_count(self):
        self.observe(12, 13, taps=0)
        self.observe(11.5, 12.5)                              # late: arrives after the window ending 13 s
        self.assertEqual(self.repository.windows("s1")[-1].jev, STALE)
        self.assertFalse(self.pressed_before(13, 14), "its end, 12.5 s, lies in the span (12, 14)")

    def test_a_window_of_the_timeline_before_a_clock_move_does_not_count(self):
        # The clock is set back by 2,000 s: the two timelines overlap in time, only the epoch tells them apart.
        self.observe(1007.5, 1008.5)                          # a press on the timeline before
        self.observe(3007.5, 3008.5, taps=0, passed=2000.0)
        self.observe(1006, 1007, taps=0)                      # off that timeline: recorded only
        self.observe(1007, 1008, taps=0)                      # follows it: the new epoch
        old = self.repository.windows("s1")[0]
        self.assertEqual((old.jev == STALE, old.epoch, self.repository.state("s1").epoch), (False, 0, 1))
        self.assertFalse(self.pressed_before(1008, 1009), "the press window ended at 1008.5, inside (1007, 1009)")


class FeaturesAppCase(unittest.TestCase):
    """An app whose ai-engine answers like the team placeholder; helpers to post engine and /features windows."""

    def setUp(self):
        self.ai_mode = "normal"
        self.ai_requests = []

        async def ai_engine(request):
            # ai-engine's placeholder (app/inference/placeholder.py): measurable with a tap or back, or a face in the
            # request's vision, which /features windows from the order screen do not carry.
            if self.ai_mode == "down":
                raise httpx.ConnectError("offline", request=request)
            payload = json.loads(request.content)
            self.ai_requests.append(payload)
            touch, vision = payload["touch"], payload.get("vision") or {}
            seen = touch["tap_count"] > 0 or touch["back_count"] > 0 or vision.get("face_detected") is True
            if self.ai_mode == "invalid":    # measurable, with scores the response rejects
                return httpx.Response(200, json={"session_id": payload["session_id"], "measurable": True,
                                                 "states": {"normal": 1.5}, "model_version": "dummy-0.1"})
            return httpx.Response(200, json={"session_id": payload["session_id"], "measurable": seen,
                                             "states": SCORES if seen else None, "model_version": "dummy-0.1"})

        self.app = create_app(self.settings())
        http = httpx.AsyncClient(base_url="http://ai-engine:8001", transport=httpx.MockTransport(ai_engine))
        patcher = patch("app.main.httpx.AsyncClient", return_value=http)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = self.enterContext(TestClient(self.app))
        self.repository = self.client.app.state.decision_repository
        self.session_id = self.new_session()

    def settings(self):
        # The switch is named, so a DECISION_SEND_SUPPORT in the shell does not turn these cases on.
        return Settings(_env_file=None, openai_api_key=None, decision_send_support=False)

    def new_session(self):
        return self.client.post("/api/v1/sessions").json()["session_id"]

    def engine(self, end_s, name, gaze=True, face_seen=True, session_id=None):
        session_id = session_id or self.session_id
        response = self.client.post(f"/api/v1/sessions/{session_id}/vision-windows",
                                    json=engine_body(session_id, end_s, name, gaze, face_seen))
        self.assertEqual(response.status_code, 202)

    def features(self, start_s, end_s, session_id=None, **touch):
        session_id = session_id or self.session_id
        response = self.client.post(f"/api/v1/sessions/{session_id}/features", json=touch_body(start_s, end_s, **touch))
        self.assertEqual(response.status_code, 200)
        records = self.repository.windows(session_id)
        return response, records[-1] if records else None

    def held(self, session_id=None):
        return self.repository.state(session_id or self.session_id).held


class PairedFeaturesTests(FeaturesAppCase):
    """/features windows read the engine window paired with them; the rule table opens what rule_table.py says."""

    def test_people_behind_open_the_remaining_steps_notice_of_scene_3_1(self):
        _, first = self.features(0, 2)
        self.assertIsNone(first.vision_window, "the engine's window for 0..2 s is not there yet")
        self.engine(2, QUEUE)                      # it arrives just after that /features request
        _, record = self.features(2, 4)            # and is read with the next one
        self.assertEqual((record.inputs["situation"]["name"], record.inputs["gaze"]), (QUEUE, True))
        self.assertEqual((record.decision["transition"], record.decision["support"], record.decision["scene"],
                          record.decision["policy"]["kind"]), ("open", NOTICE, "3-1", "fit"))
        self.assertEqual(self.held().decision.form(), ("step_guide", False))
        self.assertEqual(set(record.vision_window), {"window_start", "window_end", "received_at", "model_version",
                                                     "face_seen", "scene_tags", "situation_window_end"})
        self.assertEqual(record.vision_window["situation_window_end"], at(2), "one window gave both")
        self.assertEqual(record.vision_window["scene_tags"], ENGINE_WINDOW["observations"]["scene_tags"],
                         "the paired window's scene tags, for the later rows (review row 13)")
        self.assertEqual((record.vision_window["window_start"], record.vision_window["window_end"]), (at(1), at(2)))

    def test_a_tag_in_the_earlier_of_two_segments_opens_3_1(self):
        # The laptop run's r3: the /features window 0..2 s is sent before the engine's two segments for it arrive;
        # the tag held in the earlier segment (1 s), the later one (2 s) says none. Both are read with the next window.
        self.features(0, 2)
        self.engine(1, QUEUE, gaze=False)
        self.engine(2, "none")
        _, record = self.features(2, 4)
        self.assertEqual((record.decision["transition"], record.decision["support"], record.decision["scene"]),
                         ("open", NOTICE, "3-1"))
        self.assertEqual((record.inputs["situation"]["name"], record.inputs["gaze"]), (QUEUE, True),
                         "the tag from the earlier window, the gaze from the latest")
        self.assertEqual((record.vision_window["window_end"], record.vision_window["situation_window_end"]),
                         (at(2), at(1)))

    def test_a_companion_opens_the_wait_of_scene_3_2_in_a_window_without_touches_when_a_face_was_seen(self):
        self.engine(2, BUSY, gaze=False)
        response, record = self.features(2, 4, taps=0)
        self.assertEqual((record.ai, record.inputs["measurable"]), ("unmeasurable", True),
                         "ai-engine saw no tap or back; the engine saw a face")
        self.assertEqual((record.decision["transition"], record.decision["support"], record.decision["scene"]),
                         ("open", WAIT, "3-2"))
        self.assertEqual(self.held().decision.session_signal, {"name": "hold_timer"})
        self.assertEqual((response.json()["ai_available"], response.json()["states"]), (True, None),
                         "the answer stays ai-engine's")

    def test_a_window_without_touches_stays_unmeasurable_without_a_face_or_an_engine_window(self):
        self.engine(2, BUSY, face_seen=False)
        _, record = self.features(2, 4, taps=0)
        self.assertEqual((record.inputs["measurable"], record.decision["transition"]), (False, "none"))
        _, record = self.features(4, 6, taps=0)     # the window ending at 2 s is at this one's bound: dropped
        self.assertEqual((record.vision_window, record.inputs["measurable"]), (None, False))

    def test_a_face_does_not_make_a_window_measurable_when_ai_engine_did_not_answer(self):
        self.ai_mode = "down"
        self.engine(2, BUSY)
        response, record = self.features(2, 4, taps=0)
        self.assertEqual((record.ai, record.inputs["measurable"], record.decision["transition"]),
                         ("unavailable", False, "none"))
        self.assertEqual(response.json()["ai_available"], False)

    def test_looking_around_with_a_gaze_opens_scene_4_2_with_the_lowered_pause_and_the_fit_question(self):
        self.engine(2, AROUND)
        _, record = self.features(2, 4, backs=1)
        seen = self.held().decision
        self.assertEqual((record.decision["support"], record.decision["scene"], record.decision["policy"]["kind"]),
                         (HIGHLIGHT, "4-2", "fit"))
        self.assertEqual((seen.cues["looking_around"], seen.cues["facing_screen"], seen.cues["pause_min_s"]),
                         (True, True, PILOT_PARAMS.lost_pause_s_vision))
        self.assertEqual(seen.jev_request["state"]["vision"], {"facing_screen": True, "looking_around": True})
        # The same back in a session without an engine window: the row opens on the back alone, unraised, no question.
        other = self.new_session()
        self.features(2, 4, session_id=other, backs=1)
        plain = self.held(other).decision
        self.assertEqual((plain.support, plain.cues["looking_around"], plain.cues["facing_screen"],
                          plain.cues["pause_min_s"], plain.policy["kind"]),
                         (HIGHLIGHT, False, None, PILOT_PARAMS.lost_pause_s, None))

    def test_without_an_engine_window_record_and_answer_are_those_of_the_pre_integration_backend(self):
        # Fixed values: the same window (menu, one tap and one back, 10:00:00-10:00:02) through the backend of the base
        # commit 1a8852c, before this integration, with the same ai-engine stub (review row 11).
        response, record = self.features(0, 2, backs=1)
        self.assertEqual(response.content, b'{"session_id":"' + self.session_id.encode()
                         + b'","ai_available":true,"states":{"normal":0.167,"touch_difficulty":0.833,'
                           b'"navigation_difficulty":0.0,"visual_difficulty":0.056,"hesitation":0.1},'
                           b'"model_version":"dummy-0.1"' + PLACEHOLDER_BYTES)
        # The input fields the scene rows added after it are None without the switch.
        self.assertEqual(record.inputs, {
            "t": 1795600802.0, "measurable": True, "situation": None, "screen": "menu", "steps_left": 2, "gaze": None,
            "misses_recent": 0, "fixes_recent": None, "backs_recent": 1, "pause_s": None, "taps_segment": 1,
            "progress_segment": None, "options_open": None, "cart_items": None, "fixes_segment": None,
            "zoom_attempts_segment": None, "zoom_attempt": None, "can_offer": None, "supports_on": None})
        self.assertEqual(record.decision, {
            "transition": "open", "support": "highlight_next_action", "scene": "4-2", "action": "apply",
            "decision_id": "d0001", "reason": "row 4-2 rank 7", "tag": None,
            "policy": {"kind": None, "ask_jev": False, "lowered_action": "wait", "raised_action": None,
                       "T_LOWER": None, "T_AID": None, "T_CHOICE": None, "default_choice": None,
                       "choice_actions": None, "jev_deadline": "next_segment", "no_response_s": 10.0}})
        self.assertEqual((record.ai, record.ai_model_version, record.jev), ("ok", "dummy-0.1", "off"))
        self.assertIsNone(record.vision_window, "the one key the integration adds to the record")

    def test_an_engine_window_of_another_session_is_not_read(self):
        other = self.new_session()
        self.engine(2, AROUND, session_id=other)
        _, record = self.features(2, 4, backs=1)
        self.assertEqual((record.vision_window, record.inputs["situation"]), (None, None))
        self.assertEqual(len(self.repository.vision(other)), 1)

    def test_a_pairing_failure_leaves_the_answer_as_it_was(self):
        self.engine(2, AROUND)
        with patch.object(DecisionService, "paired_vision", side_effect=RuntimeError("pairing boom")):
            with self.assertLogs("app.modules.sessions.service", "ERROR"):
                response, _ = self.features(2, 4, backs=1)
        self.assertEqual(response.json()["support"], PLACEHOLDER_SUPPORT)
        self.assertEqual(response.json()["states"], SCORES)


PLACEHOLDER_BYTES = b',"support":{"preset":"none","requires_confirmation":false,"decided_by":"rule_placeholder"}}'


def tremor_decision():
    """The rule table's 4-1 decision (large button, asks first). Its cue, near misses fixed at once, has no /features
    field yet (fixes_recent stays None there), so the decision is made from the table's own input line."""
    inp = WindowInput(t=at(4).timestamp(), measurable=True, screen="menu", steps_left=2, fixes_recent=2, gaze=True)
    return apply(SessionState(), decide(inp, SessionState(), PILOT_PARAMS))[1]


class SwitchOffTests(FeaturesAppCase):
    def test_the_switch_is_off_by_default_and_read_from_decision_send_support(self):
        with patch.dict(os.environ):                   # independent of the shell this test runs in
            os.environ.pop("DECISION_SEND_SUPPORT", None)
            self.assertFalse(Settings(_env_file=None).decision_send_support)
            os.environ["DECISION_SEND_SUPPORT"] = "true"
            self.assertTrue(Settings(_env_file=None).decision_send_support)

    def test_with_ai_engine_down_the_answer_and_the_record_are_todays(self):
        self.ai_mode = "down"
        self.engine(2, QUEUE)
        response, record = self.features(2, 4)
        self.assertEqual(response.content, b'{"session_id":"' + self.session_id.encode()
                         + b'","ai_available":false,"states":null,"model_version":null' + PLACEHOLDER_BYTES)
        self.assertEqual((record.inputs["measurable"], record.decision["transition"]), (False, "none"),
                         "the valid gate: no ai-engine answer, not measurable")

    def test_the_answer_stays_byte_for_byte_the_placeholder_while_the_table_opens_supports(self):
        for scene, name, touch in (("3-1", QUEUE, {}), ("3-2", BUSY, {"taps": 0}), ("4-2", AROUND, {"backs": 1})):
            with self.subTest(scene):
                session_id = self.new_session()
                self.engine(2, name, session_id=session_id)
                response, record = self.features(2, 4, session_id=session_id, **touch)
                self.assertEqual((record.decision["transition"], record.decision["scene"]), ("open", scene))
                self.assertTrue(response.content.endswith(PLACEHOLDER_BYTES), response.content)
                self.assertEqual(response.json()["support"], PLACEHOLDER_SUPPORT)


class SwitchOnTests(FeaturesAppCase):
    """DECISION_SEND_SUPPORT on: the answer's support carries the rule table's decision in the contract form."""

    def settings(self):
        return Settings(_env_file=None, openai_api_key=None, decision_send_support=True)

    def support(self, *args, **kwargs):
        response, _ = self.features(*args, **kwargs)
        return response.json()["support"]

    def test_a_4_1_decision_answers_the_large_button_that_asks_first(self):
        with patch.object(DecisionService, "observe", return_value=tremor_decision()):
            self.assertEqual(self.support(2, 4), {
                "preset": "large_button", "requires_confirmation": True, "decided_by": "rule_placeholder",
                "name": BIG, "decision_id": "d0001", "steps_left": 2})

    def test_a_4_2_window_answers_the_highlight_with_its_target(self):
        self.assertEqual(self.support(0, 2, backs=1), {
            "preset": "none", "requires_confirmation": False, "decided_by": "rule_placeholder",
            "name": HIGHLIGHT, "decision_id": "d0001", "steps_left": 2})
        other = self.new_session()
        self.assertEqual(self.support(0, 2, session_id=other, backs=1, screen="review"), {
            "preset": "none", "requires_confirmation": False, "decided_by": "rule_placeholder",
            "name": HIGHLIGHT, "decision_id": "d0001", "steps_left": 1, "target_id": "cart:*:decrease"})

    def test_a_3_1_notice_answers_step_guide_with_its_message_and_progress_line(self):
        self.engine(2, QUEUE)
        self.assertEqual(self.support(2, 4), {
            "preset": "step_guide", "requires_confirmation": False, "decided_by": "rule_placeholder",
            "name": NOTICE, "decision_id": "d0001", "steps_left": 2, "target_id": "cart_progress",
            "message_id": "steps_left_notice"})

    def test_a_3_2_wait_answers_its_name_with_preset_none(self):
        self.engine(2, BUSY)
        self.assertEqual(self.support(2, 4, taps=0), {
            "preset": "none", "requires_confirmation": False, "decided_by": "rule_placeholder",
            "name": WAIT, "decision_id": "d0001", "steps_left": 2})

    def test_a_held_support_repeats_its_decision_id_and_a_replacement_brings_a_new_one(self):
        opened = self.support(0, 2, backs=1)
        repeated = self.support(2, 4)
        self.assertEqual((opened["name"], opened["decision_id"]), (HIGHLIGHT, "d0001"))
        self.assertEqual(repeated, opened, "the held 4-2 again: the same answer, the same id")
        self.assertEqual(self.repository.windows(self.session_id)[-1].decision["transition"], "keep")
        self.engine(4, QUEUE)
        replaced = self.support(4, 6)
        self.assertEqual((replaced["name"], replaced["decision_id"]), (NOTICE, "d0002"), "3-1 ranks ahead of 4-2")
        self.assertEqual(self.repository.windows(self.session_id)[-1].decision["transition"], "replace")

    def test_no_row_and_a_withdrawn_support_answer_preset_none(self):
        self.assertEqual(self.support(0, 2), PLACEHOLDER_SUPPORT, "no row opens")
        self.assertEqual(self.support(2, 4, backs=1)["name"], HIGHLIGHT)
        self.assertEqual(self.support(4, 6, screen="review"), PLACEHOLDER_SUPPORT, "a step forward withdraws 4-2")
        self.assertEqual(self.repository.windows(self.session_id)[-1].decision["transition"], "withdraw")

    def test_a_held_support_is_still_answered_while_ai_engine_is_down(self):
        opened = self.support(0, 2, backs=1)
        self.ai_mode = "down"
        response, record = self.features(2, 4)
        self.assertEqual((record.decision["transition"], record.inputs["measurable"]), ("keep", True), "a tap")
        body = response.json()
        self.assertEqual((body["ai_available"], body["states"], body["model_version"]), (False, None, None))
        self.assertEqual(body["support"], opened)

    def test_a_3_1_window_opens_the_notice_whatever_ai_engine_returned(self):
        # Review row 3: under the switch the chain does not ride on /v1/analyze.
        for mode in ("down", "invalid"):
            with self.subTest(mode):
                self.ai_mode = mode
                session_id = self.new_session()
                self.engine(2, QUEUE, session_id=session_id)
                response, record = self.features(2, 4, session_id=session_id)
                self.assertEqual((record.inputs["measurable"], record.decision["transition"],
                                  record.decision["support"]), (True, "open", NOTICE))
                self.assertEqual(record.ai, "unavailable" if mode == "down" else "invalid_scores")
                body = response.json()
                self.assertEqual((body["ai_available"], body["states"], body["model_version"]), (False, None, None))
                self.assertEqual(body["support"], {
                    "preset": "step_guide", "requires_confirmation": False, "decided_by": "rule_placeholder",
                    "name": NOTICE, "decision_id": "d0001", "steps_left": 2, "target_id": "cart_progress",
                    "message_id": "steps_left_notice"})

    def test_a_face_in_the_window_that_gave_the_situation_makes_a_touchless_window_measurable(self):
        # Review round 2 row 33: the tag held in the earlier segment with a face; the face was lost in the later one
        # (a full turn toward the people behind); no tap in the window.
        self.engine(3, QUEUE, face_seen=True)
        self.engine(4, "none", face_seen=False)
        _, record = self.features(2, 4, taps=0)
        self.assertEqual((record.inputs["measurable"], record.decision["transition"], record.decision["support"]),
                         (True, "open", NOTICE))
        self.assertEqual(record.vision_window["face_seen"], False, "the record keeps the latest window's face")

    def test_a_window_without_touch_or_face_stays_unmeasurable_under_the_switch(self):
        self.engine(2, BUSY, face_seen=False)
        _, record = self.features(2, 4, taps=0)
        self.assertEqual((record.inputs["measurable"], record.decision["transition"]), (False, "none"))

    def test_a_decision_layer_failure_answers_preset_none(self):
        with patch.object(DecisionService, "observe", side_effect=RuntimeError("decision boom")):
            with self.assertLogs("app.modules.sessions.service", "ERROR"):
                self.assertEqual(self.support(0, 2, backs=1), PLACEHOLDER_SUPPORT)


CONTRACT_TOUCH = {"tap_count", "miss_tap_count", "repeat_tap_count", "back_count", "dwell_ms"}


class PilotBlockCase(FeaturesAppCase):
    def paused(self, block, gaze=False):
        """A new session's window without touches after an engine window that saw a face (measurable by the face
        rule) and judged no situation: only the pilot block can open a row. (response, record, session_id)."""
        session_id = self.new_session()
        self.engine(2, "unknown", gaze=gaze, session_id=session_id)
        response, record = self.features(2, 4, session_id=session_id, taps=0, interaction=block)
        return response, record, session_id


class PilotBlockOnTests(PilotBlockCase):
    """DECISION_SEND_SUPPORT on: touch.interaction gives the rule table options_open and pause_s."""

    def settings(self):
        return Settings(_env_file=None, openai_api_key=None, decision_send_support=True)

    def test_a_pause_opens_the_4_2_highlight_on_the_options_target_at_the_tables_own_pause(self):
        for name, gaze, pause_min in (("lost_pause_s, gaze away", False, PILOT_PARAMS.lost_pause_s),
                                      ("lost_pause_s_vision, facing", True, PILOT_PARAMS.lost_pause_s_vision)):
            with self.subTest(name):
                block = interaction_block(since_last_input_excluding_system_busy_ms=pause_min * 1000)
                response, record, session_id = self.paused(block, gaze)
                self.assertEqual((record.inputs["pause_s"], record.inputs["options_open"]), (pause_min, True))
                self.assertEqual((record.decision["transition"], record.decision["support"]), ("open", HIGHLIGHT))
                cues = self.held(session_id).decision.cues
                self.assertEqual((cues["pause_s"], cues["pause_min_s"], cues["backs_recent"]), (pause_min, pause_min, 0))
                self.assertEqual(response.json()["support"], {
                    "preset": "none", "requires_confirmation": False, "decided_by": "rule_placeholder",
                    "name": HIGHLIGHT, "decision_id": "d0001", "steps_left": 2, "target_id": "cart-add"})
                below = interaction_block(since_last_input_excluding_system_busy_ms=pause_min * 1000 - 1)
                _, record, _ = self.paused(below, gaze)
                self.assertEqual(record.decision["transition"], "none", "one millisecond short of the table's pause")

    def test_the_raw_elapsed_time_alone_gives_no_pause(self):
        # Proposal 4.3: only the corrected value is used; no fallback to since_last_input_ms (nor dwell_ms).
        block = interaction_block(since_last_input_excluding_system_busy_ms=None, since_last_input_ms=9500)
        response, record, _ = self.paused(block)
        self.assertEqual((record.inputs["pause_s"], record.inputs["options_open"]), (None, True))
        self.assertEqual(record.decision["transition"], "none")
        self.assertEqual(response.json()["support"], PLACEHOLDER_SUPPORT)

    def test_while_the_user_speaks_the_pause_stays_unknown(self):
        # Proposal 4.3: listening time is not taken out of the corrected value, so the guard sets the pause None.
        for name, changes in (("listening", {"voice_phase": "listening"}),
                              ("microphone active", {"microphone_active": True})):
            with self.subTest(name):
                response, record, _ = self.paused(interaction_block(**changes))
                self.assertEqual((record.inputs["pause_s"], record.inputs["options_open"]), (None, True))
                self.assertEqual(record.decision["transition"], "none")
                self.assertEqual(response.json()["support"], PLACEHOLDER_SUPPORT)

    def test_a_corrected_value_with_the_microphone_off_gives_the_pause(self):
        # voice_busy is no guard: processing and speaking time are already out of the corrected value.
        for name, changes in (("voice idle", {}),
                              ("voice speaking", {"voice_phase": "speaking", "voice_speaking": True,
                                                  "voice_busy": True})):
            with self.subTest(name):
                _, record, _ = self.paused(interaction_block(microphone_active=False, **changes))
                self.assertEqual((record.inputs["pause_s"], record.decision["support"]),
                                 (PILOT_PARAMS.lost_pause_s, HIGHLIGHT))

    def test_a_malformed_block_is_not_read_and_the_window_is_still_answered(self):
        malformed = {
            "not an object": "oops", "a list": [1, 2], "no schema_version": {"options_open": True},
            "another schema": interaction_block(schema_version="touch-interaction-pilot-v2"),
            "options_open as text": interaction_block(options_open="yes"),
            "negative time": interaction_block(since_last_input_excluding_system_busy_ms=-5),
            "time as a boolean": interaction_block(since_last_input_excluding_system_busy_ms=True),
            "unknown voice phase": interaction_block(voice_phase="talking"),
            "microphone_active as text": interaction_block(microphone_active="no"),
        }
        for name, block in malformed.items():
            with self.subTest(name):
                response, record, _ = self.paused(block)
                self.assertEqual(response.status_code, 200)
                self.assertEqual((record.inputs["pause_s"], record.inputs["options_open"]), (None, None))

    def test_the_block_never_reaches_ai_engine(self):
        self.paused(interaction_block())
        self.assertEqual(set(self.ai_requests[-1]["touch"]), CONTRACT_TOUCH)


class PilotBlockOffTests(PilotBlockCase):
    def test_with_the_switch_off_the_same_block_changes_neither_the_record_nor_the_answer(self):
        response, record, _ = self.paused(interaction_block())
        self.assertEqual((record.inputs["pause_s"], record.inputs["options_open"]), (None, None))
        self.assertTrue(response.content.endswith(PLACEHOLDER_BYTES), response.content)
        self.assertEqual(set(self.ai_requests[-1]["touch"]), CONTRACT_TOUCH)
        _, without, _ = self.paused(None)
        self.assertEqual((record.inputs, record.decision), (without.inputs, without.decision),
                         "the same record as a window sent without the block")

    def test_with_the_switch_off_a_kept_highlight_still_answers_the_placeholder(self):
        session_id = self.new_session()
        first, _ = self.features(0, 2, session_id=session_id, backs=1, interaction=interaction_block(options_open=False))
        kept, record = self.features(2, 4, session_id=session_id, interaction=interaction_block(options_open=True))
        self.assertEqual(record.decision["transition"], "keep")
        for response in (first, kept):
            self.assertTrue(response.content.endswith(PLACEHOLDER_BYTES), response.content)


class KeptExecutionTests(FeaturesAppCase):
    """A kept support answers with the execution fields of the window being answered (review row 2)."""

    def settings(self):
        return Settings(_env_file=None, openai_api_key=None, decision_send_support=True)

    def test_a_kept_4_2_drops_its_target_while_the_options_sheet_is_closed_and_points_at_it_again(self):
        # Opened by a pause or a back on the options sheet; a pause or a back on the plain menu opens no 4-2.
        highlight = {"preset": "none", "requires_confirmation": False, "decided_by": "rule_placeholder",
                     "name": HIGHLIGHT, "decision_id": "d0001", "steps_left": 2}
        for name, opening in (("a pause", {"taps": 0}), ("a back", {"backs": 1})):
            with self.subTest(name):
                session_id = self.new_session()
                self.engine(2, "unknown", gaze=False, session_id=session_id)
                plain, _ = self.features(2, 4, session_id=session_id,
                                         interaction=interaction_block(options_open=False), **opening)
                self.assertEqual(plain.json()["support"], PLACEHOLDER_SUPPORT, "the plain menu: nothing chosen yet")
                self.engine(4, "unknown", gaze=False, session_id=session_id)
                opened, _ = self.features(4, 6, session_id=session_id,
                                          interaction=interaction_block(options_open=True), **opening)
                self.assertEqual(opened.json()["support"], {**highlight, "target_id": "cart-add"})
                answers = []
                for start, options_open in ((6, False), (8, True)):
                    self.engine(start + 2, "unknown", gaze=False, session_id=session_id)
                    response, record = self.features(start, start + 2, session_id=session_id, taps=0,
                                                     interaction=interaction_block(options_open=options_open))
                    self.assertEqual(record.decision["transition"], "keep")
                    answers.append(response.json()["support"])
                self.assertEqual(answers, [highlight, {**highlight, "target_id": "cart-add"}])

    def test_a_kept_notice_follows_the_screen_it_is_answered_on(self):
        # Opened on the review screen (1 step left); a back to the menu keeps it (a step forward would withdraw it).
        self.engine(2, QUEUE)
        self.assertEqual(self.features(2, 4, screen="review")[0].json()["support"]["steps_left"], 1)
        response, record = self.features(4, 6, screen="menu", backs=1)
        self.assertEqual((record.decision["transition"], record.decision["support"]), ("keep", NOTICE))
        self.assertEqual(response.json()["support"], {
            "preset": "step_guide", "requires_confirmation": False, "decided_by": "rule_placeholder",
            "name": NOTICE, "decision_id": "d0001", "steps_left": 2, "target_id": "cart_progress",
            "message_id": "steps_left_notice"})


class DecisionLogTests(FeaturesAppCase):
    """Under the switch, one INFO line per /features window (review row 9)."""

    LOGGER = "app.modules.sessions.service"

    def settings(self):
        return Settings(_env_file=None, openai_api_key=None, decision_send_support=True)

    def test_one_line_per_window_names_the_decision_and_the_engine_window_it_read(self):
        self.engine(2, QUEUE)
        with self.assertLogs(self.LOGGER, "INFO") as logs:
            self.features(2, 4)
            self.features(4, 6)        # the engine window ending at 2 s is at this one's bound: none read
        line = f"INFO:{self.LOGGER}:decision window session={self.session_id} window_end="
        self.assertEqual(logs.output, [
            line + "2026-11-25T10:00:04+00:00 transition=open support=remaining_steps_notice scene=3-1 "
                   "measurable=True engine_window_end=2026-11-25T10:00:02+00:00 "
                   "situation=looking_back_with_people_behind",
            line + "2026-11-25T10:00:06+00:00 transition=keep support=remaining_steps_notice scene=3-1 "
                   "measurable=True engine_window_end=None situation=None"])

    def test_the_switch_lets_the_line_reach_the_console(self):
        # uvicorn configures only its own loggers: the app adds one console handler to this logger, once.
        create_app(self.settings())
        logger = logging.getLogger(self.LOGGER)
        self.assertEqual(logger.level, logging.INFO)
        self.assertEqual(sum(getattr(h, "decision_lines", False) for h in logger.handlers), 1)


    def test_the_line_names_the_situations_window_when_it_is_not_the_latest(self):
        self.features(0, 2)
        self.engine(1, QUEUE)
        self.engine(2, "none")
        with self.assertLogs(self.LOGGER, "INFO") as logs:
            self.features(2, 4)
        (line,) = logs.output
        self.assertTrue(line.endswith("engine_window_end=2026-11-25T10:00:02+00:00 "
                                      "situation=looking_back_with_people_behind "
                                      "situation_window_end=2026-11-25T10:00:01+00:00"), line)


class SecondReadTests(FeaturesAppCase):
    """A tagged engine window lies in the bound of the touch window it ended in and of the next one, so it may be
    read twice; the rule table does not open a second support from it (review round 5)."""

    def settings(self):
        return Settings(_env_file=None, openai_api_key=None, decision_send_support=True)

    def test_3_1_and_3_2_open_once_and_keep_on_the_second_read(self):
        for scene, name, touch in (("3-1", QUEUE, {}), ("3-2", BUSY, {"taps": 0})):
            with self.subTest(scene):
                session_id = self.new_session()
                self.engine(3, name, session_id=session_id)
                first, opened = self.features(2, 4, session_id=session_id, **touch)
                self.engine(4, "none", session_id=session_id)
                second, kept = self.features(4, 6, session_id=session_id, **touch)
                self.assertEqual((opened.decision["transition"], opened.decision["scene"]), ("open", scene))
                self.assertEqual((kept.inputs["situation"]["name"], kept.decision["transition"]), (name, "keep"),
                                 "the same tagged window read again: kept, not opened twice")
                self.assertEqual(second.json()["support"]["decision_id"], first.json()["support"]["decision_id"])

    def test_looking_around_read_again_lowers_the_pause_bound_for_one_more_touch_window(self):
        # The second read keeps the tag current for the next touch window: a pause too short for 4-2 in the first
        # window (3 s < lost_pause_s_vision) opens it in the second (5 s), with the gaze away in both windows.
        session_id = self.new_session()
        self.engine(3, AROUND, gaze=False, session_id=session_id)
        _, first = self.features(2, 4, session_id=session_id, taps=0,
                                 interaction=interaction_block(since_last_input_excluding_system_busy_ms=3000))
        self.engine(4, "none", gaze=False, session_id=session_id)
        _, second = self.features(4, 6, session_id=session_id, taps=0,
                                  interaction=interaction_block(since_last_input_excluding_system_busy_ms=5000))
        self.assertEqual(first.decision["transition"], "none")
        self.assertEqual((second.inputs["situation"]["name"], second.decision["support"]), (AROUND, HIGHLIGHT))
        self.assertEqual(self.held(session_id).decision.cues["pause_min_s"], PILOT_PARAMS.lost_pause_s_vision)


class DecisionLogOffTests(FeaturesAppCase):
    def test_with_the_switch_off_no_line_is_logged(self):
        self.engine(2, QUEUE)
        with self.assertNoLogs("app.modules.sessions.service", "INFO"):
            self.features(2, 4)


class SwitchOnWithoutJevAnswerTests(unittest.TestCase):
    def test_the_rule_tables_result_stands_when_jev_gives_no_answer(self):
        async def ai_engine(request):
            payload = json.loads(request.content)
            return httpx.Response(200, json={"session_id": payload["session_id"], "measurable": True,
                                             "states": SCORES, "model_version": "dummy-0.1"})

        async def jev(request):
            return httpx.Response(529, json={"error": "overloaded"})

        settings = Settings(_env_file=None, openai_api_key=None, jev_api_key="jev-secret-value",
                            jev_stages="state_scores", decision_send_support=True)
        with patch("app.main.httpx.AsyncClient", side_effect=lambda **kw: RealAsyncClient(
                    base_url="http://ai-engine:8001", transport=httpx.MockTransport(ai_engine))), \
                patch("app.main.create_jev_http", lambda *args: RealAsyncClient(
                    base_url="https://api.typesafe.ai", transport=httpx.MockTransport(jev))), \
                TestClient(create_app(settings)) as client:
            session_id = client.post("/api/v1/sessions").json()["session_id"]
            body = client.post(f"/api/v1/sessions/{session_id}/features", json=touch_body(0, 2, backs=1)).json()
            repository = client.app.state.decision_repository
        self.assertEqual(body["support"]["name"], HIGHLIGHT)
        self.assertEqual([r.outcome for r in repository.records(session_id)], ["no_answer"], "Jev was asked")


if __name__ == "__main__":
    unittest.main()
