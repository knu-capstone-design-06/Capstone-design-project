"""Events and situation layers (app/modules/vision/events.py, situation.py) on synthetic observation windows.

Standard library only: the two layers need no numpy, OpenCV or MediaPipe, so these tests also run with
ai-engine/requirements.txt alone. No photos, videos or runs/.

Every PilotParams value here (P) is made for these synthetic frames (10 frames per second) and is not a proposal: the
pilot values come from the team's self-recording (vision README, '상황 층').
"""

import dataclasses
import importlib.util
import os
import tokenize
import unittest

from app.modules.vision.events import PilotParams, detect_events, observe_window
from app.modules.vision.situation import DISPLAY_TEXT, NONE, TAGS, UNKNOWN, assess, check_output, consulting_companion

NAN = float("nan")
DT = 0.1                                     # synthetic frame interval (s)
PITCH_TEST = 20.0   # head_down_pitch_min of these tests: an arbitrary round value, not a calibration
SEEN, NOT_SEEN = "보임", "못 봄"
SITUATION_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "app", "modules", "vision", "situation.py")

# test values for the synthetic frames below (see the module docstring), not pilot proposals
P = PilotParams(window_s=20.0, gap_s=0.25, offscreen_yaw_deg=30.0, shoulder_vis_min=0.5, look_back_min_count=2,
                sweep_min_count=2, stay_min_s=1.0, dwell_min_s=1.0, mouth_motion_min=0.2, body_still_max=0.05,
                min_events=3, face_visible_min=0.6,
                track_conf_min=0.6)

BEHIND, COMPANION, AROUND = "looking_back_with_people_behind", "consulting_companion", "looking_around"
BASE = {"face_state": SEEN, "body_state": SEEN, "yaw_deg": 0.0, "face_cx": 0.5, "pose_vis_shoulders": 0.9,
        "shoulder_cx": 0.5, "shoulder_cy": 0.7}
OPTIONAL = {"people_behind_count": 0, "companion_box": None, "mouth_motion": 0.0, "tap_count": 0,
            "miss_tap_count": 0}
LOST = {"face_state": NOT_SEEN, "yaw_deg": NAN, "face_cx": NAN}                  # face lost, shoulders stay
GONE = {**LOST, "body_state": NOT_SEEN, "pose_vis_shoulders": NAN, "shoulder_cx": NAN, "shoulder_cy": NAN}
RIGHT_BOX = (0.75, 0.25, 0.95, 0.95)        # companion box right of the user's face (face_cx 0.5)
LEFT_BOX = (0.05, 0.25, 0.25, 0.95)         # and left of it


def face(n):
    """n frames facing the screen."""
    return [(n, {})]


def look_back(lost=5):
    """One look-back: yaw grows past the off-screen yaw, the face points are lost while the shoulders stay, the face
    comes back (one more off-screen frame) - the return frame is the next facing frame."""
    return [(1, {"yaw_deg": 40.0}), (1, {"yaw_deg": 60.0}), (lost, LOST), (1, {"yaw_deg": 45.0})]


def sweep(sign=1):
    """One off-screen head turn with the face seen throughout (+1 = yaw positive = image right)."""
    return [(1, {"yaw_deg": sign * 40.0}), (2, {"yaw_deg": sign * 55.0}), (1, {"yaw_deg": sign * 40.0})]


def rows_of(*parts, extra=None, drop=()):
    """Frames DT apart from t = 0; each part is a list of (frames, overrides). Every row = BASE + extra (default
    OPTIONAL) + overrides, without the columns in drop."""
    extra = OPTIONAL if extra is None else extra
    rows = []
    for part in parts:
        for n, over in part:
            for _ in range(n):
                i = len(rows)
                row = {"frame_idx": i, "t_s": round(i * DT, 6), **BASE, **extra, **over}
                rows.append({k: v for k, v in row.items() if k not in drop})
    return rows


def put(rows, first, last, **values):
    """Set values on frames first..last (inclusive)."""
    for row in rows[first:last + 1]:
        row.update(values)
    return rows


def companion_window(*turns, mouth=0.3):
    """Companion box on the right all along, the given head turns, then mouth motion on 6 facing frames."""
    rows = rows_of(face(5), *turns, face(10), extra={**OPTIONAL, "companion_box": RIGHT_BOX})
    last = len(rows) - 1
    return put(rows, last - 7, last - 2, mouth_motion=mouth)


def around_window(drop=()):
    """Two off-screen turns (right, then left) with the face seen, no touch, body still, nobody behind."""
    return rows_of(face(5), sweep(+1), face(5), sweep(-1), face(5), drop=drop)


def golden_windows():
    """(name, rows, PilotParams overrides, landmarker num_faces) of the windows whose three-tag output is pinned to the
    code before the scene tags (tests/data/situation_golden_main.json, made from origin/main)."""
    return [
        ("behind", put(rows_of(face(5), look_back(), face(5), look_back(), face(5)), 0, 30, people_behind_count=1),
         {}, 1),
        ("companion", companion_window(sweep(+1)), {}, 1),
        ("companion_two_faces", companion_window(sweep(+1)), {}, 2),
        ("around", around_window(), {}, 1),
        ("around_min_events_4", around_window(), {"min_events": 4}, 1),
        ("around_no_companion_column", around_window(drop=("companion_box",)), {}, 1),
        ("facing", rows_of(face(10)), {}, 1),
        ("gone", rows_of(face(5), [(10, GONE)], face(5)), {}, 1),
        ("short_window", companion_window(sweep(+1)), {"window_s": 1.9}, 1),
    ]


def run(rows, params=P, num_faces=1):
    return assess(rows, rows[-1]["t_s"], params, landmarker_num_faces=num_faces)


def kinds(events):
    return [e["kind"] for e in events]


def ids(entry):
    return sorted({item["event_id"] for item in entry["evidence"]})


class PilotParamsTests(unittest.TestCase):
    def test_no_field_has_a_default(self):
        with self.assertRaises(TypeError):
            PilotParams()
        for f in dataclasses.fields(PilotParams):
            self.assertIs(f.default, dataclasses.MISSING, f.name)
            self.assertIs(f.default_factory, dataclasses.MISSING, f.name)

    def test_values_must_be_finite_non_negative_and_counts_at_least_one(self):
        """A count of 0 would let a rule pass without the observation it names: every count field must be >= 1.
        A floor compared with a share of frames above 1 (a percentage by mistake) and a zero window or gap are
        errors too: they would make every window unknown or split every event into single frames."""
        for bad in ({"window_s": -1.0}, {"gap_s": NAN}, {"min_events": 2.5}, {"sweep_min_count": True},
                    {"offscreen_yaw_deg": None}, {"look_back_min_count": 0}, {"sweep_min_count": 0},
                    {"min_events": 0}, {"face_visible_min": 1.5},
                    {"track_conf_min": 60.0}, {"shoulder_vis_min": 1.01}, {"window_s": 0.0}, {"gap_s": 0}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                dataclasses.replace(P, **bad)

    def test_situation_py_holds_no_number(self):
        """Every threshold of the rules is a PilotParams field: situation.py has no numeric literal at all."""
        with open(SITUATION_PY, "rb") as f:
            numbers = [t.string for t in tokenize.tokenize(f.readline) if t.type == tokenize.NUMBER]
        self.assertEqual(numbers, [])

    @unittest.skipUnless(importlib.util.find_spec("cv2") is not None, "OpenCV not installed (features.py needs it)")
    def test_seen_label_matches_the_features_layer(self):
        from app.modules.vision import events, features

        self.assertEqual(events.SEEN, features.SEEN)


class EventTests(unittest.TestCase):
    """Observations -> events (params P: test values, see the module docstring)."""

    def test_one_head_turn_is_one_event(self):
        """yaw grows, face points lost while the shoulders stay, return: ONE look_back, no separate yaw event."""
        rows = rows_of(face(5), look_back(), face(5))
        turns = [e for e in detect_events(rows, P, landmarker_num_faces=1)
                 if e["kind"] in ("look_back", "yaw_sweep_offscreen")]
        self.assertEqual(len(turns), 1)
        event = turns[0]
        self.assertEqual((event["kind"], event["event_id"]), ("look_back", "look_back@5"))
        self.assertEqual(event["source_frames"], list(range(5, 14)))       # onset 5 .. return 13
        self.assertAlmostEqual(event["t_start"], 0.5)
        self.assertAlmostEqual(event["t_end"], 1.3)
        self.assertEqual(event["obs"]["yaw_deg"], 60.0)                     # largest visible yaw
        self.assertEqual(event["obs"]["side"], "right")
        self.assertAlmostEqual(event["obs"]["face_lost_s"], 0.6)            # first lost frame 0.7 -> return 1.3
        self.assertEqual(event["obs"]["pose_vis_shoulders"], 0.9)

    def test_a_turn_with_the_face_seen_is_a_sweep(self):
        rows = rows_of(face(5), sweep(-1), face(5))
        turns = [e for e in detect_events(rows, P, landmarker_num_faces=1) if e["kind"] != "dwell_no_touch"]
        self.assertEqual(kinds(turns), ["yaw_sweep_offscreen"])
        self.assertEqual(turns[0]["obs"]["side"], "left")
        self.assertAlmostEqual(turns[0]["obs"]["offscreen_s"], 0.4)

    def test_face_lost_straight_from_facing_is_a_look_back(self):
        """Face-lost onset path (dec section 3: face points lost, shoulders kept, return): facing, then the face points
        are lost while the shoulders stay, then facing again - one look_back without a visible off-screen yaw, so its
        yaw and side are empty."""
        rows = rows_of(face(5), [(5, LOST)], face(5))
        turns = [e for e in detect_events(rows, P, landmarker_num_faces=1)
                 if e["kind"] in ("look_back", "yaw_sweep_offscreen")]
        self.assertEqual([(e["kind"], e["event_id"]) for e in turns], [("look_back", "look_back@5")])
        event = turns[0]
        self.assertEqual(event["source_frames"], list(range(5, 11)))       # first lost frame 5 .. return 10
        self.assertEqual((event["obs"]["yaw_deg"], event["obs"]["side"]), (None, None))
        self.assertAlmostEqual(event["obs"]["face_lost_s"], 0.5)            # first lost frame 0.5 -> return 1.0
        self.assertEqual(event["obs"]["pose_vis_shoulders"], 0.9)

    def test_a_face_lost_turn_records_its_context(self):
        """pre_loss_yaw_deg / pre_loss_pitch_deg = median of the facing frames in baseline_s before the onset (here
        0.25 s before 0.4 s: frames at 0.2 and 0.3 s), loss_duration_s = first to last lost frame, shoulder_vis_mean
        over the lost frames; without baseline_s the two pre-loss values stay empty."""
        facing = [(1, {"yaw_deg": y, "pitch_deg": p}) for y, p in ((2.0, 20.0), (4.0, 22.0), (6.0, 24.0), (8.0, 26.0))]
        lost = [(1, {**LOST, "pose_vis_shoulders": v}) for v in (0.6, 0.8, 0.7, 0.9)]
        rows = rows_of(facing, lost, face(3))
        (event,) = [e for e in detect_events(rows, P, landmarker_num_faces=1, baseline_s=0.25)
                    if e["kind"] == "look_back"]
        self.assertEqual((event["obs"]["pre_loss_yaw_deg"], event["obs"]["pre_loss_pitch_deg"]), (7.0, 25.0))
        self.assertAlmostEqual(event["obs"]["loss_duration_s"], 0.3)        # lost frames at 0.4 .. 0.7 s
        self.assertAlmostEqual(event["obs"]["face_lost_s"], 0.4)            # to the return at 0.8 s
        self.assertAlmostEqual(event["obs"]["shoulder_vis_mean"], 0.75)
        (plain,) = [e for e in detect_events(rows, P, landmarker_num_faces=1) if e["kind"] == "look_back"]
        self.assertEqual((plain["obs"]["pre_loss_yaw_deg"], plain["obs"]["pre_loss_pitch_deg"]), (None, None))

    def test_both_onset_paths_in_one_sequence(self):
        """Yaw path (the face passes offscreen_yaw_deg, then is lost) and face-lost path (lost straight from facing):
        two look_backs, the first with its largest visible yaw and side, the second without."""
        rows = rows_of(face(5), look_back(), face(5), [(4, LOST)], face(5))
        turns = [e for e in detect_events(rows, P, landmarker_num_faces=1) if e["kind"] == "look_back"]
        self.assertEqual([(e["event_id"], e["obs"]["yaw_deg"], e["obs"]["side"]) for e in turns],
                         [("look_back@5", 60.0, "right"), ("look_back@18", None, None)])

    def test_face_loss_that_is_not_a_turn_gives_no_turn_event(self):
        cases = {
            "face and body lost from facing (no shoulders)": rows_of(face(5), [(5, GONE)], face(5)),
            "face lost for gap_s or less (face-lost path)": rows_of(face(5), [(2, LOST)], face(5)),   # 0.2 <= 0.25
            "body lost too, longer than gap_s": rows_of(face(5), [(1, {"yaw_deg": 50.0}), (5, GONE)], face(5)),
            "no return in the window": rows_of(face(5), [(1, {"yaw_deg": 50.0}), (5, LOST)]),
            "small yaw (menu reading)": rows_of(face(3), [(4, {"yaw_deg": 15.0}), (4, {"yaw_deg": -15.0})], face(3)),
        }
        for name, rows in cases.items():
            events = detect_events(rows, P, landmarker_num_faces=1)
            self.assertNotIn("look_back", kinds(events), name)
            self.assertNotIn("yaw_sweep_offscreen", kinds(events), name)

    def test_a_short_tracking_drop_inside_a_turn_is_bridged(self):
        rows = rows_of(face(5), [(1, {"yaw_deg": 50.0}), (2, LOST), (1, GONE), (2, LOST)], face(5))
        turns = [e for e in detect_events(rows, P, landmarker_num_faces=1) if e["kind"] == "look_back"]
        self.assertEqual(len(turns), 1)
        self.assertNotIn(8, turns[0]["source_frames"])                      # the dropped frame is not evidence

    def test_presence_needs_stay_min_s_and_bridges_short_gaps(self):
        rows = put(put(rows_of(face(40)), 0, 14, people_behind_count=1), 16, 30, people_behind_count=1)
        put(rows, 35, 37, people_behind_count=2)                            # 0.2 s: passing by
        behind = [e for e in detect_events(rows, P, landmarker_num_faces=1) if e["kind"] == "people_behind"]
        self.assertEqual(len(behind), 1)                                    # frame 15 (0 people) bridged
        self.assertEqual(behind[0]["obs"], {"people_behind_count": 1, "stay_s": 3.0})

    def test_a_touch_ends_a_dwell(self):
        rows = put(rows_of(face(40)), 20, 20, tap_count=1)
        dwell = [e for e in detect_events(rows, P, landmarker_num_faces=1) if e["kind"] == "dwell_no_touch"]
        self.assertEqual([e["event_id"] for e in dwell], ["dwell_no_touch@0", "dwell_no_touch@21"])

    def test_touch_log_events(self):
        """Misses make a touch_miss event; columns no rule reads (back_count, first_input_delay_ms) make none."""
        rows = rows_of(face(50))
        put(rows, 10, 10, tap_count=1, miss_tap_count=1)
        put(rows, 12, 12, tap_count=1, back_count=1)
        put(rows, 40, 40, tap_count=1, first_input_delay_ms=3500.0)
        events = {e["kind"]: e for e in detect_events(rows, P, landmarker_num_faces=1)}
        self.assertEqual(events["touch_miss"]["obs"], {"miss_tap_count": 1})
        self.assertFalse({"back_navigation_loop", "first_input_delayed"} & set(events))

    def test_a_column_missing_in_some_rows_is_not_measured(self):
        """people_behind_count missing in one row: the window does not measure it, so its absence would not be
        concluded; the person seen behind is still an observed event."""
        rows = put(rows_of(face(30), extra={}), 0, 29, people_behind_count=1)
        rows[10].pop("people_behind_count")
        cues = observe_window(rows, (0.0, rows[-1]["t_s"]), P, landmarker_num_faces=1)
        self.assertNotIn("people_behind_count", cues.measured)
        self.assertIn("people_behind", kinds(cues.events))
        self.assertIsNone(cues.any_tap)                                     # no touch log: unknown, not 'no touch'

    def test_a_long_time_gap_ends_events_even_between_adjacent_rows(self):
        """Item 4: adjacent rows more than gap_s apart (a gap in the record) end the dwell, the presence and a turn."""
        rows = put(rows_of(face(40)), 0, 39, people_behind_count=1)
        for row in rows[20:]:
            row["t_s"] = round(row["t_s"] + 3.0, 6)                         # rows 19 -> 20: 0.1 s becomes 3.1 s
        events = detect_events(rows, P, landmarker_num_faces=1)
        self.assertEqual([e["event_id"] for e in events if e["kind"] == "dwell_no_touch"],
                         ["dwell_no_touch@0", "dwell_no_touch@20"])
        self.assertEqual([e["event_id"] for e in events if e["kind"] == "people_behind"],
                         ["people_behind@0", "people_behind@20"])
        turn = rows_of(face(5), [(1, {"yaw_deg": 50.0}), (3, LOST)], face(5))
        for row in turn[7:]:
            row["t_s"] = round(row["t_s"] + 3.0, 6)                         # the gap falls inside the turn
        self.assertNotIn("look_back", kinds(detect_events(turn, P, landmarker_num_faces=1)))

    def test_counts_must_be_whole_numbers_of_at_least_zero(self):
        """Item 6 (r2) and the backend review: the contract's TouchFeatures counts are integer, minimum 0. The two
        touch columns take a whole number or a digit string (a CSV cell), not a float, a float string, a bool or a
        negative; other values are errors, not missing values. people_behind_count (not in the contract) also takes a
        whole number written as a float."""
        for key in ("tap_count", "miss_tap_count"):
            for bad in (-1, "-1", 1.0, 1.5, "1.0", " 1", "two", True):
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    detect_events(put(rows_of(face(5)), 2, 2, **{key: bad}), P, landmarker_num_faces=1)
            for good in (0, 2, "2"):
                with self.subTest(key=key, good=good):
                    detect_events(put(rows_of(face(5)), 2, 2, **{key: good}), P, landmarker_num_faces=1)
        rows = put(rows_of(face(5)), 2, 2, tap_count="3", miss_tap_count="1")
        misses = [e for e in detect_events(rows, P, landmarker_num_faces=1) if e["kind"] == "touch_miss"]
        self.assertEqual([e["obs"] for e in misses], [{"miss_tap_count": 1}])
        huge = 2**53 + 1
        events = detect_events(put(rows_of(face(5)), 2, 2, miss_tap_count=huge), P, landmarker_num_faces=1)
        self.assertEqual([e["obs"]["miss_tap_count"] for e in events if e["kind"] == "touch_miss"], [huge])
        events = detect_events(put(rows_of(face(20)), 0, 19, people_behind_count=2.0), P, landmarker_num_faces=1)
        self.assertEqual([e["obs"]["people_behind_count"] for e in events if e["kind"] == "people_behind"], [2])

    def test_detect_events_ignores_rows_after_the_window(self):
        """Item 4 (r3): the same window gives the same events from the whole log and from the log cut at its end
        (here a dwell and a person behind go on after the window)."""
        rows = rows_of(face(5), look_back(), face(5), look_back(), face(30))
        put(rows, 0, len(rows) - 1, people_behind_count=1)
        window = (0.5, 3.0)
        cut = [r for r in rows if r["t_s"] <= window[1]]
        self.assertEqual(detect_events(rows, P, landmarker_num_faces=1, window=window),
                         detect_events(cut, P, landmarker_num_faces=1, window=window))

    def test_yaw_toward_the_companion_needs_no_return(self):
        """Item 1: the main user keeps looking toward the companion's side to the end: one yaw_toward_companion,
        and no sweep (a sweep needs the return)."""
        rows = rows_of(face(5), [(15, {"yaw_deg": 45.0})], extra={**OPTIONAL, "companion_box": RIGHT_BOX})
        events = detect_events(rows, P, landmarker_num_faces=1)
        toward = [e for e in events if e["kind"] == "yaw_toward_companion"]
        self.assertEqual([(e["event_id"], e["obs"]["side"]) for e in toward], [("yaw_toward_companion@5", "right")])
        self.assertNotIn("yaw_sweep_offscreen", kinds(events))


class LookingBackWithPeopleBehindTests(unittest.TestCase):
    """Tag 1 (params P: test values, see the module docstring)."""

    def test_person_behind_and_repeated_look_backs(self):
        rows = put(rows_of(face(5), look_back(), face(5), look_back(), face(5)), 0, 30, people_behind_count=1)
        out, events = run(rows)
        self.assertEqual(out["name"], BEHIND)
        self.assertEqual(out["display_text"], "뒤에 사람이 있어 서두르는 듯함")
        self.assertEqual(ids(out), ["look_back@18", "look_back@5", "people_behind@0"])
        self.assertEqual(out["confidence"], {"events": 3, "quality_ok": True})
        self.assertEqual(out["alternatives"], [])
        self.assertEqual(check_output(out, events, P), [])
        look = [item for item in out["evidence"] if item["event_id"] == "look_back@5"]
        self.assertEqual([item["obs"] for item in look], ["yaw_deg", "side", "face_lost_s", "pose_vis_shoulders",
                                                          "pre_loss_yaw_deg", "pre_loss_pitch_deg", "loss_duration_s",
                                                          "shoulder_vis_mean"])
        self.assertEqual({item["t"] for item in look}, {1.3})        # the event's time = its end (the return)

    def test_low_face_visibility_does_not_block_it(self):
        """Face loss is the look_back cue: a face seen in under face_visible_min of the frames still gives the tag."""
        rows = put(rows_of(face(3), look_back(lost=12), face(3), look_back(lost=12), face(3)), 0, 38,
                   people_behind_count=1)
        out, _ = run(rows)
        self.assertLess(out["quality"]["face_visible_ratio"], P.face_visible_min)
        self.assertEqual(out["name"], BEHIND)

    def test_misses_add_support(self):
        rows = put(rows_of(face(5), look_back(), face(5), look_back(), face(5)), 0, 30, people_behind_count=1)
        put(rows, 15, 15, tap_count=1, miss_tap_count=1)
        out, _ = run(rows)
        self.assertEqual(out["name"], BEHIND)
        self.assertIn("touch_miss@15", ids(out))
        self.assertEqual(out["confidence"]["events"], 4)

    def test_only_passers_by(self):
        rows = rows_of(face(5), look_back(), face(5), look_back(), face(5))
        put(put(rows, 2, 6, people_behind_count=1), 20, 24, people_behind_count=1)   # 0.4 s each
        put(rows, 30, 30, tap_count=1)                     # a touch: rules out the other two tags here
        out, _ = run(rows)
        self.assertEqual((out["name"], out["alternatives"]), (NONE, []))

    def test_no_yaw_at_all_leaves_the_look_back_cue_unknown(self):
        """Item 3 (r2): faces are seen but every yaw is missing, so no turn can be seen: with a person standing
        behind, the window is unknown, not none."""
        out, _ = run(put(rows_of(face(30)), 0, 29, people_behind_count=1, yaw_deg=NAN))
        self.assertEqual(out["name"], UNKNOWN)
        self.assertEqual([a["name"] for a in out["alternatives"]], [BEHIND])

    def test_no_shoulder_value_during_face_loss_leaves_the_look_back_cue_unknown(self):
        """Item 3 (r2): the face is lost after a turn but the shoulder values are missing, so whether the person
        turned back cannot be told: unknown, not none."""
        rows = rows_of(face(5), [(1, {"yaw_deg": 50.0}), (5, {**LOST, "pose_vis_shoulders": NAN})], face(10))
        out, _ = run(put(rows, 0, 20, people_behind_count=1))
        self.assertEqual(out["name"], UNKNOWN)

    def test_a_turn_broken_by_face_and_body_loss_is_unknown(self):
        """Item 2 (r3): after a turn starts, face and body are both lost for longer than gap_s, while the window's
        body tracking still meets track_conf_min. Whether it was a look-back cannot be told: unknown, not none."""
        rows = put(rows_of(face(5), [(1, {"yaw_deg": 50.0}), (5, GONE)], face(20)), 0, 30, people_behind_count=1)
        out, _ = run(rows)
        self.assertGreaterEqual(out["quality"]["track_conf"], P.track_conf_min)
        self.assertEqual(out["name"], UNKNOWN)
        self.assertEqual([a["name"] for a in out["alternatives"]], [BEHIND])

    def test_people_behind_without_look_backs(self):
        rows = put(put(rows_of(face(30)), 0, 29, people_behind_count=1), 15, 15, tap_count=1)
        out, _ = run(rows)
        self.assertEqual((out["name"], out["alternatives"]), (NONE, []))


class ConsultingCompanionTests(unittest.TestCase):
    """Tag 2 (params P: test values, see the module docstring)."""

    def test_companion_turn_toward_mouth_and_dwell(self):
        out, events = run(companion_window(sweep(+1)))
        self.assertEqual(out["name"], COMPANION)
        self.assertEqual(out["display_text"], "일행과 상의하는 듯함")
        self.assertEqual([k.split("@")[0] for k in ids(out)],
                         ["companion_present", "dwell_no_touch", "mouth_moving", "yaw_toward_companion"])
        self.assertEqual(out["confidence"], {"events": 4, "quality_ok": True})
        self.assertEqual(check_output(out, events, P), [])

    def test_unsmoothed_landmarker_mouth_motion_is_not_counted(self):
        """Exclusion: num_faces 2 turns smoothing off [D1] -> no mouth_moving; judged on the rest, quality_ok false."""
        out, events = run(companion_window(sweep(+1)), num_faces=2)
        self.assertNotIn("mouth_moving", kinds(events))
        self.assertEqual(out["name"], COMPANION)
        self.assertEqual(out["confidence"], {"events": 3, "quality_ok": False})

    def test_missing_mouth_column_is_left_out(self):
        rows = [{k: v for k, v in r.items() if k != "mouth_motion"} for r in companion_window(sweep(+1))]
        out, _ = run(rows)
        self.assertEqual(out["name"], COMPANION)
        self.assertEqual(out["confidence"], {"events": 3, "quality_ok": False})

    def test_blendshapes_off_drop_the_mouth_condition_and_the_evidence_shows_the_cues_used(self):
        """Fallback (README tag table, situation.py): with blendshapes off the chain writes mouth_motion blank on every
        row. The mouth condition of the conjunction is then missing (결측) and dropped: the tag stands on the other
        cues, the evidence holds only those three kinds, the verdict records the skipped cue, quality_ok is false."""
        rows = put(companion_window(sweep(+1)), 0, 18, mouth_motion=None)
        out, events = run(rows)
        self.assertEqual(out["name"], COMPANION)
        self.assertEqual(sorted({k.split("@")[0] for k in ids(out)}),
                         ["companion_present", "dwell_no_touch", "yaw_toward_companion"])
        self.assertEqual(out["confidence"], {"events": 3, "quality_ok": False})
        cues = observe_window(rows, (rows[0]["t_s"], rows[-1]["t_s"]), P, landmarker_num_faces=1)
        self.assertEqual(consulting_companion(cues, P).skipped, ("mouth_moving",))
        self.assertEqual(check_output(out, events, P), [])

    def test_turning_away_from_the_companion(self):
        out, _ = run(companion_window(sweep(-1)))
        self.assertEqual(out["name"], NONE)

    def test_mouth_seen_but_still(self):
        out, _ = run(companion_window(sweep(+1), mouth=0.0))
        self.assertEqual(out["name"], NONE)

    def test_all_blank_mouth_values_are_left_out(self):
        """Item 5: mouth_motion is there but blank in every row: not measured, so left out (quality_ok false)."""
        out, _ = run(put(companion_window(sweep(+1)), 0, 18, mouth_motion=NAN))
        self.assertEqual(out["name"], COMPANION)
        self.assertEqual(out["confidence"], {"events": 3, "quality_ok": False})

    def test_one_mouth_value_and_the_rest_missing_is_not_no_movement(self):
        """Item 2 (r2): mouth_motion is 0 on one face frame and blank on the others: 'no movement' is not concluded,
        so mouth motion is left out (quality_ok false) instead of ruling the tag out."""
        rows = put(companion_window(sweep(+1)), 0, 18, mouth_motion=NAN)
        rows[2]["mouth_motion"] = 0.0
        out, _ = run(rows)
        self.assertEqual(out["name"], COMPANION)
        self.assertEqual(out["confidence"], {"events": 3, "quality_ok": False})

    def test_mouth_movement_counts_with_the_key_missing_on_some_rows(self):
        """Item 2 (r2): rows without the mouth_motion key do not hide the movement seen on the others."""
        rows = companion_window(sweep(+1))
        for row in rows[:3]:
            row.pop("mouth_motion")
        out, _ = run(rows)
        self.assertEqual(out["confidence"], {"events": 4, "quality_ok": True})
        self.assertIn("mouth_moving", [i.split("@")[0] for i in ids(out)])

    def test_a_small_yaw_toward_the_companion_counts(self):
        """Item 8 (r2): the decision table's 'yaw toward the companion' is its side only - a yaw well inside
        offscreen_yaw_deg on the companion's side counts (README: [설계 제안] note on menu reading)."""
        out, events = run(companion_window([(6, {"yaw_deg": 10.0})]))
        self.assertEqual(out["name"], COMPANION)
        self.assertIn("yaw_toward_companion", kinds(events))
        self.assertNotIn("yaw_sweep_offscreen", kinds(events))

    def test_the_companion_side_is_read_at_each_frame(self):
        """Item 4 (r2): the companion stands right for 2.5 s, then left; the user then looks left. The side at those
        frames decides, not the median of the whole stay (which is right)."""
        rows = put(put(rows_of(face(28), [(9, {"yaw_deg": -40.0})], face(3)), 0, 24, companion_box=RIGHT_BOX),
                   25, 39, companion_box=LEFT_BOX)
        out, _ = run(put(rows, 29, 34, mouth_motion=0.3))
        self.assertEqual(out["name"], COMPANION)

    def test_positions_from_before_the_window_do_not_decide_a_frame(self):
        """Item 4 (r2): six seconds of the companion on the right before the window [6.0, 7.9]; inside it the
        companion is on the left and the user looks left."""
        rows = put(put(rows_of(face(65), [(11, {"yaw_deg": -40.0})], face(4)), 0, 59, companion_box=RIGHT_BOX),
                   60, 79, companion_box=LEFT_BOX)
        out, _ = assess(put(rows, 66, 70, mouth_motion=0.3), 7.9, dataclasses.replace(P, window_s=1.9),
                        landmarker_num_faces=1)
        self.assertEqual(out["name"], COMPANION)
        self.assertIn("yaw_toward_companion@65", ids(out))

    def test_the_companion_side_must_be_known_on_the_turn_frames(self):
        """Item 1 (r3): the companion's side is known only at the first frame (face_cx missing afterwards); the user
        then turns away from where the companion was. Without the side at those frames, 'no yaw toward the companion'
        is not concluded: unknown, not none. A yaw toward the companion seen where the side is known still counts."""
        rows = put(rows_of(face(5), sweep(-1), face(10), extra={**OPTIONAL, "companion_box": RIGHT_BOX}), 1, 18,
                   face_cx=NAN)
        out, _ = run(put(rows, 11, 16, mouth_motion=0.3))
        self.assertEqual(out["name"], UNKNOWN)
        self.assertEqual(out["alternatives"][0]["name"], COMPANION)
        seen = put(rows_of(face(5), sweep(+1), face(10), extra={**OPTIONAL, "companion_box": RIGHT_BOX}), 9, 18,
                   face_cx=NAN)                                         # the side is known up to the turn's end
        out, _ = run(put(seen, 11, 16, mouth_motion=0.3))
        self.assertEqual(out["name"], COMPANION)

    def test_no_companion(self):
        out, _ = run(put(companion_window(sweep(+1)), 0, 18, companion_box=None))
        self.assertEqual(out["name"], NONE)

    def test_a_touch_in_the_window(self):
        out, _ = run(put(companion_window(sweep(+1)), 3, 3, tap_count=1))
        self.assertEqual(out["name"], NONE)

    def test_body_moving(self):
        rows = companion_window(sweep(+1))
        for i, row in enumerate(rows):
            row["shoulder_cx"] = 0.4 + 0.01 * i                            # drifts 0.18 across the window
        out, _ = run(rows)
        self.assertEqual(out["name"], NONE)

    def test_low_face_quality_is_unknown(self):
        """The yaw toward the companion needs the face: with the face seen in under face_visible_min of the frames
        it is missing, so the tag is unknown - an alternative without the yaw cue - not consulting or none."""
        rows = rows_of(face(5), sweep(+1), face(10), [(15, LOST)], extra={**OPTIONAL, "companion_box": RIGHT_BOX})
        out, _ = run(put(rows, 11, 16, mouth_motion=0.3))
        self.assertLess(out["quality"]["face_visible_ratio"], P.face_visible_min)
        self.assertEqual(out["name"], UNKNOWN)
        alternative = out["alternatives"][0]
        self.assertEqual((alternative["name"], alternative["confidence"]), (COMPANION, UNKNOWN))
        self.assertNotIn("yaw_toward_companion", [i["event_id"].split("@")[0] for i in alternative["evidence"]])

    def test_keeps_looking_at_the_companion(self):
        """Item 1: no return to the screen inside the window - the yaw toward the companion still counts."""
        rows = rows_of(face(5), [(15, {"yaw_deg": 45.0})], extra={**OPTIONAL, "companion_box": RIGHT_BOX})
        out, _ = run(put(rows, 8, 13, mouth_motion=0.3))
        self.assertEqual(out["name"], COMPANION)
        self.assertIn("yaw_toward_companion@5", ids(out))

    def test_a_short_companion_presence_counts(self):
        """Item 1: the companion box is there for 0.4 s, under stay_min_s - the decision table asks no stay of it."""
        rows = put(rows_of(face(6), [(3, {"yaw_deg": 45.0})], face(11)), 5, 9, companion_box=RIGHT_BOX)
        out, _ = run(put(rows, 6, 8, mouth_motion=0.3))
        self.assertEqual(out["name"], COMPANION)
        self.assertIn("companion_present@5", ids(out))


class LookingAroundTests(unittest.TestCase):
    """Tag 3 (params P: test values, see the module docstring)."""

    def test_off_screen_turns_dwell_still_nobody_behind(self):
        out, events = run(around_window())
        self.assertEqual(out["name"], AROUND)
        self.assertEqual(out["display_text"], "무언가를 찾는 듯함")
        self.assertEqual(ids(out), ["dwell_no_touch@0", "yaw_sweep_offscreen@14", "yaw_sweep_offscreen@5"])
        self.assertEqual(out["confidence"], {"events": 3, "quality_ok": True})
        self.assertEqual(check_output(out, events, P), [])

    def test_menu_reading_small_yaw(self):
        rows = rows_of(face(3), [(4, {"yaw_deg": 15.0}), (4, {"yaw_deg": -15.0})] * 3, face(3))
        out, events = run(rows)
        self.assertEqual(out["name"], NONE)
        self.assertEqual(kinds(events), ["dwell_no_touch"])

    def test_person_standing_behind(self):
        out, _ = run(put(around_window(), 0, 22, people_behind_count=1))
        self.assertEqual(out["name"], NONE)

    def test_a_touch_in_the_window(self):
        out, _ = run(put(around_window(), 11, 11, tap_count=1))
        self.assertEqual(out["name"], NONE)

    def test_body_moving(self):
        rows = around_window()
        for i, row in enumerate(rows):
            row["shoulder_cx"] = 0.4 + 0.01 * i                            # drifts 0.22 across the window
        out, _ = run(rows)
        self.assertEqual(out["name"], NONE)

    def test_a_touch_seen_rules_out_even_with_counts_missing_elsewhere(self):
        """Item 1 (r2): tap_count is missing on three rows, and a touch is on another: the touch still rules the tag
        out (none, not unknown)."""
        rows = put(around_window(), 11, 11, tap_count=1)
        for row in rows[3:6]:
            row.pop("tap_count")
        out, _ = run(rows)
        self.assertEqual(out["name"], NONE)

    def test_a_person_seen_behind_rules_out_even_with_counts_missing_elsewhere(self):
        """Item 1 (r2): people_behind_count is missing on one row, and a person stands behind on the others."""
        rows = put(around_window(), 0, 22, people_behind_count=1)
        rows[15].pop("people_behind_count")
        out, _ = run(rows)
        self.assertEqual(out["name"], NONE)

    def test_a_body_movement_seen_rules_out_even_with_shoulders_partly_missing(self):
        """Observed evidence first, as for item 1 (r2): the shoulders move where they are seen."""
        rows = around_window()
        for i, row in enumerate(rows):
            row["shoulder_cx"] = 0.4 + 0.01 * i
        out, _ = run(put(rows, 3, 5, shoulder_cx=NAN, shoulder_cy=NAN))
        self.assertEqual(out["name"], NONE)

    def test_a_movement_on_one_axis_counts_with_the_other_axis_missing(self):
        """Item 3 (r3): shoulder_cx drifts beyond body_still_max while shoulder_cy is missing on every row: the
        movement seen on x rules the tag out (none); with x still and y missing, stillness is not concluded."""
        moving = around_window()
        for i, row in enumerate(moving):
            row.update(shoulder_cx=0.4 + 0.01 * i, shoulder_cy=NAN)
        self.assertEqual(run(moving)[0]["name"], NONE)
        self.assertEqual(run(put(around_window(), 0, 22, shoulder_cy=NAN))[0]["name"], UNKNOWN)

    def test_stillness_needs_every_body_frame_observed(self):
        """The shoulders are missing on three body frames and still on the rest: 'still' is not concluded."""
        out, _ = run(put(around_window(), 3, 5, shoulder_cx=NAN, shoulder_cy=NAN))
        self.assertEqual(out["name"], UNKNOWN)

    def test_no_dwell_event_is_needed(self):
        """Item 2: '터치 없음' is no touch in the window; a dwell event only adds support (here dwell_min_s is longer
        than the record, so there is none)."""
        params = dataclasses.replace(P, dwell_min_s=10.0, min_events=2)
        out, events = run(around_window(), params=params)
        self.assertNotIn("dwell_no_touch", kinds(events))
        self.assertEqual((out["name"], out["confidence"]), (AROUND, {"events": 2, "quality_ok": True}))

    def test_one_shoulder_observation_is_not_stillness(self):
        """Item 5: a single shoulder position cannot show the body still: body_still is unknown, so is the tag."""
        rows = put(around_window(), 1, 22, shoulder_cx=NAN, shoulder_cy=NAN)
        out, _ = run(rows)
        self.assertEqual(out["name"], UNKNOWN)
        self.assertEqual([a["name"] for a in out["alternatives"]], [AROUND])


class SceneCueTests(unittest.TestCase):
    """events.observe_scene: the measurements of the scene tags (values made for these frames)."""

    def test_face_height_is_the_median_of_the_main_user_face_rows_without_the_near_ones(self):
        from app.modules.vision.events import observe_scene
        rows = put(rows_of(face(10), extra={**OPTIONAL, "face_cy": 0.5, "iod_ratio_user": 1.0}), 6, 9,
                   face_cy=0.8, iod_ratio_user=1.4)                    # frames 6-9: leaning in, the face lower
        put(rows, 0, 0, face_cy=None, iod_ratio_user=None)             # someone else's face: blank values
        c = observe_scene(rows, (0.0, 0.9))
        (height,) = c.of("face_height")
        self.assertEqual(height["obs"], {"face_cy_median": 0.5, "rows": 9})   # 5 x 0.5 and 4 x 0.8 -> 0.5
        c = observe_scene(rows, (0.0, 0.9), approach_ratio_min=1.3)
        (height,) = c.of("face_height")
        self.assertEqual((height["obs"], c.near_rows), ({"face_cy_median": 0.5, "rows": 5}, 4))
        (size,) = c.of("face_size")
        self.assertEqual(size["obs"], {"iod_ratio_median": 1.0, "rows": 9})
        self.assertEqual(observe_scene(rows_of(face(3)), (0.0, 0.2)).of("face_height", "face_size"), [])

    def test_a_new_main_user_track_and_a_window_with_nobody_seen(self):
        from app.modules.vision.events import observe_scene
        rows = rows_of(face(4), [(6, GONE)], face(4), extra={**OPTIONAL, "primary_track": 1, "head_count": 1})
        put(rows, 4, 9, primary_track=None, head_count=0)
        put(rows, 10, 13, primary_track=2)
        put(rows, 10, 10, main_user_prev_track=1, main_user_gap_s=0.7, main_user_body_kept="False",
            main_user_body_gap_s=0.6)
        c = observe_scene(rows, (0.0, 1.3))
        (change,) = c.of("main_user_changed")
        self.assertEqual(change["obs"], {"track": 2, "previous_track": 1, "gap_s": 0.7, "body_kept": False,
                                         "body_gap_s": 0.6, "previous_h": None, "new_h": None, "h_ratio": None, "new_was_role": None,
                                         "new_rel_dist": None, "new_growth": None, "reacquired": None,
                                         "previous_settled": None, "stitched": None, "new_start_s": None,
                                         "start_shift": None, "start_size": None})
        self.assertTrue(c.track_measured)
        self.assertEqual(c.of("nothing_seen"), [])                     # people seen in part of the window
        (nothing,) = observe_scene(rows, (0.4, 0.9)).of("nothing_seen")
        self.assertEqual((nothing["t_start"], nothing["t_end"]), (0.4, 0.9))
        put(rows, 6, 6, head_count=1)                                  # a head box: somebody is there
        self.assertEqual(observe_scene(rows, (0.4, 0.9)).of("nothing_seen"), [])
        put(rows, 6, 6, head_count=0, aid_count=1, aid_person_count=1)   # a person box of the aid detector: somebody
        self.assertEqual(observe_scene(rows, (0.4, 0.9)).of("nothing_seen"), [])
        put(rows, 6, 6, aid_person_count=0)                            # only a recording-floor box: nobody
        self.assertEqual(len(observe_scene(rows, (0.4, 0.9)).of("nothing_seen")), 1)
        put(rows, 6, 6, aid_count=0, face_count=1)                     # a face-detector box only: somebody
        self.assertEqual(observe_scene(rows, (0.4, 0.9)).of("nothing_seen"), [])
        put(rows, 6, 6, face_count=0)
        put(rows, 6, 6, aid_count="")                                  # a blank change cell is no change
        self.assertEqual(len(observe_scene(put(rows, 0, 13, main_user_prev_track=""), (0.0, 1.3)).of(
            "main_user_changed")), 0)
        self.assertFalse(observe_scene(rows_of(face(3)), (0.0, 0.2)).track_measured)


    def test_seated_height_falls_back_to_the_head_box_where_the_face_cannot_tell(self):
        """The face decides when it can; where it cannot (no face seen, as a seated user low in the frame), the main
        user's head box decides with the head detector and a head value; without a box it cannot tell; without the
        head value the face's reason stands."""
        from app.modules.vision.events import observe_scene
        from app.modules.vision.situation import seated_height
        rows = rows_of([(10, GONE)], extra={**OPTIONAL, "primary_track": 1, "head_count": 1,
                                            "primary_box": "0.40;0.60;0.60;0.90"})       # centre 0.75, no face
        sc = observe_scene(rows, (0.0, 0.9))
        self.assertEqual(seated_height(sc, 0.6, 0.5, seated_head_cy_min=0.7)[0], True)
        self.assertEqual(seated_height(sc, 0.6, 0.5, seated_head_cy_min=0.8)[0], False)
        self.assertEqual(seated_height(sc, 0.6, 0.5)[2], "no_main_user_face")          # face rule without the value
        nobox = observe_scene(put(rows, 0, 9, primary_box=None), (0.0, 0.9))
        self.assertEqual(seated_height(nobox, 0.6, 0.5, seated_head_cy_min=0.7)[2], "no_main_user_box")
        faced = observe_scene(rows_of(face(10), extra={**OPTIONAL, "primary_track": 1, "head_count": 1,
                                                       "face_in_primary": True, "face_cy": 0.5,
                                                       "primary_box": "0.40;0.60;0.60;0.90"}), (0.0, 0.9))
        self.assertEqual(seated_height(faced, 0.6, 0.5, seated_head_cy_min=0.7)[0], False)  # the face decides

    def test_the_head_box_fallback_leaves_out_a_head_grown_by_a_lean(self):
        """The head-box fallback of seated_height: rows whose head box is larger than the user's own reference beyond
        head_approach_ratio_min (a lean brings the head closer and lower) do not count; a seated user's head at
        operating distance (ratio about 1) does."""
        from app.modules.vision.events import observe_scene
        from app.modules.vision.situation import seated_height
        rows = rows_of([(10, GONE)], extra={**OPTIONAL, "primary_track": 1, "head_count": 1,
                                            "primary_box": "0.40;0.60;0.60;0.90", "head_ratio_user": 1.4})
        lean = observe_scene(rows, (0.0, 0.9), head_approach_ratio_min=1.2)
        self.assertEqual((seated_height(lean, 0.6, 0.5, seated_head_cy_min=0.7)[2], lean.head_near_rows),
                         ("head_near", 10))                          # the box is there on every row: not 'no box'
        seated = observe_scene(put(rows, 0, 9, head_ratio_user=1.0), (0.0, 0.9), head_approach_ratio_min=1.2)
        self.assertIs(seated_height(seated, 0.6, 0.5, seated_head_cy_min=0.7)[0], True)

    def test_face_approach_does_not_count_a_bowed_head(self):
        """A larger face while the head is pitched down beyond the camera's head-down boundary is bowing (a phone,
        the counter), not leaning in to read: the window is judged False (as the company-video check counted it);
        facing the screen it is an approach."""
        from app.modules.vision.events import observe_scene
        from app.modules.vision.situation import face_approach
        rows = rows_of(face(10), extra={**OPTIONAL, "iod_ratio_user": 1.4, "dpitch_user_deg": 30.0})
        sc = observe_scene(rows, (0.0, 0.9))
        status, events, reason = face_approach(sc, 1.2, 0.5, head_down_pitch_min=PITCH_TEST)
        self.assertEqual((status, reason), (False, None))
        self.assertEqual(sorted(e["kind"] for e in events), ["face_size", "head_pitch"])
        unchanged = observe_scene(rows_of(face(10), extra={**OPTIONAL, "iod_ratio_user": 1.0,   # bowed, not grown
                                                           "dpitch_user_deg": 30.0}), (0.0, 0.9))
        self.assertEqual(face_approach(unchanged, 1.2, 0.5, head_down_pitch_min=PITCH_TEST)[::2], (False, None))
        self.assertIs(face_approach(sc, 1.2, 0.5)[0], True)                        # no head-down value: not gated
        level = observe_scene(put(rows, 0, 9, dpitch_user_deg=5.0), (0.0, 0.9))
        self.assertIs(face_approach(level, 1.2, 0.5, head_down_pitch_min=PITCH_TEST)[0], True)

    def test_the_head_down_gate_needs_the_share_of_the_window(self):
        """The head-down gate reads a pitch median only when it stands on face_visible_min of the window's frames, as
        the boundary was calibrated: two bowed face rows before the landmarker loses the leaning face do not hide the
        approach (True asks no share)."""
        from app.modules.vision.events import observe_scene
        from app.modules.vision.situation import face_approach
        rows = rows_of(face(2), [(8, GONE)], extra={**OPTIONAL, "iod_ratio_user": 1.4, "dpitch_user_deg": 30.0})
        sc = observe_scene(rows, (0.0, 0.9))
        self.assertEqual(face_approach(sc, 1.2, 0.5, head_down_pitch_min=PITCH_TEST)[::2], (True, None))

    def test_change_evidence_reads_the_same_from_rows_csv_and_a_data_frame(self):
        """Track ids from rows.csv are text ('2') and a data frame gives NaN for an empty cell: the evidence carries
        the same int ids as a replay and None for the empty role, and the output passes its check."""
        from app.modules.vision.events import observe_scene
        rows = rows_of(face(4), extra={**OPTIONAL, "primary_track": "2", "head_count": 1})
        put(rows, 1, 1, main_user_prev_track="1", main_user_gap_s=1.2, main_user_new_was_role=float("nan"))
        (change,) = observe_scene(rows, (0.0, 0.3)).of("main_user_changed")
        self.assertEqual((change["obs"]["track"], change["obs"]["previous_track"], change["obs"]["new_was_role"]),
                         (2, 1, None))
        out, _ = assess(rows, rows[-1]["t_s"], P, landmarker_num_faces=1)
        self.assertIs(out["tags"][2]["status"], True)

    @staticmethod
    def changed_rows(before: dict, after: dict, **flags):
        """20 frames (0.0-1.9 s): main-user track 1 with the values `before` on frames 0-13, track 2 with `after` from
        frame 14, which carries the change (the earlier user settled, not reacquired, not stitched; flags override)."""
        rows = rows_of(face(20), extra={**OPTIONAL, "primary_track": 1, "head_count": 1, "face_in_primary": True,
                                        **before})
        put(rows, 14, 19, primary_track=2, **after)
        return put(rows, 14, 14, main_user_prev_track=1, main_user_prev_settled=True, main_user_reacquired=False,
                   main_user_stitched=False, **flags)

    KEPT = ({"main_user_reacquired": True}, {"main_user_stitched": True}, {"main_user_prev_settled": False})

    def test_after_a_change_of_user_the_face_measures_read_the_new_user_only(self):
        """face_height, face_size, head_pitch (and face_rows, near_rows) after a change of user: the earlier user's
        lower face and bowed head do not reach the new user's seated_height and face_approach. A reacquired or
        stitched track, or a swap before the earlier user settled, keeps the history."""
        from app.modules.vision.events import observe_scene
        from app.modules.vision.situation import face_approach, seated_height
        rows = self.changed_rows({"face_cy": 0.9, "iod_ratio_user": 1.5, "dpitch_user_deg": 30.0},
                                 {"face_cy": 0.3, "iod_ratio_user": 1.5, "dpitch_user_deg": 0.0})
        sc = observe_scene(rows, (0.0, 1.9))
        self.assertEqual([e["obs"] for e in sc.of("face_height", "face_size", "head_pitch")],
                         [{"face_cy_median": 0.3, "rows": 6}, {"iod_ratio_median": 1.5, "rows": 6},
                          {"dpitch_median": 0.0, "rows": 6}])
        self.assertEqual((sc.face_rows, observe_scene(rows, (0.0, 1.9), approach_ratio_min=1.2).near_rows), (6, 6))
        self.assertIs(seated_height(sc, 0.6)[0], False)                   # the new user stands
        self.assertIs(face_approach(sc, 1.2, head_down_pitch_min=PITCH_TEST)[0], True)   # leaning in, not bowed
        for flags in self.KEPT:
            kept = observe_scene(put([dict(r) for r in rows], 14, 14, **flags), (0.0, 1.9))
            self.assertEqual((kept.face_rows, seated_height(kept, 0.6)[0],
                              face_approach(kept, 1.2, head_down_pitch_min=PITCH_TEST)[0]), (20, True, False), flags)

    def test_after_a_change_of_user_the_head_box_measures_read_the_new_user_only(self):
        """head_height and head_size (and head_near_rows) after a change of user: the earlier user's low head box does
        not reach the new user's seated_height (head-box path); reacquire / stitch / a first-approach swap keep it."""
        from app.modules.vision.events import observe_scene
        from app.modules.vision.situation import seated_height
        rows = self.changed_rows({"primary_box": "0.40;0.60;0.60;0.90", "head_ratio_user": 1.4},   # centre 0.75
                                 {"primary_box": "0.40;0.10;0.60;0.40", "head_ratio_user": 1.0})   # centre 0.25
        sc = observe_scene(rows, (0.0, 1.9))
        self.assertEqual([e["obs"] for e in sc.of("head_height", "head_size")],
                         [{"head_cy_median": 0.25, "rows": 6}, {"head_ratio_median": 1.0, "rows": 6}])
        self.assertEqual(observe_scene(rows, (0.0, 1.9), head_approach_ratio_min=1.2).head_near_rows, 0)
        self.assertIs(seated_height(sc, None, seated_head_cy_min=0.5)[0], False)
        for flags in self.KEPT:
            kept = put([dict(r) for r in rows], 14, 14, **flags)
            self.assertEqual((observe_scene(kept, (0.0, 1.9), head_approach_ratio_min=1.2).head_near_rows,
                              seated_height(observe_scene(kept, (0.0, 1.9)), None, seated_head_cy_min=0.5)[0]),
                             (14, True), flags)

    def test_after_a_change_of_user_the_aid_score_reads_the_new_user_only(self):
        """aid_score (and aid_anchor_rows) after a change of user: the earlier user's walking aid does not reach the new
        user's aid_use; reacquire / stitch / a first-approach swap keep it."""
        from app.modules.vision.events import observe_scene
        from app.modules.vision.situation import aid_use
        rows = self.changed_rows({"aid_owner": "yes", "aid_any_score": 0.8}, {"aid_owner": "no", "aid_any_score": 0.1})
        sc = observe_scene(rows, (0.0, 1.9))
        (score,) = sc.of("aid_score")
        self.assertEqual((score["obs"], sc.aid_anchor_rows),
                         ({"aid_any_median": 0.1, "rows": 6, "owner_yes_rows": 0}, 6))
        self.assertIs(aid_use(sc, 0.5)[0], False)
        for flags in self.KEPT:
            kept = observe_scene(put([dict(r) for r in rows], 14, 14, **flags), (0.0, 1.9))
            self.assertEqual((kept.aid_anchor_rows, aid_use(kept, 0.5)[0]), (20, True), flags)

    def test_after_a_change_of_user_the_head_centre_aid_score_reads_the_new_user_only(self):
        """aid_head (the head_centre reading) follows the same cut as aid_score: the earlier user's wheelchair box does
        not reach the new user's aid_use; reacquire / stitch / a first-approach swap keep it."""
        from app.modules.vision.events import observe_scene
        from app.modules.vision.situation import aid_use
        rows = self.changed_rows({"aid_head_score": 0.8, "aid_head_class": "wheelchair"},
                                 {"aid_head_score": 0.0, "aid_head_class": None})
        sc = observe_scene(rows, (0.0, 1.9))
        (score,) = sc.of("aid_head")
        self.assertEqual(score["obs"], {"aid_head_median": 0.0, "rows": 6, "aid_class": None})
        self.assertIs(aid_use(sc, None, aid_rule="head_centre", aid_head_min=0.5)[0], False)
        for flags in self.KEPT:
            kept = observe_scene(put([dict(r) for r in rows], 14, 14, **flags), (0.0, 1.9))
            self.assertEqual(aid_use(kept, None, aid_rule="head_centre", aid_head_min=0.5)[:1], (True,), flags)
            self.assertEqual(kept.of("aid_head")[0]["obs"]["aid_class"], "wheelchair", flags)

    def test_only_the_main_users_face_counts_when_the_head_detector_ran(self):
        """A face matched to no head box while the main user's track lives (face_in_primary None) may be someone
        else's: it gives no face height and no face size. True (also 'True' read back from rows.csv) counts."""
        from app.modules.vision.events import observe_scene
        rows = rows_of(face(10), extra={**OPTIONAL, "face_cy": 0.8, "iod_ratio_user": 1.8, "primary_track": 1,
                                        "face_in_primary": None})
        c = observe_scene(rows, (0.0, 0.9), approach_ratio_min=1.2)
        self.assertEqual((c.of("face_height", "face_size"), c.face_rows), ([], 0))
        put(rows, 0, 9, face_in_primary="True")
        c = observe_scene(rows, (0.0, 0.9), approach_ratio_min=1.2)
        self.assertEqual(len(c.of("face_size")), 1)


class UserChangeCueTests(unittest.TestCase):
    """The three tags' cues of the main user after a change of user in the window (events.user_since): the earlier
    user's behaviour does not reach the new user's tag; a reacquired or stitched track, or a swap before the earlier
    user settled, keeps it (values made for these frames)."""
    KEPT = ({"main_user_reacquired": True}, {"main_user_stitched": True}, {"main_user_prev_settled": False})

    @staticmethod
    def change_at(rows, k, **flags):
        """Main-user track 1 before frame k, track 2 from it; frame k carries the change (settled, not reacquired, not
        stitched; flags override)."""
        put(rows, 0, len(rows) - 1, primary_track=1, head_count=1)
        put(rows, k, len(rows) - 1, primary_track=2)
        return put(rows, k, k, **{"main_user_prev_track": 1, "main_user_prev_settled": True,
                                  "main_user_reacquired": False, "main_user_stitched": False, **flags})

    def test_after_a_change_of_user_the_head_turns_read_the_new_user_only(self):
        """The earlier user's two off-screen sweeps do not make the new user looking_around."""
        def window(**flags):                     # 13 frames of the earlier user, then 27 of the new one
            return self.change_at(rows_of(face(2), sweep(+1), face(2), sweep(-1), face(28)), 13, **flags)
        out, events = run(window())
        self.assertEqual((out["name"], set(kinds(events)) & {"yaw_sweep_offscreen", "look_back"}), (NONE, set()))
        for flags in self.KEPT:
            out, events = run(window(**flags))
            self.assertEqual((out["name"], kinds(events).count("yaw_sweep_offscreen")), (AROUND, 2), flags)

    def test_after_a_change_of_user_the_companion_cues_read_the_new_user_only(self):
        """The earlier user's turn toward the companion and mouth motion do not make the new user consult the
        companion; the companion box (a scene cue) still counts on every row."""
        def window(**flags):
            rows = companion_window(sweep(+1)) + rows_of(face(30), extra={**OPTIONAL, "companion_box": RIGHT_BOX})
            for i, r in enumerate(rows):
                r.update(frame_idx=i, t_s=round(i * DT, 6))
            return self.change_at(rows, 19, **flags)
        out, events = run(window())
        self.assertEqual((out["name"], set(kinds(events)) & {"yaw_toward_companion", "mouth_moving"}), (NONE, set()))
        self.assertIn("companion_present", kinds(events))
        for flags in self.KEPT:
            self.assertEqual(run(window(**flags))[0]["name"], COMPANION, flags)

    def test_after_a_change_of_user_the_body_and_presence_checks_read_the_new_user_only(self):
        """body_still (also phone_use's body condition), track_conf, face_visible_ratio and the dwell after a change:
        the earlier user's moving shoulders do not make the new user move; the ratios count the new user's rows over
        the window's frames."""
        def window(**flags):
            rows = rows_of(face(40))
            for i in range(20):
                rows[i]["shoulder_cx"] = 0.40 + 0.01 * i                  # the earlier user walks off
            c = observe_window(self.change_at(rows, 20, **flags), (0.0, 3.9), P, landmarker_num_faces=1)
            (dwell,) = c.of("dwell_no_touch")
            return c.body_still, c.track_conf, c.face_visible_ratio, dwell["t_start"]
        self.assertEqual(window(), (True, 0.5, 0.5, 2.0))
        for flags in self.KEPT:
            self.assertEqual(window(**flags), (False, 1.0, 1.0, 0.0), flags)


class SceneTagTests(unittest.TestCase):
    """The second list `tags` of situation.assess (values made for these frames, not proposals)."""

    @staticmethod
    def tags(out):
        return {t["name"]: (t["status"], t["unknown_reason"]) for t in out["tags"]}

    def test_without_values_or_columns_the_tags_say_why_they_cannot_tell(self):
        from app.modules.vision.situation import SCENE_TAGS
        out, events = run(rows_of(face(10)))
        self.assertEqual([t["name"] for t in out["tags"]], list(SCENE_TAGS))
        self.assertEqual(self.tags(out), {"seated_height": (UNKNOWN, "no_value_for_camera"),
                                          "face_approach": (UNKNOWN, "no_value"),
                                          "user_changed": (UNKNOWN, "column:primary_track"),
                                          "none_seen": (False, None), "aid_use": (UNKNOWN, "column:aid_owner"),
                                          "phone_use": (UNKNOWN, "column:phone_owner")})
        self.assertEqual([t["display_text"] for t in out["tags"]],
                         ["앉은 높이", "얼굴 접근", "사용자 교체 가능성", "카메라에 사람이 안 보임", "보조기구 사용 중",
                          "잠시 딴 일 중(휴대폰)"])
        self.assertEqual(check_output(out, events, P), [])

    def test_seated_height_and_face_approach_compare_window_medians(self):
        from app.modules.vision.situation import assess
        rows = rows_of(face(10), extra={**OPTIONAL, "face_cy": 0.7, "iod_ratio_user": 1.0})
        t = rows[-1]["t_s"]
        out, _ = assess(rows, t, P, landmarker_num_faces=1, seated_face_cy_min=0.6, approach_ratio_min=1.2)
        self.assertEqual(self.tags(out)["seated_height"], (True, None))
        self.assertEqual(self.tags(out)["face_approach"], (False, None))
        (item,) = [e for e in out["tags"][0]["evidence"] if e["obs"] == "face_cy_median"]
        self.assertEqual(item["value"], 0.7)
        out, _ = assess(rows, t, P, landmarker_num_faces=1, seated_face_cy_min=0.75)
        self.assertEqual(self.tags(out)["seated_height"], (False, None))
        out, _ = assess(rows, t, P, landmarker_num_faces=1, seated_face_cy_min=0.7, approach_ratio_min=1.0)
        self.assertEqual((self.tags(out)["seated_height"], self.tags(out)["face_approach"]),
                         ((False, None), (False, None)))               # equal to the value is not above it
        lean = put(rows_of(face(10), extra={**OPTIONAL, "face_cy": 0.5, "iod_ratio_user": 1.0}), 3, 9,
                   face_cy=0.8, iod_ratio_user=1.4)              # 7 of 10 rows leaning in: the face lower and larger
        out, _ = assess(lean, t, P, landmarker_num_faces=1, seated_face_cy_min=0.6, approach_ratio_min=1.2)
        self.assertEqual(self.tags(out)["face_approach"], (True, None))
        self.assertEqual(self.tags(out)["seated_height"], (UNKNOWN, "too_few_rows"))   # 3 of 10 rows left, < 0.6
        out, _ = assess(lean, t, P, landmarker_num_faces=1, seated_face_cy_min=0.6)
        self.assertEqual(self.tags(out)["seated_height"], (True, None))    # no approach value: nothing left out
        away = rows_of(face(10), extra={**OPTIONAL, "face_cy": None, "iod_ratio_user": None})
        out, _ = assess(away, t, P, landmarker_num_faces=1, seated_face_cy_min=0.6, approach_ratio_min=1.2)
        self.assertEqual((self.tags(out)["seated_height"], self.tags(out)["face_approach"]),
                         ((UNKNOWN, "no_main_user_face"), (UNKNOWN, "no_main_user_face")))
        unref = rows_of(face(10), extra={**OPTIONAL, "face_cy": 0.7, "iod_ratio_user": None})
        out, _ = assess(unref, t, P, landmarker_num_faces=1, seated_face_cy_min=0.6, approach_ratio_min=1.2)
        self.assertEqual(self.tags(out)["face_approach"], (UNKNOWN, "no_reference"))   # a face, no reference yet
        near = rows_of(face(10), extra={**OPTIONAL, "face_cy": 0.8, "iod_ratio_user": 1.4})
        out, _ = assess(near, t, P, landmarker_num_faces=1, seated_face_cy_min=0.6, approach_ratio_min=1.2)
        self.assertEqual(self.tags(out)["seated_height"], (UNKNOWN, "face_near"))      # every face row leans in

    def test_user_changed_and_none_seen(self):
        rows = rows_of(face(5), [(10, GONE)], face(5), extra={**OPTIONAL, "primary_track": 1, "head_count": 1})
        put(rows, 5, 14, primary_track=None, head_count=0)
        put(rows, 15, 19, primary_track=2)
        put(rows, 15, 15, main_user_prev_track=1, main_user_gap_s=1.1, main_user_body_kept=False)
        out, _ = run(rows)
        self.assertEqual(self.tags(out)["user_changed"], (True, None))
        self.assertEqual(self.tags(out)["none_seen"], (False, None))
        changed = out["tags"][2]["evidence"]
        self.assertEqual({e["obs"]: e["value"] for e in changed if e["value"] is not None},
                         {"track": 2, "previous_track": 1, "gap_s": 1.1, "body_kept": False})
        out, _ = assess(rows, 1.4, dataclasses.replace(P, window_s=0.9), landmarker_num_faces=1)
        self.assertEqual(self.tags(out)["none_seen"], (True, None))        # 0.5 .. 1.4 s: nothing seen
        self.assertEqual(self.tags(out)["user_changed"], (False, None))    # the column on every row, no change

    def test_the_scene_columns_do_not_leak_into_the_three_tags(self):
        """Scene columns, with a track change on the second row that is not a new user (reacquired in the same place),
        leave the three tags, their evidence and their events as they are. With the change counted as a new user the
        scene tags follow its cut: the earlier user's first row (standing, near, no aid) is not read, and the new
        user's rows make seated_height, aid_use true and face_approach false (the three tags then read the new user's
        rows too: test_after_a_change_of_user_the_three_tags_read_the_new_user_only)."""
        from app.modules.vision.situation import assess
        windows = [put(rows_of(face(5), look_back(), face(5), look_back(), face(5)), 0, 30, people_behind_count=1),
                   companion_window(sweep(+1)), around_window(), rows_of(face(10))]
        for rows in windows:
            t = rows[-1]["t_s"]
            plain, plain_events = assess(rows, t, P, landmarker_num_faces=1)
            marked = [dict(r) for r in rows]
            for i, r in enumerate(marked):          # scene columns that move the scene tags
                r.update(face_cy=0.9, iod_ratio_user=1.1, primary_track=1 + (i >= 1),
                         head_count=1, aid_owner="yes", aid_any_score=0.8)
            marked[0].update(face_cy=0.3, iod_ratio_user=1.5, aid_owner="no", aid_any_score=0.1)   # the earlier user
            marked[1].update(main_user_prev_track=1, main_user_gap_s=0.1, main_user_body_kept=True)
            same = [dict(r) for r in marked]
            same[1].update(main_user_reacquired=True)   # the same user found again: no cut
            kept, kept_events = assess(same, t, P, landmarker_num_faces=1, seated_face_cy_min=0.6,
                                       approach_ratio_min=1.2, aid_use_min=0.5)
            self.assertEqual({k: v for k, v in kept.items() if k != "tags"},
                             {k: v for k, v in plain.items() if k != "tags"})
            self.assertEqual(kept_events, plain_events)
            out, events = assess(marked, t, P, landmarker_num_faces=1, seated_face_cy_min=0.6,
                                 approach_ratio_min=1.2, aid_use_min=0.5)
            self.assertEqual([t["status"] for t in out["tags"]], [True, False, True, False, True, UNKNOWN])
            scene = {t["name"]: {e["obs"]: e["value"] for e in t["evidence"]} for t in out["tags"]}
            self.assertEqual((scene["seated_height"]["face_cy_median"], scene["aid_use"]["aid_any_median"],
                              scene["face_approach"]["iod_ratio_median"]), (0.9, 0.8, 1.1))   # row 0 not read
            self.assertEqual((scene["aid_use"]["rows"], scene["aid_use"]["owner_yes_rows"]), (len(rows) - 1,) * 2)

    def test_aid_use_reads_the_main_users_box_only_when_the_detector_ran(self):
        from app.modules.vision.situation import assess
        rows = rows_of(face(10), extra={**OPTIONAL, "aid_owner": "yes", "aid_any_score": 0.7})
        t = rows[-1]["t_s"]

        def tag(rows, **values):
            out, _ = assess(rows, t, P, landmarker_num_faces=1, **values)
            return self.tags(out)["aid_use"]
        self.assertEqual(tag(rows, aid_use_min=0.5), (True, None))
        self.assertEqual(tag(rows, aid_use_min=0.9), (False, None))
        self.assertEqual(tag(rows), (UNKNOWN, "no_value"))                      # no value given (a bundle's null)
        others = rows_of(face(10), extra={**OPTIONAL, "aid_owner": "no", "aid_any_score": 0.1})
        self.assertEqual(tag(others, aid_use_min=0.5), (False, None))           # an aid on someone else: not counted
        mixed = rows_of(face(10), extra={**OPTIONAL, "aid_owner": "no", "aid_any_score": 0.4})   # pedestrian on top
        self.assertEqual(tag(mixed, aid_use_min=0.35), (True, None))    # the score decides, as the validation rule
        few = put(rows_of(face(10), extra={**OPTIONAL, "aid_owner": "yes", "aid_any_score": None}), 0, 2,
                  aid_any_score=0.7)                                            # 3 rows of 10 carry the score
        self.assertEqual(tag(few, aid_use_min=0.5), (UNKNOWN, "too_few_rows"))
        nobox = rows_of(face(10), extra={**OPTIONAL, "aid_owner": "no", "aid_any_score": None})
        self.assertEqual(tag(nobox, aid_use_min=0.5), (UNKNOWN, "no_user_box"))
        noanchor = rows_of(face(10), extra={**OPTIONAL, "aid_owner": "unknown", "aid_any_score": None})
        self.assertEqual(tag(noanchor, aid_use_min=0.5), (UNKNOWN, "no_anchor"))
        self.assertEqual(tag(rows_of(face(10)), aid_use_min=0.5), (UNKNOWN, "column:aid_owner"))   # detector off

    def test_aid_use_under_the_head_centre_reading_reads_the_aid_class_box_at_the_users_head(self):
        """aid_rule head_centre (the kiosk-view detector files): the same window logic on aid_head_score - the median of
        the rows with the main user's head box above aid_head_min, too few rows unknown - and the evidence names the
        class behind the median. No cut: unknown (no_value_for_model), whatever aid_use_min says; the column missing
        (the detector off, or rows of the owner_box reading): column:aid_head_score; no head box on any row:
        no_main_user_box; a head box with no aid box around its centre (0.0) is a value. The default reading reads
        aid_any_score as before and ignores these columns and the cut."""
        from app.modules.vision.situation import assess
        head = {**OPTIONAL, "aid_owner": "no", "aid_any_score": 0.05, "aid_head_score": 0.7,
                "aid_head_class": "wheelchair"}

        def window(rows, **values):
            out, _ = assess(rows, rows[-1]["t_s"], P, landmarker_num_faces=1, **values)   # check_output runs inside
            return self.tags(out)["aid_use"], {e["obs"]: e["value"] for e in out["tags"][4]["evidence"]}

        def tag(rows, **values):
            return window(rows, **values)[0]
        rows = rows_of(face(10), extra=head)
        self.assertEqual(window(rows, aid_rule="head_centre", aid_head_min=0.5),
                         ((True, None), {"aid_head_median": 0.7, "rows": 10, "aid_class": "wheelchair"}))
        self.assertEqual(tag(rows, aid_rule="head_centre", aid_head_min=0.7), (False, None))   # equal is not above
        self.assertEqual(tag(rows, aid_rule="head_centre"), (UNKNOWN, "no_value_for_model"))
        self.assertEqual(tag(rows, aid_rule="head_centre", aid_use_min=0.5), (UNKNOWN, "no_value_for_model"))
        self.assertEqual(window(rows, aid_use_min=0.5),                     # the default reading, as before
                         ((False, None), {"aid_any_median": 0.05, "rows": 10, "owner_yes_rows": 0}))
        self.assertEqual(tag(rows, aid_use_min=0.5, aid_head_min=0.5), (False, None))   # a cut alone switches nothing
        zero = rows_of(face(10), extra={**head, "aid_head_score": 0.0, "aid_head_class": None})
        self.assertEqual(window(zero, aid_rule="head_centre", aid_head_min=0.5),
                         ((False, None), {"aid_head_median": 0.0, "rows": 10, "aid_class": None}))
        nohead = rows_of(face(10), extra={**head, "aid_head_score": None, "aid_head_class": None})
        self.assertEqual(tag(nohead, aid_rule="head_centre", aid_head_min=0.5), (UNKNOWN, "no_main_user_box"))
        few = put(rows_of(face(10), extra={**head, "aid_head_score": None, "aid_head_class": None}), 0, 2,
                  aid_head_score=0.7, aid_head_class="wheelchair")      # 3 rows of 10 carry the score
        self.assertEqual(tag(few, aid_rule="head_centre", aid_head_min=0.5), (UNKNOWN, "too_few_rows"))
        owner = rows_of(face(10), extra={**OPTIONAL, "aid_owner": "yes", "aid_any_score": 0.7})
        self.assertEqual(tag(owner, aid_rule="head_centre", aid_head_min=0.5), (UNKNOWN, "column:aid_head_score"))
        self.assertEqual(tag(rows_of(face(10)), aid_rule="head_centre", aid_head_min=0.5),
                         (UNKNOWN, "column:aid_head_score"))
        mixed = put(put(rows_of(face(11), extra=head), 0, 4, aid_head_score=0.2, aid_head_class="cane"), 5, 5,
                    aid_head_score=0.6, aid_head_class="crutch")       # 0.2 x 5 (cane), 0.6 (crutch), 0.7 x 5
        self.assertEqual(window(mixed, aid_rule="head_centre", aid_head_min=0.5)[1],
                         {"aid_head_median": 0.6, "rows": 11, "aid_class": "crutch"})
        even = put(rows_of(face(10), extra=head), 0, 4, aid_head_score=0.2, aid_head_class="cane")
        status, evidence = window(even, aid_rule="head_centre", aid_head_min=0.5)
        self.assertEqual((status, evidence["aid_class"]), ((False, None), "wheelchair"))   # the upper middle row
        self.assertAlmostEqual(evidence["aid_head_median"], 0.45)
        with self.assertRaises(ValueError):
            tag(rows, aid_rule="largest")

    def test_a_stitched_track_break_is_no_change(self):
        rows = rows_of(face(5), face(5), extra={**OPTIONAL, "primary_track": 1, "head_count": 1})
        put(rows, 5, 9, primary_track=2)
        put(rows, 5, 5, main_user_prev_track=1, main_user_gap_s=1.1, main_user_body_kept=True,
            main_user_reacquired=False, main_user_stitched=True, main_user_new_start_s=0.1)   # broke in place
        out, _ = run(rows)
        self.assertEqual(self.tags(out)["user_changed"], (False, None))
        evidence = {e["obs"]: e["value"] for e in out["tags"][2]["evidence"]}
        self.assertEqual(evidence, {})                             # the stitched switch is no evidence of a change
        put(rows, 5, 5, main_user_stitched=False)
        self.assertEqual(self.tags(run(rows)[0])["user_changed"], (True, None))
        put(rows, 5, 5, main_user_stitched=None)                    # no boundary: counted as before
        self.assertEqual(self.tags(run(rows)[0])["user_changed"], (True, None))
        put(rows, 5, 5, main_user_stitched=True, main_user_reacquired=True)   # both: the stitch's time bound decides
        self.assertEqual(self.tags(run(rows)[0])["user_changed"], (False, None))

    def test_phone_use_needs_the_phone_in_min_events_segments_no_touch_and_a_still_body(self):
        """phone_use (3-2's phone path): the phone at the main user in at least min_events (3 here) of the window's
        segment_s segments, no touch in the window, the body still; three-valued like the tags. The phone in the hand
        counts only while the main user does not face the screen (away True); the phone at the head counts whatever
        the head direction."""
        from app.modules.vision.situation import assess
        rows = rows_of(face(40), extra={**OPTIONAL, "phone_owner": "no", "phone_at": None, "phone_score": None})
        t = rows[-1]["t_s"]                                      # 3.9 s; window 20 s holds four 1-s segments

        def tag(rows, window_s=4.0, away=True):
            out, _ = assess(rows, t, dataclasses.replace(P, window_s=window_s), landmarker_num_faces=1,
                            segment_s=1.0, away=away)           # assess runs check_output with the scene events
            return self.tags(out)["phone_use"], {t["name"]: t for t in out["tags"]}["phone_use"]["evidence"]
        self.assertEqual(tag(rows)[0], (False, None))
        put(rows, 5, 5, phone_owner="yes", phone_at="hand", phone_score=0.4)       # segment (-0.1, 0.9]
        put(rows, 15, 15, phone_owner="yes", phone_at="head", phone_score=0.5)     # (0.9, 1.9]
        self.assertEqual(tag(rows)[0], (False, None))            # two of four segments, < 3
        put(rows, 25, 25, phone_owner="yes", phone_at="hand", phone_score=0.6)     # (1.9, 2.9]
        status, evidence = tag(rows)
        self.assertEqual(status, (True, None))
        kinds = {round(e["t"], 1): e["event_id"].split("@")[0] for e in evidence}
        self.assertEqual(kinds, {0.5: "phone_in_hand", 1.5: "phone_at_head", 2.5: "phone_in_hand"})   # per segment
        self.assertEqual(tag(rows, away=False)[0], (False, None))   # facing the screen: the hand rows do not count
        self.assertEqual(tag(rows, away=None)[0], (UNKNOWN, "gaze_unknown"))   # the hand path needs the direction
        at_head = put([dict(r) for r in rows], 5, 25, phone_at="head")
        self.assertEqual(tag(at_head, away=False)[0], (True, None))   # a call: the head path reads no direction
        self.assertEqual(tag(at_head, away=None)[0], (True, None))
        self.assertEqual(tag(put([dict(r) for r in rows], 33, 33, tap_count=1))[0], (False, None))   # a touch
        self.assertEqual(tag(put([dict(r) for r in rows], 30, 39, shoulder_cx=0.9))[0], (False, None))   # moved
        strided = put([dict(r) for r in rows], 0, 39, phone_owner=None)        # the detector did not run there ...
        for k in (5, 15, 25, 30, 35):
            strided[k].update(rows[k])                                         # ... except on these rows
        self.assertEqual(tag(strided)[0], (True, None))          # blank rows are skipped, not 'cannot tell'
        two = put([dict(r) for r in strided], 25, 25, phone_owner="no")        # two 'yes', the rest 'no' and blank
        self.assertEqual(tag(two)[0], (False, None))             # the blank rows add no 'cannot tell' segment
        self.assertEqual(tag(put(strided, 25, 39, phone_owner=None))[0], (UNKNOWN, "phone_owner_unknown"))   # 2 yes, 2 not run
        unsure = put([dict(r) for r in rows], 20, 29, phone_owner="unknown")   # segment 3 cannot tell
        self.assertEqual(tag(unsure)[0], (UNKNOWN, "phone_owner_unknown"))
        self.assertEqual(tag(put([dict(r) for r in rows], 0, 39, tap_count=None))[0], (UNKNOWN, "column:tap_count"))
        edges = put(rows_of(face(40), extra={**OPTIONAL, "phone_owner": "no", "phone_at": None}), 19, 19,
                    phone_owner="yes", phone_at="head")                        # t 1.9: the end of (0.9, 1.9]
        put(edges, 29, 29, phone_owner="yes", phone_at="head")                 # t 2.9: the end of (1.9, 2.9]
        put(edges, 39, 39, phone_owner="yes", phone_at="head")                 # t 3.9: the end of (2.9, 3.9]
        self.assertEqual(tag(edges)[0], (True, None))            # a row on a segment's end belongs to that segment
        out, _ = assess(rows, t, dataclasses.replace(P, window_s=4.0), landmarker_num_faces=1)   # no segment_s
        self.assertEqual(self.tags(out)["phone_use"], (UNKNOWN, "no_segments"))

    def test_reacquisition_unknown_reasons_and_frames_first(self):
        from app.modules.vision.events import observe_scene
        from app.modules.vision.situation import scene_tags
        rows = rows_of(face(5), face(5), extra={**OPTIONAL, "primary_track": 1, "head_count": 1})
        put(rows, 5, 9, primary_track=2)
        put(rows, 5, 5, main_user_prev_track=1, main_user_gap_s=1.3, main_user_body_kept=True,
            main_user_reacquired=True)                                       # the same place: a cap, not a new user
        out, _ = run(rows)
        self.assertEqual(self.tags(out)["user_changed"], (UNKNOWN, "reacquired_same_place"))
        put(rows, 5, 5, main_user_reacquired=False)
        self.assertEqual(self.tags(run(rows)[0])["user_changed"], (True, None))
        put(rows, 5, 5, main_user_prev_settled=False)                       # during the first approach: no change
        self.assertEqual(self.tags(run(rows)[0])["user_changed"], (False, None))
        put(rows, 5, 5, main_user_prev_settled="True")
        nohead = rows_of([(10, GONE)])                                       # nobody seen, no head detector
        self.assertEqual(self.tags(run(nohead)[0])["none_seen"], (UNKNOWN, "column:head_count"))
        empty = scene_tags(observe_scene(rows, (5.0, 6.0)), seated_face_cy_min=0.6, approach_ratio_min=1.2,
                           aid_use_min=0.5, min_share=0.6)
        self.assertEqual({t["unknown_reason"] for t in empty}, {"no_frames"})
        few = put(rows_of(face(10), extra={**OPTIONAL, "face_cy": None, "iod_ratio_user": None}), 0, 2,
                  face_cy=0.9, iod_ratio_user=1.5)                            # 3 face rows of 10
        tags = self.tags(assess(few, few[-1]["t_s"], P, landmarker_num_faces=1, seated_face_cy_min=0.6,
                                approach_ratio_min=1.2)[0])
        self.assertEqual((tags["seated_height"], tags["face_approach"]),
                         ((UNKNOWN, "face_near"), (True, None)))    # the lean loses the face: no share asked
        lost = put(rows_of(face(10), extra={**OPTIONAL, "face_cy": None, "iod_ratio_user": None}), 0, 0,
                   face_cy=0.5, iod_ratio_user=1.0)                           # one face row, then the face is lost
        tags = self.tags(assess(lost, lost[-1]["t_s"], P, landmarker_num_faces=1, seated_face_cy_min=0.6,
                                approach_ratio_min=1.2)[0])
        self.assertEqual(tags["face_approach"], (UNKNOWN, "too_few_rows"))   # False needs the share

    def test_check_rules_for_the_tags(self):
        from app.modules.vision.events import observe_scene
        rows = rows_of(face(10), extra={**OPTIONAL, "face_cy": 0.7})
        out, events = assess(rows, rows[-1]["t_s"], P, landmarker_num_faces=1, seated_face_cy_min=0.6)
        scene = observe_scene(rows, out["window_s"]).events
        self.assertEqual(check_output(out, events, P, scene_events=scene), [])
        self.assertTrue(check_output(out, events, P))                       # its evidence needs the scene events

        def broken(**over):
            tags = [dict(t) for t in out["tags"]]
            tags[0].update(over)
            return check_output({**out, "tags": tags}, events, P, scene_events=scene)
        self.assertTrue(broken(status="maybe"))
        self.assertTrue(broken(status=1))
        self.assertTrue(broken(status=1.0))                                     # equal to True, but not a bool
        self.assertTrue(broken(display_text="휠체어"))
        self.assertTrue(broken(unknown_reason="no_value"))                 # a reason with a definite status
        self.assertTrue(broken(status=UNKNOWN, unknown_reason=None))
        self.assertTrue(broken(unknown_reason={}))                         # any reason with a definite status
        self.assertTrue(broken(status=UNKNOWN, unknown_reason=""))         # unknown needs a non-empty text
        self.assertTrue(broken(status=UNKNOWN, unknown_reason={}))
        self.assertTrue(check_output({**out, "tags": out["tags"][::-1]}, events, P, scene_events=scene))
        self.assertTrue(check_output({k: v for k, v in out.items() if k != "tags"}, events, P))


class GoldenOutputTests(unittest.TestCase):
    """The three tags' output against the code before the scene tags: tests/data/situation_golden_main.json was made
    by origin/main's events.py and situation.py (a3143a5) on golden_windows(). Here the new code runs on the same windows with
    every scene column set and every scene value given, and must give the same output outside `tags`. The track
    change in the middle is marked reacquired: a change that brings a new user cuts the main user's cues by design
    (events.user_since; SceneCueTests and the round-5 tests)."""

    def test_the_three_tags_match_the_code_before_the_scene_tags(self):
        import json
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "situation_golden_main.json")
        with open(path, encoding="utf-8") as f:
            golden = json.load(f)
        windows = golden_windows()
        self.assertEqual(sorted(golden), sorted(name for name, *_ in windows))
        for name, rows, over, faces in windows:
            marked = [dict(r, face_cy=0.9, iod_ratio_user=1.5, primary_track=1 + (i >= len(rows) // 2), head_count=1,
                           aid_owner="yes", aid_any_score=0.8, aid_count=1) for i, r in enumerate(rows)]
            marked[len(rows) // 2].update(main_user_prev_track=1, main_user_gap_s=0.1, main_user_body_kept=True,
                                          main_user_reacquired=True)   # not a new user: the main user's cues stay
            out, events = assess(marked, rows[-1]["t_s"], dataclasses.replace(P, **over), landmarker_num_faces=faces,
                                 seated_face_cy_min=0.6, approach_ratio_min=1.2, aid_use_min=0.5)
            out = json.loads(json.dumps({k: v for k, v in out.items() if k != "tags"}))
            self.assertEqual(out, golden[name]["output"], name)
            self.assertEqual([e["event_id"] for e in events], golden[name]["event_ids"], name)


class UnknownAndAlternativesTests(unittest.TestCase):
    """'unknown', alternatives and ties (params P: test values, see the module docstring)."""

    def test_fewer_events_than_min_events(self):
        out, events = run(around_window(), params=dataclasses.replace(P, min_events=4))
        self.assertEqual((out["name"], out["confidence"], out["evidence"]), (UNKNOWN, UNKNOWN, []))
        self.assertEqual([(a["name"], a["confidence"]) for a in out["alternatives"]], [(AROUND, UNKNOWN)])
        self.assertEqual(check_output(out, events, dataclasses.replace(P, min_events=4)), [])

    def test_sensor_failure_body_not_tracked(self):
        rows = around_window()
        for row in rows[:16]:
            row.update(body_state=NOT_SEEN, pose_vis_shoulders=NAN, shoulder_cx=NAN, shoulder_cy=NAN)
        out, _ = run(rows)
        self.assertLess(out["quality"]["track_conf"], P.track_conf_min)
        self.assertEqual((out["name"], out["confidence"], out["alternatives"]), (UNKNOWN, UNKNOWN, []))

    def test_required_input_missing(self):
        """No people_behind_count column: 'nobody behind' cannot be told, so looking_around is unknown, not none."""
        out, _ = run(around_window(drop=("people_behind_count",)))
        self.assertEqual(out["name"], UNKNOWN)
        self.assertEqual([a["name"] for a in out["alternatives"]], [AROUND])

    def test_features_columns_only_give_unknown_and_evidence_only_alternatives(self):
        """Today's observations.csv has none of the optional columns: no tag can be ruled in or out, so the output is
        'unknown' - never 'none' - and only a tag with supporting events is listed as an alternative."""
        drop = tuple(OPTIONAL) + ("shoulder_cx", "shoulder_cy")
        out, _ = run(rows_of([(30, {"yaw_deg": 2.0})], extra={}, drop=drop))      # reading the screen, small yaw
        self.assertEqual((out["name"], out["alternatives"]), (UNKNOWN, []))
        out, _ = run(rows_of(face(30), extra={}, drop=drop))     # yaw exactly 0 throughout: toward no side at all
        self.assertEqual(out["name"], NONE)
        out, _ = run(rows_of(face(5), sweep(+1), face(5), sweep(-1), face(5), extra={}, drop=drop))
        self.assertEqual(out["name"], UNKNOWN)
        self.assertEqual([(a["name"], a["confidence"]) for a in out["alternatives"]], [(AROUND, UNKNOWN)])

    def test_two_tags_the_one_with_more_events_wins(self):
        out, events = run(companion_window(sweep(+1), face(3), sweep(+1)))
        self.assertEqual(out["name"], COMPANION)
        self.assertEqual(out["confidence"]["events"], 5)
        self.assertEqual([(a["name"], a["confidence"]) for a in out["alternatives"]],
                         [(AROUND, {"events": 3, "quality_ok": True})])
        self.assertEqual(check_output(out, events, P), [])

    def test_an_alternative_below_min_events_is_unknown(self):
        """Item 6: the same min_events floor as the name: looking_around has 3 events, k = 4."""
        out, _ = run(companion_window(sweep(+1), face(3), sweep(+1)), params=dataclasses.replace(P, min_events=4))
        self.assertEqual(out["name"], COMPANION)
        self.assertEqual([(a["name"], a["confidence"]) for a in out["alternatives"]], [(AROUND, UNKNOWN)])

    def test_a_tie_is_unknown_with_both_alternatives(self):
        out, _ = run(companion_window(sweep(+1), face(3), sweep(-1), face(3), sweep(-1)))
        self.assertEqual(out["name"], UNKNOWN)
        self.assertEqual([(a["name"], a["confidence"]["events"]) for a in out["alternatives"]],
                         [(COMPANION, 4), (AROUND, 4)])


class WindowTests(unittest.TestCase):
    """The window slides with t_end (params P with a shorter window_s: test values, see the module docstring)."""

    def test_state_is_kept_while_its_events_lie_inside_the_window_and_expires_after(self):
        """Item 7 (r3): a turn counts while all its rows lie inside the window; a state that goes on (the person
        behind) gives its part inside the window."""
        rows = put(rows_of(face(5), look_back(), face(5), look_back(), face(55)), 0, 30, people_behind_count=1)
        params = dataclasses.replace(P, window_s=3.0)
        outs = {t: assess(rows, t, params, landmarker_num_faces=1)[0] for t in (3.0, 3.4, 4.0)}
        self.assertEqual([outs[t]["name"] for t in (3.0, 3.4, 4.0)], [BEHIND, BEHIND, NONE])
        self.assertIn("look_back@5", ids(outs[3.4]))     # rows 0.5-1.3 s inside [0.4, 3.4]; not all in [1.0, 4.0]
        self.assertIn("people_behind@4", ids(outs[3.4]))     # the part from 0.4 s, the window start

    def test_a_touch_counts_in_the_window_its_row_belongs_to(self):
        """Item 5 (r2): a row's counts belong to the interval that ends at its time, and the row to the window its
        time is in. Window [0.45, 2.2]: a touch on row 4 (0.4 s) is outside it, one on row 5 (0.5 s) inside."""
        params = dataclasses.replace(P, window_s=1.75)
        before, _ = assess(put(around_window(), 4, 4, tap_count=1), 2.2, params, landmarker_num_faces=1)
        inside, _ = assess(put(around_window(), 5, 5, tap_count=1), 2.2, params, landmarker_num_faces=1)
        self.assertEqual((before["name"], inside["name"]), (AROUND, NONE))

    def test_a_turn_keeps_its_facing_frame_from_before_the_window(self):
        """Item 7: the facing frame before the first turn (0.4 s) lies just before the window [0.45, 3.0]."""
        rows = put(rows_of(face(5), look_back(), face(5), look_back(), face(5)), 0, 30, people_behind_count=1)
        out, _ = assess(rows, 3.0, dataclasses.replace(P, window_s=2.55), landmarker_num_faces=1)
        self.assertEqual(out["name"], BEHIND)
        self.assertIn("look_back@5", ids(out))


class CheckRuleTests(unittest.TestCase):
    """check_output on outputs changed by hand (params P: test values, see the module docstring)."""

    def setUp(self):
        rows = put(rows_of(face(5), look_back(), face(5), look_back(), face(5)), 0, 30, people_behind_count=1)
        self.out, self.events = run(rows)
        self.assertEqual(check_output(self.out, self.events, P), [])

    def changed(self, **values):
        return check_output({**self.out, **values}, self.events, P)

    def test_evidence_must_name_an_event_of_the_window(self):
        evidence = [dict(self.out["evidence"][0], event_id="look_back@999")] + self.out["evidence"][1:]
        self.assertTrue(any("no event of this window" in p for p in self.changed(evidence=evidence)))

    def test_evidence_rows_must_lie_inside_the_window(self):
        """Item 7 (r3): an event is evidence only when all its observation rows lie inside the window (dec section 3
        '전부 같은 창 안'); t is the event's end."""
        problems = self.changed(window_s=[1.0, 3.0])                    # look_back@5 has rows from 0.5 s
        self.assertTrue(any("look_back@5 has rows outside the window" in p for p in problems))
        self.assertEqual(self.changed(window_s=[0.0, 3.0]), [])
        evidence = [dict(item, t=0.5) if item["event_id"] == "look_back@5" else item for item in self.out["evidence"]]
        self.assertTrue(any("is not the end" in p for p in self.changed(evidence=evidence)))

    def test_a_malformed_window_or_quality_gives_problems_not_errors(self):
        """Item 5 (r3): window_s must be [start, end] with finite start <= end, and quality must carry both ratios in
        [0, 1]; a malformed output gives problems instead of an exception. An empty window (no frames) is 'unknown'
        with empty ratios."""
        for window in ([3.0], [3.0, 1.0], [NAN, 3.0], "w", None):
            self.assertTrue(any("window_s" in p for p in self.changed(window_s=window)), msg=repr(window))
        for quality in ({"track_conf": 1.0}, {"face_visible_ratio": 0.7, "track_conf": NAN},
                        {"face_visible_ratio": 1.5, "track_conf": 1.0}, "q"):
            self.assertTrue(any("quality" in p for p in self.changed(quality=quality)), msg=repr(quality))
        empty, _ = assess(rows_of(face(5)), -5.0, P, landmarker_num_faces=1)
        self.assertEqual((empty["name"], empty["quality"]), (UNKNOWN, {"face_visible_ratio": None, "track_conf": None}))

    def test_a_definite_alternative_needs_the_tracking_floor(self):
        """Item 6 (r3): a sensor-failure output (track_conf below the floor) may not carry an alternative with a
        definite confidence."""
        out, events = run(companion_window(sweep(+1), face(3), sweep(+1)))
        failed = {**out, "name": UNKNOWN, "display_text": "", "evidence": [], "confidence": UNKNOWN,
                  "quality": {**out["quality"], "track_conf": 0.1}}
        problems = check_output(failed, events, P)
        self.assertTrue(any(p.startswith(f"alternative {AROUND}") and "track_conf" in p for p in problems))

    def test_evidence_must_repeat_an_observation_of_the_event(self):
        evidence = [dict(self.out["evidence"][0], value=7)] + self.out["evidence"][1:]
        self.assertTrue(any("is not an observation" in p for p in self.changed(evidence=evidence)))

    def test_display_text_is_the_fixed_text(self):
        self.assertTrue(any("fixed text" in p for p in self.changed(display_text="뒤에 사람이 많아 초조해 보임")))
        self.assertTrue(any("is not a tag" in p for p in self.changed(name="hurried", display_text="")))
        self.assertEqual(set(DISPLAY_TEXT) - {UNKNOWN, NONE}, set(TAGS))

    def test_unknown_goes_with_unknown_and_tags_need_min_events(self):
        self.assertTrue(any("'unknown' goes only" in p for p in self.changed(name=UNKNOWN, display_text="")))
        few = {"events": 3, "quality_ok": True}
        self.assertTrue(any("fewer than min_events" in p for p in
                            check_output(self.out, self.events, dataclasses.replace(P, min_events=4))))
        self.assertTrue(any("evidence events" in p for p in self.changed(confidence={**few, "events": 2})))

    def test_an_alternative_needs_evidence_even_when_unknown(self):
        """Item 7 (r2): an alternative without an event of this window breaks the check, whatever its confidence."""
        empty = {"name": AROUND, "display_text": DISPLAY_TEXT[AROUND], "evidence": [], "confidence": UNKNOWN}
        self.assertTrue(any("no evidence event" in p for p in self.changed(alternatives=[empty])))

    def test_alternatives_need_min_events_too(self):
        """Item 6: an alternative whose {events, quality_ok} confidence is below min_events breaks rule 2."""
        out, events = run(companion_window(sweep(+1), face(3), sweep(+1)))
        self.assertEqual(out["alternatives"][0]["confidence"], {"events": 3, "quality_ok": True})
        problems = check_output(out, events, dataclasses.replace(P, min_events=4))
        self.assertTrue(any(p.startswith(AROUND) and "fewer than min_events" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
