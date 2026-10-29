"""H1 head detector (YOLOX-Nano, one class 'head', trained on Open Images V7 'Human head') with ONNX Runtime, CPU only.

The steps are the ones H1's evaluation and E3b ran (YOLOX commit 6ddff48; 4_vision/gpu_runs/h1_openimages_head):
  pre    letterbox to the model input (416 x 416): resize with the aspect ratio kept (cv2.INTER_LINEAR), the image at
         the top-left, pad value 114, HWC -> CHW, float32, BGR order, no normalisation
         (yolox/data/data_augment.py preproc; ValTransform(legacy=False))
  infer  onnxruntime on the CPUExecutionProvider; intra-op threads = `threads` (default 1)
  post   grid decode of the raw head output (yolox/utils/demo_utils.py demo_postprocess, strides 8 / 16 / 32: the
         model was exported with decode_in_inference False, as YOLOX's exporter does by default), score = objectness x
         class score, keep score >= score_min, greedy NMS with the IoU of torchvision.ops.nms (box widths without the
         +1 of demo_utils, i.e. the IoU of yolox/utils/boxes.py postprocess), boxes / resize ratio, clipped to the
         frame, then fractions of the frame width / height.
Filtering at score_min before the NMS gives the same boxes as YOLOX's order (floor, NMS, then the operating point):
a greedy NMS only lets a box be removed by a box with a higher score.

preproc, the grid decode and the NMS below are adapted from YOLOX (Apache-2.0; "Copyright (c) 2021-2022 Megvii Inc.
All rights reserved."). Changed: numpy only, one image, NMS IoU without the +1. Notice rules: LICENSE_REGISTER.md 5-5.

score_min / nms_iou come from params.PilotParams (head_score_min: the F1-best score of H1 on its Open Images validation
set at input 416, E3b; head_nms_iou: YOLOX's nmsthre). Neither was measured on the kiosk view.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

PAD_VALUE = 114                  # YOLOX preproc: np.ones(...) * 114
DEFAULT_STRIDES = (8, 16, 32)    # YOLOX demo_postprocess (p6 False): the three heads of YOLOPAFPN


@dataclass
class Heads:
    """Head boxes of one frame, highest score first."""
    boxes: np.ndarray        # (n, 4) x0, y0, x1, y1 as fractions of the frame width / height
    scores: np.ndarray       # (n,) objectness x class score, 0..1
    boxes_px: np.ndarray     # (n, 4) the same boxes in frame pixels
    frame_wh: tuple          # (width, height) of the frame
    ms: dict = field(default_factory=dict)   # pre / infer / post milliseconds

    def __len__(self):
        return len(self.scores)


def letterbox(img: np.ndarray, size_hw: tuple) -> tuple:
    """YOLOX preproc for one BGR image: (CHW float32 input, resize ratio r)."""
    h, w = img.shape[:2]
    r = min(size_hw[0] / h, size_hw[1] / w)
    resized = cv2.resize(img, (int(w * r), int(h * r)), interpolation=cv2.INTER_LINEAR).astype(np.uint8)
    padded = np.full((size_hw[0], size_hw[1], 3), PAD_VALUE, np.uint8)
    padded[:resized.shape[0], :resized.shape[1]] = resized
    return np.ascontiguousarray(padded.transpose(2, 0, 1), dtype=np.float32), r


def grid_and_strides(size_hw: tuple, strides=DEFAULT_STRIDES) -> tuple:
    """(grid (A, 2), stride per anchor (A, 1)) in the anchor order of YOLOX's head output."""
    grids, expanded = [], []
    for s in strides:
        hs, ws = size_hw[0] // s, size_hw[1] // s
        xv, yv = np.meshgrid(np.arange(ws), np.arange(hs))
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        expanded.append(np.full((hs * ws, 1), s))
    return np.concatenate(grids).astype(np.float32), np.concatenate(expanded).astype(np.float32)


def nms(boxes: np.ndarray, scores: np.ndarray, iou_max: float) -> list:
    """Greedy NMS, highest score first; a box goes when its IoU with a kept box is above iou_max (torchvision.ops.nms
    semantics: widths x1 - x0 without +1)."""
    x0, y0, x1, y1 = boxes.T
    areas = (x1 - x0) * (y1 - y0)
    order = scores.argsort(kind="stable")[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        rest = order[1:]
        w = np.maximum(0.0, np.minimum(x1[i], x1[rest]) - np.maximum(x0[i], x0[rest]))
        h = np.maximum(0.0, np.minimum(y1[i], y1[rest]) - np.maximum(y0[i], y0[rest]))
        inter = w * h
        union = areas[i] + areas[rest] - inter
        iou = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
        order = rest[iou <= iou_max]
    return keep


def decode(raw: np.ndarray, grid: np.ndarray, strides: np.ndarray) -> tuple:
    """Raw head output (A, 5 + classes) -> (boxes x0 y0 x1 y1 in input pixels (A, 4), scores (A,))."""
    xy = (raw[:, :2] + grid) * strides
    wh = np.exp(raw[:, 2:4]) * strides
    boxes = np.concatenate([xy - wh / 2.0, xy + wh / 2.0], axis=1)
    scores = raw[:, 4] * raw[:, 5:].max(axis=1)   # one class: objectness x 'head'
    return boxes, scores


class HeadDetector:
    """H1 head boxes of a BGR frame: detector(frame) -> Heads."""

    def __init__(self, model_path: str, score_min: float, nms_iou: float, threads: int = 1):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(threads)
        so.inter_op_num_threads = 1
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(model_path, sess_options=so, providers=["CPUExecutionProvider"])
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.size_hw = (int(inp.shape[2]), int(inp.shape[3]))
        meta = self.session.get_modelmeta().custom_metadata_map
        self.meta = dict(meta)
        self.classes = json.loads(meta["classes"]) if "classes" in meta else ["head"]
        if self.classes != ["head"]:
            raise ValueError(f"{model_path}: expected the one class ['head'], the model says {self.classes}")
        if meta.get("decode_in_inference", "false") != "false":
            raise ValueError(f"{model_path}: exported with decode_in_inference; this code decodes the raw output")
        strides = tuple(int(s) for s in meta["strides"].split(",")) if "strides" in meta else DEFAULT_STRIDES
        self.grid, self.strides = grid_and_strides(self.size_hw, strides)
        per_anchor = self.session.get_outputs()[0].shape[-1]
        if isinstance(per_anchor, int) and per_anchor != 4 + 1 + len(self.classes):
            raise ValueError(f"{model_path}: output has {per_anchor} values per anchor, expected 6 (box, obj, head)")
        self.score_min, self.nms_iou, self.threads = float(score_min), float(nms_iou), int(threads)

    def __call__(self, bgr: np.ndarray) -> Heads:
        H, W = bgr.shape[:2]
        t0 = time.perf_counter()
        x, r = letterbox(bgr, self.size_hw)
        t1 = time.perf_counter()
        raw = self.session.run(None, {self.input_name: x[None]})[0][0]
        t2 = time.perf_counter()
        if raw.shape[0] != self.grid.shape[0]:
            raise ValueError(f"head output has {raw.shape[0]} anchors, expected {self.grid.shape[0]}")
        boxes, scores = decode(raw.astype(np.float32), self.grid, self.strides)
        kept = scores >= self.score_min
        boxes, scores = boxes[kept], scores[kept]
        order = nms(boxes, scores, self.nms_iou) if len(scores) else []
        boxes_px = boxes[order] / r
        boxes_px[:, [0, 2]] = boxes_px[:, [0, 2]].clip(0, W)
        boxes_px[:, [1, 3]] = boxes_px[:, [1, 3]].clip(0, H)
        frac = boxes_px / np.array([W, H, W, H], dtype=np.float64)
        t3 = time.perf_counter()
        return Heads(frac.astype(np.float64), scores[order].astype(np.float64), boxes_px.astype(np.float64), (W, H),
                     {"pre": (t1 - t0) * 1e3, "infer": (t2 - t1) * 1e3, "post": (t3 - t2) * 1e3})
