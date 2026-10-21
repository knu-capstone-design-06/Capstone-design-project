"""P1 head-direction classifier (torchvision ResNet-18, 5 classes, trained from random initial weights on AI Hub 70 head
crops) with ONNX Runtime, CPU only: the probability of each direction class for a head box.

Crop and input exactly as P1 was trained and evaluated (4_vision/gpu_runs/p1_head_direction_70/code: p1_common.py
square_crop and CROP_*, 01_prepare_crops.py, p1_data.transforms(False), 03_eval.py softmax; the same steps as
kiosk_inputs_2026-10-22/code/extract_kiosk_features.py head_crop / directions):
  crop    a square of CROP_SCALE (1.5) x the long side of the head box, same centre, grey 127 outside the frame, taken
          from the full-resolution frame
  resize  to CROP_SIDE (64) px: cv2.INTER_AREA when shrinking, cv2.INTER_LINEAR when enlarging
  colour  BGR -> RGB (P1 read its images as RGB)
  eval    Resize(64) (no change on a 64-px crop), CenterCrop(56) = rows / columns 4..59, float / 255,
          Normalize(mean (0.485, 0.456, 0.406), std (0.229, 0.224, 0.225)) - the torchvision classification reference's
          numbers (no ImageNet weights were used)
  output  softmax over the classes in the model's order: 중간 · 위 · 좌 · 우 · 뒤. The labels are AI Hub 70's '촬영방향'
          (the direction the camera looks at the person from), not the person's gaze.
The crop constants are read from the ONNX metadata that tools/export_onnx.py writes from the checkpoint and checked
against the values above. Known limit (P1 README): on its test split the class 뒤 had a recall of 30.2 %.
"""
from __future__ import annotations

import json
import time

import numpy as np

DIR_CLASSES = ("중간", "위", "좌", "우", "뒤")   # P1 model_final.pt "classes" (p1_common.DEFAULT_CLASSES)
DIR_KEYS = ("middle", "up", "left", "right", "back")   # column suffixes, same order (p1_common.GAZE2KO, reversed)
CROP_SCALE = 1.5     # p1_common.CROP_SCALE (also stored in model_final.pt)
CROP_SIDE = 64       # p1_common.CROP_SIDE (also stored in model_final.pt)
CROP_IN = 56         # p1_common.CROP_IN = 64 x 224 / 256
GREY = 127           # p1_common.GREY
MEAN = np.array((0.485, 0.456, 0.406), np.float32)   # p1_common.MEAN (torchvision presets.py)
STD = np.array((0.229, 0.224, 0.225), np.float32)    # p1_common.STD


def square_crop(img: np.ndarray, box_px, scale: float = CROP_SCALE) -> tuple:
    """p1_common.square_crop: (crop uint8 S x S x 3, side S, whether any pixel of the image is inside)."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = (float(v) for v in box_px)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    S = max(1, int(round(scale * max(x1 - x0, y1 - y0))))
    X0, Y0 = int(round(cx - S / 2.0)), int(round(cy - S / 2.0))
    canvas = np.full((S, S, 3), GREY, np.uint8)
    ix0, iy0, ix1, iy1 = max(X0, 0), max(Y0, 0), min(X0 + S, W), min(Y0 + S, H)
    inside = ix1 > ix0 and iy1 > iy0
    if inside:
        canvas[iy0 - Y0:iy1 - Y0, ix0 - X0:ix1 - X0] = img[iy0:iy1, ix0:ix1]
    return canvas, S, inside


def head_crop(bgr: np.ndarray, box_px) -> np.ndarray:
    """P1's 64-px RGB crop of one head box (01_prepare_crops.py; extract_kiosk_features.head_crop)."""
    import cv2   # imported here so the constants of this module load without OpenCV (columns.py uses them)
    crop, S, _ = square_crop(bgr, box_px)
    small = cv2.resize(crop, (CROP_SIDE, CROP_SIDE), interpolation=cv2.INTER_AREA if S > CROP_SIDE else cv2.INTER_LINEAR)
    return cv2.cvtColor(small, cv2.COLOR_BGR2RGB)


def to_input(crops_rgb: np.ndarray) -> np.ndarray:
    """N x 64 x 64 x 3 uint8 RGB -> N x 3 x 56 x 56 float32: CenterCrop(56), / 255, Normalize (p1_data eval)."""
    off = int(round((CROP_SIDE - CROP_IN) / 2.0))   # torchvision center_crop offset: 4
    x = crops_rgb[:, off:off + CROP_IN, off:off + CROP_IN].astype(np.float32) / 255.0
    x = (x - MEAN) / STD
    return np.ascontiguousarray(x.transpose(0, 3, 1, 2), dtype=np.float32)


def softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


class HeadDirection:
    """Direction probabilities of head boxes: model.probs(frame, boxes_px) -> (n, 5) in DIR_CLASSES order."""

    def __init__(self, model_path: str, threads: int = 1):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(threads)
        so.inter_op_num_threads = 1
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(model_path, sess_options=so, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        meta = dict(self.session.get_modelmeta().custom_metadata_map)
        self.meta = meta
        classes = tuple(json.loads(meta["classes"])) if "classes" in meta else DIR_CLASSES
        if classes != DIR_CLASSES:
            raise ValueError(f"{model_path}: classes {classes} differ from {DIR_CLASSES}")
        for key, expected in (("crop_scale", CROP_SCALE), ("crop_side", CROP_SIDE), ("crop_in", CROP_IN)):
            if key in meta and float(meta[key]) != float(expected):
                raise ValueError(f"{model_path}: {key} {meta[key]} differs from {expected} (the crop would not match)")
        self.threads = int(threads)
        self.last_ms = {}

    def probs(self, bgr: np.ndarray, boxes_px) -> np.ndarray:
        boxes_px = np.asarray(boxes_px, dtype=np.float64).reshape(-1, 4)
        if not len(boxes_px):
            self.last_ms = {"crop": 0.0, "infer": 0.0}
            return np.zeros((0, len(DIR_CLASSES)), np.float64)
        t0 = time.perf_counter()
        x = to_input(np.stack([head_crop(bgr, b) for b in boxes_px]))
        t1 = time.perf_counter()
        logits = self.session.run(None, {self.input_name: x})[0]
        t2 = time.perf_counter()
        self.last_ms = {"crop": (t1 - t0) * 1e3, "infer": (t2 - t1) * 1e3}
        return softmax(logits.astype(np.float64))
