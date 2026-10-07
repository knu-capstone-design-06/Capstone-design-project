"""관측값 (features) layer: observations computed from the inference outputs - geometry, continuity, quality.

Observes and measures only. No judgments and no thresholds: the rules come after the team's decisions (situation.py).
Every constant below carries its source. No MediaPipe here: the inputs are plain arrays (inference.FrameInference or
any object with the same attributes), so this layer runs and is tested without the models.

Source shorthands used in the comments:
  doc 28, doc 27 = the vision owner's design notes 28_mediapipe_limits_and_reach.md (sections 0-8) and
           27_before_after_table.md (section 1-4, the vision observations), kept in the project workspace
           (01_requirements/research/), not in this repository; [C5] [D17] are entries of doc 28's source list
  [D1] [D2] [D3] = the MediaPipe Face Landmarker / Face Detector / Pose Landmarker docs (URLs in inference.py)
"""
from __future__ import annotations

import math
import time

import cv2
import numpy as np

NAN = float("nan")
SEEN, NOT_SEEN = "보임", "못 봄"   # doc 28 sections 1, 3: an empty result is '못 봄' (not seen), never 'no person'

# --- landmark indices ---------------------------------------------------------------------------------------
EYE_A = (33, 133)    # corners of one eye: points of FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_EYE (mediapipe
                     # tasks); same pair as the earlier MediaPipe bench in the project workspace
EYE_B = (362, 263)   # corners of the other eye: FACE_LANDMARKS_LEFT_EYE; same bench
SHOULDERS = (11, 12) # left / right shoulder in the 33-point pose map [D3]; doc 28 section 3 ('뒤돌아봄' row) uses them

# CSV columns in order (meanings: README.md, section "CSV 열").
COLUMNS = [
    "frame_idx", "src_frame", "t_s", "source_kind", "syn_phase",
    "face_state", "body_state", "face_count",
    "iod_px", "iod_frac_w", "iod_ratio_start",
    "yaw_deg", "pitch_deg", "roll_deg", "dyaw_start_deg", "dpitch_start_deg",
    "face_cx", "face_cy", "face_y_max",
    "face_run_id", "face_run_s", "face_unseen_s", "face_shift", "iod_step",
    "body_run_s", "body_unseen_s",
    "face_det_score", "det_box_w_frac",
    "pose_vis_mean", "pose_pres_mean", "pose_vis_shoulders",
    "bright_frame", "bright_face", "lapvar_frame", "lapvar_face",
    "ms_read", "ms_prep", "ms_face_lm", "ms_face_det", "ms_pose", "ms_features", "ms_quality", "ms_total",
]
STAGES = ["ms_read", "ms_prep", "ms_face_lm", "ms_face_det", "ms_pose", "ms_features", "ms_quality", "ms_total"]


class Continuity:
    """Runs of consecutive frames in which something is seen.

    No smoothing window: the time window that would ignore short drop-outs is a pilot value
    (doc 28 section 3, '사람 있음' row: '잠깐 끊김을 거르는 시간 창은 [파일럿]'), so every gap counts."""

    def __init__(self):
        self.t0 = None
        self.run_id = 0
        self.run_start = None
        self.last_seen_t = None
        self.prev_seen = False

    def update(self, t: float, seen: bool):
        if self.t0 is None:
            self.t0 = t
        if seen:
            if not self.prev_seen:
                self.run_id += 1
                self.run_start = t
            self.last_seen_t = t
            out = (self.run_id, t - self.run_start, NAN)
        else:
            since = self.last_seen_t if self.last_seen_t is not None else self.t0
            out = (NAN, 0.0, t - since)
        self.prev_seen = seen
        return out


def head_angles_deg(matrix) -> tuple[float, float, float]:
    """(yaw, pitch, roll) in degrees from the 4x4 facial transformation matrix.

    The matrix rotates the canonical face model into the camera view (doc 28 section 2; [D1]). Its 3x3
    rotation part is decomposed with OpenCV RQDecomp3x3, which returns Euler angles about x, y, z
    (one of several possible conventions, per the OpenCV docs) -> pitch = about x, yaw = about y,
    roll = about z. Angles are comparable within this prototype; their accuracy is not documented
    (doc 28 section 4-5)."""
    R = np.asarray(matrix, dtype=np.float64)[:3, :3]
    ax, ay, az = cv2.RQDecomp3x3(R)[0]
    return float(ay), float(ax), float(az)


def _mean(vals) -> float:
    vals = np.asarray(vals, dtype=np.float64)
    vals = vals[np.isfinite(vals)]
    return float(vals.mean()) if vals.size else NAN


def quality(row: dict, img: np.ndarray, face_box_px):
    """Brightness and sharpness of the frame and of the face box (OpenCV image statistics).

    Brightness = mean grey level 0-255; OpenCV BGR->GRAY uses Y = 0.299 R + 0.587 G + 0.114 B (cvtColor docs).
    Sharpness = variance of the Laplacian (focus measure, Pech-Pacheco et al., ICPR 2000); higher = sharper,
    lower = more blur. Laplacian ksize=1 is the OpenCV default. Doc 28 section 3: brightness and blur are not
    MediaPipe outputs -> OpenCV image statistics."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    row["bright_frame"] = float(gray.mean())
    row["lapvar_frame"] = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if face_box_px is not None:
        H, W = gray.shape
        x0, y0, x1, y1 = face_box_px
        xa, ya = max(0, int(math.floor(x0))), max(0, int(math.floor(y0)))
        xb, yb = min(W, int(math.ceil(x1))), min(H, int(math.ceil(y1)))
        if xb > xa and yb > ya:   # face box inside the frame: same statistics on the face region
            crop = gray[ya:yb, xa:xb]
            row["bright_face"] = float(crop.mean())
            row["lapvar_face"] = float(cv2.Laplacian(crop, cv2.CV_64F).var())


class Observer:
    """One observation session: runs the inference on each frame and computes the CSV row and the overlay
    geometry (the observations of doc 27 section 1-4, computed the way doc 28 section 3 describes them).

    models = inference.MediaPipeModels, or any object with infer(frame) -> FrameInference (tests use a fake)."""

    def __init__(self, models):
        self.models = models
        self.reset_session()

    def reset_session(self):
        """Start a new session: the reference for 'ratio to the session start' is taken again.

        Kiosk: a session starts at the first touch (doc 27 section 0, '세션'). Offline: the start of the file."""
        self.ref = None
        self.prev_face = None
        self.face_cont = Continuity()
        self.body_cont = Continuity()

    def process(self, frame, source_kind: str = "", syn_phase: str = ""):
        """Return (row, draw) for one Frame: row = CSV values, draw = geometry for the overlay."""
        t_start = time.perf_counter()
        img = frame.image
        H, W = img.shape[:2]
        row = dict.fromkeys(COLUMNS, NAN)
        row.update(frame_idx=frame.index, src_frame=frame.src_ref, t_s=round(frame.t_s, 4),
                   source_kind=source_kind, syn_phase=syn_phase, ms_read=frame.read_ms)
        inf = self.models.infer(frame)
        row.update(inf.ms)

        t = time.perf_counter()
        draw = self._features(row, frame.t_s, W, H, inf)
        row["ms_features"] = (time.perf_counter() - t) * 1000.0

        t = time.perf_counter()
        quality(row, img, draw.get("face_box_px"))
        row["ms_quality"] = (time.perf_counter() - t) * 1000.0

        row["ms_total"] = (time.perf_counter() - t_start) * 1000.0   # prep -> quality; file reading excluded
        return row, draw

    def _features(self, row, t_s, W, H, inf):
        draw = {"W": W, "H": H}
        face_seen = inf.face_points is not None
        body_seen = inf.pose is not None
        row["face_state"] = SEEN if face_seen else NOT_SEEN
        row["body_state"] = SEEN if body_seen else NOT_SEEN

        # Face count and detection score from the Face Detector (doc 28 section 3; score [D2]).
        dets = inf.detections
        row["face_count"] = len(dets)
        draw["det_boxes"] = list(dets)
        if dets:
            best = max(dets, key=lambda d: d[4])
            row["face_det_score"] = float(best[4])
            row["det_box_w_frac"] = best[2] / W   # box / frame width, as in doc 28 section 4-1

        run_id, run_s, unseen_s = self.face_cont.update(t_s, face_seen)
        row.update(face_run_id=run_id, face_run_s=run_s, face_unseen_s=unseen_s)
        if face_seen:
            pts = np.asarray(inf.face_points, dtype=np.float64)       # fractions of width / height (doc 28 s.2)
            px = pts * np.array([W, H])
            eye_a = px[list(EYE_A)].mean(axis=0)
            eye_b = px[list(EYE_B)].mean(axis=0)
            iod = float(np.linalg.norm(eye_a - eye_b))                 # IOD in px (doc 28 section 3)
            x0, y0 = pts.min(axis=0)
            x1, y1 = pts.max(axis=0)
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            yaw, pitch, roll = head_angles_deg(inf.face_matrix) if inf.face_matrix is not None else (NAN, NAN, NAN)
            if self.ref is None:      # session-start reference = first frame of the session with a face
                self.ref = {"iod": iod, "yaw": yaw, "pitch": pitch, "t_s": t_s}
            row.update(iod_px=iod, iod_frac_w=iod / W, iod_ratio_start=iod / self.ref["iod"],
                       yaw_deg=yaw, pitch_deg=pitch, roll_deg=roll,
                       dyaw_start_deg=yaw - self.ref["yaw"], dpitch_start_deg=pitch - self.ref["pitch"],
                       face_cx=cx, face_cy=cy, face_y_max=y1)
            if self.prev_face is not None:   # continuity of position and size since the last frame with a face
                p = self.prev_face
                row["face_shift"] = math.hypot((cx - p["cx"]) * W, (cy - p["cy"]) * H) / W
                row["iod_step"] = iod / p["iod"]
            self.prev_face = {"cx": cx, "cy": cy, "iod": iod}
            draw.update(face_px=px, eye_a=eye_a, eye_b=eye_b, face_center_px=(cx * W, cy * H),
                        face_box_px=(x0 * W, y0 * H, x1 * W, y1 * H))
            if inf.face_matrix is not None:
                draw["rot"] = np.asarray(inf.face_matrix)[:3, :3]

        _, brun_s, bunseen_s = self.body_cont.update(t_s, body_seen)
        row.update(body_run_s=brun_s, body_unseen_s=bunseen_s)
        if body_seen:
            pose = np.asarray(inf.pose, dtype=np.float64)
            vis, pres = pose[:, 2], pose[:, 3]
            row["pose_vis_mean"] = _mean(vis)          # visibility / presence [C5][D17] (doc 28 section 3, quality row)
            row["pose_pres_mean"] = _mean(pres)
            row["pose_vis_shoulders"] = _mean(vis[list(SHOULDERS)])
            draw["pose_px"] = pose[:, :2] * np.array([W, H])
            draw["pose_vis"] = np.nan_to_num(vis, nan=0.0)
        return draw
