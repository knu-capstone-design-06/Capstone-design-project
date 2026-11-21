"""Calibrate the scene-tag boundaries (params.SCENE_BOUNDARIES, five) and the track-stitch boundaries of the user change
(params.STITCH_BOUNDARIES) for one camera from standing-use recordings.

From ai-engine/:
  python -m app.modules.vision.tools.calibrate_scene --params BUNDLE.json (--rows ROWS.csv [ROWS.csv ...] | --list LIST)
                                                     [--note TEXT] [--out SNIPPET.json]

Input: rows.csv files of a replay (replay.py, or run.py's observations.csv with the same columns) of people standing
and using the kiosk normally in front of the TARGET camera. These calibration recordings must be separate from the
takes used to evaluate the tags: a value set on a take and then scored on the same take says nothing (vision README,
'장면 태그 5개'). --list = a text file with one rows.csv path per line.

Method (params.SCENE_METHOD; Wu et al., W4A 2021, a baseline +/- 2 SD): the rows are cut into the windows the runners
use - one every segment_s from the first row, each [t - window_s, t], the last stretch as one shorter window
(companion_eval rewindow) - with window_s and segment_s from --params. For each window the scene tags' own
measurements are taken (events.observe_scene): the median iod_ratio_user (columns.FaceSizeRef, anchored at the
main-user track as in a run without a touch log; recorded values are kept) and the median face_cy of the main user's
face rows. The value is mean + 2 SD (sample SD) of those window medians. approach_ratio_min is computed first, and the
face-height pass leaves out the rows above it, as the tag does at run time (the bundle's value when it has one; a
computed value only when it is written, as the bundle would then carry it). A face-height median that stands on
fewer rows than the bundle's face_visible_min of the window's frames is dropped, since seated_height reads such a
window as too_few_rows at run time; the tool prints how many were dropped.
seated_head_cy_min is computed the same way on the vertical centre of the main user's head box (rows of a replay with
the head detector; none without it). head_approach_ratio_min (window medians of head_ratio_user, columns.HeadSizeRef)
is computed first, with approach_ratio_min, and its value (the bundle's when it has one) leaves the head rows above
it out of the seated_head_cy_min pass, as the tag does at run time. head_down_pitch_min is computed on the window
medians of dpitch_user_deg (columns.PitchRef: the main user's pitch against that user's first face). A head-height or
head-pitch median that stands on fewer rows than face_visible_min of the window's frames is dropped too, as the tags
read them.
stitch_shift_max and stitch_size_max (the user change's track stitch, params.STITCH_METHOD) are the mean + 2 SD of how
far the same main-user head box moves within track_max_gap_s (columns.stitch_motion: each box against the last box of
the same track at most track_max_gap_s later; centre shift in box widths and heights, |ln height ratio|) over all
recordings. They need rows with the main user's head box (a replay with the head detector); no value is written when
fewer than two recordings give pairs.
For comparison the same is printed over every face row (per frame) and over one median per recording.

The tool sets no minimum number of windows: it prints the counts and leaves the judgment to the reader. It writes no
value when fewer than two recordings give windows (the spread between people is then not measured at all) or when the
window medians do not vary (mean + 2 SD would be the baseline itself), nor an approach_ratio_min or
head_approach_ratio_min not above 1 (a ratio of 1 is the reference size itself), nor a head_down_pitch_min not above 0
(a bundle takes boundaries above 0). The tags compare strictly (above the value).
It writes no file except --out (a bundle snippet {"chain": {name: {"value", "source"}}} to merge into a value bundle by
hand); the source text names the method, the counts and --note (describe the recordings there in aggregate words; no
file or person names). Plain Python plus columns.py (numpy).
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import statistics
import sys

from app.modules.vision.columns import (CHANGE_COLUMNS, add_face_size_ratio, add_head_size_ratio, add_main_user_change,
                                        add_pitch_user, main_user_face, stitch_motion)
from app.modules.vision.events import _box_cy, observe_scene
from app.modules.vision.params import SCENE_METHOD, STITCH_BOUNDARIES, STITCH_METHOD, load_bundle

QUANTITIES = (("seated_face_cy_min", "face_height", "face_cy_median", "face_cy"),
              ("head_approach_ratio_min", "head_size", "head_ratio_median", "head_ratio_user"),
              ("seated_head_cy_min", "head_height", "head_cy_median", "primary_box"),
              ("head_down_pitch_min", "head_pitch", "dpitch_median", "dpitch_user_deg"),
              ("approach_ratio_min", "face_size", "iod_ratio_median", "iod_ratio_user"))


def read_rows(path: str, params=None) -> list:
    """One rows.csv as dicts (blank cells None, primary_box a tuple) with the scene columns filled where missing
    (params = the chain values; defaults when None). The change columns are written again, all of them, when any one is
    missing (rows.csv written before a change column was added, such as main_user_stitched)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [{k: (None if v == "" else v) for k, v in r.items()} for r in csv.DictReader(f)]
    for row in rows:
        if row.get("primary_box"):
            row["primary_box"] = tuple(float(x) for x in row["primary_box"].split(";"))
    if not all(any(c in r for r in rows) for c in CHANGE_COLUMNS):
        add_main_user_change(rows, params)
    if not any("iod_ratio_user" in r for r in rows):
        add_face_size_ratio(rows, params)
    if not any("head_ratio_user" in r for r in rows):
        add_head_size_ratio(rows, params)
    if not any("dpitch_user_deg" in r for r in rows):
        add_pitch_user(rows, params)
    return sorted(rows, key=lambda r: float(r["t_s"]))


def window_ends(rows: list, segment_s: float) -> list:
    """The window ends of the runners: every segment_s from the first row, plus the last row when it lies after the
    last full segment."""
    if not rows:
        return []
    first, last = float(rows[0]["t_s"]), float(rows[-1]["t_s"])
    ends, t = [], first + segment_s
    while t <= last:
        ends.append(t)
        t += segment_s
    if last > (ends[-1] if ends else first):
        ends.append(last)
    return ends


def _finite(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def summary(values: list) -> dict:
    """n, mean, sample SD and mean + 2 SD of the values (SD and value None below two values)."""
    n = len(values)
    mean = statistics.fmean(values) if n else None
    sd = statistics.stdev(values) if n >= 2 else None
    return {"n": n, "mean": mean, "sd": sd, "value": None if sd is None else mean + 2 * sd}


def _windows(rows: list, window_s: float, segment_s: float, approach: float | None, kind: str, obs: str,
             min_share: float | None = None, head_approach: float | None = None) -> tuple:
    """(window medians, windows dropped) of one recording (rows sorted by time); each window is sliced by bisect, not
    re-scanned. A face_height, head_height or head_pitch median on fewer rows than min_share of the window's frames is
    dropped (situation._enough, as seated_height and the head-down gate read them)."""
    times = [float(r["t_s"]) for r in rows]
    out, dropped = [], 0
    for t in window_ends(rows, segment_s):
        part = rows[bisect.bisect_left(times, t - window_s):bisect.bisect_right(times, t)]
        cues = observe_scene(part, (t - window_s, t), approach, head_approach)
        for e in cues.of(kind):
            if kind in ("face_height", "head_height", "head_pitch") and min_share is not None \
                    and e["obs"]["rows"] < min_share * cues.frames:
                dropped += 1
            else:
                out.append(e["obs"][obs])
    return out, dropped


def calibrate(recordings: list, window_s: float, segment_s: float, approach_ratio_min: float | None = None,
              min_share: float | None = None, max_gap_s: float | None = None,
              head_approach_ratio_min: float | None = None) -> dict:
    """{field: {"windows": summary, "frames": summary, "recordings": summary, "recordings_with_windows": n,
    "windows_dropped": n}, "approach_used": value, "head_approach_used": value} over recordings = [rows of one
    recording, ...]. approach_ratio_min and head_approach_ratio_min first; the face-height pass leaves out the rows
    above approach_ratio_min (the given one, else the one just computed when it is written), the head-height pass the
    rows above head_approach_ratio_min (the given one, else the one just computed when it is written), and the
    face-height, head-height and head-pitch passes drop the windows below min_share (the bundle's face_visible_min)."""
    out = {}
    approach, head_approach = approach_ratio_min, head_approach_ratio_min
    for field, kind, obs, column in sorted(QUANTITIES, key=lambda q: q[1] not in ("face_size", "head_size")):
        windows, frames, medians, used, dropped = [], [], [], 0, 0
        for rows in recordings:
            per, cut = _windows(rows, window_s, segment_s, approach if kind != "face_size" else None, kind, obs,
                                min_share, head_approach if kind == "head_height" else None)
            dropped += cut
            if column in ("primary_box", "head_ratio_user"):
                get = _box_cy if column == "primary_box" else _finite
                values = [v for v in (get(r.get(column)) for r in rows) if v is not None]
            else:
                values = [v for v in (_finite(r.get(column)) for r in rows if main_user_face(r)) if v is not None]
            windows += per
            frames += values
            if values:
                medians.append(statistics.median(values))
            used += bool(per)
        out[field] = {"windows": summary(windows), "frames": summary(frames), "recordings": summary(medians),
                      "recordings_with_windows": used, "windows_dropped": dropped}
        if kind == "face_size" and approach is None and no_value_reason(field, out[field]) is None:
            approach = out[field]["windows"]["value"]
        if kind == "head_size" and head_approach is None and no_value_reason(field, out[field]) is None:
            head_approach = out[field]["windows"]["value"]
    for field, k in zip(STITCH_BOUNDARIES, (0, 1)):           # the track stitch: box pairs, not windows
        values, medians, used = [], [], 0
        for rows in recordings:
            per = [b[k] for b in stitch_motion(rows, max_gap_s)]
            values += per
            used += bool(per)
            if per:
                medians.append(statistics.median(per))
        out[field] = {"windows": summary(values), "frames": summary([]), "recordings": summary(medians),
                      "recordings_with_windows": used, "windows_dropped": 0}
    out["approach_used"], out["head_approach_used"] = approach, head_approach
    return out


def no_value_reason(field: str, r: dict) -> str | None:
    """Why no value is written for this field's result r (None: the value is written)."""
    if r["recordings_with_windows"] < 2:
        return f"windows from {r['recordings_with_windows']} recording(s)"
    if not r["windows"]["sd"]:
        return "the window medians do not vary"     # mean + 2 SD would be the baseline itself
    if field in ("approach_ratio_min", "head_approach_ratio_min") and r["windows"]["value"] <= 1:
        return "the value is not above 1 (the reference size itself)"
    if field == "head_down_pitch_min" and r["windows"]["value"] <= 0:
        return "the value is not above 0 (the user's first face; a bundle takes boundaries above 0)"
    return None


def snippet(result: dict, window_s: float, segment_s: float, note: str) -> dict:
    """{"chain": {field: {"value", "source"}}} for the fields that got a value (the window-median variant)."""
    chain = {}
    for field, r in result.items():
        if field in ("approach_used", "head_approach_used"):
            continue
        w = r["windows"]
        if no_value_reason(field, r) is not None:
            continue
        if field in STITCH_BOUNDARIES:
            text = (f"보정값(tools/calibrate_scene.py): {STITCH_METHOD}. 상자 짝 {w['n']}개(녹화 "
                    f"{r['recordings_with_windows']}개), 평균 {w['mean']:.4f} · SD {w['sd']:.4f}")
        else:
            text = (f"보정값(tools/calibrate_scene.py): {SCENE_METHOD}. 창 {w['n']}개(녹화 {r['recordings_with_windows']}개, "
                    f"window_s {window_s} · segment_s {segment_s}), 창 중앙값 평균 {w['mean']:.4f} · SD {w['sd']:.4f}")
        chain[field] = {"value": w["value"], "source": text + (f". {note}" if note else "")}
    return {"chain": chain}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--params", required=True, help="value bundle with the situation section (window_s) to use")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--rows", nargs="+", help="rows.csv files of standing-use recordings on the target camera")
    src.add_argument("--list", help="text file with one rows.csv path per line")
    ap.add_argument("--note", default="", help="aggregate description of the recordings for the source text")
    ap.add_argument("--out", help="write the bundle snippet here (JSON)")
    a = ap.parse_args(argv)
    bundle = load_bundle(a.params)
    if bundle.situation is None:
        print("the bundle has no situation section: window_s is needed", file=sys.stderr)
        return 2
    paths = a.rows or [line.strip() for line in open(a.list, encoding="utf-8") if line.strip()]
    window_s, segment_s = bundle.situation.window_s, bundle.chain.segment_s
    result = calibrate([read_rows(p, bundle.chain) for p in paths], window_s, segment_s,
                       bundle.chain.approach_ratio_min, bundle.situation.face_visible_min, bundle.chain.track_max_gap_s,
                       bundle.chain.head_approach_ratio_min)
    print(f"recordings {len(paths)}, window_s {window_s}, segment_s {segment_s}, approach_ratio_min for face_height "
          f"{result['approach_used']} ({'the bundle' if bundle.chain.approach_ratio_min is not None else 'computed here'};"
          f" rows above it left out); head_approach_ratio_min for head_height {result['head_approach_used']} "
          f"({'the bundle' if bundle.chain.head_approach_ratio_min is not None else 'computed here'})")
    for field, r in result.items():
        if field in ("approach_used", "head_approach_used"):
            continue
        if r["windows_dropped"]:
            print(f"{field}: {r['windows_dropped']} window(s) dropped (rows behind the median below face_visible_min "
                  f"of the window)")
        reason = no_value_reason(field, r)
        if reason is not None:
            print(f"{field}: {reason}; no value is written")
        for unit in ("windows", "frames", "recordings"):
            s = r[unit]
            fmt = (lambda v: "-" if v is None else f"{v:.4f}")
            label = "box pairs" if field in STITCH_BOUNDARIES and unit == "windows" else unit
            print(f"{field:20s} {label:10s} n {s['n']:6d}  mean {fmt(s['mean'])}  sd {fmt(s['sd'])}  "
                  f"mean+2SD {fmt(s['value'])}")
    print("no minimum count is applied: judge whether n is enough. Calibration recordings must not be evaluation takes.")
    snip = snippet(result, window_s, segment_s, a.note)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(snip, f, ensure_ascii=False, indent=1)
    else:
        print(json.dumps(snip, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
