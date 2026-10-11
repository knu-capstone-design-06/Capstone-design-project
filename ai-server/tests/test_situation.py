"""Events and situation layers (app/modules/vision/events.py, situation.py) on synthetic observation windows.

Standard library only: the two layers need no numpy, OpenCV or MediaPipe, so these tests also run with
ai-server/requirements.txt alone. No photos, videos or runs/.

Every PilotParams value here (P) is made for these synthetic frames (10 frames per second) and is not a proposal: the
pilot values come from the team's self-recording (vision README, '상황 층').
"""

import dataclasses
import importlib.util
import os
import tokenize
import unittest

from app.modules.vision.events import PilotParams, detect_events, observe_window
from app.modules.vision.situation import DISPLAY_TEXT, NONE, TAGS, UNKNOWN, assess, check_output

NAN = float("nan")
DT = 0.1                                     # synthetic frame interval (s)
SEEN, NOT_SEEN = "보임", "못 봄"
SITUATION_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "app", "modules", "vision", "situation.py")

# test values for the synthetic frames below (see the module docstring), not pilot proposals
P = PilotParams(window_s=20.0, gap_s=0.25, offscreen_yaw_deg=30.0, shoulder_vis_min=0.5, look_back_min_count=2,
                sweep_min_count=2, stay_min_s=1.0, dwell_min_s=1.0, mouth_motion_min=0.2, body_still_max=0.05,
                back_loop_min_count=2, first_input_delay_min_ms=3000.0, min_events=3, face_visible_min=0.6,
                track_conf_min=0.6)

BEHIND, COMPANION, AROUND = "looking_back_with_people_behind", "consulting_companion", "looking_around"
BASE = {"face_state": SEEN, "body_state": SEEN, "yaw_deg": 0.0, "face_cx": 0.5, "pose_vis_shoulders": 0.9,
        "shoulder_cx": 0.5, "shoulder_cy": 0.7}
OPTIONAL = {"people_behind_count": 0, "companion_box": None, "mouth_motion": 0.0, "tap_count": 0,
            "miss_tap_count": 0, "back_count": 0, "first_input_delay_ms": NAN}
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
        """A count of 0 would let a rule pass without the observation it names: every count field must be >= 1."""
        for bad in ({"window_s": -1.0}, {"gap_s": NAN}, {"min_events": 2.5}, {"sweep_min_count": True},
                    {"offscreen_yaw_deg": None}, {"look_back_min_count": 0}, {"sweep_min_count": 0},
                    {"back_loop_min_count": 0}, {"min_events": 0}):
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

    def test_face_loss_that_is_not_a_turn_gives_no_turn_event(self):
        cases = {
            "no onset (occlusion)": rows_of(face(5), [(5, LOST)], face(5)),
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
        rows = rows_of(face(50))
        put(rows, 10, 10, tap_count=1, miss_tap_count=1)
        put(rows, 12, 12, tap_count=1, back_count=1)
        put(rows, 30, 30, tap_count=1, back_count=1)
        put(rows, 40, 40, tap_count=1, first_input_delay_ms=3500.0)
        put(rows, 45, 45, first_input_delay_ms=900.0)
        events = {e["kind"]: e for e in detect_events(rows, P, landmarker_num_faces=1)}
        self.assertEqual(events["touch_miss"]["obs"], {"miss_tap_count": 1})
        self.assertEqual(events["back_navigation_loop"]["obs"], {"back_count": 2})
        self.assertEqual(events["back_navigation_loop"]["source_frames"], [12, 30])
        self.assertEqual(events["first_input_delayed"]["obs"], {"first_input_delay_ms": 3500.0})

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
        """Item 6 (r2): the contract's TouchFeatures counts are integer, minimum 0: other values are errors, not
        missing values; a whole number written as a float is fine."""
        for bad in (-1, 1.5, "two", True):
            with self.assertRaises(ValueError, msg=repr(bad)):
                detect_events(put(rows_of(face(5)), 2, 2, tap_count=bad), P, landmarker_num_faces=1)
        events = detect_events(put(rows_of(face(20)), 0, 19, people_behind_count=2.0), P, landmarker_num_faces=1)
        self.assertEqual([e["obs"]["people_behind_count"] for e in events if e["kind"] == "people_behind"], [2])

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
        self.assertEqual([item["obs"] for item in look], ["yaw_deg", "side", "face_lost_s", "pose_vis_shoulders"])
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
        out, _ = run(rows_of(face(30), extra={}, drop=drop))
        self.assertEqual((out["name"], out["alternatives"]), (UNKNOWN, []))
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

    def test_state_is_kept_while_its_events_overlap_the_window_and_expires_after(self):
        rows = put(rows_of(face(5), look_back(), face(5), look_back(), face(55)), 0, 30, people_behind_count=1)
        params = dataclasses.replace(P, window_s=3.0)
        outs = {t: assess(rows, t, params, landmarker_num_faces=1)[0] for t in (3.0, 4.0, 5.0)}
        self.assertEqual([outs[t]["name"] for t in (3.0, 4.0, 5.0)], [BEHIND, BEHIND, NONE])
        self.assertIn("look_back@5", ids(outs[4.0]))     # 0.5-1.3 s still overlaps [1.0, 4.0]; gone at [2.0, 5.0]

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

    def test_evidence_time_must_lie_inside_the_window(self):
        """Item 9 (r2): an event is evidence when its time (its end) lies inside the window; t is that time."""
        self.assertTrue(any("outside the window" in p for p in self.changed(window_s=[2.7, 3.0])))
        self.assertEqual(self.changed(window_s=[1.0, 3.0]), [])          # ends 1.3, 2.6, 3.0: all inside
        evidence = [dict(item, t=0.5) if item["event_id"] == "look_back@5" else item for item in self.out["evidence"]]
        self.assertTrue(any("is not the time (end)" in p for p in self.changed(evidence=evidence)))

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
