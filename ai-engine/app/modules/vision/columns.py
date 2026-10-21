"""선택 열 (optional columns) of events.py, made from one frame's perception outputs.

Layers: 추론 (app/inference/vision.py MediaPipe; perception/ H1 · P1) -> 관측값 (features.py) + this file -> 사건
(events.py) -> 상황 (situation.py). numpy only (no OpenCV, MediaPipe or ONNX Runtime here), so it is tested on arrays.

Columns (names = the ones events.py reads, then observation-only columns no rule reads yet):
  people_behind_count   heads standing behind the main user: every head box other than the main user's and the
                        companion's whose area is below behind_max_area_ratio x the main user's (decision table 3:
                        '주 사용자보다 작은 상자'). 0 when no head is found. 'Standing, not passing' is the events layer's
                        job (stay_min_s). Absent (column missing) when the head detector did not run.
  companion_box         (x0, y0, x1, y1) as fractions of the frame: the largest head other than the main user's when its
                        area is at least companion_min_area_ratio x the main user's ('비슷한 크기') and its centre lies
                        within companion_max_dist_widths main-user head widths ('옆'); None when there is no such head.
  shoulder_cx, shoulder_cy  midpoint of pose points 11 and 12 (left / right shoulder [D3]) as fractions of the frame;
                        None when the body is not seen.
  mouth_motion          largest absolute change of a mouth / jaw blendshape (params.mouth_dials) from that dial's
                        baseline = the median of the same dial over the previous mouth_baseline_s seconds of the same
                        unbroken face run (decision 16: the person's baseline subtracted, change only). None while the
                        face is not seen, while the run is shorter than mouth_baseline_s, and when blendshapes are off.
  head_count, primary_box, primary_score, primary_from   all kept head boxes; the main user's box, its H1 score and how
                        it was chosen ('face' | 'largest'); observation only
  head_dir_middle, head_dir_up, head_dir_left, head_dir_right, head_dir_back   P1 probabilities of the main user's
                        head (classes 중간 · 위 · 좌 · 우 · 뒤, AI Hub 70 '촬영방향'); None without a main-user head or
                        without the P1 model. Observation only: no rule reads them yet.

Main user (params.primary_rule, [파일럿] rule): 'face_then_largest' = the largest head box that contains the centre of
the face the Face Landmarker tracks (face_cx, face_cy), so the yaw, the mouth and the head box belong to the same
person; without such a box (face not seen, or no box around it) the largest box, ties broken by the distance of the box
centre to the frame's vertical centre line. 'largest' = always the largest box.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from .events import SEEN
from .perception.head_direction import DIR_KEYS

SHOULDERS = (11, 12)   # left / right shoulder in the 33-point pose map [D3]; = features.SHOULDERS
DIR_COLUMNS = tuple(f"head_dir_{k}" for k in DIR_KEYS)
HEAD_COLUMNS = ("people_behind_count", "companion_box", "head_count", "primary_box", "primary_score",
                "primary_from") + DIR_COLUMNS
OPTIONAL_COLUMNS = HEAD_COLUMNS + ("shoulder_cx", "shoulder_cy", "mouth_motion")


@dataclass(frozen=True)
class HeadRoles:
    """Who is who among the head boxes of one frame (indices into the boxes)."""
    primary: int | None
    companion: int | None
    behind: tuple
    primary_from: str | None   # 'face' | 'largest' | None (no head)


def _finite(v) -> float | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def assign_heads(boxes: np.ndarray, frame_wh: tuple, face_xy, params) -> HeadRoles:
    """Main user, companion and people behind among head boxes (fractions x0, y0, x1, y1); see the module docstring.
    face_xy = (face_cx, face_cy) of the tracked face, or None when the face is not seen."""
    boxes = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
    if not len(boxes):
        return HeadRoles(None, None, (), None)
    W, H = frame_wh
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])          # fraction units: ratios = pixel ratios
    centre_x = (boxes[:, 0] + boxes[:, 2]) / 2.0
    # largest first; ties by distance to the vertical centre line, then index (stable)
    order = sorted(range(len(boxes)), key=lambda i: (-areas[i], abs(centre_x[i] - 0.5), i))
    primary, how = order[0], "largest"
    if params.primary_rule == "face_then_largest" and face_xy is not None:
        fx, fy = face_xy
        around = [i for i in order if boxes[i, 0] <= fx <= boxes[i, 2] and boxes[i, 1] <= fy <= boxes[i, 3]]
        if around:
            primary, how = around[0], "face"
    others = [i for i in order if i != primary]
    companion = None
    if others and areas[primary] > 0:
        c = others[0]                                                           # the largest other head
        width_px = (boxes[primary, 2] - boxes[primary, 0]) * W
        pcx, pcy = centre_x[primary] * W, (boxes[primary, 1] + boxes[primary, 3]) / 2.0 * H
        ccx, ccy = centre_x[c] * W, (boxes[c, 1] + boxes[c, 3]) / 2.0 * H
        dist_widths = math.hypot(ccx - pcx, ccy - pcy) / width_px if width_px > 0 else math.inf
        if areas[c] >= params.companion_min_area_ratio * areas[primary] and \
                dist_widths <= params.companion_max_dist_widths:
            companion = c
    behind = tuple(sorted(i for i in others
                          if i != companion and areas[i] < params.behind_max_area_ratio * areas[primary]))
    return HeadRoles(primary, companion, behind, how)


def head_columns(heads, roles: HeadRoles, dir_probs) -> dict:
    """The head columns of one frame. heads = perception.head.Heads (or anything with .boxes and .scores);
    dir_probs = the P1 probabilities of the main user's head (5,), or None."""
    boxes = np.asarray(heads.boxes, dtype=np.float64).reshape(-1, 4)
    out = {"people_behind_count": len(roles.behind),
           "companion_box": None if roles.companion is None else tuple(float(v) for v in boxes[roles.companion]),
           "head_count": int(len(boxes)),
           "primary_box": None if roles.primary is None else tuple(float(v) for v in boxes[roles.primary]),
           "primary_score": None if roles.primary is None else float(heads.scores[roles.primary]),
           "primary_from": roles.primary_from}
    probs = None if dir_probs is None or roles.primary is None else np.asarray(dir_probs, dtype=np.float64).ravel()
    for k, col in enumerate(DIR_COLUMNS):
        out[col] = None if probs is None else float(probs[k])
    return out


def shoulder_columns(pose) -> dict:
    """Midpoint of pose points 11 and 12 (fractions); None when there is no pose or a coordinate is missing."""
    if pose is None:
        return {"shoulder_cx": None, "shoulder_cy": None}
    pose = np.asarray(pose, dtype=np.float64)
    xs = [_finite(pose[i, 0]) for i in SHOULDERS]
    ys = [_finite(pose[i, 1]) for i in SHOULDERS]
    return {"shoulder_cx": None if None in xs else (xs[0] + xs[1]) / 2.0,
            "shoulder_cy": None if None in ys else (ys[0] + ys[1]) / 2.0}


class MouthMotion:
    """mouth_motion per frame with the baseline of the current unbroken face run (module docstring)."""

    def __init__(self, dials, baseline_s: float):
        self.dials = tuple(dials)
        self.baseline_s = float(baseline_s)
        self.reset()

    def reset(self):
        self.buffer = deque()      # (t, dial vector) of the current face run within the last baseline_s seconds
        self.run_start = None

    def update(self, t: float, scores: dict | None) -> float | None:
        """scores = {blendshape name: score} of this frame's face, or None when the face is not seen / blendshapes are
        off (the run breaks). A dial missing from scores is an error: the model's names changed."""
        if scores is None:
            self.reset()
            return None
        missing = [d for d in self.dials if d not in scores]
        if missing:
            raise KeyError(f"blendshape dials missing from the model output: {missing}")
        vec = np.array([scores[d] for d in self.dials], dtype=np.float64)
        if self.run_start is None:
            self.run_start = t
        while self.buffer and self.buffer[0][0] < t - self.baseline_s:
            self.buffer.popleft()
        value = None
        if t - self.run_start >= self.baseline_s and self.buffer:
            baseline = np.median(np.stack([v for _, v in self.buffer]), axis=0)
            value = float(np.max(np.abs(vec - baseline)))
        self.buffer.append((t, vec))
        return value


def face_xy(row: dict):
    """(face_cx, face_cy) of a features row when its face is seen and both values are finite, else None."""
    if row.get("face_state") != SEEN:
        return None
    x, y = _finite(row.get("face_cx")), _finite(row.get("face_cy"))
    return None if x is None or y is None else (x, y)
