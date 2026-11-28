"""Runtime chain of the vision module (params, perception, columns, touch, chain, rule table v0, contract view, replay
and live runners) on inputs made here: drawn frames, arrays and JSON written by the tests. No photo, no video of a
person, no camera, no window.

- plain-Python parts (params, touch log, rule table) run with the server packages alone; columns, the window chain
  and the head post-processing need numpy (and OpenCV for the crops);
- parts that need OpenCV / ONNX Runtime / MediaPipe or the ONNX files skip when those are missing, so the server tests
  still run with ai-engine/requirements.txt.
Every number below is made for these synthetic inputs and is not a proposal for a pilot value.
"""

import csv
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
HEAD_IMAGE_ENV = "VISION_TEST_HEAD_IMAGE"   # opt-in: an image with at least one head (read only, never shown or saved)

HAS_NUMPY = importlib.util.find_spec("numpy") is not None
HAS_CV2 = HAS_NUMPY and importlib.util.find_spec("cv2") is not None
HAS_ORT = HAS_NUMPY and importlib.util.find_spec("onnxruntime") is not None
HAS_MEDIAPIPE = HAS_CV2 and importlib.util.find_spec("mediapipe") is not None
HAS_PYDANTIC = importlib.util.find_spec("pydantic") is not None
SKIP = "vision packages not installed (pip install -r app/modules/vision/requirements.txt onnxruntime)"

SEEN, NOT_SEEN = "보임", "못 봄"
NAN = float("nan")
DT = 0.1
PITCH_TEST = 20.0   # head_down_pitch_min of these tests: an arbitrary round value, not a calibration
VIS_TEST = 0.3      # hand_vis_min of these tests: between the fake points' visibility 0.0 and 0.9, not a proposal
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
        self.assertIn("track_max_gap_s", pilot)
        self.assertIn("role_window_s", pilot)
        self.assertIn("lost_pause_s", pilot)
        self.assertNotIn("head_score_min", pilot)               # data-derived (E3b), not [파일럿]
        self.assertNotIn("track_iou_min", pilot)                # convention value (SORT's public code)
        self.assertTrue(all(PILOT in sources[name] for name in pilot))
        self.assertEqual(p.to_dict()["segment_s"]["value"], p.segment_s)

    def test_role_boundaries_have_no_value_and_say_so(self):
        from app.modules.vision.params import ROLE_BOUNDARIES, UNDECIDED, Bundle, PilotParams
        p = PilotParams()
        for name in ROLE_BOUNDARIES:
            self.assertIsNone(getattr(p, name), name)
            self.assertTrue(PilotParams.sources()[name].startswith(UNDECIDED), name)
            self.assertNotIn(name, PilotParams.pilot_fields())
            self.assertEqual(Bundle(p, None).to_dict()["chain"][name]["origin"], "default")
            for bad in (0, -1.0, float("nan"), "1.5", True):
                with self.assertRaises(ValueError, msg=f"{name}={bad!r}"):
                    PilotParams(**{name: bad})
            self.assertEqual(getattr(PilotParams(**{name: 1.5}), name), 1.5)
        with self.assertRaises(ValueError):
            PilotParams(track_iou_min=1.2)

    def test_stitch_boundaries_have_no_value_and_say_how_to_get_one(self):
        from app.modules.vision.params import STITCH_BOUNDARIES, STITCH_METHOD, UNDECIDED, PilotParams
        self.assertEqual(STITCH_BOUNDARIES, ("stitch_shift_max", "stitch_size_max"))
        for name in STITCH_BOUNDARIES:
            self.assertIsNone(getattr(PilotParams(), name), name)
            self.assertTrue(PilotParams.sources()[name].startswith(UNDECIDED), name)
            self.assertIn(STITCH_METHOD, PilotParams.sources()[name])
            for bad in (0, -1.0, float("nan"), "0.5", True):
                with self.assertRaises(ValueError, msg=f"{name}={bad!r}"):
                    PilotParams(**{name: bad})

    def test_scene_boundaries_have_no_value_and_say_how_to_get_one(self):
        from app.modules.vision.params import SCENE_BOUNDARIES, SCENE_METHOD, UNDECIDED, Bundle, PilotParams
        p = PilotParams()
        self.assertEqual(SCENE_BOUNDARIES, ("seated_face_cy_min", "approach_ratio_min", "seated_head_cy_min",
                                            "head_down_pitch_min", "head_approach_ratio_min"))
        for name in SCENE_BOUNDARIES:
            self.assertIsNone(getattr(p, name), name)
            source = PilotParams.sources()[name]
            self.assertTrue(source.startswith(UNDECIDED), name)
            self.assertIn(SCENE_METHOD, source)
            self.assertNotIn(name, PilotParams.pilot_fields())
            self.assertEqual(Bundle(p, None).to_dict()["chain"][name]["origin"], "default")
            ok = 1.2 if name in ("approach_ratio_min", "head_approach_ratio_min") else 0.6   # a ratio above 1
            for bad in (0, -0.5, float("nan"), float("inf"), str(ok), True) + ((1.0, 0.6) if ok > 1 else ()):
                with self.assertRaises(ValueError, msg=f"{name}={bad!r}"):
                    PilotParams(**{name: bad})
            self.assertEqual(getattr(PilotParams(**{name: ok}), name), ok)

    def test_aid_use_boundary_is_a_pilot_value_from_a_public_set_and_the_detector_values_have_sources(self):
        from app.modules.vision.params import AID_BOUNDARIES, PILOT, PilotParams
        p = PilotParams()
        self.assertEqual(AID_BOUNDARIES, ("aid_use_min", "aid_person_min"))
        self.assertEqual((p.aid_use_min, p.aid_person_min), (0.350, 0.390))
        person = PilotParams.sources()["aid_person_min"]
        for fact in ("TU Graz", "사람 아무나", "0.38998", "joint_416", "PMMA"):
            self.assertIn(fact, person)
        self.assertIn("aid_person_min", PilotParams.pilot_fields())
        source = PilotParams.sources()["aid_use_min"]
        self.assertTrue(source.startswith(PILOT))
        for fact in ("TU Graz", "검증 분할", "joint_416", "입력 416", "0.698", "0.736", "휠체어", "PMMA"):
            self.assertIn(fact, source)
        self.assertIn("aid_use_min", PilotParams.pilot_fields())
        self.assertIsNone(PilotParams(aid_use_min=None).aid_use_min)          # a bundle may still say 'no value'
        with self.assertRaises(ValueError):
            PilotParams(aid_use_min=1.5)
        self.assertEqual((p.aid_score_min, p.aid_nms_iou), (0.01, 0.65))
        self.assertTrue(PilotParams.sources()["aid_score_min"].startswith("관행값"))
        for bad in ({"aid_use_min": 0}, {"aid_use_min": "0.5"}, {"aid_score_min": 1.5}, {"aid_nms_iou": 2.0}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                PilotParams(**bad)

    def test_the_aid_reading_defaults_to_the_owner_box_and_its_head_centre_cut_has_no_value(self):
        """aid_rule (2026-11-26): the default is the owner-box rule of 2026-11-22, head_centre the reading of the
        kiosk-view detector files; aid_head_min, the cut of that reading, has no value (UNDECIDED). A bundle or a
        runner option sets them, and the record names where each value came from."""
        from app.modules.vision.params import (AID_HEAD_BOUNDARIES, AID_RULES, UNDECIDED, Bundle, PilotParams,
                                               load_bundle, with_options)
        p = PilotParams()
        self.assertEqual((AID_RULES, p.aid_rule, AID_HEAD_BOUNDARIES, p.aid_head_min),
                         (("owner_box", "head_centre", "head_centre_carry"), "owner_box", ("aid_head_min",), None))
        source = PilotParams.sources()["aid_head_min"]
        self.assertTrue(source.startswith(UNDECIDED))
        self.assertIn("no_value_for_model", source)
        self.assertIn("head_centre", PilotParams.sources()["aid_rule"])
        for name in ("aid_rule", "aid_head_min"):
            self.assertNotIn(name, PilotParams.pilot_fields())
            self.assertEqual(Bundle(p, None).to_dict()["chain"][name]["origin"], "default")
        self.assertEqual(PilotParams(aid_rule="head_centre", aid_head_min=0.5).aid_head_min, 0.5)
        for bad in ({"aid_rule": "largest"}, {"aid_rule": None}, {"aid_head_min": 0}, {"aid_head_min": -0.2},
                    {"aid_head_min": 1.5}, {"aid_head_min": float("nan")}, {"aid_head_min": "0.5"},
                    {"aid_head_min": True}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                PilotParams(**bad)
        path = os.path.join(tempfile.mkdtemp(), "bundle.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"bundle_id": "t", "chain": sourced({"aid_rule": "head_centre", "aid_head_min": 0.4},
                                                          "file text")}, f)
        b = load_bundle(path)
        rec = b.to_dict()["chain"]
        self.assertEqual((rec["aid_rule"]["value"], rec["aid_rule"]["origin"], rec["aid_head_min"]["source"]),
                         ("head_centre", "bundle", "file text"))
        o = with_options(b, {"aid_head_min": 0.6})
        rec = o.to_dict()["chain"]
        self.assertEqual(rec["aid_head_min"], {"value": 0.6, "unit": "score 0~1", "source": "실행 옵션 --aid-head-min",
                                               "origin": "option"})
        self.assertEqual((o.chain.aid_rule, rec["aid_rule"]["origin"]), ("head_centre", "bundle"))
        o2 = with_options(load_bundle(None), {"aid_rule": "head_centre"})
        self.assertEqual((o2.to_dict()["chain"]["aid_rule"]["origin"], o2.chain.aid_head_min), ("option", None))
        self.assertIs(with_options(b, {}), b)
        for bad in ({"aid_head_min": 2.0}, {"aid_rule": "largest"}, {"no_such_value": 1}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                with_options(b, bad)

    def test_phone_detector_values_are_the_yolox_demos(self):
        from app.modules.vision.params import PilotParams
        p = PilotParams()
        self.assertEqual((p.phone_score_min, p.phone_nms_iou), (0.3, 0.45))
        for name in ("phone_score_min", "phone_nms_iou"):
            source = PilotParams.sources()[name]
            self.assertTrue(source.startswith("관행값"), name)
            self.assertNotIn(name, PilotParams.pilot_fields())
            with self.assertRaises(ValueError):
                PilotParams(**{name: 1.5})
        self.assertIn("onnx_inference.py", PilotParams.sources()["phone_score_min"])
        self.assertEqual(p.phone_every, 1)                       # every processed frame, as the head detector
        self.assertNotIn("phone_every", PilotParams.pilot_fields())
        for bad in (0, 2.5, True):
            with self.assertRaises(ValueError):
                PilotParams(phone_every=bad)

    def test_the_hand_point_limit_has_no_value_and_says_what_none_does(self):
        from app.modules.vision.params import HAND_BOUNDARIES, UNDECIDED, Bundle, PilotParams
        self.assertEqual(HAND_BOUNDARIES, ("hand_vis_min",))
        p = PilotParams()
        self.assertIsNone(p.hand_vis_min)
        source = PilotParams.sources()["hand_vis_min"]
        self.assertTrue(source.startswith(UNDECIDED))
        self.assertIn("visibility", source)
        self.assertIn("손 상자를 만들지", source)                  # no value: the hand path is held
        self.assertNotIn("hand_vis_min", PilotParams.pilot_fields())
        self.assertEqual(Bundle(p, None).to_dict()["chain"]["hand_vis_min"]["origin"], "default")
        for bad in (0, -0.5, 1.5, float("nan"), "0.5", True):
            with self.assertRaises(ValueError, msg=repr(bad)):
                PilotParams(hand_vis_min=bad)
        self.assertEqual(PilotParams(hand_vis_min=VIS_TEST).hand_vis_min, VIS_TEST)

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


    def test_aid_detector_keeps_every_class_score_with_a_stub_session(self):
        """The walking-aid detector (optional input): the same letterbox / decode / NMS, each box keeping the
        objectness x class score of all five classes; the class list comes from the export's metadata."""
        import numpy as np
        from app.inference.aid import AidDetector
        classes = ["pedestrian", "crutch", "cane", "walker", "wheelchair"]
        raw = np.zeros((1, 3549, 10), np.float32)
        raw[0, 10] = [0.5, 0.5, math.log(2.0), math.log(3.0), 0.9, 0.1, 0.8, 0.05, 0.05, 0.02]   # a crutch user
        raw[0, 11] = [-0.5, 0.5, math.log(2.0), math.log(3.0), 0.5, 0.1, 0.6, 0.0, 0.0, 0.0]     # same place, lower
        session = SimpleNamespace(
            get_inputs=lambda: [SimpleNamespace(name="images", shape=[1, 3, 416, 416])],
            get_outputs=lambda: [SimpleNamespace(shape=[1, 3549, 10])],
            get_modelmeta=lambda: SimpleNamespace(custom_metadata_map={"classes": json.dumps(classes)}),
            run=lambda _o, feed: [raw])
        det = AidDetector("stub.onnx", score_min=0.01, nms_iou=0.65, session=session)
        aids = det(np.zeros((480, 640, 3), np.uint8))
        self.assertEqual((len(aids), aids.classes), (1, tuple(classes)))     # the overlapping lower box is removed
        self.assertTrue(np.allclose(aids.class_scores[0], [0.09, 0.72, 0.045, 0.045, 0.018]))
        self.assertAlmostEqual(aids.scores[0], 0.72)
        bad = SimpleNamespace(**{**vars(session), "get_modelmeta": lambda: SimpleNamespace(
            custom_metadata_map={"classes": json.dumps(["head"])})})
        with self.assertRaises(ValueError):
            AidDetector("stub.onnx", 0.01, 0.65, session=bad)

    def test_the_per_class_reading_keeps_each_aid_class_channel_with_its_own_nms(self):
        """per_class (aid_rule head_centre): every class except pedestrian on its own - that class's channel on every
        anchor, the floor score_min, NMS inside the class - next to the person boxes, which stay as they are. A
        wheelchair channel under a pedestrian top class is kept; a channel below the floor is not."""
        import numpy as np
        from app.inference.aid import AidDetector
        classes = ["pedestrian", "crutch", "cane", "walker", "wheelchair"]
        raw = np.zeros((1, 3549, 10), np.float32)
        a, b, c = 3380 + 6 * 13 + 6, 3380 + 6 * 13 + 7, 3380                 # stride-32 anchors (6, 6), (7, 6), (0, 0)
        raw[0, a] = [0.5, 0.5, math.log(4.0), math.log(8.0), 0.9, 0.6, 0.0, 0.0, 0.0, 0.5]    # pedestrian 0.54 on top
        raw[0, b] = [-0.8, 0.5, math.log(4.0), math.log(8.0), 0.8, 0.1, 0.0, 0.0, 0.0, 0.5]   # IoU 0.86 with a
        raw[0, c] = [0.5, 0.5, math.log(4.0), math.log(8.0), 0.5, 0.1, 0.6, 0.01, 0.0, 0.0]   # crutch 0.3, cane 0.005
        session = SimpleNamespace(
            get_inputs=lambda: [SimpleNamespace(name="images", shape=[1, 3, 416, 416])],
            get_outputs=lambda: [SimpleNamespace(shape=[1, 3549, 10])],
            get_modelmeta=lambda: SimpleNamespace(custom_metadata_map={"classes": json.dumps(classes)}),
            run=lambda _o, feed: [raw])
        img = np.zeros((480, 640, 3), np.uint8)
        plain = AidDetector("stub.onnx", 0.01, 0.65, session=session)(img)
        aids = AidDetector("stub.onnx", 0.01, 0.65, session=session, per_class=True)(img)
        self.assertIsNone(plain.class_boxes)
        self.assertTrue(np.array_equal(plain.boxes, aids.boxes))             # the person boxes stay as they are
        self.assertTrue(np.array_equal(plain.class_scores, aids.class_scores))
        self.assertTrue(np.allclose(aids.scores, [0.54, 0.3]))               # b goes in the class-agnostic NMS
        self.assertEqual(sorted(aids.class_boxes), ["cane", "crutch", "walker", "wheelchair"])
        counts = {name: len(scores) for name, (_, scores) in aids.class_boxes.items()}
        self.assertEqual(counts, {"crutch": 1, "cane": 0, "walker": 0, "wheelchair": 1})
        boxes, scores = aids.class_boxes["wheelchair"]
        self.assertTrue(np.allclose(scores, [0.45]))                         # a's channel; b removed inside the class
        self.assertTrue(np.allclose(boxes[0], aids.boxes[0]))                # the same anchor, the same box
        boxes, scores = aids.class_boxes["crutch"]
        self.assertTrue(np.allclose(scores, [0.3]))
        self.assertTrue(np.allclose(boxes[0], aids.boxes[1]))
        self.assertEqual(aids.class_boxes["cane"][0].shape, (0, 4))

    def test_phone_detector_keeps_the_cell_phone_boxes_of_the_demo_postprocess_with_a_stub_session(self):
        """The phone detector (optional input): each box takes its best COCO class (objectness x class score), the
        boxes below score_min go, one class-agnostic NMS, then only 'cell phone' boxes stay."""
        import numpy as np
        from app.inference.phone import COCO_CLASSES, PHONE, PhoneDetector
        self.assertEqual((len(COCO_CLASSES), COCO_CLASSES.index(PHONE), COCO_CLASSES[0]), (80, 67, "person"))
        raw = np.zeros((1, 3549, 85), np.float32)

        def anchor(k, dx, obj, scores):
            raw[0, k, :5] = [dx, 0.5, math.log(2.0), math.log(3.0), obj]
            for c, s in scores.items():
                raw[0, k, 5 + COCO_CLASSES.index(c)] = s
        anchor(10, 0.5, 0.9, {PHONE: 0.8, "remote": 0.1})       # a phone, 0.72
        anchor(11, -0.5, 0.9, {PHONE: 0.5})                      # the same place, lower: removed by the NMS
        anchor(200, 0.5, 0.9, {"remote": 0.6, PHONE: 0.5})       # best class remote: not a phone box
        anchor(300, 0.5, 0.9, {PHONE: 0.3})                      # 0.27 < 0.3: dropped
        anchor(400, 0.5, 0.9, {"person": 0.9})                   # a person: not kept
        anchor(20, 0.5, 0.9, {"remote": 0.95})                   # a remote, 0.855, and at the same place ...
        anchor(21, -0.5, 0.9, {PHONE: 0.7})                      # ... a phone, 0.63: the class-agnostic NMS removes it
        session = SimpleNamespace(
            get_inputs=lambda: [SimpleNamespace(name="images", shape=[1, 3, 416, 416])],
            get_outputs=lambda: [SimpleNamespace(shape=[1, 3549, 85])], run=lambda _o, feed: [raw])
        det = PhoneDetector("stub.onnx", score_min=0.3, nms_iou=0.45, session=session)
        phones = det(np.zeros((480, 640, 3), np.uint8))          # r = 0.65
        self.assertEqual(len(phones), 1)
        self.assertAlmostEqual(phones.scores[0], 0.72, places=5)
        cx, cy, w, h = 84.0 / 0.65, 4.0 / 0.65, 16.0 / 0.65, 24.0 / 0.65
        self.assertTrue(np.allclose(phones.boxes[0], [(cx - w / 2) / 640, 0.0, (cx + w / 2) / 640, (cy + h / 2) / 480]))
        bad = SimpleNamespace(**{**vars(session), "get_outputs": lambda: [SimpleNamespace(shape=[1, 3549, 6])]})
        with self.assertRaises(ValueError):
            PhoneDetector("stub.onnx", 0.3, 0.45, session=bad)


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

    @unittest.skipUnless(HAS_CV2 and os.path.isfile(os.environ.get(HEAD_IMAGE_ENV, "")),
                         f"opt-in: set {HEAD_IMAGE_ENV} to an image with at least one head")
    def test_head_image_runs_h1_and_p1(self):
        """H1 boxes -> P1 directions on an image the tester names (the repository holds no picture of a person; the
        image is read in memory only, never printed, shown or saved)."""
        import cv2
        import numpy as np
        from app.inference.head import HeadDetector
        from app.inference.head_direction import DIR_CLASSES, HeadDirection
        from app.modules.vision.params import PilotParams
        img = cv2.imread(os.environ[HEAD_IMAGE_ENV])
        self.assertIsNotNone(img, "the image could not be read")
        p = PilotParams()
        heads = HeadDetector(H1_PATH, p.head_score_min, p.head_nms_iou, threads=1)(img)
        self.assertGreaterEqual(len(heads), 1)
        probs = HeadDirection(P1_PATH, threads=1).probs(img, heads.boxes_px)
        self.assertEqual(probs.shape, (len(heads), len(DIR_CLASSES)))
        self.assertTrue(np.allclose(probs.sum(1), 1.0))


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
    def people(self, **over):
        from app.modules.vision.columns import HeadPeople
        from app.modules.vision.params import PilotParams
        return HeadPeople(PilotParams(**over))

    def test_no_head_one_head(self):
        from app.modules.vision.columns import choose_primary
        self.assertEqual(choose_primary([], None, "face_then_largest"), (None, None))
        self.assertEqual(choose_primary([[0.4, 0.2, 0.6, 0.5]], None, "face_then_largest"), (0, "largest"))
        people = self.people()
        r = people.update(0.0, [], (640, 480), None)
        self.assertEqual((r.primary, r.companion, r.behind, r.primary_from), (None, None, (), None))
        r = people.update(0.1, [[0.4, 0.2, 0.6, 0.5]], (640, 480), None)
        self.assertEqual((r.primary, r.companion, r.behind, r.primary_from, r.tracks), (0, None, (), "largest", (1,)))
        self.assertTrue(r.behind_known and r.companion_known)          # nobody else: 0 behind, no companion

    def test_main_user_follows_the_tracked_face(self):
        from app.modules.vision.columns import choose_primary
        big = [0.05, 0.05, 0.35, 0.55]
        small = [0.60, 0.20, 0.70, 0.35]
        self.assertEqual(choose_primary([big, small], (0.65, 0.28), "face_then_largest"), (1, "face"))
        self.assertEqual(choose_primary([big, small], (0.65, 0.28), "largest"), (0, "largest"))
        self.assertEqual(choose_primary([big, small], (0.95, 0.95), "face_then_largest"), (0, "largest"))

    def test_tracker_keeps_ids_and_ends_a_track_after_the_gap(self):
        from app.modules.vision.columns import HeadTracker, box_iou
        self.assertAlmostEqual(box_iou([0, 0, 2, 2], [1, 0, 3, 2]), 2 / 6)
        self.assertEqual(box_iou([0, 0, 1, 1], [2, 2, 3, 3]), 0.0)
        tr = HeadTracker(iou_min=0.3, max_gap_s=1.0)
        a, b = [0.10, 0.10, 0.30, 0.40], [0.60, 0.20, 0.70, 0.35]
        self.assertEqual(tr.update(0.0, [a, b]), [1, 2])
        self.assertEqual(tr.update(0.125, [[0.61, 0.20, 0.71, 0.35], [0.11, 0.10, 0.31, 0.40]]), [2, 1])   # any order
        self.assertEqual(tr.update(0.25, [[0.30, 0.10, 0.50, 0.40]]), [3])    # IoU with track 1 below 0.3: new track
        self.assertEqual(tr.update(1.125, [a]), [1])      # track 1 last seen at 0.125 s: 1.0 s unseen keeps it
        self.assertEqual(tr.update(2.25, [a]), [4])       # 1.125 s unseen: track 1 ended, a new id
        self.assertEqual(sorted(tr.live), [4])

    def test_cues_of_hand_built_boxes(self):
        from app.modules.vision.columns import relative_cues
        user = [0.40, 0.30, 0.55, 0.50]                    # height 0.20 x 480 = 96 px, centre x 0.475
        far = [0.25, 0.25, 0.30, 0.35]                     # height 0.10: twice as far; centre x 0.275
        rel, lat = relative_cues(far, user, (640, 480))
        self.assertAlmostEqual(rel, 2.0)
        self.assertAlmostEqual(lat, -0.2 * 640 / 96)       # left of the user: negative, in user head heights
        rel, lat = relative_cues([0.65, 0.26, 0.85, 0.54], user, (640, 480))   # taller head on the right
        self.assertAlmostEqual(rel, 0.2 / 0.28)
        self.assertAlmostEqual(lat, 0.275 * 640 / 96)
        self.assertEqual(relative_cues(far, [0.4, 0.3, 0.5, 0.3], (640, 480)), (None, None))   # no height

    def test_window_median_of_one_track(self):
        user = [0.40, 0.30, 0.55, 0.50]                    # height 0.20
        people = self.people(role_window_s=0.25)
        rels = []
        for k, h in enumerate((0.20, 0.10, 0.05, 0.10)):   # rel_dist 1, 2, 4, 2 at 0.0 ... 0.3 s
            r = people.update(k * 0.1, [user, [0.70, 0.30, 0.75, 0.30 + h]], (640, 480), (0.47, 0.40))
            rels.append(r.cues[1][2])
        for got, want in zip(rels, (1.0, 1.5, 2.0, 2.0)):   # medians of 1 | 1, 2 | 1, 2, 4 | 2, 4, 2 (0.0 s left)
            self.assertAlmostEqual(got, want)

    def test_sticky_main_user_switches_only_after_the_gap(self):
        user = [0.40, 0.40, 0.50, 0.55]                    # seated user, small box
        helper = [0.35, 0.05, 0.60, 0.42]                  # larger head above, around the face in later frames
        people = self.people()                             # track_max_gap_s = 1.0 (default)
        r = people.update(0.0, [user], (640, 480), (0.45, 0.47))
        self.assertEqual((r.primary_track, r.primary_from), (1, "face"))
        r = people.update(0.1, [helper, user], (640, 480), (0.47, 0.20))    # the face now inside the helper's box
        self.assertEqual((r.primary, r.primary_track, r.primary_from), (1, 1, "track"))
        self.assertEqual(r.roles[0], "unknown")            # no boundary value: the helper's role is not decided
        self.assertTrue(r.behind_known)                    # a head larger than the user's is not behind (dec 3)
        for k in range(2, 11):                             # the user's box is lost: 1.0 s, the main user stays
            r = people.update(k * 0.1, [helper], (640, 480), (0.47, 0.20))
            self.assertEqual((r.primary, r.primary_track), (None, 1), k)
        r = people.update(1.2, [helper], (640, 480), (0.47, 0.20))          # 1.1 s unseen: the helper's turn
        self.assertEqual((r.primary, r.primary_track, r.primary_from), (0, 2, "face"))
        self.assertEqual(r.roles, ("primary",))

    def test_reset_starts_the_main_user_again_and_ids_keep_counting(self):
        user, other = [0.40, 0.30, 0.55, 0.50], [0.70, 0.30, 0.75, 0.40]
        people = self.people()
        r = people.update(0.0, [user, other], (640, 480), (0.47, 0.40))
        self.assertEqual((r.tracks, r.primary_from), ((1, 2), "face"))
        people.update(0.1, [user, other], (640, 480), (0.47, 0.40))
        people.reset()
        r = people.update(0.2, [user, other], (640, 480), None)
        self.assertEqual((r.tracks, r.primary_from, r.primary_track), ((3, 4), "largest", 3))
        self.assertEqual(r.cues[1][2], r.cues[1][0])       # the window median starts from this frame alone

    def test_roles_from_boundaries_and_unknown_without_them(self):
        user = [0.40, 0.30, 0.55, 0.50]                    # height 0.20
        mate = [0.62, 0.32, 0.75, 0.48]                    # rel 1.25, lateral 0.21 x 640 / 96 = 1.4: beside
        far = [0.45, 0.20, 0.50, 0.28]                     # rel 2.5, lateral 0: right behind
        boxes = [far, mate, user]
        r = self.people().update(0.0, boxes, (640, 480), (0.47, 0.40))
        self.assertEqual((r.primary, r.roles), (2, ("unknown", "unknown", "primary")))
        self.assertFalse(r.behind_known or r.companion_known)
        bounds = dict(companion_rel_dist_max=1.6, companion_lateral_min=1.0, behind_rel_dist_min=1.8)  # test values
        r = self.people(**bounds).update(0.0, boxes, (640, 480), (0.47, 0.40))
        self.assertEqual((r.companion, r.behind, r.roles), (1, (0,), ("behind", "companion", "primary")))
        self.assertTrue(r.behind_known and r.companion_known)
        r = self.people(**{**bounds, "companion_lateral_min": 2.0}).update(0.0, boxes, (640, 480), (0.47, 0.40))
        self.assertEqual((r.companion, r.behind, r.roles[1]), (None, (0,), "other"))   # not beside enough, not far
        r = self.people(behind_rel_dist_min=1.8).update(0.0, boxes, (640, 480), (0.47, 0.40))
        self.assertEqual(r.roles[:2], ("unknown", "unknown"))   # behind needs 'not a companion', still undecided

    def test_head_and_shoulder_columns(self):
        import numpy as np
        from app.modules.vision.columns import DIR_COLUMNS, HeadRoles, head_columns, shoulder_columns
        heads = SimpleNamespace(boxes=np.array([[0.1, 0.1, 0.3, 0.4], [0.5, 0.1, 0.7, 0.4]]),
                                scores=np.array([0.9, 0.8]))
        roles = HeadRoles(0, 1, (), "face", (3, 4), ("primary", "companion"), (None, (1.0, 2.0, 1.1, 2.1)), 3)
        cols = head_columns(heads, roles, np.array([0.6, 0.1, 0.1, 0.1, 0.1]))
        self.assertEqual(cols["people_behind_count"], 0)
        self.assertEqual(cols["companion_box"], (0.5, 0.1, 0.7, 0.4))
        self.assertEqual((cols["head_count"], cols["primary_score"], cols["primary_from"]), (2, 0.9, "face"))
        self.assertEqual(cols["primary_track"], 3)
        self.assertEqual(cols["head_dir_middle"], 0.6)
        self.assertEqual(cols["head_boxes"][1], {"track": 4, "cx": 0.6, "cy": 0.25, "w": 0.2, "h": 0.3, "score": 0.8,
                                                 "role": "companion", "rel_dist": 1.0, "lateral": 2.0,
                                                 "rel_dist_med": 1.1, "lateral_med": 2.1})
        self.assertIsNone(cols["head_boxes"][0]["rel_dist"])            # the main user's own box has no cue
        unknown = HeadRoles(0, None, (), "track", (3, 4), ("primary", "unknown"), (None, (2.0, 0.1, 2.0, 0.1)), 3,
                            behind_known=False, companion_known=False)
        cols = head_columns(heads, unknown, None)
        self.assertIsNone(cols["people_behind_count"])                  # blank: the cue is missing
        self.assertNotIn("companion_box", cols)                         # no key: the companion cannot be told
        cols = head_columns(SimpleNamespace(boxes=np.zeros((0, 4)), scores=np.zeros(0)),
                            HeadRoles(None, None, (), None), None)
        self.assertEqual((cols["people_behind_count"], cols["companion_box"], cols["primary_box"]), (0, None, None))
        self.assertEqual(cols["head_boxes"], [])
        self.assertTrue(all(cols[c] is None for c in DIR_COLUMNS))
        pose = np.zeros((33, 4))
        pose[11, :2], pose[12, :2] = (0.4, 0.6), (0.6, 0.62)
        self.assertEqual(shoulder_columns(pose), {"shoulder_cx": 0.5, "shoulder_cy": 0.61})
        self.assertEqual(shoulder_columns(None), {"shoulder_cx": None, "shoulder_cy": None})

    def test_unknown_roles_reach_the_situation_rules_as_missing_cues(self):
        """people_behind_count None and a row without companion_box (columns.head_columns) are what events.py reads
        as missing: the window does not measure them, so 'nobody behind' and 'no companion' are not concluded."""
        from app.modules.vision.events import observe_window
        rows = rows_of(facing(20), extra={**FULL, "people_behind_count": None})
        for r in rows:
            r.pop("companion_box")
        cues = observe_window(rows, (0.0, 1.9), sit_params(), landmarker_num_faces=1)
        self.assertNotIn("people_behind_count", cues.measured)
        self.assertNotIn("companion_box", cues.measured)

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

    def test_face_size_ratio_is_against_the_running_median_and_restarts_with_a_new_track(self):
        from app.modules.vision.columns import FaceSizeRef
        ref = FaceSizeRef()

        def row(iod, track=1, face=SEEN):
            return {"face_state": face, "iod_px": iod, "primary_track": track}
        got = [ref.update(row(v)) for v in (40.0, 40.0, 40.0, 52.0)]
        self.assertEqual(got[:3], [None, 1.0, 1.0])               # the first face row has no reference yet
        self.assertAlmostEqual(got[3], 1.3)
        self.assertIsNone(ref.update(row(None)))                  # someone else's face: iod_px blank
        self.assertIsNone(ref.update(row(40.0, face=NOT_SEEN)))
        self.assertIsNone(ref.update(row(40.0), collect=False))   # before the session's first press
        self.assertEqual(ref.n, 4)                                # nothing collected from those three rows
        self.assertIsNone(ref.update(row(80.0, track=2)))         # a new main-user track: a new reference
        self.assertEqual(ref.update(row(80.0, track=2)), 1.0)
        self.assertEqual(ref.update({"face_state": SEEN, "iod_px": 80.0}), 1.0)   # no track column: same reference

    def test_face_size_reference_keeps_a_bounded_state_on_a_long_run(self):
        """A live run of any length: the sizes are counted per 0.1 px, so 12,000 rows of one track keep at most one
        entry per step, and the medians stay within half a step of the exact ones."""
        import bisect
        import statistics
        from app.modules.vision.columns import FaceSizeRef
        sizes = [30 + (i * 37 % 100) / 10 for i in range(12000)]       # 30.0 .. 39.9 px in a scattered order
        ref = FaceSizeRef()
        for v in sizes:
            ref.update({"face_state": SEEN, "iod_px": v, "primary_track": 1})
        self.assertEqual(ref.n, 12000)
        self.assertLessEqual(len(ref.keys), 100)
        exact = sorted(sizes)
        self.assertAlmostEqual(ref.median(), statistics.median(exact), delta=0.05)
        upper = exact[bisect.bisect_left(exact, statistics.median(exact)):]
        self.assertAlmostEqual(ref.reference(), statistics.median(upper), delta=0.05)

    def test_face_size_reference_skips_a_size_below_the_storage_step(self):
        """A positive iod_px under half a step (0.04 px) rounds to 0: it is not stored, so the next normal row has no
        zero reference to divide by."""
        from app.modules.vision.columns import FaceSizeRef
        ref = FaceSizeRef()
        self.assertIsNone(ref.update({"face_state": SEEN, "iod_px": 0.04, "primary_track": 1}))
        self.assertIsNone(ref.update({"face_state": SEEN, "iod_px": 32.0, "primary_track": 1}))
        self.assertEqual(ref.update({"face_state": SEEN, "iod_px": 32.0, "primary_track": 1}), 1.0)

    def test_head_size_reference_follows_the_main_users_head_box(self):
        """head_ratio_user: the main user's head-box height over the same user's reference (the rules of
        FaceSizeRef); rows without the box give None."""
        from app.modules.vision.columns import HeadSizeRef, add_head_size_ratio
        ref = HeadSizeRef()
        box = lambda h: (0.4, 0.2, 0.6, 0.2 + h)                     # noqa: E731
        got = [ref.update({"primary_track": 1, "primary_box": box(h)}) for h in (0.20, 0.20, 0.20, 0.26)]
        self.assertEqual(got[:3], [None, 1.0, 1.0])
        self.assertAlmostEqual(got[3], 1.3)
        self.assertIsNone(ref.update({"primary_track": 1, "primary_box": None}))
        rows = add_head_size_ratio([{"t_s": t, "primary_track": "1", "primary_box": box(0.2)} for t in (0.1, 0.0)])
        self.assertEqual([r["head_ratio_user"] for r in rows], [1.0, None])
        self.assertEqual(add_head_size_ratio([{"t_s": 0.0}]), [{"t_s": 0.0}])  # no head detector: left as is
        self.assertIsNone(HeadSizeRef().update({"primary_track": 1, "primary_box": (0.4, float("nan"), 0.6, 0.5)}))
        text = HeadSizeRef()                                          # a box read back from rows.csv as text
        self.assertEqual([text.update({"primary_track": 1, "primary_box": "0.4;0.2;0.6;0.4"}) for _ in range(2)],
                         [None, 1.0])

    def test_face_size_reference_takes_only_the_main_users_face(self):
        """With the head detector a face matched to no box while the main user's track lives may be someone else's:
        no ratio, nothing collected. Without the head detector (no face_in_primary column) a seen face counts."""
        from app.modules.vision.columns import FaceSizeRef
        ref = FaceSizeRef()

        def row(iod, matched):
            return {"face_state": SEEN, "iod_px": iod, "primary_track": 1, "face_in_primary": matched}
        for _ in range(3):
            ref.update(row(30.0, True))
        self.assertIsNone(ref.update(row(55.0, None)))
        self.assertEqual(ref.n, 3)
        self.assertEqual(ref.update(row(30.0, "True")), 1.0)                # read back from rows.csv

    def test_face_size_reference_goes_on_through_a_same_place_reacquisition(self):
        """A cap or a camera stall ends the head track and the same person is found again in the same place
        (main_user_reacquired): the reference goes on, so a lean keeps its ratio. A new main user starts it again."""
        from app.modules.vision.columns import FaceSizeRef
        ref = FaceSizeRef()
        for _ in range(5):
            ref.update({"face_state": SEEN, "iod_px": 40.0, "primary_track": 1})
        again = {"face_state": SEEN, "iod_px": 52.0, "primary_track": 2, "main_user_reacquired": True}
        self.assertAlmostEqual(ref.update(again), 1.3)
        self.assertAlmostEqual(ref.update(dict(again, primary_track=3, main_user_reacquired="True")), 1.3)  # rows.csv
        self.assertIsNone(ref.update(dict(again, primary_track=4, main_user_reacquired=False)))

    def test_face_size_reference_keeps_the_lean_out(self):
        """Rows whose ratio already reached the face-approach boundary stay out of the reference, so a user who leans
        in and stays close keeps the ratio; without the boundary the running median drifts up to the close size."""
        from app.modules.vision.columns import FaceSizeRef
        sizes = [40.0] * 5 + [52.0] * 20
        kept = FaceSizeRef(near_min=1.2)                  # a press anchor (touch log): the lean stays out
        got = [kept.update({"face_state": SEEN, "iod_px": v, "primary_track": 1}, press_anchor=True) for v in sizes]
        self.assertAlmostEqual(got[5], 1.3)                       # leaning in: 52 against the median 40
        self.assertAlmostEqual(got[-1], 1.3)                      # 20 close rows later: still against 40
        drift = FaceSizeRef()
        got = [drift.update({"face_state": SEEN, "iod_px": v, "primary_track": 1}, press_anchor=True) for v in sizes]
        self.assertEqual(got[-1], 1.0)                            # no boundary: the median becomes 52 itself
        walk = FaceSizeRef(near_min=1.2)                  # no touch log: the upper-half reference takes the lean in
        got = [walk.update({"face_state": SEEN, "iod_px": v, "primary_track": 1}) for v in sizes]
        self.assertAlmostEqual(got[5], 1.3)
        self.assertEqual(got[-1], 1.0)

    def test_face_size_reference_without_head_tracks_restarts_after_nobody_is_seen(self):
        from app.modules.vision.columns import FaceSizeRef
        ref = FaceSizeRef(max_gap_s=1.0)

        def row(iod, face_unseen=NAN, body_unseen=NAN):
            return {"face_state": SEEN if iod else NOT_SEEN, "iod_px": iod, "face_unseen_s": face_unseen,
                    "body_unseen_s": body_unseen}
        self.assertEqual([ref.update(row(40.0)) for _ in range(2)], [None, 1.0])
        ref.update(row(None, face_unseen=1.5, body_unseen=0.5))   # the body is still seen: same person
        self.assertEqual(ref.update(row(40.0)), 1.0)
        ref.update(row(None, face_unseen=1.5, body_unseen=1.2))   # nobody for 1.2 s > 1.0 s: the next person
        self.assertIsNone(ref.update(row(80.0)))
        self.assertEqual(ref.update(row(80.0)), 1.0)

    def test_head_pitch_reference_is_the_main_users_own_first_face(self):
        """dpitch_user_deg: pitch against the same main user's first face after the anchor. User A walks in looking up
        (-15 deg); user B, a new main-user track in the same session, operates level (+10 deg) and reads 0, not 25.
        A reacquisition in the same place and a stitched track break (B bows deeply, the track breaks in place and the
        new track's first face is bowed) keep the reference; without the head detector nobody seen for longer than
        max_gap_s starts it again; before the first press (collect False) nothing is read."""
        from app.modules.vision.columns import PitchRef, add_pitch_user
        ref = PitchRef(max_gap_s=1.0)

        def row(track, pitch, **kw):
            return {"face_state": SEEN, "pitch_deg": pitch, "primary_track": track, **kw}
        self.assertEqual([ref.update(row(1, p)) for p in (-15.0, -15.0, 0.0)], [0.0, 0.0, 15.0])
        self.assertEqual([ref.update(row(2, p)) for p in (10.0, 10.0, 40.0)], [0.0, 0.0, 30.0])   # B's own first face
        self.assertEqual(ref.update(row(3, 30.0, main_user_reacquired="True")), 20.0)        # B found again
        self.assertEqual(ref.update(row(5, 35.0, main_user_stitched=True)), 25.0)            # B bowed: stitched
        self.assertEqual(ref.update(row(6, 35.0, main_user_stitched="True")), 25.0)          # read back from rows.csv
        self.assertEqual(ref.update(row(7, 35.0, main_user_stitched=False)), 0.0)            # a new main user
        self.assertIsNone(ref.update(row(3, 30.0, face_in_primary=False)))                  # not the main user's face
        self.assertIsNone(ref.update({"face_state": NOT_SEEN, "pitch_deg": NAN, "primary_track": 3}))
        gap = PitchRef(max_gap_s=1.0)                        # no head detector: the unseen gap is the anchor
        self.assertEqual(gap.update({"face_state": SEEN, "pitch_deg": -15.0}), 0.0)
        gap.update({"face_state": NOT_SEEN, "pitch_deg": NAN, "face_unseen_s": 1.5, "body_unseen_s": 1.2})
        self.assertEqual(gap.update({"face_state": SEEN, "pitch_deg": 10.0}), 0.0)
        waiting = PitchRef()
        self.assertIsNone(waiting.update(row(1, -15.0), collect=False))                      # before the first press
        self.assertEqual(waiting.update(row(1, 5.0)), 0.0)                                   # the press: its reference
        rows = add_pitch_user([{"t_s": t, "face_state": SEEN, "pitch_deg": p, "primary_track": k}
                               for t, p, k in ((0.1, -15.0, "1"), (0.0, -15.0, "1"), (0.2, 10.0, "2"),
                                               (0.3, 12.0, "2"))])
        self.assertEqual([r["dpitch_user_deg"] for r in rows], [0.0, 0.0, 0.0, 2.0])
        rows.append({"t_s": 0.4, "face_state": SEEN, "pitch_deg": 30.0, "primary_track": "3",
                     "main_user_stitched": "True"})
        self.assertEqual(add_pitch_user(rows)[-1]["dpitch_user_deg"], 20.0)                 # stitched: track 2's level

    def test_main_user_change_marks_the_first_row_of_a_new_track(self):
        from app.modules.vision.columns import MainUserChange, add_main_user_change
        change = MainUserChange()
        seq = [(0.0, 1, SEEN), (0.1, 1, SEEN), (0.2, None, SEEN), (0.3, None, NOT_SEEN), (0.4, 2, SEEN),
               (0.5, 2, SEEN), (0.6, 3, SEEN)]
        got = [change.update({"t_s": t, "primary_track": k, "body_state": b}) for t, k, b in seq]
        self.assertTrue(all(g["main_user_prev_track"] is None for i, g in enumerate(got) if i not in (4, 6)))
        self.assertEqual(got[0]["main_user_prev_track"], None)        # the first track of the session is no change
        self.assertEqual((got[4]["main_user_prev_track"], got[4]["main_user_body_kept"]), (1, False))   # body lost at 0.3
        self.assertAlmostEqual(got[4]["main_user_gap_s"], 0.3)
        self.assertEqual((got[6]["main_user_prev_track"], got[6]["main_user_body_kept"]), (2, True))
        rows = [{"t_s": 0.1, "primary_track": "1", "body_state": SEEN}, {"t_s": 0.0, "primary_track": "1",
                "body_state": SEEN}, {"t_s": 0.2, "primary_track": "4", "body_state": SEEN}, {"t_s": 0.3}]
        add_main_user_change(rows)
        self.assertEqual(rows[2]["main_user_prev_track"], 1)             # "1" read back from rows.csv is track 1
        self.assertNotIn("main_user_prev_track", rows[3])               # no head detector column: left as it is
        self.assertEqual(MainUserChange().update({"t_s": 0.0, "primary_track": float("nan")})["main_user_prev_track"],
                         None)                                          # a NaN cell is no track

    def test_a_reacquired_head_in_the_same_place_is_not_a_new_user(self):
        """A cap or a camera stall: the head detector loses the user for longer than the track gap and the next box
        starts a new track in the same place. It overlaps the ended track's last box by at least track_iou_min, so the
        change row says reacquired; a box elsewhere (the next customer) does not."""
        from app.modules.vision.columns import MainUserChange
        here, there = (0.40, 0.20, 0.60, 0.50), (0.05, 0.30, 0.20, 0.45)

        def row(t, track, box):
            return {"t_s": t, "primary_track": track, "primary_box": box, "body_state": SEEN}
        change = MainUserChange(iou_min=0.3)
        change.update(row(0.0, 1, here))
        same = change.update(row(1.4, 2, (0.41, 0.21, 0.61, 0.51)))
        self.assertEqual((same["main_user_prev_track"], same["main_user_reacquired"]), (1, True))
        other = change.update(row(3.0, 3, there))
        self.assertEqual((other["main_user_prev_track"], other["main_user_reacquired"]), (2, False))
        self.assertIsNone(MainUserChange().update(row(0.0, 1, here))["main_user_reacquired"])   # no iou_min: unknown

    def test_a_change_needs_an_earlier_user_who_had_settled(self):
        """A track that ends while its head box is still growing (the first approach) hands over without a change; a
        user whose box stopped growing (a 1-s bin not above the one before) was at the kiosk, and the next one is."""
        from app.modules.vision.columns import MainUserChange

        def run(heights):
            ch = MainUserChange(iou_min=0.3, max_gap_s=1.0, window_s=2.0, segment_s=1.0)
            t = 0.0
            for h in heights:                                      # track 1, one row every 0.1 s
                ch.update({"t_s": t, "primary_track": 1, "primary_box": (0.4, 0.1, 0.6, 0.1 + h),
                           "body_state": SEEN, "head_boxes": []})
                t += 0.1
            return ch.update({"t_s": t + 1.2, "primary_track": 2, "primary_box": (0.0, 0.5, 0.2, 0.8),
                              "body_state": NOT_SEEN, "head_boxes": []})
        walking = [0.10 + 0.01 * i for i in range(25)]             # growing in every bin
        standing = walking[:10] + [0.20] * 30                      # grows, then stays
        self.assertIs(run(walking)["main_user_prev_settled"], False)
        self.assertIs(run(standing)["main_user_prev_settled"], True)

    def test_a_reacquisition_needs_the_body_kept_through_the_gap(self):
        """Same place after the head track ended: the same person when the body stayed in view, a new customer when
        the place stood empty (nobody's body seen in the gap)."""
        from app.modules.vision.columns import MainUserChange
        box = (0.4, 0.2, 0.6, 0.5)

        def change(body_in_gap):
            ch = MainUserChange(iou_min=0.3, max_gap_s=1.0, window_s=2.0)
            ch.update({"t_s": 0.0, "primary_track": 1, "primary_box": box, "body_state": SEEN, "head_boxes": []})
            ch.update({"t_s": 0.5, "primary_track": None, "primary_box": None,
                       "body_state": SEEN if body_in_gap else NOT_SEEN, "head_boxes": []})
            return ch.update({"t_s": 1.6, "primary_track": 2, "primary_box": box, "body_state": SEEN, "head_boxes": []})
        self.assertIs(change(True)["main_user_reacquired"], True)
        self.assertIs(change(False)["main_user_reacquired"], False)

    def test_a_track_that_breaks_in_place_is_stitched_back(self):
        """A deep bow or a cap: the main user's box jumps (no IoU with the last box), so a new track starts at once in
        about the same place and size while the old one is still alive; when the old one ends the new one is the main
        user. It began after the last box and within track_max_gap_s, near it and about as large: stitched (the same
        user), and the earlier user's Settle state is kept. A head first seen in the frame of the old track's last box
        (two heads at once), a head first seen 3 s after it (the next customer in the same place), one that began
        elsewhere or much smaller, or a run without the boundaries is not stitched (None without boundaries).
        add_main_user_change with the bundle's stitch values stitches the same rows."""
        from app.modules.vision.columns import MainUserChange, add_main_user_change
        from app.modules.vision.params import PilotParams
        here = (0.40, 0.20, 0.60, 0.50)

        def listed(track, box, role="unknown"):
            return {"track": track, "cx": (box[0] + box[2]) / 2, "cy": (box[1] + box[3]) / 2, "w": box[2] - box[0],
                    "h": box[3] - box[1], "role": role}

        def stitch(new_first, first_t=0.6, bounds=(1.0, 0.3), box_until=0.55):
            ch = MainUserChange(iou_min=0.3, max_gap_s=1.0, window_s=2.0, segment_s=1.0, shift_max=bounds[0],
                                size_max=bounds[1])
            rows, out, t = [], [], 0.0
            while t < box_until + 1.5:
                if t < box_until:                                  # track 1 with its box
                    row = {"primary_track": 1, "primary_box": here, "head_boxes": [listed(1, here, "primary")]}
                elif t < box_until + 1.0:                          # track 1 alive without a box; track 2 another head
                    row = {"primary_track": 1, "primary_box": None,
                           "head_boxes": [listed(2, new_first)] if t >= first_t - 1e-9 else []}
                else:                                              # track 1 ended: track 2 is the main user
                    row = {"primary_track": 2, "primary_box": new_first, "head_boxes": [listed(2, new_first, "primary")]}
                if first_t < box_until and first_t - 1e-9 <= t < box_until:   # seen together with track 1
                    row["head_boxes"].append(listed(2, new_first))
                rows.append({"t_s": round(t, 1), "body_state": SEEN, **row})
                out.append(ch.update(rows[-1]))
                t += 0.1
            (change,) = [r for r in out if r["main_user_prev_track"] is not None]
            return change, ch, rows

        def run(*args, **kwargs):
            return stitch(*args, **kwargs)[0]
        bowed = (0.42, 0.40, 0.62, 0.70)                           # 2/3 box heights lower, same size (IoU 0.18)
        got = run(bowed)
        self.assertAlmostEqual(got["main_user_new_start_s"], 0.1)
        self.assertAlmostEqual(got["main_user_start_shift"], math.hypot(0.02 / 0.2, 0.2 / 0.3))
        self.assertAlmostEqual(got["main_user_start_size"], 0.0)
        self.assertIs(got["main_user_stitched"], True)
        self.assertIs(got["main_user_reacquired"], False)          # IoU below track_iou_min: only the stitch says same
        self.assertIs(run(bowed, first_t=0.3)["main_user_stitched"], False)      # seen together: two people
        self.assertLess(run(bowed, first_t=0.3)["main_user_new_start_s"], 0)
        same_frame = run(bowed, first_t=0.5)                       # first seen in the frame of the last box
        self.assertAlmostEqual(same_frame["main_user_new_start_s"], 0.0)
        self.assertIs(same_frame["main_user_stitched"], False)     # two heads in one frame: two people
        self.assertIs(run((0.05, 0.20, 0.25, 0.50))["main_user_stitched"], False)  # began elsewhere (the next one)
        self.assertIs(run((0.45, 0.30, 0.55, 0.42))["main_user_stitched"], False)  # much smaller (farther, behind)
        self.assertIsNone(run(bowed, bounds=(None, None))["main_user_stitched"])   # no boundary: not decided
        ch = MainUserChange(iou_min=0.3, max_gap_s=1.0, window_s=2.0, segment_s=1.0, shift_max=1.0, size_max=0.3)
        for i in range(35):                                        # track 1 until 0.5 s, then nobody until 3.4 s
            t = round(i * DT, 1)
            ch.update({"t_s": t, "primary_track": 1 if i <= 15 else None, "primary_box": here if i <= 5 else None,
                       "head_boxes": [listed(1, here, "primary")] if i <= 5 else [],
                       "body_state": SEEN if i <= 5 else NOT_SEEN, "body_unseen_s": round(max(0.0, t - 0.5), 1)})
        later = ch.update({"t_s": 3.5, "primary_track": 2, "primary_box": here, "body_state": SEEN,
                           "head_boxes": [listed(2, here, "primary")], "body_unseen_s": 0.0})   # the next customer
        self.assertAlmostEqual(later["main_user_new_start_s"], 3.0)
        self.assertAlmostEqual(later["main_user_start_shift"], 0.0)
        self.assertAlmostEqual(later["main_user_start_size"], 0.0)
        self.assertIs(later["main_user_stitched"], False)          # began after track_max_gap_s: not stitched
        self.assertIs(later["main_user_reacquired"], False)        # the place stood empty
        settled, ch, _ = stitch(bowed, first_t=2.6, box_until=2.55)      # the user stood 2.5 s, then bowed
        self.assertIs(settled["main_user_prev_settled"], True)
        self.assertIs(settled["main_user_stitched"], True)
        self.assertIs(ch.settle.settled, True)                     # the same user: Settle does not start again
        _, _, rows = stitch(bowed)
        filled = add_main_user_change([dict(r) for r in rows], PilotParams(stitch_shift_max=1.0, stitch_size_max=0.3))
        self.assertEqual([r["main_user_stitched"] for r in filled if r["main_user_prev_track"] is not None], [True])

    def test_a_box_coordinate_that_is_not_finite_gives_no_break_measure(self):
        """_break gives no shift or size for a box with a NaN coordinate (as _box_height gives no height), so
        stitch_motion leaves that pair out and one such row cannot turn the calibrated stitch value into NaN."""
        from app.modules.vision.columns import _break, stitch_motion
        here = (0.40, 0.20, 0.60, 0.50)
        self.assertEqual(_break(0.0, here, 0.1, (NAN, 0.20, 0.60, 0.50)), (0.1, None, None))
        self.assertEqual(_break(0.0, (0.40, 0.20, 0.60, NAN), 0.1, here)[1:], (None, None))
        rows = [{"t_s": round(i * DT, 1), "primary_track": "1",
                 "primary_box": "nan;0.2;0.6;0.5" if i == 1 else "0.4;0.2;0.6;0.5"} for i in range(3)]
        pairs = stitch_motion(rows, 1.0)
        self.assertEqual(len(pairs), 1)                           # the NaN row's own pair is left out
        self.assertTrue(all(math.isfinite(v) for v in pairs[0]))

    def test_a_stitch_starts_the_size_reference_again_and_a_reacquisition_keeps_it(self):
        """A stitch is no user change, but the size reference starts again (most stitches fall in the walk-up, whose
        smaller sizes would stay in it); a reacquisition in the same place keeps it."""
        from app.modules.vision.columns import FaceSizeRef
        ref = FaceSizeRef()
        row = {"face_state": SEEN, "iod_px": 40.0, "primary_track": 1, "face_in_primary": True}
        self.assertEqual([ref.update(dict(row)) for _ in range(2)], [None, 1.0])
        self.assertIsNone(ref.update({**row, "primary_track": 2, "iod_px": 44.0, "main_user_stitched": True}))
        self.assertAlmostEqual(ref.update({**row, "primary_track": 3, "iod_px": 48.4, "main_user_reacquired": True}),
                               1.1)                                # the reference 44 px of track 2 is kept

    def test_a_reacquisition_allows_body_dropouts_up_to_the_track_gap(self):
        """The place stood empty only when nothing of the user (head box or body) was seen for longer than
        track_max_gap_s, the gap a head track survives: a pose dropout of 0.5 s during a deep bow keeps the place, a
        body unseen for 1.2 s does not. Rows without body_unseen_s keep the every-row reading."""
        from app.modules.vision.columns import MainUserChange
        box = (0.4, 0.2, 0.6, 0.5)

        def change(unseen_from, unseen_to, with_column=True):
            ch = MainUserChange(iou_min=0.3, max_gap_s=1.0, window_s=2.0)
            ch.update({"t_s": 0.0, "primary_track": 1, "primary_box": box, "body_state": SEEN, "head_boxes": [],
                       "body_unseen_s": 0.0})
            t, last_seen = 0.1, 0.0
            while t < 1.55:                                       # no head box from 0.1 s to 1.5 s
                gone = unseen_from - 1e-9 <= t <= unseen_to + 1e-9
                last_seen = last_seen if gone else t
                row = {"t_s": round(t, 1), "primary_track": None, "primary_box": None,
                       "body_state": NOT_SEEN if gone else SEEN, "head_boxes": []}
                if with_column:
                    row["body_unseen_s"] = round(t - last_seen, 1)
                ch.update(row)
                t += 0.1
            last_row = {"t_s": 1.6, "primary_track": 2, "primary_box": box, "body_state": SEEN, "head_boxes": []}
            if with_column:
                last_row["body_unseen_s"] = 0.0
            if unseen_to >= 1.6:                                  # the body still unseen when the head comes back
                last_row.update(body_state=NOT_SEEN, body_unseen_s=round(1.6 - last_seen, 1) if with_column else None)
            return ch.update(last_row)
        short = change(0.6, 1.0)                                  # unseen 0.5 s
        self.assertIs(short["main_user_body_kept"], False)        # not on every row ...
        self.assertAlmostEqual(short["main_user_body_gap_s"], 0.5)
        self.assertIs(short["main_user_reacquired"], True)        # ... but never longer than the track gap
        long = change(0.2, 1.3)                                   # unseen 1.2 s
        self.assertAlmostEqual(long["main_user_body_gap_s"], 1.2)
        self.assertIs(long["main_user_reacquired"], False)        # the place stood empty: the next customer
        back = change(1.2, 1.6)                                   # the head is back before the body: 0.5 s
        self.assertAlmostEqual(back["main_user_body_gap_s"], 0.5)
        self.assertIs(back["main_user_reacquired"], True)
        old = change(0.6, 1.0, with_column=False)
        self.assertIsNone(old["main_user_body_gap_s"])
        self.assertIs(old["main_user_reacquired"], False)         # without the column: the body on every row
        edge = change(0.6, 1.5)                                   # unseen exactly track_max_gap_s (1.0 s)
        self.assertAlmostEqual(edge["main_user_body_gap_s"], 1.0)
        self.assertIs(edge["main_user_reacquired"], True)         # not longer than the track gap
        ch = MainUserChange(iou_min=0.3, max_gap_s=1.0, window_s=2.0)
        for i in range(61):          # head box until 5.0 s with the body unseen from 3.0 s (shoulders out of view),
            t = round(i * DT, 1)     # then no head box from 5.1 to 6.0 s and the body back from 5.2 s
            gone = 30 <= i <= 51
            ch.update({"t_s": t, "primary_track": 1, "primary_box": box if i <= 50 else None, "head_boxes": [],
                       "body_state": NOT_SEEN if gone else SEEN, "body_unseen_s": round(t - 2.9, 1) if gone else 0.0})
        capped = ch.update({"t_s": 6.1, "primary_track": 2, "primary_box": box, "body_state": SEEN, "head_boxes": [],
                            "body_unseen_s": 0.0})
        self.assertAlmostEqual(capped["main_user_body_gap_s"], 0.1)   # counted from the last head box, not from 3.0 s
        self.assertIs(capped["main_user_reacquired"], True)       # the head box was there until 5.0 s: the same place

    def test_main_user_change_keeps_a_bounded_history_of_the_other_heads(self):
        from app.modules.vision.columns import MainUserChange
        change = MainUserChange(iou_min=0.3, max_gap_s=1.0, window_s=2.0)

        def row(t, others):
            return {"t_s": t, "primary_track": 1, "primary_box": (0.4, 0.2, 0.6, 0.5), "body_state": SEEN,
                    "head_boxes": [{"track": k, "h": h, "role": "behind", "rel_dist_med": 2.0} for k, h in others]}
        for i in range(50):                                             # a passer-by (track 5) for 0.5 s, then gone
            change.update(row(i * 0.1, [(2, 0.15)] + ([(5, 0.1)] if i < 5 else [])))
        self.assertEqual(sorted(change.others), [2])                    # track 5 unseen > 1.0 s: dropped
        self.assertLessEqual(len(change.others[2]["hist"]), 21)         # heights of the last 2.0 s only

    def test_aid_columns_say_whose_aid_it_is_from_the_shoulders(self):
        """The owner's words (2026-11-22): whether the main user uses an aid, from the shoulder line. The box holding
        both shoulder points is the main user's; without shoulders the head-box centre; without both, unknown. An aid
        seen on someone else is 'no' for the main user. (Person-level classes: the shoulders find the box; how the aid
        is held is not judged.)"""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.columns import aid_columns
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
        aids = Aids(np.array([[0.30, 0.10, 0.70, 0.95], [0.00, 0.10, 0.25, 0.95]]), np.array([0.72, 0.6]),
                    np.array([[0.09, 0.72, 0.05, 0.04, 0.02], [0.6, 0.1, 0.0, 0.3, 0.0]]), classes, (640, 480))
        pose = np.zeros((33, 4))
        pose[11, :2], pose[12, :2] = (0.42, 0.40), (0.58, 0.40)
        out = aid_columns(aids, pose, None)
        self.assertEqual((out["aid_owner"], out["aid_count"], out["aid_kind"]), ("yes", 2, "standing"))
        self.assertAlmostEqual(out["aid_any_score"], 0.72)
        self.assertAlmostEqual(out["aid_wheelchair_score"], 0.02)
        self.assertEqual(out["aid_box"], (0.30, 0.10, 0.70, 0.95))
        pose[11, :2], pose[12, :2] = (0.05, 0.40), (0.20, 0.40)          # inside the pedestrian's box
        out = aid_columns(aids, pose, None)
        self.assertEqual(out["aid_owner"], "no")
        self.assertAlmostEqual(out["aid_any_score"], 0.3)                 # its walker score, below its pedestrian one
        pose[11, :2], pose[12, :2] = (0.80, 0.40), (0.95, 0.40)          # in no box: no score, still 'no'
        self.assertEqual((aid_columns(aids, pose, None)["aid_owner"], aid_columns(aids, pose, None)["aid_any_score"]),
                         ("no", None))
        self.assertEqual(aid_columns(aids, None, (0.40, 0.10, 0.60, 0.30))["aid_owner"], "yes")   # head-box centre
        self.assertEqual(aid_columns(aids, None, None)["aid_owner"], "unknown")

    def test_phone_columns_tie_the_phone_to_the_main_users_head_or_hand(self):
        """A phone box meeting the main user's head box is 'head' unless another head box overlaps it more; with
        hand_vis_min, one meeting a box spanned by a hand's pose points of the main user (its nose in the head box) is
        'hand'; a phone elsewhere is 'no'; without the head box, or with someone else's pose (or no hand point that
        counts) and a phone not at the head, it cannot be told. Without hand_vis_min no hand box is built: a phone away
        from the heads cannot be told ('unknown', never 'hand'), and the head path is as with the value."""
        import functools
        import numpy as np
        from app.inference.phone import Phones
        from app.modules.vision.columns import phone_columns as unset
        phone_columns = functools.partial(unset, hand_vis_min=VIS_TEST)

        def phones(*boxes):
            return Phones(np.array(boxes, float).reshape(-1, 4), np.array([0.5 + 0.1 * i for i in range(len(boxes))]),
                          (100, 100))
        head = (0.40, 0.10, 0.60, 0.30)
        pose = np.full((33, 4), np.nan)
        pose[0, :2] = (0.50, 0.20)                                # nose in the head box: the main user's pose
        for k, xy in zip((15, 17, 19, 21), ((0.30, 0.60), (0.28, 0.58), (0.29, 0.56), (0.32, 0.57))):
            pose[k, :2] = xy                                      # the left hand around (0.30, 0.58)
        pose[:, 2] = 0.9                                          # visibility above the test limit
        ear = (0.58, 0.15, 0.66, 0.28)                            # beside the head, overlapping its edge
        held = (0.31, 0.50, 0.40, 0.57)                           # touching the hand box
        away = (0.80, 0.80, 0.90, 0.90)
        self.assertEqual((unset(phones(ear), pose, head)["phone_at"], unset(phones(held), pose, head)["phone_owner"],
                          unset(phones(away), pose, head)["phone_owner"], unset(phones(), pose, head)["phone_owner"]),
                         ("head", "unknown", "unknown", "no"))   # no value: the head path only, the hand path held
        out = phone_columns(phones(ear), pose, head)
        self.assertEqual((out["phone_owner"], out["phone_at"], out["phone_count"]), ("yes", "head", 1))
        out = phone_columns(phones(held, away), pose, head)
        self.assertEqual((out["phone_owner"], out["phone_at"], out["phone_box"]), ("yes", "hand", held))
        self.assertAlmostEqual(out["phone_score"], 0.5)
        self.assertEqual(phone_columns(phones(away), pose, head)["phone_owner"], "no")
        self.assertEqual(phone_columns(phones(), None, head)["phone_owner"], "no")             # no phone at all
        self.assertEqual(phone_columns(phones(held), pose, None)["phone_owner"], "unknown")    # no head box
        other = pose.copy()
        other[0, :2] = (0.85, 0.20)                               # the pose's nose outside: someone else's pose
        self.assertEqual(phone_columns(phones(held), other, head)["phone_owner"], "unknown")
        self.assertEqual(phone_columns(phones(ear), other, head)["phone_at"], "head")         # the head box still tells
        self.assertEqual(phone_columns(phones(away), other, head)["phone_owner"], "unknown")
        no_hands = pose.copy()
        no_hands[15:23, :2] = np.nan                              # the main user's pose without one finite hand point
        self.assertEqual(phone_columns(phones(away), no_hands, head)["phone_owner"], "unknown")   # nothing checked
        # several heads: a phone meeting the main user's head box is the main user's only when no other head box of
        # the frame overlaps it more (box_iou); the companion's phone at the companion's ear is not the main user's
        main = {"cx": 0.50, "cy": 0.20, "w": 0.20, "h": 0.20, "role": "primary"}
        beside = {"cx": 0.71, "cy": 0.21, "w": 0.18, "h": 0.18, "role": "companion"}     # (0.62, 0.12, 0.80, 0.30)
        far = {"cx": 0.90, "cy": 0.80, "w": 0.10, "h": 0.10, "role": "behind"}
        out = phone_columns(phones(ear), pose, head, [main, beside])   # ear box: IoU 0.05 with main, 0.10 beside
        self.assertEqual((out["phone_owner"], out["phone_at"]), ("no", None))
        self.assertEqual(phone_columns(phones(ear), other, head, [main, beside])["phone_owner"], "no")   # checked
        self.assertEqual(phone_columns(phones(ear), pose, head, [main, far])["phone_at"], "head")   # no rival head
        self.assertEqual(phone_columns(phones(ear), pose, head, [])["phone_at"], "head")
        out = phone_columns(phones(ear, held), pose, head, [main, beside])   # the user's own phone in the hand stays
        self.assertEqual((out["phone_owner"], out["phone_at"], out["phone_box"]), ("yes", "hand", held))
        big = (0.30, 0.10, 0.55, 0.45)                            # the main user near: a large head box ...
        small = {"cx": 0.63, "cy": 0.23, "w": 0.12, "h": 0.16, "role": "companion"}   # ... and a small one beside
        call = (0.52, 0.20, 0.58, 0.32)                           # share of the phone box: main 0.50, beside 0.15
        out = phone_columns(phones(call), None, big, [dict(main, cx=0.425, cy=0.275, w=0.25, h=0.35), small])
        self.assertEqual((out["phone_owner"], out["phone_at"]), ("yes", "head"))   # (IoU would favour the small head)
        edge = (0.60, 0.15, 0.66, 0.28)                           # touches the main head box's edge only: no area
        self.assertEqual(phone_columns(phones(edge), pose, head, [main, far])["phone_at"], "head")   # tie: main user
        left = {"cx": 0.30, "cy": 0.20, "w": 0.20, "h": 0.20, "role": "primary"}         # main (0.20, 0.10, 0.40, 0.30)
        right = {"cx": 0.70, "cy": 0.20, "w": 0.20, "h": 0.20, "role": "companion"}      # (0.60, 0.10, 0.80, 0.30)
        reach = pose.copy()
        reach[0, :2] = (0.30, 0.20)                               # the main user's nose in the left head box
        for k, xy in zip((15, 17, 19, 21), ((0.55, 0.26), (0.62, 0.30), (0.58, 0.28), (0.56, 0.29))):
            reach[k, :2] = xy                                     # a hand near the companion's ear
        companion_call = (0.58, 0.14, 0.64, 0.28)                 # at the companion's head, not at the main head
        out = phone_columns(phones(companion_call), reach, (0.20, 0.10, 0.40, 0.30), [left, right])
        self.assertEqual((out["phone_owner"], out["phone_at"]), ("no", None))   # another head holds it: not a hand

    def test_hand_points_below_the_visibility_limit_are_no_ownership_evidence(self):
        """With hand_vis_min (params; no value by default) a hand point counts only when its visibility is at least the
        limit: a hidden hand whose position the landmarker estimated spans no hand box, and a point without a
        visibility (NaN) does not count either. The other hand still checks the phone ('no'); with neither hand left the
        hands cannot be checked ('unknown'). Without the limit no hand point is confirmed: no hand box, 'unknown' even
        for a visible hand (the hand path is held)."""
        import numpy as np
        from app.inference.phone import Phones
        from app.modules.vision.columns import phone_columns
        held = (0.31, 0.50, 0.40, 0.57)
        phones = Phones(np.array([held]), np.array([0.6]), (100, 100))
        head = (0.40, 0.10, 0.60, 0.30)
        pose = np.zeros((33, 4))
        pose[:, 2:] = 0.9                                         # visibility, presence
        pose[0, :2] = (0.50, 0.20)                                # nose in the head box: the main user's pose
        for k, xy in zip((15, 17, 19, 21), ((0.30, 0.60), (0.28, 0.58), (0.29, 0.56), (0.32, 0.57))):
            pose[k, :2] = xy                                      # the left hand at the phone
        for k in (16, 18, 20, 22):
            pose[k, :2] = (0.70, 0.70)                            # the right hand away from it
        self.assertEqual(phone_columns(phones, pose, head, hand_vis_min=VIS_TEST)["phone_at"], "hand")   # seen
        hidden = pose.copy()
        hidden[[15, 17, 19, 21], 2] = 0.0                         # the left hand's points not visible
        self.assertEqual((phone_columns(phones, hidden, head)["phone_owner"],
                          phone_columns(phones, pose, head)["phone_owner"]), ("unknown", "unknown"))   # no limit: held
        self.assertEqual(phone_columns(phones, hidden, head, hand_vis_min=VIS_TEST)["phone_owner"], "no")
        unrated = pose.copy()
        unrated[[15, 17, 19, 21], 2] = np.nan                     # no visibility from the landmarker
        self.assertEqual(phone_columns(phones, unrated, head, hand_vis_min=VIS_TEST)["phone_owner"], "no")
        self.assertEqual(phone_columns(phones, unrated, head)["phone_owner"], "unknown")
        both = hidden.copy()
        both[[16, 18, 20, 22], 2] = np.nan                        # neither hand counts: nothing checked
        self.assertEqual(phone_columns(phones, both, head, hand_vis_min=VIS_TEST)["phone_owner"], "unknown")
        self.assertEqual(phone_columns(phones, pose[:, :2], head, hand_vis_min=VIS_TEST)["phone_owner"], "unknown")

    def test_aid_columns_use_the_shoulders_only_when_they_are_the_main_users(self):
        """One pose per frame, not always the main user's. Shoulders under another person's box give way to the main
        user's head box; with the head detector on and no main-user box in the frame there is no anchor."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.columns import aid_columns
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
        aids = Aids(np.array([[0.10, 0.10, 0.35, 0.95], [0.60, 0.12, 0.85, 0.95]]), np.array([0.9, 0.88]),
                    np.array([[0.90, 0.03, 0.02, 0.01, 0.01], [0.05, 0.88, 0.02, 0.01, 0.01]]), classes, (640, 480))
        pose = np.zeros((33, 4))
        pose[11, :2], pose[12, :2] = (0.66, 0.35), (0.80, 0.35)          # the crutch user on the right
        out = aid_columns(aids, pose, (0.15, 0.12, 0.30, 0.30), head_detector=True)   # the main user on the left
        self.assertEqual((out["aid_owner"], out["aid_box"]), ("no", (0.10, 0.10, 0.35, 0.95)))
        self.assertAlmostEqual(out["aid_any_score"], 0.03)
        out = aid_columns(aids, pose, None, head_detector=True)           # no main-user box in this frame
        self.assertEqual((out["aid_owner"], out["aid_any_score"]), ("unknown", None))
        self.assertEqual(aid_columns(aids, pose, None)["aid_owner"], "yes")   # no head detector: the pose's person

    def test_aid_columns_choose_by_the_head_when_a_companion_overlaps(self):
        """Overlapping boxes: the companion's box holds the main user's head and the companion's own shoulders (x 0.34
        and 0.66, midpoint under the user's head); the user's box (x 0.40-0.60) holds the head but not those shoulders.
        With the head detector the head chooses: the user's own box, not the companion's crutch."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.columns import aid_columns
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
        user, companion = [0.40, 0.10, 0.60, 0.95], [0.28, 0.16, 0.72, 0.98]
        aids = Aids(np.array([user, companion]), np.array([0.8, 0.88]),
                    np.array([[0.80, 0.05, 0.01, 0.01, 0.01], [0.05, 0.88, 0.02, 0.01, 0.01]]), classes, (640, 480))
        pose = np.zeros((33, 4))
        pose[11, :2], pose[12, :2] = (0.34, 0.40), (0.66, 0.40)          # the companion's shoulders
        out = aid_columns(aids, pose, (0.45, 0.10, 0.55, 0.30), head_detector=True)
        self.assertEqual((out["aid_owner"], out["aid_box"]), ("no", tuple(user)))
        self.assertAlmostEqual(out["aid_any_score"], 0.05)

    def test_aid_boxes_below_the_person_operating_point_are_only_recorded(self):
        """aid_score_min (0.01) is a recording floor: a box at or below aid_person_min is neither a person seen
        (aid_person_count) nor a candidate for the main user's box."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.columns import aid_columns
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
        own, part = [0.30, 0.10, 0.70, 0.95], [0.38, 0.12, 0.62, 0.60]   # the user's box and a faint partial box
        aids = Aids(np.array([own, part]), np.array([0.7, 0.015]),
                    np.array([[0.05, 0.7, 0.0, 0.0, 0.0], [0.015, 0.0, 0.0, 0.0, 0.0]]), classes, (640, 480))
        head = (0.42, 0.12, 0.58, 0.30)
        out = aid_columns(aids, None, head, head_detector=True, person_min=0.390)
        self.assertEqual((out["aid_count"], out["aid_person_count"], out["aid_box"]), (2, 1, tuple(own)))
        self.assertAlmostEqual(out["aid_any_score"], 0.7)
        out = aid_columns(aids, None, head, head_detector=True)            # no value: every box, count not given
        self.assertEqual((out["aid_person_count"], out["aid_box"]), (None, tuple(part)))

    def test_aid_columns_take_the_box_that_starts_at_the_users_head(self):
        """Overlapping person boxes: the user's own box (pedestrian, top at the user's head) and the larger box of a
        walker user standing behind that also holds the user's shoulders. The box whose top edge meets the user's head
        box is the user's, so the aid behind is not given to the user; a pose that is not under the user's head
        (MediaPipe following someone else) is not used."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.columns import aid_columns
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
        own, behind = [0.35, 0.20, 0.65, 0.98], [0.25, 0.05, 0.75, 0.99]
        aids = Aids(np.array([own, behind]), np.array([0.70, 0.90]),
                    np.array([[0.70, 0.01, 0.01, 0.02, 0.01], [0.05, 0.0, 0.0, 0.90, 0.0]]), classes, (640, 480))
        head = (0.42, 0.20, 0.58, 0.38)
        pose = np.zeros((33, 4))
        pose[11, :2], pose[12, :2] = (0.42, 0.50), (0.58, 0.50)
        out = aid_columns(aids, pose, head)
        self.assertEqual((out["aid_owner"], out["aid_top_class"], out["aid_box"]), ("no", "pedestrian", tuple(own)))
        self.assertAlmostEqual(out["aid_any_score"], 0.02)
        pose[11, :2], pose[12, :2] = (0.05, 0.30), (0.20, 0.30)          # another person's shoulders
        self.assertEqual(aid_columns(aids, pose, head)["aid_box"], tuple(own))   # the head-box centre decides
        wheel = Aids(np.array([own]), np.array([0.8]), np.array([[0.1, 0.0, 0.0, 0.0, 0.8]]), classes, (640, 480))
        out = aid_columns(wheel, None, head)                            # a wheelchair is an assistive device too
        self.assertEqual((out["aid_owner"], out["aid_top_class"], out["aid_kind"]), ("yes", "wheelchair", "wheelchair"))
        self.assertAlmostEqual(out["aid_any_score"], 0.8)
        self.assertAlmostEqual(out["aid_wheelchair_score"], 0.8)

    def test_aid_head_columns_read_the_aid_class_box_that_holds_the_main_users_head_centre(self):
        """The head_centre reading (aid_rule, the kiosk-view detector files): per class the highest kept box that
        contains the centre of the main user's head box, the frame's value the highest class; 0.0 when the head box is
        there and no box contains its centre (a box beside the user, or one that misses the centre); no value without
        a head box; a tie goes to the class first in the model's order; no per-class boxes is an error."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.columns import AID_HEAD_COLUMNS, aid_head_columns
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
        head = (0.40, 0.10, 0.50, 0.30)                                     # centre (0.45, 0.20)
        user, beside, low = [0.30, 0.05, 0.70, 0.95], [0.75, 0.05, 0.95, 0.95], [0.30, 0.25, 0.70, 0.95]

        def frame(class_boxes):
            return Aids(np.zeros((0, 4)), np.zeros(0), np.zeros((0, 5)), classes, (640, 480), {},
                        {c: (np.array(b, float).reshape(-1, 4), np.array(s, float)) for c, (b, s) in
                         {**{c: ([], []) for c in classes[1:]}, **class_boxes}.items()})
        self.assertEqual(AID_HEAD_COLUMNS, ("aid_head_score", "aid_head_class", "aid_head_box"))
        out = aid_head_columns(frame({"wheelchair": ([user, beside], [0.62, 0.9])}), head)
        self.assertEqual(out, {"aid_head_score": 0.62, "aid_head_class": "wheelchair", "aid_head_box": tuple(user)})
        out = aid_head_columns(frame({"wheelchair": ([beside, low], [0.9, 0.8])}), head)   # neither holds the centre
        self.assertEqual(out, {"aid_head_score": 0.0, "aid_head_class": None, "aid_head_box": None})
        self.assertEqual(aid_head_columns(frame({"wheelchair": ([user], [0.62])}), None),
                         dict.fromkeys(AID_HEAD_COLUMNS))
        several = frame({"crutch": ([user], [0.2]), "walker": ([user, low], [0.35, 0.95]),
                         "wheelchair": ([user], [0.3])})
        out = aid_head_columns(several, head)                               # the highest class at the centre
        self.assertEqual((out["aid_head_score"], out["aid_head_class"]), (0.35, "walker"))
        tie = frame({"cane": ([user], [0.4]), "wheelchair": ([user], [0.4])})
        self.assertEqual(aid_head_columns(tie, head)["aid_head_class"], "cane")
        edge = frame({"crutch": ([[0.45, 0.20, 0.60, 0.90]], [0.5])})     # the centre on the box edge counts
        self.assertEqual(aid_head_columns(edge, head)["aid_head_score"], 0.5)
        with self.assertRaises(ValueError):
            aid_head_columns(Aids(np.zeros((0, 4)), np.zeros(0), np.zeros((0, 5)), classes, (640, 480)), head)

    def test_aid_carry_follows_the_users_aid_box_through_rows_without_a_head_box(self):
        """The head_centre_carry reading (AidCarry): a row with the main user's head box gives aid_head_columns' value
        and remembers the aid box; rows without the head box follow that box by the head tracker's rule (the highest
        IoU, at least track_iou_min) and read the matched box's score and class; a box of lower IoU is not taken even
        with a higher score; a 0.0 head row clears the box; nothing matched for longer than track_max_gap_s ends the
        carry; a head row of a new main user replaces the box; nothing is carried without a head row first."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.columns import AID_CARRY_COLUMNS, AID_HEAD_COLUMNS, AidCarry, aid_head_columns
        from app.modules.vision.params import PilotParams
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
        p = PilotParams()
        head = (0.40, 0.10, 0.50, 0.30)                                     # centre (0.45, 0.20)
        user, moved = [0.30, 0.05, 0.70, 0.95], [0.32, 0.06, 0.72, 0.96]    # IoU about 0.91
        near = [0.45, 0.05, 0.85, 0.95]                                     # IoU with moved 0.50, user's 0.89
        other = [0.75, 0.05, 0.98, 0.95]                                    # no overlap with user
        low = [0.30, 0.25, 0.70, 0.95]                                      # misses the head centre

        def frame(class_boxes):
            return Aids(np.zeros((0, 4)), np.zeros(0), np.zeros((0, 5)), classes, (640, 480), {},
                        {c: (np.array(b, float).reshape(-1, 4), np.array(s, float)) for c, (b, s) in
                         {**{c: ([], []) for c in classes[1:]}, **class_boxes}.items()})

        def value(out):
            return out["aid_head_score"], out["aid_head_class"], out["aid_head_from"]
        self.assertEqual(AID_CARRY_COLUMNS, ("aid_head_from",))
        carry = AidCarry(p.track_iou_min, p.track_max_gap_s)
        none = dict.fromkeys(AID_HEAD_COLUMNS + AID_CARRY_COLUMNS)
        seed = frame({"wheelchair": ([user, other], [0.62, 0.9])})
        self.assertEqual(carry.update(0.0, frame({"wheelchair": ([moved], [0.7])}), None), none)   # no seed yet
        out = carry.update(0.1, seed, head)                                 # a head row: head_centre's value
        self.assertEqual({k: out[k] for k in AID_HEAD_COLUMNS}, aid_head_columns(seed, head))
        self.assertEqual(value(out), (0.62, "wheelchair", "head"))
        out = carry.update(0.2, frame({"wheelchair": ([other, moved], [0.9, 0.55])}), None)
        self.assertEqual(value(out) + (out["aid_head_box"],), (0.55, "wheelchair", "carried", tuple(moved)))
        out = carry.update(0.3, frame({"crutch": ([near], [0.95]), "wheelchair": ([user], [0.4])}), None)
        self.assertEqual(value(out), (0.4, "wheelchair", "carried"))         # the higher IoU, not the higher score
        out = carry.update(0.4, frame({"crutch": ([user], [0.3])}), None)     # any aid class
        self.assertEqual(value(out), (0.3, "crutch", "carried"))
        self.assertEqual(carry.update(0.5, frame({"wheelchair": ([other], [0.9])}), None), none)  # IoU 0: no value
        self.assertEqual(value(carry.update(1.4, frame({"wheelchair": ([user], [0.6])}), None)),
                         (0.6, "wheelchair", "carried"))                     # 1.0 s since the last match: alive
        self.assertEqual(carry.update(2.5, frame({"wheelchair": ([user], [0.6])}), None), none)   # 1.1 s: ended
        self.assertEqual(carry.update(2.6, frame({"wheelchair": ([user], [0.6])}), None), none)   # and stays ended
        carry.update(3.0, seed, head)
        out = carry.update(3.1, frame({"wheelchair": ([low], [0.8])}), head)
        self.assertEqual(value(out), (0.0, None, "head"))                    # a 0.0 head row clears the box
        self.assertEqual(carry.update(3.2, seed, None), none)
        carry.update(4.0, seed, head)
        new_head = (0.80, 0.10, 0.90, 0.30)                                  # a new main user inside `other`
        self.assertEqual(value(carry.update(4.1, seed, new_head)), (0.9, "wheelchair", "head"))
        out = carry.update(4.2, frame({"wheelchair": ([user, other], [0.95, 0.5])}), None)
        self.assertEqual((value(out), out["aid_head_box"]), ((0.5, "wheelchair", "carried"), tuple(other)))
        carry.reset()                                                        # a new touch-log session
        self.assertEqual(carry.update(4.3, seed, None), none)

    def test_main_user_change_records_the_size_of_the_head_that_took_over(self):
        """The owner's suggestion (2026-11-22): a person behind is smaller and becomes the next user by stepping
        forward. The change row says how big the new main user's head is against the earlier one, whether that track
        was another head before (its role and rel_dist then) and how much it grew; no threshold is applied."""
        from app.modules.vision.columns import MainUserChange
        change = MainUserChange()

        def row(t, track, primary_h, others=()):
            boxes = [{"track": track, "h": primary_h, "role": "primary", "rel_dist_med": None}] if primary_h else []
            boxes += [{"track": k, "h": h, "role": role, "rel_dist_med": rel} for k, h, role, rel in others]
            box = (0.4, 0.2, 0.6, 0.2 + primary_h) if primary_h else None
            return {"t_s": t, "primary_track": track, "primary_box": box, "body_state": SEEN, "head_boxes": boxes}
        behind = (2, 0.15, "unknown", 2.0)
        got = [change.update(row(0.0, 1, 0.3, [behind])), change.update(row(0.1, 1, 0.3, [(2, 0.15, "behind", 2.0)])),
               change.update(row(0.2, 2, 0.16))]                 # the user's head is lost; the head behind takes over
        last = got[-1]
        self.assertEqual((last["main_user_prev_track"], last["main_user_new_was_role"]), (1, "behind"))
        self.assertAlmostEqual(last["main_user_prev_h"], 0.3)
        self.assertAlmostEqual(last["main_user_new_h"], 0.16)
        self.assertAlmostEqual(last["main_user_h_ratio"], 0.16 / 0.3)
        self.assertEqual(last["main_user_new_rel_dist"], 2.0)
        self.assertAlmostEqual(last["main_user_new_growth"], 0.16 / 0.15)   # still at a behind size
        fresh = change.update(row(0.3, 3, 0.31))                  # a head never seen before
        self.assertEqual((fresh["main_user_prev_track"], fresh["main_user_new_was_role"]), (2, None))
        self.assertIsNone(fresh["main_user_new_growth"])
        self.assertAlmostEqual(fresh["main_user_h_ratio"], 0.31 / 0.16)
        cell = row(0.0, 1, 0.3, [behind])
        cell["head_boxes"] = json.dumps(cell["head_boxes"])       # read back from rows.csv: a JSON cell
        self.assertIsNone(MainUserChange().update(cell)["main_user_prev_track"])

    def test_rewindow_fills_the_scene_columns_only_where_the_rows_lack_them(self):
        from app.modules.vision.params import PilotParams
        from app.modules.vision.tools.companion_eval import fill_scene_columns
        old = [{"t_s": t, "face_state": SEEN, "iod_px": 40.0, "primary_track": k, "primary_box": box,
                "body_state": SEEN, "pitch_deg": p}
               for t, k, box, p in ((0.0, "1", (0, 0, 1, 1), 5.0), (0.1, "1", (0, 0, 1, 1), 8.0),
                                    (0.2, "2", (0.8, 0, 1, 1), 9.0))]             # elsewhere: a new user
        fill_scene_columns(old)
        self.assertEqual([r["iod_ratio_user"] for r in old], [None, 1.0, None])   # the new track starts again
        self.assertEqual([r["head_ratio_user"] for r in old], [None, 1.0, None])
        self.assertEqual([r["dpitch_user_deg"] for r in old], [0.0, 3.0, 0.0])
        self.assertEqual(old[2]["main_user_prev_track"], 1)
        strict = [{k: v for k, v in r.items() if k not in ("iod_ratio_user", "head_ratio_user", "dpitch_user_deg")
                   and not k.startswith("main_user_")} for r in old]
        fill_scene_columns(strict, PilotParams(track_iou_min=0.1))       # the bundle's chain values are used
        self.assertIs(strict[2]["main_user_reacquired"], True)            # IoU 0.2 passes 0.1
        stitch_columns = ("main_user_new_start_s", "main_user_start_shift", "main_user_start_size",
                          "main_user_stitched", "main_user_body_gap_s")
        stale = [{k: v for k, v in r.items() if k not in stitch_columns} for r in old]   # rows.csv before them
        fill_scene_columns(stale, PilotParams(stitch_shift_max=0.1, stitch_size_max=0.1))
        self.assertIs(stale[2]["main_user_stitched"], False)              # written again: 0.4 box widths away
        new = [dict(r, iod_ratio_user=1.7, head_ratio_user=1.6, dpitch_user_deg=30.0, main_user_prev_track=None)
               for r in old]
        fill_scene_columns(new)
        self.assertEqual([(r["iod_ratio_user"], r["head_ratio_user"], r["dpitch_user_deg"]) for r in new],
                         [(1.7, 1.6, 30.0)] * 3)                                   # recorded values stay
        self.assertTrue(all(r["main_user_prev_track"] is None for r in new))

    def test_calibration_tool_takes_mean_plus_two_sd_of_window_medians(self):
        import statistics
        from app.modules.vision.params import load_bundle
        from app.modules.vision.tools.calibrate_scene import main
        folder = tempfile.mkdtemp()
        paths = []
        for k, cy in enumerate((0.4, 0.6)):                      # two standing recordings, 3 s each
            path = os.path.join(folder, f"rec{k}.csv")
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["frame_idx", "t_s", "face_state", "body_state", "face_cy", "iod_px"])
                for i in range(30):
                    w.writerow([i, round(i * DT, 6), SEEN, SEEN, cy, 40 + (i % 2)])
            paths.append(path)
        params = os.path.join(folder, "b.json")
        with open(params, "w", encoding="utf-8") as f:
            json.dump({"bundle_id": "t", "situation": sourced({**SIT_VALUES, "window_s": 1.0})}, f)
        out = os.path.join(folder, "snippet.json")
        with redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(main(["--params", params, "--rows", *paths, "--note", "test rows", "--out", out]), 0)
        self.assertIn("no minimum count", printed.getvalue())
        with open(out, encoding="utf-8") as f:
            chain = json.load(f)["chain"]
        medians = [0.4] * 3 + [0.6] * 3                         # windows end at 1.0, 2.0 and the last row 2.9 s
        expected = statistics.fmean(medians) + 2 * statistics.stdev(medians)
        self.assertAlmostEqual(chain["seated_face_cy_min"]["value"], expected)
        self.assertIn("창 6개(녹화 2개", chain["seated_face_cy_min"]["source"])
        self.assertIn("test rows", chain["seated_face_cy_min"]["source"])
        self.assertIn("approach_ratio_min", chain)
        self.assertIn("computed here", printed.getvalue())       # the face-height pass used the new approach value
        with redirect_stdout(io.StringIO()) as printed:          # one recording: the spread between people is unknown
            self.assertEqual(main(["--params", params, "--rows", paths[0], "--out", out]), 0)
        self.assertIn("no value is written", printed.getvalue())
        with open(out, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["chain"], {})
        with open(params, "w", encoding="utf-8") as f:           # the snippet merges into a bundle as it is
            json.dump({"situation": sourced(SIT_VALUES), "chain": chain}, f)
        self.assertAlmostEqual(load_bundle(params).chain.seated_face_cy_min, expected)

    def test_calibration_leaves_out_the_near_rows_and_the_windows_the_tag_would_not_judge(self):
        """The face-height pass works on the same rows and windows as seated_height: rows above approach_ratio_min
        are left out (a lean lowers the face), and a window whose median stands on fewer than face_visible_min of its
        frames is dropped."""
        from app.modules.vision.tools.calibrate_scene import calibrate

        def recording(k):
            rows = []
            for i in range(30):                           # 2 s standing, then 1 s leaning in: lower and larger
                lean = i >= 20
                rows.append({"frame_idx": i, "t_s": round(i * DT, 6), "face_state": SEEN, "body_state": SEEN,
                             "face_cy": (0.9 if lean else 0.4 + k * 0.05), "iod_ratio_user": 1.5 if lean else 1.0})
            return rows
        recs = [recording(0), recording(1)]
        kept = calibrate(recs, 1.0, 1.0, approach_ratio_min=1.2)["seated_face_cy_min"]["windows"]
        mixed = calibrate(recs, 1.0, 1.0, approach_ratio_min=10.0)["seated_face_cy_min"]["windows"]
        self.assertAlmostEqual(kept["mean"], 0.425)                 # standing rows only
        self.assertGreater(mixed["mean"], kept["mean"])            # the lean rows would raise it
        result = calibrate(recs, 1.0, 1.0, approach_ratio_min=1.2, min_share=0.6)
        self.assertEqual(result["seated_face_cy_min"]["windows_dropped"], 2)   # the lean window of each recording
        self.assertEqual(result["seated_face_cy_min"]["windows"]["n"], 4)

    def test_calibration_writes_no_approach_value_not_above_one(self):
        """A constant distance gives ratios around 1, so mean + 2 SD can stay at or below 1, the reference size
        itself. No value is written, the face-height pass keeps every row, and a bundle refuses such a value."""
        import random
        from app.modules.vision.params import PilotParams
        from app.modules.vision.tools.calibrate_scene import calibrate, snippet
        recordings = []
        for k in range(3):
            rng = random.Random(k)
            recordings.append([{"frame_idx": i, "t_s": round(i * DT, 6), "face_state": SEEN, "body_state": SEEN,
                                "face_cy": 0.4 + k * 0.05, "iod_ratio_user": 0.97 + rng.random() * 0.02}
                               for i in range(30)])
        result = calibrate(recordings, 1.0, 1.0)
        self.assertLessEqual(result["approach_ratio_min"]["windows"]["value"], 1.0)
        self.assertIsNone(result["approach_used"])
        chain = snippet(result, 1.0, 1.0, "")["chain"]
        self.assertEqual(sorted(chain), ["seated_face_cy_min"])
        with self.assertRaises(ValueError):
            PilotParams(approach_ratio_min=1.0)

    def test_calibration_writes_no_approach_value_for_an_exactly_constant_distance(self):
        """An exactly constant distance gives the ratio 1.0 on every row: the window medians do not vary (SD 0), so
        mean + 2 SD is the reference size itself and no approach_ratio_min is written; the face-height pass keeps
        every row and still writes its value."""
        from app.modules.vision.tools.calibrate_scene import calibrate, no_value_reason, snippet
        recordings = [[{"frame_idx": i, "t_s": round(i * DT, 6), "face_state": SEEN, "body_state": SEEN,
                        "face_cy": 0.4 + k * 0.05, "iod_ratio_user": 1.0} for i in range(30)] for k in range(3)]
        result = calibrate(recordings, 1.0, 1.0)
        windows = result["approach_ratio_min"]["windows"]
        self.assertEqual((windows["n"], windows["sd"]), (9, 0.0))
        self.assertEqual(no_value_reason("approach_ratio_min", result["approach_ratio_min"]),
                         "the window medians do not vary")
        self.assertIsNone(result["approach_used"])
        self.assertEqual(result["seated_face_cy_min"]["windows"]["n"], 9)   # every row kept
        self.assertEqual(sorted(snippet(result, 1.0, 1.0, "")["chain"]), ["seated_face_cy_min"])

    def test_calibration_takes_the_stitch_values_from_the_same_heads_motion(self):
        """stitch_shift_max / stitch_size_max = mean + 2 SD of how far the same main-user box moves within
        track_max_gap_s: each box against the last box of the same track at most that much later (a new track is a
        new pair set). No value from one recording; a recording without head boxes does not count as one. The tool's
        main() takes track_max_gap_s from the bundle and writes the stitch value."""
        import statistics
        from app.modules.vision.columns import stitch_motion
        from app.modules.vision.tools.calibrate_scene import calibrate, main, snippet

        def recording(step):                  # 0.1 s rows; the box moves right by `step` box widths per row
            rows = []
            for i in range(30):
                x0 = 0.4 + step * 0.2 * i
                rows.append({"frame_idx": i, "t_s": round(i * DT, 6), "face_state": SEEN, "body_state": SEEN,
                             "face_cy": 0.4, "primary_track": "1" if i < 20 else "2",
                             "primary_box": f"{x0};0.2;{x0 + 0.2};0.5"})
            return rows
        pairs = stitch_motion(recording(0.01), 1.0)
        self.assertEqual(len(pairs), 19 + 9)                      # the last box of each track has no later pair
        self.assertAlmostEqual(pairs[0][0], 0.10)                 # 10 rows (1.0 s) later: 10 x 0.01 box widths
        self.assertAlmostEqual(pairs[0][1], 0.0)
        self.assertEqual(stitch_motion(recording(0.01), None), [])
        recs = [recording(0.01), recording(0.02)]
        result = calibrate(recs, 1.0, 1.0, max_gap_s=1.0)
        shift = result["stitch_shift_max"]["windows"]
        values = [p[0] for r in recs for p in stitch_motion(r, 1.0)]
        self.assertEqual((shift["n"], result["stitch_shift_max"]["recordings_with_windows"]), (len(values), 2))
        self.assertAlmostEqual(shift["value"], statistics.fmean(values) + 2 * statistics.stdev(values))
        chain = snippet(result, 1.0, 1.0, "")["chain"]
        self.assertIn("상자 짝", chain["stitch_shift_max"]["source"])
        self.assertNotIn("stitch_size_max", chain)               # the size never changes: no spread, no value
        self.assertNotIn("stitch_shift_max", snippet(calibrate(recs[:1], 1.0, 1.0, max_gap_s=1.0), 1.0, 1.0,
                                                     "")["chain"])        # one recording: no spread between people
        nobox = [{k: v for k, v in r.items() if k not in ("primary_track", "primary_box")}
                 for r in recording(0.03)]                                # a replay without the head detector
        self.assertEqual(calibrate(recs + [nobox], 1.0, 1.0, max_gap_s=1.0)["stitch_shift_max"]
                         ["recordings_with_windows"], 2)
        self.assertNotIn("stitch_shift_max", snippet(calibrate(recs[:1] + [nobox], 1.0, 1.0, max_gap_s=1.0), 1.0, 1.0,
                                                     "")["chain"])        # still one recording with pairs
        folder = tempfile.mkdtemp()
        paths = []
        for k, rec in enumerate(recs):
            paths.append(os.path.join(folder, f"rec{k}.csv"))
            with open(paths[-1], "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rec[0]))
                w.writeheader()
                w.writerows(rec)
        params = os.path.join(folder, "b.json")
        with open(params, "w", encoding="utf-8") as f:                   # track_max_gap_s: the chain default 1.0
            json.dump({"bundle_id": "t", "situation": sourced({**SIT_VALUES, "window_s": 1.0})}, f)
        out = os.path.join(folder, "snippet.json")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--params", params, "--rows", *paths, "--out", out]), 0)
        with open(out, encoding="utf-8") as f:
            self.assertAlmostEqual(json.load(f)["chain"]["stitch_shift_max"]["value"], shift["value"])

    def test_calibration_of_the_head_boundaries_and_the_pitch_share(self):
        """The head-box passes of calibrate(): head_approach_ratio_min is computed first and leaves the grown head
        rows out of the seated_head_cy_min windows; a head_pitch median on fewer than min_share of its window's frames
        is dropped; a head_approach_ratio_min not above 1 is not written."""
        import statistics
        from app.modules.vision.tools.calibrate_scene import _windows, calibrate, no_value_reason

        def recording(k):
            rows = []
            for i in range(30):
                lean = 20 <= i < 25                       # in the third window the head grows and drops
                cy = 0.95 if lean else 0.40 + 0.01 * (i % 10) + 0.05 * k
                rows.append({"frame_idx": i, "t_s": round(i * DT, 6), "body_state": SEEN,
                             "face_state": SEEN if (i < 20 or i >= 27) else NOT_SEEN,   # the face lost meanwhile
                             "primary_track": "1", "primary_box": (0.4, cy - 0.1, 0.6, cy + 0.1),
                             "head_ratio_user": 3.0 if lean else 1.0 + 0.05 * k,
                             "dpitch_user_deg": 2.0 * k + 0.1 * (i % 10)})
            return rows
        recs = [recording(0), recording(1)]
        result = calibrate(recs, 1.0, 1.0, min_share=0.5)
        head = result["head_approach_ratio_min"]["windows"]["value"]
        self.assertTrue(head is not None and 1.0 < head < 3.0)
        kept = [m for r in recs for m in _windows(r, 1.0, 1.0, None, "head_height", "head_cy_median", 0.5, head)[0]]
        mixed = [m for r in recs for m in _windows(r, 1.0, 1.0, None, "head_height", "head_cy_median", 0.5, None)[0]]
        self.assertNotAlmostEqual(statistics.fmean(kept), statistics.fmean(mixed))
        self.assertAlmostEqual(result["seated_head_cy_min"]["windows"]["mean"], statistics.fmean(kept))
        self.assertEqual(result["head_down_pitch_min"]["windows_dropped"], 2)   # the third window of each recording
        self.assertEqual(result["head_down_pitch_min"]["windows"]["n"], 4)
        low = {"recordings_with_windows": 2, "windows": {"sd": 0.01, "value": 0.99}}
        self.assertIn("not above 1", no_value_reason("head_approach_ratio_min", low))
        below = {"recordings_with_windows": 2, "windows": {"sd": 1.0, "value": -0.5}}
        self.assertIn("not above 0", no_value_reason("head_down_pitch_min", below))   # a bundle would refuse it
        given = calibrate(recs, 1.0, 1.0, min_share=0.5, head_approach_ratio_min=10.0)   # the bundle's head value
        self.assertEqual(given["head_approach_used"], 10.0)
        self.assertAlmostEqual(given["seated_head_cy_min"]["windows"]["mean"], statistics.fmean(mixed))

    def test_read_rows_fills_the_head_and_pitch_columns(self):
        """calibrate_scene.read_rows fills head_ratio_user and dpitch_user_deg on rows.csv that lack them, and writes
        the change columns again on a rows.csv that has main_user_prev_track but not the stitch columns."""
        from app.modules.vision.tools.calibrate_scene import read_rows
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "rows.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["frame_idx", "t_s", "face_state", "body_state", "pitch_deg", "primary_track", "primary_box",
                        "main_user_prev_track"])
            for i, pitch in enumerate((4.0, 4.0, 9.0)):
                w.writerow([i, round(i * DT, 6), SEEN, SEEN, pitch, 1, "0.40;0.30;0.60;0.50", ""])
        rows = read_rows(path)
        self.assertEqual([r["head_ratio_user"] for r in rows], [None, 1.0, 1.0])
        self.assertEqual([r["dpitch_user_deg"] for r in rows], [0.0, 0.0, 5.0])
        self.assertTrue(all("main_user_stitched" in r for r in rows))   # the change columns written again

    def test_add_face_size_ratio_fills_recorded_rows_in_time_order(self):
        from app.modules.vision.columns import add_face_size_ratio
        rows = [{"t_s": t, "face_state": SEEN, "iod_px": v, "primary_track": "1"} for t, v in
                ((0.2, 60.0), (0.0, 40.0), (0.1, 40.0))]
        add_face_size_ratio(rows)
        self.assertEqual([r["iod_ratio_user"] for r in rows], [1.5, None, 1.0])


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
        self.assertEqual(tl.counts(0.4, 0.6)["near_miss_fix_count"], 0)    # the fixing press (0.7 s) is after t1
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
        self.assertEqual([tl.session_since(t) for t in (-2.0, 5.0, 8.05, 8.5)], [None, None, None, 8.1])
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
        busy = sit("consulting_companion")
        (d1, d2, d3, d4, d5), state = self.run_windows([
            win(10, situation=busy), win(11, situation=busy), win(12, situation=busy, taps_segment=1),
            win(13, situation=busy), win(14, measurable=False, situation=busy)])
        self.assertEqual((d1.transition, d1.support, d1.action, d1.rank), ("open", "wait_hold_timer", "wait", 2))
        self.assertEqual(d1.form(), ("none", False))
        self.assertIsNone(d1.jev_request)                          # ask_jev false (JP scene table)
        self.assertEqual(d1.session_signal, {"name": "hold_timer"})
        self.assertEqual((d2.transition, d2.session_signal, d2.scene), ("keep", {"name": "hold_timer"}, "3-2"))
        self.assertEqual((d3.transition, d3.decision_id, d3.session_signal), ("withdraw", d1.decision_id, None))
        self.assertEqual((d4.transition, d4.support, d4.scope), ("open", "wait_hold_timer", d1.scope))   # re-opened
        self.assertNotEqual(d4.decision_id, d1.decision_id)
        self.assertEqual((d5.transition, d5.session_signal), ("keep", None))   # not measurable: no hold_timer
        self.assertEqual(state.held.decision_id, d4.decision_id)
        self.assertEqual(d1.to_dict()["session_signal"], {"name": "hold_timer"})

    def test_3_2_phone_path_ranks_with_the_other_rows(self):
        """The phone path opens the same rank-2 wait as the companion: it wins over a 3-1 row in the same window,
        replaces a held 4-2 highlight (which comes back after the touch ends the wait) and a held 4-1 ask (JP 0-3 ⑤);
        the cues name the companion tag only when the companion path holds, and the path when the phone path holds:
        another tag of the window (here looking_back_with_people_behind, or none known) is not a cue of the 3-2 row."""
        def phone(name="none", tags=True):
            return {**sit(name), "tags": [{"name": "phone_use", "status": tags}]}
        (d,), _ = self.run_windows([win(situation=phone("looking_back_with_people_behind"), screen="menu",
                                        steps_left=2)])
        self.assertEqual((d.transition, d.scene, d.cues), ("open", "3-2", {"path": "phone_use"}))
        unknown = {**phone(), "name": "unknown"}                  # the situation tag unknown, phone_use true
        (d,), _ = self.run_windows([win(situation=unknown)])
        self.assertEqual((d.scene, d.cues), ("3-2", {"path": "phone_use"}))
        (d,), _ = self.run_windows([win(situation=phone("consulting_companion"))])
        self.assertEqual(d.cues, {"tag": "consulting_companion", "path": "phone_use"})
        (d,), _ = self.run_windows([win(situation=phone("consulting_companion", tags="unknown"))])
        self.assertEqual(d.cues, {"tag": "consulting_companion"})   # an unknown phone_use is no path
        lost = dict(screen="menu", steps_left=2, backs_recent=1)
        (h1, w1, w2, h2), _ = self.run_windows([
            win(10, situation=sit("none", 0), **lost), win(11, situation=phone(), **lost),
            win(12, situation=sit("none", 0), taps_segment=1, **lost), win(13, situation=sit("none", 0), **lost)])
        self.assertEqual([(d.transition, d.scene) for d in (h1, w1, w2, h2)],
                         [("open", "4-2"), ("replace", "3-2"), ("withdraw", None), ("open", "4-2")])
        ask = dict(screen="menu", steps_left=2, gaze=True, fixes_recent=self.p.tremor_miss_min, misses_recent=0)
        (a1, w1), state = self.run_windows([win(10, situation=sit("none", 0), **ask), win(11, situation=phone(), **ask)])
        self.assertEqual([(d.transition, d.scene) for d in (a1, w1)], [("open", "4-1"), ("replace", "3-2")])
        self.assertEqual(state.held.support, "wait_hold_timer")

    def test_3_2_phone_path_counts_for_the_wait_only_in_a_window_that_is_not_measurable(self):
        """A window not measurable by the placeholder (no touch, no face) with phone_use true opens or keeps the 3-2
        wait (hold_timer) and nothing else: with the wait refused, a 9-s pause after choosing opens no 4-2 there, and a
        4-2 opened in a measurable window is kept there (without hold_timer); a true scene tag other than phone_use
        changes nothing."""
        R = self.R

        def phone(status=True, name="phone_use"):
            return {**sit("none", 0), "tags": [{"name": name, "status": status}]}
        pause = dict(screen="menu", steps_left=2, pause_s=self.p.lost_pause_s + 1.0)
        (d1, d2), state = self.run_windows([win(5.0, measurable=False, situation=phone()),
                                            win(6.0, measurable=False, situation=phone())])
        self.assertEqual((d1.transition, d1.support, d1.session_signal), ("open", "wait_hold_timer",
                                                                          {"name": "hold_timer"}))
        self.assertEqual((d2.transition, d2.session_signal), ("keep", {"name": "hold_timer"}))
        state = R.react(state, "refuse", d1.decision_id)
        self.assertIn("wait_hold_timer", state.refused)
        (d3,), _ = self.run_windows([win(20.0, measurable=False, situation=phone(), **pause)], state)
        self.assertEqual((d3.transition, d3.support), ("none", None))       # no 4-2 in a phone-only window
        (d4, d6), _ = self.run_windows([win(20.0, measurable=True, situation=phone(), **pause),
                                        win(21.0, measurable=False, situation=phone(), **pause)], state)
        self.assertEqual((d4.transition, d4.scene), ("open", "4-2"))         # measurable: the 4-2 row runs
        self.assertEqual((d6.transition, d6.scene, d6.decision_id, d6.session_signal),
                         ("keep", "4-2", d4.decision_id, None))  # phone-only window, wait refused: the 4-2 stays
        (h, k), _ = self.run_windows([win(5.0, measurable=True, situation=phone()),
                                      win(6.0, measurable=False, situation=phone(True, "aid_use"))])
        self.assertEqual((k.transition, k.session_signal), ("keep", None))   # another tag: not measurable
        (d5,), _ = self.run_windows([win(5.0, measurable=False, situation=phone(True, "aid_use"), **pause)])
        self.assertEqual(d5.transition, "none")
        (q, w), _ = self.run_windows([win(5.0, situation=sit("none", 0), backs_recent=1, screen="menu", steps_left=2),
                                      win(6.0, measurable=False, situation=phone(), screen="menu", steps_left=2)])
        self.assertEqual([(d.transition, d.scene) for d in (q, w)], [("open", "4-2"), ("replace", "3-2")])

    def test_a_kept_decision_keeps_its_content(self):
        lost = dict(situation=sit("none", 0), screen="menu", steps_left=2, backs_recent=1)
        (d1, d2), state = self.run_windows([win(10, **lost), win(11, **lost)])
        self.assertEqual((d1.transition, d1.scene, d1.policy["kind"]), ("open", "4-2", "fit"))
        self.assertIsNotNone(d1.jev_request)
        self.assertEqual((d2.transition, d2.decision_id, d2.scene, d2.policy, d2.cues),
                         ("keep", d1.decision_id, "4-2", d1.policy, d1.cues))
        self.assertIsNone(d2.jev_request)                          # no new Jev question on a keep
        self.assertEqual(d2.to_dict()["steps_left"], 2)
        self.assertEqual(state.snapshot()["held"]["scene"], "4-2")

    def test_execution_fields_of_notices_and_highlights(self):
        R = self.R
        self.assertEqual(R.execution(R.NOTICE, win(screen="menu", steps_left=2)),
                         {"steps_left": 2, "target_id": "cart_progress", "message_id": "steps_left_notice"})
        self.assertEqual(R.execution(R.DELAY, win(screen="menu", steps_left=2))["message_id"],
                         "delay_responsibility_notice")
        highlight = [R.execution(R.HIGHLIGHT, win(screen=s, steps_left=2, options_open=o))["target_id"]
                     for s, o in (("menu", True), ("review", False), ("menu", False))]
        self.assertEqual(highlight, ["cart-add", "cart:*:decrease", None])
        self.assertIsNone(R.execution(R.BIG, win(screen="menu", steps_left=2))["target_id"])
        (d,), _ = self.run_windows([win(situation=sit("looking_back_with_people_behind"), screen="menu", steps_left=2)])
        self.assertEqual({k: d.to_dict()[k] for k in ("steps_left", "target_id", "message_id")},
                         {"steps_left": 2, "target_id": "cart_progress", "message_id": "steps_left_notice"})

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

    def test_away_from_screen_reads_the_gaze_gate_or_a_head_box_without_a_face(self):
        """phone_use's hand path: away = the gaze gate says away, or the segment has rows with the main user's head box
        and none of them shows the main user's face (the camera above the screen); not away when one of them shows it;
        unknown only without the head box. face_in_primary read back from rows.csv ('True' / 'False') reads as in
        memory."""
        from app.modules.vision.chain import away_from_screen as away
        sp = sit_params()                                          # offscreen_yaw_deg 30 (test value)
        box = (0.38, 0.22, 0.62, 0.58)
        face_lost = {"face_state": NOT_SEEN, "yaw_deg": NAN, "face_cx": NAN}      # the body is still seen
        self.assertFalse(away(rows_of([(3, {"yaw_deg": 10.0, "primary_box": box})]), sp))   # facing the screen
        self.assertTrue(away(rows_of([(3, {"yaw_deg": -45.0})]), sp))                       # the gaze gate: away
        self.assertTrue(away(rows_of(facing(3), [(2, {**face_lost, "primary_box": box})]), sp))   # head, no face
        self.assertIsNone(away(rows_of(facing(3), [(2, face_lost)]), sp))                    # no head box: unknown
        self.assertIsNone(away(rows_of(facing(3), [(2, {**face_lost, "primary_box": None})]), sp))
        for other in (False, "False"):                            # someone else's face, in memory and read back
            row = {"yaw_deg": NAN, "face_in_primary": other, "primary_box": box}
            self.assertTrue(away(rows_of(facing(3), [(2, row)]), sp), other)
        for mine in (True, "True"):
            self.assertFalse(away(rows_of([(3, {"yaw_deg": NAN, "face_in_primary": mine, "primary_box": box})]), sp))
        head_only = {**face_lost, "body_state": NOT_SEEN, "primary_box": box}
        self.assertFalse(away(rows_of([(3, {"yaw_deg": 10.0, "primary_box": box})], [(1, head_only)]), sp))
        missed = rows_of([(9, {"yaw_deg": 0.0, "primary_box": box})], [(1, {**face_lost, "primary_box": box})])
        self.assertFalse(away(missed, sp))                          # one missed face frame while reading the screen
        stray = {"yaw_deg": 40.0, "primary_box": None, "face_in_primary": None}   # head box dropped, face unmatched
        self.assertFalse(away(rows_of([(9, {"yaw_deg": 0.0, "primary_box": box, "face_in_primary": True})],
                                      [(1, stray)]), sp))           # no direction evidence: the boxed face decides
        looked_away = [(9, {"yaw_deg": 40.0, "primary_box": box, "face_in_primary": True})]
        turned = {"yaw_deg": 0.0, "primary_box": None, "face_in_primary": None}   # the mirror: unmatched, toward the screen
        self.assertTrue(away(rows_of(looked_away, [(1, turned)]), sp))   # skipped: the confirmed face before it decides
        from app.modules.vision.chain import facing as gate
        self.assertTrue(gate(rows_of(looked_away, [(1, turned)]), sp))   # the rule table's gate reads every face
        self.assertIs(gate(rows_of(looked_away, [(1, turned)]), sp, main_only=True), False)
        lost_in_box = {**face_lost, "primary_box": box}           # turning further: the face lost, the head box kept
        self.assertTrue(away(rows_of(looked_away, [(1, lost_in_box)]), sp))   # boxed faces only turned away: away
        self.assertIsNone(away(rows_of(facing(3)), None))                                  # no situation values

    def test_away_from_screen_reads_the_new_user_only_after_a_change_in_the_segment(self):
        """phone_use's hand path after a change of user inside the segment: the earlier user's face turned to the
        screen does not decide the new user's 'away' (the new user's head box without a face: away). A reacquired or
        stitched track, or a swap before the earlier user settled, keeps the earlier rows (not away)."""
        from app.modules.vision.chain import away_from_screen as away
        sp = sit_params()
        box = (0.38, 0.22, 0.62, 0.58)
        flags = {"main_user_prev_track": 1, "main_user_prev_settled": True, "main_user_reacquired": False,
                 "main_user_stitched": False}
        earlier = {"yaw_deg": 0.0, "primary_box": box, "face_in_primary": True, "primary_track": 1}
        new = {"face_state": NOT_SEEN, "yaw_deg": NAN, "face_cx": NAN, "primary_box": box, "face_in_primary": None,
               "primary_track": 2}                                # looking down: the head box without a face
        seg = rows_of([(5, earlier)], [(1, {**new, **flags})], [(4, new)])
        self.assertIs(away(seg, sp), True)
        for kept in ({"main_user_reacquired": True}, {"main_user_stitched": "True"}, {"main_user_prev_settled": False}):
            rows = [dict(r) for r in seg]
            rows[5].update(kept)
            self.assertIs(away(rows, sp), False, kept)

    def gate_after_change(self, **change):
        """The review's input (PR #98, 1a8852c, chain.facing): one touch-log session; the main user (track 1) faces the
        screen until 5.4 s, the main user changes at 5.5 s (track 2, seen as a head box only: no face, no body), two
        off-button presses fixed at once (3.0 / 3.2 s and 5.6 / 5.7 s) up to the window ending at 6.0 s. change = the
        change row's flags. Returns (user_changed, facing_screen, (transition, support))."""
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.touch import load_timeline
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        miss = {"target": None, "nearestCandidates": [{"id": "product:1", "kind": "button"}]}
        press = {"target": {"id": "product:1", "kind": "button", "disabled": False}}
        events = [(-1000, "session_start", "menu", None), (-900, "screen_enter", "menu", None),
                  (3000, "pointer_start", "menu", miss), (3200, "pointer_start", "menu", press),
                  (5600, "pointer_start", "menu", miss), (5700, "pointer_start", "menu", press)]
        tl = load_timeline(touch_log(folder, events, video), video)
        box = (0.38, 0.22, 0.62, 0.58)
        flags = {"main_user_prev_track": None, "main_user_prev_settled": None, "main_user_reacquired": None,
                 "main_user_stitched": None}
        earlier = {"primary_track": 1, "primary_box": box, "face_in_primary": True, "head_count": 1, **flags}
        head_only = {**earlier, "primary_track": 2, "face_state": NOT_SEEN, "body_state": NOT_SEEN, "yaw_deg": NAN,
                     "face_cx": NAN, "face_in_primary": None}
        first = {**head_only, "main_user_prev_track": 1, "main_user_prev_settled": True, "main_user_reacquired": False,
                 "main_user_stitched": False, **change}
        rows = rows_of([(55, earlier)], [(1, first)], [(5, head_only)])
        rec = WindowJudge(bundle(), tl).evaluate(rows, 6.0)
        tags = {t["name"]: t["status"] for t in rec["situation"]["tags"]}
        return tags["user_changed"], rec["vision"]["facing_screen"], (rec["decision"]["transition"],
                                                                     rec["decision"]["support"])

    def test_after_a_change_of_user_the_gaze_gate_reads_the_new_user_only(self):
        """The earlier user's face toward the screen does not stand for the new user's gaze: the gate cannot tell
        (None), so 4-1 takes its raised criterion (tremor_miss_min_no_gaze) and two fixes open nothing."""
        self.assertEqual(self.gate_after_change(), (True, None, ("none", None)))

    def test_a_reacquired_or_stitched_track_keeps_the_gaze_gate_history(self):
        """The same user found again or stitched back: the gate reads the face before the new track, as before, and two
        fixes while facing the screen offer the large buttons."""
        self.assertEqual(self.gate_after_change(main_user_reacquired=True)[1:], (True, ("open", "large_button")))
        self.assertEqual(self.gate_after_change(main_user_stitched=True)[1:], (True, ("open", "large_button")))

    def boundary_window(self, **change):
        """The reviewers' input (PR #98, bade183, events.py:562): one touch-log session on the menu, somebody behind
        all along; the earlier user (track 1) faces the screen until 1.9 s; the new user (track 2) enters exactly at
        2.0 s, the first row of the judgment window [2.0, 8.0], already turning off the screen, then looks back once more
        at 3.2 s. change = the change row's flags. Returns (look_back events of the window, situation name, (transition,
        support))."""
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.touch import load_timeline
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        tl = load_timeline(touch_log(folder, [(-1000, "session_start", "menu", None),
                                              (-900, "screen_enter", "menu", None)], video), video)
        box = (0.38, 0.22, 0.62, 0.58)
        user = {"primary_box": box, "face_in_primary": True, "head_count": 2, "people_behind_count": 1,
                **dict.fromkeys(("main_user_prev_track", "main_user_prev_settled", "main_user_reacquired",
                                 "main_user_stitched"))}
        earlier, new = {**user, "primary_track": 1}, {**user, "primary_track": 2}
        flags = {"main_user_prev_track": 1, "main_user_prev_settled": True, "main_user_reacquired": False,
                 "main_user_stitched": False, **change}
        turn = [(n, {**new, **over}) for n, over in look_back()]
        rows = rows_of([(20, earlier)], [(1, {**turn[0][1], **flags})], turn[1:], [(4, new)], turn, [(41, new)])
        rec = WindowJudge(bundle(), tl).evaluate(rows, 8.0)
        backs = [e for e in rec["turns"] if e["kind"] == "look_back"]
        return [e["t_start"] for e in backs], rec["situation"]["name"], (rec["decision"]["transition"],
                                                                        rec["decision"]["support"])

    def test_a_change_on_the_first_row_of_the_window_drops_the_context_before_it(self):
        """The window's first row starts a new user: the rows before the window are the earlier user's and give the new
        user's first turn no facing frame to start from. One look-back (3.2 s), not two, and 3-1 opens nothing."""
        backs, name, decision = self.boundary_window()
        self.assertEqual((backs, decision), ([3.2], ("none", None)))
        self.assertNotEqual(name, "looking_back_with_people_behind")

    def test_a_reacquired_or_stitched_track_on_the_first_row_keeps_the_context(self):
        """The same boundary with the same user found again or stitched back: the context rows are kept as before, the
        turn at 2.0 s counts and 3-1 opens."""
        for flags in ({"main_user_reacquired": True}, {"main_user_stitched": True}):
            backs, name, decision = self.boundary_window(**flags)
            self.assertEqual((backs, name, decision), ([2.0, 3.2], "looking_back_with_people_behind",
                                                       ("open", "remaining_steps_notice")), flags)

    def test_a_change_on_the_first_row_of_the_segment_or_window_for_the_gate_and_a_scene_measure(self):
        """The gaze gate with the change on the segment's first row reads that segment only (the new user seen as a head
        box only: None); face_height with the change on the window's first row reads the window's rows, all the new
        user's. Neither reads rows before its own span."""
        from app.modules.vision.chain import facing
        from app.modules.vision.events import observe_scene
        box = (0.38, 0.22, 0.62, 0.58)
        earlier = {"primary_track": 1, "primary_box": box, "face_in_primary": True, "face_cy": 0.8}
        head_only = {**earlier, "primary_track": 2, "face_state": NOT_SEEN, "body_state": NOT_SEEN, "yaw_deg": NAN,
                     "face_cx": NAN, "face_in_primary": None, "face_cy": None}
        flags = {"main_user_prev_track": 1, "main_user_prev_settled": True, "main_user_reacquired": False,
                 "main_user_stitched": False}
        seg = rows_of([(1, {**head_only, **flags})], [(9, head_only)], start=5.1)
        self.assertIsNone(facing(seg, sit_params()))
        rows = rows_of([(20, earlier)], [(1, {**earlier, "primary_track": 2, "face_cy": 0.3, **flags})],
                       [(19, {**earlier, "primary_track": 2, "face_cy": 0.3})])
        (height,) = observe_scene(rows, (2.0, 3.9)).of("face_height")
        self.assertEqual(height["obs"], {"face_cy_median": 0.3, "rows": 20})

    def test_after_a_change_of_user_the_segment_observations_read_the_new_user_only(self):
        """measurable's face and vision_summary's face / body / mouth values after a change inside the segment: the
        earlier user's face does not make the new user's segment measurable; the scene's values (head boxes) and the
        frame count read every row. A reacquired or stitched track keeps the earlier rows."""
        from app.modules.vision.chain import WindowJudge
        box = (0.38, 0.22, 0.62, 0.58)
        earlier = {"primary_track": 1, "primary_box": box, "face_in_primary": True, "head_count": 1,
                   "mouth_motion": 0.4}
        head_only = {**earlier, "primary_track": 2, "face_state": NOT_SEEN, "body_state": NOT_SEEN, "yaw_deg": NAN,
                     "face_cx": NAN, "face_in_primary": None, "mouth_motion": None}

        def judge(**flags):
            first = {**head_only, "main_user_prev_track": 1, "main_user_prev_settled": True,
                     "main_user_reacquired": False, "main_user_stitched": False, **flags}
            rec = WindowJudge(bundle()).evaluate(rows_of([(55, earlier)], [(1, first)], [(5, head_only)]), 6.0)
            v = rec["vision"]
            return rec["measurable"], (v["frames"], v["face_seen_ratio"], v["body_seen_ratio"], v["head_count_max"],
                                       v["mouth_motion_max"])
        self.assertEqual(judge(), (False, (10, 0.0, 0.0, 1.0, None)))   # (5.0, 6.0]: 4 earlier rows, 6 new rows
        for flags in ({"main_user_reacquired": True}, {"main_user_stitched": True}):
            self.assertEqual(judge(**flags), (True, (10, 0.4, 0.4, 1.0, 0.4)), flags)

    @staticmethod
    def user_change_rows(**change):
        """The review's input (PR #98, 2026-11-22 and 11-24): one UI session, a 6-s window; 0.0-3.9 s main-user track 1
        with its phone at the head, 4.0-6.0 s track 2 without a phone, facing the screen; no touch, the body still.
        change = the change row's flags (main_user_prev_settled, main_user_reacquired, main_user_stitched)."""
        box = (0.38, 0.22, 0.62, 0.58)
        first = {"primary_track": 1, "primary_box": box, "face_in_primary": True, "head_count": 1,
                 "phone_owner": "yes", "phone_at": "head", "phone_score": 0.6,
                 **dict.fromkeys(("main_user_prev_track", "main_user_prev_settled", "main_user_reacquired",
                                  "main_user_stitched"))}
        second = {**first, "primary_track": 2, "phone_owner": "no", "phone_at": None, "phone_score": None}
        flags = {"main_user_prev_track": 1, "main_user_prev_settled": True, "main_user_reacquired": False,
                 "main_user_stitched": False, **change}
        return rows_of([(40, first)], [(1, {**second, **flags})], [(20, second)])

    def judge_user_change(self, **change):
        """(user_changed, phone_use, (transition, support)) of the window ending at 6.0 s, min_events 2."""
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.params import Bundle, PilotParams
        rec = WindowJudge(Bundle(PilotParams(), sit_params(min_events=2), "test")).evaluate(
            self.user_change_rows(**change), 6.0)
        tags = {t["name"]: (t["status"], t["unknown_reason"]) for t in rec["situation"]["tags"]}
        return tags["user_changed"], tags["phone_use"], (rec["decision"]["transition"], rec["decision"]["support"])

    def test_after_a_change_of_user_the_earlier_users_phone_opens_no_wait(self):
        """After a confirmed change of user (user_changed true) only the new user's rows feed the phone segments: the
        earlier user's call opens no 3-2 wait. The segments before the change have no rows of the new user, so
        phone_use cannot tell (review of PR #98 on 9ad34c2, events.py:614)."""
        self.assertEqual(self.judge_user_change(),
                         ((True, None), ("unknown", "phone_owner_unknown"), ("none", None)))

    def test_a_reacquired_track_keeps_its_phone_history(self):
        """The same user found again in the same place (main_user_reacquired) is no change: the phone segments keep the
        rows before the new track, and the call opens the wait."""
        self.assertEqual(self.judge_user_change(main_user_reacquired=True),
                         (("unknown", "reacquired_same_place"), (True, None), ("open", "wait_hold_timer")))
        self.assertEqual(self.judge_user_change(main_user_reacquired="True")[1:],     # read back from rows.csv
                         ((True, None), ("open", "wait_hold_timer")))

    def test_a_stitched_track_keeps_its_phone_history(self):
        """A track stitched back to the same user (main_user_stitched), and a swap before the earlier user settled
        (main_user_prev_settled False), are no change: the phone segments keep the rows before the new track."""
        for flags in ({"main_user_stitched": True}, {"main_user_prev_settled": False}, {"main_user_stitched": "True"}):
            self.assertEqual(self.judge_user_change(**flags),
                             ((False, None), (True, None), ("open", "wait_hold_timer")), flags)

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

    def test_the_window_record_and_the_contract_view_carry_the_scene_tags(self):
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.judgment.rule_table_v0 import SCENE_OF_TAG
        from app.modules.vision.situation import SCENE_TAGS, TAGS
        rows = rows_of(facing(30), extra={**FULL, "face_cy": 0.7, "iod_ratio_user": 1.0})
        rec = WindowJudge(bundle(seated_face_cy_min=0.6, approach_ratio_min=1.2)).evaluate(rows, 2.9)
        self.assertEqual({t["name"]: t["status"] for t in rec["situation"]["tags"]},
                         {"seated_height": True, "face_approach": False, "user_changed": "unknown", "none_seen": False,
                          "aid_use": "unknown", "phone_use": "unknown"})
        ext = rec["contract"]["extension"]["situation"]["tags"]
        self.assertEqual([t["name"] for t in ext], list(SCENE_TAGS))
        self.assertEqual((ext[0]["status"], ext[0]["unknown_reason"]), (True, None))
        self.assertEqual(ext[0]["evidence_ids"], ["face_height@0"])
        self.assertEqual(ext[2]["unknown_reason"], "column:primary_track")
        plain = WindowJudge(bundle()).evaluate(rows, 2.9)              # chain defaults: no boundary values
        self.assertEqual([t["status"] for t in plain["situation"]["tags"]][:2], ["unknown", "unknown"])
        self.assertEqual({k: v for k, v in plain["situation"].items() if k != "tags"},
                         {k: v for k, v in rec["situation"].items() if k != "tags"})
        self.assertEqual(WindowJudge(bundle(situation=False)).evaluate(rows, 2.9)["situation"]["tags"], [])
        self.assertEqual(set(SCENE_OF_TAG), set(TAGS) | set(SCENE_TAGS))
        self.assertEqual([SCENE_OF_TAG[n] for n in SCENE_TAGS],
                         ["wheelchair", "lowvision", "newcustomer", "absence", "aid", "busy"])

    def test_the_window_record_and_the_contract_view_say_which_detectors_ran(self):
        """'detectors' = {heads, aids, phones}: a detector counts when a row of the segment carries its column (head_count,
        aid_owner, phone_owner; a blank phone_owner on a frame phone_every skipped still counts). The contract view's
        extension carries the same; model_version stays the same string."""
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.contract_view import MODEL_VERSION
        none_ran = WindowJudge(bundle()).evaluate(rows_of(facing(30)), 2.9)
        self.assertEqual(none_ran["detectors"], {"heads": False, "aids": False, "phones": False})
        every = rows_of(facing(30), extra={**FULL, "head_count": 1, "aid_owner": "no", "phone_owner": None})
        rec = WindowJudge(bundle()).evaluate(every, 2.9)
        self.assertEqual(rec["detectors"], {"heads": True, "aids": True, "phones": True})
        self.assertEqual(rec["contract"]["extension"]["detectors"], rec["detectors"])
        heads = WindowJudge(bundle(situation=False)).evaluate(rows_of(facing(30), extra={**FULL, "head_count": 0}), 2.9)
        self.assertEqual(heads["contract"]["extension"]["detectors"], {"heads": True, "aids": False, "phones": False})
        self.assertEqual({r["contract"]["extension"]["model_version"] for r in (none_ran, rec, heads)}, {MODEL_VERSION})
        empty = WindowJudge(bundle()).evaluate(every, 9.0)          # no row in the segment (8.0, 9.0]
        self.assertEqual((empty["frames"], empty["detectors"]), (0, {"heads": False, "aids": False, "phones": False}))

    def test_the_window_record_lists_its_head_turns_with_the_loss_context(self):
        """'turns' = the window's look_back / yaw_sweep_offscreen events and their observations; the pre-loss head
        pose uses the chain's mouth_baseline_s (2.0 s by default) as its window. No value bundle: no events, None."""
        from app.modules.vision.chain import WindowJudge
        rows = rows_of(facing(5), look_back(), facing(10))
        rec = WindowJudge(bundle()).evaluate(rows, 2.2)
        (turn,) = rec["turns"]
        self.assertEqual((turn["event_id"], turn["kind"]), ("look_back@5", "look_back"))
        self.assertEqual(turn["obs"]["pre_loss_yaw_deg"], 0.0)              # the five facing frames before 0.5 s
        self.assertIsNone(turn["obs"]["pre_loss_pitch_deg"])                # the synthetic rows carry no pitch
        self.assertAlmostEqual(turn["obs"]["loss_duration_s"], 0.4)         # lost frames at 0.7 .. 1.1 s
        self.assertAlmostEqual(turn["obs"]["shoulder_vis_mean"], 0.9)
        self.assertNotIn("turns", rec["contract"]["extension"])
        self.assertIsNone(WindowJudge(bundle(situation=False)).evaluate(rows, 2.2)["turns"])

    def test_the_bundle_carries_both_gates_to_the_scene_tags(self):
        """WindowJudge passes head_down_pitch_min and head_approach_ratio_min from the bundle to the scene tags: a
        bowed window whose face grew is no face approach with the head-down value and one without it; head rows grown
        by a lean are left out of seated_height's head-box path with the head value (head_near)."""
        from app.modules.vision.chain import WindowJudge

        def tags(rows, **chain):
            out = WindowJudge(bundle(**chain)).evaluate(rows, 0.9)["situation"]["tags"]
            return {t["name"]: (t["status"], t["unknown_reason"]) for t in out}
        bowed = rows_of([(10, {})], extra={**FULL, "iod_ratio_user": 1.4, "dpitch_user_deg": 30.0})
        self.assertEqual(tags(bowed, approach_ratio_min=1.2)["face_approach"], (True, None))
        gated = tags(bowed, approach_ratio_min=1.2, head_down_pitch_min=PITCH_TEST)
        self.assertEqual(gated["face_approach"], (False, None))
        lean = rows_of([(10, {"face_state": NOT_SEEN})], extra={**FULL, "primary_track": 1, "head_count": 1,
                                                                 "primary_box": "0.40;0.60;0.60;0.90",
                                                                 "head_ratio_user": 1.4})
        seated = dict(seated_face_cy_min=0.6, seated_head_cy_min=0.7)
        self.assertEqual(tags(lean, **seated)["seated_height"], (True, None))
        self.assertEqual(tags(lean, head_approach_ratio_min=1.2, **seated)["seated_height"], ("unknown", "head_near"))

    def test_a_new_touch_log_session_starts_the_state_again(self):
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.touch import load_timeline
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        events = [(-1000, "session_start", "menu", None), (-900, "screen_enter", "menu", None),
                  (1000, "screen_enter", "review", {"from": "menu"}),
                  (2000, "screen_enter", "menu", {"from": "review"}),
                  (6000, "session_end", "menu", {"reason": "server_session_change"}),
                  (6100, "session_start", "menu", {"reason": "server_session_change"}, "s2"),
                  (6100, "screen_enter", "menu", None, "s2")]
        judge = WindowJudge(bundle(), load_timeline(touch_log(folder, events, video), video))
        rows = rows_of(facing(90))
        r1 = judge.evaluate(rows, 4.0)                             # the back at 2.0 s opens the 4-2 highlight
        self.assertEqual((r1["decision"]["transition"], r1["decision"]["support"], r1["session_reset"]),
                         ("open", "highlight_next_action", False))
        r2 = judge.evaluate(rows, 7.0)                             # session s2: judged from the start
        self.assertTrue(r2["session_reset"])
        self.assertIsNone(r2["session"]["held"])
        self.assertNotEqual(r2["decision"]["transition"], "keep")
        self.assertFalse(judge.evaluate(rows, 8.0)["session_reset"])

    def test_a_new_session_reads_only_its_own_rows(self):
        """The previous user's observations stay out of the next session: look-backs with a person behind in s1 open
        the 3-1 notice there, and every window of s2 reads only the rows from s2's first event, as if s2 were the
        whole record (the 6-s windows at 3.5 / 4.5 / 5.5 s still reach back into s1)."""
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.situation import assess
        from app.modules.vision.touch import load_timeline
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        events = [(-1000, "session_start", "menu", None), (-900, "screen_enter", "menu", None),
                  (3000, "session_end", "menu", {"reason": "server_session_change"}),
                  (3100, "session_start", "menu", {"reason": "server_session_change"}, "s2"),
                  (3100, "screen_enter", "menu", None, "s2")]
        rows = rows_of(facing(5), look_back(), facing(4), look_back(), facing(40),
                       extra={**FULL, "people_behind_count": 1})   # turns end at 1.3 s and 2.5 s, in s1
        judge = WindowJudge(bundle(), load_timeline(touch_log(folder, events, video), video))
        upto = lambda t: [r for r in rows if r["t_s"] <= t]
        r1 = judge.evaluate(upto(3.0), 3.0)
        self.assertEqual((r1["situation"]["name"], r1["decision"]["transition"], r1["decision"]["support"]),
                         ("looking_back_with_people_behind", "open", "remaining_steps_notice"))
        for t in (3.5, 4.5, 5.5):
            r = judge.evaluate(upto(t), t)
            own, _ = assess([x for x in upto(t) if x["t_s"] >= 3.1], t, bundle().situation, landmarker_num_faces=1)
            self.assertEqual(r["session_reset"], t == 3.5)
            self.assertEqual((r["situation"]["name"], r["situation"]["evidence_ids"]), ("none", []))
            self.assertEqual(r["situation"]["name"], own["name"])
            self.assertEqual((r["decision"]["transition"], r["session"]["held"]), ("none", None))
            if t == 3.5:
                self.assertEqual(r["frames"], 5)                   # the segment's rows from 3.1 s on
                self.assertIsNone(r["touch"])                      # a segment reaching into s1 has no touch count

    def test_a_cancelled_or_unsaved_cart_add_press_keeps_the_guidance(self):
        """A press on the cart-add button is an attempt: a cancelled press or a failed order call leaves the cart as it
        was, and the raw log records no result of the press (Touch-Log-Review T06), so neither withdraws the 4-2
        highlight or blocks it for the screen visit; a screen forward still withdraws it (cart_progress)."""
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.touch import load_timeline
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        opened = [(-6000, "session_start", "menu", None), (-5900, "screen_enter", "menu", None),
                  (200, "screen_enter", "review", {"from": "menu"}),
                  (500, "screen_enter", "menu", {"from": "review"})]    # a back: the highlight opens at 1.0 s
        rows = rows_of(facing(40))

        def records(after):
            judge = WindowJudge(bundle(), load_timeline(touch_log(folder, opened + after, video), video))
            return [judge.evaluate(rows, t) for t in (1.0, 2.0, 3.0)]
        cart_add = {"target": {"id": "cart-add", "kind": "button", "disabled": False}}
        for cancelled in (True, False):                            # False: released, then the order call fails
            r1, r2, r3 = records([(900, "options_open", "menu", {"productId": "1"}),
                                  (1500, "pointer_start", "menu", cart_add),
                                  (1600, "pointer_end", "menu", {"inputId": "e5", "cancelled": cancelled})])
            self.assertEqual((r1["decision"]["transition"], r1["decision"]["support"]),
                             ("open", "highlight_next_action"))
            self.assertEqual([r["decision"]["transition"] for r in (r2, r3)], ["keep", "keep"])
            self.assertEqual(r3["decision"]["decision_id"], r1["decision"]["decision_id"])
            self.assertEqual(r3["session"]["withdrawn"], [])
        r1, r2, _ = records([(1500, "pointer_start", "menu", {"target": {"id": "review-open", "kind": "button",
                                                                         "disabled": False}}),
                             (1600, "screen_enter", "review", {"from": "menu"})])
        self.assertEqual((r2["decision"]["transition"], r2["decision"]["decision_id"], r2["decision"]["reason"]),
                         ("withdraw", r1["decision"]["decision_id"], "withdraw condition cart_progress"))


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


class ScheduledHeads:
    """Head boxes (fractions) per call from a schedule: frame k gets schedule[min(k, last)]."""

    def __init__(self, schedule):
        self.schedule, self.calls = schedule, 0

    def __call__(self, img):
        import numpy as np
        from app.inference.head import Heads
        H, W = img.shape[:2]
        frac = np.array(self.schedule[min(self.calls, len(self.schedule) - 1)], float).reshape(-1, 4)
        self.calls += 1
        return Heads(frac, np.array([0.9] * len(frac)), frac * [W, H, W, H], (W, H),
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
        bounds = dict(companion_rel_dist_max=1.6, companion_lateral_min=1.0, behind_rel_dist_min=1.8)  # test values
        chain = FrameChain(FakeModels(schedule), PilotParams(mouth_baseline_s=0.5, **bounds), FakeHeads(behind=True),
                           FakeDirection(), tl, blendshapes=True)
        rows = [chain.process(f) for f in frames(12)]
        r = rows[-1]
        self.assertEqual((r["people_behind_count"], r["companion_box"], r["head_count"]), (1, None, 2))
        self.assertEqual((rows[0]["primary_from"], r["primary_from"], r["head_dir_middle"]), ("face", "track", 0.8))
        self.assertEqual(([b["track"] for b in r["head_boxes"]], r["primary_track"]), ([1, 2], 1))
        self.assertEqual(r["head_boxes"][1]["role"], "behind")
        self.assertAlmostEqual(r["head_boxes"][1]["rel_dist"], 4.5)          # 0.36 / 0.08
        self.assertAlmostEqual(r["shoulder_cx"], 0.5)
        self.assertEqual(r["mouth_motion"], 0.0)                  # an unchanged face after a 0.5-s baseline
        self.assertIsNone(rows[0]["mouth_motion"])
        self.assertEqual([x["tap_count"] for x in rows[4:10]], [0, 1, 0, 1, 1, 1])   # presses at 0.5 / 0.7 / 0.8 / 0.9 s
        self.assertEqual([x["miss_tap_count"] for x in rows[4:10]], [0, 1, 0, 0, None, 0])   # 0.8 s: no target field
        for key in ("ms_heads", "ms_head_dir", "ms_chain", "cpu_ms_chain", "ms_total"):
            self.assertGreaterEqual(r[key], 0.0, key)

    def test_face_size_reference_waits_for_the_first_press_of_the_touch_session(self):
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.params import PilotParams
        from app.modules.vision.touch import load_timeline
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        tl = load_timeline(touch_log(folder, MENU_EVENTS, video), video)   # first press at 0.5 s
        with_log = FrameChain(FakeModels([fake_inference() for _ in range(8)]), PilotParams(), FakeHeads(), None, tl)
        got = [with_log.process(f)["iod_ratio_user"] for f in frames(8)]
        self.assertEqual(got[:6], [None] * 6)        # walking up (before the press), then the press row: no reference
        self.assertAlmostEqual(got[6], 1.0)
        without = FrameChain(FakeModels([fake_inference() for _ in range(3)]), PilotParams(), FakeHeads())
        rows = [without.process(f) for f in frames(3)]
        self.assertIsNone(rows[0]["iod_ratio_user"])  # no touch log: from the main-user track's first face row
        self.assertAlmostEqual(rows[1]["iod_ratio_user"], 1.0)
        self.assertTrue(all(r["main_user_prev_track"] is None for r in rows))   # one main-user track: no change
        no_heads = FrameChain(FakeModels([fake_inference()]), PilotParams()).process(frames(1)[0])
        self.assertNotIn("main_user_prev_track", no_heads)                      # no head detector: column absent

    def test_the_head_pitch_reference_follows_the_main_user_and_the_press(self):
        """dpitch_user_deg in the chain: with a touch log None before the session's first press, then pitch against
        the first main-user face after it (the walk-up rows look 10 deg up); a new touch-log session without a press
        yet is None again. Without a touch log (live.py) it is written from the main-user track's first face."""
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.params import PilotParams
        from app.modules.vision.touch import load_timeline

        def pitched(deg):
            inf = fake_inference()
            a = math.radians(deg)
            inf.face_matrix[:3, :3] = [[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]]
            return inf
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        tl = load_timeline(touch_log(folder, MENU_EVENTS, video), video)   # first press at 0.5 s, session s2 from 8.1 s
        schedule = [pitched(-10.0 if k < 5 else 0.0 if k < 82 else 7.0) for k in range(86)]
        chain = FrameChain(FakeModels(schedule), PilotParams(), FakeHeads(), None, tl)
        got = [chain.process(f)["dpitch_user_deg"] for f in frames(86)]
        self.assertEqual(got[:5], [None] * 5)                                  # walking up, before the press
        self.assertAlmostEqual(got[5], 0.0)
        self.assertAlmostEqual(got[80], 0.0)
        self.assertEqual(got[81:], [None] * 5)                                 # s2 from 8.1 s: waits for its press
        live = FrameChain(FakeModels([pitched(-10.0), pitched(0.0)]), PilotParams(), FakeHeads())
        got = [live.process(f)["dpitch_user_deg"] for f in frames(2)]
        self.assertAlmostEqual(got[0], 0.0)
        self.assertAlmostEqual(got[1], 10.0)
        press = {"target": {"id": "product:1", "kind": "button", "disabled": False}}
        events = [(-1000, "session_start", "menu", None), (500, "pointer_start", "menu", press),
                  (2900, "session_end", "menu", {"reason": "server_session_change"}),
                  (3000, "session_start", "menu", {"reason": "server_session_change"}, "s2"),
                  (3200, "pointer_start", "menu", press, "s2")]
        tl2 = load_timeline(touch_log(tempfile.mkdtemp(), events, video), video)
        no_heads = FrameChain(FakeModels([pitched(0.0 if k < 30 else 10.0) for k in range(36)]), PilotParams(), None,
                              None, tl2)                     # no head detector: the touch-log session is the anchor
        got = [no_heads.process(f)["dpitch_user_deg"] for f in frames(36)]
        self.assertAlmostEqual(got[29], 0.0)
        self.assertAlmostEqual(got[35], 0.0)                 # the next session's user against its own first face

    def test_the_head_size_reference_in_the_chain(self):
        """head_ratio_user as FrameChain writes it with a touch log: from the session's first press, a lean of the head
        box kept out of the reference (head_approach_ratio_min), and a new touch-log session starts it again."""
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.params import PilotParams
        from app.modules.vision.touch import load_timeline
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        press = {"target": {"id": "product:1", "kind": "button", "disabled": False}}
        events = [(-1000, "session_start", "menu", None), (-900, "screen_enter", "menu", None),
                  (500, "pointer_start", "menu", press), (4900, "session_end", "menu", {"reason": "server_session_change"}),
                  (5000, "session_start", "menu", {"reason": "server_session_change"}, "s2"),
                  (5000, "screen_enter", "menu", None, "s2"), (5200, "pointer_start", "menu", press, "s2")]
        tl = load_timeline(touch_log(folder, events, video), video)
        normal, tall = [0.38, 0.22, 0.62, 0.58], [0.38, 0.22, 0.62, 0.72]      # heights 0.36 and 0.50
        boxes = [normal] * 15 + [tall] * 20 + [normal] * 15 + [tall] * 10        # s2 from frame 50: a taller head
        chain = FrameChain(FakeModels([fake_inference() for _ in range(60)]), PilotParams(head_approach_ratio_min=1.2),
                           ScheduledHeads(boxes), None, tl)
        got = [chain.process(f)["head_ratio_user"] for f in frames(60)]
        self.assertEqual(got[:6], [None] * 6)                     # before the press, and the press row itself
        self.assertAlmostEqual(got[14], 1.0)
        self.assertAlmostEqual(got[34], 0.50 / 0.36)              # twenty lean rows later: kept out of the reference
        self.assertIsNone(got[52])                                # s2's first press starts it again
        self.assertAlmostEqual(got[59], 1.0)

    def test_aid_use_with_the_default_value_reads_the_main_users_box(self):
        """The chain's default aid_use_min (0.350): a crutch user's box scored 0.7 is 'uses an aid'; a pedestrian's box
        with a walker score of 0.2 is not; with no aid input the tag stays unknown."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.chain import FrameChain, WindowJudge
        from app.modules.vision.params import PilotParams
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")

        def run(scores):
            def aids(img):
                return Aids(np.array([[0.30, 0.10, 0.70, 0.95]]), np.array([max(scores)]), np.array([scores]), classes,
                            (img.shape[1], img.shape[0]), {"infer": 0.0})
            chain = FrameChain(FakeModels([fake_inference() for _ in range(20)]), PilotParams(), FakeHeads(),
                               aids=aids)
            rows = [chain.process(f) for f in frames(20)]
            tags = WindowJudge(bundle()).evaluate(rows, 1.9)["situation"]["tags"]
            return {t["name"]: (t["status"], t["unknown_reason"]) for t in tags}["aid_use"]
        self.assertEqual(run([0.1, 0.7, 0.0, 0.0, 0.0]), (True, None))
        self.assertEqual(run([0.7, 0.0, 0.0, 0.2, 0.0]), (False, None))
        rows = [FrameChain(FakeModels([fake_inference()] * 3), PilotParams(), FakeHeads()).process(f) for f in frames(3)]
        tags = WindowJudge(bundle()).evaluate(rows, 0.2)["situation"]["tags"]
        self.assertEqual({t["name"]: t["unknown_reason"] for t in tags}["aid_use"], "column:aid_owner")

    def test_aid_use_under_the_head_centre_reading_through_the_chain(self):
        """A stand-in detector output (no model file): a pedestrian box that wins the class-agnostic NMS and, under it,
        a wheelchair-class box at the main user's head. The default reading reads the pedestrian box (aid_use false,
        as before); head_centre reads the wheelchair box: true above its cut, false at a higher one, unknown without
        one (no_value_for_model); the evidence names the class."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.chain import FrameChain, WindowJudge
        from app.modules.vision.params import PilotParams
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
        ped, wheel = [0.30, 0.10, 0.70, 0.95], [0.28, 0.12, 0.72, 0.97]      # both hold the head centre (0.5, 0.4)
        empty = (np.zeros((0, 4)), np.zeros(0))

        def aids(img):
            return Aids(np.array([ped]), np.array([0.8]), np.array([[0.8, 0.0, 0.0, 0.0, 0.02]]), classes,
                        (img.shape[1], img.shape[0]), {"infer": 0.0},
                        {"crutch": empty, "cane": empty, "walker": empty,
                         "wheelchair": (np.array([wheel]), np.array([0.6]))})

        def run(**chain):
            fc = FrameChain(FakeModels([fake_inference() for _ in range(20)]), PilotParams(**chain), FakeHeads(),
                            aids=aids)
            rows = [fc.process(f) for f in frames(20)]
            (tag,) = [t for t in WindowJudge(bundle(**chain)).evaluate(rows, 1.9)["situation"]["tags"]
                      if t["name"] == "aid_use"]
            return (tag["status"], tag["unknown_reason"]), {e["obs"]: e["value"] for e in tag["evidence"]}
        self.assertEqual(run(), ((False, None), {"aid_any_median": 0.02, "rows": 20, "owner_yes_rows": 0}))
        self.assertEqual(run(aid_rule="head_centre", aid_head_min=0.5),
                         ((True, None), {"aid_head_median": 0.6, "rows": 20, "aid_class": "wheelchair"}))
        self.assertEqual(run(aid_rule="head_centre", aid_head_min=0.65)[0], (False, None))
        self.assertEqual(run(aid_rule="head_centre"), (("unknown", "no_value_for_model"), {}))

    def test_aid_use_under_the_carry_reading_through_the_chain(self):
        """aid_rule head_centre_carry: the main user's head box on the first 5 rows only, a wheelchair-class box at the
        user throughout, gone from 1.0 s to 2.0 s and back from 2.1 s. The head rows carry head_centre's values; the
        rows after them follow the box ('carried') until it is gone, and more than track_max_gap_s (1.0 s) without a
        match ends the carry, so the box coming back gives no value. The window at 0.9 s is too_few_rows under
        head_centre (5 of 10 rows) and true under the carry (10 of 10); the default reading writes no aid_head
        column."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.chain import FrameChain, WindowJudge
        from app.modules.vision.columns import AID_CARRY_COLUMNS, AID_HEAD_COLUMNS
        from app.modules.vision.params import PilotParams
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
        head, wheel = [0.38, 0.22, 0.62, 0.58], [0.28, 0.12, 0.72, 0.97]   # the wheel box holds the head centre
        empty = (np.zeros((0, 4)), np.zeros(0))

        def aids_at(k):
            def aids(img):
                box = empty if 10 <= k[0] <= 20 else (np.array([wheel]), np.array([0.6]))
                k[0] += 1
                return Aids(np.zeros((0, 4)), np.zeros(0), np.zeros((0, 5)), classes, (img.shape[1], img.shape[0]),
                            {"infer": 0.0}, {"crutch": empty, "cane": empty, "walker": empty, "wheelchair": box})
            return aids

        def run(**chain):
            fc = FrameChain(FakeModels([fake_inference() for _ in range(30)]), PilotParams(**chain),
                            ScheduledHeads([[head]] * 5 + [[]] * 25), aids=aids_at([0]))
            rows = [fc.process(f) for f in frames(30)]
            (tag,) = [t for t in WindowJudge(bundle(**chain)).evaluate(rows[:10], 0.9)["situation"]["tags"]
                      if t["name"] == "aid_use"]
            return rows, (tag["status"], tag["unknown_reason"]), {e["obs"]: e["value"] for e in tag["evidence"]}
        old, old_tag, _ = run(aid_rule="head_centre", aid_head_min=0.5)
        new, new_tag, evidence = run(aid_rule="head_centre_carry", aid_head_min=0.5)
        self.assertEqual(old_tag, ("unknown", "too_few_rows"))
        self.assertEqual((new_tag, evidence), ((True, None), {"aid_head_median": 0.6, "rows": 10,
                                                              "aid_class": "wheelchair"}))
        for i in range(5):                                       # the head rows: head_centre's values
            self.assertEqual({k: new[i][k] for k in AID_HEAD_COLUMNS}, {k: old[i][k] for k in AID_HEAD_COLUMNS})
        self.assertFalse(any(set(AID_CARRY_COLUMNS) & set(r) for r in old))
        self.assertEqual([r["aid_head_from"] for r in new], ["head"] * 5 + ["carried"] * 5 + [None] * 20)
        self.assertEqual([r["aid_head_score"] for r in new[5:10]], [0.6] * 5)
        self.assertEqual({r["aid_head_score"] for r in old[5:]}, {None})
        default, _, _ = run()
        self.assertFalse(any(set(AID_HEAD_COLUMNS + AID_CARRY_COLUMNS) & set(r) for r in default))

    def test_a_new_touch_log_session_ends_the_aid_carry(self):
        """The carried box is per-user state: a change of the touch-log session clears it with the head tracks and the
        references, so the next session's rows without a head box get no value until a head row of their own."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.params import PilotParams
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
        empty = (np.zeros((0, 4)), np.zeros(0))

        def aids(img):
            return Aids(np.zeros((0, 4)), np.zeros(0), np.zeros((0, 5)), classes, (img.shape[1], img.shape[0]),
                        {"infer": 0.0}, {"crutch": empty, "cane": empty, "walker": empty,
                                         "wheelchair": (np.array([[0.28, 0.12, 0.72, 0.97]]), np.array([0.6]))})

        class TwoSessions:                                      # session s1 before 1.0 s, s2 from then on
            def session_at(self, t):
                return "s1" if t < 1.0 else "s2"

            def session_since(self, t):
                return 0.0 if t < 1.0 else 1.0

            def counts(self, t0, t1):
                return None

            def last_press(self, t):
                return None
        fc = FrameChain(FakeModels([fake_inference() for _ in range(20)]), PilotParams(aid_rule="head_centre_carry"),
                        ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * 3 + [[]] * 17), timeline=TwoSessions(),
                        aids=aids)
        got = [fc.process(f)["aid_head_from"] for f in frames(20)]
        self.assertEqual(got, ["head"] * 3 + ["carried"] * 7 + [None] * 10)

    def test_the_phone_input_opens_the_3_2_wait_through_the_phone_path(self):
        """The phone input is off by default (columns absent, phone_use unknown); with it, a phone in the main user's
        hand in every segment while the user looks away from the screen, no touch and the body still make phone_use
        true, and the rule table opens the 3-2 wait through that path. A touch in the window rules the path out, and so
        does facing the screen. Looking down at the phone loses the face while the head box stays: away from the
        screen, the wait opens; without the head box as well the direction cannot be told (unknown). A face not matched
        to the main user (head box dropped on the last row, face_in_primary None, turned away) is no direction evidence:
        phone_use stays false (review of 2026-11-22 on PR #98). A phone at the
        head (a call) needs no direction, and its window is measurable with the face lost: the wait opens and keeps its
        hold_timer there (the window stays not measurable for every other row). The contract basis names the phone path
        in that window only: a call with the face in view is measurable, every row runs, and the basis stays plain.
        The hand path needs hand_vis_min (VIS_TEST here; the fake hand points are visible); without it the head path
        gives the same columns."""
        import numpy as np
        from app.inference.phone import Phones
        from app.modules.vision.chain import FrameChain, WindowJudge
        from app.modules.vision.columns import PHONE_COLUMNS
        from app.modules.vision.contract_view import BASIS, BASIS_PHONE
        from app.modules.vision.params import PilotParams

        def inference(yaw=40.0, face=True):                      # 40 deg: beyond offscreen_yaw_deg 30, looking away
            inf = fake_inference(yaw=yaw, face=face)
            inf.pose[0, :2] = (0.50, 0.40)                       # nose inside the fake head box
            for k in (15, 17, 19, 21):
                inf.pose[k, :2] = (0.45, 0.80)                   # one hand at the chest
            return inf

        def fake_phones(img):
            return Phones(np.array([[0.40, 0.70, 0.48, 0.82]]), np.array([0.6]), (img.shape[1], img.shape[0]),
                          {"infer": 0.0})
        off = FrameChain(FakeModels([inference()]), PilotParams(), FakeHeads()).process(frames(1)[0])
        self.assertFalse(set(PHONE_COLUMNS) & set(off))
        chain = FrameChain(FakeModels([inference() for _ in range(60)]),
                           PilotParams(phone_every=5, hand_vis_min=VIS_TEST), FakeHeads(), phones=fake_phones)
        rows = [chain.process(f) for f in frames(60)]
        self.assertEqual((rows[55]["phone_owner"], rows[55]["phone_at"]), ("yes", "hand"))   # phone_every 5: 0, 5, ...
        self.assertGreaterEqual(rows[55]["ms_phones"], 0.0)
        self.assertEqual(({rows[k]["phone_owner"] for k in (56, 57, 58, 59)}, rows[59]["ms_phones"]), ({None}, None))
        every = FrameChain(FakeModels([inference() for _ in range(3)]), PilotParams(phone_every=1, hand_vis_min=VIS_TEST),
                           FakeHeads(), phones=fake_phones)
        self.assertEqual([every.process(f)["phone_owner"] for f in frames(3)], ["yes"] * 3)

        def rival(img):     # meets the main user's head box (0.38-0.62) but overlaps the head behind (0.10-0.16) more
            return Phones(np.array([[0.12, 0.21, 0.40, 0.30]]), np.array([0.6]), (img.shape[1], img.shape[0]),
                          {"infer": 0.0})
        row = FrameChain(FakeModels([inference()]), PilotParams(), FakeHeads(behind=True), phones=rival).process(
            frames(1)[0])
        self.assertEqual((len(row["head_boxes"]), row["phone_owner"]), (2, "no"))   # the chain passes every head box

        def phone_tag(rec):
            return {t["name"]: (t["status"], t["unknown_reason"]) for t in rec["situation"]["tags"]}["phone_use"]

        def quiet(rows):
            return [dict(r, tap_count=0, miss_tap_count=0) for r in rows]
        rec = WindowJudge(bundle()).evaluate(rows, 5.9)
        self.assertEqual(phone_tag(rec), ("unknown", "column:tap_count"))   # no touch count: cannot tell
        still = quiet(rows)
        rec = WindowJudge(bundle()).evaluate(still, 5.9)
        self.assertEqual(phone_tag(rec), (True, None))
        self.assertEqual((rec["decision"]["support"], rec["decision"]["transition"]), ("wait_hold_timer", "open"))
        self.assertEqual(rec["decision"]["cues"]["path"], "phone_use")
        self.assertEqual(rec["decision"]["session_signal"], {"name": "hold_timer"})
        still[55]["tap_count"] = 1
        self.assertEqual(phone_tag(WindowJudge(bundle()).evaluate(still, 5.9)), (False, None))

        def run(schedule, phones=fake_phones, params=PilotParams(hand_vis_min=VIS_TEST)):
            chain = FrameChain(FakeModels(schedule), params, FakeHeads(), phones=phones)
            return quiet([chain.process(f) for f in frames(len(schedule))])
        facing = run([inference(yaw=0.0) for _ in range(60)])     # holding the phone while reading the screen
        rec = WindowJudge(bundle()).evaluate(facing, 5.9)
        self.assertEqual((phone_tag(rec), rec["decision"]["support"]), ((False, None), None))
        stray = [dict(r) for r in facing]                        # the last row: head box dropped, an unmatched face
        stray[-1].update(primary_box=None, face_in_primary=None, yaw_deg=40.0)
        rec = WindowJudge(bundle()).evaluate(stray, 5.9)
        self.assertEqual((phone_tag(rec), rec["decision"]["support"]), ((False, None), None))
        away_run = run([inference(yaw=40.0) for _ in range(60)])     # the mirror: looking away, phone in hand
        turned = [dict(r) for r in away_run]                     # the last row: head box dropped, an unmatched face
        turned[-1].update(primary_box=None, face_in_primary=None, yaw_deg=0.0)   # turned to the screen
        rec = WindowJudge(bundle()).evaluate(turned, 5.9)
        self.assertEqual((phone_tag(rec), rec["decision"]["support"]), ((True, None), "wait_hold_timer"))
        self.assertTrue(rec["vision"]["facing_screen"])           # the rule table's gaze gate still reads every face
        lost = run([inference(face=k < 45) for k in range(60)])  # looking down: the face lost from 4.5 s, head kept
        rec = WindowJudge(bundle()).evaluate(lost, 5.9)
        self.assertEqual((phone_tag(rec), rec["decision"]["support"]), ((True, None), "wait_hold_timer"))
        chain = FrameChain(FakeModels([inference(face=k < 45) for k in range(60)]), PilotParams(hand_vis_min=VIS_TEST),
                           ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * 50 + [[]] * 10), phones=fake_phones)
        no_head = quiet([chain.process(f) for f in frames(60)])  # the head box missing too in the last segment
        self.assertEqual(phone_tag(WindowJudge(bundle()).evaluate(no_head, 5.9)), ("unknown", "gaze_unknown"))
        missed = run([inference(yaw=0.0, face=k != 59) for k in range(60)])   # reading; one face frame missed
        rec = WindowJudge(bundle()).evaluate(missed, 5.9)
        self.assertEqual((phone_tag(rec), rec["decision"]["support"]), ((False, None), None))

        def call(img):                                           # a phone at the main user's head box (a call)
            return Phones(np.array([[0.55, 0.30, 0.66, 0.45]]), np.array([0.6]), (img.shape[1], img.shape[0]),
                          {"infer": 0.0})
        on_call = run([inference(face=k < 45) for k in range(60)], call)
        self.assertEqual(on_call[50]["phone_at"], "head")
        unset = run([inference(face=k < 45) for k in range(60)], call, PilotParams())   # no hand_vis_min
        self.assertEqual([(r["phone_owner"], r["phone_at"]) for r in unset],
                         [(r["phone_owner"], r["phone_at"]) for r in on_call])   # the head path does not need it
        rec = WindowJudge(bundle()).evaluate(on_call, 5.9)       # no face in the last segment (4.9, 5.9]
        self.assertEqual((phone_tag(rec), rec["measurable"]), ((True, None), False))   # placeholder: not measurable
        self.assertEqual((rec["decision"]["support"], rec["decision"]["transition"]), ("wait_hold_timer", "open"))
        self.assertEqual(rec["contract"]["extension"]["measurement"]["basis"], BASIS_PHONE)
        in_view = run([inference(yaw=0.0) for _ in range(60)], call)   # a call with the face in view
        rec = WindowJudge(bundle()).evaluate(in_view, 5.9)
        self.assertEqual((phone_tag(rec), rec["measurable"]), ((True, None), True))    # measurable: every row runs
        self.assertEqual((rec["decision"]["support"], rec["decision"]["transition"]), ("wait_hold_timer", "open"))
        self.assertEqual(rec["contract"]["extension"]["measurement"]["basis"], BASIS)
        judge = WindowJudge(bundle())
        first, second = judge.evaluate(on_call, 4.9), judge.evaluate(on_call, 5.9)   # open with the face, then lost
        self.assertEqual((first["decision"]["transition"], second["decision"]["transition"]), ("open", "keep"))
        self.assertEqual(second["decision"]["session_signal"], {"name": "hold_timer"})   # the hold timer stays held
        gone = [dict(r) for r in on_call]
        for r in gone[20:]:                                     # two of six segments with the phone: < 3
            r.update(dict.fromkeys(PHONE_COLUMNS), phone_owner="no")   # the phone is no longer seen
        rec = WindowJudge(bundle()).evaluate(gone, 5.9)
        self.assertEqual((rec["measurable"], rec["decision"]["transition"]), (False, "none"))   # placeholder again
        self.assertNotIn("phone_use", rec["contract"]["extension"]["measurement"]["basis"])

    def test_a_hidden_hand_at_the_phone_opens_no_wait_with_the_visibility_limit(self):
        """The review's input (PR #98, 2026-11-24, columns.py:911): the fake-detector run above (60 frames, the main
        user looking away, no touch) with the visibility of the four hand points at the phone set to 0.0. Without
        hand_vis_min no hand box is built (the hand path is held: review of 2026-11-25 on bade183, columns.py:966):
        phone_owner 'unknown', phone_use cannot tell, no wait - also with visible hands. With it the hidden hand is no
        ownership evidence: the other hand is checked, phone_use is false and no wait opens."""
        import numpy as np
        from app.inference.phone import Phones
        from app.modules.vision.chain import FrameChain, WindowJudge
        from app.modules.vision.params import PilotParams

        def inference(vis=0.0):
            inf = fake_inference(yaw=40.0)                       # beyond offscreen_yaw_deg 30: looking away
            inf.pose[0, :2] = (0.50, 0.40)                       # nose inside the fake head box
            for k in (15, 17, 19, 21):
                inf.pose[k, :2] = (0.45, 0.80)                   # one hand at the chest, inside the phone box ...
                inf.pose[k, 2] = vis                             # ... not visible (0.0)
            return inf

        def fake_phones(img):
            return Phones(np.array([[0.40, 0.70, 0.48, 0.82]]), np.array([0.6]), (img.shape[1], img.shape[0]),
                          {"infer": 0.0})

        def run(params, vis=0.0):
            chain = FrameChain(FakeModels([inference(vis) for _ in range(60)]), params, FakeHeads(), phones=fake_phones)
            rows = [dict(chain.process(f), tap_count=0, miss_tap_count=0) for f in frames(60)]
            rec = WindowJudge(bundle()).evaluate(rows, 5.9)
            tag = {t["name"]: (t["status"], t["unknown_reason"]) for t in rec["situation"]["tags"]}["phone_use"]
            return (rows[55]["phone_owner"], rows[55]["phone_at"]), tag, (rec["decision"]["transition"],
                                                                          rec["decision"]["support"])
        held = (("unknown", None), ("unknown", "phone_owner_unknown"), ("none", None))
        self.assertEqual(run(PilotParams()), held)
        self.assertEqual(run(PilotParams(), vis=0.9), held)                  # visible hands: still held
        self.assertEqual(run(PilotParams(hand_vis_min=VIS_TEST), vis=0.9),
                         (("yes", "hand"), (True, None), ("open", "wait_hold_timer")))   # with the value: as before
        self.assertEqual(run(PilotParams(hand_vis_min=VIS_TEST)), (("no", None), (False, None), ("none", None)))

    def test_the_aid_input_is_off_by_default_and_fills_its_columns_when_given(self):
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.columns import AID_COLUMNS
        from app.modules.vision.params import PilotParams
        row = FrameChain(FakeModels([fake_inference()]), PilotParams(), FakeHeads()).process(frames(1)[0])
        self.assertFalse(set(AID_COLUMNS) & set(row))                  # no detector: the columns are absent

        def fake_aids(img):
            return Aids(np.array([[0.30, 0.10, 0.70, 0.95]]), np.array([0.7]),
                        np.array([[0.1, 0.7, 0.0, 0.0, 0.0]]), ("pedestrian", "crutch", "cane", "walker", "wheelchair"),
                        (img.shape[1], img.shape[0]), {"infer": 0.0})
        chain = FrameChain(FakeModels([fake_inference()]), PilotParams(), FakeHeads(), aids=fake_aids)
        row = chain.process(frames(1)[0])                               # fake pose shoulders (0.42, 0.7), (0.58, 0.7)
        self.assertEqual(row["aid_owner"], "yes")
        self.assertAlmostEqual(row["aid_any_score"], 0.7)
        self.assertGreaterEqual(row["ms_aids"], 0.0)

    def test_the_head_centre_reading_adds_its_columns_and_the_default_reading_does_not(self):
        """aid_rule head_centre: the chain writes the aid_head columns from the detector's per-class boxes and the main
        user's head box (FakeHeads: centre (0.5, 0.4)) next to the aid columns, which do not change; the default
        reading writes the aid columns only, as before. Without the head detector there is no head box: no value."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.columns import AID_COLUMNS, AID_HEAD_COLUMNS
        from app.modules.vision.params import PilotParams
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
        box = [0.30, 0.10, 0.70, 0.95]
        empty = (np.zeros((0, 4)), np.zeros(0))

        def fake_aids(img):                                          # one box, pedestrian on top, a wheelchair channel
            return Aids(np.array([box]), np.array([0.7]), np.array([[0.7, 0.0, 0.0, 0.0, 0.6]]), classes,
                        (img.shape[1], img.shape[0]), {"infer": 0.0},
                        {"crutch": empty, "cane": empty, "walker": empty,
                         "wheelchair": (np.array([box]), np.array([0.6]))})

        def row(params, heads=None):
            return FrameChain(FakeModels([fake_inference()]), params, heads, aids=fake_aids).process(frames(1)[0])
        default = row(PilotParams(), FakeHeads())
        self.assertFalse(set(AID_HEAD_COLUMNS) & set(default))
        self.assertEqual((default["aid_owner"], default["aid_top_class"]), ("no", "pedestrian"))
        head = row(PilotParams(aid_rule="head_centre"), FakeHeads())
        self.assertEqual({k: head[k] for k in AID_COLUMNS}, {k: default[k] for k in AID_COLUMNS})
        self.assertEqual({k: head[k] for k in AID_HEAD_COLUMNS},
                         {"aid_head_score": 0.6, "aid_head_class": "wheelchair", "aid_head_box": tuple(box)})
        no_heads = row(PilotParams(aid_rule="head_centre"))
        self.assertEqual({k: no_heads[k] for k in AID_HEAD_COLUMNS}, dict.fromkeys(AID_HEAD_COLUMNS))

    def test_a_sustained_lean_stays_face_approach_and_never_becomes_seated_height(self):
        """With a touch log (the reference starts at the first press): 1 s at the normal size, then the face 1.5 times
        larger and lower in the frame for 7 s. Every later window keeps face_approach True, and seated_height never
        turns True from the leaning rows (they are left out: face_near)."""
        from app.modules.vision.chain import FrameChain, WindowJudge
        from app.modules.vision.params import PilotParams
        from app.modules.vision.touch import load_timeline
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        tl = load_timeline(touch_log(folder, MENU_EVENTS[:3], video), video)   # the first press at 0.5 s

        def lean(k):
            inf = fake_inference()
            if k >= 15:                                   # from 1.5 s: eyes 1.5 times apart, the face lower
                inf.face_points[:, 1] = 0.55                # (still inside the head box, so it stays the user's)
                inf.face_points[[33, 133]] = [(0.38, 0.55), (0.44, 0.55)]
                inf.face_points[[362, 263]] = [(0.56, 0.55), (0.62, 0.55)]
            return inf
        p = PilotParams(approach_ratio_min=1.2, seated_face_cy_min=0.5)
        chain = FrameChain(FakeModels([lean(k) for k in range(85)]), p, FakeHeads(), None, tl)
        rows = [chain.process(f) for f in frames(85)]
        judge = WindowJudge(bundle(approach_ratio_min=1.2, seated_face_cy_min=0.5), tl)
        tags = [{t["name"]: t["status"] for t in judge.evaluate(rows, t_end)["situation"]["tags"]}
                for t_end in (3.0, 5.0, 8.0)]
        self.assertEqual([t["face_approach"] for t in tags], [True, True, True])
        self.assertTrue(all(t["seated_height"] is not True for t in tags))

    def test_without_a_touch_log_the_walk_up_does_not_read_as_face_approach(self):
        """No touch log: the reference starts with the main-user track while the person still walks up (eyes 20 to 40
        px). The upper half of the sizes so far is the reference, so standing at 40 px reads near 1, and a lean to 52
        px still reads above it."""
        from app.modules.vision.columns import FaceSizeRef
        ref = FaceSizeRef(near_min=1.2)
        walk = [20.0, 24.0, 28.0, 32.0, 36.0, 40.0] + [40.0] * 6
        got = [ref.update({"face_state": SEEN, "iod_px": v, "primary_track": 1}) for v in walk]
        self.assertLess(got[-1], 1.2)
        self.assertGreater(ref.update({"face_state": SEEN, "iod_px": 52.0, "primary_track": 1}), 1.2)

    def test_a_first_press_during_the_walk_up_does_not_read_the_arrival_as_face_approach(self):
        """Touch log: the session's first press comes while the user is still stepping up (eyes 20 to 40 px over 30
        rows after the press). The reference is the same upper-half median as without a log, so standing at 40 px reads
        1.0 with either anchor; a lean to 52 px reads 1.3, and after the press it stays out of the reference. The plain
        median of the same rows would leave the arrival out as a lean and read standing still as an approach."""
        from app.modules.vision.columns import FaceSizeRef
        walk = [20.0 + 20.0 * k / 29 for k in range(30)] + [40.0] * 30
        lean = [52.0] * 20
        for press in (True, False):
            ref = FaceSizeRef(near_min=1.2)
            got = [ref.update({"face_state": SEEN, "iod_px": v, "primary_track": 1}, press_anchor=press)
                   for v in walk + lean]
            self.assertLess(got[29], 1.2, press)                      # arriving: below the boundary
            self.assertEqual(got[len(walk) - 1], 1.0, press)          # standing at the kiosk
            self.assertAlmostEqual(got[len(walk)], 1.3, msg=press)    # leaning in
            self.assertAlmostEqual(got[-1], 1.3, msg=press)
        kept = FaceSizeRef(near_min=1.2)                  # after the press a long lean stays out of the reference
        got = [kept.update({"face_state": SEEN, "iod_px": v, "primary_track": 1}, press_anchor=True)
               for v in walk + lean * 4]
        self.assertAlmostEqual(got[-1], 1.3)
        faded = FaceSizeRef(near_min=1.2)                 # without a log the same long lean enters it and fades
        got = [faded.update({"face_state": SEEN, "iod_px": v, "primary_track": 1}) for v in walk + lean * 4]
        self.assertLess(got[-1], 1.2)

    def test_a_new_touch_session_restarts_the_session_start_reference_and_nothing_else(self):
        """iod_ratio_start, dyaw_start_deg and dpitch_start_deg compare with the first face frame of the session: a
        new sessionId in the touch log takes that frame again (the run counters keep going). Without a touch log the
        rows are those of a single session."""
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.params import PilotParams
        from app.modules.vision.touch import load_timeline
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        tl = load_timeline(touch_log(folder, MENU_EVENTS, video), video)   # session s2 from 8.1 s

        def grown(k):                                   # the eye corners move apart: the face comes closer
            inf = fake_inference(yaw=float(k % 5))
            inf.face_points[[33, 133]] -= [0.001 * k, 0.0]
            inf.face_points[[362, 263]] += [0.001 * k, 0.0]
            return inf
        sched = [grown(k) for k in range(90)]
        chain = FrameChain(FakeModels(sched), PilotParams(), FakeHeads(), None, tl)
        rows = [chain.process(f) for f in frames(90)]
        self.assertGreater(rows[80]["iod_ratio_start"], 1.0)
        self.assertEqual((rows[81]["iod_ratio_start"], rows[81]["dyaw_start_deg"]), (1.0, 0.0))   # s2's first frame
        self.assertGreater(rows[85]["iod_ratio_start"], 1.0)
        self.assertGreater(rows[81]["face_run_s"], 8.0)            # the face run is not restarted
        self.assertTrue(all(r["main_user_prev_track"] is None for r in rows))   # the new session's track: no change
        self.assertIsNone(rows[81]["iod_ratio_user"])               # the size reference starts again (no press yet)
        plain = FrameChain(FakeModels(sched), PilotParams(), FakeHeads())
        rows = [plain.process(f) for f in frames(90)]
        self.assertGreater(rows[81]["iod_ratio_start"], 1.0)        # no touch log: one session, no restart

    def test_a_covered_face_keeps_the_main_user_track_and_only_a_long_head_loss_starts_a_new_one(self):
        """A cap or a hand covers the face (2026-11-22, scene 2-2): the head box stays, so the main user's track goes
        on - no main_user_changed row and user_changed False. A head box lost for longer than track_max_gap_s
        (1.0 s by default) ends the track; when the next box is in the same place (IoU >= track_iou_min with the last
        one) it is a reacquisition and user_changed says unknown; a box elsewhere is a new user (True)."""
        from app.modules.vision.chain import FrameChain, WindowJudge
        from app.modules.vision.params import PilotParams
        box = [0.38, 0.22, 0.62, 0.58]
        sched = [fake_inference() for _ in range(5)] + [fake_inference(face=False) for _ in range(15)] +                 [fake_inference() for _ in range(5)]
        covered = FrameChain(FakeModels(sched), PilotParams(), ScheduledHeads([[box]] * 25))
        rows = [covered.process(f) for f in frames(25)]
        self.assertEqual({r["primary_track"] for r in rows}, {1})
        self.assertTrue(all(r["main_user_prev_track"] is None for r in rows))
        tags = {t["name"]: t["status"] for t in WindowJudge(bundle()).evaluate(rows, 2.4)["situation"]["tags"]}
        self.assertEqual((tags["user_changed"], tags["none_seen"]), (False, False))
        stood = [fake_inference() for _ in range(21)] + [fake_inference(face=False) for _ in range(15)] +             [fake_inference() for _ in range(5)]                     # the user stands 2 s (the box stops growing)
        lost = FrameChain(FakeModels(stood), PilotParams(), ScheduledHeads([[box]] * 21 + [[]] * 15 + [[box]] * 5))
        rows = [lost.process(f) for f in frames(41)]                 # no head box from 2.1 to 3.5 s
        self.assertEqual((rows[20]["primary_track"], rows[36]["primary_track"]), (1, 2))
        self.assertEqual(rows[36]["main_user_prev_track"], 1)
        self.assertAlmostEqual(rows[36]["main_user_gap_s"], 1.6)
        self.assertIs(rows[36]["main_user_body_kept"], True)          # the body stayed in view
        self.assertIs(rows[36]["main_user_reacquired"], True)         # the same place: the same person found again
        self.assertIs(rows[36]["main_user_prev_settled"], True)       # the user had stood at the kiosk
        out = WindowJudge(bundle()).evaluate(rows, 4.0)["situation"]["tags"]
        self.assertEqual({t["name"]: (t["status"], t["unknown_reason"]) for t in out}["user_changed"],
                         ("unknown", "reacquired_same_place"))
        moved = [0.05, 0.25, 0.25, 0.55]                             # the next box elsewhere: a new customer
        elsewhere = FrameChain(FakeModels(stood), PilotParams(), ScheduledHeads([[box]] * 21 + [[]] * 15 + [[moved]] * 5))
        rows = [elsewhere.process(f) for f in frames(41)]
        self.assertIs(rows[36]["main_user_reacquired"], False)
        tags = {t["name"]: t["status"] for t in WindowJudge(bundle()).evaluate(rows, 4.0)["situation"]["tags"]}
        self.assertEqual(tags["user_changed"], True)
        early = FrameChain(FakeModels(sched), PilotParams(), ScheduledHeads([[box]] * 5 + [[]] * 15 + [[moved]] * 5))
        rows = [early.process(f) for f in frames(25)]                # the first track ends after 0.5 s: an approach
        self.assertIs(rows[20]["main_user_prev_settled"], False)
        tags = {t["name"]: t["status"] for t in WindowJudge(bundle()).evaluate(rows, 2.4)["situation"]["tags"]}
        self.assertEqual(tags["user_changed"], False)

    def test_a_head_box_that_jumps_in_place_is_stitched_in_the_chain(self):
        """A deep bow: after 2 s standing the main user's head box jumps lower in the same place (IoU below
        track_iou_min), so the tracker starts a new track at once and hands the main user over when the old track ends
        (track_max_gap_s later). With the two stitch values the chain marks that row stitched and user_changed is
        False; without them the same frames count a change."""
        from app.modules.vision.chain import FrameChain, WindowJudge
        from app.modules.vision.params import PilotParams
        box, bowed = [0.38, 0.22, 0.62, 0.58], [0.38, 0.45, 0.62, 0.81]     # IoU 0.22: no match for the tracker

        def run(**values):
            chain = FrameChain(FakeModels([fake_inference() for _ in range(41)]), PilotParams(**values),
                               ScheduledHeads([[box]] * 21 + [[bowed]] * 20))
            rows = [chain.process(f) for f in frames(41)]
            tags = WindowJudge(bundle()).evaluate(rows, 4.0)["situation"]["tags"]
            return rows, {t["name"]: (t["status"], t["unknown_reason"]) for t in tags}["user_changed"]
        rows, changed = run(stitch_shift_max=1.0, stitch_size_max=0.3)
        self.assertEqual((rows[30]["primary_track"], rows[31]["primary_track"]), (1, 2))   # track 1 ends after 1.0 s
        self.assertEqual(rows[31]["main_user_prev_track"], 1)
        self.assertAlmostEqual(rows[31]["main_user_new_start_s"], 0.1)    # first seen in the frame after the last box
        self.assertIs(rows[31]["main_user_reacquired"], False)
        self.assertIs(rows[31]["main_user_prev_settled"], True)
        self.assertIs(rows[31]["main_user_stitched"], True)
        self.assertEqual(changed, (False, None))
        rows, changed = run()                                              # no stitch values: a change
        self.assertIsNone(rows[31]["main_user_stitched"])
        self.assertEqual(changed, (True, None))

    def test_a_face_outside_the_main_user_box_is_missing(self):
        """The main user's track is a head box left of the face (chosen while it was the only box); a box around the
        face comes later. The face is then someone else's: its values and mouth_motion are blank, face_in_primary is
        False, and the events layer finds no yaw it could use (yaw_ok False), so the turn cues are missing."""
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.columns import FACE_VALUE_COLUMNS
        from app.modules.vision.events import observe_window
        from app.modules.vision.params import PilotParams
        left, around = [0.02, 0.10, 0.30, 0.45], [0.40, 0.25, 0.60, 0.55]   # the fake face centre is (0.5, 0.4)
        blend = {name: 0.1 for name in PilotParams().mouth_dials}
        chain = FrameChain(FakeModels([fake_inference(yaw=10.0, blend=blend) for _ in range(12)]),
                           PilotParams(mouth_baseline_s=0.3), ScheduledHeads([[left]] * 3 + [[left, around]]),
                           blendshapes=True)
        rows = [chain.process(f) for f in frames(12)]
        r = rows[-1]
        self.assertEqual((r["primary_from"], r["primary_track"], r["face_track"], r["face_in_primary"]),
                         ("track", 1, 2, False))
        self.assertEqual(r["face_state"], SEEN)                       # a face is seen, but not the main user's
        self.assertTrue(all(r[c] is None for c in FACE_VALUE_COLUMNS), [c for c in FACE_VALUE_COLUMNS if r[c] is not None])
        self.assertTrue(all(x["mouth_motion"] is None for x in rows))
        cues = observe_window(rows, (0.0, 1.1), sit_params(), landmarker_num_faces=1)
        self.assertFalse(cues.yaw_ok)
        same = FrameChain(FakeModels([fake_inference(yaw=10.0) for _ in range(3)]), PilotParams(), FakeHeads())
        r = [same.process(f) for f in frames(3)][-1]                  # the face inside the main user's box
        self.assertEqual((r["face_in_primary"], r["face_track"]), (True, 1))
        self.assertAlmostEqual(abs(r["yaw_deg"]), 10.0, places=3)

    def test_another_face_while_the_main_user_box_is_missing_is_not_the_main_users(self):
        """The main user's box (around the face) is missing for 3 frames, well within track_max_gap_s, while a smaller
        box of another person, overlapping it below track_iou_min, holds the face centre; then the main user's box
        returns. While it is missing the face is the other person's: face_in_primary False, face values and
        mouth_motion blank. After the return it is the main user's again (box lost, other face, return)."""
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.columns import FACE_VALUE_COLUMNS
        from app.modules.vision.params import PilotParams
        user, other = [0.38, 0.22, 0.62, 0.58], [0.45, 0.30, 0.55, 0.50]   # IoU 0.02 / 0.0864 = 0.23; face (0.5, 0.4)
        blend = {name: 0.1 for name in PilotParams().mouth_dials}
        heads = ScheduledHeads([[user]] * 3 + [[other]] * 3 + [[user, other]])
        chain = FrameChain(FakeModels([fake_inference(yaw=10.0, blend=blend) for _ in range(9)]),
                           PilotParams(mouth_baseline_s=0.15), heads, blendshapes=True)
        rows = [chain.process(f) for f in frames(9)]
        self.assertEqual(rows[2]["mouth_motion"], 0.0)                   # the main user's mouth before the gap
        for r in rows[3:6]:
            self.assertEqual((r["primary_track"], r["primary_box"], r["face_track"], r["face_in_primary"]),
                             (1, None, 2, False))
            self.assertEqual(r["face_state"], SEEN)
            self.assertTrue(all(r[c] is None for c in FACE_VALUE_COLUMNS),
                            [c for c in FACE_VALUE_COLUMNS if r[c] is not None])
            self.assertIsNone(r["mouth_motion"])                         # the other person's blendshapes not used
        for r in rows[6:]:
            self.assertEqual((r["primary_track"], r["face_track"], r["face_in_primary"]), (1, 1, True))
            self.assertAlmostEqual(abs(r["yaw_deg"]), 10.0, places=3)
        self.assertEqual(rows[8]["mouth_motion"], 0.0)                   # a new face run (from 0.6 s), baseline filled

    def test_a_face_in_no_box_while_the_main_user_box_is_missing_cannot_be_told(self):
        """The main user's box is missing and the only box is far from the face: the face may be the main user's (a
        head detector miss), so face_in_primary stays None and the face values are kept."""
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.params import PilotParams
        user, away = [0.38, 0.22, 0.62, 0.58], [0.02, 0.10, 0.30, 0.45]
        chain = FrameChain(FakeModels([fake_inference(yaw=10.0) for _ in range(5)]), PilotParams(),
                           ScheduledHeads([[user]] * 3 + [[away]]))
        r = [chain.process(f) for f in frames(5)][-1]
        self.assertEqual((r["primary_track"], r["primary_box"], r["face_track"], r["face_in_primary"]),
                         (1, None, None, None))
        self.assertAlmostEqual(abs(r["yaw_deg"]), 10.0, places=3)

    def test_face_value_columns_are_feature_columns(self):
        from app.modules.vision.columns import FACE_VALUE_COLUMNS
        from app.modules.vision.features import COLUMNS
        self.assertLessEqual(set(FACE_VALUE_COLUMNS), set(COLUMNS))
        self.assertNotIn("face_state", FACE_VALUE_COLUMNS)

    def test_a_new_touch_log_session_starts_the_head_tracks_again(self):
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.params import PilotParams
        from app.modules.vision.touch import load_timeline
        folder = tempfile.mkdtemp()
        video = os.path.join(folder, "take.mp4")
        events = [(-1000, "session_start", "menu", None), (-900, "screen_enter", "menu", None),
                  (500, "session_end", "menu", {"reason": "server_session_change"}),
                  (550, "session_start", "menu", {"reason": "server_session_change"}, "s2")]
        tl = load_timeline(touch_log(folder, events, video), video)
        chain = FrameChain(FakeModels([fake_inference() for _ in range(9)]), PilotParams(), FakeHeads(behind=True),
                           timeline=tl)
        rows = [chain.process(f) for f in frames(9)]
        seen = [(r["primary_from"], [b["track"] for b in r["head_boxes"]]) for r in rows[4:8]]
        self.assertEqual(seen, [("track", [1, 2]), ("track", [1, 2]),     # 0.4 s, 0.5 s: session s1
                                ("face", [3, 4]), ("track", [3, 4])])      # 0.6 s: s2 chooses anew
        # s1's main user leaves at 0.3 s and another person's face is seen in their own box until the session ends:
        # blank in s1 (the main user's track is still alive); from 0.6 s that person is s2's main user, chosen anew
        from app.modules.vision.columns import FACE_VALUE_COLUMNS
        user, other = [0.38, 0.22, 0.62, 0.58], [0.45, 0.30, 0.55, 0.50]
        chain = FrameChain(FakeModels([fake_inference(yaw=10.0) for _ in range(9)]), PilotParams(),
                           ScheduledHeads([[user]] * 3 + [[other]]), timeline=tl)
        rows = [chain.process(f) for f in frames(9)]
        for r in rows[3:6]:                                               # 0.3 to 0.5 s: session s1
            self.assertEqual((r["primary_track"], r["face_track"], r["face_in_primary"]), (1, 2, False))
            self.assertTrue(all(r[c] is None for c in FACE_VALUE_COLUMNS))
        self.assertEqual((rows[6]["primary_from"], rows[6]["primary_track"]), ("face", 3))
        for r in rows[6:]:                                                # 0.6 s on: session s2, new main user
            self.assertEqual((r["primary_track"], r["face_track"], r["face_in_primary"]), (3, 3, True))
            self.assertAlmostEqual(abs(r["yaw_deg"]), 10.0, places=3)

    def test_without_boundary_values_the_head_behind_is_unknown(self):
        from app.modules.vision.chain import FrameChain
        from app.modules.vision.params import PilotParams
        chain = FrameChain(FakeModels([fake_inference() for _ in range(3)]), PilotParams(), FakeHeads(behind=True))
        rows = [chain.process(f) for f in frames(3)]
        self.assertIsNone(rows[-1]["people_behind_count"])          # blank: missing, not 0
        self.assertNotIn("companion_box", rows[-1])                 # absent: the companion cannot be told
        self.assertEqual(rows[-1]["head_boxes"][1]["role"], "unknown")
        self.assertAlmostEqual(rows[-1]["head_boxes"][1]["rel_dist_med"], 4.5)   # the cues are still written

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

    def test_rows_csv_read_back_gives_the_same_scene_tags(self):
        """rows.csv written by the replay and read back (companion_eval.row_from_csv: track ids as strings, bools as
        text, boxes as tuples) gives the same scene tags as the rows the replay judged in memory. The head box is lost
        for 1.2 s, so a change row (a reacquisition in the same place) is part of it."""
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.replay import run_replay
        from app.modules.vision.tools.companion_eval import row_from_csv
        folder = tempfile.mkdtemp()
        out = os.path.join(folder, "out")
        b = bundle(approach_ratio_min=1.2, seated_face_cy_min=0.6)
        box = [0.38, 0.22, 0.62, 0.58]
        run_replay(frames(30), out, b, models=FakeModels([fake_inference() for _ in range(30)]),
                   detector=ScheduledHeads([[box]] * 10 + [[]] * 12 + [[box]] * 8), direction=FakeDirection(),
                   session_id="t")
        with open(os.path.join(out, "windows.jsonl"), encoding="utf-8") as f:
            recs = [json.loads(line) for line in f]
        with open(os.path.join(out, "rows.csv"), encoding="utf-8-sig", newline="") as f:
            back = [row_from_csv(r) for r in csv.DictReader(f)]
        self.assertEqual([r["main_user_reacquired"] for r in back if r.get("main_user_prev_track")], ["True"])
        judge = WindowJudge(b)
        for rec in recs:
            again = judge.evaluate(back, rec["t"], segment_s=(rec.get("partial") or {}).get("segment_s"))
            self.assertEqual([(t["name"], t["status"], t["unknown_reason"]) for t in again["situation"]["tags"]],
                             [(t["name"], t["status"], t["unknown_reason"]) for t in rec["situation"]["tags"]], rec["t"])

    def test_rows_csv_read_back_keeps_the_phone_columns_and_events(self):
        """With the phone input, rows.csv read back gives the same phone_use tag and phone events as the windows the
        replay judged in memory: every phone column is written (a missing phone_at would keep the 'yes' states and lose
        every phone event)."""
        import numpy as np
        from app.inference.phone import Phones
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.replay import run_replay
        from app.modules.vision.tools.companion_eval import row_from_csv

        def inference():
            inf = fake_inference(yaw=40.0)
            inf.pose[0, :2] = (0.50, 0.40)                       # nose inside the fake head box
            for k in (15, 17, 19, 21):
                inf.pose[k, :2] = (0.45, 0.80)                   # one hand at the chest
            return inf

        def fake_phones(img):
            return Phones(np.array([[0.40, 0.70, 0.48, 0.82]]), np.array([0.6]), (img.shape[1], img.shape[0]),
                          {"infer": 0.0})
        folder = tempfile.mkdtemp()
        out = os.path.join(folder, "out")
        b = bundle(hand_vis_min=VIS_TEST)                         # the hand path needs the value
        run_replay(frames(30), out, b, models=FakeModels([inference() for _ in range(30)]), detector=FakeHeads(),
                   phones=fake_phones, session_id="t")
        with open(os.path.join(out, "windows.jsonl"), encoding="utf-8") as f:
            recs = [json.loads(line) for line in f]
        with open(os.path.join(out, "rows.csv"), encoding="utf-8-sig", newline="") as f:
            back = [row_from_csv(r) for r in csv.DictReader(f)]
        self.assertEqual({(r["phone_owner"], r["phone_at"]) for r in back}, {("yes", "hand")})

        def phone(rec):
            tag = {t["name"]: t for t in rec["situation"]["tags"]}["phone_use"]
            return tag["status"], tag["unknown_reason"], sorted(e["event_id"] for e in tag["evidence"])
        self.assertTrue(any(phone(rec)[2] for rec in recs))      # the in-memory windows hold phone events
        judge = WindowJudge(b)
        for rec in recs:
            again = judge.evaluate(back, rec["t"], segment_s=(rec.get("partial") or {}).get("segment_s"))
            self.assertEqual(phone(again), phone(rec), rec["t"])

    def test_rows_csv_read_back_keeps_the_head_centre_aid_columns_and_tag(self):
        """The head_centre reading in a replay with a stand-in detector: rows.csv holds the aid_head columns (a value,
        0.0 once the wheelchair box is gone, blank while the head box is lost), read back they give the same aid_use
        as the windows judged in memory, and meta.json records the reading and its cut with their origin."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.replay import run_replay
        from app.modules.vision.tools.companion_eval import row_from_csv
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
        box, empty, calls = [0.28, 0.12, 0.72, 0.97], (np.zeros((0, 4)), np.zeros(0)), []

        def aids(img):
            calls.append(1)
            wheel = (np.array([box]), np.array([0.6])) if len(calls) <= 20 else empty
            return Aids(np.zeros((0, 4)), np.zeros(0), np.zeros((0, 5)), classes, (img.shape[1], img.shape[0]),
                        {"infer": 0.0}, {"crutch": empty, "cane": empty, "walker": empty, "wheelchair": wheel})
        head = [0.38, 0.22, 0.62, 0.58]
        folder = tempfile.mkdtemp()
        out = os.path.join(folder, "out")
        b = bundle(aid_rule="head_centre", aid_head_min=0.5)
        meta = run_replay(frames(40), out, b, models=FakeModels([fake_inference() for _ in range(40)]),
                          detector=ScheduledHeads([[head]] * 12 + [[]] * 4 + [[head]] * 24), aids=aids, session_id="t")
        self.assertEqual({k: (meta["bundle"]["chain"][k]["value"], meta["bundle"]["chain"][k]["origin"])
                          for k in ("aid_rule", "aid_head_min")},
                         {"aid_rule": ("head_centre", "code"), "aid_head_min": (0.5, "code")})
        with open(os.path.join(out, "windows.jsonl"), encoding="utf-8") as f:
            recs = [json.loads(line) for line in f]
        with open(os.path.join(out, "rows.csv"), encoding="utf-8-sig", newline="") as f:
            back = [row_from_csv(r) for r in csv.DictReader(f)]
        self.assertEqual([(back[i]["aid_head_score"], back[i]["aid_head_class"]) for i in (10, 13, 18, 25)],
                         [("0.6", "wheelchair"), (None, None), ("0.6", "wheelchair"), ("0", None)])

        def aid(rec):
            tag = {t["name"]: t for t in rec["situation"]["tags"]}["aid_use"]
            return tag["status"], tag["unknown_reason"], [(e["obs"], e["value"]) for e in tag["evidence"]]
        self.assertEqual({aid(rec)[0] for rec in recs}, {True, False})
        judge = WindowJudge(b)
        for rec in recs:
            again = judge.evaluate(back, rec["t"], segment_s=(rec.get("partial") or {}).get("segment_s"))
            self.assertEqual(aid(again), aid(rec), rec["t"])

    def test_rows_csv_read_back_keeps_the_carry_column_and_tag(self):
        """The head_centre_carry reading in a replay with a stand-in detector: the head box on the first 5 of 30 rows,
        the wheelchair box throughout. rows.csv holds aid_head_from (head, then carried) and the carried values; read
        back they give the same aid_use as the windows judged in memory, which are true (under head_centre the
        same input leaves them unknown)."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.chain import WindowJudge
        from app.modules.vision.replay import run_replay
        from app.modules.vision.tools.companion_eval import row_from_csv
        classes = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
        empty = (np.zeros((0, 4)), np.zeros(0))

        def aids(img):
            return Aids(np.zeros((0, 4)), np.zeros(0), np.zeros((0, 5)), classes, (img.shape[1], img.shape[0]),
                        {"infer": 0.0}, {"crutch": empty, "cane": empty, "walker": empty,
                                         "wheelchair": (np.array([[0.28, 0.12, 0.72, 0.97]]), np.array([0.6]))})

        def replay(rule):
            out = os.path.join(tempfile.mkdtemp(), "out")
            b = bundle(aid_rule=rule, aid_head_min=0.5)
            run_replay(frames(30), out, b, models=FakeModels([fake_inference() for _ in range(30)]),
                       detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * 5 + [[]] * 25), aids=aids,
                       session_id="t")
            with open(os.path.join(out, "windows.jsonl"), encoding="utf-8") as f:
                recs = [json.loads(line) for line in f]
            with open(os.path.join(out, "rows.csv"), encoding="utf-8-sig", newline="") as f:
                back = [row_from_csv(r) for r in csv.DictReader(f)]
            return b, recs, back

        def aid(rec):
            tag = {t["name"]: t for t in rec["situation"]["tags"]}["aid_use"]
            return tag["status"], tag["unknown_reason"], [(e["obs"], e["value"]) for e in tag["evidence"]]
        b, recs, back = replay("head_centre_carry")
        self.assertEqual([(back[i]["aid_head_score"], back[i]["aid_head_from"]) for i in (2, 5, 29)],
                         [("0.6", "head"), ("0.6", "carried"), ("0.6", "carried")])
        self.assertEqual({aid(rec)[0] for rec in recs}, {True})
        judge = WindowJudge(b)
        for rec in recs:
            again = judge.evaluate(back, rec["t"], segment_s=(rec.get("partial") or {}).get("segment_s"))
            self.assertEqual(aid(again), aid(rec), rec["t"])
        _, old, old_back = replay("head_centre")
        self.assertEqual({aid(rec)[0] for rec in old}, {"unknown"})
        self.assertNotIn("aid_head_from", old_back[0])

    def test_load_aids_is_off_without_a_file_and_names_a_missing_one(self):
        from app.modules.vision.params import PilotParams
        from app.modules.vision.replay import load_aids
        self.assertEqual(load_aids(None, PilotParams(), 1, print), (None, {}))
        with self.assertRaises(FileNotFoundError):
            load_aids(os.path.join(tempfile.mkdtemp(), "missing.onnx"), PilotParams(), 1, print)

    def test_load_aids_reads_the_per_class_boxes_only_with_the_head_centre_reading(self):
        """A stand-in for AidDetector (no model file): per_class follows aid_rule, and the head_centre start line says
        whether aid_use has a cut."""
        from unittest import mock
        from app.modules.vision.params import PilotParams
        from app.modules.vision.replay import load_aids
        path = os.path.join(tempfile.mkdtemp(), "stand_in.onnx")
        with open(path, "wb") as f:
            f.write(b"stand-in")
        made = []

        class StandIn:
            def __init__(self, *args, per_class=False, **kwargs):
                made.append(per_class)
                self.classes, self.meta = ("pedestrian", "crutch", "cane", "walker", "wheelchair"), {}
        lines = []
        with mock.patch("app.inference.aid.AidDetector", StandIn):
            for p in (PilotParams(), PilotParams(aid_rule="head_centre"),
                      PilotParams(aid_rule="head_centre", aid_head_min=0.5)):
                detector, info = load_aids(path, p, 1, lines.append)
                self.assertIsInstance(detector, StandIn)
                self.assertEqual(list(info), ["stand_in.onnx"])
        self.assertEqual(made, [False, True, True])
        self.assertEqual(len(lines), 5)                                  # one line, then two lines twice
        self.assertIn("no_value_for_model", lines[2])
        self.assertIn("aid_head_min = 0.5", lines[4])

    def test_load_aids_reads_the_per_class_boxes_with_the_carry_reading_and_names_its_rule(self):
        """head_centre_carry reads the per-class boxes as head_centre does, and its start lines name the reading, the
        cut and the head tracker's two values it follows the box with; the runners take it as an --aid-rule choice."""
        from unittest import mock
        from app.modules.vision.params import PilotParams
        from app.modules.vision.replay import add_aid_options, aid_values, load_aids
        import argparse
        path = os.path.join(tempfile.mkdtemp(), "stand_in.onnx")
        with open(path, "wb") as f:
            f.write(b"stand-in")
        made, lines = [], []

        class StandIn:
            def __init__(self, *args, per_class=False, **kwargs):
                made.append(per_class)
                self.classes, self.meta = ("pedestrian", "crutch", "cane", "walker", "wheelchair"), {}
        p = PilotParams(aid_rule="head_centre_carry", aid_head_min=0.5)
        with mock.patch("app.inference.aid.AidDetector", StandIn):
            load_aids(path, p, 1, lines.append)
        self.assertEqual(made, [True])
        self.assertEqual(len(lines), 3)
        self.assertIn("head_centre_carry", lines[1])
        self.assertIn("aid_head_min = 0.5", lines[1])
        self.assertIn(f"track_iou_min {p.track_iou_min:g}", lines[2])
        self.assertIn(f"{p.track_max_gap_s:g}초", lines[2])
        ap = argparse.ArgumentParser()
        add_aid_options(ap)
        self.assertEqual(aid_values(ap.parse_args(["--aid-rule", "head_centre_carry"])),
                         {"aid_rule": "head_centre_carry"})

    def test_looking_around_tag_and_the_4_2_highlight_end_to_end(self):
        sched = [fake_inference(y) for y in yaw_schedule()]
        meta, recs, out = self.run_replay(sched)
        self.assertEqual(meta["frames"], len(sched))
        self.assertEqual(len(recs), meta["windows"])
        self.assertNotIn("partial", recs[0])                       # full windows at 1 ... 5 s
        self.assertAlmostEqual(recs[-1]["partial"]["segment_s"], 0.9)   # the last 0.9 s (frames to 5.9 s)
        self.assertAlmostEqual(meta["last_window_partial_s"], 0.9)
        self.assertEqual(meta["counts"]["frames"], {"with_face": 60, "with_heads": 60, "with_direction": 60})
        self.assertEqual(meta["counts"]["session_resets"], 0)      # one touch-log session
        self.assertTrue(all(r["session_reset"] is False for r in recs))
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
        from app.modules.vision.contract_view import MODEL_VERSION
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
            self.assertEqual(set(c), {"support", "extension"})
            self.assertEqual(set(c["support"]), {"preset", "requires_confirmation", "decided_by"})
            self.assertIn(c["support"]["preset"], presets)
            self.assertIn(c["support"]["decided_by"], decided)
            self.assertIsInstance(c["support"]["requires_confirmation"], bool)
            self.assertIs(c["extension"]["measurement"]["measurable"], r["measurable"])
            self.assertEqual(c["extension"]["measurement"]["basis"],
                             "A tap or back in the segment, or a face seen in the segment (team placeholder).")
            self.assertEqual(c["extension"]["model_version"], MODEL_VERSION)
            self.assertLessEqual({"steps_left", "target_id", "message_id", "session_signal"},   # JP 2-5 execution
                                 set(c["extension"]["decision_meta"]))

    def test_measurable_follows_the_team_placeholder(self):
        from app.modules.vision.contract_view import BASIS
        sched = [fake_inference(face=False, body=True) for _ in range(30)]
        _, recs, _ = self.run_replay(sched)
        self.assertTrue(all(r["measurable"] is False for r in recs))      # no tap, no back, no face
        self.assertTrue(all(r["contract"]["extension"]["measurement"]["measurable"] is False for r in recs))
        phone = {t["status"] for r in recs for t in r["situation"]["tags"] if t["name"] == "phone_use"}
        self.assertEqual(phone, {"unknown"})                              # no phone detector
        self.assertTrue(all(r["contract"]["extension"]["measurement"]["basis"] == BASIS for r in recs))   # not phone
        self.assertTrue(all("analyze_response" not in r["contract"] for r in recs))
        self.assertTrue(all(r["decision"]["transition"] == "none" for r in recs))


@unittest.skipUnless(HAS_PYDANTIC, "pydantic not installed")
class ContractViewTests(unittest.TestCase):
    def test_backend_analyze_response_requires_state_scores(self):
        # Load the backend file without importing its app package over ai-engine's.
        repo_root = os.path.dirname(AI_ENGINE_DIR)
        path = os.path.join(repo_root, "backend", "app", "infrastructure", "external", "ai_schemas.py")
        if not os.path.isfile(path):
            self.skipTest("backend ai_schemas.py not available")
        try:
            from pydantic import ValidationError, model_validator
        except ImportError as exc:
            self.skipTest(f"backend schemas require pydantic v2: {exc}")
        spec = importlib.util.spec_from_file_location("vision_test_backend_ai_schemas", path)
        if spec is None or spec.loader is None:
            self.skipTest("backend schemas cannot be loaded by file path")
        schemas = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(schemas)
        except ImportError as exc:
            self.skipTest(f"backend schema imports unavailable in this environment: {exc}")
        from app.modules.vision.contract_view import MODEL_VERSION
        # A sensor-measurable window has no state scores in this chain.
        payload = {"session_id": "t1", "measurable": True, "states": None, "model_version": MODEL_VERSION}
        with self.assertRaisesRegex(ValidationError, "measurable=true requires nonempty states"):
            schemas.AnalyzeResponse.model_validate(payload)
        # This validates as an envelope, but does not represent observed sensor data.
        response = schemas.AnalyzeResponse.model_validate({**payload, "measurable": False})
        self.assertFalse(response.measurable)
        self.assertIsNone(response.states)


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
        self.assertAlmostEqual(meta["last_window_partial_s"], 0.9)   # frames to 5.9 s: one shorter window at the end
        self.assertEqual(meta["counts"]["frames"]["with_heads"], meta["frames"])
        self.assertTrue(all(line.startswith("[") and "상황" in line for line in lines))
        self.assertIn("column:tap_count", " ".join(lines))          # no touch log in live use
        self.assertFalse(meta["window_shown"])
        with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
            self.assertEqual(sum(1 for _ in f), meta["windows"])

    def test_the_aid_reading_options_override_the_bundle_and_say_so(self):
        """--aid-rule / --aid-head-min next to --aid-model (both runners): unset, the bundle as it is (the owner_box
        reading, no cut); given, they override it with origin 'option'. Without --aid-model, or with a value the chain
        refuses, the parser stops before any file is read."""
        from contextlib import redirect_stderr
        from app.modules.vision import replay
        from app.modules.vision.live import parse_args
        from app.modules.vision.params import load_bundle, with_options
        base = ["--camera", "0", "--no-window", "--seconds", "1"]
        plain = load_bundle(None)
        self.assertEqual(replay.aid_values(parse_args(base + ["--aid-model", "aid.onnx"])), {})
        self.assertIs(with_options(plain, replay.aid_values(parse_args(base))), plain)
        a = parse_args(base + ["--aid-model", "aid.onnx", "--aid-rule", "head_centre", "--aid-head-min", "0.4"])
        self.assertEqual(replay.aid_values(a), {"aid_rule": "head_centre", "aid_head_min": 0.4})
        chain = with_options(plain, replay.aid_values(a)).to_dict()["chain"]
        self.assertEqual({k: (chain[k]["value"], chain[k]["origin"], chain[k]["source"])
                          for k in ("aid_rule", "aid_head_min")},
                         {"aid_rule": ("head_centre", "option", "실행 옵션 --aid-rule"),
                          "aid_head_min": (0.4, "option", "실행 옵션 --aid-head-min")})
        for extra in (["--aid-rule", "head_centre"], ["--aid-head-min", "0.4"],
                      ["--aid-model", "aid.onnx", "--aid-rule", "largest"],
                      ["--aid-model", "aid.onnx", "--aid-head-min", "1.5"],
                      ["--aid-model", "aid.onnx", "--aid-head-min", "0"],
                      ["--aid-model", "aid.onnx", "--aid-head-min", "nan"]):
            with self.assertRaises(SystemExit, msg=extra), redirect_stderr(io.StringIO()):
                parse_args(base + extra)
        out = os.path.join(tempfile.mkdtemp(), "out")
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            replay.main(["--video", os.path.join(out, "missing.mp4"), "--out", out, "--aid-rule", "head_centre"])
        self.assertFalse(os.path.exists(out))                           # stopped before anything was written
        lines = []                                                      # a cut without the reading is named at start
        from unittest import mock

        class StandIn:
            def __init__(self, *args, **kwargs):
                self.classes, self.meta = ("pedestrian", "crutch", "cane", "walker", "wheelchair"), {}
        path = os.path.join(tempfile.mkdtemp(), "stand_in.onnx")
        with open(path, "wb") as f:
            f.write(b"stand-in")
        with mock.patch("app.inference.aid.AidDetector", StandIn):
            replay.load_aids(path, with_options(plain, {"aid_head_min": 0.4}).chain, 1, lines.append)
        self.assertIn("head_centre 읽기에서만", lines[-1])

    def test_both_runners_summarise_every_timing_column(self):
        """meta.json timing_ms of the replay and the live runner carries ms_total and every TIMING_COLUMNS entry
        (ms_aids and ms_phones included, from fake detectors), and its note names each of them."""
        import numpy as np
        from app.inference.aid import Aids
        from app.inference.phone import Phones
        from app.modules.vision.live import run_live
        from app.modules.vision.replay import TIMING_COLUMNS, run_replay

        def aids(img):
            return Aids(np.array([[0.30, 0.10, 0.70, 0.95]]), np.array([0.7]), np.array([[0.1, 0.7, 0.0, 0.0, 0.0]]),
                        ("pedestrian", "crutch", "cane", "walker", "wheelchair"), (img.shape[1], img.shape[0]),
                        {"pre": 1.0, "infer": 2.0, "post": 0.5})

        def phones(img):
            return Phones(np.array([[0.40, 0.70, 0.48, 0.82]]), np.array([0.6]), (img.shape[1], img.shape[0]),
                          {"pre": 0.5, "infer": 1.5, "post": 0.25})
        sched = [fake_inference() for _ in range(20)]
        common = dict(models=FakeModels(sched), detector=FakeHeads(), direction=FakeDirection(), blendshapes=False,
                      aids=aids, phones=phones)
        replay = run_replay(frames(20), os.path.join(tempfile.mkdtemp(), "out"), bundle(), **common)["timing_ms"]
        live = run_live(frames(20), bundle(), show_window=False, out_dir=tempfile.mkdtemp(), print_fn=lambda line: None,
                        **common)["timing_ms"]
        for timing in (replay, live):
            for key in ("ms_total",) + TIMING_COLUMNS:
                self.assertIsNotNone(timing.get(key), key)
                self.assertIn(key, timing["note"])
            self.assertEqual((timing["ms_aids"]["p50"], timing["ms_phones"]["p50"]), (3.5, 2.25))


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
        self.assertEqual([r["t"] for r in recs], [1.0, 2.0, 2.9])   # two full windows and the last 0.9 s
        self.assertNotIn("partial", recs[1])
        self.assertAlmostEqual(recs[-1]["partial"]["segment_s"], 0.9)
        self.assertEqual(recs[-1]["segment_s"], [2.0, 2.9])
        self.assertEqual(recs[0]["touch"]["tap_count"], 4)
        # drawn shapes give no head box, so the H1 -> P1 path is not exercised here (test_head_image_runs_h1_and_p1)
        self.assertEqual(meta["counts"]["frames"]["with_heads"], 0)
        for r in recs:
            self.assertEqual(r["situation"]["name"], "unknown")
            self.assertTrue(r["situation"]["unknown_reason"])
        self.assertTrue(set(meta["models"]) >= {"h1_head_yolox_nano_416.onnx", "p1_head_direction_resnet18_56.onnx"})
        self.assertFalse(meta["settings"]["blendshapes"])         # off unless --blendshapes (decision list §16)
        self.assertIn("blendshapes off", meta["settings"]["face_landmarker"])


@unittest.skipUnless(HAS_CV2, SKIP)
class AidConfirmTests(unittest.TestCase):
    """The wheelchair confirm step (aid_confirm.py, app/inference/aid_confirm.py) with stand-in readers: the reader's
    crop, the mean of several files, and in a replay a wheelchair window kept or withdrawn by the reader."""

    CLASSES = ("pedestrian", "crutch", "cane", "walker", "wheelchair")
    PERSON = [0.28, 0.12, 0.72, 0.97]

    class Session:
        """A stand-in ONNX session: input 'input' (1, 3, 8, 8) and fixed logits."""

        def __init__(self, logits):
            self.logits = logits

        def get_inputs(self):
            return [SimpleNamespace(name="input", shape=[1, 3, 8, 8])]

        def run(self, _names, feed):
            import numpy as np
            assert feed["input"].shape == (1, 3, 8, 8) and feed["input"].dtype == np.float32
            return [np.array([self.logits], np.float32)]

    class Reader:
        """A stand-in reader: P(wheelchair) = p for every crop; counts its reads."""

        def __init__(self, p):
            import numpy as np
            self.p = np.array([1.0 - p, 0.0, 0.0, 0.0, p])
            self.ms = []

        def crop(self, bgr, box_px):
            import numpy as np
            return np.zeros((8, 8, 3), np.uint8)

        def probs(self, image):
            self.ms.append(0.0)
            return self.p

    def aids(self, img):
        import numpy as np
        from app.inference.aid import Aids
        empty = (np.zeros((0, 4)), np.zeros(0))
        return Aids(np.array([self.PERSON]), np.array([0.6]), np.array([[0.1, 0, 0, 0, 0.6]]), self.CLASSES,
                    (img.shape[1], img.shape[0]), {"infer": 0.0},
                    {"crutch": empty, "cane": empty, "walker": empty,
                     "wheelchair": (np.array([self.PERSON]), np.array([0.6]))})

    def replay(self, confirm=None):
        from app.modules.vision.replay import run_replay
        out = os.path.join(tempfile.mkdtemp(), "out")
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        meta = run_replay(frames(30), out, b, models=FakeModels([fake_inference() for _ in range(30)]),
                          detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * 5 + [[]] * 25), aids=self.aids,
                          session_id="t", **({} if confirm is None else {"aid_confirm": confirm}))
        with open(os.path.join(out, "windows.jsonl"), encoding="utf-8") as f:
            recs = [json.loads(line) for line in f]
        return b, recs, meta

    @staticmethod
    def aid(rec):
        tag = {t["name"]: t for t in rec["situation"]["tags"]}["aid_use"]
        return tag["status"], tag["unknown_reason"]

    class MetaSession(Session):
        """A stand-in session with export metadata; keeps the last input it was given."""

        def __init__(self, logits, meta):
            super().__init__(logits)
            self.meta, self.seen = meta, None

        def get_modelmeta(self):
            return SimpleNamespace(custom_metadata_map=self.meta)

        def run(self, names, feed):
            self.seen = feed["input"]
            return super().run(names, feed)

    def test_reader_takes_mean_and_std_from_the_file_metadata_and_falls_back_to_imagenet(self):
        """A file whose metadata names mean / std (as a PE-Core export would: 0.5, 0.5) gets (x / 255 - 0.5) / 0.5; a
        file without metadata gets the measured ResNet-18 reader's ImageNet values; wrong classes are refused."""
        import numpy as np
        from app.inference.aid_confirm import CLASSES, MEAN, STD, AidConfirmReader
        img = np.full((8, 8, 3), 255, np.uint8)
        img[:, :, 1] = 0
        pe = self.MetaSession([0.0] * 5, {"mean": "[0.5, 0.5, 0.5]", "std": "[0.5, 0.5, 0.5]",
                                          "classes": json.dumps(list(CLASSES)), "output": "logits"})
        plain = self.MetaSession([0.0] * 5, {})
        AidConfirmReader([], sessions=[pe, plain]).probs(img)
        np.testing.assert_allclose(pe.seen[0, :, 0, 0], [1.0, -1.0, 1.0], atol=1e-6)
        np.testing.assert_allclose(plain.seen[0, :, 0, 0], [(1.0 - MEAN[0]) / STD[0], (0.0 - MEAN[1]) / STD[1],
                                                            (1.0 - MEAN[2]) / STD[2]], atol=1e-6)
        with self.assertRaises(ValueError):
            AidConfirmReader([], sessions=[self.MetaSession([0.0] * 5, {"classes": '["a", "b", "c", "d", "e"]'})])
        with self.assertRaises(ValueError):
            AidConfirmReader([], sessions=[self.MetaSession([0.0] * 5, {"mean": "[0.5, 0.5, 0.5]"})])

    def test_live_reads_checked_windows_on_a_worker_in_window_order_with_the_same_answers(self):
        """run_live with the step: the windows come in time order and are as many as without it; a reader that reads
        0.9 leaves every situation and decision as without the step, one that reads 0.1 makes aid_use false. The
        reads (each 20 ms here) run on the release worker, and meta gives the release delays."""
        import time as _time
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.live import run_live
        outer = self

        class Slow(self.Reader):
            def probs(self, image):
                _time.sleep(0.02)
                return super().probs(image)

        def live(confirm):
            folder = tempfile.mkdtemp()
            b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
            meta = run_live(frames(30), b, models=FakeModels([fake_inference() for _ in range(30)]),
                            detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * 5 + [[]] * 25), aids=outer.aids,
                            show_window=False, out_dir=folder, print_fn=lambda line: None, aid_confirm=confirm)
            with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
                return b, [json.loads(line) for line in f], meta
        b, off, _ = live(None)
        keep = history_s(b) + b.chain.segment_s
        _, kept, meta = live(AidConfirm(Slow(0.9), 0.5, keep))
        _, dropped, meta_low = live(AidConfirm(Slow(0.1), 0.5, keep))
        for recs in (kept, dropped):
            self.assertEqual([r["t"] for r in recs], [r["t"] for r in off])
        self.assertEqual([(r["situation"], r["decision"]) for r in kept], [(r["situation"], r["decision"]) for r in off])
        self.assertEqual({self.aid(r) for r in off}, {(True, None)})
        self.assertEqual({self.aid(r) for r in dropped}, {(False, None)})
        self.assertEqual(meta["aid_confirm"]["reads"], 30)
        self.assertEqual(meta_low["aid_confirm"]["release_delay_s_checked"]["n"], len(dropped))
        self.assertGreater(meta_low["aid_confirm"]["release_delay_s_checked"]["max"], 0.0)

    def test_hold_keeps_later_wheelchair_windows_without_reading_after_one_agreement(self):
        """With the hold the reader reads only the first wheelchair window's rows: the later windows are kept as held
        (no read), and the answers equal the step without the hold when the reader agrees; without an agreement the
        hold changes nothing."""
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        b, off, _ = self.replay()
        keep = history_s(b) + b.chain.segment_s
        _, plain, meta_plain = self.replay(AidConfirm(self.Reader(0.9), 0.5, keep))
        reader = self.Reader(0.9)
        _, held, meta = self.replay(AidConfirm(reader, 0.5, keep, hold=True))
        self.assertEqual([self.aid(r) for r in held], [self.aid(r) for r in plain])
        self.assertEqual([r["aid_confirm"]["held"] for r in held], [False] + [True] * (len(held) - 1))
        first = held[0]["aid_confirm"]["reads"]
        self.assertEqual(len(reader.ms), first)                     # no reader call after the agreement
        self.assertLess(meta["aid_confirm"]["reads"], meta_plain["aid_confirm"]["reads"])
        self.assertEqual(meta["aid_confirm"]["windows_held"], len(held) - 1)
        _, low, _ = self.replay(AidConfirm(self.Reader(0.1), 0.5, keep, hold=True))
        self.assertEqual({self.aid(r) for r in low}, {(False, None)})
        self.assertFalse(any(r["aid_confirm"]["held"] for r in low))

    def test_hold_ends_at_a_new_main_user_or_a_new_session(self):
        """A held step keeps a wheelchair window without reading; a window whose user_changed tag brings a
        main_user_changed event not seen before, or a new touch session, needs a new agreement (here no rows: not
        confirmed). The same change event in the next window does not end the hold again."""
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.params import PilotParams

        def out(change_ids=()):
            return {"tags": [{"name": "user_changed", "status": True if change_ids else False,
                              "evidence": [{"event_id": i, "obs": "track", "value": 1, "t": 1.0} for i in change_ids],
                              "unknown_reason": None},
                             {"name": "aid_use", "status": True, "unknown_reason": None,
                              "evidence": [{"event_id": "aid_head@1", "obs": "aid_class", "value": "wheelchair",
                                            "t": 1.0}]}]}
        sp, cp = sit_params(), PilotParams()
        step = AidConfirm(self.Reader(0.9), 0.5, 10.0, hold=True)
        step.held = True
        self.assertTrue(step.check(out(), [], 3.0, sp, cp)["held"])
        r = step.check(out(["main_user_changed@7"]), [], 4.0, sp, cp)
        self.assertEqual((r["held"], r["confirmed"]), (False, False))
        step.held = True
        self.assertTrue(step.check(out(["main_user_changed@7"]), [], 5.0, sp, cp)["held"])   # seen before
        r = step.check(out(), [], 6.0, sp, cp, session_reset=True)
        self.assertEqual((r["held"], r["confirmed"]), (False, False))
        self.assertEqual(step.reader.ms, [])

    def fading_aids(self, wheelchair_frames):
        """A stand-in detector whose wheelchair box holds the head centre on the first wheelchair_frames calls only
        (then only the person box): the engine's own answer turns from wheelchair to no aid."""
        import numpy as np
        from app.inference.aid import Aids
        empty = (np.zeros((0, 4)), np.zeros(0))
        calls = []

        def aids(img):
            calls.append(1)
            wc = (np.array([self.PERSON]), np.array([0.6])) if len(calls) <= wheelchair_frames else empty
            return Aids(np.array([self.PERSON]), np.array([0.6]), np.array([[0.1, 0, 0, 0, 0.6]]), self.CLASSES,
                        (img.shape[1], img.shape[0]), {"infer": 0.0},
                        {"crutch": empty, "cane": empty, "walker": empty, "wheelchair": wc})
        return aids

    def replay_fading(self, confirm, n=60, wheelchair_frames=30):
        from app.modules.vision.replay import run_replay
        out = os.path.join(tempfile.mkdtemp(), "out")
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        meta = run_replay(frames(n), out, b, models=FakeModels([fake_inference() for _ in range(n)]),
                          detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * n),
                          aids=self.fading_aids(wheelchair_frames), session_id="t",
                          **({} if confirm is None else {"aid_confirm": confirm}))
        with open(os.path.join(out, "windows.jsonl"), encoding="utf-8") as f:
            return b, [json.loads(line) for line in f], meta

    def test_user_hold_answers_every_later_window_and_keeps_the_engine_reading(self):
        """The engine answers wheelchair while the box holds, then no aid. Without the user hold those later windows
        stay false; with it they answer true after the first agreement, without a reader call, and the record keeps the
        engine's own status and class (evidence unchanged) beside hold_user true. Without an agreement nothing is
        added."""
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        b, off, _ = self.replay_fading(None)
        keep = history_s(b) + b.chain.segment_s
        self.assertIn((False, None), {self.aid(r) for r in off})
        reader = self.Reader(0.9)
        _, user, meta = self.replay_fading(AidConfirm(reader, 0.5, keep, hold_user=True))
        reads_at_agreement = user[0]["aid_confirm"]["reads"]
        self.assertEqual(len(reader.ms), reads_at_agreement)              # no reader call after the agreement
        self.assertEqual({self.aid(r)[0] for r in user}, {True})
        for o, u in zip(off, user):
            tag_o = {t["name"]: t for t in o["situation"]["tags"]}["aid_use"]
            tag_u = {t["name"]: t for t in u["situation"]["tags"]}["aid_use"]
            self.assertEqual(tag_u["evidence"], tag_o["evidence"])     # the engine's own evidence
            if u["aid_confirm"].get("held"):
                self.assertTrue(u["aid_confirm"]["hold_user"])
                self.assertEqual(u["aid_confirm"]["engine_status"], tag_o["status"])
        self.assertGreater(meta["aid_confirm"]["windows_user_held"], 0)
        _, plain, _ = self.replay_fading(AidConfirm(self.Reader(0.9), 0.5, keep, hold=True))
        self.assertEqual([self.aid(r) for r in plain], [self.aid(r) for r in off])
        _, none, _ = self.replay_fading(AidConfirm(self.Reader(0.1), 0.5, keep, hold_user=True))
        self.assertNotIn(True, {self.aid(r)[0] for r in none})              # every wheelchair window withdrawn
        self.assertFalse(any((r.get("aid_confirm") or {}).get("held") for r in none))

    def test_user_hold_ends_at_a_new_main_user_or_a_new_session(self):
        """A user-held step answers a no-aid window true without reading; a new main_user_changed event or a new
        touch session ends it (that window keeps the engine's own answer)."""
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.params import PilotParams

        def out(change_ids=()):
            return {"tags": [{"name": "user_changed", "status": True if change_ids else False,
                              "evidence": [{"event_id": i, "obs": "track", "value": 1, "t": 1.0} for i in change_ids],
                              "unknown_reason": None},
                             {"name": "aid_use", "status": False, "unknown_reason": None,
                              "evidence": [{"event_id": "aid_head@1", "obs": "aid_class", "value": None, "t": 1.0}]}]}
        sp, cp = sit_params(), PilotParams()
        step = AidConfirm(self.Reader(0.9), 0.5, 10.0, hold_user=True)
        step.held = True
        o = out()
        r = step.check(o, [], 3.0, sp, cp)
        self.assertEqual((r["hold_user"], r["engine_status"], o["tags"][1]["status"]), (True, False, True))
        o = out(["main_user_changed@7"])
        self.assertEqual(step.check(o, [], 4.0, sp, cp), {"confirmed": None, "held": False, "hold_end": "user_changed"})
        self.assertIs(o["tags"][1]["status"], False)
        step.held = True
        o = out()
        self.assertEqual(step.check(o, [], 5.0, sp, cp, session_reset=True)["hold_end"], "session")
        self.assertIs(o["tags"][1]["status"], False)
        self.assertEqual(step.reader.ms, [])

    def live_sessions(self, confirm, n=80, heads=None, at=None, aids=None):
        """run_live on the fake camera with the touch entry; at = touch windows by frame (default: 1 s windows of
        session s1 up to 4 s, then of s2); heads = the head boxes per frame (default: one head throughout); aids =
        the stand-in detector (default self.aids)."""
        from test_vision_links import entry, reporting, timed_frames, window_body
        from app.modules.vision.live import run_live
        if at is None:
            at = {10 * k: [window_body(k - 1.0, float(k), session_id="s1" if k <= 4 else "s2")]
                  for k in range(1, n // 10)}
        folder = tempfile.mkdtemp()
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        svc = entry(b=b)
        meta = run_live(reporting(timed_frames(n), svc, at), b, models=FakeModels([fake_inference() for _ in range(n)]),
                        detector=ScheduledHeads(heads or [[[0.38, 0.22, 0.62, 0.58]]] * n), aids=aids or self.aids,
                        show_window=False, out_dir=folder, print_fn=lambda line: None, entry=svc, aid_confirm=confirm)
        with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
            return b, [json.loads(line) for line in f], meta

    def test_live_hold_ends_at_a_new_touch_session(self):
        """Through run_live with two session ids (the judge there has no touch log, so session_reset stays false):
        after the reader agreed in session s1, the first window of s2 is not held, and no window of s2 is held before
        a new agreement in s2; the hold ended there with the signal 'session'. The same for the engine-wheelchair hold
        and the user hold. s1 lasts 9 s and s2 10 s: a hold starts only on a window whose rows all lie at or after the
        chain's reset, so in s2 (reset at 10 s) the agreement that starts it is a read window whose span
        starts at or after 10 s, and every s2 window after it is held (assert_hold_restarts_after_reset)."""
        from test_vision_links import window_body
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        at = {10 * k: [window_body(k - 1.0, float(k), session_id="s1" if k <= 9 else "s2")] for k in range(1, 20)}
        for flags in ({"hold": True}, {"hold_user": True}):
            step = AidConfirm(self.Reader(0.9), 0.5, keep, **flags)
            _, recs, meta = self.live_sessions(step, n=200, at=at)
            sessions = [r["evaluated"]["session_id"] for r in recs]
            self.assertEqual(set(sessions) - {None}, {"s1", "s2"}, flags)
            s1 = [r for r in recs if r["evaluated"]["session_id"] == "s1"]
            s2 = [r for r in recs if r["evaluated"]["session_id"] == "s2"]
            self.assertTrue(any((r["aid_confirm"] or {}).get("held") for r in s1), flags)    # held in s1
            first = s2[0]["aid_confirm"]
            self.assertEqual((first["held"], first["hold_end"]), (False, "session"), flags)
            self.assertEqual(step.reset[1], "s2", flags)
            self.assert_hold_restarts_after_reset(s2, step.reset[0], b.situation.window_s, flags)
            self.assertEqual(meta["aid_confirm"]["hold_ends"], {"session": 1}, flags)

    def assert_hold_restarts_after_reset(self, windows, reset_t, window_s, label):
        """In one session's windows (time order): some window is held; the first held one follows a read window that
        agreed (confirmed, not held) and whose whole span lies at or after the chain's reset of that session; no
        window before that agreement is held, and every window after it is."""
        held = [i for i, r in enumerate(windows) if (r["aid_confirm"] or {}).get("held")]
        self.assertTrue(held, label)
        i = held[0]
        self.assertGreater(i, 0, label)
        agree = windows[i - 1]
        self.assertEqual((agree["aid_confirm"]["confirmed"], agree["aid_confirm"]["held"]), (True, False), label)
        self.assertGreaterEqual(agree["t"] - window_s, reset_t - 1e-6, (label, agree["t"], reset_t))
        self.assertEqual(held, list(range(i, len(windows))), label)

    def test_both_holds_end_at_a_window_with_no_main_user_box_or_no_frames(self):
        """A held step (user hold, then engine-wheelchair hold): a window whose aid_use is unknown with the engine's
        reason no_main_user_box or no_frames keeps that unknown and ends the hold (hold_end = that reason), so the next
        no-aid window keeps the engine's false and the next wheelchair window needs a new agreement. Another unknown
        reason (too_few_rows) does not end it."""
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.params import PilotParams

        def out(status, reason=None, cls=None):
            return {"tags": [{"name": "user_changed", "status": False, "evidence": [], "unknown_reason": None},
                             {"name": "aid_use", "status": status, "unknown_reason": reason,
                              "evidence": [{"event_id": "aid_head@1", "obs": "aid_class", "value": cls, "t": 1.0}]}]}
        sp, cp = sit_params(), PilotParams()
        step = AidConfirm(self.Reader(0.9), 0.5, 10.0, hold_user=True)
        step.held = True
        o = out("unknown", "no_main_user_box")
        r = step.check(o, [], 3.0, sp, cp)
        self.assertEqual((r["held"], r["hold_end"]), (False, "no_main_user_box"))
        self.assertEqual((o["tags"][1]["status"], o["tags"][1]["unknown_reason"]), ("unknown", "no_main_user_box"))
        o = out(False)
        self.assertIsNone(step.check(o, [], 4.0, sp, cp))
        self.assertIs(o["tags"][1]["status"], False)
        o = out("unknown", "too_few_rows")                      # another unknown reason does not end it
        step.held = True
        self.assertTrue(step.check(o, [], 5.0, sp, cp)["held"])
        self.assertIs(o["tags"][1]["status"], True)
        o = out("unknown", "no_frames")                         # a window with no rows is never forced true
        r = step.check(o, [], 6.0, sp, cp)
        self.assertEqual((r["held"], r["hold_end"], o["tags"][1]["status"]), (False, "no_frames", "unknown"))
        engine = AidConfirm(self.Reader(0.9), 0.5, 10.0, hold=True)
        for reason in ("no_main_user_box", "no_frames"):
            engine.held = True
            r = engine.check(out("unknown", reason), [], 3.0, sp, cp)
            self.assertEqual((r["held"], r["hold_end"]), (False, reason))
            r = engine.check(out(True, cls="wheelchair"), [], 4.0, sp, cp)   # no rows: not confirmed, not held
            self.assertEqual((r["held"], r["confirmed"]), (False, False))
        self.assertEqual(step.reader.ms + engine.reader.ms, [])
        self.assertEqual(engine.summary()["hold_ends"], {"no_main_user_box": 1, "no_frames": 1})

    def test_live_user_hold_ends_where_the_main_user_leaves(self):
        """Through run_live: the user and the detector's boxes are there for 3 s, then nothing. The user hold agreed
        while the user was there; the first window whose aid_use is unknown with no_main_user_box is not held, and no
        window after it."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        n, calls = 160, []
        empty = (np.zeros((0, 4)), np.zeros(0))

        def leaving(img):
            calls.append(1)
            if len(calls) <= 30:
                return self.aids(img)
            return Aids(np.zeros((0, 4)), np.zeros(0), np.zeros((0, 5)), self.CLASSES, (img.shape[1], img.shape[0]),
                        {"infer": 0.0}, {"crutch": empty, "cane": empty, "walker": empty, "wheelchair": empty})
        heads = [[[0.38, 0.22, 0.62, 0.58]]] * 30 + [[]] * (n - 30)
        _, recs, _ = self.live_sessions(AidConfirm(self.Reader(0.9), 0.5, keep, hold_user=True), n=n, heads=heads,
                                        at={}, aids=leaving)
        reasons = [self.aid(r)[1] for r in recs]
        self.assertIn("no_main_user_box", reasons)
        k = reasons.index("no_main_user_box")
        self.assertTrue(any((r["aid_confirm"] or {}).get("held") for r in recs[:k]))
        self.assertEqual(recs[k]["aid_confirm"]["hold_end"], "no_main_user_box")
        self.assertFalse(any((r["aid_confirm"] or {}).get("held") for r in recs[k:]))

    class PixelReader:
        """A stand-in reader whose crop carries the frame's pixel value (pixel_frames: the frame index) and whose
        P(wheelchair) depends on it (0.5 to 0.95 in steps of 0.05), so a window's median depends on which rows it reads;
        order = the pixel values in the order they were read."""

        def __init__(self, delay_s=0.0):
            self.ms, self.order, self.delay_s = [], [], delay_s

        def crop(self, bgr, box_px):
            import numpy as np
            return np.full((8, 8, 3), int(bgr[0, 0, 0]), np.uint8)

        def probs(self, image):
            import time as _time
            import numpy as np
            if self.delay_s:
                _time.sleep(self.delay_s)
            k = int(image[0, 0, 0])
            self.ms.append(0.0)
            self.order.append(k)
            p = 0.5 + 0.05 * (k % 10)
            return np.array([1.0 - p, 0.0, 0.0, 0.0, p])

    @staticmethod
    def pixel_frames(times):
        """Fake camera frames at the given times whose pixels hold their index (< 256), with a wall time."""
        import numpy as np
        from test_vision_links import EPOCH0
        from app.modules.vision.sources import Frame
        return [Frame(i, round(t, 6), np.full((120, 160, 3), i, np.uint8), str(i), 0.0, EPOCH0 + t)
                for i, t in enumerate(times)]

    class Watched:
        """Wraps an AidConfirm's check: at the entry of every check of an engine-wheelchair window that is not held,
        records the valued rows of the window (those with a crop) that were neither read nor submitted yet."""

        def __init__(self, step):
            self.step, self.missing, self.checked = step, [], 0
            inner = step.check

            def check(out, rows, t_end, sp, cp, images=None, *rest):
                tag = next(t for t in out["tags"] if t["name"] == "aid_use")
                cls = next((e["value"] for e in tag["evidence"] if e["obs"] == "aid_class"), None)
                if tag["status"] is True and cls == "wheelchair" and not step.held:
                    self.checked += 1
                    valued = [int(r["frame_idx"]) for r in rows if t_end - sp.window_s <= float(r["t_s"]) <= t_end
                              and int(r["frame_idx"]) in (images or {})]
                    self.missing += [k for k in valued if k not in step.futures and k not in step.wheelchair]
                return inner(out, rows, t_end, sp, cp, images, *rest)
            step.check = check

    def test_live_hold_ends_at_the_first_named_session(self):
        """Through run_live with the touch entry: no touch window for the first 4 s (the windows are released on the
        runner's cadence, session none, and the reader agrees there), then session s1. The first s1 window carries
        hold_end session and no s1 window is held before a new agreement (both holds): FrameChain resets the main-user
        tracker there, so no change event could end it. s1 lasts 10 s, so the hold starts again on a read window whose
        span lies after the reset (assert_hold_restarts_after_reset)."""
        from test_vision_links import window_body
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        at = {10 * k: [window_body(k - 1.0, float(k), session_id="s1")] for k in range(5, 15)}
        for flags in ({"hold": True}, {"hold_user": True}):
            step = AidConfirm(self.Reader(0.9), 0.5, keep, **flags)
            _, recs, meta = self.live_sessions(step, n=150, at=at)
            before = [r for r in recs if r["evaluated"]["session_id"] is None]
            s1 = [r for r in recs if r["evaluated"]["session_id"] == "s1"]
            self.assertTrue(any((r["aid_confirm"] or {}).get("held") for r in before), flags)
            self.assertEqual((s1[0]["aid_confirm"]["held"], s1[0]["aid_confirm"].get("hold_end")), (False, "session"))
            self.assertEqual(step.reset[1], "s1", flags)
            self.assert_hold_restarts_after_reset(s1, step.reset[0], b.situation.window_s, flags)
            self.assertEqual(meta["aid_confirm"]["hold_ends"], {"session": 1}, flags)

    def test_live_user_hold_ends_at_a_user_change_the_chain_itself_finds(self):
        """Through run_live: user A (wheelchair) for 3 s, then nobody (no head, no body) for 1.5 s (above the head
        track's max gap, below the window), then user B elsewhere whom the detector reads as no aid. The chain gives
        a main_user_changed event; the user hold ends at the first window whose user_changed is true, and the windows
        after it keep the engine's own answer."""
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.live import run_live
        n = 110
        heads = [[[0.38, 0.22, 0.62, 0.58]]] * 30 + [[]] * 15 + [[[0.05, 0.25, 0.25, 0.55]]] * (n - 45)
        sched = ([fake_inference() for _ in range(30)] + [fake_inference(face=False, body=False) for _ in range(15)]
                 + [fake_inference() for _ in range(n - 45)])
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        folder = tempfile.mkdtemp()
        run_live(frames(n), b, models=FakeModels(sched), detector=ScheduledHeads(heads), aids=self.fading_aids(30),
                 show_window=False, out_dir=folder, print_fn=lambda line: None,
                 aid_confirm=AidConfirm(self.Reader(0.9), 0.5, keep, hold_user=True))
        with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
            recs = [json.loads(line) for line in f]
        changed = [i for i, r in enumerate(recs)
                   if {t["name"]: t for t in r["situation"]["tags"]}["user_changed"]["status"] is True]
        self.assertTrue(changed)
        k = changed[0]
        self.assertTrue(any((r["aid_confirm"] or {}).get("held") for r in recs[:k]))
        self.assertEqual(recs[k]["aid_confirm"]["hold_end"], "user_changed")
        for r in recs[k:]:
            self.assertFalse((r["aid_confirm"] or {}).get("held"), r["t"])
            self.assertIsNot(self.aid(r)[0], True, r["t"])

    def test_a_late_release_reads_the_same_rows_and_median_as_replay(self):
        """Through run_live with the touch entry: the touch windows of s1 come 2 s late up to 8 s and then stop, so the
        later windows wait until their start is about to leave the kept history (kept_history). Every window whose
        span starts after the session start gives the same aid_confirm rows and median as the replay of the same
        frames, with no error."""
        from test_vision_links import entry, reporting, window_body
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.live import run_live
        from app.modules.vision.replay import run_replay
        n = 170
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        heads = [[[0.38, 0.22, 0.62, 0.58]]] * n

        def recs_of(folder):
            with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
                return {r["t"]: r for r in (json.loads(line) for line in f)}
        out = os.path.join(tempfile.mkdtemp(), "out")
        run_replay(self.pixel_frames([i * DT for i in range(n)]), out, b,
                   models=FakeModels([fake_inference() for _ in range(n)]), detector=ScheduledHeads(heads),
                   aids=self.aids, session_id="t", aid_confirm=AidConfirm(self.PixelReader(), 0.5, keep))
        replay = recs_of(out)
        folder, svc = tempfile.mkdtemp(), entry(b=b)
        at = {10 * (k + 2): [window_body(k - 1.0, float(k), session_id="s1")] for k in range(1, 9)}
        run_live(reporting(self.pixel_frames([i * DT for i in range(n)]), svc, at), b,
                 models=FakeModels([fake_inference() for _ in range(n)]), detector=ScheduledHeads(heads),
                 aids=self.aids, show_window=False, out_dir=folder, print_fn=lambda line: None, entry=svc,
                 aid_confirm=AidConfirm(self.PixelReader(), 0.5, keep))
        live = recs_of(folder)
        hows = {live[t]["evaluated"]["how"] for t in live if t > b.situation.window_s}
        self.assertTrue({"touch", "kept_history"} <= hows, hows)
        compared = 0
        for t, r in live.items():
            if t <= b.situation.window_s or t not in replay or r.get("partial"):
                continue
            a, e = r["aid_confirm"], replay[t]["aid_confirm"]
            self.assertEqual((a["rows"], a["median"]), (e["rows"], e["median"]), (t, r["evaluated"]["how"]))
            self.assertNotIn("error", a)
            compared += 1
        self.assertGreaterEqual(compared, 5)

    def test_readahead_has_every_valued_row_submitted_before_the_check_and_backfills_in_time_order(self):
        """Through run_live: the detector reads a wheelchair only from frame 20 on. At the entry of every check of an
        engine-wheelchair window, every row of the window with a crop is already read or submitted (this fails when
        read-ahead does nothing), and the reader reads the rows before frame 20 first, oldest first."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.live import run_live
        empty = (np.zeros((0, 4)), np.zeros(0))
        calls, n, k0 = [], 60, 20

        def from_k(img):
            calls.append(1)
            wc = (np.array([self.PERSON]), np.array([0.6])) if len(calls) > k0 else empty
            return Aids(np.array([self.PERSON]), np.array([0.6]), np.array([[0.1, 0, 0, 0, 0.6]]), self.CLASSES,
                        (img.shape[1], img.shape[0]), {"infer": 0.0},
                        {"crutch": empty, "cane": empty, "walker": empty, "wheelchair": wc})
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        reader = self.PixelReader()
        step = AidConfirm(reader, 0.5, keep)
        watched = self.Watched(step)
        run_live(self.pixel_frames([i * DT for i in range(n)]), b,
                 models=FakeModels([fake_inference() for _ in range(n)]),
                 detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * n), aids=from_k, show_window=False,
                 out_dir=tempfile.mkdtemp(), print_fn=lambda line: None, aid_confirm=step)
        self.assertGreater(watched.checked, 0)
        self.assertEqual(watched.missing, [])
        self.assertEqual(reader.order[:k0 + 1], list(range(k0 + 1)))       # back-fill of the span, oldest first
        self.assertEqual(reader.order, sorted(reader.order))
        self.assertEqual(len(reader.order), len(set(reader.order)))         # every row once

    def test_a_slow_reader_with_the_tag_sender_keeps_order_count_and_settles(self):
        """Through run_live with the touch entry and the real tag sender to a stand-in backend, a reader of 30 ms per
        call and frames paced at half real time: the windows arrive in time order, as many as the windows with a
        session, nothing is replaced or left unsent, and every touch window is settled."""
        import time as _time
        from test_vision_links import StubBackend, entry, reporting, timed_frames, window_body
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.live import run_live
        from app.modules.vision.tag_sender import TagSender
        stub = StubBackend()
        self.addCleanup(stub.close)
        n = 60
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        svc = entry(b=b)
        sender = TagSender(stub.url, b.chain.segment_s)

        def paced(frames_):
            for f in frames_:
                _time.sleep(DT / 2)
                yield f
        at = {10 * k: [window_body(k - 1.0, float(k), session_id="s1")] for k in range(1, 6)}
        folder = tempfile.mkdtemp()
        meta = run_live(paced(reporting(timed_frames(n), svc, at)), b,
                        models=FakeModels([fake_inference() for _ in range(n)]),
                        detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * n), aids=self.aids, show_window=False,
                        out_dir=folder, print_fn=lambda line: None, entry=svc, sender=sender,
                        aid_confirm=AidConfirm(self.PixelReader(delay_s=0.03), 0.5, keep))
        with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
            recs = [json.loads(line) for line in f]
        with_session = [r for r in recs if r["evaluated"]["session_id"] is not None]
        s = meta["tag_sender"]
        self.assertEqual((s["replaced"], s["unsent_at_close"], s["failed"]), (0, 0, 0))
        self.assertEqual(len(stub.received), len(with_session))
        ends = [body["window_end"] for _, body in stub.received]
        self.assertEqual(ends, sorted(ends))
        settling = svc.status()["settling"]
        self.assertEqual(settling["settled"], settling["accepted"])

    def test_both_holds_end_at_an_empty_window_through_the_runner_and_the_cut_is_strict(self):
        """Through run_live: (a) the engine-wheelchair hold ends where the user and the detector's boxes have left
        (no_main_user_box); (b) a camera gap of 8 s gives windows with no rows (no_frames): both holds end there and
        such a window is never answered true; (c) a reader at exactly the cut (0.5 at 0.5) withdraws every window,
        with the reason median."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.live import run_live
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        empty = (np.zeros((0, 4)), np.zeros(0))
        n, calls = 160, []

        def leaving(img):
            calls.append(1)
            if len(calls) <= 30:
                return self.aids(img)
            return Aids(np.zeros((0, 4)), np.zeros(0), np.zeros((0, 5)), self.CLASSES, (img.shape[1], img.shape[0]),
                        {"infer": 0.0}, {"crutch": empty, "cane": empty, "walker": empty, "wheelchair": empty})
        heads = [[[0.38, 0.22, 0.62, 0.58]]] * 30 + [[]] * (n - 30)
        _, recs, meta = self.live_sessions(AidConfirm(self.Reader(0.9), 0.5, keep, hold=True), n=n, heads=heads,
                                           at={}, aids=leaving)
        self.assertEqual(meta["aid_confirm"]["hold_ends"], {"no_main_user_box": 1})
        k = [self.aid(r)[1] for r in recs].index("no_main_user_box")
        self.assertEqual(recs[k]["aid_confirm"]["hold_end"], "no_main_user_box")

        def gap_run(flags, reader):
            times = [i * DT for i in range(40)] + [12.0 + i * DT for i in range(40)]
            folder = tempfile.mkdtemp()
            meta = run_live(self.pixel_frames(times), b, models=FakeModels([fake_inference() for _ in range(80)]),
                            detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * 80), aids=self.aids,
                            show_window=False, out_dir=folder, print_fn=lambda line: None,
                            aid_confirm=AidConfirm(reader, 0.5, keep, **flags))
            with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
                return [json.loads(line) for line in f], meta
        for flags in ({"hold": True}, {"hold_user": True}):
            recs, meta = gap_run(flags, self.Reader(0.9))
            empty_windows = [r for r in recs if self.aid(r)[1] == "no_frames"
                             or (r["aid_confirm"] or {}).get("engine_unknown_reason") == "no_frames"]
            self.assertTrue(empty_windows, flags)
            self.assertEqual(empty_windows[0]["aid_confirm"]["hold_end"], "no_frames")
            self.assertEqual({self.aid(r) for r in empty_windows}, {("unknown", "no_frames")}, flags)   # never true
            self.assertEqual(meta["aid_confirm"]["hold_ends"], {"no_frames": 1}, flags)
            after = [r for r in recs if r["t"] > empty_windows[-1]["t"] and (r["aid_confirm"] or {}).get("confirmed")]
            self.assertFalse(after[0]["aid_confirm"]["held"], flags)              # a new agreement first
        recs, meta = gap_run({}, self.Reader(0.5))
        checked = [r for r in recs if r["aid_confirm"] is not None]
        self.assertTrue(checked)
        for r in checked:
            self.assertEqual((r["aid_confirm"]["confirmed"], r["aid_confirm"]["reason"]), (False, "median"))
            self.assertEqual(r["aid_confirm"]["median"], 0.5)

    def test_a_reader_error_makes_the_window_not_confirmed_and_the_run_goes_on(self):
        """A reader whose read raises: every checked window is not confirmed (aid_use false) with aid_confirm.error,
        one log line for the run, the run ends normally and meta.json counts the errors. Each record carries its
        release delay and the reader calls so far."""
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.live import run_live

        class Broken(self.Reader):
            def probs(self, image):
                raise OSError("reader broke")
        logged = []
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        folder = tempfile.mkdtemp()
        meta = run_live(frames(30), b, models=FakeModels([fake_inference() for _ in range(30)]),
                        detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * 30), aids=self.aids,
                        show_window=False, out_dir=folder, print_fn=lambda line: None,
                        aid_confirm=AidConfirm(Broken(0.9), 0.5, keep, log=logged.append))
        with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
            recs = [json.loads(line) for line in f]
        self.assertTrue(recs)
        self.assertEqual({self.aid(r) for r in recs}, {(False, None)})
        for r in recs:
            self.assertEqual(r["aid_confirm"]["confirmed"], False)
            self.assertIn("OSError: reader broke", r["aid_confirm"]["error"])
            self.assertIsInstance(r["evaluated"]["release_delay_s"], float)
            self.assertIsInstance(r["evaluated"]["reader_calls_total"], int)
        self.assertEqual(len(logged), 1)
        self.assertEqual(meta["aid_confirm"]["reader_errors"], len(recs))
        self.assertIsNone(meta["aid_confirm"]["release_error"])
        self.assertTrue(os.path.exists(os.path.join(folder, "meta.json")))
        _, off, _ = self.live_sessions(None, n=30, at={})
        self.assertFalse(any("release_delay_s" in r["evaluated"] or "reader_calls_total" in r["evaluated"]
                             for r in off))

    def test_an_error_in_a_release_still_closes_the_entry_and_writes_meta(self):
        """Any other exception on the release worker (here on_window) stops the frame loop, and run_live still stops
        the touch entry and writes meta.json (release_error) before it raises the exception."""
        from test_vision_links import entry, timed_frames
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.live import run_live
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        folder, svc = tempfile.mkdtemp(), entry(b=b)

        def boom(rec, body):
            raise ValueError("release broke")
        with self.assertRaises(ValueError):
            run_live(timed_frames(40), b, models=FakeModels([fake_inference() for _ in range(40)]),
                     detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * 40), aids=self.aids, show_window=False,
                     out_dir=folder, print_fn=lambda line: None, entry=svc, on_window=boom,
                     aid_confirm=AidConfirm(self.Reader(0.9), 0.5, keep))
        with open(os.path.join(folder, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        self.assertIn("ValueError: release broke", meta["aid_confirm"]["release_error"])
        self.assertIn("release worker error", meta["stop_reason"])
        self.assertIsNotNone(svc.status()["camera"]["stopped"])

    def test_readahead_reads_only_rows_of_a_wheelchair_span_and_keeps_the_answers(self):
        """run_live with read-ahead: a detector that never reads a wheelchair gives no reader call; one that reads a
        wheelchair gives the same answers as the window-end reading, and the checks wait for few reads."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.live import run_live
        empty = (np.zeros((0, 4)), np.zeros(0))

        def no_wheelchair(img):
            return Aids(np.array([self.PERSON]), np.array([0.6]), np.array([[0.6, 0, 0, 0, 0.1]]), self.CLASSES,
                        (img.shape[1], img.shape[0]), {"infer": 0.0},
                        {"crutch": empty, "cane": empty, "walker": empty, "wheelchair": empty})

        def live(aids, confirm):
            folder = tempfile.mkdtemp()
            b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
            meta = run_live(frames(30), b, models=FakeModels([fake_inference() for _ in range(30)]),
                            detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * 30), aids=aids,
                            show_window=False, out_dir=folder, print_fn=lambda line: None, aid_confirm=confirm)
            with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
                return b, [json.loads(line) for line in f], meta
        b, _, _ = live(no_wheelchair, None)
        keep = history_s(b) + b.chain.segment_s
        reader = self.Reader(0.9)
        _, recs, meta = live(no_wheelchair, AidConfirm(reader, 0.5, keep))
        self.assertEqual((reader.ms, meta["aid_confirm"]["reads"]), ([], 0))
        step = AidConfirm(self.Reader(0.1), 0.5, keep)
        watched = self.Watched(step)                      # every valued row submitted before its check
        _, ahead, meta = live(self.aids, step)
        self.assertGreater(watched.checked, 0)
        self.assertEqual(watched.missing, [])
        self.assertTrue(meta["aid_confirm"]["readahead"])
        self.assertEqual({self.aid(r) for r in ahead}, {(False, None)})
        self.assertEqual(meta["aid_confirm"]["reads"], 30)

    # --- a hold starts only after the chain's reset; the reader behind the frames ----------------------------------
    class ByPlace:
        """A stand-in reader that reads by where the person box is: 0.9 for a box at the left (the wheelchair user W),
        0.1 elsewhere (the ordinary person O)."""

        def __init__(self):
            self.ms = []

        def crop(self, bgr, box_px):
            import numpy as np
            cx = (box_px[0] + box_px[2]) / 2.0 / bgr.shape[1]
            return np.full((8, 8, 3), 200 if cx < 0.3 else 50, np.uint8)

        def probs(self, image):
            import numpy as np
            self.ms.append(0.0)
            p = 0.9 if int(image[0, 0, 0]) == 200 else 0.1
            return np.array([1.0 - p, 0.0, 0.0, 0.0, p])

    W_HEAD, O_HEAD = [0.05, 0.25, 0.25, 0.55], [0.38, 0.22, 0.62, 0.58]
    W_BODY, O_BODY = [0.0, 0.10, 0.30, 0.97], [0.33, 0.12, 0.72, 0.97]

    def two_people(self, img):
        """The detector stand-in of two people: W's box with a wheelchair channel, O's box without."""
        import numpy as np
        from app.inference.aid import Aids
        empty = (np.zeros((0, 4)), np.zeros(0))
        return Aids(np.array([self.W_BODY, self.O_BODY]), np.array([0.6, 0.6]),
                    np.array([[0.1, 0, 0, 0, 0.6], [0.6, 0, 0, 0, 0.1]]), self.CLASSES, (img.shape[1], img.shape[0]),
                    {"infer": 0.0}, {"crutch": empty, "cane": empty, "walker": empty,
                                     "wheelchair": (np.array([self.W_BODY]), np.array([0.6]))})

    def test_live_holds_do_not_start_on_rows_before_the_first_sessions_reset(self):
        """Through run_live with the touch entry (first case): W (wheelchair) is the main user from the start
        and stays in view; O stands at the kiosk from 3 s; the page's first touch window of s1 arrives at 5 s, where
        FrameChain resets and chooses O. The first s1 window's rows are mostly W's rows from before the reset, so it
        is confirmed, but no s1 window may be held or user-held, and every s1 answer equals plain confirmation's."""
        from test_vision_links import window_body
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        n = 110
        at = {10 * k: [window_body(k - 1.0, float(k), session_id="s1")] for k in range(5, 11)}
        heads = [[self.W_HEAD]] * 30 + [[self.W_HEAD, self.O_HEAD]] * (n - 30)

        def s1_of(flags):
            step = AidConfirm(self.ByPlace(), 0.5, keep, **flags)
            _, recs, _ = self.live_sessions(step, n=n, heads=heads, at=at, aids=self.two_people)
            return [r for r in recs if r["evaluated"]["session_id"] == "s1"], step
        plain, _ = s1_of({})
        self.assertTrue(plain and plain[0]["aid_confirm"]["confirmed"])     # the case: W's rows agree at first
        for flags in ({"hold": True}, {"hold_user": True}):
            s1, step = s1_of(flags)
            self.assertIs(step.held, False, flags)    # also a latent hold that no later wheelchair window would show
            self.assertEqual([self.aid(r) for r in s1], [self.aid(r) for r in plain], flags)
            for r in s1:
                ac = r["aid_confirm"] or {}
                self.assertFalse(ac.get("held") or ac.get("hold_user"), (flags, r["t"], ac))

    def test_live_holds_do_not_start_on_the_few_rows_before_a_second_sessions_reset(self):
        """Through run_live with the touch entry (second case): the detector reads a wheelchair on every frame,
        the reader 0.9 on frames 48 to 50 only. Session s2 starts at 4.75 s and its first touch window arrives at 5.8 s,
        so the window ending 5.0 s reads three rows, all before the chain's reset. It is confirmed, but no s2 window is
        held or user-held, and every s2 answer equals plain confirmation's."""
        import numpy as np
        from test_vision_links import window_body
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        n = 110

        class Burst(self.PixelReader):
            def probs(self, image):
                p = 0.9 if 48 <= int(image[0, 0, 0]) <= 50 else 0.1
                self.ms.append(0.0)
                return np.array([1.0 - p, 0.0, 0.0, 0.0, p])
        at = {10 * k: [window_body(k - 1.0, float(k), session_id="s1")] for k in range(1, 5)}
        at.update({58 + 10 * j: [window_body(4.75 + j, 5.75 + j, session_id="s2")] for j in range(0, 5)})

        def s2_of(flags):
            from test_vision_links import entry, reporting
            from app.modules.vision.live import run_live
            folder, svc = tempfile.mkdtemp(), entry(b=b)
            run_live(reporting(self.pixel_frames([i * DT for i in range(n)]), svc, at), b,
                     models=FakeModels([fake_inference() for _ in range(n)]),
                     detector=ScheduledHeads([[self.O_HEAD]] * n), aids=self.aids, show_window=False, out_dir=folder,
                     print_fn=lambda line: None, entry=svc, aid_confirm=AidConfirm(Burst(), 0.5, keep, **flags))
            with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
                return [r for r in (json.loads(line) for line in f) if r["evaluated"]["session_id"] == "s2"]
        plain = s2_of({})
        self.assertEqual((plain[0]["t"], plain[0]["aid_confirm"]["confirmed"]), (5.0, True))
        for flags in ({"hold": True}, {"hold_user": True}):
            s2 = s2_of(flags)
            self.assertEqual([self.aid(r) for r in s2], [self.aid(r) for r in plain], flags)
            for r in s2:
                ac = r["aid_confirm"] or {}
                self.assertFalse(ac.get("held") or ac.get("hold_user"), (flags, r["t"], ac))

    def test_live_hold_does_not_start_when_the_first_touch_window_comes_during_a_frame(self):
        """Through run_live with the touch entry, the usual ordering of the first session: the page's first
        touch window of s1 arrives while FrameChain processes frame 50 (here from inside the detector call, after the
        chain read the frame's session), so the same loop iteration releases the window ending 5.0 s naming s1 while
        the chain's reset is still to come (frame 51); the check runs before frame 51 is processed. Its rows are all
        from before the reset: it is confirmed but not held, and no s1 window is held (both holds)."""
        import threading
        from test_vision_links import entry, timed_frames, window_body
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.live import run_live
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        n = 70
        for flags in ({"hold": True}, {"hold_user": True}):
            svc, calls, checked = entry(b=b), [], threading.Event()

            def aids(img):
                calls.append(1)
                if len(calls) == 51:          # frame 50, inside process: after its session read
                    self.assertEqual(svc.receive(window_body(4.0, 5.0, session_id="s1"))[0], 202)
                elif len(calls) > 51 and (len(calls) - 1) % 10 == 0:
                    svc.receive(window_body((len(calls) - 1) / 10 - 1.0, (len(calls) - 1) / 10, session_id="s1"))
                return self.aids(img)

            def on_window(rec, body):
                if rec["evaluated"]["session_id"] == "s1":
                    checked.set()

            def ordered(frames_):             # frame 51 only after the s1 window was checked on the worker
                for f in frames_:
                    if f.index == 51:
                        self.assertTrue(checked.wait(10.0))   # a test bound only
                    yield f
            step = AidConfirm(self.Reader(0.9), 0.5, keep, **flags)
            folder = tempfile.mkdtemp()
            run_live(ordered(timed_frames(n)), b, models=FakeModels([fake_inference() for _ in range(n)]),
                     detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * n), aids=aids, show_window=False,
                     out_dir=folder, print_fn=lambda line: None, entry=svc, on_window=on_window, aid_confirm=step)
            with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
                s1 = [r for r in (json.loads(line) for line in f) if r["evaluated"]["session_id"] == "s1"]
            self.assertEqual((s1[0]["t"], s1[0]["aid_confirm"]["confirmed"]), (5.0, True), flags)
            self.assertEqual(step.reset[1], "s1")             # the reset came after that check
            for r in s1:
                ac = r["aid_confirm"] or {}
                self.assertFalse(ac.get("held"), (flags, r["t"], ac))

    def test_live_hold_does_not_carry_into_a_second_session_whose_first_touch_window_comes_during_a_frame(self):
        """Through run_live with the touch entry: s1 (touch windows to 7 s) is held first; the first touch
        window of s2 arrives while FrameChain processes frame 90 (from inside the detector call, after the chain read
        the frame's session), and frame 91 (the chain's reset of s2) is processed only after the s2 window was checked.
        The stored reset is still s1's and every row of the s2 windows lies after it, so only the session match keeps
        the hold from starting: no s2 window is held (both holds), and the hold is not on at the end."""
        import threading
        from test_vision_links import entry, timed_frames, window_body
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.live import run_live
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        n = 150
        for flags in ({"hold": True}, {"hold_user": True}):
            svc, calls, checked = entry(b=b), [], threading.Event()

            def aids(img):
                calls.append(1)
                if len(calls) - 1 == 90:      # inside process(frame 90): after its session read
                    self.assertEqual(svc.receive(window_body(8.0, 9.0, session_id="s2"))[0], 202)
                return self.aids(img)

            def on_window(rec, body):
                if rec["evaluated"]["session_id"] == "s2":
                    checked.set()

            def source():
                for f in timed_frames(n):
                    k = f.index
                    if 1 <= k // 10 <= 7 and k % 10 == 0:
                        svc.receive(window_body(k / 10 - 1.0, k / 10, session_id="s1"))
                    if k > 90 and k % 10 == 0:
                        svc.receive(window_body(k / 10 - 1.0, k / 10, session_id="s2"))
                    if k == 91:
                        self.assertTrue(checked.wait(10.0))   # a test bound only
                    yield f
            step = AidConfirm(self.Reader(0.9), 0.5, keep, **flags)
            folder = tempfile.mkdtemp()
            run_live(source(), b, models=FakeModels([fake_inference() for _ in range(n)]),
                     detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * n), aids=aids, show_window=False,
                     out_dir=folder, print_fn=lambda line: None, entry=svc, on_window=on_window, aid_confirm=step)
            with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
                recs = [json.loads(line) for line in f]
            s1 = [r for r in recs if r["evaluated"]["session_id"] == "s1"]
            s2 = [r for r in recs if r["evaluated"]["session_id"] == "s2"]
            self.assertTrue(any((r["aid_confirm"] or {}).get("held") for r in s1), flags)       # held in s1
            self.assertEqual((s2[0]["t"], s2[0]["aid_confirm"]["hold_end"]), (9.0, "session"), flags)
            self.assertEqual(step.reset[1], "s2", flags)
            for r in s2:
                ac = r["aid_confirm"] or {}
                self.assertFalse(ac.get("held"), (flags, r["t"], ac))
            self.assertIs(step.held, False, flags)

    def test_replay_hold_with_a_two_session_touch_log_ends_and_starts_again_in_the_new_session(self):
        """A replay with a touch log of two sessions (s2 from 9.55 s) under each hold: held in s1, the first s2 window
        ends the hold (session) and agrees again on s2's own rows (the window reads only rows of its session, all at
        or after the chain's reset), the later s2 windows are held, and every answer equals plain confirmation's (the
        reset rule changes no answer, so replay parity stays)."""
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.replay import run_replay
        from app.modules.vision.touch import load_timeline
        n = 150
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s

        def replay(flags):
            folder = tempfile.mkdtemp()
            video = os.path.join(folder, "take.mp4")
            events = [(-1000, "session_start", "menu", None), (-900, "screen_enter", "menu", None),
                      (9500, "session_end", "menu", {"reason": "server_session_change"}),
                      (9550, "session_start", "menu", {"reason": "server_session_change"}, "s2")]
            out = os.path.join(folder, "out")
            meta = run_replay(frames(n), out, b, timeline=load_timeline(touch_log(folder, events, video), video),
                              models=FakeModels([fake_inference() for _ in range(n)]),
                              detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * n), aids=self.aids,
                              session_id="t", aid_confirm=AidConfirm(self.Reader(0.9), 0.5, keep, **flags))
            with open(os.path.join(out, "windows.jsonl"), encoding="utf-8") as f:
                return [json.loads(line) for line in f], meta
        plain, _ = replay({})
        for flags in ({"hold": True}, {"hold_user": True}):
            recs, meta = replay(flags)
            self.assertEqual([self.aid(r) for r in recs], [self.aid(r) for r in plain], flags)
            k = next(i for i, r in enumerate(recs) if r["session_reset"])
            self.assertTrue(any(r["aid_confirm"]["held"] for r in recs[:k]), flags)
            first = recs[k]["aid_confirm"]
            self.assertEqual((first["hold_end"], first["confirmed"], first["held"]), ("session", True, False), flags)
            self.assertTrue(all(r["aid_confirm"]["held"] for r in recs[k + 1:]), flags)
            self.assertEqual(meta["aid_confirm"]["hold_ends"], {"session": 1}, flags)

    @staticmethod
    def pixel_row(k, wheelchair=True):
        """A row of frame k (t = k x DT) with the main user's head box and the detector's own reading of it, and its
        frame whose pixels hold k (PixelReader)."""
        import numpy as np
        row = {"t_s": round(k * DT, 6), "frame_idx": k, "primary_box": [0.38, 0.22, 0.62, 0.58],
               "aid_head_class": "wheelchair" if wheelchair else None, "aid_head_score": 0.6 if wheelchair else 0.0}
        return row, np.full((120, 160, 3), k, np.uint8)

    def test_readahead_after_a_hold_end_backfills_only_that_windows_rows(self):
        """Read-ahead stops while held; at the hold's end trigger_until is cleared and the back-fill
        starts at the ending window's first row (readahead_from). A wheelchair row soon after (inside the span the
        trigger before the hold had opened) back-fills that window's rows and no older row."""
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.params import PilotParams
        reader = self.PixelReader()
        step = AidConfirm(reader, 0.5, 100.0, hold=True)
        step.start_readahead(0.5, sit_params().window_s)
        rows = {}
        for k in range(0, 21):                     # rows 0 to 9 no wheelchair, 10 a trigger; then held
            if k == 11:
                step.held = True
            row, img = self.pixel_row(k, wheelchair=k >= 10)
            rows[k] = row
            step.add_row(row, img, self.aids(img))
        out = {"tags": [{"name": "user_changed", "status": False, "evidence": [], "unknown_reason": None},
                        {"name": "aid_use", "status": False, "unknown_reason": None,
                         "evidence": [{"event_id": "aid_head@1", "obs": "aid_class", "value": None, "t": 1.0}]}]}
        ended = step.check(out, [rows[k] for k in range(15, 21)], 2.0, sit_params(), PilotParams(), session_reset=True)
        self.assertEqual(ended["hold_end"], "session")
        row, img = self.pixel_row(21)
        step.add_row(row, img, self.aids(img))
        step.stop_readahead()
        self.assertEqual(reader.order, list(range(0, 11)) + list(range(15, 22)))

    class GatedReader(PixelReader):
        """A PixelReader whose read of frame `gate` waits until go is set (started is set when it begins), so the
        reader thread is busy while the frame thread goes on."""

        def __init__(self, gate=0):
            import threading
            super().__init__()
            self.gate, self.started, self.go = gate, threading.Event(), threading.Event()

        def probs(self, image):
            if int(image[0, 0, 0]) == self.gate:
                self.started.set()
                self.go.wait(10.0)              # a test bound only: go is always set by the test
            return super().probs(image)

    def test_a_pruned_rows_queued_read_is_cancelled_and_a_waiting_check_reads_it_again(self):
        """The reader thread is busy with row 0 and rows 1 to 4 are queued. A check waits on row 1's
        read when the frame thread prunes rows 0 to 2: the queued reads of rows 1 and 2 are cancelled (row 2 is never
        read), the check catches the cancel and reads row 1 again from its own images, the running read of row 0
        finishes without leaving a value for the pruned row, and no future of a pruned row stays in the table."""
        import threading
        from app.modules.vision.aid_confirm import AidConfirm
        reader = self.GatedReader(gate=0)
        step = AidConfirm(reader, 0.5, 1.05)      # keep_s: rows older than t - 1.05 s are pruned
        step.start_readahead(0.5, sit_params().window_s)
        images = {}
        for k in range(0, 5):
            row, img = self.pixel_row(k)
            step.add_row(row, img, self.aids(img))
            images[k] = step.images[k][1]
        self.assertTrue(reader.started.wait(10.0))
        queued = dict(step.futures)
        asked = threading.Event()

        class Telling(dict):
            def get(self, key, default=None):
                value = dict.get(self, key, default)
                if key == 1:
                    asked.set()
                return value
        step.futures = Telling(step.futures)
        got = {}

        def check_row_1():
            try:
                got["value"] = step._value(1, {1: images[1]})
            except BaseException as e:          # recorded for the assertion below
                got["error"] = e
        waiting = threading.Thread(target=check_row_1)
        waiting.start()
        self.assertTrue(asked.wait(10.0))
        row, img = self.pixel_row(13)            # t 1.3: floor 0.25 prunes rows 0, 1 and 2
        step.add_row(row, img, self.aids(img))
        self.assertTrue(queued[1].cancelled() and queued[2].cancelled())
        reader.go.set()
        waiting.join(10.0)
        step.stop_readahead()
        self.assertEqual(set(got), {"value"}, got)
        self.assertAlmostEqual(got["value"], 0.55)
        self.assertNotIn(2, reader.order)
        self.assertEqual(sorted(reader.order), [0, 1, 3, 4, 13])
        self.assertNotIn(0, step.wheelchair)       # read after its prune: no value kept
        self.assertLessEqual(set(step.futures), set(step.images))

    def test_a_reader_error_pruned_between_test_and_lookup_still_reads_as_an_error(self):
        """_value reads a row's error with one lookup (.get), so a prune on the frame thread between
        a membership test and a lookup cannot raise a KeyError in the check; the row stays a reader error."""
        from app.modules.vision.aid_confirm import AidConfirm

        class Vanishing(dict):
            def __contains__(self, key):         # the frame thread prunes the row right after the test
                hit = dict.__contains__(self, key)
                self.pop(key, None)
                return hit
        step = AidConfirm(self.Reader(0.9), 0.5, 10.0)
        step.failed = Vanishing({5: "OSError: reader broke"})
        with self.assertRaisesRegex(RuntimeError, "reader broke"):
            step._value(5, {})

    def test_a_reader_behind_the_frames_is_reported_from_the_frame_loop_and_counted(self):
        """The reader thread blocks on its first read, frames go on (paced). The frame loop sees the oldest
        queued release older than segment_s and prints the late line before any window has come back; after the
        reader is let go, the late windows are counted in meta.json aid_confirm.releases_later_than_segment and the
        line is not printed again."""
        import time as _time
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.live import run_live
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        keep = history_s(b) + b.chain.segment_s
        reader = self.GatedReader(gate=0)
        lines, seen_blocked = [], []
        n = 45

        def paced(frames_):                       # 50 ms per frame while the reader is blocked, then at once
            for f in frames_:
                if not reader.go.is_set() and any("aid_confirm.releases_later_than_segment" in x for x in lines):
                    seen_blocked.append(f.index)
                    reader.go.set()
                if not reader.go.is_set():
                    _time.sleep(0.05)
                yield f
            reader.go.set()
        meta = run_live(paced(self.pixel_frames([i * DT for i in range(n)])), b,
                        models=FakeModels([fake_inference() for _ in range(n)]),
                        detector=ScheduledHeads([[[0.38, 0.22, 0.62, 0.58]]] * n), aids=self.aids,
                        show_window=False, out_dir=tempfile.mkdtemp(), print_fn=lines.append,
                        aid_confirm=AidConfirm(reader, 0.5, keep))
        self.assertTrue(seen_blocked)                         # printed while the reader was still blocked
        late = [x for x in lines if "aid_confirm.releases_later_than_segment" in x]
        self.assertEqual(len(late), 1)
        self.assertIn("아직 내보내지 못했습니다", late[0])
        self.assertGreaterEqual(meta["aid_confirm"]["releases_later_than_segment"], 1)

    def test_a_reader_slower_than_the_frames_gives_the_replays_rows_and_medians(self):
        """The reader-behind run made short (a 2 s window, so rows leave the kept history after
        3.5 s): a reader of 10 ms per read and frames as fast as the chain runs, so the release worker falls far behind,
        rows of queued windows are pruned and their queued reads cancelled. Every window gives the replay's rows,
        median and answer, with no error, in time order; the late line comes once and its count is in meta; no future
        of a pruned row stays in the table."""
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        from app.modules.vision.live import run_live
        from app.modules.vision.params import Bundle, PilotParams
        from app.modules.vision.replay import run_replay
        n = 70
        b = Bundle(PilotParams(aid_rule="head_centre_carry", aid_head_min=0.5), sit_params(window_s=2.0), "test")
        keep = history_s(b) + b.chain.segment_s
        heads = [[[0.38, 0.22, 0.62, 0.58]]] * n
        out = os.path.join(tempfile.mkdtemp(), "out")
        run_replay(self.pixel_frames([i * DT for i in range(n)]), out, b,
                   models=FakeModels([fake_inference() for _ in range(n)]), detector=ScheduledHeads(heads),
                   aids=self.aids, session_id="t", aid_confirm=AidConfirm(self.PixelReader(), 0.5, keep),
                   log=lambda *a: None)
        with open(os.path.join(out, "windows.jsonl"), encoding="utf-8") as f:
            replay = {r["t"]: r for r in (json.loads(line) for line in f)}
        step, lines, folder = AidConfirm(self.PixelReader(delay_s=0.01), 0.5, keep), [], tempfile.mkdtemp()
        meta = run_live(self.pixel_frames([i * DT for i in range(n)]), b,
                        models=FakeModels([fake_inference() for _ in range(n)]), detector=ScheduledHeads(heads),
                        aids=self.aids, show_window=False, out_dir=folder, print_fn=lines.append, aid_confirm=step)
        with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
            live = [json.loads(line) for line in f]
        self.assertEqual([r["t"] for r in live], sorted(r["t"] for r in live))
        compared = 0
        for r in live:
            if r.get("partial"):
                continue
            a, e = r["aid_confirm"], replay[r["t"]]["aid_confirm"]
            self.assertNotIn("error", a)
            self.assertEqual((a["rows"], a["median"], a["confirmed"]), (e["rows"], e["median"], e["confirmed"]), r["t"])
            compared += 1
        self.assertGreaterEqual(compared, 5)
        late = [x for x in lines if "aid_confirm.releases_later_than_segment" in x]
        self.assertEqual(len(late), 1)
        self.assertGreater(meta["aid_confirm"]["releases_later_than_segment"], 0)
        self.assertLessEqual(set(step.futures), set(step.images))

    def test_crop_box_widens_the_person_box_by_the_margin_and_clips_it(self):
        from app.inference.aid_confirm import MARGIN_PX, crop_box
        self.assertEqual(MARGIN_PX, 20)
        self.assertEqual(crop_box((30.4, 40.6, 80.2, 100.0), (160, 120)), (10, 20, 101, 120))
        self.assertEqual(crop_box((-50, -50, -30, -30), (160, 120)), (0, 0, 160, 120))   # nothing left: whole frame

    def test_reader_means_the_softmax_of_its_files_and_cuts_rgb(self):
        import numpy as np
        from app.inference.aid_confirm import AidConfirmReader, softmax
        a, b = [2.0, 0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 0.0, 3.0]
        r = AidConfirmReader([], sessions=[self.Session(a), self.Session(b)])
        p = r.probs(np.zeros((8, 8, 3), np.uint8))
        np.testing.assert_allclose(p, (softmax(np.array(a)) + softmax(np.array(b))) / 2)
        self.assertAlmostEqual(float(p.sum()), 1.0)
        img = np.zeros((40, 40, 3), np.uint8)
        img[:, :, 2] = 200                                     # BGR: the red channel last
        crop = r.crop(img, (10, 10, 20, 20))
        self.assertEqual(crop.shape, (8, 8, 3))
        self.assertEqual(int(crop[0, 0, 0]), 200)              # RGB: red first

    def test_reader_refuses_a_file_with_another_output_size(self):
        from app.inference.aid_confirm import AidConfirmReader
        with self.assertRaises(ValueError):
            AidConfirmReader([], sessions=[self.Session([0.0, 1.0])])
        with self.assertRaises(ValueError):
            AidConfirmReader([], sessions=[])

    def test_replay_keeps_a_wheelchair_window_the_reader_confirms_and_withdraws_the_others(self):
        """The same replay three times: without the step every window is true with the class wheelchair; a reader
        that reads P(wheelchair) 0.9 keeps them (records carry aid_confirm, confirmed); one that reads 0.1 makes
        them false. Each row is read once; without the step no record or meta carries aid_confirm."""
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        b, off, meta_off = self.replay()
        self.assertEqual({self.aid(r) for r in off}, {(True, None)})
        self.assertFalse(any("aid_confirm" in r for r in off))
        self.assertNotIn("aid_confirm", meta_off)
        keep = history_s(b) + b.chain.segment_s
        _, kept, meta = self.replay(AidConfirm(self.Reader(0.9), 0.5, keep))
        self.assertEqual([self.aid(r) for r in kept], [self.aid(r) for r in off])
        self.assertTrue(all(r["aid_confirm"]["confirmed"] for r in kept))
        self.assertEqual(meta["aid_confirm"]["windows_checked"], len(kept))
        self.assertEqual(meta["aid_confirm"]["windows_withdrawn"], 0)
        self.assertEqual(meta["aid_confirm"]["reads"], 30)                 # every row once, though windows overlap
        _, dropped, meta = self.replay(AidConfirm(self.Reader(0.1), 0.5, keep))
        self.assertEqual({self.aid(r) for r in dropped}, {(False, None)})
        self.assertFalse(any(r["aid_confirm"]["confirmed"] for r in dropped))
        self.assertEqual(meta["aid_confirm"]["windows_withdrawn"], len(dropped))

    def test_person_box_is_the_detector_box_around_the_head_or_the_carried_box(self):
        """A head row reads the best-scoring box that holds the head centre; a carried row the box with the highest
        IoU to the carried aid box; a row with neither has no crop."""
        import numpy as np
        from app.inference.aid import Aids
        from app.modules.vision.aid_confirm import person_box
        aids = Aids(np.array([[0.0, 0.0, 0.3, 0.3], [0.2, 0.1, 0.8, 0.9], [0.25, 0.1, 0.75, 0.95]]),
                    np.array([0.9, 0.4, 0.7]), np.zeros((3, 5)), self.CLASSES, (160, 120), {})
        self.assertEqual(person_box(aids, {"primary_box": (0.4, 0.2, 0.6, 0.4)}), (0.25, 0.1, 0.75, 0.95))
        self.assertEqual(person_box(aids, {"primary_box": None, "aid_head_from": "carried",
                                           "aid_head_box": (0.2, 0.1, 0.8, 0.9)}), (0.2, 0.1, 0.8, 0.9))
        self.assertIsNone(person_box(aids, {"primary_box": None, "aid_head_from": None, "aid_head_box": None}))

    def test_runner_options_need_the_aid_model_and_a_head_reading(self):
        import argparse
        from app.modules.vision.replay import CONFIRM_MIN_DEFAULT, add_aid_confirm_options, check_aid_confirm_options
        ap = argparse.ArgumentParser()
        ap.add_argument("--aid-model", default=None)
        add_aid_confirm_options(ap)
        path = os.path.join(tempfile.mkdtemp(), "reader.onnx")
        with open(path, "wb") as f:
            f.write(b"stand-in")
        errors = []
        a = ap.parse_args([])
        self.assertEqual((a.aid_confirm_model, a.aid_confirm_min), (None, CONFIRM_MIN_DEFAULT))
        check_aid_confirm_options(errors.append, a, "owner_box")              # off: nothing to check
        check_aid_confirm_options(errors.append, ap.parse_args(["--aid-confirm-model", path]), "head_centre_carry")
        check_aid_confirm_options(errors.append, ap.parse_args(["--aid-model", "d.onnx", "--aid-confirm-model", path]),
                                  "owner_box")
        check_aid_confirm_options(errors.append, ap.parse_args(["--aid-model", "d.onnx", "--aid-confirm-model",
                                                                path + ".missing"]), "head_centre")
        check_aid_confirm_options(errors.append, ap.parse_args(["--aid-model", "d.onnx", "--aid-confirm-model", path,
                                                                "--aid-confirm-model", path]), "head_centre_carry")
        self.assertEqual(len(errors), 3)
        self.assertIn("needs --aid-model", errors[0])
        self.assertIn("head_centre", errors[1])
        self.assertIn("no file", errors[2])
        held = []
        check_aid_confirm_options(held.append, ap.parse_args(["--aid-model", "d.onnx", "--aid-confirm-hold"]),
                                  "head_centre_carry")
        self.assertEqual(held, ["--aid-confirm-hold needs --aid-confirm-model"])
        user = []
        check_aid_confirm_options(user.append, ap.parse_args(["--aid-model", "d.onnx", "--aid-confirm-hold-user"]),
                                  "head_centre_carry")
        self.assertEqual(user, ["--aid-confirm-hold-user needs --aid-confirm-model"])
        self.assertFalse(ap.parse_args([]).aid_confirm_hold)

    # --- --aid-start-only (aid_confirm.py, 'Start only') ---------------------------------------------------------------
    def clocked_aids(self, n, sched=None, wheelchair=(), person=None):
        """Fake inferences that note the frame index, and a stand-in detector that records the frame indices it is
        called on; wheelchair = frame indices on which its wheelchair box (= the person box) is there, elsewhere only
        the person box; person(k) = the person box of frame k (default PERSON). Returns (models, aids, called)."""
        import numpy as np
        from app.inference.aid import Aids
        outer, called = self, []
        empty = (np.zeros((0, 4)), np.zeros(0))

        class Clock(FakeModels):
            def infer(self, frame):
                self.k = frame.index
                return super().infer(frame)
        models = Clock(sched or [fake_inference() for _ in range(n)])

        def aids(img):
            called.append(models.k)
            box = np.array([outer.PERSON if person is None else person(models.k)])
            wc = (box, np.array([0.6])) if models.k in wheelchair else empty
            return Aids(box, np.array([0.6]), np.array([[0.1, 0, 0, 0, 0.6]]), outer.CLASSES,
                        (img.shape[1], img.shape[0]), {"infer": 0.0},
                        {"crutch": empty, "cane": empty, "walker": empty, "wheelchair": wc})
        return models, aids, called

    def start_live(self, confirm, n, at, heads=None, sched=None, wheelchair=(), person=None):
        """run_live on the fake camera with the touch entry; at = touch windows by frame; heads / sched = head boxes and
        fake inferences per frame (default: one user throughout); wheelchair, person: clocked_aids. Returns (records,
        meta, the frame indices on which the detector was called)."""
        from test_vision_links import entry, reporting, timed_frames
        from app.modules.vision.live import run_live
        models, aids, called = self.clocked_aids(n, sched, wheelchair, person)
        folder = tempfile.mkdtemp()
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        svc = entry(b=b)
        meta = run_live(reporting(timed_frames(n), svc, at), b, models=models,
                        detector=ScheduledHeads(heads or [[[0.38, 0.22, 0.62, 0.58]]] * n), aids=aids,
                        show_window=False, out_dir=folder, print_fn=lambda line: None, entry=svc, aid_confirm=confirm)
        with open(os.path.join(folder, "windows.jsonl"), encoding="utf-8") as f:
            return [json.loads(line) for line in f], meta, called

    @staticmethod
    def touch_at(last, taps=(), session=lambda k: "s1", first=1):
        """1 s touch windows (k - 1, k] for k = first .. last, sent at frame 10 k; taps = the k with one press."""
        from test_vision_links import window_body
        return {10 * k: [window_body(k - 1.0, float(k), tap=int(k in taps), session_id=session(k))]
                for k in range(first, last + 1)}

    def start_step(self, p=0.9, **flags):
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        return AidConfirm(self.Reader(p), 0.5, history_s(b) + b.chain.segment_s, **flags)

    @staticmethod
    def start_flags(rec):
        c = rec.get("aid_confirm") or {}
        return bool(c.get("start_off")), bool(c.get("start_judgment"))

    def test_start_only_switches_off_after_a_press_at_a_judged_false_window(self):
        """Through run_live, one session, an ordinary user (the engine answers no aid). Without a press nothing changes:
        the answers equal the plain confirm step's and the detector runs on every frame. With one press at 3 s the
        first window that answers no aid and whose span starts at or after the press (and after the chain's reset)
        switches the session off; the windows before it equal the plain step's, the ones after it answer false with
        start_off and no evidence, and the detector is not called on the frames after the switch."""
        n = 150
        plain, _, called_plain = self.start_live(self.start_step(), n, self.touch_at(14))
        self.assertEqual(called_plain, list(range(n)))
        recs, meta, called = self.start_live(self.start_step(start_only=True), n, self.touch_at(14))
        self.assertEqual([self.aid(r) for r in recs], [self.aid(r) for r in plain])
        self.assertFalse(any(self.start_flags(r) != (False, False) for r in recs))
        self.assertEqual((len(called), meta["aid_confirm"]["sessions_off"]), (n, 0))
        step = self.start_step(start_only=True)
        recs, meta, called = self.start_live(step, n, self.touch_at(14, taps={3}))
        k = next(i for i, r in enumerate(recs) if self.start_flags(r)[1])
        judgment = recs[k]
        window_s = bundle().situation.window_s
        self.assertGreaterEqual(judgment["t"] - window_s, 3.0 - 1e-6)
        self.assertGreaterEqual(judgment["t"] - window_s, step.reset[0] - 1e-6)
        self.assertEqual(self.aid(judgment), (False, None))
        self.assertEqual([self.aid(r) for r in recs[:k + 1]], [self.aid(r) for r in plain[:k + 1]])
        self.assertFalse(any(self.start_flags(r)[0] for r in recs[:k + 1]))
        after = recs[k + 1:]
        self.assertTrue(after)
        for r in after:
            tag = {t["name"]: t for t in r["situation"]["tags"]}["aid_use"]
            self.assertEqual((r["aid_confirm"], tag["status"], tag["evidence"]),
                             ({"confirmed": None, "start_off": True}, False, []), r["t"])
        self.assertLess(len(called), n)
        self.assertEqual(called, list(range(len(called))))       # every frame up to the switch, none after it
        # the switch comes from the release worker, so in live it lands on the frame that released the judgment window
        # or a later one (the exact frame is checked in the replay test, where windows are judged on the frame loop)
        self.assertGreaterEqual(called[-1], int(round(judgment["t"] / DT)))
        s = meta["aid_confirm"]
        self.assertEqual((s["start_only"], s["sessions_off"], s["windows_start_off"], s["frames_aid_skipped"]),
                         (True, 1, len(after), n - len(called)))

    def start_out(self, status, cls=None, reason=None):
        return {"tags": [{"name": "aid_use", "status": status, "unknown_reason": reason,
                          "evidence": [{"event_id": "aid_head@1", "obs": "aid_class", "value": cls, "t": 1.0}]}]}

    def start_rows(self, t_end, press=None):
        """One row per 0.1 s from 0 to t_end, with a press on the row at time press."""
        return [{"frame_idx": i, "t_s": round(i * DT, 6), "tap_count": int(press is not None
                                                                         and abs(i * DT - press) < 1e-6)}
                for i in range(int(round(t_end / DT)) + 1)]

    def judged_step(self, record):
        """A start-only step in session s1 from 0 s whose confirm check is replaced by a stand-in: an engine
        wheelchair window gets aid_use false and the given record (a withdrawal with its reason)."""
        step = self.start_step(start_only=True)
        step.new_start(0.0, "s1")

        def check(out, rows, t_end, sp, cp, images=None, *rest):
            tag = out["tags"][0]
            if tag["status"] is True and record is not None:
                tag["status"] = False
                return dict(record)
            return None
        step.check = check
        return step

    def test_start_only_needs_a_judged_answer(self):
        """An unknown window, and a wheelchair window withdrawn because of a reader error or of too few reader rows
        (or no main user box), make no start judgment, also after a press; a wheelchair window the reader read and
        did not agree with (reason median) does, and so does the engine's own no-aid answer."""
        from app.modules.vision.params import PilotParams
        sp, cp = sit_params(), PilotParams()
        rows = self.start_rows(12.0, press=3.0)
        step = self.judged_step(None)
        self.assertIsNone(step.check_start(self.start_out("unknown", reason="too_few_rows"), rows, 10.0, sp, cp,
                                           session="s1"))
        self.assertIsNone(step.off)
        for reason in ("reader_error", "too_few_rows", "no_main_user_box"):
            step = self.judged_step({"confirmed": False, "reason": reason})
            for t_end in (9.0, 10.0, 11.0):
                step.check_start(self.start_out(True, "wheelchair"), rows, t_end, sp, cp, session="s1")
            self.assertIsNone(step.off, reason)
        step = self.judged_step({"confirmed": False, "reason": "median"})
        r = step.check_start(self.start_out(True, "wheelchair"), rows, 9.0, sp, cp, session="s1")
        self.assertEqual((r["start_judgment"], step.off), (True, (1, "s1", 0.0)))
        step = self.judged_step(None)
        self.assertIsNone(step.check_start(self.start_out(False), rows, 8.9, sp, cp, session="s1"))  # before the press
        self.assertIsNone(step.off)
        r = step.check_start(self.start_out(False), rows, 9.0, sp, cp, session="s1")
        self.assertEqual((r, step.off), ({"confirmed": None, "start_judgment": True}, (1, "s1", 0.0)))

    def test_start_only_never_switches_off_a_session_with_an_aid_seen(self):
        """Through run_live: the user's wheelchair is held by the detector for the first 7 s and the reader agrees,
        then the engine answers no aid; a press at 3 s. The session is never switched off, though its later windows
        are false after the press. The same at the judge with a stick-class window."""
        from app.modules.vision.params import PilotParams
        n = 200
        recs, meta, called = self.start_live(self.start_step(start_only=True), n, self.touch_at(19, taps={3}),
                                             wheelchair=set(range(70)))
        self.assertIn((True, None), [self.aid(r) for r in recs])
        self.assertIn((False, None), [self.aid(r) for r in recs if r["t"] > 12.0])
        self.assertFalse(any(self.start_flags(r) != (False, False) for r in recs))
        self.assertEqual((len(called), meta["aid_confirm"]["sessions_off"]), (n, 0))
        sp, cp = sit_params(), PilotParams()
        rows = self.start_rows(14.0, press=3.0)
        step = self.judged_step(None)
        step.check_start(self.start_out(True, "crutch"), rows, 8.0, sp, cp, session="s1")
        for t_end in (9.0, 10.0, 11.0):
            self.assertIsNone(step.check_start(self.start_out(False), rows, t_end, sp, cp, session="s1"))
        self.assertIsNone(step.off)

    def test_start_only_turns_the_detector_on_again_in_the_next_session(self):
        """Through run_live: session s1 to 12 s with a press at 3 s (switched off), then s2 without a press. The
        detector is not called on s1's frames after the switch, and is called on every frame from s2's reset on; no s2
        window answers start_off, and s2's windows whose rows all come after its reset equal the plain step's."""
        n = 230
        at = self.touch_at(22, taps={3}, session=lambda k: "s1" if k <= 12 else "s2")
        plain, _, _ = self.start_live(self.start_step(), n, at)
        step = self.start_step(start_only=True)
        recs, meta, called = self.start_live(step, n, at)
        s1 = [r for r in recs if r["evaluated"]["session_id"] == "s1"]
        s2 = [r for r in recs if r["evaluated"]["session_id"] == "s2"]
        self.assertTrue(any(self.start_flags(r)[0] for r in s1))
        self.assertFalse(any(self.start_flags(r) != (False, False) for r in s2))
        self.assertEqual((step.reset[1], meta["aid_confirm"]["sessions_off"]), ("s2", 1))
        first_s2 = int(round(step.reset[0] / DT))
        self.assertEqual([k for k in called if k >= first_s2], list(range(first_s2, n)))
        self.assertTrue(set(range(100, 120)).isdisjoint(called))         # s1 frames after the switch
        window_s = bundle().situation.window_s
        same = {r["t"]: self.aid(r) for r in plain if r["t"] - window_s >= step.reset[0] - 1e-6}
        self.assertTrue(same)
        self.assertEqual({r["t"]: self.aid(r) for r in s2 if r["t"] in same}, same)

    def test_start_only_drops_a_late_off_for_an_earlier_session_or_user(self):
        """An OFF the judge publishes for a stretch the frame thread has already left (a new session, or a counted
        change of main user) is not applied: the detector keeps running. An OFF for the current stretch is."""
        step = self.start_step(start_only=True)
        step.new_start(1.0, "s1")
        old = step.start_from
        step.new_start(5.0, "s2")
        self.assertFalse(step.switch_off(old[2], "s1", old[0]))
        self.assertEqual((step.off, step.start_skip()), (None, False))
        step.row_change(self.change_row(5.5), "s2")
        self.assertEqual(step.start_from[:2], (5.5, "s2"))
        self.assertFalse(step.switch_off(old[2] + 1, "s2", 5.0))             # the stretch before the change row
        self.assertEqual((step.off, step.start_skip()), (None, False))
        now = step.start_from
        self.assertTrue(step.switch_off(now[2], "s2", now[0]))
        self.assertTrue(step.start_skip())
        self.assertEqual(step.frames_skipped, 1)

    def test_start_only_does_not_count_a_press_placed_before_the_chains_reset(self):
        """Through run_live: the session's first touch window (with the only press, at 1 s) comes during frame 15, so
        the chain resets at 1.5 s and the press lies on a row before it: no window switches off. A second press at
        6 s does, at a window whose span starts at or after the chain's reset."""
        n = 150
        at = {15: self.touch_at(1, taps={1})[10], **{k: v for k, v in self.touch_at(14).items() if k > 10}}
        step = self.start_step(start_only=True)
        recs, meta, called = self.start_live(step, n, at)
        self.assertAlmostEqual(step.reset[0], 1.5)
        self.assertEqual((len(called), meta["aid_confirm"]["sessions_off"]), (n, 0))
        at = {15: self.touch_at(1, taps={1})[10], **{k: v for k, v in self.touch_at(14, taps={6}).items() if k > 10}}
        step = self.start_step(start_only=True)
        recs, meta, _ = self.start_live(step, n, at)
        judgment = next(r for r in recs if self.start_flags(r)[1])
        self.assertGreaterEqual(judgment["t"] - bundle().situation.window_s, max(6.0, step.reset[0]) - 1e-6)

    def test_start_only_option_off_or_without_a_session_changes_nothing(self):
        """Without the option no record or meta carries a start-only key and the step is the plain one. With the
        option but without a session (replay without a touch log, live with the touch entry but no touch window) every
        answer, record and detector call equals the plain step's."""
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        b, _, _ = self.replay_fading(None)
        keep = history_s(b) + b.chain.segment_s
        _, plain, meta_plain = self.replay_fading(AidConfirm(self.Reader(0.1), 0.5, keep))
        for key in ("start_only", "sessions_off", "windows_start_off", "frames_aid_skipped"):
            self.assertNotIn(key, meta_plain["aid_confirm"])
        _, start, meta = self.replay_fading(AidConfirm(self.Reader(0.1), 0.5, keep, start_only=True))
        strip = lambda recs: [{k: v for k, v in r.items() if k != "ms_window"} for r in recs]   # noqa: E731
        self.assertEqual(strip(start), strip(plain))
        self.assertEqual((meta["aid_confirm"]["sessions_off"], meta["aid_confirm"]["frames_aid_skipped"]), (0, 0))
        self.assertTrue(all(not self.start_flags(r)[0] and not self.start_flags(r)[1] for r in start))
        recs, _, called = self.start_live(self.start_step(start_only=True), 120, {})
        plain_live, _, _ = self.start_live(self.start_step(), 120, {})
        self.assertEqual([(self.aid(r), r["aid_confirm"]) for r in recs],
                         [(self.aid(r), r["aid_confirm"]) for r in plain_live])
        self.assertEqual(len(called), 120)

    def test_start_only_option_needs_the_confirm_model_and_not_the_holds(self):
        import argparse
        from app.modules.vision.replay import add_aid_confirm_options, check_aid_confirm_options
        ap = argparse.ArgumentParser()
        ap.add_argument("--aid-model", default=None)
        add_aid_confirm_options(ap)
        path = os.path.join(tempfile.mkdtemp(), "reader.onnx")
        with open(path, "wb") as f:
            f.write(b"stand-in")
        self.assertFalse(ap.parse_args([]).aid_start_only)
        for argv, expected in ((["--aid-start-only"], ["--aid-start-only needs --aid-confirm-model"]),
                               (["--aid-confirm-model", path, "--aid-start-only", "--aid-confirm-hold"],
                                ["--aid-start-only cannot be combined with --aid-confirm-hold or "
                                 "--aid-confirm-hold-user"]),
                               (["--aid-confirm-model", path, "--aid-start-only", "--aid-confirm-hold-user"],
                                ["--aid-start-only cannot be combined with --aid-confirm-hold or "
                                 "--aid-confirm-hold-user"]),
                               (["--aid-confirm-model", path, "--aid-start-only"], [])):
            errors = []
            check_aid_confirm_options(errors.append, ap.parse_args(["--aid-model", "d.onnx"] + argv),
                                      "head_centre_carry")
            self.assertEqual(errors, expected, argv)

    @staticmethod
    def change_row(t, **flags):
        """A row whose change columns say the main user changed (track 1 to 2); flags override the change's flags."""
        return {"t_s": t, "primary_track": 2, "main_user_prev_track": 1,
                **{"main_user_reacquired": False, "main_user_prev_settled": True, "main_user_stitched": False,
                   **flags}}

    def test_start_only_starts_again_only_at_a_counted_change_of_user(self):
        """A change row that the engine does not count as a new user (the same user found again in place, a stitched
        break, or an earlier user who had not settled) leaves the stretch as it is; a counted one starts a new
        stretch at its row and clears an OFF for the frame thread."""
        step = self.start_step(start_only=True)
        step.new_start(1.0, "s1")
        self.assertTrue(step.switch_off(step.start_from[2], "s1", 1.0))
        for flags in ({"main_user_reacquired": True}, {"main_user_stitched": True},
                      {"main_user_prev_settled": False}):
            step.row_change(self.change_row(9.0, **flags), "s1")
            self.assertEqual(step.start_from[:2], (1.0, "s1"), flags)
            self.assertTrue(step.start_skip(), flags)
        step.row_change({"t_s": 9.0, "primary_track": 2, "main_user_prev_track": None}, "s1")
        self.assertTrue(step.start_skip())
        step.row_change(self.change_row(9.5), "s1")
        self.assertEqual(step.start_from[:2], (9.5, "s1"))
        self.assertFalse(step.start_skip())
        self.assertEqual(step.off_until, 9.5)

    def test_start_only_a_new_user_in_an_off_session_is_judged_again(self):
        """Through run_live, one session: user A (an ordinary user) for 10.5 s with a press at 3 s, nobody for 1.5 s,
        then user B elsewhere. The session is switched off for A; the chain's counted change of main user at B's
        first row turns the detector on again from that row, no later window answers start_off, and without a press
        after the change B is not switched off. With a press at 15 s B is switched off again, at a window whose
        span starts at or after both the change and that press."""
        n = 230
        heads = [[[0.38, 0.22, 0.62, 0.58]]] * 105 + [[]] * 15 + [[[0.05, 0.25, 0.25, 0.55]]] * (n - 120)
        sched = ([fake_inference() for _ in range(105)] + [fake_inference(face=False, body=False) for _ in range(15)]
                 + [fake_inference() for _ in range(n - 120)])
        window_s = bundle().situation.window_s
        for taps, offs in (({3}, 1), ({3, 15}, 2)):
            step = self.start_step(start_only=True)
            recs, meta, called = self.start_live(step, n, self.touch_at(22, taps=taps), heads=heads, sched=sched)
            change_t = step.start_from[0]
            self.assertEqual(step.start_from[2], 2, taps)                 # the session's start and the change
            self.assertGreaterEqual(change_t, 10.5 - 1e-6)
            first = int(round(change_t / DT))
            judgments = [r for r in recs if self.start_flags(r)[1]]
            self.assertEqual(meta["aid_confirm"]["sessions_off"], offs, taps)
            self.assertLess(judgments[0]["t"], change_t)
            self.assertTrue(any(self.start_flags(r)[0] for r in recs if r["t"] < change_t), taps)
            if offs == 1:
                self.assertFalse(any(self.start_flags(r)[0] for r in recs if r["t"] >= change_t), taps)
                self.assertEqual([k for k in called if k >= first], list(range(first, n)), taps)
            else:
                later = judgments[1]
                self.assertGreaterEqual(later["t"] - window_s, max(15.0, change_t) - 1e-6)
                self.assertFalse(any(self.start_flags(r)[0] for r in recs if change_t <= r["t"] <= later["t"]))
                self.assertTrue(all(self.start_flags(r)[0] for r in recs if r["t"] > later["t"]))
                self.assertIn(first, called)

    HEAD = [0.38, 0.22, 0.62, 0.58]
    PRESS = {"target": {"id": "product:1", "kind": "button", "disabled": False}}
    OPEN = [(-1000, "session_start", "menu", None), (-900, "screen_enter", "menu", None)]
    TO_S2 = [(12000, "session_end", "menu", {"reason": "server_session_change"}),
             (12050, "session_start", "menu", {"reason": "server_session_change"}, "s2"),
             (12050, "screen_enter", "menu", None, "s2")]

    def start_replay(self, confirm, n, events, wheelchair=()):
        """run_replay with a touch log of these events (touch_log; None = no touch log) and the clocked stand-in
        detector. Returns (records, meta, the frame indices the detector was called on, rows.csv as dicts)."""
        import csv
        from app.modules.vision.replay import run_replay
        from app.modules.vision.touch import load_timeline
        models, aids, called = self.clocked_aids(n, wheelchair=wheelchair)
        folder = tempfile.mkdtemp()
        video, out = os.path.join(folder, "take.mp4"), os.path.join(folder, "out")
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        timeline = None if events is None else load_timeline(touch_log(folder, events, video), video)
        meta = run_replay(frames(n), out, b, timeline=timeline, models=models,
                          detector=ScheduledHeads([[self.HEAD]] * n), aids=aids, session_id="t", aid_confirm=confirm)
        with open(os.path.join(out, "windows.jsonl"), encoding="utf-8") as f:
            recs = [json.loads(line) for line in f]
        with open(os.path.join(out, "rows.csv"), encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        return recs, meta, called, rows

    def test_start_only_in_replay_with_a_two_session_touch_log(self):
        """A replay whose touch log opens session s1 before the first frame, has a press at 3 s and changes to s2 at
        12.05 s. s1 (whose first row has no chain reset) is switched off at the 9 s window, the first whose span starts
        at the press; the detector runs on every frame up to the frame that released it and on none after it until
        s2's first row, from which it runs on every frame. s1's later windows answer start_off; s2's do not, and s2
        (no press) is not switched off. The windows up to the judgment equal the plain step's. The skipped rows keep
        every aid column in rows.csv, blank, with ms_aids blank."""
        from app.modules.vision.columns import AID_CARRY_COLUMNS, AID_COLUMNS, AID_HEAD_COLUMNS
        n = 230
        events = self.OPEN + [(3000, "pointer_start", "menu", self.PRESS)] + self.TO_S2
        plain, _, called_plain, _ = self.start_replay(self.start_step(), n, events)
        self.assertEqual(called_plain, list(range(n)))
        step = self.start_step(start_only=True)
        recs, meta, called, rows = self.start_replay(step, n, events)
        k = next(i for i, r in enumerate(recs) if self.start_flags(r)[1])
        self.assertEqual(recs[k]["t"], 9.0)
        self.assertEqual([self.aid(r) for r in recs[:k + 1]], [self.aid(r) for r in plain[:k + 1]])
        self.assertEqual(step.reset[1], "s2")
        first_s2 = int(round(step.reset[0] / DT))
        self.assertEqual(called, list(range(91)) + list(range(first_s2, n)))
        for r in recs[k + 1:]:
            self.assertEqual(self.start_flags(r), (r["t"] < step.reset[0], False), r["t"])
        self.assertTrue(any(self.start_flags(r)[0] for r in recs))
        s = meta["aid_confirm"]
        self.assertEqual((s["sessions_off"], s["frames_aid_skipped"]), (1, first_s2 - 91))
        skipped = set(range(91, first_s2))
        for name in AID_COLUMNS + AID_HEAD_COLUMNS + AID_CARRY_COLUMNS + ("ms_aids",):
            self.assertIn(name, rows[0])
        for row in rows:
            blank = {name: row[name] for name in AID_COLUMNS + AID_HEAD_COLUMNS + AID_CARRY_COLUMNS + ("ms_aids",)
                     if row[name] != ""}
            if int(row["frame_idx"]) in skipped:
                self.assertEqual(blank, {}, row["frame_idx"])
            else:
                self.assertIn("ms_aids", blank, row["frame_idx"])

    def test_start_only_in_replay_does_not_count_a_press_that_is_the_touch_logs_first_event(self):
        """A touch log whose first event is the press (no session-opening event before it): the touch log has no count
        for the stretch before its first event, so that press is never counted and nothing is switched off."""
        n = 150
        events = [(3000, "pointer_start", "menu", self.PRESS), (4000, "screen_enter", "review", {"from": "menu"})]
        recs, meta, called, _ = self.start_replay(self.start_step(start_only=True), n, events)
        self.assertEqual((meta["aid_confirm"]["sessions_off"], called), (0, list(range(n))))
        self.assertFalse(any(self.start_flags(r) != (False, False) for r in recs))

    def test_start_only_judges_through_the_real_confirm_check(self):
        """A replay of a user the detector reads as a wheelchair throughout, a press at 3 s. A reader that reads 0.1
        withdraws every window with the reason median, and the first one after the press is the judgment that switches
        the session off. A reader that fails withdraws them with reader_error, which is no judgment: nothing is
        switched off."""
        n = 150
        events = self.OPEN + [(3000, "pointer_start", "menu", self.PRESS)]
        recs, meta, called, _ = self.start_replay(self.start_step(0.1, start_only=True), n, events,
                                                  wheelchair=set(range(n)))
        judgment = next(r for r in recs if self.start_flags(r)[1])
        self.assertEqual((judgment["t"], judgment["aid_confirm"]["confirmed"], judgment["aid_confirm"]["reason"]),
                         (9.0, False, "median"))
        self.assertEqual((meta["aid_confirm"]["sessions_off"], called), (1, list(range(91))))

        class Failing(self.Reader):
            def probs(self, image):
                raise RuntimeError("stand-in reader failure")
        step = self.start_step(start_only=True)
        step.reader = Failing(0.9)
        step.log = lambda line: None
        recs, meta, called, _ = self.start_replay(step, n, events, wheelchair=set(range(n)))
        reasons = {r["aid_confirm"].get("reason") for r in recs if r["t"] >= 9.0}
        self.assertEqual(reasons, {"reader_error"})
        self.assertEqual((meta["aid_confirm"]["sessions_off"], called), (0, list(range(n))))

    def test_start_only_answers_a_wheelchair_newcomer_after_a_switched_off_stretch(self):
        """After an ordinary user's stretch was switched off, a wheelchair user who comes next is read again and
        answered true: in a replay as the next session (s2 from 12.05 s), and in live as a counted change of main user
        in the same session (user B elsewhere from 12 s, with a press at 15 s that does not switch B off)."""
        n = 230
        events = self.OPEN + [(3000, "pointer_start", "menu", self.PRESS)] + self.TO_S2
        step = self.start_step(start_only=True)
        recs, meta, called, _ = self.start_replay(step, n, events, wheelchair=set(range(121, n)))
        first_s2 = int(round(step.reset[0] / DT))
        self.assertEqual([k for k in called if k >= first_s2], list(range(first_s2, n)))
        s2 = [r for r in recs if r["t"] >= step.reset[0]]
        self.assertIn(((True, None), True), [(self.aid(r), r["aid_confirm"]["confirmed"]) for r in s2])
        self.assertEqual(meta["aid_confirm"]["sessions_off"], 1)
        heads = [[self.HEAD]] * 105 + [[]] * 15 + [[[0.05, 0.25, 0.25, 0.55]]] * (n - 120)
        sched = ([fake_inference() for _ in range(105)] + [fake_inference(face=False, body=False) for _ in range(15)]
                 + [fake_inference() for _ in range(n - 120)])
        step = self.start_step(start_only=True)
        recs, meta, called = self.start_live(step, n, self.touch_at(22, taps={3, 15}), heads=heads, sched=sched,
                                             wheelchair=set(range(120, n)),
                                             person=lambda k: self.PERSON if k < 120 else [0.0, 0.1, 0.32, 0.97])
        change_t = step.start_from[0]
        self.assertEqual(step.start_from[2], 2)
        first = int(round(change_t / DT))
        self.assertEqual([k for k in called if k >= first], list(range(first, n)))
        after = [r for r in recs if r["t"] >= change_t]
        self.assertIn(((True, None), True), [(self.aid(r), (r["aid_confirm"] or {}).get("confirmed")) for r in after])
        self.assertFalse(any(self.start_flags(r)[0] for r in after))
        self.assertEqual(meta["aid_confirm"]["sessions_off"], 1)

    def test_start_only_keeps_a_session_on_after_true_windows_that_cross_its_start(self):
        """Through run_live: the user's wheelchair is read for the first 3.5 s, so the windows answered true are the
        ones whose span starts before the session's start in the chain; a press at 2 s and no-aid windows after it.
        Those true windows end inside the session, so the session counts as one with an aid and is never switched
        off."""
        n = 160
        step = self.start_step(start_only=True)
        recs, meta, called = self.start_live(step, n, self.touch_at(15, taps={2}), wheelchair=set(range(35)))
        window_s = bundle().situation.window_s
        true = [r for r in recs if self.aid(r)[0] is True]
        self.assertTrue(true)
        self.assertTrue(all(r["t"] - window_s < step.start_from[0] <= r["t"] for r in true))
        self.assertIn((False, None), [self.aid(r) for r in recs if r["t"] - window_s >= 2.0])
        self.assertEqual((meta["aid_confirm"]["sessions_off"], called), (0, list(range(n))))

    def test_start_only_option_reaches_the_step_from_both_runners(self):
        """load_aid_confirm builds the step with start_only and says so at the start; replay.main and live.main pass
        --aid-start-only to it (off when not given)."""
        from contextlib import redirect_stdout
        from unittest import mock
        from app.modules.vision import live, replay
        path = os.path.join(tempfile.mkdtemp(), "stand_in.onnx")
        with open(path, "wb") as f:
            f.write(b"stand-in")

        class StandIn:
            def __init__(self, *args, **kwargs):
                self.classes, self.meta = self.CLASSES, {}
        StandIn.CLASSES = self.CLASSES
        lines = []
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        with mock.patch("app.inference.aid_confirm.AidConfirmReader", StandIn):
            step, _ = replay.load_aid_confirm([path], 0.5, b, 1, lines.append, start_only=True)
            plain, _ = replay.load_aid_confirm([path], 0.5, b, 1, lines.append)
        self.assertEqual((step.start_only, plain.start_only), (True, False))
        self.assertIn("--aid-start-only", lines[0])

        class Stop(Exception):
            pass
        aid = ["--aid-model", path, "--aid-rule", "head_centre_carry", "--aid-head-min", "0.5",
               "--aid-confirm-model", path]
        out = os.path.join(tempfile.mkdtemp(), "out")
        for module, argv in ((replay, ["--video", os.path.join(out, "take.mp4"), "--out", out, "--no-heads"]),
                             (live, ["--camera", "0", "--no-window", "--seconds", "1", "--no-heads"])):
            for given in (True, False):
                seen = mock.Mock(side_effect=Stop)
                with mock.patch("app.inference.aid.AidDetector", StandIn), \
                        mock.patch("app.modules.vision.sources.VideoFileSource"), \
                        mock.patch.object(module, "load_aid_confirm", seen), redirect_stdout(io.StringIO()):
                    with self.assertRaises(Stop):
                        module.main(argv + aid + (["--aid-start-only"] if given else []))
                self.assertIs(seen.call_args.args[-1], given, (module.__name__, given))

    # --- --aid-stick-model (aid_confirm.py, 'Stick at the start') -----------------------------------------------------
    class BoxReader:
        """A stand-in confirm reader whose crop image carries the box's left edge in pixels (so a stick reader can
        tell the users apart) or, with by_frame, the frame's first pixel value (so it can tell the rows apart)."""

        def __init__(self, by_frame=False):
            import numpy as np
            self.p, self.ms, self.by_frame = np.array([0.9, 0.0, 0.0, 0.0, 0.1]), [], by_frame

        def crop(self, bgr, box_px):
            import numpy as np
            return np.full((8, 8, 3), int(bgr[0, 0, 0]) if self.by_frame else int(box_px[0]) % 256, np.uint8)

        def probs(self, image):
            self.ms.append(0.0)
            return self.p

    class StickReader:
        """A stand-in stick file: reads a stick (P(cane) 0.7) on the crops whose first value is in marks, otherwise
        P(crutch) 0.3 and P(cane) 0.3 (their sum is above 0.5, their maximum is not); counts its reads."""

        def __init__(self, marks):
            self.marks, self.calls = set(marks), 0

        def probs(self, image):
            import numpy as np
            self.calls += 1
            if int(image[0, 0, 0]) in self.marks:
                return np.array([0.2, 0.1, 0.7, 0.0, 0.0])
            return np.array([0.4, 0.3, 0.3, 0.0, 0.0])

    def stick_step(self, marks, n_min=2):
        from app.modules.vision.aid_confirm import AidConfirm
        stick = self.StickReader(marks)
        step = AidConfirm(self.BoxReader(by_frame=True), 0.5, 100.0, start_only=True, stick=[stick], stick_min=n_min,
                          stick_row_min=0.5)
        return step, stick

    def feed(self, step, ks, wheel=()):
        """add_row for the rows k (time k / 10 s, the main user's head box, frame value k); the rows in wheel are read
        by the detector as a wheelchair above the cut."""
        import numpy as np
        for k in ks:
            img = np.full((10, 10, 3), k % 256, np.uint8)
            row = {"frame_idx": k, "t_s": round(k * DT, 6), "primary_box": (0.4, 0.2, 0.6, 0.4),
                   "aid_head_class": "wheelchair" if k in wheel else None, "aid_head_score": 0.9 if k in wheel else 0.0}
            step.add_row(row, img, self.aids(img))

    def stick_check(self, step, t_end, press=3.0, out=None):
        from app.modules.vision.params import PilotParams
        out = out or self.start_out(False)
        rec = step.check_start(out, self.start_rows(t_end + 2.0, press=press), t_end, sit_params(), PilotParams(),
                               session="s1")
        return out["tags"][0], rec

    def test_stick_answers_cane_with_its_evidence_and_holds_without_reading(self):
        """Two stick rows (one before the press, one after it) give the cane answer at the first window after the
        press: aid_use true, evidence aid_head@<frame> aid_class cane, the record's stick fields; the stretch is not
        switched off, and later windows answer the same without further reads."""
        step, stick = self.stick_step({10, 50})
        step.new_start(0.0, "s1")
        self.feed(step, range(91))
        tag, rec = self.stick_check(step, 9.0)
        self.assertEqual((tag["status"], tag["unknown_reason"]), (True, None))
        self.assertEqual(tag["evidence"], [{"event_id": "aid_head@90", "obs": "aid_class", "value": "cane", "t": 9.0}])
        self.assertEqual(rec, {"confirmed": None, "stick": True, "stick_frames": 2, "stick_min": 2})
        self.assertIsNone(step.off)
        calls = stick.calls
        self.feed(step, range(91, 120))
        tag, rec = self.stick_check(step, 11.0)
        self.assertEqual((tag["status"], rec["stick"], stick.calls), (True, True, calls))
        s = step.summary()["stick"]
        self.assertEqual((s["stick_frames"], s["windows_answered"], s["users_answered"], s["stick_frame_t"]),
                         (2, 2, 1, [1.0, 5.0]))

    def test_stick_needs_its_count_and_the_maximum_of_the_two_classes(self):
        """One stick row (N - 1) gives no answer, and the start judgment switches the stretch off as before; rows whose
        P(crutch) + P(cane) is above 0.5 but whose maximum is not are no stick rows."""
        step, _ = self.stick_step({10})
        step.new_start(0.0, "s1")
        self.feed(step, range(91))
        tag, rec = self.stick_check(step, 9.0)
        self.assertEqual((tag["status"], rec), (False, {"confirmed": None, "start_judgment": True}))
        self.assertEqual(step.off, (1, "s1", 0.0))
        self.assertEqual(step.summary()["stick"]["per_user"], {"0": 1})   # the walk-in key carried into s1

    def test_stick_is_never_answered_for_a_wheelchair(self):
        """A window the reader agreed is a wheelchair keeps its answer and its user never gets the stick answer. A
        detector wheelchair row stops the count: stick rows after it never count, and stick rows before it (fewer
        than N) are cleared."""
        step, _ = self.stick_step({10, 50, 60})
        step.new_start(0.0, "s1")
        step.check = lambda out, *rest, **kw: {"confirmed": True}
        self.feed(step, range(91))
        tag, rec = self.stick_check(step, 8.0, out=self.start_out(True, "wheelchair"))
        self.assertEqual((tag["status"], tag["evidence"][0]["value"], rec), (True, "wheelchair", {"confirmed": True}))
        step.check = lambda out, *rest, **kw: None
        tag, rec = self.stick_check(step, 9.0)
        self.assertEqual((tag["status"], rec), (False, None))
        for wheel, marks in ((5, {20, 21, 30}), (25, {10, 30, 31, 40})):
            step, stick = self.stick_step(marks)
            step.new_start(0.0, "s1")
            self.feed(step, range(91), wheel={wheel})
            tag, rec = self.stick_check(step, 9.0)
            self.assertEqual((tag["status"], rec.get("stick")), (False, None), wheel)
            self.assertEqual(stick.calls, wheel, wheel)                     # no read from the wheelchair row on
            self.assertEqual(step.summary()["stick"]["per_user"], {"0": 0}, wheel)

    def test_stick_count_starts_again_per_user_and_keeps_the_walk_in(self):
        """A counted change of main user starts a new count. The rows before the first session (the walk-in) and a
        stretch started by a counted change carry into the next session; a session's own stretch does not."""
        step, _ = self.stick_step({10, 60})
        step.new_start(0.0, "s1")
        self.feed(step, range(50))
        step.row_change({**self.change_row(5.0), "frame_idx": 50}, "s1")
        self.feed(step, range(50, 131))
        tag, rec = self.stick_check(step, 13.0, press=6.0)
        self.assertEqual((tag["status"], (rec or {}).get("stick")), (False, None))
        step, _ = self.stick_step({60, 61})
        step.new_start(0.0, "s1")
        self.feed(step, range(50))
        step.row_change({**self.change_row(5.0), "frame_idx": 50}, "s1")
        self.feed(step, range(50, 131))
        self.assertTrue(self.stick_check(step, 13.0, press=6.0)[1]["stick"])
        for first, carried in (("walk_in", True), ("user", True), ("session", False)):
            step, _ = self.stick_step({5, 6})
            if first == "user":
                step.new_start(0.0, "s0")
                step.row_change({**self.change_row(0.05), "frame_idx": 0}, "s0")
            elif first == "session":
                step.new_start(0.0, "s0")
            self.feed(step, range(10))
            step.new_start(1.0, "s1")
            self.feed(step, range(10, 91))
            tag, _ = self.stick_check(step, 9.0)
            self.assertEqual(tag["status"] is True, carried, first)

    def test_stick_option_off_or_never_stick_changes_nothing(self):
        """A replay with a stick file that never reads a stick gives the same windows and detector calls as the step
        without it, and its meta differs only by the 'stick' block (and the read times); a file that reads every crop
        as a stick answers cane, and the session is never switched off."""
        n = 150
        events = self.OPEN + [(3000, "pointer_start", "menu", self.PRESS)]
        strip = lambda recs: [{k: v for k, v in r.items() if k != "ms_window"} for r in recs]   # noqa: E731
        plain, meta_plain, called_plain, _ = self.start_replay(self.start_step(start_only=True), n, events)
        step = self.start_step(start_only=True)
        step.stick, step.stick_min, step.stick_row_min = [self.StickReader(set())], 2, 0.5
        never, meta, called, _ = self.start_replay(step, n, events)
        self.assertEqual(strip(never), strip(plain))
        self.assertEqual(called, called_plain)
        stick = meta["aid_confirm"].pop("stick")
        self.assertEqual(stick["stick_frames"], 0)
        for m in (meta, meta_plain):
            for k in ("ms_read_p50", "ms_read_max"):
                m["aid_confirm"].pop(k)
        self.assertEqual(meta["aid_confirm"], meta_plain["aid_confirm"])
        step = self.start_step(start_only=True)
        step.stick, step.stick_min, step.stick_row_min = [self.StickReader({0})], 2, 0.5
        recs, meta, called, _ = self.start_replay(step, n, events)
        self.assertTrue(all(self.aid(r) == (True, None) for r in recs if r["t"] >= 6.0))
        first = next(r for r in recs if (r["aid_confirm"] or {}).get("stick"))
        tag = {t["name"]: t for t in first["situation"]["tags"]}["aid_use"]
        self.assertEqual(tag["evidence"][0]["value"], "cane")
        self.assertEqual((meta["aid_confirm"]["sessions_off"], called), (0, list(range(n))))

    def test_stick_newcomer_after_a_switched_off_user_is_read_on_arrival(self):
        """Through run_live, one session: user A (no stick) with a press at 3 s is switched off; A leaves, and user B,
        whose crops read as a stick, walks in at 12 s without pressing. The engine's counted change of main user
        turns the detector and the crop on again from B's first row, B's rows are read on the reader thread, and B is
        answered aid_use true with the class cane."""
        from app.modules.vision.aid_confirm import AidConfirm
        from app.modules.vision.chain import history_s
        n = 230
        heads = [[self.HEAD]] * 105 + [[]] * 15 + [[[0.05, 0.25, 0.25, 0.55]]] * (n - 120)
        sched = ([fake_inference() for _ in range(105)] + [fake_inference(face=False, body=False) for _ in range(15)]
                 + [fake_inference() for _ in range(n - 120)])
        b = bundle(aid_rule="head_centre_carry", aid_head_min=0.5)
        stick = self.StickReader({0})                       # B's box starts at the frame's left edge
        step = AidConfirm(self.BoxReader(), 0.5, history_s(b) + b.chain.segment_s, start_only=True, stick=[stick],
                          stick_min=2, stick_row_min=0.5)
        recs, meta, called = self.start_live(step, n, self.touch_at(22, taps={3}), heads=heads, sched=sched,
                                             person=lambda k: self.PERSON if k < 120 else [0.0, 0.1, 0.32, 0.97])
        change_t = step.start_from[0]
        self.assertGreaterEqual(change_t, 10.5 - 1e-6)
        first = int(round(change_t / DT))
        self.assertEqual([k for k in called if k >= first], list(range(first, n)))
        self.assertEqual(meta["aid_confirm"]["sessions_off"], 1)
        self.assertFalse(any(self.aid(r)[0] is True for r in recs if r["t"] < change_t))
        answered = [r for r in recs if (r["aid_confirm"] or {}).get("stick")]
        self.assertTrue(answered)
        self.assertGreaterEqual(answered[0]["t"], change_t)
        tag = {t["name"]: t for t in answered[0]["situation"]["tags"]}["aid_use"]
        self.assertEqual((tag["status"], tag["evidence"][0]["value"]), (True, "cane"))
        self.assertGreaterEqual(meta["aid_confirm"]["stick"]["stick_frames"], 2)

    def test_stick_options_need_the_start_option_and_both_values(self):
        import argparse
        from app.modules.vision.replay import add_aid_confirm_options, check_aid_confirm_options, stick_kwargs
        ap = argparse.ArgumentParser()
        ap.add_argument("--aid-model", default=None)
        add_aid_confirm_options(ap)
        path = os.path.join(tempfile.mkdtemp(), "reader.onnx")
        with open(path, "wb") as f:
            f.write(b"stand-in")
        a = ap.parse_args([])
        self.assertEqual((a.aid_stick_model, a.aid_stick_frames, stick_kwargs(a)), (None, None, {}))
        base = ["--aid-model", "d.onnx", "--aid-confirm-model", path]
        for argv, expected in ((["--aid-start-only", "--aid-stick-model", path], "go together"),
                               (["--aid-start-only", "--aid-stick-frames", "2"], "go together"),
                               (["--aid-stick-model", path, "--aid-stick-frames", "2"], "--aid-start-only"),
                               (["--aid-start-only", "--aid-stick-model", path, "--aid-stick-frames", "0"],
                                "at least 1"),
                               (["--aid-start-only", "--aid-stick-model", path + ".x", "--aid-stick-frames", "2"],
                                "no file")):
            errors = []
            check_aid_confirm_options(errors.append, ap.parse_args(base + argv), "head_centre_carry")
            self.assertTrue(errors and expected in errors[0], (argv, errors))
        errors = []
        a = ap.parse_args(base + ["--aid-start-only", "--aid-stick-model", path, path, "--aid-stick-frames", "2"])
        check_aid_confirm_options(errors.append, a, "head_centre_carry")
        self.assertEqual((errors, stick_kwargs(a)), ([], {"stick_paths": [path, path], "stick_frames": 2}))


if __name__ == "__main__":
    unittest.main()
