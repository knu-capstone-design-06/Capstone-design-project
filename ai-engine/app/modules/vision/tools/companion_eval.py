"""Evaluate the companion / behind cues and the sticky main user on recorded takes with per-person labels.

Evaluation only (decision list 2026-10-13, items 3 and 19: recordings evaluate, they never set a value): this tool
replays takes with the current chain, joins the head boxes with person labels and reports the cue distributions, the
agreement of each label class with every boundary of a grid, and how often the main user is the labelled user. It
picks no boundary and writes no value into params.py. From ai-engine/ (vision runtime: requirements.txt +
app/modules/vision/requirements.txt + onnxruntime):

  python -m app.modules.vision.tools.companion_eval replay  --videos DIR --out RUNS [--exclude NAME,...]
                                                           [--step 3 --width 960 --threads 2] [--models DIR]
  python -m app.modules.vision.tools.companion_eval analyze --runs RUNS --truth TRUTH.csv --out DIR [--behind-only]
  python -m app.modules.vision.tools.companion_eval sheets  --runs RUNS --truth TRUTH.csv --videos DIR --out DIR

replay   one replay.py run per DIR/*.mp4 (no value bundle, so the situation output is 'unknown' and only the frame
         rows matter) into RUNS/<take>/ (rows.csv, windows.jsonl, meta.json). The defaults step 3, width 960 and
         threads 2 are the settings of the team's replays of 2026-10-29 (their meta.json), so H1 gives the same boxes
         that the labels were made on.
analyze  reads RUNS/<take>/rows.csv (its head_boxes column) and meta.json and writes, into --out:
           boxes_labelled.csv      one row per head box: the chain's track, role and cues, the label (person, role)
           cues_by_person.csv      per labelled person and cue: n, quartiles and median, per frame and per window
           cues_by_class.csv       the same pooled per label class
           sweep_rel_dist.csv/png  per candidate boundary: the share of each class's frames that agree with the label
           sweep_lateral.csv/png   if the boundary were companion_rel_dist_max / behind_rel_dist_min /
                                   companion_lateral_min (columns.decide_role), per frame and per window
           primary_stability.csv   per labelled take: frames where the main user's box is the labelled user's, the
                                   per-frame rule (columns.choose_primary every frame, the chain before 2026-11-04;
                                   its face box is read from the face_track column, since the face values of a face
                                   outside the main user's box are blank) and the sticky track (the chain now); frames
                                   whose tracked face centre lies outside the main user's box (face_in_primary False:
                                   the face values of those frames are blank in the rows)
           primary_changes.csv     per take: how often the main-user track changes and how many tracks there are
           track_fragments.csv     per labelled person: how many chain tracks carry the person's boxes
           summary.json            counts, the checks below, the grid and the settings read from meta.json
         with --behind-only also
           sweep_behind_only.csv/png  behind or not from rel_dist alone (rel_dist > 1 and >= the boundary, i.e.
                                   decide_role's behind rule without its 'not a companion' condition): per boundary the
                                   share of behind frames (standing, passing) caught and of the others (companion,
                                   helper) left out, per frame and per window
sheets   contact sheets (JPEG) of sampled frames with every box, its track, role and window cues and the label. They
         show the people in the takes: write them only where those people agreed to (not into a repository).

Labels (TRUTH.csv, columns clip,track,frame_from,frame_to,person,role,note): one row per labelled track and frame range.
Their track ids come from the linking the labels were made with (research/56, 56_tracks.py: per take, a box joins the
live track whose last box overlaps it most, IoU > 0, highest first; a track stays live for LABEL_GAP_FRAMES processed
frames), so this tool links the boxes the same way only to read the labels (label_tracks); the chain's own tracks
(columns.HeadTracker) are what is evaluated. Roles: user, companion, behind_standing, behind_passing, helper, leaving.

Cues (columns.py): rel_dist = h_primary / h_box, lateral = (cx_box - cx_primary) / h_primary in pixels, and their
medians over the track's last role_window_s seconds since the main user last changed. The distributions and sweeps use
the frames whose main user (the chain's) is the labelled user, so every cue is measured against the right person; the
frames where it is not are counted in primary_stability.csv. lateral_x_rel = lateral x rel_dist (= the offset in the
other person's own head heights, the '옆 거리 dx / 높이 비' of the design notes) is reported beside the two cues the
chain uses. The grid (GRID_*) only spans the values to show; it is not a proposal.

Checks in summary.json: the window medians recomputed from the per-frame cues equal the chain's (rounding only), and the
per-person frame counts, for a comparison with the labels' own analysis.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import os
import sys

import numpy as np

LABEL_GAP_FRAMES = 10                      # the labels' linking (research/56 56_tracks.py GAP_FRAMES; see docstring)
CLASSES = ("companion", "behind_standing", "helper", "behind_passing")      # label roles other than the user's
CLASS_KO = {"companion": "일행(옆)", "behind_standing": "뒤에 선 사람(줄)", "helper": "돕는 사람",
            "behind_passing": "지나간 사람"}
# Claude's evaluation grid: it spans the cue values seen per person in research/56 (rel_dist 0.8 ~ 2.6, horizontal
# offset up to about 2 head widths) with margin on both sides; it shows curves and decides nothing.
GRID_REL = tuple(round(0.5 + 0.05 * k, 2) for k in range(71))        # 0.50 ... 4.00
GRID_LAT = tuple(round(0.05 * k, 2) for k in range(81))              # 0.00 ... 4.00
CUES = ("rel_dist", "abs_lateral", "lateral_x_rel")


# --- replay ---------------------------------------------------------------------------------------------------------
def cmd_replay(a) -> int:
    from app.modules.vision import replay
    exclude = {x.strip() for x in (a.exclude or "").split(",") if x.strip()}
    takes = sorted(os.path.splitext(n)[0] for n in os.listdir(a.videos) if n.lower().endswith(".mp4"))
    takes = [t for t in takes if t not in exclude]
    print(f"{len(takes)} takes (excluded: {sorted(exclude) or 'none'})", flush=True)
    for k, take in enumerate(takes, 1):
        args = ["--video", os.path.join(a.videos, take + ".mp4"), "--out", os.path.join(a.out, take),
                "--step", str(a.step), "--width", str(a.width), "--threads", str(a.threads), "--overwrite"]
        if a.models:
            args += ["--models", a.models]
        print(f"[{k}/{len(takes)}] {take}", flush=True)
        replay.main(args)
    return 0


# --- reading the runs -----------------------------------------------------------------------------------------------
def _f(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def load_run(folder: str) -> tuple:
    """(frames, meta): frames = [{frame_idx, t_s, src_frame, face_xy, primary_track, primary_from, boxes: [dict]}]."""
    from app.modules.vision.columns import face_xy
    with open(os.path.join(folder, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    frames = []
    with open(os.path.join(folder, "rows.csv"), encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            cell = r.get("head_boxes")
            if cell is None:
                raise ValueError(f"{folder}: rows.csv has no head_boxes column (replay with the 2026-11-04 chain)")
            boxes = json.loads(cell) if cell else []
            for b in boxes:
                b["x0"], b["x1"] = b["cx"] - b["w"] / 2.0, b["cx"] + b["w"] / 2.0
                b["y0"], b["y1"] = b["cy"] - b["h"] / 2.0, b["cy"] + b["h"] / 2.0
            in_primary = {"True": True, "False": False}.get(r.get("face_in_primary"))
            frames.append({"frame_idx": int(r["frame_idx"]), "t_s": float(r["t_s"]), "src_frame": r["src_frame"],
                           "face_xy": face_xy(r), "primary_track": None if r["primary_track"] == ""
                           else int(float(r["primary_track"])), "primary_from": r["primary_from"] or None,
                           "face_in_primary": in_primary, "has_face_track": "face_track" in r,
                           "face_track": None if not r.get("face_track") else int(float(r["face_track"])),
                           "boxes": boxes})
    return frames, meta


def label_tracks(frames: list) -> None:
    """Adds 'label_track' to every box: the linking the labels were made with (module docstring)."""
    from app.modules.vision.columns import box_iou
    live, next_id = {}, 1                                   # label track -> (last box, last frame)
    for fr in frames:
        f = fr["frame_idx"]
        boxes = [(b["x0"], b["y0"], b["x1"], b["y1"]) for b in fr["boxes"]]
        cands = sorted(((box_iou(b, lb), i, t) for i, b in enumerate(boxes) for t, (lb, lf) in live.items()
                        if f - lf <= LABEL_GAP_FRAMES), reverse=True)
        used_b, used_t = set(), set()
        for v, i, t in cands:
            if v <= 0 or i in used_b or t in used_t:
                continue
            fr["boxes"][i]["label_track"] = t
            used_b.add(i), used_t.add(t)
        for i, b in enumerate(fr["boxes"]):
            if i not in used_b:
                b["label_track"], next_id = next_id, next_id + 1
            live[b["label_track"]] = (boxes[i], f)


def load_truth(path: str) -> dict:
    """{take: [(label track, frame_from, frame_to, person, role)]}."""
    out = collections.defaultdict(list)
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            out[r["clip"]].append((int(r["track"]), int(r["frame_from"]), int(r["frame_to"]), r["person"], r["role"]))
    return out


def attach_labels(frames: list, truth_rows: list) -> None:
    for fr in frames:
        for b in fr["boxes"]:
            hit = [(p, role) for t, lo, hi, p, role in truth_rows if t == b["label_track"] and lo <= fr["frame_idx"] <= hi]
            b["person"], b["label"] = hit[0] if hit else (None, None)


def window_medians(frames: list, window_s: float) -> float:
    """Recomputes the chain's window medians from the per-frame cues (columns.HeadPeople: a track's last window_s
    seconds since the main user last changed) and adds lateral_x_rel and its median; returns the largest difference
    from the chain's own rel_dist_med / lateral_med (rounding only, as a check)."""
    since, past, worst = None, collections.defaultdict(list), 0.0
    for fr in frames:
        t = fr["t_s"]
        if fr["primary_from"] in ("face", "largest"):
            since, past = t, collections.defaultdict(list)
        for b in fr["boxes"]:
            rel, lat = b.get("rel_dist"), b.get("lateral")
            b["abs_lateral"] = None if lat is None else abs(lat)
            b["lateral_x_rel"] = None if rel is None or lat is None else abs(lat) * rel
            if b["role"] == "primary":
                continue
            if rel is not None:
                past[b["track"]].append((t, rel, lat, abs(lat) * rel))
            keep = [x for x in past[b["track"]] if x[0] >= t - window_s and (since is None or x[0] >= since)]
            past[b["track"]] = keep
            if keep:
                med = [float(np.median([x[k] for x in keep])) for k in (1, 2, 3)]
                for mine, theirs in ((med[0], b.get("rel_dist_med")), (med[1], b.get("lateral_med"))):
                    worst = max(worst, abs(mine - theirs)) if theirs is not None else math.inf
                b["w_rel_dist"], b["w_abs_lateral"], b["w_lateral_x_rel"] = med[0], abs(med[1]), med[2]
            else:
                if b.get("rel_dist_med") is not None:
                    worst = math.inf
                b["w_rel_dist"] = b["w_abs_lateral"] = b["w_lateral_x_rel"] = None
    return worst


# --- analysis -------------------------------------------------------------------------------------------------------
def _quart(values: list) -> dict:
    v = np.asarray([x for x in values if x is not None], dtype=np.float64)
    if not len(v):
        return {"n": 0, "q1": None, "median": None, "q3": None}
    q1, med, q3 = np.percentile(v, [25, 50, 75])
    return {"n": int(len(v)), "q1": round(float(q1), 3), "median": round(float(med), 3), "q3": round(float(q3), 3)}


def _write_csv(path: str, rows: list, fields: list) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def _user_box(fr: dict):
    users = [b for b in fr["boxes"] if b["label"] == "user"]
    return users[0] if users else None


def _sweep(points: dict, grid: tuple, rules: list) -> list:
    """points = {class: [values]}; rules = [(column, class, test(value, b))] -> one row per boundary."""
    rows = []
    for g in grid:
        row = {"boundary": g}
        for col, cls, test in rules:
            vals = [v for v in points.get(cls, []) if v is not None]
            row[col] = round(sum(test(v, g) for v in vals) / len(vals), 4) if vals else None
        rows.append(row)
    return rows


def _plot(path: str, rows: list, panels: list, xlabel: str, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for reg in (r"C:\Windows\Fonts\malgun.ttf", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"):
        if os.path.isfile(reg):
            font_manager.fontManager.addfont(reg)
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=reg).get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False
    series = {"companion": "#2a78d6", "behind_standing": "#eb6834", "helper": "#1baf7a", "behind_passing": "#eda100"}
    ink, muted, grid = "#0b0b0b", "#898781", "#e1e0d9"
    fig, axes = plt.subplots(1, len(panels), figsize=(6.2 * len(panels), 4.4), sharey=True, facecolor="#fcfcfb")
    axes = np.atleast_1d(axes)
    x = [r["boundary"] for r in rows]
    for ax, (subtitle, lines) in zip(axes, panels):
        ax.set_facecolor("#fcfcfb")
        for col, cls, label, dashed in lines:
            y = [r[col] for r in rows]
            if all(v is None for v in y):
                continue
            ax.plot(x, [np.nan if v is None else v for v in y], color=series[cls], lw=2,
                    ls="--" if dashed else "-", label=label)
        ax.set_title(subtitle, fontsize=10, color=ink, loc="left")
        ax.set_xlabel(xlabel, fontsize=9, color=ink)
        ax.grid(True, color=grid, lw=0.6)
        ax.set_ylim(-0.02, 1.02)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(muted)
        ax.tick_params(colors=muted, labelsize=8)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=8, frameon=False, loc="center right")
    axes[0].set_ylabel("라벨과 맞는 프레임 비율", fontsize=9, color=ink)
    fig.suptitle(title, fontsize=10.5, color=ink, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)


def cmd_analyze(a) -> int:
    from app.modules.vision.columns import choose_primary
    truth = load_truth(a.truth)
    os.makedirs(a.out, exist_ok=True)
    takes = sorted(d for d in os.listdir(a.runs) if os.path.isfile(os.path.join(a.runs, d, "rows.csv")))
    all_boxes, stability, changes, fragments, checks, settings = [], [], [], [], {}, {}
    cue_points = collections.defaultdict(list)          # (stage, cue, class) -> values
    per_person = collections.defaultdict(list)          # (take, person, class, stage, cue) -> values
    for take in takes:
        frames, meta = load_run(os.path.join(a.runs, take))
        chain = {k: v["value"] for k, v in meta["bundle"]["chain"].items()}
        settings[take] = {k: chain[k] for k in ("primary_rule", "track_iou_min", "track_max_gap_s", "role_window_s",
                                                "companion_rel_dist_max", "companion_lateral_min",
                                                "behind_rel_dist_min")} | {"step": meta["settings"]["step"],
                                                                           "width": meta["settings"]["width"],
                                                                           "threads": meta["settings"]["threads"]}
        checks.setdefault("median_recompute_max_diff", {})[take] = window_medians(frames, chain["role_window_s"])
        sticky = [fr["primary_track"] for fr in frames if fr["primary_track"] is not None]
        changes.append({"take": take, "frames": len(frames),
                        "frames_with_heads": sum(bool(fr["boxes"]) for fr in frames),
                        "max_heads": max((len(fr["boxes"]) for fr in frames), default=0),
                        "tracks": len({b["track"] for fr in frames for b in fr["boxes"]}),
                        "primary_tracks": len(set(sticky)),
                        "primary_changes": sum(1 for p, q in zip(sticky, sticky[1:]) if p != q),
                        "labelled": take in truth})
        if take not in truth:
            continue
        label_tracks(frames)
        attach_labels(frames, truth[take])
        n_user = n_old = n_sticky = n_unseen = n_face = n_face_out = 0
        old_wrong = collections.Counter()
        sticky_wrong = collections.Counter()
        for fr in frames:
            boxes = fr["boxes"]
            xyxy = [(b["x0"], b["y0"], b["x1"], b["y1"]) for b in boxes]
            k, _ = choose_primary(xyxy, fr["face_xy"], chain["primary_rule"])
            if fr["has_face_track"] and boxes:        # the face's own box (face values may be blank in the row)
                by_face = [i for i, b in enumerate(boxes) if b["track"] == fr["face_track"]]
                k = by_face[0] if by_face and chain["primary_rule"] == "face_then_largest" else \
                    choose_primary(xyxy, None, chain["primary_rule"])[0]
            prim = next((b for b in boxes if b["role"] == "primary"), None)
            for i, b in enumerate(boxes):
                b["primary_old"] = i == k
                all_boxes.append({"take": take, "frame_idx": fr["frame_idx"], "t_s": fr["t_s"], **b})
            user = _user_box(fr)
            if fr["has_face_track"]:
                n_face += fr["face_in_primary"] is not None
                n_face_out += fr["face_in_primary"] is False
            elif prim is not None and fr["face_xy"] is not None:
                n_face += 1
                fx, fy = fr["face_xy"]
                n_face_out += not (prim["x0"] <= fx <= prim["x1"] and prim["y0"] <= fy <= prim["y1"])
            if user is not None:
                n_user += 1
                n_old += boxes[k]["label"] == "user"
                if boxes[k]["label"] != "user":
                    old_wrong[boxes[k]["person"] or "?"] += 1
                if prim is None:
                    n_unseen += 1
                elif prim["label"] == "user":
                    n_sticky += 1
                else:
                    sticky_wrong[prim["person"] or "?"] += 1
            if prim is None or prim["label"] != "user":
                continue                                        # cues against the wrong person: counted above only
            for b in boxes:
                if b["role"] == "primary" or b["label"] not in CLASSES:
                    continue
                for cue in CUES:
                    for stage, key in (("frame", cue), ("window", "w_" + cue)):
                        cue_points[(stage, cue, b["label"])].append(b.get(key))
                        per_person[(take, b["person"], b["label"], stage, cue)].append(b.get(key))
        users = sorted({b["person"] for fr in frames for b in fr["boxes"] if b["label"] == "user"})
        stability.append({"take": take, "users": "/".join(users), "user_frames": n_user,
                          "per_frame_rule_user": n_old, "per_frame_rule_share": round(n_old / n_user, 4) if n_user else None,
                          "per_frame_rule_other": dict(old_wrong) or "",
                          "sticky_user": n_sticky, "sticky_share": round(n_sticky / n_user, 4) if n_user else None,
                          "sticky_other": dict(sticky_wrong) or "", "sticky_primary_unseen": n_unseen,
                          "face_frames_with_primary": n_face, "face_outside_primary": n_face_out})
        by_person = collections.defaultdict(list)
        for fr in frames:
            for b in fr["boxes"]:
                if b["person"] is not None:
                    by_person[(b["person"], b["label"])].append(b["track"])
        for (person, label), tracks in sorted(by_person.items()):
            c = collections.Counter(tracks)
            fragments.append({"take": take, "person": person, "label": label, "frames": len(tracks),
                              "chain_tracks": len(c), "largest_track_frames": max(c.values()),
                              "tracks": " ".join(f"{t}:{n}" for t, n in sorted(c.items()))})
    box_fields = ["take", "frame_idx", "t_s", "track", "cx", "cy", "w", "h", "score", "role", "rel_dist", "lateral",
                  "rel_dist_med", "lateral_med", "lateral_x_rel", "w_lateral_x_rel", "label_track", "person", "label",
                  "primary_old"]
    _write_csv(os.path.join(a.out, "boxes_labelled.csv"), all_boxes, box_fields)
    q = ["n", "q1", "median", "q3"]
    _write_csv(os.path.join(a.out, "cues_by_person.csv"),
               [{"take": t, "person": p, "class": c, "stage": s, "cue": cue, **_quart(v)}
                for (t, p, c, s, cue), v in sorted(per_person.items())], ["take", "person", "class", "stage", "cue"] + q)
    persons = collections.Counter((c, s, cue) for (t, p, c, s, cue) in per_person)
    _write_csv(os.path.join(a.out, "cues_by_class.csv"),
               [{"class": c, "persons": persons[(s, cue, c)] if False else persons[(c, s, cue)], "stage": s, "cue": cue,
                 **_quart(v)} for (s, cue, c), v in sorted(cue_points.items(), key=lambda x: (CLASSES.index(x[0][2]),
                                                                                             x[0][1], x[0][0]))],
               ["class", "persons", "stage", "cue"] + q)
    # sweeps: agreement with the label if the grid value were the boundary (columns.decide_role, one condition each)
    le, ge, lt, gt = (lambda v, g: v <= g), (lambda v, g: v >= g), (lambda v, g: v < g), (lambda v, g: v > g)
    rel_rows, lat_rows = [], []
    for stage in ("frame", "window"):
        pts = {c: cue_points.get((stage, "rel_dist", c), []) for c in CLASSES}
        rel = _sweep(pts, GRID_REL, [
            (f"{stage}_cmax_companion_le", "companion", le), (f"{stage}_cmax_behind_gt", "behind_standing", gt),
            (f"{stage}_cmax_helper_le", "helper", le),
            (f"{stage}_bmin_behind_ge", "behind_standing", ge), (f"{stage}_bmin_companion_lt", "companion", lt),
            (f"{stage}_bmin_passing_ge", "behind_passing", ge)])
        pts = {c: cue_points.get((stage, "abs_lateral", c), []) for c in CLASSES}
        lat = _sweep(pts, GRID_LAT, [
            (f"{stage}_latmin_companion_ge", "companion", ge), (f"{stage}_latmin_behind_lt", "behind_standing", lt),
            (f"{stage}_latmin_helper_ge", "helper", ge)])
        rel_rows = rel if not rel_rows else [x | y for x, y in zip(rel_rows, rel)]
        lat_rows = lat if not lat_rows else [x | y for x, y in zip(lat_rows, lat)]
    _write_csv(os.path.join(a.out, "sweep_rel_dist.csv"), rel_rows, list(rel_rows[0]))
    _write_csv(os.path.join(a.out, "sweep_lateral.csv"), lat_rows, list(lat_rows[0]))
    _plot(os.path.join(a.out, "sweep_rel_dist.png"), rel_rows, [
        ("companion_rel_dist_max = x일 때 (상대 거리 ≤ x → 일행 조건 통과)",
         [("window_cmax_companion_le", "companion", "일행: 통과(맞음)", False),
          ("window_cmax_behind_gt", "behind_standing", "뒤에 선 사람: 막힘(맞음)", False),
          ("frame_cmax_companion_le", "companion", "일행, 프레임마다", True),
          ("frame_cmax_behind_gt", "behind_standing", "뒤에 선 사람, 프레임마다", True)]),
        ("behind_rel_dist_min = x일 때 (상대 거리 ≥ x → 뒤 사람 조건 통과)",
         [("window_bmin_behind_ge", "behind_standing", "뒤에 선 사람: 통과(맞음)", False),
          ("window_bmin_companion_lt", "companion", "일행: 막힘(맞음)", False),
          ("frame_bmin_behind_ge", "behind_standing", "뒤에 선 사람, 프레임마다", True),
          ("frame_bmin_companion_lt", "companion", "일행, 프레임마다", True)])],
        "경계 후보 x (상대 거리 = 주 사용자 머리 높이 ÷ 그 머리 높이)",
        "상대 거리 경계 후보별 라벨 일치율\n실선: 트랙별 2초 중앙값, 점선: 프레임마다. 10-28 팀 촬영, 평가 전용")
    _plot(os.path.join(a.out, "sweep_lateral.png"), lat_rows, [
        ("companion_lateral_min = x일 때 (|옆 거리| ≥ x → 일행 조건 통과)",
         [("window_latmin_companion_ge", "companion", "일행: 통과(맞음)", False),
          ("window_latmin_behind_lt", "behind_standing", "뒤에 선 사람: 막힘(맞음)", False),
          ("frame_latmin_companion_ge", "companion", "일행, 프레임마다", True),
          ("frame_latmin_behind_lt", "behind_standing", "뒤에 선 사람, 프레임마다", True)])],
        "경계 후보 x (|옆 거리| = 머리 중심 가로 차 ÷ 주 사용자 머리 높이)",
        "옆 거리 경계 후보별 라벨 일치율\n실선: 트랙별 2초 중앙값, 점선: 프레임마다. 10-28 팀 촬영, 평가 전용")
    if a.behind_only:
        behind_only(a.out, cue_points)
    _write_csv(os.path.join(a.out, "primary_stability.csv"), stability, list(stability[0]) if stability else ["take"])
    _write_csv(os.path.join(a.out, "primary_changes.csv"), changes, list(changes[0]) if changes else ["take"])
    _write_csv(os.path.join(a.out, "track_fragments.csv"), fragments,
               list(fragments[0]) if fragments else ["take"])
    frames_per_person = collections.Counter()
    for b in all_boxes:
        if b["person"] is not None:
            frames_per_person[f"{b['take']} {b['person']} {b['label']}"] += 1
    summary = {"takes": len(takes), "labelled_takes": len(stability), "truth": os.path.abspath(a.truth),
               "settings": settings, "grid": {"rel_dist": [GRID_REL[0], GRID_REL[-1], 0.05],
                                              "abs_lateral": [GRID_LAT[0], GRID_LAT[-1], 0.05]},
               "checks": checks, "label_frames_per_person": dict(sorted(frames_per_person.items())),
               "cue_frames": {f"{s} {cue} {c}": len([v for v in vals if v is not None])
                              for (s, cue, c), vals in sorted(cue_points.items())}}
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({k: summary[k] for k in ("takes", "labelled_takes")}), flush=True)
    return 0


def behind_only(out: str, cue_points: dict) -> None:
    """sweep_behind_only.csv / .png (module docstring): rel_dist alone, behind = rel_dist > 1 and >= boundary."""
    from app.modules.vision.columns import SMALLER_THAN_USER
    caught = lambda v, g: v > SMALLER_THAN_USER and v >= g
    left_out = lambda v, g: not caught(v, g)
    rows = []
    for stage in ("frame", "window"):
        pts = {c: cue_points.get((stage, "rel_dist", c), []) for c in CLASSES}
        pts["behind"] = pts["behind_standing"] + pts["behind_passing"]
        pts["not_behind"] = pts["companion"] + pts["helper"]
        part = _sweep(pts, GRID_REL, [
            (f"{stage}_behind_caught", "behind", caught), (f"{stage}_not_behind_left_out", "not_behind", left_out),
            (f"{stage}_behind_standing_caught", "behind_standing", caught),
            (f"{stage}_behind_passing_caught", "behind_passing", caught),
            (f"{stage}_companion_left_out", "companion", left_out), (f"{stage}_helper_left_out", "helper", left_out)])
        rows = part if not rows else [x | y for x, y in zip(rows, part)]
    _write_csv(os.path.join(out, "sweep_behind_only.csv"), rows, list(rows[0]))
    _plot(os.path.join(out, "sweep_behind_only.png"), rows, [
        ("behind_rel_dist_min = x일 때, 상대 거리만으로 (상대 거리 > 1이고 ≥ x → 뒤 사람)",
         [("window_behind_caught", "behind_standing", "뒤 사람(줄 · 지나감): 잡힘(맞음)", False),
          ("window_not_behind_left_out", "companion", "뒤 사람 아님(일행 · 돕는 사람): 빠짐(맞음)", False),
          ("frame_behind_caught", "behind_standing", "뒤 사람, 프레임마다", True),
          ("frame_not_behind_left_out", "companion", "뒤 사람 아님, 프레임마다", True)])],
        "경계 후보 x (상대 거리 = 주 사용자 머리 높이 ÷ 그 머리 높이)",
        "뒤 사람인지 아닌지를 상대 거리만으로 가를 때의 라벨 일치율\n실선: 트랙별 2초 중앙값, 점선: 프레임마다. "
        "일행 조건 없이. 10-28 팀 촬영, 평가 전용")


# --- contact sheets -------------------------------------------------------------------------------------------------
def cmd_sheets(a) -> int:
    import cv2
    from app.modules.vision.sources import VideoFileSource
    truth = load_truth(a.truth)
    os.makedirs(a.out, exist_ok=True)
    colour = {"user": (25, 158, 112), "companion": (214, 120, 42), "behind_standing": (52, 104, 235),
              "behind_passing": (0, 161, 237), "helper": (164, 123, 232), "leaving": (136, 142, 143), None: (200, 200, 200)}
    for take in sorted(truth):
        folder = os.path.join(a.runs, take)
        if not os.path.isfile(os.path.join(folder, "rows.csv")):
            continue
        frames, meta = load_run(folder)
        window_medians(frames, meta["bundle"]["chain"]["role_window_s"]["value"])
        label_tracks(frames)
        attach_labels(frames, truth[take])
        multi = [fr for fr in frames if len(fr["boxes"]) >= 2] or frames
        pick = {multi[int(round(i))]["frame_idx"] for i in np.linspace(0, len(multi) - 1, min(a.per_take, len(multi)))}
        wrong = [fr["frame_idx"] for fr in frames if _user_box(fr) is not None
                 and not any(b["role"] == "primary" and b["label"] == "user" for b in fr["boxes"])]
        pick |= set(wrong[:: max(1, len(wrong) // 4)][:4])            # up to 4 frames whose main user is not the user
        by_idx = {fr["frame_idx"]: fr for fr in frames}
        tiles = {}
        src = VideoFileSource(os.path.join(a.videos, take + ".mp4"), step=meta["settings"]["step"],
                              width=meta["settings"]["width"])
        for frame in src:
            if frame.index not in pick:
                continue
            img = frame.image.copy()
            H, W = img.shape[:2]
            fr = by_idx[frame.index]
            for b in fr["boxes"]:
                p0, p1 = (int(b["x0"] * W), int(b["y0"] * H)), (int(b["x1"] * W), int(b["y1"] * H))
                c = colour.get(b["label"], colour[None])
                cv2.rectangle(img, p0, p1, c, 9 if b["role"] == "primary" else 4)
                text = [f"T{b['track']} {b['role'][:4]}", f"label {b['person'] or '-'} {(b['label'] or '-')[:8]}"]
                if b["role"] != "primary" and b.get("w_rel_dist") is not None:
                    text.append(f"d {b['w_rel_dist']:.2f} x {b['w_abs_lateral']:.2f}")
                for j, s in enumerate(text):
                    cv2.putText(img, s, (p0[0] + 4, max(40, p0[1] - 12 - 44 * (len(text) - 1 - j))),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.3, c, 3)
            flag = "" if frame.index not in wrong else "  MAIN USER != LABEL"
            cv2.putText(img, f"{take} f{frame.index} t{fr['t_s']:.1f}{flag}", (10, H - 24), cv2.FONT_HERSHEY_SIMPLEX,
                        1.5, (0, 0, 255), 4)
            tiles[frame.index] = cv2.resize(img, (360, int(H * 360 / W)), interpolation=cv2.INTER_AREA)
            if len(tiles) == len(pick):
                break
        ims = [tiles[i] for i in sorted(tiles)]
        while len(ims) % 6:
            ims.append(np.zeros_like(ims[0]))
        grid = np.vstack([np.hstack(ims[i:i + 6]) for i in range(0, len(ims), 6)])
        path = os.path.join(a.out, f"sheet_{take}.jpg")
        cv2.imwrite(path, grid, [cv2.IMWRITE_JPEG_QUALITY, 82])
        print(path, f"frames {sorted(tiles)}", f"main user != label: {len(wrong)}", flush=True)
    return 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--videos", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--exclude", default="")
    r.add_argument("--step", type=int, default=3)
    r.add_argument("--width", type=int, default=960)
    r.add_argument("--threads", type=int, default=2)
    r.add_argument("--models", default=None)
    n = sub.add_parser("analyze")
    n.add_argument("--runs", required=True)
    n.add_argument("--truth", required=True)
    n.add_argument("--out", required=True)
    n.add_argument("--behind-only", action="store_true",
                   help="also write sweep_behind_only.csv / .png: behind or not from rel_dist alone")
    s = sub.add_parser("sheets")
    s.add_argument("--runs", required=True)
    s.add_argument("--truth", required=True)
    s.add_argument("--videos", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--per-take", type=int, default=8)
    a = ap.parse_args(argv)
    return {"replay": cmd_replay, "analyze": cmd_analyze, "sheets": cmd_sheets}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
