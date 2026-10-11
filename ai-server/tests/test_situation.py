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

    def test_values_must_be_finite_non_negative_and_counts_whole(self):
        for bad in ({"window_s": -1.0}, {"gap_s": NAN}, {"min_events": 2.5}, {"sweep_min_count": True},
                    {"offscreen_yaw_deg": None}):
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

    def test_optional_columns_are_cues_only_when_every_row_has_them(self):
        rows = put(rows_of(face(30), extra={}), 0, 29, people_behind_count=1)
        rows[10].pop("people_behind_count")
        cues = observe_window(rows, P, landmarker_num_faces=1)
        self.assertNotIn("people_behind_count", cues.measured)
        self.assertNotIn("people_behind", kinds(cues.events))
        self.assertIsNone(cues.any_tap)                                     # no touch log: unknown, not 'no touch'


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
                         ["companion_present", "dwell_no_touch", "mouth_moving", "yaw_sweep_offscreen"])
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

    def test_a_tie_is_unknown_with_both_alternatives(self):
        out, _ = run(companion_window(sweep(+1), face(3), sweep(-1), face(3), sweep(-1)))
        self.assertEqual(out["name"], UNKNOWN)
        self.assertEqual([(a["name"], a["confidence"]["events"]) for a in out["alternatives"]],
                         [(COMPANION, 4), (AROUND, 4)])


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

    def test_evidence_event_must_lie_inside_the_window(self):
        self.assertTrue(any("outside the window" in p for p in self.changed(window_s=[1.0, 3.0])))

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


if __name__ == "__main__":
    unittest.main()
