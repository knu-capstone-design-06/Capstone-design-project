"""E12 camera block: per-window numbers from the MediaPipe and H1 columns of the vision replay (rows.csv), no images.

Source: 4_vision/companion_behind_2026-11-04/round2/replay/<clip>/rows.csv (the replay E3 and E5 read; about 10 frames per
second, MediaPipe Face Landmarker / Pose Landmarker and the H1 head detector). Nothing here is a threshold: every value
is a measured column, a share of frames, or a min / median / max over frames.

Span of a window ending at t: frames with t - SPAN < t_s <= t, SPAN = the situation window of value bundle b0_r0
(bundles/b0_r0.json situation.window_s, 3.0 s, the span the situation tags of E5's J input were judged over; read from
the file). In a rule-table session after the first one (E5 session_reset, only clips 171807 and 171844) the span also
starts at the session start (frames with t_s >= start), as E3's harness restricts its rows (harness.run_take 'since');
the start is the end time of the session's first window, which equals E3's TouchTimeline.session_since in all 12
session changes (checked 2026-11-08 with labels v2, the labels E5's b0_r0 rows were made with).

Start pose (dyaw_start_deg, dpitch_start_deg): yaw / pitch minus those of the first frame of the session with the main
user's face values. Session 0: the replay's own columns (features.Observer: first face frame of the recording; equal to
the first frame with face values in all 34 clips that have one, up to 0.001 deg rounding). Later sessions: re-taken
from the session start (Observer.reset_session at a new session), computed here from yaw_deg / pitch_deg.

Fields left out: mouth_motion (blendshapes off in this replay: no value in any of the 5,381 frames), P1 head_dir_*,
people_behind_count and companion_box (role decisions made with rule boundaries), face_count and the quality columns
(not in the design list). face values are present only where the chain kept them (it blanks a face that lies outside
the main user's head box, columns.FACE_VALUE_COLUMNS).
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
REPLAY = WS / "4_vision" / "companion_behind_2026-11-04" / "round2" / "replay"
BUNDLE = WS / "4_vision" / "eval_ab_2026-11-04" / "bundles" / "b0_r0.json"
SEEN = "보임"   # features.SEEN (face_state / body_state)


def span_s() -> float:
    return float(json.loads(BUNDLE.read_text(encoding="utf-8"))["situation"]["window_s"]["value"])


def _f(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load_rows(clip: str) -> list[dict]:
    """The columns the camera block uses, parsed (None = blank cell)."""
    out = []
    with open(REPLAY / clip / "rows.csv", encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            pb = r.get("primary_box") or ""
            box = tuple(float(x) for x in pb.split(";")) if pb else None
            out.append({
                "t": float(r["t_s"]),
                "face_values": r["yaw_deg"] != "",
                "yaw": _f(r["yaw_deg"]), "pitch": _f(r["pitch_deg"]), "roll": _f(r["roll_deg"]),
                "dyaw": _f(r["dyaw_start_deg"]), "dpitch": _f(r["dpitch_start_deg"]),
                "iod": _f(r["iod_frac_w"]), "fcx": _f(r["face_cx"]), "fcy": _f(r["face_cy"]),
                "body": r["body_state"] == SEEN,
                "vis_sh": _f(r["pose_vis_shoulders"]), "scx": _f(r["shoulder_cx"]), "scy": _f(r["shoulder_cy"]),
                "head_count": int(r["head_count"]) if r["head_count"] != "" else None,
                "primary": box,
                "boxes": json.loads(r["head_boxes"]) if r.get("head_boxes") else [],
            })
    return out


def _stats(values, nd):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return {"min": round(min(vals), nd), "med": round(statistics.median(vals), nd), "max": round(max(vals), nd)}


def _share(k, n):
    return None if n == 0 else round(k / n, 2)


def session_ref(rows: list[dict], start: float) -> tuple | None:
    """(yaw, pitch) of the first frame at or after start with the main user's face values, or None."""
    for r in rows:
        if r["t"] >= start - 1e-9 and r["face_values"]:
            return r["yaw"], r["pitch"]
    return None


def camera_block(rows: list[dict], t: float, span: float, start: float | None, ref: tuple | None) -> dict:
    """The camera numbers of the window ending at t. start = session start (None = first session: no lower bound but
    the span); ref = the start pose of a later session (None = use the replay's start columns)."""
    fr = [r for r in rows if t - span < r["t"] <= t + 1e-9 and (start is None or r["t"] >= start - 1e-9)]
    n = len(fr)
    face = [r for r in fr if r["face_values"]]
    if start is None:
        dyaw, dpitch = [r["dyaw"] for r in face], [r["dpitch"] for r in face]
    elif ref is None:
        dyaw, dpitch = [], []
    else:
        dyaw = [None if r["yaw"] is None else r["yaw"] - ref[0] for r in face]
        dpitch = [None if r["pitch"] is None else r["pitch"] - ref[1] for r in face]
    body = [r for r in fr if r["body"]]
    tracks: dict = {}
    for r in fr:
        p = r["primary"]
        hp = None if p is None else p[3] - p[1]
        cyp = None if p is None else (p[1] + p[3]) / 2.0
        for b in r["boxes"]:
            if b.get("role") == "primary":
                continue
            d = tracks.setdefault(b.get("track"), {"n": 0, "rel": [], "lat": [], "ver": []})
            d["n"] += 1
            d["rel"].append(b.get("rel_dist"))
            d["lat"].append(b.get("lateral"))
            d["ver"].append(None if (hp is None or hp <= 0 or b.get("cy") is None) else (b["cy"] - cyp) / hp)
    others = [{"seen_share": _share(d["n"], n), "rel_dist": _stats(d["rel"], 2), "lateral": _stats(d["lat"], 2),
               "vertical": _stats(d["ver"], 2)}
              for _, d in sorted(tracks.items(), key=lambda kv: (-kv[1]["n"], kv[0] if kv[0] is not None else -1))]
    return {
        "frames": n,
        "face": {"seen_share": _share(len(face), n),
                 "yaw_deg": _stats([r["yaw"] for r in face], 1), "pitch_deg": _stats([r["pitch"] for r in face], 1),
                 "roll_deg": _stats([r["roll"] for r in face], 1),
                 "dyaw_start_deg": _stats(dyaw, 1), "dpitch_start_deg": _stats(dpitch, 1),
                 "iod_frac_w": _stats([r["iod"] for r in face], 3),
                 "face_cx": _stats([r["fcx"] for r in face], 3), "face_cy": _stats([r["fcy"] for r in face], 3)},
        "body": {"seen_share": _share(len(body), n),
                 "pose_vis_shoulders": _stats([r["vis_sh"] for r in body], 2),
                 "shoulder_cx": _stats([r["scx"] for r in body], 3), "shoulder_cy": _stats([r["scy"] for r in body], 3)},
        "heads": {"head_count": _stats([r["head_count"] for r in fr], 0),
                  "user_head_share": _share(sum(1 for r in fr if r["primary"] is not None), n),
                  "others": others},
    }


# The definitions sent in every RAW question (instructions.camera_fields). English, units and sign conventions from the
# vision module's CSV table (ai-engine/app/modules/vision/README.md 'CSV 열', columns.py, features.py).
FIELD_DEFS = {
    "camera": "Measured by the kiosk camera (above the screen, facing the user) in the last {span} s of this window, "
              "about 10 frames/s, current session only; no image. {{min, med, max}} = minimum, median, maximum over "
              "the frames that have the value; null = no frame had it.",
    "camera.frames": "number of frames in the span",
    "camera.face": "the face the face landmarker follows (one face), kept only when it lies in the main user's head "
                   "box",
    "camera.face.seen_share": "share of frames (0-1) with the main user's face measured",
    "camera.face.yaw_deg": "head yaw, degrees (0 = facing the camera, + = turned to the image's right)",
    "camera.face.pitch_deg": "head pitch, degrees (+ = down)",
    "camera.face.roll_deg": "head roll, degrees (+ = counter-clockwise)",
    "camera.face.dyaw_start_deg": "yaw minus the yaw of the user's first face frame in this session, degrees",
    "camera.face.dpitch_start_deg": "pitch minus the pitch of that first face frame, degrees",
    "camera.face.iod_frac_w": "eye-to-eye distance / frame width (larger = closer to the camera)",
    "camera.face.face_cx": "face centre x, fraction of frame width (0 = left)",
    "camera.face.face_cy": "face centre y, fraction of frame height (0 = top)",
    "camera.body": "the body the pose landmarker follows (one person, not always the main user)",
    "camera.body.seen_share": "share of frames (0-1) with a body found",
    "camera.body.pose_vis_shoulders": "mean visibility (0-1) of the two shoulder points",
    "camera.body.shoulder_cx": "shoulder midpoint x, fraction of frame width",
    "camera.body.shoulder_cy": "shoulder midpoint y, fraction of frame height",
    "camera.heads.head_count": "head boxes found by the head detector in a frame",
    "camera.heads.user_head_share": "share of frames (0-1) with the main user's head box",
    "camera.heads.others": "one entry per other tracked head seen in the span, most seen first",
    "camera.heads.others[].seen_share": "share of frames with this head",
    "camera.heads.others[].rel_dist": "user head height / this head height (1 = same size, above 1 = smaller, i.e. "
                                      "farther from the camera)",
    "camera.heads.others[].lateral": "x offset from the user's head centre, in user head heights (+ = image right)",
    "camera.heads.others[].vertical": "y offset from the user's head centre, in user head heights (+ = lower)",
}


def field_defs(span: float) -> dict:
    return {k: v.format(span=f"{span:g}") for k, v in FIELD_DEFS.items()}
