"""Replay a recorded take through the whole chain: one JSONL line per window (situation tag, evidence ids, unknown
reason, alternatives, measurable, rule-table decision, session state, contract view). Headless: no window, no camera.

From ai-engine/ (runtime environment: requirements.txt + app/modules/vision/requirements.txt + onnxruntime):
  python -m app.modules.vision.replay --video TAKE.mp4 [--touch-log TAKE_touch.json] [--start-offset S]
                                      [--params BUNDLE.json] --out DIR [--step N] [--width W] [--threads 1]
                                      [--max-seconds S] [--blendshapes] [--no-heads] [--overwrite]

- Frame times: TAKE.mp4.times.csv when it is there (record_clip.py), else frame index / container fps (sources.py).
- Blendshapes: off unless --blendshapes is given (decision list 2026-10-10 §16: a setting, off by default); while
  off, mouth_motion stays blank and the cues that need it are missing.
- Touch log: placed on the video time axis with TAKE.mp4.clock.json (record_clip.py) or with --start-offset (touch.py).
  Without --touch-log the touch columns are missing and every rule that needs them stays 'unknown'.
- Value bundle (--params): the 13 situation values (no defaults, vision README '상황 층') and overrides of the chain's
  [파일럿] values (params.py). Without it the situation output is 'unknown' (reason no_value_bundle) and the rule
  table runs on the touch rows only.
- Models: MediaPipe files in app/modules/vision/models/ (download_models.py) and the two ONNX files from
  tools/export_onnx.py. A missing ONNX file is reported and its columns stay missing (--no-heads does the same on
  purpose).
- Outputs in --out: windows.jsonl, rows.csv (one line per processed frame), meta.json (inputs, bundle with sources,
  model hashes, versions, timing p50 / p95, counts per tag and decision).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import sys
import time
from collections import deque

from .chain import SOURCE_KIND, FrameChain, WindowJudge, history_s
from .columns import OPTIONAL_COLUMNS
from .params import load_bundle

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(CODE_DIR, "models")
H1_ONNX = "h1_head_yolox_nano_416.onnx"
P1_ONNX = "p1_head_direction_resnet18_56.onnx"
TOUCH_ROW_COLUMNS = ("tap_count", "miss_tap_count")
TIMING_COLUMNS = ("ms_heads", "ms_head_dir", "ms_chain", "cpu_ms_chain")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jsonable(v):
    """NaN / inf -> None, tuples -> lists, recursively (JSON has no NaN)."""
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return v


def cell(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return "" if not math.isfinite(v) else f"{v:.6g}"
    if isinstance(v, (tuple, list)):
        return ";".join(cell(x) for x in v)
    return v


def percentiles(values: list) -> dict | None:
    """p50 / p95 (linear interpolation, numpy.percentile's default) and n, the first frame left out by the caller."""
    vals = sorted(v for v in values if v is not None and math.isfinite(v))
    if not vals:
        return None

    def q(p):
        k = (len(vals) - 1) * p
        lo, hi = math.floor(k), math.ceil(k)
        return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)
    return {"p50": round(q(0.50), 3), "p95": round(q(0.95), 3), "max": round(vals[-1], 3), "n": len(vals)}


def timing_summary(rows: list, records: list) -> dict:
    later = rows[1:]   # the first frame loads models and caches (render.timing_stats convention)
    out = {k: percentiles([r.get(k) for r in later]) for k in ("ms_total", "ms_heads", "ms_head_dir", "ms_chain",
                                                               "cpu_ms_chain")}
    out["ms_window"] = percentiles([r.get("ms_window") for r in records])
    out["note"] = ("ms_total = MediaPipe set + features (features.Observer); ms_heads = H1 pre + infer + post; "
                   "ms_head_dir = P1 crop + infer (main user only); ms_chain = the whole per-frame step (wall); "
                   "cpu_ms_chain = process CPU time of that step (all threads); ms_window = situation + rule table "
                   "per window; first frame left out")
    return out


def load_perception(models_dir: str, params, threads: int, heads_on: bool, log) -> tuple:
    """(head detector or None, direction model or None, {file: info}) from the ONNX files; a missing file is logged."""
    info = {}
    detector = direction = None
    if not heads_on:
        log("머리 탐지기 끔(--no-heads): 뒤 사람 · 동행자 · 머리 방향 열은 결측입니다")
        return None, None, info
    h1, p1 = os.path.join(models_dir, H1_ONNX), os.path.join(models_dir, P1_ONNX)
    if os.path.isfile(h1):
        from .perception.head import HeadDetector
        detector = HeadDetector(h1, params.head_score_min, params.head_nms_iou, threads)
        info[H1_ONNX] = {"bytes": os.path.getsize(h1), "sha256": sha256(h1)}
    else:
        log(f"머리 탐지기 파일이 없습니다({h1}): 뒤 사람 · 동행자 열은 결측입니다. tools/export_onnx.py로 만드세요")
    if detector is not None and os.path.isfile(p1):
        from .perception.head_direction import HeadDirection
        direction = HeadDirection(p1, threads)
        info[P1_ONNX] = {"bytes": os.path.getsize(p1), "sha256": sha256(p1)}
    elif detector is not None:
        log(f"머리 방향 파일이 없습니다({p1}): head_dir_* 열은 비어 있습니다")
    return detector, direction, info


def environment() -> dict:
    env = {"python": platform.python_version(), "platform": platform.platform(), "cpu_count": os.cpu_count()}
    for mod in ("numpy", "cv2", "mediapipe", "onnxruntime"):
        try:
            env[mod] = __import__(mod).__version__
        except Exception:   # not installed: say so
            env[mod] = None
    return env


def write_rows(path: str, rows: list):
    from .features import COLUMNS
    extra = [c for c in OPTIONAL_COLUMNS + TOUCH_ROW_COLUMNS + TIMING_COLUMNS if any(c in r for r in rows)]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        wr.writerow(list(COLUMNS) + extra)
        for r in rows:
            wr.writerow([cell(r.get(c)) for c in list(COLUMNS) + extra])


def run_replay(source, out_dir: str, bundle, *, timeline=None, models=None, detector=None, direction=None,
               blendshapes: bool = False, max_seconds: float | None = None, session_id: str = "replay",
               model_info: dict | None = None, settings: dict | None = None, log=print) -> dict:
    """Run the chain over a frame source (sources.VideoFileSource or any iterable of sources.Frame) and write the
    outputs. models = MediaPipe models (or a fake with .infer(frame)); detector / direction = perception models or
    None. Returns the meta dict (also written to meta.json)."""
    os.makedirs(out_dir, exist_ok=True)
    chain = FrameChain(models, bundle.chain, detector, direction, timeline, blendshapes=blendshapes,
                       source_kind=SOURCE_KIND.get(getattr(source, "kind", ""), ""))
    judge = WindowJudge(bundle, timeline, session_id=session_id)
    keep_s = history_s(bundle)
    rows, recent, records = [], deque(), []
    next_t = None
    wall0 = time.perf_counter()
    stop_reason = "input ended"
    with open(os.path.join(out_dir, "windows.jsonl"), "w", encoding="utf-8") as out:
        def emit(t_end):
            window_rows = [r for r in recent if float(r["t_s"]) >= t_end - keep_s]
            rec = judge.evaluate(window_rows, t_end)
            records.append(rec)
            out.write(json.dumps(jsonable(rec), ensure_ascii=False) + "\n")

        frames = iter(source)
        try:
            for frame in frames:
                if max_seconds is not None and frame.t_s > max_seconds:
                    stop_reason = "--max-seconds reached"
                    break
                row = chain.process(frame)
                rows.append(row)
                recent.append(row)
                t = float(row["t_s"])
                if next_t is None:
                    next_t = t + bundle.chain.segment_s
                while t >= next_t:
                    emit(next_t)
                    next_t += bundle.chain.segment_s
                while recent and float(recent[0]["t_s"]) < t - keep_s - bundle.chain.segment_s:
                    recent.popleft()
        finally:
            close = getattr(frames, "close", None)
            if close:
                close()
    wall_s = time.perf_counter() - wall0
    write_rows(os.path.join(out_dir, "rows.csv"), rows)
    tags, transitions, supports = {}, {}, {}
    for rec in records:
        tags[rec["situation"]["name"]] = tags.get(rec["situation"]["name"], 0) + 1
        transitions[rec["decision"]["transition"]] = transitions.get(rec["decision"]["transition"], 0) + 1
        if rec["decision"]["transition"] in ("open", "replace"):
            supports[rec["decision"]["support"]] = supports.get(rec["decision"]["support"], 0) + 1
    meta = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "input": getattr(source, "name", "frames"),
            "frame_time_source": getattr(source, "time_source", None), "fps_nominal": getattr(source, "fps", None),
            "frames": len(rows), "windows": len(records), "wall_s": round(wall_s, 3), "stop_reason": stop_reason,
            "first_t": rows[0]["t_s"] if rows else None, "last_t": rows[-1]["t_s"] if rows else None,
            "settings": settings or {}, "bundle": bundle.to_dict(), "pilot_fields": bundle.pilot_fields(),
            "touch": None if timeline is None else timeline.meta, "models": model_info or {},
            "environment": environment(), "timing_ms": timing_summary(rows, records),
            "counts": {"situation": tags, "transition": transitions, "opened_support": supports},
            "jev_questions_recorded": len(judge.jev.log)}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(jsonable(meta), f, ensure_ascii=False, indent=2)
    return meta


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):      # Windows code page: replace what it cannot print
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", required=True)
    ap.add_argument("--touch-log", default=None)
    ap.add_argument("--start-offset", type=float, default=None,
                    help="seconds added to the touch times (with TAKE.mp4.clock.json: a correction; without it: the "
                         "video time of the log's first event)")
    ap.add_argument("--params", default=None, help="value bundle JSON (params.py)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--step", type=int, default=1, help="use every N-th video frame (1 = all)")
    ap.add_argument("--width", type=int, default=None, help="resize to this width, aspect ratio kept")
    ap.add_argument("--threads", type=int, default=1, help="ONNX Runtime intra-op threads (default 1)")
    ap.add_argument("--models", default=MODELS_DIR)
    ap.add_argument("--max-seconds", type=float, default=None, help="stop after this video time")
    ap.add_argument("--session-id", default=None, help="session_id in the contract view (default: the video name)")
    ap.add_argument("--blendshapes", action="store_true",
                    help="blendshapes on (default off, decision list 2026-10-10 §16); off: mouth_motion stays blank")
    ap.add_argument("--no-heads", action="store_true", help="no H1 / P1: head columns stay missing")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)
    if os.path.isfile(os.path.join(a.out, "windows.jsonl")) and not a.overwrite:
        ap.error(f"{a.out} already holds a replay - choose another --out or add --overwrite")
    bundle = load_bundle(a.params)
    timeline = None
    if a.touch_log:
        from .touch import load_timeline
        timeline = load_timeline(a.touch_log, a.video, a.start_offset)
    import cv2
    cv2.setNumThreads(1)
    from app.inference.vision import FACE_LANDMARKER_MODEL, POSE_LANDMARKER_MODEL, FACE_DETECTOR_MODEL, MediaPipeModels
    from .sources import VideoFileSource
    source = VideoFileSource(a.video, step=a.step, width=a.width)
    detector, direction, info = load_perception(a.models, bundle.chain, a.threads, not a.no_heads, print)
    for name in (FACE_LANDMARKER_MODEL, FACE_DETECTOR_MODEL, POSE_LANDMARKER_MODEL):
        p = os.path.join(a.models, name)
        if os.path.isfile(p):
            info[name] = {"bytes": os.path.getsize(p), "sha256": sha256(p)}
    models = MediaPipeModels(a.models, blendshapes=a.blendshapes)
    settings = {"step": a.step, "width": a.width, "threads": a.threads, "blendshapes": a.blendshapes,
                "heads": detector is not None, "head_direction": direction is not None,
                "face_landmarker": "VIDEO, num_faces=1, transformation matrix on, blendshapes "
                                   + ("on" if a.blendshapes else "off"),
                "touch_log": a.touch_log, "start_offset_s": a.start_offset, "params_file": a.params}
    print(f"재생 시작: {source.name} → {a.out}", flush=True)
    try:
        meta = run_replay(source, a.out, bundle, timeline=timeline, models=models, detector=detector,
                          direction=direction, blendshapes=a.blendshapes, max_seconds=a.max_seconds,
                          session_id=a.session_id or os.path.splitext(os.path.basename(a.video))[0],
                          model_info=info, settings=settings)
    finally:
        models.close()
    tm = meta["timing_ms"].get("ms_chain") or {}
    print(f"끝: 프레임 {meta['frames']}장 · 창 {meta['windows']}개 · 상황 {meta['counts']['situation']} · "
          f"전이 {meta['counts']['transition']} · 프레임 처리 p50 {tm.get('p50')} ms → {a.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
