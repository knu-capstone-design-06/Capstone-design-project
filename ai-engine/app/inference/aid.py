"""Walking-aid detector (YOLOX-Nano, person-level classes: pedestrian, crutch, cane, walker, wheelchair) with ONNX
Runtime, CPU only. An optional input of the vision chain: it runs only when its ONNX file is given (replay.py / live.py
--aid-model); the weights are never in this repository (vision README, '보조기구 입력').

Each box is one person, and its class says how that person moves (with no aid = pedestrian). The steps are the H1
ones (head.py: letterbox, grid decode, greedy NMS; YOLOX 6ddff48, Apache-2.0) with the class scores kept: every box
carries objectness x class score for all classes, its score is the largest of them, and boxes below score_min are
dropped before one NMS over all classes (one box per person). The export's metadata names the classes, the input size,
the licence and the attribution text; the class list is read from it.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import numpy as np

from .head import DEFAULT_STRIDES, grid_and_strides, letterbox, nms

STANDING_AIDS = ("crutch", "cane", "walker")   # aids a person stands and walks with: the route to scene 1-1
WHEELCHAIR = "wheelchair"                       # the route to scene 1-2
AID_CLASSES = STANDING_AIDS + (WHEELCHAIR,)     # 'the person uses an assistive device' (the owner's decision, 2026-11-22)
NO_AID = "pedestrian"


@dataclass
class Aids:
    """Person boxes of one frame. boxes: (n, 4) x0 y0 x1 y1 as fractions of the frame; scores: (n,) best class score;
    class_scores: (n, len(classes)) objectness x class score; classes: the model's class names."""
    boxes: np.ndarray
    scores: np.ndarray
    class_scores: np.ndarray
    classes: tuple
    frame_wh: tuple
    ms: dict = field(default_factory=dict)

    def __len__(self):
        return len(self.scores)


def decode_classes(raw: np.ndarray, grid: np.ndarray, strides: np.ndarray) -> tuple:
    """Raw head output (A, 5 + classes) -> (boxes in input pixels (A, 4), class scores (A, classes))."""
    xy = (raw[:, :2] + grid) * strides
    wh = np.exp(raw[:, 2:4]) * strides
    boxes = np.concatenate([xy - wh / 2.0, xy + wh / 2.0], axis=1)
    return boxes, raw[:, 4:5] * raw[:, 5:]


class AidDetector:
    """Person boxes with walking-aid class scores of a BGR frame: detector(frame) -> Aids."""

    def __init__(self, model_path: str, score_min: float, nms_iou: float, threads: int = 1, session=None):
        if session is None:
            import onnxruntime as ort
            so = ort.SessionOptions()
            so.intra_op_num_threads = int(threads)
            so.inter_op_num_threads = 1
            so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            session = ort.InferenceSession(model_path, sess_options=so, providers=["CPUExecutionProvider"])
        self.session = session
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.size_hw = (int(inp.shape[2]), int(inp.shape[3]))
        self.meta = dict(self.session.get_modelmeta().custom_metadata_map)
        if "classes" not in self.meta:
            raise ValueError(f"{model_path}: the export carries no class list")
        self.classes = tuple(json.loads(self.meta["classes"]))
        missing = [c for c in (NO_AID,) + AID_CLASSES if c not in self.classes]
        if missing:
            raise ValueError(f"{model_path}: classes {self.classes} lack {missing}")
        strides = tuple(int(s) for s in self.meta["strides"].split(",")) if "strides" in self.meta else DEFAULT_STRIDES
        self.grid, self.strides = grid_and_strides(self.size_hw, strides)
        per_anchor = self.session.get_outputs()[0].shape[-1]
        if isinstance(per_anchor, int) and per_anchor != 5 + len(self.classes):
            raise ValueError(f"{model_path}: output has {per_anchor} values per anchor, expected {5 + len(self.classes)}")
        # a symbolic output shape passes the check above: one blank input checks the real shape before the first frame
        raw = self.session.run(None, {self.input_name: np.zeros((1, 3) + self.size_hw, np.float32)})[0]
        if raw.shape[-2:] != (self.grid.shape[0], 5 + len(self.classes)):
            raise ValueError(f"{model_path}: output shape {raw.shape}, expected (1, {self.grid.shape[0]}, "
                             f"{5 + len(self.classes)}) for the classes {self.classes}")
        self.score_min, self.nms_iou = float(score_min), float(nms_iou)

    def __call__(self, bgr: np.ndarray) -> Aids:
        H, W = bgr.shape[:2]
        t0 = time.perf_counter()
        x, r = letterbox(bgr, self.size_hw)
        t1 = time.perf_counter()
        raw = self.session.run(None, {self.input_name: x[None]})[0][0]
        t2 = time.perf_counter()
        if raw.shape[0] != self.grid.shape[0]:
            raise ValueError(f"aid output has {raw.shape[0]} anchors, expected {self.grid.shape[0]}")
        boxes, cls = decode_classes(raw.astype(np.float32), self.grid, self.strides)
        scores = cls.max(axis=1)
        kept = scores >= self.score_min
        boxes, scores, cls = boxes[kept], scores[kept], cls[kept]
        order = nms(boxes, scores, self.nms_iou) if len(scores) else []
        boxes_px = boxes[order] / r
        boxes_px[:, [0, 2]] = boxes_px[:, [0, 2]].clip(0, W)
        boxes_px[:, [1, 3]] = boxes_px[:, [1, 3]].clip(0, H)
        frac = boxes_px / np.array([W, H, W, H], dtype=np.float64)
        t3 = time.perf_counter()
        return Aids(frac.astype(np.float64), scores[order].astype(np.float64), cls[order].astype(np.float64),
                    self.classes, (W, H), {"pre": (t1 - t0) * 1e3, "infer": (t2 - t1) * 1e3, "post": (t3 - t2) * 1e3})
