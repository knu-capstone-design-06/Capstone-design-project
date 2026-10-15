"""추론 (inference) layer: MediaPipe model loading and per-frame inference only.

Runs the three MediaPipe Tasks models in VIDEO mode on one frame and returns their outputs as plain arrays
(FrameInference) with the time each step took. No observation is computed here - app/modules/vision/features.py
does that. This file lives in app/inference/ as AGENTS.md asks (app/inference/ holds the loading and inference code
of the models the server runs itself); app/modules/vision/inference.py re-exports these names for the module.

Source shorthands used in the comments:
  doc 28 = the vision owner's design note 28_mediapipe_limits_and_reach.md (sections 0-8), kept in the project
           workspace (01_requirements/research/), not in this repository
  [D1] Face Landmarker docs  https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker
  [D2] Face Detector docs    https://ai.google.dev/edge/mediapipe/solutions/vision/face_detector
  [D3] Pose Landmarker docs  https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker
"""
from __future__ import annotations

import os
import platform
import time
from dataclasses import dataclass, field

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mpp
from mediapipe.tasks.python import vision as V

# --- model files (models/download_models.py fetches them; sources and licence: models/README.md) -----------
FACE_LANDMARKER_MODEL = "face_landmarker.task"          # the Face Landmarker bundle [D1]
FACE_DETECTOR_MODELS = {                                # Face Detector variants [D2]
    "short_range": "blaze_face_short_range.tflite",     # default; the variant the Face Landmarker bundle also uses
    "full_range": "blaze_face_full_range.tflite",       # for small / distant faces; needs mediapipe >= 0.10.33
}                                                       # (doc 28 section 1, note 3; it failed to run on 0.10.21)
FACE_DETECTOR_MODEL = FACE_DETECTOR_MODELS["short_range"]
POSE_LANDMARKER_MODEL = "pose_landmarker_lite.task"     # lite = the variant in doc 28's section 4-1 table and team bench


@dataclass
class FrameInference:
    """The models' outputs for one frame as plain data - what features.py reads.

    face_points: (N, 2) landmarks of the first face, x and y as fractions of width / height [D1]; None = no face
    face_matrix: 4x4 facial transformation matrix of that face [D1]; None when the model gave none
    detections:  (origin_x, origin_y, width, height, score) per face the detector found, box in px [D2]
    pose:        (33, 4) x, y (fractions), visibility, presence of the first pose [D3]; None = no body;
                 a value the library left empty is NaN
    ms:          ms_prep, ms_face_lm, ms_face_det, ms_pose - each model time includes turning its output into arrays
    """
    face_points: np.ndarray | None
    face_matrix: np.ndarray | None
    detections: list
    pose: np.ndarray | None
    ms: dict = field(default_factory=dict)


class MediaPipeModels:
    """The three MediaPipe Tasks models in VIDEO mode (frames in order, so the landmarkers track)."""

    def __init__(self, model_dir: str, face_detector: str = "short_range"):
        self.face_detector_model = FACE_DETECTOR_MODELS[face_detector]

        paths = {}
        for name in (FACE_LANDMARKER_MODEL, self.face_detector_model, POSE_LANDMARKER_MODEL):
            p = os.path.join(model_dir, name)
            if not os.path.isfile(p):
                raise FileNotFoundError(f"model file missing: {p} (python app/modules/vision/models/download_models.py)")
            paths[name] = p   # all three checked before any model is created, so a missing file leaves none open

        self.face_lm = V.FaceLandmarker.create_from_options(V.FaceLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=paths[FACE_LANDMARKER_MODEL]),
            running_mode=V.RunningMode.VIDEO,             # frames in order -> tracking (doc 28 section 0)
            num_faces=1,                                  # smoothing only with num_faces=1 [D1] (doc 28 sections 1, 4-4)
            output_face_blendshapes=False,                # no observation uses blendshapes
            output_facial_transformation_matrixes=True))  # head direction (doc 28 sections 2, 3)
        # min_face_detection / min_face_presence / min_tracking confidence: library default 0.5 [D1] -
        # a library pass mark, not our criterion (doc 28 section 0).
        self.face_det = V.FaceDetector.create_from_options(V.FaceDetectorOptions(
            base_options=mpp.BaseOptions(model_asset_path=paths[self.face_detector_model]),
            running_mode=V.RunningMode.VIDEO))
        # min_detection_confidence 0.5 and min_suppression_threshold 0.3: library defaults [D2].
        # The detector counts faces and gives the face detection score (doc 28 section 3, '사람 수' and
        # '입력 품질' rows) while the landmarker stays at num_faces=1 so its smoothing stays on.
        self.pose = V.PoseLandmarker.create_from_options(V.PoseLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=paths[POSE_LANDMARKER_MODEL]),
            running_mode=V.RunningMode.VIDEO,
            num_poses=1))                                 # library default 1 [D3]; body = fallback presence cue
        # min_pose_detection / presence / tracking confidence: library default 0.5 [D3].
        self.last_ts = -1

    def close(self):
        for task in (self.face_lm, self.face_det, self.pose):
            task.close()

    def _timestamp_ms(self, t_s: float) -> int:
        # MediaPipe VIDEO mode needs strictly increasing integer timestamps in ms (API requirement).
        ts = int(round(t_s * 1000.0))
        if ts <= self.last_ts:
            ts = self.last_ts + 1
        self.last_ts = ts
        return ts

    def infer(self, frame) -> FrameInference:
        """Run the three models on one Frame (sources.Frame: .image BGR, .t_s seconds)."""
        ms = {}
        t = time.perf_counter()
        rgb = cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB)
        mimg = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts = self._timestamp_ms(frame.t_s)
        ms["ms_prep"] = (time.perf_counter() - t) * 1000.0

        t = time.perf_counter()
        r_face = self.face_lm.detect_for_video(mimg, ts)
        face_points = face_matrix = None
        if r_face.face_landmarks:
            face_points = np.array([[p.x, p.y] for p in r_face.face_landmarks[0]], dtype=np.float64)
            if r_face.facial_transformation_matrixes:
                face_matrix = np.asarray(r_face.facial_transformation_matrixes[0], dtype=np.float64)
        ms["ms_face_lm"] = (time.perf_counter() - t) * 1000.0

        t = time.perf_counter()
        r_det = self.face_det.detect_for_video(mimg, ts)
        detections = [(d.bounding_box.origin_x, d.bounding_box.origin_y, d.bounding_box.width,
                       d.bounding_box.height, float(d.categories[0].score)) for d in r_det.detections]
        ms["ms_face_det"] = (time.perf_counter() - t) * 1000.0

        t = time.perf_counter()
        r_pose = self.pose.detect_for_video(mimg, ts)
        pose = None
        if r_pose.pose_landmarks:
            pose = np.array([[p.x, p.y, np.nan if p.visibility is None else p.visibility,
                              np.nan if p.presence is None else p.presence] for p in r_pose.pose_landmarks[0]],
                            dtype=np.float64)
        ms["ms_pose"] = (time.perf_counter() - t) * 1000.0
        return FrameInference(face_points, face_matrix, detections, pose, ms)


def _cpu_name() -> str:
    try:   # Windows: the marketing name of the CPU from the registry
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
    except Exception:
        return ""


def environment() -> dict:
    """Versions and machine facts for meta.json."""
    return {
        "python": platform.python_version(),
        "mediapipe": mp.__version__,
        "opencv": cv2.__version__,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_name": _cpu_name(),
        "cpu_count": os.cpu_count(),
        "delegate": "CPU (no delegate set in BaseOptions; Windows Python builds are CPU-only, doc 28 section 6)",
    }
