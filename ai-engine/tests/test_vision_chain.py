"""Runtime chain of the vision module (params, perception, columns, touch, chain, rule table v0, contract view, replay
and live runners) on inputs made here: drawn frames, arrays and JSON written by the tests. No photo, no video of a
person, no camera, no window.

- plain-Python parts (params, touch log, rule table) run with the server packages alone; columns, the window chain
  and the head post-processing need numpy (and OpenCV for the crops);
- parts that need OpenCV / ONNX Runtime / MediaPipe or the ONNX files skip when those are missing, so the server tests
  still run with ai-engine/requirements.txt.
Every number below is made for these synthetic inputs and is not a proposal for a pilot value.
"""

import dataclasses
import datetime
import importlib.util
import io
import json
import math
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace

AI_ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VISION_DIR = os.path.join(AI_ENGINE_DIR, "app", "modules", "vision")
MODEL_DIR = os.path.join(VISION_DIR, "models")
CONTRACT_FB = os.path.join(os.path.dirname(AI_ENGINE_DIR), "contract", "frontend-backend.openapi.yaml")
TOUCH_LOG_TS = os.path.join(os.path.dirname(AI_ENGINE_DIR), "frontend", "src", "features", "order", "touchLog.ts")
H1_PATH = os.path.join(MODEL_DIR, "h1_head_yolox_nano_416.onnx")
P1_PATH = os.path.join(MODEL_DIR, "p1_head_direction_resnet18_56.onnx")

HAS_NUMPY = importlib.util.find_spec("numpy") is not None
HAS_CV2 = HAS_NUMPY and importlib.util.find_spec("cv2") is not None
HAS_ORT = HAS_NUMPY and importlib.util.find_spec("onnxruntime") is not None
HAS_MEDIAPIPE = HAS_CV2 and importlib.util.find_spec("mediapipe") is not None
HAS_PYDANTIC = importlib.util.find_spec("pydantic") is not None
SKIP = "vision packages not installed (pip install -r app/modules/vision/requirements.txt onnxruntime)"

SEEN, NOT_SEEN = "보임", "못 봄"
NAN = float("nan")
DT = 0.1
SIT_VALUES = dict(window_s=6.0, gap_s=0.25, offscreen_yaw_deg=30.0, shoulder_vis_min=0.5, look_back_min_count=2,
                  sweep_min_count=2, stay_min_s=1.0, dwell_min_s=1.0, mouth_motion_min=0.2, body_still_max=0.05,
                  min_events=3, face_visible_min=0.6, track_conf_min=0.6)   # test values for the synthetic rows


def sit_params(**over):
    from app.modules.vision.events import PilotParams
    return PilotParams(**{**SIT_VALUES, **over})


def sourced(values: dict, text: str = "test value") -> dict:
    """The value-bundle file form of plain values: {name: {"value": v, "source": text}}."""
    return {k: {"value": v, "source": text} for k, v in values.items()}


def bundle(situation=True, **chain):
    from app.modules.vision.params import Bundle, PilotParams
    return Bundle(PilotParams(**chain), sit_params() if situation else None, "test")


# --- synthetic observation rows (the events layer's input) --------------------------------------------------------
BASE = {"face_state": SEEN, "body_state": SEEN, "yaw_deg": 0.0, "face_cx": 0.5, "pose_vis_shoulders": 0.9,
        "shoulder_cx": 0.5, "shoulder_cy": 0.7}
FULL = {"people_behind_count": 0, "companion_box": None, "mouth_motion": 0.0, "tap_count": 0, "miss_tap_count": 0}


def rows_of(*parts, extra=None, start=0.0):
    extra = FULL if extra is None else extra
    rows = []
    for n, over in [x for part in parts for x in part]:
        for _ in range(n):
            i = len(rows)
            rows.append({"frame_idx": i, "t_s": round(start + i * DT, 6), **BASE, **extra, **over})
    return rows


def facing(n):
    return [(n, {})]


def sweep(sign=1):
    return [(1, {"yaw_deg": sign * 40.0}), (2, {"yaw_deg": sign * 55.0}), (1, {"yaw_deg": sign * 40.0})]


def look_back():
    lost = {"face_state": NOT_SEEN, "yaw_deg": NAN, "face_cx": NAN}
    return [(1, {"yaw_deg": 40.0}), (1, {"yaw_deg": 60.0}), (5, lost), (1, {"yaw_deg": 45.0})]


class ParamsTests(unittest.TestCase):   # plain Python: runs with the server packages too
    def test_every_chain_value_has_a_default_and_a_source(self):
        from app.modules.vision.params import PILOT, PilotParams
        p = PilotParams()
        sources = PilotParams.sources()
        for f in dataclasses.fields(PilotParams):
            self.assertIsNot(f.default, dataclasses.MISSING, f.name)
            self.assertTrue(sources[f.name].strip(), f.name)
        pilot = PilotParams.pilot_fields()
        self.assertIn("companion_min_area_ratio", pilot)
        self.assertIn("lost_pause_s", pilot)
        self.assertNotIn("head_score_min", pilot)               # data-derived (E3b), not [파일럿]
        self.assertNotIn("behind_max_area_ratio", pilot)        # decision table 3
        self.assertTrue(all(PILOT in sources[name] for name in pilot))
        self.assertEqual(p.to_dict()["segment_s"]["value"], p.segment_s)

    def test_values_are_checked(self):
        from app.modules.vision.params import PilotParams
        for bad in ({"segment_s": 0}, {"head_score_min": 1.5}, {"tremor_miss_min": 0}, {"tremor_miss_min": 2.5},
                    {"primary_rule": "nearest"}, {"mouth_dials": ()}, {"delay_notice_on": 1},
                    {"lost_pause_s": float("nan")}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                PilotParams(**bad)

    def test_bundle_file_needs_all_13_situation_values_and_keeps_sources(self):
        from app.modules.vision.params import PilotParams, SituationParams, load_bundle
        folder = tempfile.mkdtemp()
        good = os.path.join(folder, "bundle.json")
        with open(good, "w", encoding="utf-8") as f:
            json.dump({"bundle_id": "b1",
                       "situation": {**sourced(SIT_VALUES), "window_s": {"value": 8.0, "source": "window text"}},
                       "chain": {"head_score_min": {"value": 0.9, "source": "override text"},
                                 "tremor_miss_min": {"value": 3, "source": "count text"}}}, f)
        b = load_bundle(good)
        self.assertEqual((b.situation.window_s, b.chain.head_score_min, b.chain.tremor_miss_min), (8.0, 0.9, 3))
        self.assertEqual(b.bundle_id, "b1")
        rec = b.to_dict()
        self.assertEqual(rec["chain"]["head_score_min"],              # the override's own source, not the default's
                         {"value": 0.9, "unit": "score 0~1", "source": "override text", "origin": "bundle"})
        self.assertEqual((rec["chain"]["segment_s"]["origin"], rec["chain"]["segment_s"]["source"]),
                         ("default", PilotParams.sources()["segment_s"]))
        self.assertEqual(rec["situation"]["window_s"], {"value": 8.0, "source": "window text", "origin": "bundle"})
        self.assertEqual(rec["situation"]["gap_s"]["source"], "test value")
        self.assertNotIn("head_score_min", b.pilot_fields())
        self.assertIn("segment_s", b.pilot_fields())
        code = bundle(segment_s=2.0).to_dict()                          # built in code: no source given
        self.assertEqual(code["situation"]["gap_s"], {"value": SIT_VALUES["gap_s"], "source": None, "origin": "code"})
        self.assertEqual((code["chain"]["segment_s"]["source"], code["chain"]["segment_s"]["origin"]), (None, "code"))
        self.assertFalse({f.name for f in dataclasses.fields(PilotParams)}             # Bundle.sources is one dict
                         & {f.name for f in dataclasses.fields(SituationParams)})
        self.assertIsNone(load_bundle(None).situation)          # no file: chain defaults, no situation values
        for broken in ({"situation": sourced({k: v for k, v in SIT_VALUES.items() if k != "gap_s"})},
                       {"chain": {"no_such_value": {"value": 1, "source": "x"}}}, {"situations": {}},
                       {"chain": {"segment_s": 2.0}},                                    # a bare number
                       {"chain": {"segment_s": {"value": 2.0, "source": " "}}},          # an empty source
                       {"chain": {"segment_s": {"value": 2.0}}},                         # no source
                       {"situation": {**sourced(SIT_VALUES), "gap_s": 0.25}}):           # a bare situation value
            p = os.path.join(folder, "broken.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(broken, f)
            with self.assertRaises(ValueError, msg=repr(broken)):
                load_bundle(p)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"chain": {"segment_s": 2.0}}, f)
        with self.assertRaisesRegex(ValueError, r'chain\.segment_s.*"source"'):      # names the field and the form
            load_bundle(p)


@unittest.skipUnless(HAS_CV2, SKIP)
class HeadPostprocessTests(unittest.TestCase):
    def test_letterbox_keeps_the_aspect_ratio_at_the_top_left_with_pad_114(self):
        import numpy as np
        from app.inference.head import letterbox
        img = np.full((480, 640, 3), 10, np.uint8)
        x, r = letterbox(img, (416, 416))
        self.assertEqual(x.shape, (3, 416, 416))
        self.assertAlmostEqual(r, 0.65)
        self.assertEqual(x.dtype, np.float32)
        self.assertTrue((x[:, :312, :] == 10).all())             # 480 x 0.65 = 312 rows of image
        self.assertTrue((x[:, 312:, :] == 114).all())            # padding below

    def test_grid_has_the_3549_anchors_of_a_416_input(self):
        from app.inference.head import grid_and_strides
        grid, strides = grid_and_strides((416, 416))
        self.assertEqual(grid.shape, (52 * 52 + 26 * 26 + 13 * 13, 2))
        self.assertEqual(float(strides[0, 0]), 8.0)
        self.assertEqual(float(strides[-1, 0]), 32.0)
        self.assertEqual(grid[52 * 52 - 1].tolist(), [51.0, 51.0])

    def test_decode_and_nms(self):
        import numpy as np
        from app.inference.head import decode, grid_and_strides, nms
        grid, st = grid_and_strides((416, 416))
        raw = np.zeros((len(grid), 6), np.float32)
        raw[:, 4] = 0.0
        raw[10] = [0.5, 0.5, math.log(2.0), math.log(3.0), 0.9, 0.8]   # anchor 10: stride 8, grid (10, 0)
        boxes, scores = decode(raw, grid, st)
        self.assertAlmostEqual(float(scores[10]), 0.72, places=5)
        cx, cy, w, h = (10.5 * 8, 0.5 * 8, 16.0, 24.0)
        self.assertTrue(np.allclose(boxes[10], [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]))
        b = np.array([[0, 0, 10, 10], [1, 0, 11, 10], [20, 20, 30, 30], [0, 0, 10, 10.0]], float)
        s = np.array([0.9, 0.8, 0.7, 0.6])
        self.assertEqual(nms(b, s, 0.65), [0, 2])                # IoU(0,1) = 90/110 > 0.65; box 3 = box 0
        self.assertEqual(nms(b[:2], s[:2], 0.9), [0, 1])          # 0.818 <= 0.9: kept (torchvision: '> thr' goes)

    def test_filtering_before_nms_equals_nms_at_the_floor_then_filtering(self):
        import numpy as np
        from app.inference.head import nms
        rng = np.random.default_rng(1)
        xy = rng.random((300, 2)) * 300
        wh = rng.random((300, 2)) * 60 + 5
        b = np.concatenate([xy, xy + wh], 1)
        s = rng.random(300)
        floor = s >= 0.01
        idx = np.flatnonzero(floor)
        after = [idx[k] for k in nms(b[idx], s[idx], 0.65)]
        late = sorted(int(i) for i in after if s[i] >= 0.65)
        early_idx = np.flatnonzero(s >= 0.65)
        early = sorted(int(early_idx[k]) for k in nms(b[early_idx], s[early_idx], 0.65))
        self.assertEqual(late, early)

    def test_detector_call_path_with_a_stub_session(self):
        """The whole __call__ (letterbox, decode, threshold, NMS, frame fractions) with a stub ONNX session."""
        import numpy as np
        from app.inference.head import HeadDetector, grid_and_strides
        det = HeadDetector.__new__(HeadDetector)
        det.size_hw = (416, 416)
        det.grid, det.strides = grid_and_strides(det.size_hw)
        det.input_name, det.score_min, det.nms_iou = "images", 0.65, 0.65
        raw = np.zeros((1, len(det.grid), 6), np.float32)
        raw[0, 10] = [0.5, 0.5, math.log(2.0), math.log(3.0), 0.9, 0.9]     # score 0.81 kept
        raw[0, 11] = [0.5, 0.5, math.log(2.0), math.log(3.0), 0.9, 0.5]     # score 0.45 dropped
        det.session = SimpleNamespace(run=lambda _o, feed: [raw])
        heads = det(np.zeros((480, 640, 3), np.uint8))                     # r = 0.65
        self.assertEqual(len(heads), 1)
        cx, cy, w, h = 84.0 / 0.65, 4.0 / 0.65, 16.0 / 0.65, 24.0 / 0.65
        x0, y0, x1, y1 = cx - w / 2, max(0.0, cy - h / 2), cx + w / 2, cy + h / 2
        self.assertTrue(np.allclose(heads.boxes_px[0], [x0, y0, x1, y1]))
        self.assertTrue(np.allclose(heads.boxes[0], [x0 / 640, y0 / 480, x1 / 640, y1 / 480]))
        self.assertEqual(heads.frame_wh, (640, 480))
        self.assertEqual(set(heads.ms), {"pre", "infer", "post"})


@unittest.skipUnless(HAS_ORT and os.path.isfile(H1_PATH) and os.path.isfile(P1_PATH),
                     "ONNX files missing: python -m app.modules.vision.tools.export_onnx (see the vision README)")
class OnnxModelTests(unittest.TestCase):
    def test_head_detector_on_a_drawn_frame(self):
        import numpy as np
        from app.inference.head import HeadDetector
        det = HeadDetector(H1_PATH, 0.65, 0.65, threads=1)
        self.assertEqual(det.size_hw, (416, 416))
        heads = det(np.full((360, 640, 3), 127, np.uint8))
        self.assertEqual(heads.boxes.shape[1], 4)
        self.assertTrue(((heads.boxes >= 0) & (heads.boxes <= 1)).all())
        self.assertTrue((heads.scores >= 0.65).all())

    def test_head_direction_probabilities(self):
        import numpy as np
        from app.inference.head_direction import DIR_CLASSES, HeadDirection
        model = HeadDirection(P1_PATH, threads=1)
        img = np.full((240, 320, 3), 90, np.uint8)
        probs = model.probs(img, [[100, 60, 160, 140], [0, 0, 20, 30]])
        self.assertEqual(probs.shape, (2, len(DIR_CLASSES)))
        self.assertTrue(np.allclose(probs.sum(1), 1.0))
        self.assertEqual(model.probs(img, []).shape, (0, 5))


@unittest.skipUnless(HAS_CV2, SKIP)
class HeadDirectionInputTests(unittest.TestCase):
    def test_crop_is_square_grey_outside_and_rgb(self):
        import numpy as np
        from app.inference.head_direction import GREY, head_crop, square_crop, to_input
        img = np.zeros((100, 100, 3), np.uint8)
        img[:, :] = (255, 0, 0)                                  # pure blue in BGR
        crop, side, inside = square_crop(img, (-10, -10, 10, 30))   # long side 40 -> 60 px, centred at (0, 10)
        self.assertEqual((crop.shape, side, inside), ((60, 60, 3), 60, True))
        self.assertTrue((crop[0, 0] == GREY).all())              # outside the image
        small = head_crop(img, (40, 40, 60, 60))
        self.assertEqual(small.shape, (64, 64, 3))
        self.assertEqual(small[32, 32].tolist(), [0, 0, 255])     # RGB: blue is the last channel
        x = to_input(small[None])
        self.assertEqual(x.shape, (1, 3, 56, 56))
        self.assertAlmostEqual(float(x[0, 2, 0, 0]), (1.0 - 0.406) / 0.225, places=5)
        self.assertAlmostEqual(float(x[0, 0, 0, 0]), (0.0 - 0.485) / 0.229, places=5)


@unittest.skipUnless(HAS_NUMPY, SKIP)
class ColumnsTests(unittest.TestCase):
    def roles(self, boxes, face=None, **over):
        import numpy as np
        from app.modules.vision.columns import assign_heads
        from app.modules.vision.params import PilotParams
        return assign_heads(np.array(boxes, float), (640, 480), face, PilotParams(**over))

    def test_no_head_one_head(self):
        r = self.roles([])
        self.assertEqual((r.primary, r.companion, r.behind, r.primary_from), (None, None, (), None))
        r = self.roles([[0.4, 0.2, 0.6, 0.5]])
        self.assertEqual((r.primary, r.companion, r.behind, r.primary_from), (0, None, (), "largest"))

    def test_companion_beside_and_people_behind(self):
        user = [0.40, 0.20, 0.55, 0.45]           # 0.15 x 0.25
        mate = [0.60, 0.22, 0.74, 0.46]           # similar size, beside: centre 1.3 user widths away (in pixels)
        far = [0.10, 0.30, 0.15, 0.37]            # small: behind
        r = self.roles([far, mate, user])
        self.assertEqual((r.primary, r.companion, r.behind), (2, 1, (0,)))
        r = self.roles([far, mate, user], companion_max_dist_widths=1.0)   # too far for the companion rule
        self.assertEqual((r.companion, r.behind), (None, (0, 1)))
        r = self.roles([far, mate, user], companion_min_area_ratio=0.95)    # not similar enough
        self.assertEqual((r.companion, r.behind), (None, (0, 1)))
        r = self.roles([far, user], behind_max_area_ratio=0.05)             # far head not small enough
        self.assertEqual(r.behind, ())

    def test_main_user_follows_the_tracked_face(self):
        big = [0.05, 0.05, 0.35, 0.55]
        small = [0.60, 0.20, 0.70, 0.35]
        r = self.roles([big, small], face=(0.65, 0.28))
        self.assertEqual((r.primary, r.primary_from), (1, "face"))
        self.assertEqual(r.behind, ())                              # the big head is not smaller than the user
        r = self.roles([big, small], face=(0.65, 0.28), primary_rule="largest")
        self.assertEqual((r.primary, r.primary_from, r.behind), (0, "largest", (1,)))
        r = self.roles([big, small], face=(0.95, 0.95))             # no box around the face: largest
        self.assertEqual((r.primary, r.primary_from), (0, "largest"))

    def test_head_and_shoulder_columns(self):
        import numpy as np
        from app.modules.vision.columns import DIR_COLUMNS, HeadRoles, head_columns, shoulder_columns
        heads = SimpleNamespace(boxes=np.array([[0.1, 0.1, 0.3, 0.4], [0.5, 0.1, 0.7, 0.4]]),
                                scores=np.array([0.9, 0.8]))
        cols = head_columns(heads, HeadRoles(0, 1, (), "face"), np.array([0.6, 0.1, 0.1, 0.1, 0.1]))
        self.assertEqual(cols["people_behind_count"], 0)
        self.assertEqual(cols["companion_box"], (0.5, 0.1, 0.7, 0.4))
        self.assertEqual((cols["head_count"], cols["primary_score"], cols["primary_from"]), (2, 0.9, "face"))
        self.assertEqual(cols["head_dir_middle"], 0.6)
        cols = head_columns(SimpleNamespace(boxes=np.zeros((0, 4)), scores=np.zeros(0)),
                            HeadRoles(None, None, (), None), None)
        self.assertEqual((cols["people_behind_count"], cols["companion_box"], cols["primary_box"]), (0, None, None))
        self.assertTrue(all(cols[c] is None for c in DIR_COLUMNS))
        pose = np.zeros((33, 4))
        pose[11, :2], pose[12, :2] = (0.4, 0.6), (0.6, 0.62)
        self.assertEqual(shoulder_columns(pose), {"shoulder_cx": 0.5, "shoulder_cy": 0.61})
        self.assertEqual(shoulder_columns(None), {"shoulder_cx": None, "shoulder_cy": None})

    def test_mouth_motion_needs_a_full_baseline_run_and_resets_on_face_loss(self):
        from app.modules.vision.columns import MouthMotion
        m = MouthMotion(("jawOpen", "mouthClose"), baseline_s=0.3)
        values = [m.update(t * 0.1, {"jawOpen": 0.1, "mouthClose": 0.0}) for t in range(3)]
        self.assertEqual(values, [None, None, None])              # the run is shorter than 0.3 s
        self.assertAlmostEqual(m.update(0.3, {"jawOpen": 0.5, "mouthClose": 0.05}), 0.4)
        self.assertIsNone(m.update(0.4, None))                    # face lost: the run breaks
        self.assertIsNone(m.update(0.5, {"jawOpen": 0.5, "mouthClose": 0.0}))
        with self.assertRaises(KeyError):
            m.update(0.6, {"jawOpen": 0.5})


def _iso(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


T0_MS = 1_792_600_000_000.0


def touch_log(folder, events, video=None, clock=True):
    """A touch log export (touchLog.ts SavedLog) with events [(ms from the first frame, kind, screen, data[, session
    id])] (session 's1' unless given) and, when video is given, the video's clock file."""
    evs = [{"id": f"e{i}", "sessionId": ev[4] if len(ev) > 4 else "s1", "serverSessionId": None,
            "occurredAt": _iso(T0_MS + ev[0]), "elapsedMs": ev[0] + 1000, "screen": ev[2], "visitId": "v",
            "settings": {}, "kind": ev[1], "data": ev[3]}
           for i, ev in enumerate(events)]
    path = os.path.join(folder, "take_touch.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "sessionId": "s1", "serverSessionId": None, "startedAt": T0_MS - 1000,
                   "events": evs}, f)
    if video and clock:
        with open(video + ".clock.json", "w", encoding="utf-8") as f:
            json.dump({"first_frame": {"wall_epoch_ms": T0_MS}}, f)
    return path


MENU_EVENTS = [(-1000, "session_start", "menu", None), (-900, "screen_enter", "menu", None),
               (500, "pointer_start", "menu", {"target": None,                    # a miss; next press product:1 = a fix
                                               "nearestCandidates": [{"id": "product:1", "kind": "button"}]}),
               (700, "pointer_start", "menu", {"target": {"id": "product:1", "kind": "button", "disabled": False}}),
               (800, "pointer_start", "menu", {"start": {"x": 1, "y": 2}}),               # no target field
               (900, "pointer_start", "menu", {"target": {"id": "cart-add", "kind": "button", "disabled": True}}),
               (2000, "screen_enter", "review", {"from": "menu"}),
               (3000, "screen_enter", "menu", {"from": "review"}),
               (3500, "pointer_start", "menu", {"target": {"id": "cart-add", "kind": "button", "disabled": False}}),
               (4000, "screen_enter", "menu", {"from": "complete"}),
               (4500, "pointer_start", "menu", {"target": None,                    # a miss; next press elsewhere
                                                "nearestCandidates": [{"id": "product:3", "kind": "button"}]}),
               (4700, "pointer_start", "menu", {"target": {"id": "product:2", "kind": "button", "disabled": False}}),
               (5000, "options_open", "menu", {"productId": "2"}),
               (5500, "options_close", "menu", {"productId": "2"}),
               (6000, "session_suspend", "menu", {"reason": "pagehide"}),
               (7000, "session_resume", "menu", {"reason": "bfcache"}), (7000, "screen_enter", "menu", None),
               (8000, "session_end", "menu", {"reason": "server_session_change"}),
               (8100, "session_start", "menu", {"reason": "server_session_change"}, "s2"),
               (8100, "screen_enter", "menu", None, "s2")]


class TouchTests(unittest.TestCase):   # plain Python: runs with the server packages too
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.video = os.path.join(self.folder, "take.mp4")

    def test_clock_file_places_the_log_and_counts_follow_the_frontend_summary(self):
        from app.modules.vision.touch import load_timeline
        tl = load_timeline(touch_log(self.folder, MENU_EVENTS, self.video), self.video)
        self.assertEqual(tl.meta["anchor"], "take.mp4.clock.json first_frame.wall_epoch_ms")
        c = tl.counts(0.0, 1.0)
        self.assertEqual((c["tap_count"], c["miss_tap_count"], c["unknown_target_presses"]), (4, None, 1))
        self.assertIsNone(c["repeat_tap_count"])
        self.assertIsNone(c["dwell_ms"])
        self.assertEqual(tl.counts(2.5, 3.0)["back_count"], 1)        # review -> menu
        self.assertEqual(tl.counts(3.9, 4.0)["back_count"], 0)        # complete -> menu is a new order
        self.assertEqual(tl.counts(0.5, 0.5)["tap_count"], 0)          # (t0, t1]: the press at 0.5 is outside
        self.assertEqual(tl.counts(None, 0.5)["tap_count"], 1)          # first row: [0, t]
        self.assertTrue(tl.flags(1.9, 2.0)["forward"])
        self.assertFalse(tl.flags(0.0, 1.0)["cart_add"])               # the disabled cart-add press
        self.assertTrue(tl.flags(3.4, 3.5)["cart_add"])
        self.assertEqual(tl.screen_at(2.5), ("review", 2.0))
        self.assertEqual(tl.screen_at(-5.0), (None, None))
        self.assertAlmostEqual(tl.last_press(1.5), 0.9)

    def test_rows_before_the_log_have_no_count(self):
        from app.modules.vision.touch import load_timeline
        late = [(2000, "session_start", "menu", None), (2500, "pointer_start", "menu", {"target": None})]
        tl = load_timeline(touch_log(self.folder, late, self.video), self.video)
        self.assertIsNone(tl.counts(0.0, 1.0))
        self.assertEqual(tl.counts(2.0, 3.0)["tap_count"], 1)
        self.assertEqual(tl.counts(3.0, 9.0)["tap_count"], 0)          # after the last event: covered, no touch
        self.assertIsNone(tl.counts(1.5, 2.5))                          # starts before the first event, ends after
        self.assertFalse(tl.covered_interval(1.5, 2.5))
        self.assertEqual(tl.counts(2.0, 3.0)["near_miss_fix_count"], 0)   # a miss without candidates is no fix

    def test_start_offset_without_a_clock_file_and_the_error_without_both(self):
        from app.modules.vision.touch import load_timeline
        log = touch_log(self.folder, MENU_EVENTS, self.video, clock=False)
        tl = load_timeline(log, self.video, start_offset_s=10.0)       # the first event is at video 10 s
        self.assertAlmostEqual(tl.first_t, 10.0)
        self.assertAlmostEqual(tl.last_press(20.0), 10.0 + 5.7)
        with self.assertRaises(ValueError):
            load_timeline(log, self.video)

    def test_misses_fixed_at_once_and_unknown_targets(self):
        from app.modules.vision.touch import load_timeline
        tl = load_timeline(touch_log(self.folder, MENU_EVENTS, self.video), self.video)
        c = tl.counts(0.4, 0.75)                                        # the miss at 0.5, then product:1 at 0.7
        self.assertEqual((c["tap_count"], c["miss_tap_count"], c["near_miss_fix_count"]), (2, 1, 1))
        c = tl.counts(0.0, 1.0)                                         # the 0.8-s press has no target field
        self.assertEqual((c["miss_tap_count"], c["near_miss_fix_count"], c["unknown_target_presses"]), (None, None, 1))
        c = tl.counts(4.4, 4.8)                                         # the next press is not one of the candidates
        self.assertEqual((c["miss_tap_count"], c["near_miss_fix_count"]), (1, 0))
        self.assertEqual(tl.counts(0.6, 0.75)["near_miss_fix_count"], 0)   # counted at the miss's time, not the fix's
        other = [(0, "session_start", "menu", None),
                 (100, "pointer_start", "menu", {"target": None, "nearestCandidates": [{"id": "product:1"}]}),
                 (200, "pointer_start", "menu", {"target": {"id": "product:1", "kind": "button"}}, "s2")]
        tl = load_timeline(touch_log(self.folder, other, self.video), self.video)
        self.assertEqual(tl.counts(0.0, 0.3)["near_miss_fix_count"], 0)   # the next press is in another session

    def test_observation_spans_sessions_and_options(self):
        from app.modules.vision.touch import load_timeline
        tl = load_timeline(touch_log(self.folder, MENU_EVENTS, self.video), self.video)
        self.assertEqual(tl.spans, [(-1.0, 6.0), (7.0, 8.0), (8.1, None)])
        self.assertIsNone(tl.counts(6.2, 6.8))                          # between session_suspend and session_resume
        self.assertIsNone(tl.counts(5.5, 7.5))                          # reaches into the stretch not observed
        self.assertEqual(tl.counts(7.0, 7.5)["tap_count"], 0)           # observed again from session_resume
        self.assertEqual((tl.covered(6.5), tl.covered(7.5)), (False, True))
        self.assertEqual(tl.screen_at(6.5), (None, None))               # after session_suspend
        self.assertEqual(tl.screen_at(7.5), ("menu", 7.0))
        self.assertEqual(tl.screen_at(8.05), (None, None))              # after session_end
        self.assertEqual(tl.screen_at(8.5), ("menu", 8.1))
        self.assertIsNone(tl.options_open_at(-2.0))                     # before the first event
        self.assertEqual([tl.options_open_at(t) for t in (4.9, 5.2, 5.6)], [False, True, False])
        self.assertEqual((tl.session_at(-2.0), tl.session_at(0.0), tl.session_at(8.05), tl.session_at(8.5)),
                         (None, "s1", "s1", "s2"))
        self.assertEqual([(s["session_id"], s["first_t"], s["last_t"]) for s in tl.meta["sessions"]],
                         [("s1", -1.0, 8.0), ("s2", 8.1, 8.1)])
        self.assertEqual((tl.meta["truncated_possible"], tl.meta["warnings"]), (False, []))

    def test_a_log_at_the_frontend_limit_may_have_lost_its_start(self):
        from app.modules.vision.touch import LOG_LIMIT, load_timeline
        if os.path.isfile(TOUCH_LOG_TS):                                # the frontend's own limit
            with open(TOUCH_LOG_TS, encoding="utf-8") as f:
                self.assertEqual(int(re.search(r"logLimit = (\d+)", f.read()).group(1)), LOG_LIMIT)
        full = [(1000 + 10 * i, "pointer_start", "menu", {"target": None}) for i in range(LOG_LIMIT)]
        tl = load_timeline(touch_log(self.folder, full, self.video), self.video)
        self.assertTrue(tl.meta["truncated_possible"])
        self.assertEqual(len(tl.meta["warnings"]), 1)
        self.assertIsNone(tl.counts(0.5, 1.5))                          # before the first remaining event: unknown
        other = os.path.join(self.folder, "no_clock")
        os.makedirs(other)
        log = touch_log(other, full)                                    # no clock file
        with self.assertRaisesRegex(ValueError, "clock file"):
            load_timeline(log, os.path.join(other, "take.mp4"), start_offset_s=3.0)

    def test_events_without_a_time_are_skipped_and_counted(self):
        from app.modules.vision.touch import load_timeline
        path = touch_log(self.folder, MENU_EVENTS[:3], self.video)
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        saved["events"].append({"id": "old", "sessionId": "s0", "kind": "pointer_start"})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(saved, f)
        tl = load_timeline(path, self.video)
        self.assertEqual(tl.meta["events_without_time"], 1)
        self.assertEqual(len(tl.events), 3)


def win(t=10.0, measurable=True, situation=None, **kw):
    from app.modules.vision.judgment.rule_table_v0 import WindowInput
    return WindowInput(t=t, measurable=measurable, situation=situation, **kw)


def sit(name, events=3):
    ev = [{"event_id": f"look_back@{i}", "obs": "yaw_deg", "value": 60.0, "t": 1.0} for i in range(events)]
    return {"name": name, "display_text": "", "evidence": ev, "confidence": {"events": events, "quality_ok": True},
            "alternatives": [], "quality": {"face_visible_ratio": 1.0, "track_conf": 1.0}, "window_s": [0, 10],
            "source": "rules_v1"}


class RuleTableTests(unittest.TestCase):   # plain Python: runs with the server packages too
    def setUp(self):
        from app.modules.vision.judgment import rule_table_v0 as R
        from app.modules.vision.params import PilotParams
        self.R, self.p = R, PilotParams()

    def run_windows(self, inputs, state=None, p=None):
        R = self.R
        state = state or R.SessionState()
        out = []
        for inp in inputs:
            state, _ = R.tick(state, inp.t, p or self.p)
            d = R.decide(inp, state, p or self.p)
            state, d = R.apply(state, d)
            out.append(d)
        return out, state

    def test_rule_table_holds_no_number_literal_but_ranks(self):
        """Every count and time is a PilotParams field: the only literals are the rank table and the id format."""
        import ast
        with open(os.path.join(VISION_DIR, "judgment", "rule_table_v0.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        numbers = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
                   and not isinstance(n.value, bool)}
        self.assertLessEqual(numbers, {0, 1, 2, 3, 4, 7})   # ranks 2 3 4 7 (JP 0-3); 0 = no step left; id step 1

    def test_3_2_companion_opens_the_wait_and_a_touch_ends_it(self):
        (d1, d2, d3), state = self.run_windows([
            win(10, situation=sit("consulting_companion")), win(11, situation=sit("consulting_companion")),
            win(12, situation=sit("consulting_companion"), taps_segment=1)])
        self.assertEqual((d1.transition, d1.support, d1.action, d1.rank), ("open", "wait_hold_timer", "wait", 2))
        self.assertEqual(d1.form(), ("none", False))
        self.assertIsNone(d1.jev_request)                          # ask_jev false (JP scene table)
        self.assertEqual(d2.transition, "keep")
        self.assertEqual((d3.transition, d3.decision_id), ("withdraw", d1.decision_id))
        self.assertIsNone(state.held)

    def test_3_1_queue_notice_with_fit_or_choice(self):
        (d,), state = self.run_windows([win(situation=sit("looking_back_with_people_behind"), screen="menu",
                                            steps_left=2, gaze=False, misses_recent=0)])
        self.assertEqual((d.transition, d.support, d.action), ("open", "remaining_steps_notice", "apply"))
        self.assertEqual(d.form(), ("step_guide", False))
        self.assertEqual(d.policy["kind"], "fit")
        q = d.jev_request["questions"]["proposal_fits"]
        self.assertEqual(q["type"], "noul")
        self.assertEqual(d.jev_request["state"]["situation"]["evidence"], {"look_back": 3})
        self.assertFalse(re.search("[가-힣]", json.dumps(d.jev_request["questions"], ensure_ascii=False)))
        (d,), _ = self.run_windows([win(situation=sit("looking_back_with_people_behind"), screen="menu", steps_left=2,
                                        gaze=True, fixes_recent=self.p.tremor_miss_min)])
        self.assertEqual((d.support, d.rank, d.policy["kind"]), ("remaining_steps_notice", 3, "choice"))
        self.assertEqual(d.policy["default_choice"], "remaining_steps_notice")
        self.assertEqual(set(d.jev_request["questions"]["queue_support"]["criteria"]),
                         {"remaining_steps_notice", "defer_big_button_question"})
        self.assertIsNone(d.policy["T_CHOICE"])                    # 기준 없음: shadow mode
        self.assertEqual(d.jev_request["state"]["touch"]["fixes_recent"], self.p.tremor_miss_min)
        (d,), _ = self.run_windows([win(situation=sit("looking_back_with_people_behind"), screen="menu", steps_left=2,
                                        gaze=None, fixes_recent=self.p.tremor_miss_min_no_gaze)])
        self.assertEqual((d.support, d.policy["kind"], d.cues["options"]),    # the raised 4-1 row is no defer premise
                         ("remaining_steps_notice", "fit", ["remaining_steps_notice"]))

    def test_3_1_with_the_delay_notice_switch_and_without_steps(self):
        p = dataclasses.replace(self.p, delay_notice_on=True)
        (d,), _ = self.run_windows([win(situation=sit("looking_back_with_people_behind"), screen="menu",
                                        steps_left=1)], p=p)
        self.assertEqual((d.support, d.jev_request), ("delay_responsibility_notice", None))
        (d,), _ = self.run_windows([win(situation=sit("looking_back_with_people_behind"), screen="complete",
                                        steps_left=0)])
        self.assertEqual(d.transition, "none")

    def test_4_1_needs_the_gaze_gate(self):
        k = self.p.tremor_miss_min
        (d,), _ = self.run_windows([win(fixes_recent=k, misses_recent=k, gaze=True, screen="menu", steps_left=2)])
        self.assertEqual((d.support, d.action, d.form()), ("large_button", "propose", ("large_button", True)))
        self.assertIsNone(d.jev_request)                           # situation not known: no Jev (JP 0-4)
        self.assertEqual(d.cues["fixes_recent"], k)
        (d,), _ = self.run_windows([win(fixes_recent=k, gaze=False, screen="menu", steps_left=2)])
        self.assertEqual(d.transition, "none")                     # looking away: ask later
        (d,), _ = self.run_windows([win(fixes_recent=k, gaze=None, screen="menu", steps_left=2)])
        self.assertEqual(d.transition, "none")                     # camera cannot tell: the raised criterion
        (d,), _ = self.run_windows([win(fixes_recent=self.p.tremor_miss_min_no_gaze, gaze=None, screen="menu",
                                        steps_left=2, situation=sit("none", 0))])
        self.assertEqual((d.support, d.policy["ask_jev"], d.cues.get("raised")), ("large_button", False, True))

    def test_4_1_opens_on_fixed_misses_while_steps_are_left(self):
        k = self.p.tremor_miss_min
        (d,), _ = self.run_windows([win(misses_recent=k + 3, fixes_recent=0, gaze=True, screen="menu", steps_left=2)])
        self.assertEqual(d.transition, "none")                     # misses alone, none fixed at once: no 4-1
        (d,), _ = self.run_windows([win(misses_recent=k, gaze=True, screen="menu", steps_left=2)])
        self.assertEqual(d.transition, "none")                     # fixes unknown
        (d,), _ = self.run_windows([win(fixes_recent=k, gaze=True, screen="complete", steps_left=0)])
        self.assertEqual(d.transition, "none")                     # complete screen: nothing left to press

    def test_4_2_back_or_pause_and_the_vision_lowered_pause(self):
        (d,), _ = self.run_windows([win(backs_recent=1, screen="menu", steps_left=2)])
        self.assertEqual((d.support, d.action, d.form()), ("highlight_next_action", "apply", ("none", False)))
        pause = self.p.lost_pause_s_vision
        (d,), _ = self.run_windows([win(pause_s=pause, screen="menu", steps_left=2, gaze=None)])
        self.assertEqual(d.transition, "none")                     # below lost_pause_s without a vision cue
        (d,), _ = self.run_windows([win(pause_s=pause, screen="menu", steps_left=2, gaze=True)])
        self.assertEqual(d.support, "highlight_next_action")
        (d,), _ = self.run_windows([win(pause_s=pause, screen="menu", steps_left=2,
                                        situation=sit("looking_around"))])
        self.assertEqual((d.support, d.policy["kind"]), ("highlight_next_action", "fit"))
        self.assertTrue(d.jev_request["state"]["vision"]["looking_around"])

    def test_rank_order_held_ask_and_replacements(self):
        k = self.p.tremor_miss_min
        both = dict(situation=sit("looking_back_with_people_behind"), screen="menu", steps_left=2, gaze=True,
                    fixes_recent=k)
        (d1, d2), state = self.run_windows([win(10, **both), win(11, **both)])
        self.assertEqual((d1.support, d2.transition, d2.support), ("remaining_steps_notice", "replace",
                                                                    "large_button"))   # shown notice -> ask
        self.assertEqual(state.withdrawn[-1]["reason"], "replace")
        (d3,), state = self.run_windows([win(12, situation=sit("looking_around"), screen="menu", steps_left=2,
                                             backs_recent=1)], state)
        self.assertEqual(d3.transition, "keep")                    # an open ask stays
        (d4,), state = self.run_windows([win(13, situation=sit("consulting_companion"), screen="menu",
                                             steps_left=2)], state)
        self.assertEqual((d4.transition, d4.support), ("replace", "wait_hold_timer"))   # 3-2 ranked ahead

    def test_not_measurable_keeps_or_does_nothing(self):
        (d1, d2), _ = self.run_windows([win(10, backs_recent=1, screen="menu", steps_left=2),
                                        win(11, measurable=False, backs_recent=1, screen="menu", steps_left=2)])
        self.assertEqual((d1.transition, d2.transition), ("open", "keep"))
        (d,), _ = self.run_windows([win(10, measurable=False, backs_recent=1, screen="menu", steps_left=2)])
        self.assertEqual(d.transition, "none")

    def test_no_response_refusal_and_scope(self):
        R, k = self.R, self.p.tremor_miss_min
        ask = dict(fixes_recent=k, gaze=True, screen="menu", steps_left=2)
        (d1,), state = self.run_windows([win(10, **ask)])
        state, gone = R.tick(state, 10 + self.p.no_response_s, self.p)
        self.assertEqual((gone, state.held), (d1.decision_id, None))
        (d2,), state = self.run_windows([win(11 + self.p.no_response_s, **ask)], state)
        self.assertEqual(d2.transition, "none")                    # withdrawn in this screen visit
        (d3,), state = self.run_windows([win(30, **{**ask, "screen": "review", "steps_left": 1})], state)
        self.assertEqual((d3.transition, d3.support), ("open", "large_button"))   # a new screen frees it
        state = R.react(state, "refuse", decision_id=d3.decision_id)
        self.assertEqual(state.refused, ["large_button"])
        (d4,), state = self.run_windows([win(40, **{**ask, "screen": "menu"})], state)
        self.assertEqual(d4.transition, "none")                    # refused for the session
        state = R.react(R.SessionState(active=["highlight_next_action"]), "revert", support="highlight_next_action")
        self.assertEqual((state.active, state.refused), ([], ["highlight_next_action"]))

    def test_unknown_situation_runs_touch_rows_only_and_continues_the_tag(self):
        (d1, d2), state = self.run_windows([
            win(10, situation=sit("looking_back_with_people_behind"), screen="menu", steps_left=2),
            win(11, situation=sit("unknown", 0), screen="menu", steps_left=2, backs_recent=1)])
        self.assertEqual(d1.support, "remaining_steps_notice")
        self.assertEqual(d2.transition, "keep")                    # rank 7 waits behind the held notice
        self.assertEqual((d2.meta["tag"], d2.meta["tag_since"]), ("looking_back_with_people_behind", 10))


@unittest.skipUnless(HAS_NUMPY, SKIP)
class UnknownReasonTests(unittest.TestCase):
    def test_missing_touch_and_behind_columns_name_their_cues(self):
        from app.modules.vision.chain import unknown_reasons
        from app.modules.vision.situation import assess
        sp = sit_params()
        rows = rows_of(facing(5), sweep(+1), facing(5), sweep(-1), facing(5), extra={})   # no optional column
        out, _ = assess(rows, rows[-1]["t_s"], sp, landmarker_num_faces=1)
        self.assertEqual(out["name"], "unknown")
        reasons = unknown_reasons(rows, rows[-1]["t_s"], sp)
        by_tag = {r["tag"]: r["missing"] for r in reasons if r["code"] == "missing_cue"}
        self.assertEqual(set(by_tag), {"consulting_companion", "looking_around"})
        self.assertIn("column:tap_count", by_tag["looking_around"])
        self.assertIn("column:people_behind_count", by_tag["looking_around"])
        self.assertIn("column:companion_box", by_tag["consulting_companion"])

    def test_sensor_failure_no_frames_and_too_few_events(self):
        from app.modules.vision.chain import unknown_reasons
        from app.modules.vision.situation import assess
        sp = sit_params()
        rows = rows_of(facing(30), extra={**FULL, "body_state": NOT_SEEN})
        self.assertEqual(unknown_reasons(rows, rows[-1]["t_s"], sp)[0]["code"], "sensor_failure")
        self.assertEqual(unknown_reasons(rows, 100.0, sp), [{"code": "no_frames"}])
        sp = sit_params(dwell_min_s=100.0)                         # no dwell event: two sweeps only
        rows = rows_of(facing(5), sweep(+1), facing(5), sweep(-1), facing(5))
        out, _ = assess(rows, rows[-1]["t_s"], sp, landmarker_num_faces=1)
        self.assertEqual(out["name"], "unknown")
        self.assertEqual(unknown_reasons(rows, rows[-1]["t_s"], sp),
                         [{"code": "too_few_events", "tag": "looking_around", "events": 2, "min_events": 3}])

    def test_tie(self):
        from app.modules.vision import chain
        from app.modules.vision.situation import Verdict
        strong = lambda c, p: Verdict(True, [{}, {}, {}])
        none = lambda c, p: Verdict(False, [])
        rules = {"looking_back_with_people_behind": strong, "consulting_companion": strong, "looking_around": none}
        rows = rows_of(facing(20))
        original = chain.RULES
        chain.RULES = rules
        try:
            reasons = chain.unknown_reasons(rows, rows[-1]["t_s"], sit_params())
        finally:
            chain.RULES = original
        self.assertEqual(reasons[0], {"code": "tie", "tags": ["looking_back_with_people_behind",
                                                             "consulting_companion"], "events": 3})

    def test_every_unknown_window_gets_a_reason_and_no_other_does(self):
        from app.modules.vision.chain import unknown_reasons
        from app.modules.vision.situation import UNKNOWN, assess
        sp = sit_params()
        rows = rows_of(facing(5), sweep(+1), facing(3), look_back(), facing(4), sweep(-1), facing(6),
                       look_back(), facing(10), extra={**FULL, "people_behind_count": 1})
        rows += rows_of(facing(30), extra={"mouth_motion": 0.0}, start=rows[-1]["t_s"] + DT)
        for k in range(10, len(rows), 7):
            t = rows[k]["t_s"]
            out, _ = assess(rows[:k + 1], t, sp, landmarker_num_faces=1)
            reasons = unknown_reasons(rows[:k + 1], t, sp)
            if out["name"] == UNKNOWN:
                self.assertTrue(reasons, f"unknown without a reason at {t}")
                for r in reasons:
                    if r["code"] == "missing_cue":
                        self.assertTrue(r["missing"], f"missing_cue without a cue at {t}: {r}")


@unittest.skipUnless(HAS_NUMPY, SKIP)
class WindowJudgeTests(unittest.TestCase):
    def test_gaze_gate_needs_a_measured_head_direction(self):
        from app.modules.vision.chain import facing as gaze
        sp = sit_params()                                          # offscreen_yaw_deg 30 (test value)
        face_lost = {"face_state": NOT_SEEN, "yaw_deg": NAN, "face_cx": NAN}      # the body is still seen
        nothing = {**face_lost, "body_state": NOT_SEEN}
        self.assertIsNone(gaze(rows_of(facing(3), [(2, face_lost)]), sp))          # cannot measure, not 'away'
        self.assertTrue(gaze(rows_of([(3, {"yaw_deg": 10.0})]), sp))
        self.assertFalse(gaze(rows_of([(3, {"yaw_deg": -45.0})]), sp))
        self.assertTrue(gaze(rows_of([(3, {"yaw_deg": 5.0})], [(2, nothing)]), sp))   # the last frame seeing anyone
        self.assertIsNone(gaze(rows_of(facing(3)), None))                          # no situation values

    def test_pause_counts_only_after_a_press_on_this_screen_visit(self):
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.touch import load_timeline
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        events = [(-1000, "session_start", "menu", None), (-900, "screen_enter", "menu", None)]
        rows = rows_of(facing(40))

        def screen_at(t_end):
            tl = load_timeline(touch_log(folder, events, video), video)
            return WindowJudge(bundle(), tl).evaluate(rows, t_end)["screen"]
        self.assertIsNone(screen_at(3.0)["pause_s"])               # reading the first menu without choosing
        events.append((1000, "pointer_start", "menu", {"target": {"id": "product:1", "kind": "button",
                                                                  "disabled": False}}))
        self.assertAlmostEqual(screen_at(3.0)["pause_s"], 2.0)     # from the press at 1.0 s
        events.append((2500, "screen_enter", "review", {"from": "menu"}))
        self.assertEqual((screen_at(3.0)["name"], screen_at(3.0)["pause_s"]), ("review", None))   # a new visit
        events.append((3500, "options_open", "review", {"productId": "1"}))
        self.assertEqual((screen_at(3.0)["options_open"], screen_at(3.9)["options_open"]), (False, True))


@unittest.skipUnless(HAS_NUMPY, SKIP)
class HistoryTests(unittest.TestCase):
    def test_a_window_reads_the_same_from_its_history_as_from_all_rows(self):
        """chain.history_s rows (window_s + 2 gap_s) give assess the same output as the whole record."""
        from app.modules.vision.chain import history_s
        from app.modules.vision.situation import assess
        b = bundle()
        sp = b.situation
        rows = rows_of(facing(5), sweep(+1), facing(3), look_back(), facing(4), sweep(-1), facing(6),
                       look_back(), facing(10), sweep(+1), facing(8), extra={**FULL, "people_behind_count": 1})
        keep = history_s(b)
        for k in range(5, len(rows)):
            t = rows[k]["t_s"]
            full, _ = assess(rows[:k + 1], t, sp, landmarker_num_faces=1)
            part, _ = assess([r for r in rows[:k + 1] if r["t_s"] >= t - keep], t, sp, landmarker_num_faces=1)
            self.assertEqual(full, part, f"window ending {t}")


def fake_inference(yaw=0.0, face=True, body=True, blend=None):
    """A FrameInference-like object: 478 face points around (0.5, 0.4), a y-rotation of `yaw` degrees, a pose."""
    import numpy as np
    pts = np.full((478, 2), 0.5)
    pts[:, 1] = 0.4
    pts[33], pts[133], pts[362], pts[263] = (0.42, 0.4), (0.46, 0.4), (0.54, 0.4), (0.58, 0.4)
    pts[0], pts[1] = (0.40, 0.30), (0.60, 0.50)
    a = math.radians(yaw)
    m = np.eye(4)
    m[:3, :3] = [[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]]
    pose = np.zeros((33, 4))
    pose[:, 2:] = 0.9
    pose[11, :2], pose[12, :2] = (0.42, 0.7), (0.58, 0.7)
    ms = {"ms_prep": 0.0, "ms_face_lm": 0.0, "ms_face_det": 0.0, "ms_pose": 0.0}
    return SimpleNamespace(face_points=pts if face else None, face_matrix=m if face else None, detections=[],
                           pose=pose if body else None, ms=ms, blendshapes=blend if face else None)


class FakeModels:
    """infer(frame) from a schedule of fake inferences (one per frame index)."""

    def __init__(self, schedule):
        self.schedule = schedule

    def infer(self, frame):
        return self.schedule[frame.index]


class FakeHeads:
    """One head box around the tracked face, and an optional small head behind."""

    def __init__(self, behind=False):
        self.behind = behind

    def __call__(self, img):
        import numpy as np
        from app.inference.head import Heads
        H, W = img.shape[:2]
        boxes = [[0.38, 0.22, 0.62, 0.58]] + ([[0.10, 0.20, 0.16, 0.28]] if self.behind else [])
        frac = np.array(boxes, float)
        return Heads(frac, np.array([0.9] * len(boxes)), frac * [W, H, W, H], (W, H),
                     {"pre": 0.0, "infer": 0.0, "post": 0.0})


class FakeDirection:
    last_ms = {"crop": 0.0, "infer": 0.0}

    def probs(self, img, boxes):
        import numpy as np
        return np.tile([0.8, 0.05, 0.05, 0.05, 0.05], (len(boxes), 1))


def frames(n, size=(120, 160)):
    import numpy as np
    from app.modules.vision.sources import Frame
    img = np.full((size[0], size[1], 3), 127, np.uint8)
    return [Frame(i, round(i * DT, 6), img, str(i), 0.0) for i in range(n)]


def yaw_schedule():
    """Facing, a sweep right, facing, a sweep left, facing (yaw in degrees per frame, 10 frames per second)."""
    seq = [0.0] * 10 + [40.0, 55.0, 55.0, 40.0] + [0.0] * 10 + [-40.0, -55.0, -55.0, -40.0] + [0.0] * 32
    return seq


@unittest.skipUnless(HAS_CV2, SKIP)
class FrameChainTests(unittest.TestCase):
    def test_row_gets_the_optional_columns_timing_and_touch_counts(self):
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.params import PilotParams
        from app.modules.vision.touch import load_timeline
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        tl = load_timeline(touch_log(folder, MENU_EVENTS, video), video)
        blend = {name: 0.1 for name in PilotParams().mouth_dials}
        schedule = [fake_inference(blend=blend) for _ in range(12)]
        chain = FrameChain(FakeModels(schedule), PilotParams(mouth_baseline_s=0.5), FakeHeads(behind=True),
                           FakeDirection(), tl, blendshapes=True)
        rows = [chain.process(f) for f in frames(12)]
        r = rows[-1]
        self.assertEqual((r["people_behind_count"], r["companion_box"], r["head_count"]), (1, None, 2))
        self.assertEqual((r["primary_from"], r["head_dir_middle"]), ("face", 0.8))
        self.assertAlmostEqual(r["shoulder_cx"], 0.5)
        self.assertEqual(r["mouth_motion"], 0.0)                  # an unchanged face after a 0.5-s baseline
        self.assertIsNone(rows[0]["mouth_motion"])
        self.assertEqual([x["tap_count"] for x in rows[4:10]], [0, 1, 0, 1, 1, 1])   # presses at 0.5 / 0.7 / 0.8 / 0.9 s
        self.assertEqual([x["miss_tap_count"] for x in rows[4:10]], [0, 1, 0, 0, None, 0])   # 0.8 s: no target field
        for key in ("ms_heads", "ms_head_dir", "ms_chain", "cpu_ms_chain", "ms_total"):
            self.assertGreaterEqual(r[key], 0.0, key)

    def test_missing_sources_leave_their_columns_missing(self):
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.params import PilotParams
        chain = FrameChain(FakeModels([fake_inference(blend={"jawOpen": 0.2})] * 3), PilotParams())
        rows = [chain.process(f) for f in frames(3)]
        self.assertNotIn("people_behind_count", rows[-1])          # no detector: the column is absent
        self.assertNotIn("tap_count", rows[-1])                    # no touch log
        self.assertIsNone(rows[-1]["mouth_motion"])                # blendshapes off


@unittest.skipUnless(HAS_CV2, SKIP)
class ReplayWithFakePerceptionTests(unittest.TestCase):
    """The whole replay (rows -> windows -> rule table -> contract view -> files) on fake perception outputs."""

    def run_replay(self, sched, touch=True, situation=True, behind=False):
        from app.modules.vision.replay import run_replay
        from app.modules.vision.touch import load_timeline
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        tl = None
        if touch:
            events = [(-1000, "session_start", "menu", None), (-900, "screen_enter", "menu", None),
                      (-500, "pointer_start", "menu", {"target": {"id": "category:커피", "kind": "button",
                                                                  "disabled": False}})]   # chosen before the take
            tl = load_timeline(touch_log(folder, events, video), video)
        out = os.path.join(folder, "out")
        meta = run_replay(frames(len(sched)), out, bundle(situation=situation), timeline=tl, models=FakeModels(sched),
                          detector=FakeHeads(behind=behind), direction=FakeDirection(), blendshapes=False,
                          session_id="t1")
        with open(os.path.join(out, "windows.jsonl"), encoding="utf-8") as f:
            recs = [json.loads(line) for line in f]
        return meta, recs, out

    def test_looking_around_tag_and_the_4_2_highlight_end_to_end(self):
        sched = [fake_inference(y) for y in yaw_schedule()]
        meta, recs, out = self.run_replay(sched)
        self.assertEqual(meta["frames"], len(sched))
        self.assertEqual(len(recs), meta["windows"])
        names = [r["situation"]["name"] for r in recs]
        self.assertIn("looking_around", names)
        tagged = next(r for r in recs if r["situation"]["name"] == "looking_around")
        self.assertTrue(any(i.startswith("yaw_sweep_offscreen@") for i in tagged["situation"]["evidence_ids"]))
        opened = [r for r in recs if r["decision"]["transition"] == "open"]
        self.assertTrue(opened)
        self.assertEqual(opened[0]["decision"]["support"], "highlight_next_action")   # pause with looking around
        self.assertEqual(opened[0]["contract"]["extension"]["decision_meta"]["jev_kind"], "fit")
        self.assertTrue(os.path.isfile(os.path.join(out, "rows.csv")))
        with open(os.path.join(out, "meta.json"), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["counts"]["situation"].get("looking_around"), names.count("looking_around"))
        self.assertIn("ms_chain", saved["timing_ms"])

    def test_without_touch_log_or_values_the_tags_stay_unknown_with_reasons(self):
        sched = [fake_inference(y) for y in yaw_schedule()]
        _, recs, _ = self.run_replay(sched, touch=False)
        self.assertTrue(all(r["situation"]["name"] == "unknown" for r in recs if r["t"] >= 3.0))
        codes = {m for r in recs for x in r["situation"]["unknown_reason"] for m in x.get("missing", [])}
        self.assertIn("column:tap_count", codes)
        self.assertTrue(all(r["touch"] is None for r in recs))
        _, recs, _ = self.run_replay(sched, situation=False)
        self.assertTrue(all(r["situation"]["unknown_reason"] == [{"code": "no_value_bundle"}] for r in recs))

    def test_contract_view_fits_the_existing_contract(self):
        sched = [fake_inference(y) for y in yaw_schedule()]
        _, recs, _ = self.run_replay(sched)
        with open(CONTRACT_FB, encoding="utf-8") as f:
            text = f.read()
        presets = re.search(r"UIPreset:\s*\n\s*type: string\s*\n\s*enum: \[([^\]]+)\]", text).group(1)
        presets = {p.strip() for p in presets.split(",")}
        decided = re.search(r"decided_by: \{ type: string, enum: \[([^\]]+)\]", text).group(1)
        decided = {p.strip() for p in decided.split(",")}
        for r in recs:
            c = r["contract"]
            self.assertEqual(set(c), {"analyze_response", "support", "extension"})
            self.assertIn(c["support"]["preset"], presets)
            self.assertIn(c["support"]["decided_by"], decided)
            self.assertIsInstance(c["support"]["requires_confirmation"], bool)
            self.assertEqual(c["analyze_response"]["session_id"], "t1")
        if HAS_PYDANTIC:
            from app.modules.analyze.schemas import AnalyzeResponse
            for r in recs:
                AnalyzeResponse.model_validate(r["contract"]["analyze_response"])

    def test_measurable_follows_the_team_placeholder(self):
        sched = [fake_inference(face=False, body=True) for _ in range(30)]
        _, recs, _ = self.run_replay(sched)
        self.assertTrue(all(r["measurable"] is False for r in recs))      # no tap, no back, no face
        self.assertTrue(all(r["decision"]["transition"] == "none" for r in recs))


@unittest.skipUnless(HAS_CV2, SKIP)
class LiveTests(unittest.TestCase):
    def test_live_prints_one_line_per_window_without_a_window(self):
        from app.modules.vision.live import parse_args, run_live
        a = parse_args(["--camera", "0", "--no-window", "--seconds", "1"])
        self.assertTrue(a.no_window)                               # parsing opens no camera
        self.assertFalse(a.blendshapes)                            # off by default (decision list 2026-10-10 §16)
        self.assertTrue(parse_args(["--camera", "0", "--no-window", "--seconds", "1", "--blendshapes"]).blendshapes)
        lines = []
        sched = [fake_inference(y) for y in yaw_schedule()]
        folder = tempfile.mkdtemp()
        meta = run_live(frames(len(sched)), bundle(), models=FakeModels(sched), detector=FakeHeads(),
                        direction=FakeDirection(), show_window=False, out_dir=folder, blendshapes=False,
                        print_fn=lines.append)
        self.assertEqual(len(lines), meta["windows"])
        self.assertTrue(all(line.startswith("[") and "상황" in line for line in lines))
        self.assertIn("column:tap_count", " ".join(lines))          # no touch log in live use
        self.assertFalse(meta["window_shown"])
        with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
            self.assertEqual(sum(1 for _ in f), meta["windows"])


def drawn_clip(folder, n=30, fps=10.0):
    """A short MPEG-4 clip of drawn shapes (grey background, ellipses, a rectangle): no photo, no person."""
    import cv2
    import numpy as np
    path = os.path.join(folder, "drawn_take.mp4")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 240))
    for i in range(n):
        img = np.full((240, 320, 3), 127, np.uint8)
        cv2.ellipse(img, (140 + i, 100), (28, 36), 0, 0, 360, (60, 80, 120), -1)
        cv2.rectangle(img, (100 + i, 140), (190 + i, 240), (150, 60, 40), -1)
        writer.write(img)
    writer.release()
    return path


@unittest.skipUnless(HAS_MEDIAPIPE and HAS_ORT and os.path.isfile(H1_PATH) and os.path.isfile(P1_PATH) and all(
    os.path.isfile(os.path.join(MODEL_DIR, m)) for m in ("face_landmarker.task", "pose_landmarker_lite.task",
                                                         "blaze_face_short_range.tflite")),
                     "MediaPipe / ONNX model files missing (download_models.py, tools/export_onnx.py)")
class ReplaySmokeTests(unittest.TestCase):
    """The replay command on a drawn clip with the real models: the chain runs end to end and every window is
    written; nothing in the clip is a person, so the tags stay unknown with their reasons."""

    def test_replay_command_on_a_drawn_clip(self):
        from app.modules.vision import replay
        folder = tempfile.mkdtemp()
        clip = drawn_clip(folder)
        log = touch_log(folder, MENU_EVENTS, clip)
        bundle_path = os.path.join(folder, "bundle.json")
        with open(bundle_path, "w", encoding="utf-8") as f:
            json.dump({"bundle_id": "smoke", "situation": sourced(SIT_VALUES), "chain": {}}, f)
        out = os.path.join(folder, "out")
        with redirect_stdout(io.StringIO()):
            code = replay.main(["--video", clip, "--touch-log", log, "--params", bundle_path, "--out", out])
        self.assertEqual(code, 0)
        with open(os.path.join(out, "windows.jsonl"), encoding="utf-8") as f:
            recs = [json.loads(line) for line in f]
        with open(os.path.join(out, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(meta["frames"], 30)
        self.assertEqual(len(recs), 2)                             # windows at 1.0 s and 2.0 s
        self.assertEqual(recs[0]["touch"]["tap_count"], 4)
        for r in recs:
            self.assertEqual(r["situation"]["name"], "unknown")
            self.assertTrue(r["situation"]["unknown_reason"])
        self.assertTrue(set(meta["models"]) >= {"h1_head_yolox_nano_416.onnx", "p1_head_direction_resnet18_56.onnx"})
        self.assertFalse(meta["settings"]["blendshapes"])         # off unless --blendshapes (decision list §16)
        self.assertIn("blendshapes off", meta["settings"]["face_landmarker"])


if __name__ == "__main__":
    unittest.main()
