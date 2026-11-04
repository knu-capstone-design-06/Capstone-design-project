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
  python -m app.modules.vision.tools.companion_eval ablation --runs RUNS --truth TRUTH.csv --videos DIR --out DIR
  python -m app.modules.vision.tools.companion_eval inventory --runs RUNS --truth TRUTH.csv --scenes SCENES.csv --out DIR

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
ablation the four combinations of cues and tracking on the same recorded H1 boxes (no H1 run; each frame's boxes are
         read from head_boxes), over every labelled frame of the labelled takes:
           a  old cues without tracking: the main user chosen every frame (choose_primary) and the roles of the chain
              before 2026-11-04 (old_roles: area ratio OLD_COMPANION_AREA, centre distance OLD_COMPANION_DIST head
              widths, behind = smaller than OLD_BEHIND_AREA x the user's area) = the behaviour before the change
           b  old cues with the sticky main-user track (columns.HeadPeople's main user, old_roles against it)
           c  new cues without tracking: rel_dist and lateral of every frame against the main user chosen that frame,
              no window median
           d  new cues, tracking and the role_window_s median: columns.HeadPeople as the chain runs it
         It needs rows whose face position is kept (face_cx, face_cy: a replay from before the face check, or rows
         where face_in_primary is never False), since the per-frame rule and the face check read it, and --videos for
         each take's frame size. Writes ablation_geometry_tracking.csv (one value per row: section, variant, take,
         class, cue, boundary, measure, value) and ablation_geometry_tracking.png. Sections: primary (per take: frames
         with the labelled user's box, frames whose main user is that box, frames without a main-user box, switches
         of the person behind the main-user box), handover (frames and seconds from the labelled change of user to the
         first frame whose main user is the new user), face (frames whose tracked face centre lies outside the main
         user's box), old_roles (a, b: the old roles per label class), separation (c, d: rel_dist and |lateral| per
         class, d per frame and per window) and grid (c, d: the sweep agreements at every grid value). Checks against
         the recorded replay (d's tracks, roles and medians; a's main user) go to ablation_checks.json.
         Also ablation_grid_wide.csv: one row per cue, rule and grid value with, for c_frame, d_frame (new cues and
         tracking, every frame, no median) and d_window, the agreement of each label class and, apart from them, the
         helper acceptance rate (the share of helpers passing that rule's condition; helpers are neither companion nor
         queue, so it is not an agreement); and fig_e1_paper.png (7.0 x 2.4 in, 300 dpi, fonts 8 pt and up).
inventory inclusion_table.csv (one row per replayed take: scene and people from the scene labels, role instances and
         frames from the person labels and the rows, labelled or not and why) and parameter_sources.csv (every value
         the chain's head part and this tool use, with its source tag). Needs --scenes (the scene label CSV: video,
         user, others, scene_key, scene_label).

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
from dataclasses import fields as fields_of

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


# --- inventory: which takes, which values -------------------------------------------------------------------------
def _people(text: str) -> list:
    """The person codes A-D named in a scene-label field ('2 behind (B·A)' -> ['A', 'B'])."""
    return sorted(set(ch for ch in (text or "") if ch in "ABCD"))


def cmd_inventory(a) -> int:
    from app.modules.vision.columns import FACE_VALUE_COLUMNS, SMALLER_THAN_USER
    from app.modules.vision.params import PilotParams
    truth = load_truth(a.truth)
    with open(a.scenes, encoding="utf-8-sig", newline="") as f:
        scenes = {r["video"]: r for r in csv.DictReader(f)}
    os.makedirs(a.out, exist_ok=True)
    rows, settings = [], None
    roles_of = {"companion": "companion", "behind_standing": "queue", "helper": "helper", "behind_passing": "passer"}
    for take in sorted(d for d in os.listdir(a.runs) if os.path.isfile(os.path.join(a.runs, d, "rows.csv"))):
        frames, meta = load_run(os.path.join(a.runs, take))
        settings = settings or meta["settings"]
        sc = scenes.get(take, {})
        row = {"take": take, "scene_key": sc.get("scene_key"), "scene_label": sc.get("scene_label"),
               "user_in_plan": sc.get("user"), "others_in_plan": sc.get("others"), "frames": len(frames),
               "frames_with_heads": sum(bool(fr["boxes"]) for fr in frames),
               "frames_2plus_heads": sum(len(fr["boxes"]) >= 2 for fr in frames),
               "max_heads": max((len(fr["boxes"]) for fr in frames), default=0)}
        if take in truth:
            label_tracks(frames)
            attach_labels(frames, truth[take])
            persons = collections.defaultdict(set)
            for _, _, _, person, role in truth[take]:
                persons[roles_of.get(role, role)].add(person)
            row["identities"] = " ".join(sorted({p for _, _, _, p, _ in truth[take]}))
            for r in ("companion", "queue", "helper", "passer"):
                row[f"{r}_n"] = None if "X" in persons[r] else len(persons[r])
            row["user_frames"] = sum(any(b["label"] == "user" for b in fr["boxes"]) for fr in frames)
            row["role_box_frames"] = sum(b["label"] in CLASSES for fr in frames for b in fr["boxes"])
            row["labelled"] = "yes"
            notes = []
            if "X" in persons["passer"]:
                notes.append("지나간 사람은 라벨에서 사람을 나누지 않음(X; 라벨 메모: B · A · D가 뒤로 지나감)")
            if any(lo > 0 for _, lo, _, _, _ in truth[take]):
                notes.append("사용자 교체 프레임은 Claude가 확인 시트로 정한 값(56_truth.csv)")
            row["note"] = "; ".join(notes)
        else:
            row["identities"] = " ".join(_people(sc.get("user", "")) + [p for p in _people(sc.get("others", ""))
                                                                          if p not in _people(sc.get("user", ""))])
            for r in ("companion", "queue", "helper", "passer"):
                row[f"{r}_n"] = 0 if str(sc.get("others", "")).strip() == "0" else None
            row["labelled"] = "no"
            reason = "장면 라벨의 다른 사람 0명(사람 라벨은 다른 사람이 있는 영상에만 붙임)" \
                if str(sc.get("others", "")).strip() == "0" else "사람 라벨 없음"
            if row["max_heads"] >= 2:
                reason += f"; 그래도 머리 상자가 2개 이상인 프레임 {row['frames_2plus_heads']}개"
            row["reason_not_labelled"] = reason
        rows.append(row)
    fields = ["take", "scene_key", "scene_label", "user_in_plan", "others_in_plan", "identities", "companion_n",
              "queue_n", "helper_n", "passer_n", "frames", "frames_with_heads", "frames_2plus_heads", "max_heads",
              "user_frames", "role_box_frames", "labelled", "reason_not_labelled", "note"]
    _write_csv(os.path.join(a.out, "inclusion_table.csv"), rows, fields)

    src = PilotParams.sources()
    unit = {f.name: f.metadata["unit"] for f in fields_of(PilotParams)}
    p = PilotParams()

    def tag(text):
        if text.startswith("정할 수 없음"):
            return "정할 수 없음"
        for key, t in (("[파일럿]", "[파일럿]"), ("관행값", "[관행값]"), ("데이터", "[데이터]")):
            if key in text:
                return t
        return "[결정]" if "결정" in text else "[출처]"
    params = []
    for name in ("head_score_min", "head_nms_iou", "primary_rule", "track_iou_min", "track_max_gap_s", "role_window_s",
                 "companion_rel_dist_max", "companion_lateral_min", "behind_rel_dist_min", "segment_s",
                 "mouth_baseline_s"):
        params.append({"name": name, "value": getattr(p, name), "unit": unit[name], "where": "params.PilotParams",
                       "used_by": "코드(머리 상자 · 트랙 · 역할)" if name not in ("segment_s", "mouth_baseline_s")
                       else "코드(다른 용도) · 위 두 시작값의 출처", "source_tag": tag(src[name]), "source": src[name]})
    params += [
        {"name": "SMALLER_THAN_USER", "value": SMALLER_THAN_USER, "unit": "상대 거리", "where": "columns.py",
         "used_by": "코드(뒤 사람 조건)", "source_tag": "[결정]",
         "source": "결정 §3 '주 사용자보다 작은 상자': 상대 거리 > 1 = 주 사용자보다 작은 머리 상자(정의)"},
        {"name": "FACE_VALUE_COLUMNS", "value": len(FACE_VALUE_COLUMNS), "unit": "열 개수", "where": "columns.py",
         "used_by": "코드(얼굴 포함 검사에서 비우는 열)", "source_tag": "[Claude]",
         "source": "Face Landmarker 얼굴에서 나오는 features.COLUMNS: " + " ".join(FACE_VALUE_COLUMNS)},
        {"name": "replay step / width / threads", "value": f"{settings['step']} / {settings['width']} / "
                                                          f"{settings['threads']}",
         "unit": "프레임 · px · 스레드", "where": "companion_eval replay(기본값)", "used_by": "평가(재생)",
         "source_tag": "[재현]", "source": "10-29 팀 재생(datasets/team_recording_2026-10-28/replay/*/meta.json)과 조사 56의 "
                                         "설정과 같음: 같은 H1 상자를 얻으려고"},
        {"name": "LABEL_GAP_FRAMES", "value": LABEL_GAP_FRAMES, "unit": "처리 프레임", "where": "companion_eval",
         "used_by": "평가(사람 라벨을 읽는 연결)", "source_tag": "[Claude]",
         "source": "조사 56 56_tracks.py의 연결(IoU > 0, 1초 = 10 처리 프레임): 라벨을 만든 방식 그대로 읽으려고"},
        {"name": "GRID_REL", "value": f"{GRID_REL[0]}~{GRID_REL[-1]}, 0.05 간격", "unit": "상대 거리",
         "where": "companion_eval", "used_by": "평가(경계 후보 격자)", "source_tag": "[Claude]",
         "source": "조사 56의 사람별 값 범위(0.8~2.6)를 넉넉히 덮는 평가 격자. 값을 고르지 않음"},
        {"name": "GRID_LAT", "value": f"{GRID_LAT[0]}~{GRID_LAT[-1]}, 0.05 간격", "unit": "주 사용자 머리 높이",
         "where": "companion_eval", "used_by": "평가(경계 후보 격자)", "source_tag": "[Claude]",
         "source": "같은 평가 격자. 값을 고르지 않음"},
        {"name": "OLD_COMPANION_AREA / OLD_COMPANION_DIST / OLD_BEHIND_AREA",
         "value": f"{OLD_COMPANION_AREA} / {OLD_COMPANION_DIST} / {OLD_BEHIND_AREA}", "unit": "넓이 비 · 머리 폭 · 넓이 비",
         "where": "companion_eval", "used_by": "평가(ablation의 a · b, 바꾸기 전 동작을 되살림)",
         "source_tag": "[파일럿] · [파일럿] · [결정]",
         "source": "2026-11-04 전 params.py(커밋 3705060)의 companion_min_area_ratio · companion_max_dist_widths · "
                   "behind_max_area_ratio"},
        {"name": "HANDOVER 171844", "value": HANDOVER["20261028_171844"], "unit": "처리 프레임",
         "where": "companion_eval (56_truth.csv)", "used_by": "평가(사용자 교체 지연)", "source_tag": "[Claude]",
         "source": "사용자 교체 시점: Claude가 확인 시트를 보고 붙인 라벨(조사 56)"},
        {"name": "percentile", "value": "선형 보간", "unit": "", "where": "companion_eval _quart",
         "used_by": "평가(사분위)", "source_tag": "[관행값]", "source": "numpy.percentile 기본 방법(linear)"},
        {"name": "제외 영상", "value": "20261028_171615", "unit": "", "where": "companion_eval replay --exclude",
         "used_by": "평가(재생 대상)", "source_tag": "[승용님]", "source": "말씀 145: rejected"},
    ]
    _write_csv(os.path.join(a.out, "parameter_sources.csv"), params,
               ["name", "value", "unit", "where", "used_by", "source_tag", "source"])
    print(f"inclusion_table.csv {len(rows)} takes, parameter_sources.csv {len(params)} rows", flush=True)
    return 0


# --- ablation: cues x tracking on the same boxes -------------------------------------------------------------------
# The values of the roles before 2026-11-04 (params.py at 3705060, removed with them): companion_min_area_ratio 0.5
# ([파일럿]), companion_max_dist_widths 3.0 ([파일럿]), behind_max_area_ratio 1.0 (decision table 3 '주 사용자보다 작은
# 상자'). Used here only to reproduce the old behaviour.
OLD_COMPANION_AREA, OLD_COMPANION_DIST, OLD_BEHIND_AREA = 0.5, 3.0, 1.0
VARIANTS = ("a", "b", "c", "d")
VARIANT_KO = {"a": "a 옛 단서 · 추적 없음(바꾸기 전)", "b": "b 옛 단서 + 주 사용자 트랙",
              "c": "c 새 단서 · 추적 없음", "d": "d 새 단서 + 트랙 + 2초 중앙값(지금)"}
HANDOVER = {"20261028_171844": 36}
GRID_CLASS = {"cmax_companion_le": "companion", "cmax_behind_gt": "behind_standing", "cmax_helper_le": "helper",
              "bmin_behind_ge": "behind_standing", "bmin_companion_lt": "companion", "bmin_passing_ge": "behind_passing",
              "latmin_companion_ge": "companion", "latmin_behind_lt": "behind_standing", "latmin_helper_ge": "helper"}          # labels (56_truth.csv): user C to frame 35, user A from frame 36


def old_roles(boxes: np.ndarray, primary, frame_wh) -> list:
    """Role per box under the chain before 2026-11-04 (columns.assign_heads at 3705060) for a given main-user box."""
    from app.modules.vision.columns import _areas, _order
    roles = ["none"] * len(boxes)
    if primary is None:
        return roles
    W, H = frame_wh
    areas = _areas(boxes)
    roles[primary] = "primary"
    others = [i for i in _order(boxes) if i != primary]
    companion = None
    if others and areas[primary] > 0:
        width_px = (boxes[primary, 2] - boxes[primary, 0]) * W
        pcx, pcy = (boxes[primary, 0] + boxes[primary, 2]) / 2.0 * W, (boxes[primary, 1] + boxes[primary, 3]) / 2.0 * H
        for c in others:                                   # largest first: the first that fits
            ccx, ccy = (boxes[c, 0] + boxes[c, 2]) / 2.0 * W, (boxes[c, 1] + boxes[c, 3]) / 2.0 * H
            dist = math.hypot(ccx - pcx, ccy - pcy) / width_px if width_px > 0 else math.inf
            if areas[c] >= OLD_COMPANION_AREA * areas[primary] and dist <= OLD_COMPANION_DIST:
                companion = c
                break
    for i in others:
        roles[i] = "companion" if i == companion else ("behind" if areas[i] < OLD_BEHIND_AREA * areas[primary]
                                                       else "other")
    return roles


def _frame_size(videos: str, take: str, meta: dict) -> tuple:
    from app.modules.vision.sources import VideoFileSource
    src = VideoFileSource(os.path.join(videos, take + ".mp4"), step=meta["settings"]["step"],
                          width=meta["settings"]["width"])
    it = iter(src)
    try:
        img = next(it).image
    finally:
        close = getattr(it, "close", None)
        if close:
            close()
    return img.shape[1], img.shape[0]


def cmd_ablation(a) -> int:
    from app.modules.vision.columns import HeadPeople, choose_primary, inside, relative_cues
    from app.modules.vision.params import PilotParams
    truth = load_truth(a.truth)
    os.makedirs(a.out, exist_ok=True)
    out, checks = [], {"d_track_mismatch": 0, "d_role_mismatch": 0, "d_median_max_diff": 0.0,
                       "boxes": 0, "frame_size": {}}
    pts = collections.defaultdict(list)                  # (variant, stage, cue, class) -> values
    old_counts = collections.defaultdict(collections.Counter)   # (variant, class) -> role counts

    def emit(section, variant, take="", cls="", cue="", boundary="", measure="", value=None):
        out.append({"section": section, "variant": variant, "take": take, "class": cls, "cue": cue,
                    "boundary": boundary, "measure": measure, "value": value})

    for take in sorted(truth):
        folder = os.path.join(a.runs, take)
        if not os.path.isfile(os.path.join(folder, "rows.csv")):
            continue
        frames, meta = load_run(folder)
        if any(fr["face_in_primary"] is False for fr in frames):
            raise ValueError(f"{take}: rows with face_in_primary False have no face position; use a replay from "
                             f"before the face check (round 1)")
        label_tracks(frames)
        attach_labels(frames, truth[take])
        wh = _frame_size(a.videos, take, meta)
        checks["frame_size"][take] = wh
        p = PilotParams()
        people = {"b": HeadPeople(p), "d": HeadPeople(p)}
        seq = {v: [] for v in VARIANTS}                   # (frame_idx, t, primary person or None, user box exists)
        stats = {v: collections.Counter() for v in VARIANTS}
        for fr in frames:
            boxes = np.array([(b["x0"], b["y0"], b["x1"], b["y1"]) for b in fr["boxes"]], dtype=np.float64).reshape(-1, 4)
            face = fr["face_xy"]
            k_frame, _ = choose_primary(boxes, face, p.primary_rule)
            rb = people["b"].update(fr["t_s"], boxes, wh, face)
            rd = people["d"].update(fr["t_s"], boxes, wh, face)
            prim = {"a": k_frame, "b": rb.primary, "c": k_frame, "d": rd.primary}
            # checks against the recorded chain (d) and the recorded per-frame rule (a)
            checks["boxes"] += len(boxes)
            for i, b in enumerate(fr["boxes"]):
                checks["d_track_mismatch"] += rd.tracks[i] != b["track"]
                checks["d_role_mismatch"] += rd.roles[i] != b["role"]
                if rd.cues[i] is not None and b.get("rel_dist_med") is not None:
                    checks["d_median_max_diff"] = max(checks["d_median_max_diff"],
                                                      abs(rd.cues[i][2] - b["rel_dist_med"]),
                                                      abs(rd.cues[i][3] - b["lateral_med"]))
            user = next((i for i, b in enumerate(fr["boxes"]) if b["label"] == "user"), None)
            for v in VARIANTS:
                k = prim[v]
                who = None if k is None else (fr["boxes"][k]["person"] or f"T{fr['boxes'][k]['label_track']}")
                seq[v].append((fr["frame_idx"], fr["t_s"], who, user is not None,
                               None if k is None else fr["boxes"][k]["label"]))
                if user is not None:
                    stats[v]["user_frames"] += 1
                    if k is None:
                        stats[v]["primary_unseen"] += 1
                    elif fr["boxes"][k]["label"] == "user":
                        stats[v]["primary_is_user"] += 1
                    else:
                        stats[v]["primary_other"] += 1
                if face is not None and k is not None:
                    stats[v]["face_frames"] += 1
                    stats[v]["face_outside_primary"] += not inside(face, boxes[k])
            for v, k in (("a", k_frame), ("b", rb.primary)):
                roles = old_roles(boxes, k, wh)
                for i, b in enumerate(fr["boxes"]):
                    if b["label"] in CLASSES or b["label"] == "user":
                        old_counts[(v, b["label"])][roles[i]] += 1
            for i, b in enumerate(fr["boxes"]):
                if b["label"] not in CLASSES:
                    continue
                if k_frame is not None and i != k_frame:
                    rel, lat = relative_cues(boxes[i], boxes[k_frame], wh)
                    pts[("c", "frame", "rel_dist", b["label"])].append(rel)
                    pts[("c", "frame", "abs_lateral", b["label"])].append(None if lat is None else abs(lat))
                if rd.primary is not None and i != rd.primary and rd.cues[i] is not None:
                    rel, lat, rel_med, lat_med = rd.cues[i]
                    pts[("d", "frame", "rel_dist", b["label"])].append(rel)
                    pts[("d", "frame", "abs_lateral", b["label"])].append(None if lat is None else abs(lat))
                    pts[("d", "window", "rel_dist", b["label"])].append(rel_med)
                    pts[("d", "window", "abs_lateral", b["label"])].append(None if lat_med is None else abs(lat_med))
        for v in VARIANTS:
            s = stats[v]
            for m in ("user_frames", "primary_is_user", "primary_other", "primary_unseen"):
                emit("primary", v, take, measure=m, value=s[m])
            emit("primary", v, take, measure="primary_is_user_share",
                 value=round(s["primary_is_user"] / s["user_frames"], 4) if s["user_frames"] else None)
            who = [x[2] for x in seq[v] if x[2] is not None]
            emit("primary", v, take, measure="switches", value=sum(1 for p_, q in zip(who, who[1:]) if p_ != q))
            emit("face", v, take, measure="face_frames", value=s["face_frames"])
            emit("face", v, take, measure="face_outside_primary", value=s["face_outside_primary"])
            if take in HANDOVER:
                start = HANDOVER[take]
                t0 = next(x[1] for x in seq[v] if x[0] == start)
                hit = next((x for x in seq[v] if x[0] >= start and x[4] == "user"), None)
                emit("handover", v, take, measure="delay_frames", value=None if hit is None else hit[0] - start)
                emit("handover", v, take, measure="delay_s", value=None if hit is None else round(hit[1] - t0, 3))
    for v in VARIANTS:
        emit("primary", v, "all", measure="switches_total",
             value=sum(r["value"] for r in out if r["section"] == "primary" and r["variant"] == v
                       and r["measure"] == "switches"))
        emit("face", v, "all", measure="face_outside_primary_total",
             value=sum(r["value"] for r in out if r["section"] == "face" and r["variant"] == v
                       and r["measure"] == "face_outside_primary"))
    for (v, cls), c in sorted(old_counts.items()):
        total = sum(c.values())
        for role in ("primary", "companion", "behind", "other", "none"):
            emit("old_roles", v, "all", cls, measure=f"{role}_frames", value=c[role])
        emit("old_roles", v, "all", cls, measure="frames", value=total)
    for (v, stage, cue, cls), vals in sorted(pts.items()):
        for m, x in _quart(vals).items():
            emit("separation", f"{v}_{stage}", "all", cls, cue, measure=m, value=x)
    le, ge, lt, gt = (lambda x, g: x <= g), (lambda x, g: x >= g), (lambda x, g: x < g), (lambda x, g: x > g)
    figure = {}
    for key in (("c", "frame"), ("d", "frame"), ("d", "window")):
        name = f"{key[0]}_{key[1]}"
        rel = {c: pts.get((key[0], key[1], "rel_dist", c), []) for c in CLASSES}
        lat = {c: pts.get((key[0], key[1], "abs_lateral", c), []) for c in CLASSES}
        rows_rel = _sweep(rel, GRID_REL, [("cmax_companion_le", "companion", le), ("cmax_behind_gt", "behind_standing", gt),
                                          ("cmax_helper_le", "helper", le), ("bmin_behind_ge", "behind_standing", ge),
                                          ("bmin_companion_lt", "companion", lt),
                                          ("bmin_passing_ge", "behind_passing", ge)])
        rows_lat = _sweep(lat, GRID_LAT, [("latmin_companion_ge", "companion", ge),
                                          ("latmin_behind_lt", "behind_standing", lt),
                                          ("latmin_helper_ge", "helper", ge)])
        figure[name] = (rows_rel, rows_lat)
        for cue, rows in (("rel_dist", rows_rel), ("abs_lateral", rows_lat)):
            for r in rows:
                for m, x in r.items():
                    if m != "boundary":
                        emit("grid", name, "all", GRID_CLASS[m], cue, r["boundary"], m, x)
    _write_csv(os.path.join(a.out, "ablation_geometry_tracking.csv"), out,
               ["section", "variant", "take", "class", "cue", "boundary", "measure", "value"])
    _grid_wide(os.path.join(a.out, "ablation_grid_wide.csv"), pts)
    _paper_figure(os.path.join(a.out, "fig_e1_paper.png"), out, pts)
    with open(os.path.join(a.out, "ablation_checks.json"), "w", encoding="utf-8") as f:
        json.dump(checks, f, ensure_ascii=False, indent=2)
    _ablation_plot(os.path.join(a.out, "ablation_geometry_tracking.png"), out, figure)
    print(json.dumps({k: v for k, v in checks.items() if k != "frame_size"}), flush=True)
    return 0


def _grid_wide(path: str, pts: dict) -> None:
    """ablation_grid_wide.csv (module docstring): agreement per class and the helper acceptance rate apart."""
    from app.modules.vision.columns import SMALLER_THAN_USER
    behind = lambda v, g: v > SMALLER_THAN_USER and v >= g            # columns.decide_role's behind condition
    rules = [("rel_dist", "companion_rel_dist_max", GRID_REL,
              {"companion_agree": ("companion", lambda v, g: v <= g), "queue_agree": ("behind_standing", lambda v, g: v > g),
               "passer_agree": ("behind_passing", lambda v, g: v > g), "helper_accept": ("helper", lambda v, g: v <= g)}),
             ("rel_dist", "behind_rel_dist_min", GRID_REL,
              {"companion_agree": ("companion", lambda v, g: not behind(v, g)),
               "queue_agree": ("behind_standing", behind), "passer_agree": ("behind_passing", behind),
               "helper_accept": ("helper", behind)}),
             ("abs_lateral", "companion_lateral_min", GRID_LAT,
              {"companion_agree": ("companion", lambda v, g: v >= g), "queue_agree": ("behind_standing", lambda v, g: v < g),
               "passer_agree": ("behind_passing", lambda v, g: v < g), "helper_accept": ("helper", lambda v, g: v >= g)})]
    rows = []
    for cue, rule, grid, cols in rules:
        for g in grid:
            row = {"cue": cue, "rule": rule, "boundary": g}
            for var in ("c_frame", "d_frame", "d_window"):
                v, stage = var.split("_")
                for col, (cls, test) in cols.items():
                    vals = [x for x in pts.get((v, stage, cue, cls), []) if x is not None]
                    row[f"{var}_{col}"] = round(sum(test(x, g) for x in vals) / len(vals), 4) if vals else None
            rows.append(row)
    _write_csv(path, rows, list(rows[0]))


def _paper_figure(path: str, out: list, pts: dict) -> None:
    """fig_e1_paper.png: 7.0 x 2.4 in at 300 dpi, three panels, one shared legend, every font 8 pt or larger."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.lines import Line2D
    for reg in (r"C:\Windows\Fonts\malgun.ttf", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"):
        if os.path.isfile(reg):
            font_manager.fontManager.addfont(reg)
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=reg).get_name()
            break
    plt.rcParams.update({"axes.unicode_minus": False, "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8,
                         "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8})
    ink, muted, grid, surface = "#0b0b0b", "#898781", "#e1e0d9", "#ffffff"
    blue, orange = "#2a78d6", "#eb6834"
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.4), dpi=300, facecolor=surface,
                             gridspec_kw={"width_ratios": [1.15, 1, 1]})
    ax = axes[0]
    takes = sorted({r["take"] for r in out if r["section"] == "primary" and r["take"] != "all"})
    share = lambda v, t: next(r["value"] for r in out if r["section"] == "primary" and r["variant"] == v
                              and r["take"] == t and r["measure"] == "primary_is_user_share")
    xs = range(len(takes))
    ax.scatter([x - 0.14 for x in xs], [share("a", t) for t in takes], s=16, facecolors="none", edgecolors=ink,
               linewidths=0.9, zorder=3)
    ax.scatter([x + 0.14 for x in xs], [share("b", t) for t in takes], s=16, color=ink, zorder=3)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([t[-4:] for t in takes], rotation=90)
    ax.set_ylim(-0.05, 1.08)
    ax.set_title("주 사용자 정확도", loc="left", color=ink)
    ax.set_ylabel("비율", color=ink)
    sweeps = [(axes[1], "rel_dist", GRID_REL, "상대 거리",
               [("companion", lambda v, g: v <= g, blue), ("behind_standing", lambda v, g: v >= g, orange)]),
              (axes[2], "abs_lateral", GRID_LAT, "|옆 거리|",
               [("companion", lambda v, g: v >= g, blue), ("behind_standing", lambda v, g: v < g, orange)])]
    for ax, cue, gridv, title, lines in sweeps:
        for var, ls in (("c_frame", (0, (3, 1.5))), ("d_window", "-")):
            v, stage = var.split("_")
            for cls, test, col in lines:
                vals = [x for x in pts.get((v, stage, cue, cls), []) if x is not None]
                ax.plot(gridv, [sum(test(x, g) for x in vals) / len(vals) for g in gridv], color=col, ls=ls, lw=1.2)
        ax.set_title(title, loc="left", color=ink)
        ax.set_xlabel("경계 후보", color=ink)
        ax.set_ylim(-0.03, 1.03)
    axes[1].set_ylabel("라벨 일치율", color=ink)
    for ax in axes:
        ax.set_facecolor(surface)
        ax.grid(True, color=grid, lw=0.5)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(muted)
        ax.tick_params(colors=ink, length=2)
    handles = [Line2D([], [], ls="none", marker="o", mfc="none", mec=ink, ms=4, label="a · c 추적 없음"),
               Line2D([], [], ls="none", marker="o", color=ink, ms=4, label="b · d 트랙"),
               Line2D([], [], color=blue, lw=1.2, label="일행"), Line2D([], [], color=orange, lw=1.2, label="뒤에 선 사람"),
               Line2D([], [], color=ink, lw=1.2, ls=(0, (3, 1.5)), label="c 프레임마다"),
               Line2D([], [], color=ink, lw=1.2, label="d 2초 중앙값")]
    fig.legend(handles=handles, loc="lower center", ncol=6, frameon=False, bbox_to_anchor=(0.5, -0.01),
               handlelength=1.8, columnspacing=1.2)
    fig.tight_layout(rect=(0, 0.09, 1, 1), w_pad=1.0)
    fig.savefig(path, dpi=300, facecolor=surface)
    plt.close(fig)


def _ablation_plot(path: str, out: list, figure: dict) -> None:
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
    ink, muted, grid, surface = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
    colour = {"a": "#2a78d6", "b": "#eb6834", "c": "#1baf7a", "d": "#eda100"}
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.2), facecolor=surface)
    ax = axes[0]
    takes = sorted({r["take"] for r in out if r["section"] == "primary" and r["take"] != "all"})
    for j, v in enumerate(VARIANTS):
        ys = [next(r["value"] for r in out if r["section"] == "primary" and r["variant"] == v and r["take"] == t
                   and r["measure"] == "primary_is_user_share") for t in takes]
        ax.scatter([i + (j - 1.5) * 0.18 for i in range(len(takes))], ys, s=46, color=colour[v], label=VARIANT_KO[v],
                   zorder=3, edgecolors=surface, linewidths=1.5)
    ax.set_xticks(range(len(takes)))
    ax.set_xticklabels([t.split("_")[1] for t in takes], rotation=45, fontsize=8)
    ax.set_ylim(-0.03, 1.05)
    ax.set_title("주 사용자 = 라벨의 사용자인 프레임 비율(영상마다)", fontsize=10, loc="left", color=ink)
    ax.legend(fontsize=8, frameon=False, loc="center left")
    panels = [(axes[1], 0, "상대 거리: 일행 ≤ x(일행 조건 통과), 뒤에 선 사람 ≥ x(뒤 사람 조건 통과)",
               [("cmax_companion_le", "companion"), ("bmin_behind_ge", "behind_standing")], "경계 후보 x (상대 거리)"),
              (axes[2], 1, "|옆 거리|: 일행 ≥ x(통과), 뒤에 선 사람 < x(막힘)",
               [("latmin_companion_ge", "companion"), ("latmin_behind_lt", "behind_standing")],
               "경계 후보 x (|옆 거리|, 주 사용자 머리 높이)")]
    style = {"c_frame": ("#1baf7a", "--", "c 프레임마다"), "d_window": ("#eda100", "-", "d 2초 중앙값")}
    for ax, idx, title, cols, xlabel in panels:
        for name, (col_, ls, vlabel) in style.items():
            rows = figure[name][idx]
            x = [r["boundary"] for r in rows]
            for col, cls in cols:
                y = [np.nan if r[col] is None else r[col] for r in rows]
                ax.plot(x, y, color=colour["c"] if name.startswith("c") else colour["d"], ls=ls, lw=2 if cls ==
                        "companion" else 1.2, label=f"{vlabel}, {CLASS_KO[cls]}")
        ax.set_title(title, fontsize=10, loc="left", color=ink)
        ax.set_xlabel(xlabel, fontsize=9, color=ink)
        ax.set_ylim(-0.02, 1.02)
        ax.legend(fontsize=8, frameon=False, loc="center right")
    for ax in axes:
        ax.set_facecolor(surface)
        ax.grid(True, color=grid, lw=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(muted)
        ax.tick_params(colors=muted, labelsize=8)
    axes[0].set_ylabel("비율", fontsize=9, color=ink)
    axes[1].set_ylabel("라벨과 맞는 프레임 비율", fontsize=9, color=ink)
    fig.suptitle("같은 머리 상자에서 단서와 추적을 하나씩 바꾼 비교(라벨 있는 영상 12개의 모든 라벨 프레임)\n"
                 "굵은 선: 일행, 가는 선: 뒤에 선 사람. 10-28 팀 촬영, 평가 전용", fontsize=10.5, color=ink, x=0.01,
                 ha="left")
    fig.tight_layout()
    fig.savefig(path, dpi=120, facecolor=surface)
    plt.close(fig)


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
    b = sub.add_parser("ablation")
    b.add_argument("--runs", required=True)
    b.add_argument("--truth", required=True)
    b.add_argument("--videos", required=True)
    b.add_argument("--out", required=True)
    i = sub.add_parser("inventory")
    i.add_argument("--runs", required=True)
    i.add_argument("--truth", required=True)
    i.add_argument("--scenes", required=True)
    i.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    return {"replay": cmd_replay, "analyze": cmd_analyze, "sheets": cmd_sheets, "ablation": cmd_ablation,
            "inventory": cmd_inventory}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
