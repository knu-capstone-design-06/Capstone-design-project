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
        A reacquisition in the same place keeps the reference; without the head detector nobody seen for longer than
        max_gap_s starts it again; before the first press (collect False) nothing is read."""
        from app.modules.vision.columns import PitchRef, add_pitch_user
        ref = PitchRef(max_gap_s=1.0)

        def row(track, pitch, **kw):
            return {"face_state": SEEN, "pitch_deg": pitch, "primary_track": track, **kw}
        self.assertEqual([ref.update(row(1, p)) for p in (-15.0, -15.0, 0.0)], [0.0, 0.0, 15.0])
        self.assertEqual([ref.update(row(2, p)) for p in (10.0, 10.0, 40.0)], [0.0, 0.0, 30.0])   # B's own first face
        self.assertEqual(ref.update(row(3, 30.0, main_user_reacquired="True")), 20.0)        # B found again
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
        """A phone box meeting the main user's head box is 'head' unless another head box overlaps it more; one meeting
        a box spanned by a hand's pose points of the main user (its nose in the head box) is 'hand'; a phone elsewhere
        is 'no'; without the head box, or with someone else's pose (or no finite hand point) and a phone not at the
        head, it cannot be told."""
        import numpy as np
        from app.inference.phone import Phones
        from app.modules.vision.columns import phone_columns

        def phones(*boxes):
            return Phones(np.array(boxes, float).reshape(-1, 4), np.array([0.5 + 0.1 * i for i in range(len(boxes))]),
                          (100, 100))
        head = (0.40, 0.10, 0.60, 0.30)
        pose = np.full((33, 4), np.nan)
        pose[0, :2] = (0.50, 0.20)                                # nose in the head box: the main user's pose
        for k, xy in zip((15, 17, 19, 21), ((0.30, 0.60), (0.28, 0.58), (0.29, 0.56), (0.32, 0.57))):
            pose[k, :2] = xy                                      # the left hand around (0.30, 0.58)
        ear = (0.58, 0.15, 0.66, 0.28)                            # beside the head, overlapping its edge
        held = (0.31, 0.50, 0.40, 0.57)                           # touching the hand box
        away = (0.80, 0.80, 0.90, 0.90)
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
        with both paths the cues name both."""
        def phone(name="none", tags=True):
            return {**sit(name), "tags": [{"name": "phone_use", "status": tags}]}
        (d,), _ = self.run_windows([win(situation=phone("looking_back_with_people_behind"), screen="menu",
                                        steps_left=2)])
        self.assertEqual((d.transition, d.scene, d.cues), ("open", "3-2", {"tag": "looking_back_with_people_behind",
                                                                         "path": "phone_use"}))
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
        wait (hold_timer) and nothing else: with the wait refused, a 9-s pause after choosing opens no 4-2 there; a
        true scene tag other than phone_use changes nothing."""
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
        (d4,), _ = self.run_windows([win(20.0, measurable=True, situation=phone(), **pause)], state)
        self.assertEqual((d4.transition, d4.scene), ("open", "4-2"))         # measurable: the 4-2 row runs
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
        self.assertIsNone(away(rows_of(facing(3)), None))                                  # no situation values

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

    def test_the_phone_input_opens_the_3_2_wait_through_the_phone_path(self):
        """The phone input is off by default (columns absent, phone_use unknown); with it, a phone in the main user's
        hand in every segment while the user looks away from the screen, no touch and the body still make phone_use
        true, and the rule table opens the 3-2 wait through that path. A touch in the window rules the path out, and so
        does facing the screen. Looking down at the phone loses the face while the head box stays: away from the
        screen, the wait opens; without the head box as well the direction cannot be told (unknown). A phone at the
        head (a call) needs no direction, and its window is measurable with the face lost: the wait opens and keeps its
        hold_timer there (the window stays not measurable for every other row)."""
        import numpy as np
        from app.inference.phone import Phones
        from app.modules.vision.chain import FrameChain, WindowJudge
        from app.modules.vision.columns import PHONE_COLUMNS
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
        chain = FrameChain(FakeModels([inference() for _ in range(60)]), PilotParams(phone_every=5), FakeHeads(),
                           phones=fake_phones)
        rows = [chain.process(f) for f in frames(60)]
        self.assertEqual((rows[55]["phone_owner"], rows[55]["phone_at"]), ("yes", "hand"))   # phone_every 5: 0, 5, ...
        self.assertGreaterEqual(rows[55]["ms_phones"], 0.0)
        self.assertEqual(({rows[k]["phone_owner"] for k in (56, 57, 58, 59)}, rows[59]["ms_phones"]), ({None}, None))
        every = FrameChain(FakeModels([inference() for _ in range(3)]), PilotParams(phone_every=1), FakeHeads(),
                           phones=fake_phones)
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

        def run(schedule, phones=fake_phones):
            chain = FrameChain(FakeModels(schedule), PilotParams(), FakeHeads(), phones=phones)
            return quiet([chain.process(f) for f in frames(len(schedule))])
        facing = run([inference(yaw=0.0) for _ in range(60)])     # holding the phone while reading the screen
        rec = WindowJudge(bundle()).evaluate(facing, 5.9)
        self.assertEqual((phone_tag(rec), rec["decision"]["support"]), ((False, None), None))
        lost = run([inference(face=k < 45) for k in range(60)])  # looking down: the face lost from 4.5 s, head kept
        rec = WindowJudge(bundle()).evaluate(lost, 5.9)
        self.assertEqual((phone_tag(rec), rec["decision"]["support"]), ((True, None), "wait_hold_timer"))
        chain = FrameChain(FakeModels([inference(face=k < 45) for k in range(60)]), PilotParams(),
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
        rec = WindowJudge(bundle()).evaluate(on_call, 5.9)       # no face in the last segment (4.9, 5.9]
        self.assertEqual((phone_tag(rec), rec["measurable"]), ((True, None), False))   # placeholder: not measurable
        self.assertEqual((rec["decision"]["support"], rec["decision"]["transition"]), ("wait_hold_timer", "open"))
        self.assertIn("phone_use", rec["contract"]["extension"]["measurement"]["basis"])
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
        b = bundle()
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

    def test_load_aids_is_off_without_a_file_and_names_a_missing_one(self):
        from app.modules.vision.params import PilotParams
        from app.modules.vision.replay import load_aids
        self.assertEqual(load_aids(None, PilotParams(), 1, print), (None, {}))
        with self.assertRaises(FileNotFoundError):
            load_aids(os.path.join(tempfile.mkdtemp(), "missing.onnx"), PilotParams(), 1, print)

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
        sched = [fake_inference(face=False, body=True) for _ in range(30)]
        _, recs, _ = self.run_replay(sched)
        self.assertTrue(all(r["measurable"] is False for r in recs))      # no tap, no back, no face
        self.assertTrue(all(r["contract"]["extension"]["measurement"]["measurable"] is False for r in recs))
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


if __name__ == "__main__":
    unittest.main()
