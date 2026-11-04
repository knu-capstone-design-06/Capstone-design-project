"""선택 열 (optional columns) of events.py, made from one frame's perception outputs.

Layers: 추론 (app/inference/vision.py MediaPipe; app/inference/head.py H1 · head_direction.py P1) -> 관측값
(features.py) + this file -> 사건 (events.py) -> 상황 (situation.py). numpy only (no OpenCV, MediaPipe or ONNX Runtime
here), so it is tested on arrays.

Columns (names = the ones events.py reads, then observation-only columns no rule reads yet):
  people_behind_count   heads standing behind the main user: the boxes of this frame whose track is decided 'behind'
                        (below). 0 when no head other than the main user's is found; None (blank, the cue is missing)
                        when another head's role cannot be told. 'Standing, not passing' is the events layer's job
                        (stay_min_s). Absent (column missing) when the head detector did not run.
  companion_box         (x0, y0, x1, y1) as fractions of the frame: the largest box of this frame whose track is decided
                        'companion'; None when every other head is decided not to be one. The key is left out of the
                        row when no companion is found and another head's role cannot be told (events.py: a row
                        without the column = the companion cannot be told there, not 'no companion').
  shoulder_cx, shoulder_cy  midpoint of pose points 11 and 12 (left / right shoulder [D3]) as fractions of the frame;
                        None when the body is not seen.
  mouth_motion          largest absolute change of a mouth / jaw blendshape (params.mouth_dials) from that dial's
                        baseline = the median of the same dial over the previous mouth_baseline_s seconds of the same
                        unbroken face run (decision list 2026-10-10 §16: the person's baseline subtracted, change
                        only). None while the face is not seen, while the run is shorter than mouth_baseline_s, and
                        when blendshapes are off.
  head_count, primary_box, primary_score, primary_from   all kept head boxes; the main user's box, its H1 score and how
                        it was chosen ('track' = the main user's track from earlier frames, 'face' | 'largest' = chosen
                        anew at this frame); observation only. primary_box is None while the main user's track is alive
                        but has no box in this frame.
  primary_track         track id of the main user (also while its track has no box in this frame); observation only
  head_boxes            every head box of the frame in H1 order, one dict each: track (id), cx, cy, w, h (fractions of
                        the frame), score (H1), role ('primary' | 'companion' | 'behind' | 'other' | 'unknown') and the
                        cues against the main user - rel_dist, lateral of this frame and rel_dist_med, lateral_med of
                        the trailing window (None for the main user's box and where a cue cannot be computed). Written
                        as one JSON cell in rows.csv ("[]" = no head); observation only, so later analyses need no rerun
  head_dir_middle, head_dir_up, head_dir_left, head_dir_right, head_dir_back   P1 probabilities of the main user's
                        head (classes 중간 · 위 · 좌 · 우 · 뒤, AI Hub 70 '촬영방향'); None without a main-user head or
                        without the P1 model. Observation only: no rule reads them yet.

Tracks (HeadTracker; params track_iou_min, track_max_gap_s): frame by frame, each head box joins the live track whose
last box overlaps it most, highest IoU first, when that IoU is at least track_iou_min (the association step of SORT,
Bewley et al. 2016, without its Kalman prediction and with a greedy instead of a Hungarian assignment); a box that joins
none starts a new track. A track ends when it has had no box for more than track_max_gap_s seconds.

Main user (HeadPeople; params.primary_rule, [파일럿] rule). The main user is a track: while its track is alive it
stays the main user, and only after it ended is a new one chosen among the boxes of the frame (choose_primary):
'face_then_largest' = the largest head box that contains the centre of the face the Face Landmarker tracks (face_cx,
face_cy), so the yaw, the mouth and the head box belong to the same person at the moment of choice; without such a box
(face not seen, or no box around it) the largest box, ties broken by the distance of the box centre to the frame's
vertical centre line. 'largest' = always the largest box. The Face Landmarker follows one face on its own, so after the
choice a face centre outside the main user's box (primary_box) means the face and the head box are two people.

Cues of every other track against the main user (relative_cues), in frames where both have a box: rel_dist = h_primary /
h_box (box heights; a pinhole camera images a head at a size inversely proportional to its distance, so with heads of
similar size this is the distance from the camera relative to the main user's, research 56 section 4 [유도]; the height
is less cut than the width at the left and right frame edges) and lateral = (cx_box - cx_primary) / h_primary in pixels
(signed, + = right in the image; in main-user head heights). Each track keeps its cues of the last role_window_s
seconds; their medians (rel_dist_med, the signed lateral_med) decide its role (decide_role):
  companion   rel_dist_med <= companion_rel_dist_max ('비슷한 크기') and |lateral_med| >= companion_lateral_min ('옆')
  behind      rel_dist_med > 1 (decision table 3: '주 사용자보다 작은 상자', SMALLER_THAN_USER) and rel_dist_med >=
              behind_rel_dist_min ('뒤쪽') and not a companion
  other       neither; unknown = cannot tell (a boundary without a value, or no cue in the window)
The three boundaries have no value (params.UNDECIDED): until a value bundle gives one, the roles they decide are
'unknown' and the cues are still written (head_boxes). The tracks' cue history starts again when the main user changes.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from app.inference.head_direction import DIR_KEYS

from .events import SEEN

SHOULDERS = (11, 12)   # left / right shoulder in the 33-point pose map [D3]; = features.SHOULDERS
DIR_COLUMNS = tuple(f"head_dir_{k}" for k in DIR_KEYS)
HEAD_COLUMNS = ("people_behind_count", "companion_box", "head_count", "primary_box", "primary_score",
                "primary_from", "primary_track") + DIR_COLUMNS + ("head_boxes",)
OPTIONAL_COLUMNS = HEAD_COLUMNS + ("shoulder_cx", "shoulder_cy", "mouth_motion")
SMALLER_THAN_USER = 1.0   # decision table 3 '주 사용자보다 작은 상자': rel_dist > 1 = a head box smaller than the user's
ROLES = ("primary", "companion", "behind", "other", "unknown")


@dataclass(frozen=True)
class HeadRoles:
    """Who is who among the head boxes of one frame (indices into the boxes)."""
    primary: int | None            # the main user's box; None when the main user's track has no box in this frame
    companion: int | None          # the largest box of a track decided 'companion', or None
    behind: tuple                  # the boxes of tracks decided 'behind'
    primary_from: str | None       # 'track' | 'face' | 'largest' | None (no box of the main user in this frame)
    tracks: tuple = ()             # track id per box
    roles: tuple = ()              # role per box (ROLES)
    cues: tuple = ()               # per box (rel_dist, lateral, rel_dist_med, lateral_med); None for the main user's
    primary_track: int | None = None
    behind_known: bool = True      # every other box is decided behind or not
    companion_known: bool = True   # a companion was found, or every other box is decided not to be one


def _finite(v) -> float | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _areas(boxes: np.ndarray) -> np.ndarray:
    return (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])          # fraction units: ratios = pixel ratios


def choose_primary(boxes, face_xy, rule: str) -> tuple:
    """(index, how) of the main user among one frame's head boxes (fractions x0, y0, x1, y1) by primary_rule (module
    docstring), how = 'face' | 'largest'; (None, None) without boxes. face_xy = (face_cx, face_cy) of the tracked face,
    or None when the face is not seen."""
    boxes = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
    if not len(boxes):
        return None, None
    areas = _areas(boxes)
    centre_x = (boxes[:, 0] + boxes[:, 2]) / 2.0
    # largest first; ties by distance to the vertical centre line, then index (stable)
    order = sorted(range(len(boxes)), key=lambda i: (-areas[i], abs(centre_x[i] - 0.5), i))
    if rule == "face_then_largest" and face_xy is not None:
        fx, fy = face_xy
        around = [i for i in order if boxes[i, 0] <= fx <= boxes[i, 2] and boxes[i, 1] <= fy <= boxes[i, 3]]
        if around:
            return around[0], "face"
    return order[0], "largest"


def box_iou(a, b) -> float:
    """Intersection over union of two boxes (x0, y0, x1, y1); 0 when the union is empty."""
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return float(inter / union) if union > 0 else 0.0


class HeadTracker:
    """Head boxes linked into tracks with persistent ids (module docstring 'Tracks')."""

    def __init__(self, iou_min: float, max_gap_s: float):
        self.iou_min, self.max_gap_s = float(iou_min), float(max_gap_s)
        self.live = {}          # track id -> (last box, time of the last box)
        self.next_id = 1

    def update(self, t: float, boxes) -> list:
        """Track ids of this frame's boxes (same order). Tracks unseen for more than max_gap_s end first."""
        boxes = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
        self.live = {k: v for k, v in self.live.items() if t - v[1] <= self.max_gap_s}
        pairs = sorted(((box_iou(boxes[i], last), i, k) for i in range(len(boxes))
                        for k, (last, _) in self.live.items()), key=lambda x: (-x[0], x[1], x[2]))
        ids, used = [None] * len(boxes), set()
        for value, i, k in pairs:
            if value < self.iou_min:
                break
            if ids[i] is None and k not in used:
                ids[i] = k
                used.add(k)
        for i in range(len(boxes)):
            if ids[i] is None:
                ids[i], self.next_id = self.next_id, self.next_id + 1
            self.live[ids[i]] = (boxes[i].copy(), t)
        return ids


def relative_cues(box, primary_box, frame_wh) -> tuple:
    """(rel_dist, lateral) of a head box against the main user's box (both fractions x0, y0, x1, y1; module
    docstring); (None, None) when a box has no height."""
    W, H = frame_wh
    hp, hb = primary_box[3] - primary_box[1], box[3] - box[1]
    if hp <= 0 or hb <= 0 or H <= 0:
        return None, None
    lateral = ((box[0] + box[2]) / 2.0 - (primary_box[0] + primary_box[2]) / 2.0) * W / (hp * H)
    return float(hp / hb), float(lateral)


def _and3(*conditions):
    """Three-valued AND (as situation._all): False if any is False, else None if any is None, else True."""
    if any(c is False for c in conditions):
        return False
    return None if any(c is None for c in conditions) else True


def _at_most(value, bound):
    return None if value is None or bound is None else value <= bound


def _at_least(value, bound):
    return None if value is None or bound is None else value >= bound


def decide_role(rel_dist_med, lateral_med, params) -> tuple:
    """(role, companion, behind) of one other track from its window medians (module docstring): companion and behind
    are True, False or None (cannot tell: a boundary without a value, or no cue in the window)."""
    companion = _and3(_at_most(rel_dist_med, params.companion_rel_dist_max),
                      _at_least(None if lateral_med is None else abs(lateral_med), params.companion_lateral_min))
    smaller = None if rel_dist_med is None else rel_dist_med > SMALLER_THAN_USER
    behind = _and3(smaller, _at_least(rel_dist_med, params.behind_rel_dist_min),
                   None if companion is None else not companion)
    if companion is True:
        role = "companion"
    elif behind is True:
        role = "behind"
    elif companion is False and behind is False:
        role = "other"
    else:
        role = "unknown"
    return role, companion, behind


class HeadPeople:
    """Per frame: head tracks, the main user as a track, the cues of every other track and their roles (module
    docstring). One instance per input; replay and live share it through chain.FrameChain."""

    def __init__(self, params):
        self.p = params
        self.tracker = HeadTracker(params.track_iou_min, params.track_max_gap_s)
        self.primary_track = None
        self.history = {}        # track id -> deque of (t, rel_dist, lateral) against the current main user

    def update(self, t: float, boxes, frame_wh: tuple, face_xy) -> HeadRoles:
        boxes = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
        ids = self.tracker.update(t, boxes)
        how = None
        if self.primary_track is not None and self.primary_track not in self.tracker.live:
            self.primary_track = None                       # unseen for more than track_max_gap_s: ended
        if self.primary_track is None and len(boxes):
            k, how = choose_primary(boxes, face_xy, self.p.primary_rule)
            self.primary_track = ids[k]
            self.history.clear()                            # cues against the previous main user no longer apply
        primary = ids.index(self.primary_track) if self.primary_track in ids else None
        if primary is not None and how is None:
            how = "track"
        for k in [k for k in self.history if k not in self.tracker.live]:
            del self.history[k]
        cues, roles, companions, behind_status = [], [], [], []
        for i, k in enumerate(ids):
            if i == primary:
                cues.append(None)
                roles.append("primary")
                continue
            rel, lat = (None, None) if primary is None else relative_cues(boxes[i], boxes[primary], frame_wh)
            past = self.history.setdefault(k, deque())
            if rel is not None:
                past.append((t, rel, lat))
            while past and past[0][0] < t - self.p.role_window_s:
                past.popleft()
            rel_med = float(np.median([x[1] for x in past])) if past else None
            lat_med = float(np.median([x[2] for x in past])) if past else None
            role, companion, behind = decide_role(rel_med, lat_med, self.p)
            cues.append((rel, lat, rel_med, lat_med))
            roles.append(role)
            companions.append((i, companion))
            behind_status.append((i, behind))
        areas = _areas(boxes)
        found = sorted((i for i, c in companions if c is True), key=lambda i: (-areas[i], i))
        companion = found[0] if found else None
        return HeadRoles(primary, companion, tuple(i for i, b in behind_status if b is True), how, tuple(ids),
                         tuple(roles), tuple(cues), self.primary_track,
                         behind_known=all(b is not None for _, b in behind_status),
                         companion_known=companion is not None or all(c is False for _, c in companions))


def _r(v, digits):
    return None if v is None else round(float(v), digits)


def head_columns(heads, roles: HeadRoles, dir_probs) -> dict:
    """The head columns of one frame. heads = app.inference.head.Heads (or anything with .boxes and .scores);
    dir_probs = the P1 probabilities of the main user's head (5,), or None. companion_box is left out when the
    companion cannot be told (module docstring)."""
    boxes = np.asarray(heads.boxes, dtype=np.float64).reshape(-1, 4)
    out = {"people_behind_count": len(roles.behind) if roles.behind_known else None,
           "head_count": int(len(boxes)),
           "primary_box": None if roles.primary is None else tuple(float(v) for v in boxes[roles.primary]),
           "primary_score": None if roles.primary is None else float(heads.scores[roles.primary]),
           "primary_from": roles.primary_from, "primary_track": roles.primary_track}
    if roles.companion is not None:
        out["companion_box"] = tuple(float(v) for v in boxes[roles.companion])
    elif roles.companion_known:
        out["companion_box"] = None
    probs = None if dir_probs is None or roles.primary is None else np.asarray(dir_probs, dtype=np.float64).ravel()
    for k, col in enumerate(DIR_COLUMNS):
        out[col] = None if probs is None else float(probs[k])
    listed = []
    for i, b in enumerate(boxes):
        cue = roles.cues[i] if i < len(roles.cues) and roles.cues[i] is not None else (None,) * 4
        listed.append({"track": roles.tracks[i] if i < len(roles.tracks) else None,
                       "cx": _r((b[0] + b[2]) / 2.0, 6), "cy": _r((b[1] + b[3]) / 2.0, 6),
                       "w": _r(b[2] - b[0], 6), "h": _r(b[3] - b[1], 6), "score": _r(heads.scores[i], 4),
                       "role": roles.roles[i] if i < len(roles.roles) else None,
                       "rel_dist": _r(cue[0], 4), "lateral": _r(cue[1], 4),
                       "rel_dist_med": _r(cue[2], 4), "lateral_med": _r(cue[3], 4)})
    out["head_boxes"] = listed
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
