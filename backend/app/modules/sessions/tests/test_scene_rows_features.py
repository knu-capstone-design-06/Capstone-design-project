"""Scenes 1-1, 1-2, 2-1, 2-2 and 4-1 through real /features and engine bodies (DECISION_SEND_SUPPORT on and off)."""

import unittest
from unittest.mock import patch
from uuid import uuid4

from app.common.config.settings import Settings
from app.modules.decision.schemas import PILOT_PARAMS, STALE
from app.modules.decision.service import DecisionService
from app.modules.sessions.tests.test_vision_windows import (
    CONTRACT_TOUCH, PLACEHOLDER_BYTES, PLACEHOLDER_SUPPORT, FeaturesAppCase, at, engine_body, interaction_block,
    touch_body,
)

# The pilot block with no pause (no 4-2 by pause) and voice ordering off (interaction_block has it on).
PLAIN = {"since_last_input_excluding_system_busy_ms": None, "voice_enabled": False}


def signals(fixes=0, zooms=0, can_offer=True, **changes):
    """touch.scene_signals as the order screen sends it (schema touch-scene-signals-pilot-v1)."""
    return {"schema_version": "touch-scene-signals-pilot-v1", "near_miss_fix_count": fixes,
            "zoom_attempt_count": zooms, "can_offer": can_offer, **changes}


def asked(name, preset="none", steps_left=2, **fields):
    """The switch-on answer of an ask by the rule table, opened as the session's first decision."""
    return {"preset": preset, "requires_confirmation": True, "decided_by": "rule_placeholder", "name": name,
            "decision_id": "d0001", "steps_left": steps_left, **fields}


class SceneCase(FeaturesAppCase):
    """Engine windows that carry scene tags, and /features bodies with the pilot blocks."""

    def engine_tags(self, end_s, session_id=None, name="none", gaze=True, face_seen=True, change=None, **statuses):
        """An engine window with these scene tags; change = the frame of the main_user_changed event in the evidence
        of its user_changed tag (the engine's event id main_user_changed@<frame>)."""
        session_id = session_id or self.session_id
        body = engine_body(session_id, end_s, name, gaze, face_seen)

        def evidence(tag):
            return [] if tag != "user_changed" or change is None else [
                {"event_id": f"main_user_changed@{change}", "obs": obs, "value": value, "t": float(end_s)}
                for obs, value in (("track", 2), ("previous_track", 1))]

        body["observations"]["scene_tags"] = [{"name": tag, "status": status, "unknown_reason": None,
                                               "evidence": evidence(tag)} for tag, status in statuses.items()]
        response = self.client.post(f"/api/v1/sessions/{session_id}/vision-windows", json=body)
        self.assertEqual(response.status_code, 202)

    def window(self, start_s, end_s, session_id=None, signals=None, **touch):
        """(response, record) of one /features window; signals = its touch.scene_signals block."""
        session_id = session_id or self.session_id
        body = touch_body(start_s, end_s, **touch)
        if signals is not None:
            body["touch"]["scene_signals"] = signals
        response = self.client.post(f"/api/v1/sessions/{session_id}/features", json=body)
        self.assertEqual(response.status_code, 200)
        return response, self.repository.windows(session_id)[-1]

    def step(self, start_s, end_s, tags=None, session_id=None, **touch):
        """An engine window with these scene tags ending 1 s before end_s (in this touch window's bound), then the
        /features window start_s..end_s. (response, record)."""
        if tags is not None:
            self.engine_tags(end_s - 1, session_id=session_id, **tags)
        return self.window(start_s, end_s, session_id=session_id, **touch)

    def support(self, *args, **kwargs):
        return self.step(*args, **kwargs)[0].json()["support"]


class SwitchOn:
    def settings(self):
        return Settings(_env_file=None, openai_api_key=None, decision_send_support=True)


class SceneTagsOnTests(SwitchOn, SceneCase):
    def test_the_tags_of_both_engine_windows_in_the_bound_reach_the_input_line(self):
        self.window(0, 2)
        self.engine_tags(1, seated_height=True, user_changed=True)
        self.engine_tags(2, seated_height=False, user_changed=False, face_approach="unknown")
        _, record = self.window(2, 4)
        self.assertEqual(record.inputs["situation"]["tags"], [
            {"name": "seated_height", "status": True, "t": at(1).timestamp()},
            {"name": "face_approach", "status": "unknown", "t": None},
            {"name": "user_changed", "status": True, "t": at(1).timestamp()},
        ])
        self.assertEqual(record.vision_window["scene_tags"][0]["status"], False, "the record keeps the latest's own")


class SceneTagsOffTests(SceneCase):
    def test_with_the_switch_off_the_situation_carries_no_tags(self):
        self.window(0, 2)
        self.engine_tags(1, seated_height=True)
        _, record = self.window(2, 4)
        self.assertNotIn("tags", record.inputs["situation"])


class StartAsksOnTests(SwitchOn, SceneCase):
    """1-2 and 1-1 over HTTP: asked by name, preset none, after the session's first press."""

    def test_the_low_screen_ask_answers_its_name(self):
        self.assertEqual(self.support(0, 2, taps=0, tags={"seated_height": True}), PLACEHOLDER_SUPPORT,
                         "no press in the session yet")
        self.assertEqual(self.support(2, 4, tags={"seated_height": True}), asked("lower_screen"))

    def test_the_voice_ask_answers_its_name_on_the_menu(self):
        self.assertEqual(self.support(0, 2, screen="review", tags={"aid_use": True}), PLACEHOLDER_SUPPORT)
        self.assertEqual(self.support(2, 4, tags={"aid_use": True}), asked("voice_order"))

    def test_the_asks_wait_while_the_options_dialog_is_open(self):
        for name, tag in (("lower_screen", "seated_height"), ("voice_order", "aid_use")):
            with self.subTest(name):
                session_id = self.new_session()
                held_back = self.support(0, 2, session_id=session_id, tags={tag: True},
                                         interaction=interaction_block(options_open=True, **PLAIN))
                self.assertEqual(held_back, PLACEHOLDER_SUPPORT, "the press opened the options dialog")
                self.assertEqual(self.support(2, 4, session_id=session_id, taps=0, tags={tag: True},
                                              interaction=interaction_block(options_open=False, **PLAIN)),
                                 asked(name), "the window after it closes")

    def test_the_asks_wait_while_the_screen_cannot_show_an_ask(self):
        for name, tag in (("lower_screen", "seated_height"), ("voice_order", "aid_use")):
            with self.subTest(name):
                session_id = self.new_session()
                response, record = self.step(0, 2, session_id=session_id, tags={tag: True},
                                             signals=signals(can_offer=False))
                self.assertEqual((response.json()["support"], record.inputs["can_offer"]), (PLACEHOLDER_SUPPORT, False),
                                 "a sheet, a message or voice ordering keeps the screen from showing it")
                self.assertEqual(self.support(2, 4, session_id=session_id, taps=0, tags={tag: True},
                                              signals=signals(can_offer=True)), asked(name), "the window after it can")

    def test_a_lapsed_low_screen_ask_is_not_asked_again_after_menu_review_menu(self):
        tags = {"seated_height": True}
        self.assertEqual(self.support(0, 2, tags=tags)["name"], "lower_screen")
        end = 2 + PILOT_PARAMS.no_response_s
        answers = [self.support(end - 2, end, tags=tags), self.support(end, end + 2, screen="review", tags=tags),
                   self.support(end + 2, end + 4, tags=tags)]
        self.assertEqual(answers, [PLACEHOLDER_SUPPORT] * 3)
        self.assertEqual(self.repository.windows(self.session_id)[1].timed_out, "d0001")


class PressSpanOnTests(SwitchOn, SceneCase):
    """Under the switch a press is read over the window's pairing span, the span of the engine windows it reads: a
    window without a press or a face is measurable when an earlier touch window with a press ended inside that span
    (review round 2 row 1). The rows still read this window's own presses."""

    def test_a_cue_that_first_reaches_the_window_after_the_press_opens_the_voice_ask(self):
        # A press at 10.2 s in the touch window (10, 11]; aid_use true first in an engine segment ending 11.5 s, which
        # the touch window (11, 12] reads; that window holds no press, and no engine window saw a face.
        _, pressed = self.window(10, 11)
        self.assertEqual((pressed.inputs["measurable"], pressed.decision["transition"]), (True, "none"), "no tag yet")
        self.engine_tags(11.5, face_seen=False, aid_use=True)
        response, record = self.window(11, 12, taps=0)
        self.assertEqual((record.inputs["measurable"], record.inputs["taps_segment"]), (True, 0))
        self.assertEqual(response.json()["support"], asked("voice_order"))

    def test_a_press_window_that_ended_at_the_spans_lower_bound_does_not_count(self):
        # The touch window (11, 12] was skipped: (12, 13] reads back to 11 s, where the press window ended.
        self.window(10, 11)
        self.engine_tags(12.5, face_seen=False, aid_use=True)
        response, record = self.window(12, 13, taps=0)
        self.assertEqual((record.inputs["measurable"], record.decision["transition"]), (False, "none"))
        self.assertEqual(response.json()["support"], PLACEHOLDER_SUPPORT)

    def test_the_request_that_confirms_a_clock_move_does_not_borrow_a_press_of_the_timeline_before(self):
        # Review round 3 row 1: the frontend clock is set back by 2,000 s, so the two timelines overlap in time. The
        # window (1008, 1009] confirms the move; before it is placed, the old timeline's press window ending 1008.5 s
        # lies in its span (1007, 1009). Its pause would open 4-2 if that window were measurable.
        clock = {"now": 0.0}
        self.client.app.state.decision_service._now = lambda: clock["now"]   # the server time passed, moved here

        def send(start_s, end_s, passed=1.0, **touch):
            clock["now"] += passed
            return self.window(start_s, end_s, **touch)

        send(1007.5, 1008.5)                                          # a press on the timeline before
        send(3007.5, 3008.5, taps=0, passed=2000.0)
        send(1006, 1007, taps=0)                                      # off that timeline: recorded only
        paused = interaction_block(since_last_input_excluding_system_busy_ms=PILOT_PARAMS.lost_pause_s * 1000)
        response, record = send(1008, 1009, taps=0, interaction=paused)   # follows it: the new epoch starts here
        self.assertEqual((record.epoch, record.jev == STALE, record.inputs["pause_s"]),
                         (1, False, PILOT_PARAMS.lost_pause_s))
        self.assertEqual((record.inputs["measurable"], record.decision["transition"]), (False, "none"))
        self.assertEqual(response.json()["support"], PLACEHOLDER_SUPPORT)


class PressSpanOffTests(SceneCase):
    def test_with_the_switch_off_an_earlier_press_is_not_read(self):
        with patch.object(DecisionService, "pressed_before") as lookup:
            self.window(10, 11)
            self.engine_tags(11.5, face_seen=False, aid_use=True)
            response, record = self.window(11, 12, taps=0)
        lookup.assert_not_called()
        self.assertTrue(response.content.endswith(PLACEHOLDER_BYTES), response.content)
        self.assertEqual((record.ai, record.inputs["measurable"], record.decision["transition"]),
                         ("unmeasurable", False, "none"))


class WheelchairOnTests(SwitchOn, SceneCase):
    """A wheelchair behind aid_use also opens 1-2; any other class opens 1-1 (the engine's head-centre reading)."""

    def aid_window(self, end_s, cls, seated):
        body = engine_body(self.session_id, end_s, "none")
        body["observations"]["scene_tags"] = [
            {"name": "seated_height", "status": seated, "unknown_reason": None, "evidence": []},
            {"name": "aid_use", "status": True, "unknown_reason": None, "evidence": [
                {"event_id": f"aid_head@{end_s}", "obs": "aid_head_median", "value": 0.8, "t": float(end_s)},
                {"event_id": f"aid_head@{end_s}", "obs": "rows", "value": 5, "t": float(end_s)},
                {"event_id": f"aid_head@{end_s}", "obs": "aid_class", "value": cls, "t": float(end_s)}]}]
        self.assertEqual(self.client.post(f"/api/v1/sessions/{self.session_id}/vision-windows", json=body).status_code,
                         202)

    def test_a_wheelchair_asks_the_low_screen_and_a_crutch_asks_voice_ordering(self):
        for cls, seated, name in (("wheelchair", False, "lower_screen"), ("wheelchair", "unknown", "lower_screen"),
                                  ("crutch", False, "voice_order")):
            with self.subTest(cls=cls, seated=seated):
                self.session_id = self.new_session()
                self.aid_window(1, cls, seated)
                response, record = self.window(0, 2)
                self.assertEqual(response.json()["support"], asked(name))
                aid = next(t for t in record.inputs["situation"]["tags"] if t["name"] == "aid_use")
                self.assertEqual(aid, {"name": "aid_use", "status": True, "t": at(1).timestamp(), "aid_class": cls})


class NewCustomerOnTests(SwitchOn, SceneCase):
    """2-2 over HTTP: the engine's user_changed window, the session's own cart, the next press."""

    def add_to_cart(self, version=0):
        response = self.client.post(f"/api/v1/sessions/{self.session_id}/cart/items", json={
            "product_id": "americano", "temperature": "iced", "quantity": 1, "expected_version": version,
        }, headers={"Idempotency-Key": str(uuid4())})
        self.assertEqual(response.status_code, 200)

    def test_a_change_in_a_stretch_that_is_not_measurable_opens_the_question_at_the_next_press_once(self):
        # The first press; the touch window (0, 2] after it was skipped, so the press window ended at the lower bound of
        # the quiet window's pairing span (0, 4], not inside it: that stretch has no press and no face.
        self.window(-2, 0)
        self.add_to_cart()
        self.engine_tags(2, face_seen=False)                              # the engine segment before, delivered
        self.engine_tags(3, face_seen=False, change=40, user_changed=True)   # the next customer, no face in the window
        _, quiet = self.window(2, 4, taps=0)
        self.assertEqual((quiet.inputs["measurable"], quiet.decision["transition"]), (False, "none"))
        self.engine_tags(4, change=40, user_changed=True)                 # the same change in the next engine window
        response, record = self.window(4, 6)
        self.assertEqual(response.json()["support"], asked("continue_or_new_order"))
        self.assertEqual(record.inputs["cart_items"], 1)
        end = 6 + PILOT_PARAMS.no_response_s
        later = []
        for s in range(6, int(end) + 4, 2):
            if s == 6:
                self.engine_tags(6, change=40, user_changed=True)         # and once more, after the question
            later.append(self.window(s, s + 2)[0].json()["support"])
        self.assertEqual([s.get("decision_id") for s in later[:4]], ["d0001"] * 4, "held until it lapses")
        self.assertEqual(later[-2:], [PLACEHOLDER_SUPPORT] * 2, "not asked again")

    def test_with_an_empty_cart_the_first_press_uses_the_event_up(self):
        self.window(0, 2)
        self.engine_tags(2)                                               # the engine segment before, delivered
        self.engine_tags(3, change=40, user_changed=True)
        self.assertEqual(self.window(2, 4)[0].json()["support"], PLACEHOLDER_SUPPORT)
        self.add_to_cart()
        _, record = self.window(4, 6)
        self.assertEqual((record.inputs["cart_items"], record.decision["transition"]), (1, "none"))

    def test_a_change_before_the_first_press_does_not_count_nor_its_later_windows(self):
        self.engine_tags(1, change=40, user_changed=True)                 # before any /features window: no state yet
        self.window(0, 2, taps=0)
        self.engine_tags(2)                                               # the engine window before, delivered
        self.engine_tags(3, change=90, user_changed=True)                 # a state without a press yet
        self.add_to_cart()
        _, first = self.window(2, 4)                                      # the first press
        for end_s in (4, 5):                                              # both changes again in later windows
            self.engine_tags(end_s, change=40, user_changed=True)
            self.engine_tags(end_s, change=90, user_changed=True)
        _, next_press = self.window(4, 6)
        self.assertEqual([first.decision["transition"], next_press.decision["transition"]], ["none", "none"])

    def test_a_change_inside_the_newcomers_first_press_window_opens_no_question(self):
        self.engine_tags(1)                                               # the engine segment (0, 1], delivered
        self.window(0, 2)                                                 # his first press, touch window (0, 2]
        self.engine_tags(2, change=40, user_changed=True)                 # segment (1, 2], posted after that window
        self.engine_tags(3, change=40, user_changed=True)                 # the same change in the next window
        self.add_to_cart()                                                # his own item
        _, record = self.window(2, 4)
        self.assertEqual((record.inputs["cart_items"], record.decision["transition"]), (1, "none"))

    def test_a_change_brought_after_a_lost_engine_window_opens_no_question(self):
        self.engine_tags(1)                                               # the engine segment (0, 1], delivered
        self.window(0, 2)                                                 # his first press; the segment (1, 2] is lost
        self.engine_tags(3, change=40, user_changed=True)                 # (2, 3] is the first to bring the id
        self.add_to_cart()
        _, record = self.window(2, 4)
        self.assertEqual((record.inputs["cart_items"], record.decision["transition"]), (1, "none"))

    def test_each_engine_window_with_new_ids_logs_whether_they_became_events_or_why_not(self):
        log = "app.modules.sessions.service"
        other = self.new_session()
        with self.assertLogs(log, level="INFO") as caught:
            self.window(0, 2, session_id=other)                           # a first press, then the session's first
            self.engine_tags(3, session_id=other, change=10, user_changed=True)   # engine window
            self.engine_tags(1)
            self.window(0, 2, taps=0)
            self.engine_tags(2, change=20, user_changed=True)             # before the first press
            self.window(2, 4)                                             # the first press: window (2, 4]
            self.engine_tags(3, change=30, user_changed=True)             # previous window ended at 2, before 4
            self.engine_tags(4)
            self.engine_tags(5, change=40, user_changed=True)             # previous window ended at 4: an event
            self.engine_tags(6, change=40, user_changed=True)             # the same id again: no line
        lines = [record.getMessage() for record in caught.records if record.getMessage().startswith("new customer event")]
        self.assertEqual([line.split(" ids=")[1] for line in lines], [
            "main_user_changed@10 remembered only: no previous engine window",
            "main_user_changed@20 remembered only: no first press yet",
            "main_user_changed@30 remembered only: the previous engine window ended before the first-press window's end",
            "main_user_changed@40 pending"])
        self.assertEqual([f"session={other}" in lines[0]] + [f"session={self.session_id}" in line for line in lines[1:]],
                         [True] * 4)

    def test_a_true_user_changed_without_the_engines_event_id_opens_nothing(self):
        self.window(0, 2)
        self.add_to_cart()
        self.engine_tags(3, user_changed=True)
        _, record = self.window(2, 4)
        self.assertEqual((record.inputs["cart_items"], record.decision["transition"]), (1, "none"))


class NewCustomerOffTests(SceneCase):
    def test_with_the_switch_off_no_new_customer_line_is_logged(self):
        with self.assertNoLogs("app.modules.sessions.service", level="INFO"):
            self.window(0, 2)
            self.engine_tags(2)
            self.engine_tags(3, change=40, user_changed=True)


class SceneSignalsOnTests(SwitchOn, SceneCase):
    """touch.scene_signals: this window's counts, summed over the session's windows in touch_span_s."""

    def test_near_miss_fixes_summed_over_the_span_open_4_1_while_facing_the_screen(self):
        self.engine_tags(1)                                            # gaze true: facing the screen
        _, first = self.window(0, 2, signals=signals(fixes=1))
        self.engine_tags(3)
        response, second = self.window(2, 4, signals=signals(fixes=1))
        self.assertEqual((first.inputs["fixes_recent"], second.inputs["fixes_recent"]), (1, 2))
        self.assertEqual(PILOT_PARAMS.tremor_miss_min, 2)
        self.assertEqual(response.json()["support"], asked("large_button", preset="large_button"))

    def test_a_window_counts_while_its_end_lies_in_the_span(self):
        sums = [self.window(s, s + 2, signals=signals(fixes=1 if s == 0 else 0))[1].inputs["fixes_recent"]
                for s in (0, 2, 4, 6)]
        self.assertEqual(PILOT_PARAMS.touch_span_s, 5.0)
        self.assertEqual(sums, [1, 1, 1, 0], "the window ending at 2 s is out of the span at 8 s")

    def test_a_window_of_the_span_without_the_count_makes_the_sum_unknown(self):
        cases = {"no block": None, "null count": signals(fixes=None)}
        for name, block in cases.items():
            with self.subTest(name):
                session_id = self.new_session()
                self.window(0, 2, session_id=session_id, signals=block)
                _, record = self.window(2, 4, session_id=session_id, signals=signals(fixes=2))
                self.assertEqual((record.inputs["fixes_segment"], record.inputs["fixes_recent"]), (2, None))
                self.assertEqual(record.decision["transition"], "none")

    def test_a_zoom_attempt_in_the_span_sets_zoom_attempt(self):
        _, first = self.window(0, 2, signals=signals(zooms=1))
        _, second = self.window(2, 4, signals=signals())
        _, third = self.window(4, 6, signals=signals())
        _, fourth = self.window(6, 8, signals=signals())
        self.assertEqual([r.inputs["zoom_attempt"] for r in (first, second, third, fourth)], [True, True, True, False])

    def test_a_block_of_another_version_or_a_malformed_one_is_not_read(self):
        blocks = {
            "another version": signals(fixes=2, schema_version="touch-scene-signals-pilot-v2"),
            "not an object": "oops", "a count as text": signals(fixes="2"), "a negative count": signals(fixes=-1),
            "a boolean count": signals(fixes=True), "a float count": signals(fixes=2.0),
            "a key left out": {"schema_version": "touch-scene-signals-pilot-v1", "near_miss_fix_count": 2,
                               "can_offer": True},
            "the ask gate left out": {"schema_version": "touch-scene-signals-pilot-v1", "near_miss_fix_count": 2,
                                      "zoom_attempt_count": 0},
            "the ask gate as a number": signals(fixes=2, can_offer=1), "the ask gate as text": signals(can_offer="true"),
        }
        for name, block in blocks.items():
            with self.subTest(name):
                _, record = self.window(0, 2, session_id=self.new_session(), signals=block)
                self.assertEqual((record.inputs["fixes_segment"], record.inputs["zoom_attempts_segment"],
                                  record.inputs["fixes_recent"], record.inputs["zoom_attempt"],
                                  record.inputs["can_offer"]), (None, None, None, None, None))

    def test_the_block_never_reaches_ai_engine(self):
        self.window(0, 2, signals=signals(fixes=1, zooms=1))
        self.assertEqual(set(self.ai_requests[-1]["touch"]), CONTRACT_TOUCH)


class LowVisionOnTests(SwitchOn, SceneCase):
    """2-1 over HTTP: the 크게 보기 ask (code name large_text) and the help ring."""

    def test_a_double_tap_on_text_opens_the_large_view_ask(self):
        response, _ = self.window(0, 2, signals=signals(zooms=1))
        self.assertEqual(response.json()["support"], asked("large_text", preset="large_text"))

    def test_a_face_approach_rings_the_help_entry_and_a_kept_ring_keeps_its_target(self):
        ring = {"preset": "none", "requires_confirmation": False, "decided_by": "rule_placeholder",
                "name": "highlight_large_view_help", "decision_id": "d0001", "steps_left": 2, "target_id": "support-toggle"}
        self.assertEqual(self.support(0, 2, tags={"face_approach": True}), ring)
        kept, record = self.step(2, 4, tags={"face_approach": True})
        self.assertEqual((record.decision["transition"], kept.json()["support"]), ("keep", ring))


def settings_block(voice=False, options_open=False, **ui):
    """touch.interaction with these ui_settings on (the rest off), voice ordering as given, no pause."""
    block = interaction_block(options_open=options_open, **{**PLAIN, "voice_enabled": voice})
    return {**block, "ui_settings": {**block["ui_settings"], **ui}}


class SettingsOnTests(SwitchOn, SceneCase):
    """A setting the customer already has on counts as active: its row stays closed."""

    def test_a_setting_that_is_on_keeps_its_row_closed(self):
        cases = {   # name: (scene tags, scene signals, the setting that is on, the row it closes)
            "low screen": ({"seated_height": True}, None, {"low_screen": True}, "lower_screen"),
            "voice ordering": ({"aid_use": True}, None, {"voice": True}, "voice_order"),
            "large text, zoom": (None, signals(zooms=1), {"large_text": True}, "large_text"),
            "large buttons, zoom": (None, signals(zooms=1), {"large_button": True}, "large_text"),
            "large text, ring": ({"face_approach": True}, None, {"large_text": True}, "highlight_large_view_help"),
        }
        for name, (tags, block, setting, row) in cases.items():
            with self.subTest(name):
                session_id = self.new_session()
                response, record = self.step(0, 2, session_id=session_id, tags=tags, signals=block,
                                             interaction=settings_block(**setting))
                self.assertEqual(response.json()["support"], PLACEHOLDER_SUPPORT, row)
                self.assertTrue(record.inputs["supports_on"])
                other = self.new_session()
                _, opened = self.step(0, 2, session_id=other, tags=tags, signals=block, interaction=settings_block())
                self.assertEqual((opened.inputs["supports_on"], opened.decision["support"]), ((), row),
                                 "the same window with the setting off")

    def test_large_buttons_on_close_the_4_1_ask_too(self):
        for setting in ({"large_button": True}, {"large_text": True}):
            with self.subTest(setting):
                session_id = self.new_session()
                self.engine_tags(1, session_id=session_id)
                self.window(0, 2, session_id=session_id, signals=signals(fixes=1), interaction=settings_block(**setting))
                self.engine_tags(3, session_id=session_id)
                _, record = self.window(2, 4, session_id=session_id, signals=signals(fixes=1),
                                        interaction=settings_block(**setting))
                self.assertEqual((record.inputs["fixes_recent"], record.decision["transition"]), (2, "none"))

    def test_the_settings_map_to_the_rule_table_names_and_a_malformed_part_is_read_apart(self):
        _, record = self.window(0, 2, interaction=settings_block(voice=True, low_screen=True, large_text=True,
                                                                  large_button=True))
        self.assertEqual(record.inputs["supports_on"], ("large_text", "large_button", "lower_screen", "voice_order"))
        bad = {**settings_block(options_open=True), "ui_settings": {"low_screen": "yes"}}
        _, record = self.window(2, 4, interaction=bad)
        self.assertEqual((record.inputs["supports_on"], record.inputs["options_open"]), (None, True),
                         "settings not known; the options dialog still read")
        _, record = self.window(4, 6)
        self.assertIsNone(record.inputs["supports_on"], "no block: not known")


class SceneSignalsOffTests(SceneCase):
    def test_with_the_switch_off_a_body_with_the_block_is_accepted_and_not_read(self):
        self.engine_tags(1)
        self.window(0, 2, signals=signals(fixes=1))
        self.engine_tags(3)
        response, record = self.window(2, 4, signals=signals(fixes=1))
        self.assertTrue(response.content.endswith(PLACEHOLDER_BYTES), response.content)
        self.assertEqual((record.inputs["fixes_segment"], record.inputs["fixes_recent"], record.inputs["can_offer"],
                          record.decision["transition"]), (None, None, None, "none"))
        self.assertEqual(set(self.ai_requests[-1]["touch"]), CONTRACT_TOUCH)


class StartAsksOffTests(SceneCase):
    def test_with_the_switch_off_the_answers_stay_byte_for_byte_the_placeholder(self):
        for tags in ({"seated_height": True}, {"aid_use": True}, {"face_approach": True}):
            with self.subTest(tags):
                session_id = self.new_session()
                response, record = self.step(0, 2, session_id=session_id, tags=tags)
                self.assertTrue(response.content.endswith(PLACEHOLDER_BYTES), response.content)
                self.assertEqual(record.decision["transition"], "none", "without the switch the tags are not read")

    def test_with_the_switch_off_a_zoom_attempt_leaves_the_placeholder(self):
        response, record = self.window(0, 2, signals=signals(zooms=1))
        self.assertTrue(response.content.endswith(PLACEHOLDER_BYTES), response.content)
        self.assertEqual((record.inputs["zoom_attempt"], record.decision["transition"]), (None, "none"))


if __name__ == "__main__":
    unittest.main()
