"""The rows of scenes 1-1, 1-2, 2-1 and 2-2 and the scene tags they read (rule table, decision service)."""

import unittest
from datetime import datetime, timedelta, timezone

from app.modules.decision.repository import RETENTION, DecisionRepository
from app.modules.decision.rule_table import apply, decide, scene_tag, tick
from app.modules.decision.schemas import (
    AID_USE, APPROACH, BIG, CHANGED, HIGHLIGHT, LARGE_TEXT, LARGE_VIEW, LOWER, NO_FIRST_PRESS, NO_PREVIOUS_WINDOW,
    NOT_AFTER_PREVIOUS, PILOT_PARAMS, PREVIOUS_BEFORE_PRESS, SEATED, SWAP, UNKNOWN, VOICE, ChangeNote, PairedVision,
    SessionState, VisionWindow, WindowInput,
)
from app.modules.decision.service import DecisionService, recent_signals
from app.modules.sessions.schemas import FeatureWindowRequest, VisionWindowRequest

T0 = datetime(2026, 11, 26, 10, 0, tzinfo=timezone.utc)
P = PILOT_PARAMS
STEPS = {"menu": 2, "review": 1}


def at(seconds):
    return T0 + timedelta(seconds=seconds)


def line(t, taps=1, screen="menu", tags=None, aid_class=None, **fields):
    """One measurable input line on a screen of the flow; tags = {scene tag: status} in the situation's `tags`, the
    aid_use item with aid_class as PairedVision.scene_tag_states gives it."""
    def item(name, status):
        state = {"name": name, "status": status, "t": t if status is True else None}
        return {**state, "aid_class": aid_class} if name == AID_USE else state

    situation = None if tags is None else {
        "name": "none", "evidence": [], "confidence": "unknown",
        "tags": [item(name, status) for name, status in tags.items()]}
    return WindowInput(t=t, measurable=True, situation=situation, screen=screen, steps_left=STEPS[screen],
                       taps_segment=taps, **fields)


def play(state, *inputs):
    """tick, decide and apply window by window, as the service does; (state, decisions)."""
    decisions = []
    for inp in inputs:
        state, _ = tick(state, inp.t, P)
        state, decision = apply(state, decide(inp, state, P))
        decisions.append(decision)
    return state, decisions


def opened(decision):
    return decision.support if decision.transition in ("open", "replace") else None


def engine(end_s, **statuses):
    """One engine window (1 s segment) ending end_s after T0 with the given scene tag statuses."""
    tags = [{"name": name, "status": status, "unknown_reason": None, "evidence": []} for name, status in statuses.items()]
    return VisionWindow("s1", at(end_s - 1), at(end_s), {"name": "none", "evidence": [], "confidence": "unknown"},
                        True, True, tags, "test", at(end_s))


def paired(*windows):
    latest = max(windows, key=lambda w: w.window_end)
    return PairedVision(latest, latest, tuple(reversed(windows)))


def states(*windows):
    return {item["name"]: (item["status"], item["t"]) for item in paired(*windows).scene_tag_states()}


class SceneTagStatesTests(unittest.TestCase):
    """Inside the pairing bound a tag is true when any window says true, false when the latest says false, else unknown."""

    def test_a_tag_true_only_in_the_earlier_window_of_the_pair_still_counts(self):
        self.assertEqual(states(engine(3, user_changed=True), engine(4, user_changed=False))[CHANGED],
                         (True, at(3).timestamp()))

    def test_the_freshest_true_window_gives_the_time(self):
        self.assertEqual(states(engine(3, seated_height=True), engine(4, seated_height=True))[SEATED],
                         (True, at(4).timestamp()))

    def test_false_needs_the_latest_window_to_say_false(self):
        self.assertEqual(states(engine(3, aid_use=UNKNOWN), engine(4, aid_use=False))[AID_USE], (False, None))
        self.assertEqual(states(engine(3, aid_use=False), engine(4, aid_use=UNKNOWN))[AID_USE], (UNKNOWN, None))
        self.assertEqual(states(engine(3, aid_use=False), engine(4))[AID_USE], (UNKNOWN, None),
                         "the latest window does not carry it")

    def test_only_the_four_names_the_table_reads_and_only_those_carried(self):
        self.assertEqual(set(states(engine(4, face_approach=True, phone_use=True))), {APPROACH})

    def test_the_aid_class_comes_from_the_window_that_gave_aid_use_its_true_status(self):
        def aid(end_s, status, cls=None):
            window = engine(end_s, aid_use=status)
            if cls is not None:
                window.scene_tags[0]["evidence"] = [
                    {"event_id": f"aid_head@{end_s}", "obs": "aid_head_median", "value": 0.8, "t": float(end_s)},
                    {"event_id": f"aid_head@{end_s}", "obs": "aid_class", "value": cls, "t": float(end_s)}]
            return window

        def read(*windows):
            return next(i for i in paired(*windows).scene_tag_states() if i["name"] == AID_USE)

        self.assertEqual(read(aid(3, True, "wheelchair"), aid(4, False, "crutch"))["aid_class"], "wheelchair")
        self.assertEqual(read(aid(3, True, "cane"), aid(4, True, "wheelchair"))["aid_class"], "wheelchair",
                         "the freshest true window")
        older = engine(4, aid_use=True)
        older.scene_tags[0]["evidence"] = [{"event_id": "aid_score@4", "obs": "aid_any_median", "value": 0.6, "t": 4.0}]
        self.assertEqual(read(older)["aid_class"], None, "the older reading names no class")
        self.assertEqual(read(aid(4, False, "wheelchair"))["aid_class"], None, "not true: no class")

    def test_without_the_list_of_windows_the_latest_alone_is_read(self):
        latest = engine(4, seated_height=True)
        self.assertEqual(PairedVision(latest, latest).scene_tag_states(),
                         [{"name": SEATED, "status": True, "t": at(4).timestamp()}])


class SceneTagReaderTests(unittest.TestCase):
    def test_only_a_boolean_status_is_read(self):
        def inp(tags):
            return WindowInput(t=0.0, measurable=True, situation={"name": "none", "tags": tags})

        self.assertIs(scene_tag(inp([{"name": SEATED, "status": True, "t": 1.0}]), SEATED), True)
        self.assertIs(scene_tag(inp([{"name": SEATED, "status": False, "t": None}]), SEATED), False)
        self.assertIsNone(scene_tag(inp([{"name": SEATED, "status": UNKNOWN, "t": None}]), SEATED))
        self.assertIsNone(scene_tag(inp([]), SEATED), "absent")
        self.assertIsNone(scene_tag(WindowInput(t=0.0, measurable=True, situation={"name": "none"}), SEATED),
                          "no tags: the switch is off")
        self.assertIsNone(scene_tag(WindowInput(t=0.0, measurable=True), SEATED), "not judged")


def touch_window(start_s, end_s, taps=1, screen="menu"):
    return FeatureWindowRequest.model_validate({
        "screen_id": screen, "window_start": at(start_s).isoformat(), "window_end": at(end_s).isoformat(),
        "touch": {"tap_count": taps, "miss_tap_count": 0, "repeat_tap_count": 0, "back_count": 0, "dwell_ms": 1000}})


def engine_post(end_s, change=None, **statuses):
    """One engine body ending end_s after T0; change = the frame of the main_user_changed event behind its
    user_changed tag (the tag's evidence, one item per observation as the vision chain gives it)."""
    def evidence(name):
        if name != CHANGED or change is None:
            return []
        return [{"event_id": f"main_user_changed@{change}", "obs": obs, "value": value, "t": float(end_s)}
                for obs, value in (("track", 2), ("previous_track", 1), ("previous_settled", True))]

    return VisionWindowRequest.model_validate({
        "window_start": at(end_s - 1).isoformat(), "window_end": at(end_s).isoformat(),
        "situation": {"name": "none", "evidence": [], "confidence": "unknown"},
        "observations": {"gaze": True, "face_seen": True, "scene_tags": [
            {"name": name, "status": status, "evidence": evidence(name)} for name, status in statuses.items()]},
        "model_version": "test"})


A, B = "main_user_changed@40", "main_user_changed@90"   # two changes of customer (the frame each new track starts)


class NewCustomerEventTests(unittest.TestCase):
    """2-2's events: the engine's event ids behind a true user_changed, kept when the engine window ARRIVES. Every id
    is remembered; only an id first received after the session's first press is an event; the next press uses it."""

    def setUp(self):
        self.now = [T0]
        self.repository = DecisionRepository(clock=lambda: self.now[0])
        self.service = DecisionService(self.repository, PILOT_PARAMS, None, stages=())

    def state(self):
        return self.repository.state("s1")

    def press(self, start_s, end_s, cart=None):
        """A /features window with a press; cart = the session cart's items as the session service reads them."""
        return self.service.observe("s1", touch_window(start_s, end_s), measurable=True, cart_items=cart)

    def test_an_event_before_the_first_press_does_not_count(self):
        self.service.observe("s1", touch_window(0, 2, taps=0), measurable=True)
        self.service.add_vision("s1", engine_post(1))                                # the window before, delivered
        noted = self.service.add_vision("s1", engine_post(2, change=40, user_changed=True))
        self.assertEqual(noted, ChangeNote((A,), NO_FIRST_PRESS))
        state = self.state()
        self.assertEqual((state.first_press, state.user_changed_seen, state.user_changed_pending), (False, [A], []))

    def test_after_the_first_press_the_event_waits_for_the_next_press_and_is_used_by_it(self):
        self.press(0, 2)
        self.assertTrue(self.state().first_press)
        self.service.add_vision("s1", engine_post(2))                                # the segment before, delivered
        self.service.add_vision("s1", engine_post(3, change=40, user_changed=True))
        self.service.add_vision("s1", engine_post(4, user_changed=False))
        self.assertEqual(self.state().user_changed_pending, [A], "kept on arrival, a later false aside")
        self.service.observe("s1", touch_window(2, 4, taps=0), measurable=False)
        self.assertEqual(self.state().user_changed_pending, [A], "a window without a press keeps it")
        self.press(4, 6)
        self.assertEqual(self.state().user_changed_pending, [], "the first press after it uses it, row or not")

    def test_one_change_true_in_three_windows_around_the_first_press_is_no_event(self):
        # The situation window (3 s) moves by 1 s: one change is true in about three windows, with the same event id.
        self.service.add_vision("s1", engine_post(1, change=40, user_changed=True))   # before any /features window
        self.press(0, 2)                                                            # the newcomer's first press
        for end_s in (2, 3):                                                        # the same change, later windows
            self.service.add_vision("s1", engine_post(end_s, change=40, user_changed=True))
        self.assertEqual((self.state().user_changed_seen, self.state().user_changed_pending), ([A], []))
        self.assertEqual(self.press(2, 4, cart=1).transition, "none", "his own item in the cart: no 2-2 for him")

    def test_an_answered_question_is_not_opened_again_by_the_later_windows_of_its_change(self):
        self.press(0, 2)
        self.service.add_vision("s1", engine_post(2))                                # the segment before, delivered
        self.service.add_vision("s1", engine_post(3, change=40, user_changed=True))
        asked = self.press(2, 4, cart=1)
        self.assertEqual((asked.transition, asked.support, asked.scope), ("open", SWAP, ("swap", A)))
        for end_s in (4, 5):                                                        # the same change, later windows
            self.service.add_vision("s1", engine_post(end_s, change=40, user_changed=True))
        self.assertEqual(self.state().user_changed_pending, [], "the same id is no new event")
        self.assertEqual(self.press(4, 6, cart=1).transition, "keep", "the customer answers on the dialog")
        lapse = 4 + P.no_response_s
        after = [self.press(s, s + 2, cart=1) for s in (lapse, lapse + 2)]
        self.assertEqual([d.transition for d in after], ["none", "none"], "no second dialog after the ask lapsed")

    def test_two_changes_after_the_first_press_are_two_events(self):
        self.press(0, 2)
        self.service.add_vision("s1", engine_post(2))                                # the segment before, delivered
        self.service.add_vision("s1", engine_post(3, change=40, user_changed=True))
        first = self.press(2, 4, cart=1)
        lapse = 4 + P.no_response_s
        self.assertEqual(self.press(lapse, lapse + 2, cart=1).transition, "none", "the first ask lapsed")
        self.service.add_vision("s1", engine_post(lapse + 2))                        # the segment before, delivered
        self.service.add_vision("s1", engine_post(lapse + 3, change=90, user_changed=True))
        second = self.press(lapse + 2, lapse + 4, cart=1)
        self.assertEqual([(d.transition, d.support, d.scope) for d in (first, second)],
                         [("open", SWAP, ("swap", A)), ("open", SWAP, ("swap", B))])

    def test_two_events_before_one_press_are_both_used_by_it(self):
        self.press(0, 2)
        self.service.add_vision("s1", engine_post(2))                                # the segment before, delivered
        self.service.add_vision("s1", engine_post(3, change=40, user_changed=True))
        self.service.add_vision("s1", engine_post(4, change=90, user_changed=True))
        self.assertEqual(self.state().user_changed_pending, [A, B], "in the order they arrived")
        asked = self.press(4, 6, cart=1)
        self.assertEqual((asked.scope, asked.cues[CHANGED], self.state().user_changed_pending),
                         (("swap", B), [A, B], []), "one question; the scope names the id received last")

    def test_a_change_inside_the_first_press_window_posted_after_it_was_judged_is_no_event(self):
        self.service.add_vision("s1", engine_post(1))                                # segment (0, 1], delivered
        self.press(0, 2)                                                            # the first press, window W = (0, 2]
        self.assertEqual(self.state().first_press_t, at(2).timestamp())
        self.service.add_vision("s1", engine_post(2, change=40, user_changed=True))   # segment (1, 2]: starts inside W
        self.assertEqual((self.state().user_changed_seen, self.state().user_changed_pending), ([A], []),
                         "remembered only: the change may have come before the press")
        self.service.add_vision("s1", engine_post(3, change=40, user_changed=True))   # the same id, a later window
        self.assertEqual(self.state().user_changed_pending, [], "a later window of a remembered id changes nothing")
        self.assertEqual(self.press(2, 4, cart=1).transition, "none", "no 2-2 over the newcomer's own cart")

    def test_a_change_in_a_window_starting_at_or_after_the_first_press_window_end_opens_2_2_once(self):
        for start_s in (2, 5):                                                      # exactly at W's end, and later
            with self.subTest(start_s=start_s):
                self.setUp()
                self.press(0, 2)
                self.service.add_vision("s1", engine_post(start_s))                  # the segment before, delivered
                self.service.add_vision("s1", engine_post(start_s + 1, change=40, user_changed=True))
                self.assertEqual(self.state().user_changed_pending, [A])
                end = start_s + 2
                decisions = [self.press(end, end + 2, cart=1), self.press(end + 2, end + 4, cart=1)]
                self.assertEqual([(d.transition, d.support) for d in decisions], [("open", SWAP), ("keep", SWAP)])

    def test_the_first_press_end_moves_with_the_order_screens_clock(self):
        from app.modules.decision.service import moved
        state = SessionState(first_press=True, first_press_t=2.0, tag_since=1.0)
        self.assertEqual((moved(state, 100.0).first_press_t, moved(state, 100.0).tag_since), (102.0, 101.0))

    def test_an_id_brought_by_a_window_after_a_lost_one_is_only_remembered(self):
        # The change at 1.5 s, inside the first-press window (0, 2]; the segment (1, 2] that held it is lost, so (2, 3]
        # is the first window the backend receives with the id: it starts at the first-press window's end, but a whole
        # segment is missing before it.
        self.service.add_vision("s1", engine_post(1))                                # segment (0, 1], delivered
        self.press(0, 2)
        noted = self.service.add_vision("s1", engine_post(3, change=40, user_changed=True))   # (2, 3]; (1, 2] lost
        self.assertEqual(noted, ChangeNote((A,), PREVIOUS_BEFORE_PRESS), "the previous window ended at 1, before 2")
        self.assertEqual((self.state().user_changed_seen, self.state().user_changed_pending), ([A], []))
        self.assertEqual(self.press(2, 4, cart=1).transition, "none", "no 2-2 over the newcomer's own cart")

    def test_an_id_after_a_delivered_window_without_it_is_an_event(self):
        self.service.add_vision("s1", engine_post(1))
        self.press(0, 2)
        self.service.add_vision("s1", engine_post(2, user_changed=False))           # (1, 2] delivered, no change in it
        self.service.add_vision("s1", engine_post(3, change=40, user_changed=True))   # (2, 3] brings the id
        self.assertEqual(self.state().user_changed_pending, [A])
        self.assertEqual(self.press(2, 4, cart=1).support, SWAP)

    def test_an_id_in_the_sessions_first_engine_window_is_only_remembered(self):
        self.press(0, 2)
        noted = self.service.add_vision("s1", engine_post(5, change=40, user_changed=True))   # no engine window before
        self.assertEqual(noted, ChangeNote((A,), NO_PREVIOUS_WINDOW))
        self.assertEqual((self.state().user_changed_seen, self.state().user_changed_pending), ([A], []))
        self.service.add_vision("s1", engine_post(6, change=40, user_changed=True))   # the same id, a following window
        self.assertEqual(self.state().user_changed_pending, [], "a remembered id stays remembered")

    def test_a_window_lost_after_the_first_press_window_does_not_hide_a_real_change(self):
        self.press(0, 2)                                                            # first press, window (0, 2]
        self.service.add_vision("s1", engine_post(2))                                # (1, 2] delivered: ends at 2
        noted = self.service.add_vision("s1", engine_post(4, change=40, user_changed=True))   # (2, 3] lost
        self.assertEqual(noted, ChangeNote((A,), None))
        self.assertEqual(self.state().user_changed_pending, [A])
        self.assertEqual(self.press(4, 6, cart=1).support, SWAP)

    def test_a_previous_window_ending_inside_the_first_press_window_keeps_a_later_id_remembered_only(self):
        self.service.add_vision("s1", engine_post(1))                                # (0, 1] delivered: ends at 1
        self.press(0, 2)                                                            # first press, window (0, 2]
        noted = self.service.add_vision("s1", engine_post(4, change=40, user_changed=True))   # (1, 2], (2, 3] lost
        self.assertEqual(noted, ChangeNote((A,), PREVIOUS_BEFORE_PRESS), "the change may lie inside (1, 2]")
        self.assertEqual(self.press(4, 6, cart=1).transition, "none")

    def test_the_boundary_is_the_previous_windows_end_at_or_after_the_first_press_end(self):
        # The runner's clock offset moves a few ms between releases: the previous window's end lies a few ms around the
        # whole second. 1.994 < 2.0: only remembered; 2.006 >= 2.0: pending; exactly 2.0: pending.
        for previous_end, reason in ((1.994, PREVIOUS_BEFORE_PRESS), (2.006, None), (2.0, None)):
            with self.subTest(previous_end=previous_end):
                self.setUp()
                self.press(0, 2)
                self.service.add_vision("s1", engine_post(previous_end))
                noted = self.service.add_vision("s1", engine_post(previous_end + 1, change=40, user_changed=True))
                self.assertEqual(noted, ChangeNote((A,), reason))
                self.assertEqual(self.state().user_changed_pending, [] if reason else [A])

    def test_a_window_that_does_not_end_after_the_previous_one_keeps_its_id_remembered_only(self):
        self.press(0, 2)
        self.service.add_vision("s1", engine_post(4))
        noted = self.service.add_vision("s1", engine_post(4, change=40, user_changed=True))   # the same end again
        self.assertEqual(noted, ChangeNote((A,), NOT_AFTER_PREVIOUS))

    def test_a_true_tag_without_the_engines_event_id_is_no_event(self):
        self.press(0, 2)
        self.service.add_vision("s1", engine_post(3, user_changed=True))
        self.assertEqual((self.state().user_changed_seen, self.state().user_changed_pending), ([], []))

    def test_an_event_before_any_features_window_is_kept_and_an_engine_post_does_not_refresh_the_idle_time(self):
        self.service.add_vision("s2", engine_post(1, change=40, user_changed=True))   # no /features window of s2 yet
        self.service.observe("s2", touch_window(0, 2), measurable=True)
        self.service.add_vision("s2", engine_post(2, change=40, user_changed=True))
        self.assertEqual(self.repository.state("s2").user_changed_pending, [], "seen before the first press")
        self.service.observe("s1", touch_window(0, 2), measurable=True)
        self.now[0] = T0 + RETENTION
        self.service.add_vision("s1", engine_post(3, change=90, user_changed=True))
        self.now[0] = T0 + RETENTION + timedelta(seconds=1)
        self.assertEqual(self.repository.windows("s1"), [], "the session expired from its last /features window")


class StartAskTests(unittest.TestCase):
    """1-2 lower_screen and 1-1 voice_order: asks, once per session, after the session's first press."""

    def test_1_2_opens_on_seated_height_after_a_press_and_not_without(self):
        _, (none,) = play(SessionState(), line(10, taps=0, tags={SEATED: True}))
        self.assertIsNone(opened(none), "no press in the session yet")
        for status in (False, UNKNOWN):
            with self.subTest(status):
                _, (none,) = play(SessionState(), line(10, tags={SEATED: status}))
                self.assertIsNone(opened(none))
        _, (asked,) = play(SessionState(), line(10, tags={SEATED: True}))
        self.assertEqual((asked.transition, asked.support, asked.scene, asked.action, asked.rank, asked.scope),
                         ("open", LOWER, "1-2", "propose", 1, ("session",)))
        self.assertEqual(asked.form(), ("none", True))
        self.assertIsNone(asked.jev_request)

    def test_an_earlier_press_counts_for_a_later_window_without_one(self):
        state, (none, asked) = play(SessionState(), line(10), line(12, taps=0, tags={SEATED: True}))
        self.assertEqual((opened(none), opened(asked)), (None, LOWER))

    def test_1_1_opens_on_aid_use_on_the_menu_only(self):
        _, (none,) = play(SessionState(), line(10, screen="review", tags={AID_USE: True}))
        self.assertIsNone(opened(none), "voice ordering exists on the menu screen only")
        _, (asked,) = play(SessionState(), line(10, tags={AID_USE: True}))
        self.assertEqual((asked.support, asked.scene, asked.action, asked.scope, asked.form()),
                         (VOICE, "1-1", "propose", ("session",), ("none", True)))
        _, (none,) = play(SessionState(), line(10, tags={AID_USE: False}))
        self.assertIsNone(opened(none))

    def test_both_wait_while_the_options_dialog_is_open_and_open_in_the_window_after_it_closes(self):
        for support, tags in ((LOWER, {SEATED: True}), (VOICE, {AID_USE: True})):
            with self.subTest(support):
                _, (waiting, asked) = play(SessionState(), line(10, tags=tags, options_open=True),
                                           line(12, taps=0, tags=tags, options_open=False))
                self.assertEqual((opened(waiting), opened(asked)), (None, support))

    def test_both_wait_while_the_screen_cannot_show_an_ask_and_open_when_it_can_or_it_is_not_known(self):
        for support, tags in ((LOWER, {SEATED: True}), (VOICE, {AID_USE: True})):
            for then in (True, None):
                with self.subTest(support=support, then=then):
                    _, decisions = play(SessionState(), line(10, tags=tags, can_offer=False),
                                        line(12, taps=0, tags=tags, can_offer=False),
                                        line(14, taps=0, tags=tags, can_offer=then))
                    self.assertEqual([opened(d) for d in decisions], [None, None, support])

    def test_no_other_row_reads_the_screens_ask_gate(self):
        cases = (({"tags": {APPROACH: True}}, LARGE_VIEW), ({"zoom_attempt": True}, LARGE_TEXT),
                 (FACING_TREMOR, BIG), ({"backs_recent": P.lost_back_min}, HIGHLIGHT))
        for fields, row in cases:
            with self.subTest(row):
                _, (shown,) = play(SessionState(), line(10, can_offer=False, **fields))
                self.assertEqual(opened(shown), row)
        _, (asked,) = play(changed_state(), line(10, cart_items=1, can_offer=False))
        self.assertEqual(opened(asked), SWAP)

    def test_1_2_comes_before_1_1_and_1_1_opens_after_1_2_lapses(self):
        both = {SEATED: True, AID_USE: True}
        lapse = 10 + P.no_response_s
        state, (first, kept, after) = play(SessionState(), line(10, tags=both), line(12, tags=both),
                                           line(lapse, tags=both))
        self.assertEqual((opened(first), kept.transition, kept.support), (LOWER, "keep", LOWER))
        self.assertEqual(opened(after), VOICE, "1-2 lapsed unanswered; 1-1 is asked next")
        self.assertEqual([(w["support"], w["reason"], tuple(w["scope"])) for w in state.withdrawn],
                         [(LOWER, "no_response", ("session",))])

    def test_a_wheelchair_behind_aid_use_also_opens_1_2_and_1_1_comes_after_its_ask(self):
        for seated, read in ((False, False), (UNKNOWN, None)):
            with self.subTest(seated=seated):
                _, (asked,) = play(SessionState(), line(10, tags={SEATED: seated, AID_USE: True}, aid_class="wheelchair"))
                self.assertEqual((opened(asked), asked.cues), (LOWER, {SEATED: read, "aid_class": "wheelchair"}))
        lapse = 10 + P.no_response_s
        both = {SEATED: True, AID_USE: True}
        _, decisions = play(SessionState(), line(10, tags=both, aid_class="wheelchair"),
                            line(lapse, tags=both, aid_class="wheelchair"))
        self.assertEqual([opened(d) for d in decisions], [LOWER, VOICE], "the low screen first, voice after its ask")

    def test_another_class_or_none_opens_1_1_and_not_1_2(self):
        lapse = 10 + P.no_response_s
        for cls in ("crutch", "cane", "walker", None):
            with self.subTest(cls=cls):
                tags = {SEATED: False, AID_USE: True}
                _, decisions = play(SessionState(), line(10, tags=tags, aid_class=cls),
                                    line(lapse, tags=tags, aid_class=cls))
                self.assertEqual([opened(d) for d in decisions], [VOICE, None], "no low-screen ask after it either")

    def test_a_lapsed_ask_is_not_asked_again_in_the_session_across_a_screen_change(self):
        for support, tags in ((LOWER, {SEATED: True}), (VOICE, {AID_USE: True})):
            with self.subTest(support):
                lapse = 10 + P.no_response_s
                state, decisions = play(SessionState(), line(10, tags=tags), line(lapse, tags=tags),
                                        line(lapse + 2, screen="review", tags=tags), line(lapse + 4, tags=tags),
                                        line(lapse + 6, tags=tags))
                self.assertEqual([opened(d) for d in decisions], [support, None, None, None, None])
                self.assertEqual(decisions[1].transition, "none", "withdrawn before the window was judged")


class RecentSignalsTests(unittest.TestCase):
    """The two scene-signal counts summed over touch_span_s, window by window."""

    @staticmethod
    def counts(fixes, zooms=0):
        return {"fixes_segment": fixes, "zoom_attempts_segment": zooms}

    def test_the_windows_ending_inside_the_span_are_summed_with_this_one(self):
        earlier = [(4.0, self.counts(5)), (5.0, self.counts(1, 1)), (8.0, self.counts(2, 1)), (10.0, self.counts(7))]
        self.assertEqual(recent_signals(self.counts(1), earlier, 10.0, P.touch_span_s),
                         {"fixes_recent": 3, "zoom_attempt": True},
                         "(5, 10): the window ending at 5 s is out, and one recorded at 10 s is not this one")

    def test_with_1_s_windows_the_sum_covers_this_window_and_the_four_before_it(self):
        def windows(fixes):
            """The order screen's 1 s windows ending at 1 s to 9 s, with fixes in the windows named by their end."""
            return [(float(end), self.counts(fixes.get(end, 0))) for end in range(1, 10)]

        self.assertEqual(recent_signals(self.counts(1), windows({6: 1}), 10.0, P.touch_span_s)["fixes_recent"], 2,
                         "fixes at 5.5 s (window ending 6 s) and at 10 s, 4.5 s apart: both counted")
        self.assertEqual(recent_signals(self.counts(1), windows({5: 1}), 10.0, P.touch_span_s)["fixes_recent"], 1,
                         "a fix in the window ending 5 s, 5.0 s before this window's end: not counted")

    def test_no_zoom_attempt_is_false_and_a_missing_count_unknown(self):
        self.assertEqual(recent_signals(self.counts(0), [(8.0, self.counts(0))], 10.0, P.touch_span_s),
                         {"fixes_recent": 0, "zoom_attempt": False})
        self.assertEqual(recent_signals(self.counts(1), [(8.0, self.counts(None, None))], 10.0, P.touch_span_s),
                         {"fixes_recent": None, "zoom_attempt": None})
        self.assertEqual(recent_signals({}, [], 10.0, P.touch_span_s), {"fixes_recent": None, "zoom_attempt": None},
                         "no block in this window (the switch off)")


def changed_state(*ids):
    """A session that has had its first press and holds unused new-customer events (engine event ids; A by default)."""
    ids = list(ids or (A,))
    return SessionState(first_press=True, user_changed_seen=list(ids), user_changed_pending=ids)


class NewCustomerRowTests(unittest.TestCase):
    """2-2 continue_or_new_order: a press with a cart after a new-customer event; the first press uses the event."""

    def test_a_press_with_a_cart_after_the_event_opens_the_question(self):
        state, (asked,) = play(changed_state(), line(10, cart_items=1))
        self.assertEqual((asked.transition, asked.support, asked.scene, asked.action, asked.rank, asked.scope),
                         ("open", SWAP, "2-2", "propose", 0, ("swap", A)))
        self.assertEqual(asked.form(), ("none", True))
        self.assertEqual(state.user_changed_pending, [], "used up")

    def test_not_without_the_event_the_press_or_the_cart(self):
        _, (none,) = play(SessionState(first_press=True), line(10, cart_items=1))
        self.assertIsNone(opened(none), "no event")
        state, (none,) = play(changed_state(), line(10, taps=0, cart_items=1))
        self.assertEqual((opened(none), state.user_changed_pending), (None, [A]), "no press: the event waits")
        for cart in (0, None):
            with self.subTest(cart=cart):
                state, (none,) = play(changed_state(), line(10, cart_items=cart))
                self.assertEqual((opened(none), state.user_changed_pending), (None, []),
                                 "an empty or unknown cart uses the event up")

    def test_the_question_comes_before_every_other_row(self):
        _, (asked,) = play(changed_state(), line(10, cart_items=2, backs_recent=1,
                                                 tags={SEATED: True, AID_USE: True}))
        self.assertEqual(opened(asked), SWAP)

    def test_once_per_event_and_the_same_event_again_after_a_lapse_stays_shut(self):
        lapse = 10 + P.no_response_s
        state, decisions = play(changed_state(), line(10, cart_items=1), line(12, cart_items=1),
                                line(lapse, cart_items=1), line(lapse + 2, cart_items=1))
        self.assertEqual([(d.transition, d.support) for d in decisions],
                         [("open", SWAP), ("keep", SWAP), ("none", None), ("none", None)])
        state.user_changed_pending = [A]                          # the same event once more after the lapse
        state, (none,) = play(state, line(lapse + 4, cart_items=1))
        self.assertIsNone(opened(none), "withdrawn in the event's own scope")
        state.user_changed_pending = [B]                          # a later event opens it again
        _, (again,) = play(state, line(lapse + 6, cart_items=1))
        self.assertEqual((opened(again), again.scope), (SWAP, ("swap", B)))

    def test_a_press_while_another_ask_is_held_keeps_the_event_for_the_first_press_after_that_ask(self):
        lapse = 10 + P.no_response_s
        for cart in (1, 0):
            with self.subTest(cart=cart):
                state, (ask,) = play(SessionState(), line(10, tags={SEATED: True}))     # 1-2 asked and held
                self.assertEqual(opened(ask), LOWER)
                state.user_changed_seen, state.user_changed_pending = [A], [A]         # then the next customer
                state, (kept,) = play(state, line(12, cart_items=cart, tags={SEATED: True}))
                self.assertEqual((kept.transition, kept.support, state.user_changed_pending), ("keep", LOWER, [A]),
                                 "the held ask keeps 2-2 shut: the press does not use the event")
                state, (after,) = play(state, line(lapse, cart_items=cart))
                self.assertEqual((opened(after), state.user_changed_pending), (SWAP if cart else None, []),
                                 "after the ask lapsed the next press decides: a cart opens 2-2, an empty one uses it")

    def test_a_shown_quiet_highlight_gives_way(self):
        state, (highlight,) = play(SessionState(first_press=True), line(10, backs_recent=1))
        self.assertEqual(opened(highlight), HIGHLIGHT)
        state.user_changed_pending = [A]
        _, (asked,) = play(state, line(12, cart_items=1))
        self.assertEqual((asked.transition, asked.support), ("replace", SWAP))


class SupportChoiceCandidateTests(unittest.TestCase):
    """The support_choice stage lists in its state only the candidates its question offers (a WHAT line)."""

    def test_the_asks_by_name_are_left_out_of_both_the_state_and_the_criteria(self):
        from app.modules.decision.jev_questions import NO_SUPPORT, StageInput, SupportChoiceStage
        inp = line(10, backs_recent=P.lost_back_min, tags={SEATED: True})        # 1-2 by name and 4-2 can open
        state, questions = SupportChoiceStage(P).build(StageInput(inp, SessionState(), decide(inp, SessionState(), P), None))
        self.assertEqual(state["candidates"], [HIGHLIGHT])
        self.assertEqual(list(questions["support_choice"]["criteria"]), [HIGHLIGHT, NO_SUPPORT])


FACING_TREMOR = {"fixes_recent": P.tremor_miss_min, "gaze": True}   # what opens 4-1 while facing the screen


class LowVisionRowTests(unittest.TestCase):
    """2-1: the 크게 보기 ask on a zoom attempt, the help ring on a face approach alone."""

    def test_a_zoom_attempt_opens_the_large_view_ask_and_no_attempt_does_not(self):
        _, (asked,) = play(SessionState(), line(10, zoom_attempt=True, tags={APPROACH: True}))
        self.assertEqual((asked.support, asked.scene, asked.action, asked.rank, asked.scope[0]),
                         (LARGE_TEXT, "2-1", "propose", 6, "screen"))
        self.assertEqual(asked.form(), ("large_text", True))
        self.assertEqual(asked.cues, {"zoom_attempt": True, APPROACH: True})
        self.assertEqual(asked.policy["kind"], "fit")
        state = asked.jev_request["state"]
        self.assertEqual((state["touch"]["zoom_attempt"], state["vision"]["face_approach"]), (True, True))
        question = asked.jev_request["questions"]["proposal_fits"]
        self.assertEqual(question["instructions"]["proposed_support"]["what"],
                         "Ask the user whether the text should become bigger")
        for zoom in (False, None):
            with self.subTest(zoom=zoom):
                _, (none,) = play(SessionState(), line(10, zoom_attempt=zoom))
                self.assertIsNone(opened(none))

    def test_a_face_approach_after_a_press_rings_the_help_entry(self):
        _, (ring,) = play(SessionState(), line(10, tags={APPROACH: True}))
        self.assertEqual((ring.support, ring.scene, ring.action, ring.rank, ring.form()),
                         (LARGE_VIEW, "2-1", "apply", 8, ("none", False)))
        self.assertEqual(ring.execution["target_id"], "support-toggle")
        self.assertEqual(ring.jev_request["questions"]["proposal_fits"]["criteria"]["true"],
                         "The user's face comes close to the screen while operating it, so pointing at the help "
                         "button for a bigger screen helps")

    def test_the_ring_waits_for_a_press_and_a_closed_options_dialog_and_skips_a_known_large_view(self):
        _, (none,) = play(SessionState(), line(10, taps=0, tags={APPROACH: True}))
        self.assertIsNone(opened(none), "no press in the session yet")
        _, (none,) = play(SessionState(), line(10, options_open=True, tags={APPROACH: True}))
        self.assertIsNone(opened(none), "the ring target sits outside the options dialog")
        for kind in ("active", "refused"):
            for support in (LARGE_TEXT, BIG):
                with self.subTest(kind=kind, support=support):
                    _, (none,) = play(SessionState(**{kind: [support]}), line(10, tags={APPROACH: True}))
                    self.assertIsNone(opened(none))

    def test_the_shown_ring_gives_way_to_an_ask(self):
        state, (ring,) = play(SessionState(), line(10, tags={APPROACH: True}))
        _, (asked,) = play(state, line(12, zoom_attempt=True, tags={APPROACH: True}))
        self.assertEqual((asked.transition, asked.support), ("replace", LARGE_TEXT))

    def test_a_setting_on_counts_as_active_for_the_rows(self):
        cases = (   # (input fields, the support that is on, the row it closes)
            ({"tags": {SEATED: True}}, LOWER, LOWER), ({"tags": {AID_USE: True}}, VOICE, VOICE),
            ({"zoom_attempt": True}, LARGE_TEXT, LARGE_TEXT), ({"zoom_attempt": True}, BIG, LARGE_TEXT),
            (FACING_TREMOR, BIG, BIG), (FACING_TREMOR, LARGE_TEXT, BIG),
            ({"tags": {APPROACH: True}}, LARGE_TEXT, LARGE_VIEW), ({"tags": {APPROACH: True}}, BIG, LARGE_VIEW),
        )
        for fields, on, row in cases:
            with self.subTest(on=on, row=row):
                _, (none,) = play(SessionState(), line(10, supports_on=(on,), **fields))
                self.assertIsNone(opened(none))
                for unknown in (None, ()):
                    _, (asked,) = play(SessionState(), line(10, supports_on=unknown, **fields))
                    self.assertEqual(opened(asked), row)

    def test_the_two_large_view_asks_block_each_other_in_one_screen_visit(self):
        lapse = 10 + P.no_response_s
        for first, second, name in ((FACING_TREMOR, {"zoom_attempt": True}, "4-1 then 2-1"),
                                    ({"zoom_attempt": True}, FACING_TREMOR, "2-1 then 4-1")):
            with self.subTest(name):
                state, (asked, held, lapsed, after) = play(
                    SessionState(), line(10, **first), line(12, **second), line(lapse, **second),
                    line(lapse + 2, **second))
                self.assertIn(opened(asked), (BIG, LARGE_TEXT))
                self.assertEqual((held.transition, held.support), ("keep", asked.support))
                self.assertEqual([opened(lapsed), opened(after)], [None, None],
                                 "the other code name of 크게 보기 stays closed in this screen visit")
                _, (review, menu) = play(state, line(lapse + 4, screen="review", **second),
                                         line(lapse + 6, **second))
                self.assertIn(opened(review), (BIG, LARGE_TEXT), "a new screen visit")


LOST = ({"pause_s": P.lost_pause_s}, {"backs_recent": P.lost_back_min})   # what opens 4-2: a pause, a back


class NextActionRowTests(unittest.TestCase):
    """4-2 highlight_next_action: not on the menu while the options dialog is known closed (nothing chosen yet)."""

    def test_on_the_menu_with_the_options_dialog_known_closed_4_2_stays_shut_and_the_help_ring_opens(self):
        for opening in LOST:
            with self.subTest(opening):
                _, (none,) = play(SessionState(), line(10, options_open=False, **opening))
                self.assertIsNone(opened(none))
                _, (ring,) = play(SessionState(), line(10, options_open=False, tags={APPROACH: True}, **opening))
                self.assertEqual((opened(ring), ring.execution["target_id"]), (LARGE_VIEW, "support-toggle"))

    def test_with_the_options_dialog_open_on_the_menu_4_2_opens_on_the_add_button(self):
        for opening in LOST:
            with self.subTest(opening):
                _, (shown,) = play(SessionState(), line(10, options_open=True, **opening))
                self.assertEqual((opened(shown), shown.rank, shown.execution["target_id"]), (HIGHLIGHT, 7, "cart-add"))

    def test_with_the_options_dialog_not_known_4_2_opens_as_before(self):
        for opening in LOST:
            with self.subTest(opening):
                _, (shown,) = play(SessionState(), line(10, **opening))
                self.assertEqual((opened(shown), shown.execution["target_id"]), (HIGHLIGHT, None))
                _, (shown,) = play(SessionState(), line(10, tags={APPROACH: True}, **opening))
                self.assertEqual(opened(shown), HIGHLIGHT, "rank 7 before the help ring's 8")

    def test_on_the_review_screen_4_2_opens_on_the_decrease_buttons_as_before(self):
        for options_open in (False, None):
            for opening in LOST:
                with self.subTest(options_open=options_open, opening=opening):
                    _, (shown,) = play(SessionState(), line(10, screen="review", options_open=options_open, **opening))
                    self.assertEqual((opened(shown), shown.execution["target_id"]), (HIGHLIGHT, "cart:*:decrease"))


if __name__ == "__main__":
    unittest.main()
