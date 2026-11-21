"""Phone detector: the COCO-pretrained YOLOX-Nano of the YOLOX release (yolox_nano.onnx, release 0.1.1rc0, input 416,
80 COCO classes) with ONNX Runtime, CPU only, keeping the class 'cell phone'. An optional input of the vision chain: it
runs only when its ONNX file is given (replay.py / live.py --phone-model); the weights are never in this repository
(vision README, '휴대폰 입력').

The steps are the ones of YOLOX's ONNX Runtime demo (commit 6ddff48, demo/ONNXRuntime/onnx_inference.py with
yolox/utils/demo_utils.py; Apache-2.0, "Copyright (c) 2021-2022 Megvii Inc. All rights reserved."):
  pre    the H1 letterbox (head.py: resize with the aspect ratio kept, pad 114, BGR, no normalisation = yolox preproc)
  infer  onnxruntime on the CPUExecutionProvider; intra-op threads = `threads` (default 1)
  post   the grid decode (demo_postprocess; the released file outputs the raw head, 5 + 80 values per anchor), score =
         objectness x class score, each box takes its best class (multiclass_nms_class_agnostic: argmax), boxes below
         score_min are dropped, one class-agnostic greedy NMS (IoU of head.nms, without the demo's +1 pixel), then only
         the 'cell phone' boxes are kept, as fractions of the frame.
Filtering at score_min before the NMS gives the boxes the demo shows (it runs the NMS on boxes above 0.1 and draws
those at or above its --score_thr): a greedy NMS only lets a box be removed by a box with a higher score.
score_min / nms_iou come from params.PilotParams (phone_score_min, phone_nms_iou: the demo's values). Neither was
measured on the kiosk view.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .aid import decode_classes
from .head import grid_and_strides, letterbox, nms

# yolox/data/datasets/coco_classes.py (commit 6ddff48): the 80 class names in the order of the model's class scores
COCO_CLASSES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant",
    "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli",
    "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant", "bed", "dining table", "toilet",
    "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
)
PHONE = "cell phone"


@dataclass
class Phones:
    """'cell phone' boxes of one frame, highest score first. boxes: (n, 4) x0 y0 x1 y1 as fractions of the frame;
    scores: (n,) objectness x 'cell phone' score."""
    boxes: np.ndarray
    scores: np.ndarray
    frame_wh: tuple
    ms: dict = field(default_factory=dict)

    def __len__(self):
        return len(self.scores)


class PhoneDetector:
    """'cell phone' boxes of a BGR frame: detector(frame) -> Phones."""

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
        self.grid, self.strides = grid_and_strides(self.size_hw)
        per_anchor = self.session.get_outputs()[0].shape[-1]
        if isinstance(per_anchor, int) and per_anchor != 5 + len(COCO_CLASSES):
            raise ValueError(f"{model_path}: output has {per_anchor} values per anchor, expected "
                             f"{5 + len(COCO_CLASSES)} (box, objectness, the 80 COCO classes)")
        # a symbolic output shape passes the check above: one blank input checks the real shape before the first frame
        raw = self.session.run(None, {self.input_name: np.zeros((1, 3) + self.size_hw, np.float32)})[0]
        if raw.shape[-2:] != (self.grid.shape[0], 5 + len(COCO_CLASSES)):
            raise ValueError(f"{model_path}: output shape {raw.shape}, expected (1, {self.grid.shape[0]}, "
                             f"{5 + len(COCO_CLASSES)})")
        self.phone = COCO_CLASSES.index(PHONE)
        self.score_min, self.nms_iou = float(score_min), float(nms_iou)

    def __call__(self, bgr: np.ndarray) -> Phones:
        H, W = bgr.shape[:2]
        t0 = time.perf_counter()
        x, r = letterbox(bgr, self.size_hw)
        t1 = time.perf_counter()
        raw = self.session.run(None, {self.input_name: x[None]})[0][0]
        t2 = time.perf_counter()
        if raw.shape[0] != self.grid.shape[0]:
            raise ValueError(f"phone output has {raw.shape[0]} anchors, expected {self.grid.shape[0]}")
        boxes, cls = decode_classes(raw.astype(np.float32), self.grid, self.strides)
        best = cls.argmax(axis=1)
        scores = cls[np.arange(len(best)), best]
        kept = scores >= self.score_min
        boxes, scores, best = boxes[kept], scores[kept], best[kept]
        order = nms(boxes, scores, self.nms_iou) if len(scores) else []
        order = [i for i in order if best[i] == self.phone]
        boxes_px = boxes[order] / r
        boxes_px[:, [0, 2]] = boxes_px[:, [0, 2]].clip(0, W)
        boxes_px[:, [1, 3]] = boxes_px[:, [1, 3]].clip(0, H)
        frac = boxes_px / np.array([W, H, W, H], dtype=np.float64)
        t3 = time.perf_counter()
        return Phones(frac.astype(np.float64), scores[order].astype(np.float64), (W, H),
                      {"pre": (t1 - t0) * 1e3, "infer": (t2 - t1) * 1e3, "post": (t3 - t2) * 1e3})
