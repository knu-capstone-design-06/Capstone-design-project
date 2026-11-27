"""Walking-aid confirm reader: a person-crop classifier (ResNet-18, five classes pedestrian, crutch, cane, walker,
wheelchair) with ONNX Runtime, CPU only. An optional input of the vision chain: it runs only when its ONNX file(s) are
given (replay.py / live.py --aid-confirm-model); the weights are never in this repository (vision README, '휠체어 확인
분류기'). With several files the probabilities are the mean of their softmax outputs per crop (deep ensemble,
Lakshminarayanan et al. 2017).

The crop is the one the reader was trained and measured with (aid_cls_v2_train.py body_box 'full' and to_tensor of the
training packet; the team's crop reader measurement of 2026-11-27): the person box widened by MARGIN_PX on every side,
floor / ceil to whole pixels and clipped to the frame (thinner than 2 px: the bare box, then the whole frame), cut from
the frame as RGB, resized to the model input with PIL's bilinear filter (aspect ratio not kept), divided by 255, minus
MEAN and over STD, CHW, float32. The model output is logits (softmaxed here).

Per file, the export's metadata (custom_metadata_map) is read when present: 'mean' and 'std' = JSON lists of three
numbers (the normalisation of that file's input, in 0..1 pixel units), 'classes' = JSON list of the class names (must
equal CLASSES, else the file is refused), 'output' = 'logits' or 'probs'. A file without them uses the values of the
measured ResNet-18 reader (MEAN, STD, CLASSES, logits): its export carries no metadata. The input size is the file's
input shape (all files must share it: one crop image serves them all).
"""
from __future__ import annotations

import json
import math
import time

import numpy as np

CLASSES = ("pedestrian", "crutch", "cane", "walker", "wheelchair")   # the training run's class order (train_meta.json)
MARGIN_PX = 20                                   # the training run's crop margin (train_meta.json args.margin)
MEAN = (0.485, 0.456, 0.406)                     # torchvision ImageNet weights' transform (aid_cls_v2_train.py)
STD = (0.229, 0.224, 0.225)


def crop_box(box_px, frame_wh) -> tuple:
    """(x0, y0, x1, y1) whole pixels of the reader's crop of a person box (x0, y0, x1, y1 pixels) in a frame (W, H)."""
    W, H = frame_wh

    def whole(r):
        b = (max(0, int(math.floor(r[0]))), max(0, int(math.floor(r[1]))), min(W, int(math.ceil(r[2]))),
             min(H, int(math.ceil(r[3]))))
        return b if b[2] - b[0] >= 2 and b[3] - b[1] >= 2 else None
    x0, y0, x1, y1 = box_px
    m = MARGIN_PX
    return whole((x0 - m, y0 - m, x1 + m, y1 + m)) or whole((x0, y0, x1, y1)) or (0, 0, W, H)


def softmax(x: np.ndarray) -> np.ndarray:
    z = np.exp(x - np.max(x))
    return z / z.sum()


class AidConfirmReader:
    """Class probabilities of person crops: reader.crop(bgr, box_px) -> uint8 (H, W, 3) RGB input image;
    reader.probs(image) -> (len(CLASSES),) probabilities (the mean over the files). sessions = stand-ins for tests."""

    def __init__(self, model_paths, threads: int = 1, sessions=None):
        if sessions is None:
            import onnxruntime as ort
            sessions = []
            for path in model_paths:
                so = ort.SessionOptions()
                so.intra_op_num_threads = int(threads)
                so.inter_op_num_threads = 1
                so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                sessions.append(ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"]))
        if not sessions:
            raise ValueError("the confirm reader needs at least one model file")
        self.sessions = list(sessions)
        inp = self.sessions[0].get_inputs()[0]
        self.size_hw = (int(inp.shape[2]), int(inp.shape[3]))
        self.inputs = []                             # per file: (input name, mean, std, output is logits)
        for s in self.sessions:
            i = s.get_inputs()[0]
            if (int(i.shape[2]), int(i.shape[3])) != self.size_hw:
                raise ValueError(f"the confirm reader files differ in input size: {self.size_hw} and {tuple(i.shape)}")
            mean, std, logits = self.normalisation(s)
            out = np.asarray(s.run(None, {i.name: np.zeros((1, 3) + self.size_hw, np.float32)})[0])
            if out.reshape(-1).shape[0] != len(CLASSES):
                raise ValueError(f"a confirm reader file gives {out.shape}, expected {len(CLASSES)} values ({CLASSES})")
            self.inputs.append((i.name, mean, std, logits))
        self.ms = []                                 # wall time of each probs() call (all files), milliseconds

    @staticmethod
    def normalisation(session) -> tuple:
        """(mean (3, 1, 1), std (3, 1, 1), output is logits) of one file: its metadata, else the measured reader's."""
        try:
            meta = dict(session.get_modelmeta().custom_metadata_map)
        except AttributeError:                       # a stand-in session without metadata
            meta = {}
        if "classes" in meta and tuple(json.loads(meta["classes"])) != CLASSES:
            raise ValueError(f"a confirm reader file has the classes {meta['classes']}, expected {CLASSES}")
        if ("mean" in meta) != ("std" in meta):
            raise ValueError("a confirm reader file's metadata has only one of 'mean' and 'std'")
        mean = json.loads(meta["mean"]) if "mean" in meta else MEAN
        std = json.loads(meta["std"]) if "std" in meta else STD
        if len(mean) != 3 or len(std) != 3 or min(std) <= 0:
            raise ValueError(f"a confirm reader file's mean / std are not three numbers with std > 0: {mean}, {std}")
        output = meta.get("output", "logits")
        if output not in ("logits", "probs"):
            raise ValueError(f"a confirm reader file's 'output' is {output!r}, expected 'logits' or 'probs'")
        return (np.asarray(mean, np.float32).reshape(3, 1, 1), np.asarray(std, np.float32).reshape(3, 1, 1),
                output == "logits")

    def crop(self, bgr: np.ndarray, box_px) -> np.ndarray:
        """The model-size RGB image (uint8) of the person box box_px (pixels) of a BGR frame (module docstring)."""
        from PIL import Image
        x0, y0, x1, y1 = crop_box(box_px, (bgr.shape[1], bgr.shape[0]))
        rgb = np.ascontiguousarray(bgr[y0:y1, x0:x1, ::-1])
        return np.asarray(Image.fromarray(rgb).resize((self.size_hw[1], self.size_hw[0]), Image.BILINEAR), np.uint8)

    def probs(self, image: np.ndarray) -> np.ndarray:
        t0 = time.perf_counter()
        x01 = image.transpose(2, 0, 1).astype(np.float32) / np.float32(255)
        ps = []
        for s, (name, mean, std, logits) in zip(self.sessions, self.inputs):
            x = ((x01 - mean) / std)[None].astype(np.float32)
            out = np.asarray(s.run(None, {name: x})[0], np.float64).reshape(-1)
            ps.append(softmax(out) if logits else out / out.sum())
        p = np.mean(ps, axis=0)
        self.ms.append((time.perf_counter() - t0) * 1000.0)
        return p
