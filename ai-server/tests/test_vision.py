"""Vision module (app/modules/vision): the observation layers on inputs made here - no photos, videos or runs/.

- features layer on fake inference outputs: needs numpy and OpenCV only (no MediaPipe, no model files)
- inference + features on blank frames: also needs mediapipe and the model files
  (python app/modules/vision/models/download_models.py)
Tests whose packages or files are missing are skipped, so the server tests still run with ai-server/requirements.txt.
"""

import importlib.util
import math
import os
import subprocess
import sys
import unittest

AI_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(AI_SERVER_DIR, "app", "modules", "vision", "models")
HAS_NUMPY_CV2 = all(importlib.util.find_spec(m) is not None for m in ("numpy", "cv2"))
HAS_MEDIAPIPE = HAS_NUMPY_CV2 and importlib.util.find_spec("mediapipe") is not None
SKIP_REASON = "vision packages not installed (pip install -r app/modules/vision/requirements.txt)"


def _fake_face(eye_gap):
    """478 face points at the centre; the eye corners put the two eye centres eye_gap (fraction of the width) apart."""
    import numpy as np

    pts = np.full((478, 2), 0.5)
    half = eye_gap / 2
    pts[33], pts[133] = (0.5 - half - 0.02, 0.4), (0.5 - half + 0.02, 0.4)
    pts[362], pts[263] = (0.5 + half - 0.02, 0.4), (0.5 + half + 0.02, 0.4)
    return pts


@unittest.skipUnless(HAS_NUMPY_CV2, SKIP_REASON)
class FeaturesOnFakeInferenceTests(unittest.TestCase):
    def test_features_layer_runs_on_fake_inference_outputs_without_mediapipe(self):
        from types import SimpleNamespace

        import numpy as np

        from app.modules.vision.features import NOT_SEEN, SEEN, Observer
        from app.modules.vision.sources import Frame

        # importing the features layer loads no MediaPipe (checked in a fresh interpreter)
        code = "import sys, app.modules.vision.features; print('mediapipe' in sys.modules)"
        out = subprocess.run([sys.executable, "-c", code], cwd=AI_SERVER_DIR, capture_output=True, text=True,
                             check=True).stdout.strip()
        self.assertEqual(out, "False")

        width, height = 640, 480

        def face(eye_gap):
            # 478 face points at the centre; the eye corners put the two eye centres eye_gap (fraction of the width)
            # apart at y = 0.4 -> face box x 0.5 -+ (eye_gap / 2 + 0.02), y 0.4 .. 0.5
            pts = np.full((478, 2), 0.5)
            half = eye_gap / 2
            pts[33], pts[133] = (0.5 - half - 0.02, 0.4), (0.5 - half + 0.02, 0.4)
            pts[362], pts[263] = (0.5 + half - 0.02, 0.4), (0.5 + half + 0.02, 0.4)
            return pts

        pose = np.zeros((33, 4))
        pose[:, 2], pose[:, 3] = 0.8, 0.6               # visibility, presence of every pose point
        ms = {"ms_prep": 0.0, "ms_face_lm": 0.0, "ms_face_det": 0.0, "ms_pose": 0.0}
        outputs = [   # same attributes as inference.FrameInference
            SimpleNamespace(face_points=face(0.10), face_matrix=np.eye(4), detections=[(256, 144, 128, 128, 0.9)],
                            pose=pose, ms=ms),
            SimpleNamespace(face_points=face(0.15), face_matrix=np.eye(4), detections=[], pose=pose, ms=ms),
            SimpleNamespace(face_points=None, face_matrix=None, detections=[], pose=None, ms=ms),
        ]

        class FakeModels:   # stands in for inference.MediaPipeModels
            def infer(self, frame):
                return outputs[frame.index]

        observer = Observer(FakeModels())
        image = np.full((height, width, 3), 100, np.uint8)
        r0, r1, r2 = [observer.process(Frame(i, i * 0.5, image, str(i), 0.0))[0] for i in range(3)]

        self.assertEqual((r0["face_state"], r0["body_state"]), (SEEN, SEEN))
        self.assertAlmostEqual(r0["iod_px"], 0.10 * width)
        self.assertAlmostEqual(r0["iod_ratio_start"], 1.0)
        self.assertAlmostEqual(r1["iod_ratio_start"], 1.5)          # 0.15 / 0.10
        self.assertAlmostEqual(r1["iod_step"], 1.5)
        self.assertAlmostEqual(r0["face_cx"], 0.5)
        self.assertAlmostEqual(r0["face_cy"], 0.45)
        self.assertAlmostEqual(r0["face_y_max"], 0.5)
        self.assertEqual((r0["yaw_deg"], r0["pitch_deg"], r0["roll_deg"]), (0.0, 0.0, 0.0))
        self.assertEqual(r0["face_count"], 1)
        self.assertAlmostEqual(r0["face_det_score"], 0.9)
        self.assertAlmostEqual(r0["det_box_w_frac"], 128 / width)
        self.assertEqual((r0["face_run_id"], r1["face_run_id"]), (1, 1))
        self.assertAlmostEqual(r1["face_run_s"], 0.5)
        self.assertAlmostEqual(r0["pose_vis_mean"], 0.8)
        self.assertAlmostEqual(r0["pose_pres_mean"], 0.6)
        self.assertAlmostEqual(r0["pose_vis_shoulders"], 0.8)
        self.assertEqual((r2["face_state"], r2["body_state"]), (NOT_SEEN, NOT_SEEN))
        self.assertEqual(r2["face_run_s"], 0.0)
        self.assertAlmostEqual(r2["face_unseen_s"], 0.5)            # since the last face frame at 0.5 s
        self.assertTrue(math.isnan(r2["iod_px"]))
        self.assertEqual(r0["bright_frame"], 100.0)                 # uniform grey image
        self.assertEqual(r0["lapvar_frame"], 0.0)
        self.assertEqual(r0["bright_face"], 100.0)
        self.assertGreaterEqual(r0["ms_total"], r0["ms_features"])

    def test_eye_distance_ratios_are_blank_when_the_reference_distance_is_zero(self):
        from types import SimpleNamespace

        import numpy as np

        from app.modules.vision.features import SEEN, Observer
        from app.modules.vision.sources import Frame

        ms = {"ms_prep": 0.0, "ms_face_lm": 0.0, "ms_face_det": 0.0, "ms_pose": 0.0}
        outputs = [   # first face with the two eye centres at the same point (distance 0), then a normal face
            SimpleNamespace(face_points=_fake_face(0.0), face_matrix=np.eye(4), detections=[], pose=None, ms=ms),
            SimpleNamespace(face_points=_fake_face(0.10), face_matrix=np.eye(4), detections=[], pose=None, ms=ms),
        ]

        class FakeModels:
            def infer(self, frame):
                return outputs[frame.index]

        observer = Observer(FakeModels())
        image = np.full((480, 640, 3), 100, np.uint8)
        r0, r1 = [observer.process(Frame(i, i * 0.5, image, str(i), 0.0))[0] for i in range(2)]
        self.assertEqual(r0["iod_px"], 0.0)
        self.assertTrue(math.isnan(r0["iod_ratio_start"]))       # 0 / 0 has no meaning: blank, not an error
        self.assertTrue(math.isnan(r1["iod_ratio_start"]))       # the session reference distance is 0
        self.assertTrue(math.isnan(r1["iod_step"]))
        self.assertEqual((r0["face_state"], r1["face_state"]), (SEEN, SEEN))   # the other observations go on
        self.assertAlmostEqual(r1["face_cx"], 0.5)


@unittest.skipUnless(HAS_MEDIAPIPE, SKIP_REASON)
class InferenceOnBlankFramesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np

        from app.modules.vision.features import COLUMNS, NOT_SEEN, Observer
        from app.inference.vision import (FACE_DETECTOR_MODEL, FACE_LANDMARKER_MODEL, POSE_LANDMARKER_MODEL,
                                                  MediaPipeModels)
        from app.modules.vision.sources import Frame

        missing = [m for m in (FACE_LANDMARKER_MODEL, FACE_DETECTOR_MODEL, POSE_LANDMARKER_MODEL)
                   if not os.path.isfile(os.path.join(MODEL_DIR, m))]
        if missing:
            raise unittest.SkipTest(f"model files missing {missing}: run app/modules/vision/models/download_models.py")
        # 640x480 BGR frames, black and mid grey in turn, 10 frames per second: nothing in them to find
        frames = [Frame(i, i / 10.0, np.full((480, 640, 3), 128 if i % 2 else 0, np.uint8), str(i), 0.0)
                  for i in range(4)]
        models = MediaPipeModels(MODEL_DIR)
        try:
            observer = Observer(models)
            cls.rows = [observer.process(frame, source_kind="합성")[0] for frame in frames]
        finally:
            models.close()
        cls.columns, cls.not_seen = COLUMNS, NOT_SEEN

    def test_rows_have_the_csv_columns_in_order(self):
        for row in self.rows:
            self.assertEqual(list(row.keys()), self.columns)

    def test_blank_frames_are_not_seen_and_face_values_stay_blank(self):
        for row in self.rows:
            self.assertEqual(row["face_state"], self.not_seen)
            self.assertEqual(row["body_state"], self.not_seen)
            self.assertEqual(row["face_count"], 0)
            self.assertTrue(math.isnan(row["iod_px"]))
            self.assertTrue(math.isnan(row["yaw_deg"]))

    def test_unseen_time_counts_from_the_session_start(self):
        t0 = self.rows[0]["t_s"]
        for row in self.rows:
            self.assertEqual(row["face_run_s"], 0.0)
            self.assertAlmostEqual(row["face_unseen_s"], row["t_s"] - t0)
            self.assertAlmostEqual(row["body_unseen_s"], row["t_s"] - t0)

    def test_stage_times_are_recorded_and_the_total_covers_them(self):
        stages = ("ms_prep", "ms_face_lm", "ms_face_det", "ms_pose", "ms_features", "ms_quality")
        for row in self.rows:
            values = [row[k] for k in stages]
            self.assertTrue(all(v >= 0.0 for v in values))
            self.assertGreaterEqual(row["ms_total"], max(values))


@unittest.skipUnless(HAS_NUMPY_CV2, SKIP_REASON)
class VisionHelperTests(unittest.TestCase):
    def test_continuity_numbers_runs_and_measures_gaps(self):
        from app.modules.vision.features import Continuity

        continuity = Continuity()
        out = [continuity.update(t, seen) for t, seen in
               ((0.0, True), (0.1, True), (0.2, False), (0.3, False), (0.4, True))]
        self.assertEqual([o[0] for o in out if not math.isnan(o[0])], [1, 1, 2])   # a new run after the gap
        self.assertAlmostEqual(out[1][1], 0.1)                                      # run length so far
        self.assertEqual(out[2][1], 0.0)                                            # no current run while not seen
        self.assertAlmostEqual(out[3][2], 0.2)                                      # since the last seen frame
        self.assertEqual(out[4][1], 0.0)                                            # the new run starts at 0 s

    def test_head_angles_of_pure_rotations(self):
        import cv2
        import numpy as np

        from app.modules.vision.features import head_angles_deg

        # rotation about x -> pitch (index 1), about y -> yaw (index 0), about z -> roll (index 2)
        for axis, index in ((0, 1), (1, 0), (2, 2)):
            rvec = np.zeros(3)
            rvec[axis] = math.radians(10.0)
            matrix = np.eye(4)
            matrix[:3, :3] = cv2.Rodrigues(rvec)[0]
            angles = head_angles_deg(matrix)
            self.assertAlmostEqual(abs(angles[index]), 10.0)
            for other in {0, 1, 2} - {index}:
                self.assertAlmostEqual(angles[other], 0.0)

    def test_effective_fps_is_one_over_the_mean_frame_interval(self):
        from app.modules.vision.sources import effective_fps

        self.assertAlmostEqual(effective_fps([0.0, 0.05, 0.10, 0.15]), 20.0)
        self.assertIsNone(effective_fps([0.0]))
        self.assertIsNone(effective_fps([1.0, 1.0]))


@unittest.skipUnless(HAS_NUMPY_CV2, SKIP_REASON)
class SidecarTimesTests(unittest.TestCase):
    """Frame times of a recorded clip come from <clip>.times.csv only when that file is complete and in order."""

    def _clip_with_sidecar(self, *lines):
        import tempfile

        from app.modules.vision.sources import TIMES_SUFFIX

        clip = os.path.join(tempfile.mkdtemp(), "clip.mp4")   # read_times opens the sidecar only
        with open(clip + TIMES_SUFFIX, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines) + "\n")
        return clip

    def test_complete_sidecar_gives_the_times_in_frame_order(self):
        import tempfile

        from app.modules.vision.sources import read_times

        clip = self._clip_with_sidecar("frame,t_s", "0,0.0", "1,0.05", "2,0.1")
        self.assertEqual(read_times(clip), [0.0, 0.05, 0.1])
        self.assertIsNone(read_times(os.path.join(tempfile.mkdtemp(), "no_sidecar.mp4")))

    def test_incomplete_or_disordered_sidecar_is_refused(self):
        from app.modules.vision.sources import read_times

        for lines in (("frame,t_s",),                          # header only
                      ("frame,t_s", "0,0.0", "2,0.1"),         # frame 1 missing
                      ("frame,t_s", "0,0.0", "1,-0.1"),        # time goes backwards
                      ("frame,t_s", "0,0.0", "1,nan"),         # not a finite time
                      ("t,x", "0,0.0")):                       # wrong columns
            with self.assertRaises(ValueError, msg=repr(lines)):
                read_times(self._clip_with_sidecar(*lines))

    def test_video_frame_beyond_the_sidecar_is_an_error(self):
        from app.modules.vision.sources import VideoFileSource

        src = VideoFileSource.__new__(VideoFileSource)   # no video file is opened
        src.path, src.src_fps, src.times = "clip.mp4", 30.0, [0.0, 0.05]
        self.assertEqual(src._t(1), 0.05)
        with self.assertRaises(ValueError):
            src._t(2)
        src.times = None
        self.assertAlmostEqual(src._t(3), 0.1)             # no sidecar: index / container fps


if __name__ == "__main__":
    unittest.main()
