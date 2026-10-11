"""Events layer (app/modules/vision/events.py) on synthetic observation windows.

Standard library only: the layer needs no numpy, OpenCV or MediaPipe, so these tests also run with
ai-server/requirements.txt alone. No photos, videos or runs/.

Every PilotParams value here (P) is made for these synthetic frames (10 frames per second) and is not a proposal: the
pilot values come from the team's self-recording (vision README, '상황 층').
"""

import dataclasses
import importlib.util
import unittest

from app.modules.vision.events import PilotParams, detect_events, observe_window

NAN = float("nan")
DT = 0.1                                     # synthetic frame interval (s)
SEEN, NOT_SEEN = "보임", "못 봄"

# test values for the synthetic frames below (see the module docstring), not pilot proposals
P = PilotParams(window_s=20.0, gap_s=0.25, offscreen_yaw_deg=30.0, shoulder_vis_min=0.5, look_back_min_count=2,
                sweep_min_count=2, stay_min_s=1.0, dwell_min_s=1.0, mouth_motion_min=0.2, body_still_max=0.05,
                back_loop_min_count=2, first_input_delay_min_ms=3000.0, min_events=3, face_visible_min=0.6,
                track_conf_min=0.6)

BASE = {"face_state": SEEN, "body_state": SEEN, "yaw_deg": 0.0, "face_cx": 0.5, "pose_vis_shoulders": 0.9,
        "shoulder_cx": 0.5, "shoulder_cy": 0.7}
OPTIONAL = {"people_behind_count": 0, "companion_box": None, "mouth_motion": 0.0, "tap_count": 0,
            "miss_tap_count": 0, "back_count": 0, "first_input_delay_ms": NAN}
LOST = {"face_state": NOT_SEEN, "yaw_deg": NAN, "face_cx": NAN}                  # face lost, shoulders stay
GONE = {**LOST, "body_state": NOT_SEEN, "pose_vis_shoulders": NAN, "shoulder_cx": NAN, "shoulder_cy": NAN}


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


def kinds(events):
    return [e["kind"] for e in events]


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


if __name__ == "__main__":
    unittest.main()
