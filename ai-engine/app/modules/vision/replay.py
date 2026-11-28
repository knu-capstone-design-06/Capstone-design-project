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
- Walking-aid detector (--aid-model AID.onnx, optional): --aid-rule owner_box | head_centre | head_centre_carry picks
  how it is read (params.py aid_rule; default owner_box, the main user's person box; head_centre for the kiosk-view
  detector files; head_centre_carry = head_centre with the user's aid box followed through the rows without the head
  box) and --aid-head-min SCORE gives the aid_use cut of the two head_centre readings (params.py aid_head_min; no
  default: without it aid_use stays unknown, no_value_for_model). Both override the value bundle, need --aid-model and
  are recorded in meta.json with origin 'option'.
- Wheelchair confirm step (--aid-confirm-model READER.onnx, repeatable, optional; aid_confirm.py): a window's
  aid_use true with the class wheelchair stays true only when the confirm reader also reads a wheelchair in that
  window (--aid-confirm-min SCORE, default 0.5: the reader's own decision point, the cut of every table of the
  measurement); otherwise aid_use becomes false. Several files: the mean of their softmax probabilities. Needs
  --aid-model with --aid-rule head_centre or head_centre_carry. Off without the option: every output as before.
  --aid-start-only (with it, not with the two holds): the walking aid is judged at the start of each touch session
  and again after a change of main user the engine counts (aid_confirm.py, 'Start only'). --aid-stick-model
  READER.onnx [...] with --aid-stick-frames N (with --aid-start-only): a user with N stick rows of the person-crop
  readers is answered aid_use true with the class cane (aid_confirm.py, 'Stick at the start').
- Windows: one every segment_s from the first frame; the rows after the last full window get one shorter window at
  the last frame (its record has 'partial': {segment_s}; meta last_window_partial_s), so the end of the take is judged.
- Outputs in --out: windows.jsonl, rows.csv (one line per processed frame), meta.json (inputs, bundle with sources,
  model hashes, versions, timing p50 / p95, counts per tag and decision, frames with a face / a head box / P1
  viewpoint probabilities).
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
from .events import AID_HEAD_RULES, AID_RULES, HEAD_CENTRE_CARRY, SEEN
from .params import PilotParams, load_bundle, with_options

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(CODE_DIR, "models")
H1_ONNX = "h1_head_yolox_nano_416.onnx"
P1_ONNX = "p1_head_direction_resnet18_56.onnx"
TOUCH_ROW_COLUMNS = ("tap_count", "miss_tap_count")
TIMING_COLUMNS = ("ms_heads", "ms_head_dir", "ms_aids", "ms_phones", "ms_chain", "cpu_ms_chain")


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
    if isinstance(v, dict) or (isinstance(v, list) and all(isinstance(x, dict) for x in v)):
        return json.dumps(jsonable(v), ensure_ascii=False, separators=(",", ":"))   # head_boxes: one JSON cell
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
    out = {k: percentiles([r.get(k) for r in later]) for k in ("ms_total",) + TIMING_COLUMNS}
    out["ms_window"] = percentiles([r.get("ms_window") for r in records])
    out["note"] = ("ms_total = MediaPipe set + features (features.Observer); ms_heads = H1 pre + infer + post; "
                   "ms_head_dir = P1 crop + infer (main user only); ms_aids = walking-aid detector pre + infer + post; "
                   "ms_phones = phone detector pre + infer + post (frames it ran on); "
                   "ms_chain = the whole per-frame step (wall); "
                   "cpu_ms_chain = process CPU time of that step (all threads); ms_window = situation + rule table "
                   "per window; first frame left out")
    return out


def load_perception(models_dir: str, params, threads: int, heads_on: bool, log) -> tuple:
    """(head detector or None, direction model or None, {file: info}) from the ONNX files; a missing file is logged."""
    info = {}
    detector = direction = None
    if not heads_on:
        log("머리 탐지기 끔(--no-heads): 뒤 사람 · 동행자 · P1 카메라 시점(head_dir_*) 열은 결측입니다")
        return None, None, info
    h1, p1 = os.path.join(models_dir, H1_ONNX), os.path.join(models_dir, P1_ONNX)
    if os.path.isfile(h1):
        from app.inference.head import HeadDetector
        detector = HeadDetector(h1, params.head_score_min, params.head_nms_iou, threads)
        info[H1_ONNX] = {"bytes": os.path.getsize(h1), "sha256": sha256(h1)}
    else:
        log(f"머리 탐지기 파일이 없습니다({h1}): 뒤 사람 · 동행자 열은 결측입니다. tools/export_onnx.py로 만드세요")
    if detector is not None and os.path.isfile(p1):
        from app.inference.head_direction import HeadDirection
        direction = HeadDirection(p1, threads)
        info[P1_ONNX] = {"bytes": os.path.getsize(p1), "sha256": sha256(p1)}
    elif detector is not None:
        log(f"P1 카메라 시점 분류기 파일이 없습니다({p1}): head_dir_* 열은 비어 있습니다")
    return detector, direction, info


def load_aids(path: str | None, params, threads: int, log):
    """The walking-aid detector of --aid-model, or None (off unless a file is given; the weights are not in this
    repository); with params.aid_rule head_centre or head_centre_carry it also reads the per-class boxes (AidDetector
    per_class). Returns (detector or None, {file: info})."""
    if not path:
        return None, {}
    if not os.path.isfile(path):
        raise FileNotFoundError(f"--aid-model: no file {path}")
    from app.inference.aid import AidDetector
    head_centre = params.aid_rule in AID_HEAD_RULES
    detector = AidDetector(path, params.aid_score_min, params.aid_nms_iou, threads, per_class=head_centre)
    log(f"보조기구 탐지기 켬: 클래스 {', '.join(detector.classes)}. 키오스크 시점 정확도는 재지 않았습니다")
    if head_centre:
        cut = ("aid_use 컷(aid_head_min)이 없어 aid_use는 모름(no_value_for_model)입니다" if params.aid_head_min is None
               else f"aid_use 컷 aid_head_min = {params.aid_head_min:g}")
        log(f"보조기구 읽기 {params.aid_rule}: 주 사용자 머리 상자 가운데를 품은 보조기구 클래스 상자의 점수"
            f"(aid_head_score). {cut}")
        if params.aid_rule == HEAD_CENTRE_CARRY:
            log(f"머리 상자가 없는 프레임은 직전 머리 프레임의 그 상자를 머리 트랙 규칙(IoU가 가장 큰 상자, "
                f"track_iou_min {params.track_iou_min:g} 이상; {params.track_max_gap_s:g}초 넘게 맞는 상자가 없으면 "
                f"끝)으로 따라가 그 상자의 점수를 읽습니다(aid_head_from carried)")
    elif params.aid_head_min is not None:
        log(f"aid_head_min {params.aid_head_min:g}은 head_centre 읽기에서만 씁니다. 지금 읽기는 {params.aid_rule}입니다")
    return detector, {os.path.basename(path): {"bytes": os.path.getsize(path), "sha256": sha256(path),
                                               "licence": detector.meta.get("licence"),
                                               "attribution": detector.meta.get("attribution")}}


CONFIRM_MIN_DEFAULT = 0.5   # the reader's own decision point: the cut of every table of the crop reader measurement


def add_aid_confirm_options(ap):
    """--aid-confirm-model (repeatable) and --aid-confirm-min: the wheelchair confirm step (aid_confirm.py)."""
    ap.add_argument("--aid-confirm-model", action="append", default=None, metavar="READER.onnx",
                    help="wheelchair confirm reader ONNX (repeatable: the mean of the files' probabilities; optional, "
                         "off unless given, weights not in the repository; needs --aid-model with a head_centre "
                         "reading)")
    ap.add_argument("--aid-confirm-min", type=float, default=CONFIRM_MIN_DEFAULT, metavar="SCORE",
                    help="the confirm cut on the window median of the reader's wheelchair probability (default "
                         f"{CONFIRM_MIN_DEFAULT:g}: the reader's own decision point, the measurement's cut)")
    ap.add_argument("--aid-confirm-hold", action="store_true",
                    help="after the reader agrees with a wheelchair window, keep the user's later wheelchair windows "
                         "without reading until the engine ends the user's stretch (a new touch session, a new main "
                         "user, a window with no main user box or with no rows; aid_confirm.py); needs "
                         "--aid-confirm-model")
    ap.add_argument("--aid-confirm-hold-user", action="store_true",
                    help="after the reader agrees with a wheelchair window, every later window of the same user "
                         "answers aid_use true, whatever the engine's own window answer is, until the same four ends "
                         "(a new touch session, a new main user, a window with no main user box or with no rows; "
                         "includes --aid-confirm-hold; aid_confirm.py); needs --aid-confirm-model")
    ap.add_argument("--aid-start-only", action="store_true",
                    help="judge the walking aid at the start of each touch session (and again after a change of "
                         "main user the engine counts): at the first window after a press that answers no aid, "
                         "unless an aid was seen before, the walking-aid detector is off for the rest of that stretch "
                         "and its windows answer aid_use false (aid_confirm.py, 'Start only'); needs "
                         "--aid-confirm-model, not with the two hold options")
    ap.add_argument("--aid-stick-model", nargs="+", default=None, metavar="READER.onnx",
                    help="stick at the start: person-crop reader ONNX files (one or more) that read the main user's "
                         "crop on each row until the user is answered; a row is a stick frame when any file's "
                         "max(P(crutch), P(cane)) lies above 0.5 (each file's own decision point), and a user with "
                         "--aid-stick-frames such rows is answered aid_use true with the class cane (aid_confirm.py, "
                         "'Stick at the start'); optional, off unless given; needs --aid-confirm-model and "
                         "--aid-start-only")
    ap.add_argument("--aid-stick-frames", type=int, default=None, metavar="N",
                    help="the stick frames a user needs for the cane answer (no default: the runner gives it); "
                         "needs --aid-stick-model")


def check_aid_confirm_options(error, a, bundle_rule: str):
    """Stops (error(message), for example ap.error) when --aid-confirm-model comes without --aid-model or without a
    head_centre reading, names a missing file, or comes with a cut outside [0, 1]."""
    if getattr(a, "aid_confirm_hold", False) and not a.aid_confirm_model:
        error("--aid-confirm-hold needs --aid-confirm-model")
    if getattr(a, "aid_confirm_hold_user", False) and not a.aid_confirm_model:
        error("--aid-confirm-hold-user needs --aid-confirm-model")
    if getattr(a, "aid_start_only", False):
        if not a.aid_confirm_model:
            error("--aid-start-only needs --aid-confirm-model")
        if getattr(a, "aid_confirm_hold", False) or getattr(a, "aid_confirm_hold_user", False):
            error("--aid-start-only cannot be combined with --aid-confirm-hold or --aid-confirm-hold-user")
    stick = getattr(a, "aid_stick_model", None)
    if stick or getattr(a, "aid_stick_frames", None) is not None:
        if not stick or getattr(a, "aid_stick_frames", None) is None:
            error("--aid-stick-model and --aid-stick-frames go together")
        if not getattr(a, "aid_start_only", False):
            error("--aid-stick-model needs --aid-confirm-model and --aid-start-only")
        if a.aid_stick_frames is not None and a.aid_stick_frames < 1:
            error("--aid-stick-frames must be at least 1")
        for path in stick or ():
            if not os.path.isfile(path):
                error(f"--aid-stick-model: no file {path}")
    if not a.aid_confirm_model:
        return
    if not a.aid_model:
        error("--aid-confirm-model needs --aid-model")
    if bundle_rule not in AID_HEAD_RULES:
        error(f"--aid-confirm-model needs --aid-rule head_centre or head_centre_carry (now {bundle_rule})")
    for path in a.aid_confirm_model:
        if not os.path.isfile(path):
            error(f"--aid-confirm-model: no file {path}")
    if not 0.0 <= a.aid_confirm_min <= 1.0:
        error("--aid-confirm-min must lie in [0, 1]")


def load_aid_confirm(paths, cut: float, bundle, threads: int, log, hold: bool = False, hold_user: bool = False,
                     start_only: bool = False, stick_paths=None, stick_frames: int | None = None):
    """The wheelchair confirm step of --aid-confirm-model, or None (off without a file). Returns (step or None,
    {file: info}). stick_paths, stick_frames = --aid-stick-model, --aid-stick-frames (aid_confirm.py, 'Stick at the
    start'; one reader per file, each with the confirm reader's input size)."""
    if not paths:
        return None, {}
    from app.inference.aid_confirm import AidConfirmReader
    from .aid_confirm import AidConfirm
    reader = AidConfirmReader(paths, threads)
    stick = None
    if stick_paths:
        stick = [AidConfirmReader([p], threads) for p in stick_paths]
        for p, r in zip(stick_paths, stick):
            size = getattr(r, "size_hw", None)
            if size is not None and getattr(reader, "size_hw", size) != size:
                raise ValueError(f"--aid-stick-model {p}: input size {size} differs from the confirm reader's "
                                 f"{reader.size_hw} (one crop serves both)")
    step = AidConfirm(reader, cut, history_s(bundle) + bundle.chain.segment_s, hold, hold_user, log=log,
                      start_only=start_only, stick=stick, stick_min=stick_frames if stick else None,
                      stick_row_min=bundle.chain.aid_head_min if stick else None)
    if stick:
        log(f"지팡이 시작 판단 켬(--aid-stick-model): 파일 {len(stick)}개. 주 사용자의 사람 crop을 줄마다 읽어 어느 "
            f"파일이든 max(P(crutch), P(cane))가 0.5를 넘으면 지팡이 줄로 세고, 지팡이 줄이 {stick_frames}개 이상인 "
            "사용자는 보조기구 사용 참(지팡이)으로 답합니다. 탐지기가 휠체어로 읽은 줄이 나오면 그 사용자는 세지 않습니다")
    if start_only:
        log("보조기구 시작 판단 켬(--aid-start-only): 세션마다(엔진이 사용자 교체로 센 뒤에도) 첫 누름 뒤 보조기구 "
            "없음으로 판정한 창에서, 그 전에 보조기구를 본 적이 없으면 그 구간이 끝날 때까지 보조기구 탐지기를 "
            "끄고 보조기구 사용 아님으로 답합니다")
    log(f"휠체어 확인 분류기 켬: 파일 {len(paths)}개(여러 개면 확률 평균). 휠체어로 판정한 창은 같은 창에서 분류기의 "
        f"휠체어 확률 중앙값이 {cut:g}를 넘을 때만 유지합니다"
        + ("; 한 번 맞으면 같은 사용자의 뒤 휠체어 창은 다시 읽지 않고 유지합니다" if hold and not hold_user else "")
        + ("; 한 번 맞으면 같은 사용자의 뒤 창은 엔진 답과 관계없이 보조기구 사용 참으로 답합니다" if hold_user else "")
        + ("(새 세션 · 사용자 교체 · 주 사용자 상자 없는 창 · 줄 없는 창에서 끝나고 다시 확인)" if hold or hold_user else ""))
    info = {os.path.basename(p): {"bytes": os.path.getsize(p), "sha256": sha256(p), "role": "aid_confirm"}
            for p in paths}
    for p in stick_paths or ():
        info.setdefault(os.path.basename(p), {"bytes": os.path.getsize(p), "sha256": sha256(p), "role": "aid_stick"})
    return step, info


def stick_kwargs(a) -> dict:
    """load_aid_confirm's keywords of --aid-stick-model / --aid-stick-frames ({} when not given: the call as before)."""
    paths = getattr(a, "aid_stick_model", None)
    return {"stick_paths": paths, "stick_frames": a.aid_stick_frames} if paths else {}


def add_aid_options(ap):
    """--aid-rule and --aid-head-min, next to --aid-model (params.py aid_rule, aid_head_min). Unset: the value
    bundle's value (by default the owner_box reading and no cut)."""
    ap.add_argument("--aid-rule", default=None, choices=AID_RULES,
                    help="how the walking-aid detector is read (params.py aid_rule): owner_box = the main user's "
                         "person box (the default), head_centre = the aid-class box that holds the centre of the main "
                         "user's head box (the kiosk-view detector files), head_centre_carry = head_centre with that "
                         "box followed through the frames without the head box (the head tracker's rule); overrides "
                         "the value bundle; needs --aid-model")
    ap.add_argument("--aid-head-min", type=float, default=None, metavar="SCORE",
                    help="the aid_use cut of the head_centre and head_centre_carry readings (params.py aid_head_min; "
                         "no default: without it aid_use stays unknown, no_value_for_model); overrides the value "
                         "bundle; needs --aid-model")


def aid_values(a) -> dict:
    """{chain field: value} of the aid options given on the command line ({} when neither is: the bundle as it is)."""
    return {k: v for k, v in (("aid_rule", a.aid_rule), ("aid_head_min", a.aid_head_min)) if v is not None}


def check_aid_options(ap, a):
    """Stops the parser (ap.error) when an aid option comes without --aid-model or with a value PilotParams refuses."""
    values = aid_values(a)
    if values and not a.aid_model:
        ap.error("--aid-rule / --aid-head-min need --aid-model")
    try:
        PilotParams(**values)
    except ValueError as e:
        ap.error(f"--aid-rule / --aid-head-min: {e}")


def load_phones(path: str | None, params, threads: int, log):
    """The phone detector of --phone-model (the COCO YOLOX-Nano ONNX of the YOLOX release), or None (off unless a file
    is given; the weights are not in this repository). Returns (detector or None, {file: info})."""
    if not path:
        return None, {}
    if not os.path.isfile(path):
        raise FileNotFoundError(f"--phone-model: no file {path}")
    from app.inference.phone import PhoneDetector
    detector = PhoneDetector(path, params.phone_score_min, params.phone_nms_iou, threads)
    log("휴대폰 탐지기 켬(COCO 'cell phone'). 키오스크 시점 정확도는 재지 않았습니다")
    return detector, {os.path.basename(path): {"bytes": os.path.getsize(path), "sha256": sha256(path),
                                               "licence": "Apache-2.0 (YOLOX, Megvii)"}}


def environment() -> dict:
    env = {"python": platform.python_version(), "platform": platform.platform(), "cpu_count": os.cpu_count()}
    for mod in ("numpy", "cv2", "mediapipe", "onnxruntime"):
        try:
            env[mod] = __import__(mod).__version__
        except Exception:   # not installed: say so
            env[mod] = None
    return env


def frame_flags(row: dict) -> dict:
    """Which perception outputs one row has: a face seen, at least one head box (H1), a head direction (P1)."""
    return {"with_face": row.get("face_state") == SEEN, "with_heads": (row.get("head_count") or 0) >= 1,
            "with_direction": row.get("head_dir_middle") is not None}


def add_frame_counts(counts: dict, row: dict) -> dict:
    """counts (meta counts.frames) with one more row."""
    for key, present in frame_flags(row).items():
        counts[key] = counts.get(key, 0) + int(present)
    return counts


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
               model_info: dict | None = None, settings: dict | None = None, log=print, aids=None,
               phones=None, aid_confirm=None) -> dict:
    """Run the chain over a frame source (sources.VideoFileSource or any iterable of sources.Frame) and write the
    outputs. models = MediaPipe models (or a fake with .infer(frame)); detector / direction = perception models or
    None. Returns the meta dict (also written to meta.json)."""
    os.makedirs(out_dir, exist_ok=True)
    chain = FrameChain(models, bundle.chain, detector, direction, timeline, blendshapes=blendshapes,
                       source_kind=SOURCE_KIND.get(getattr(source, "kind", ""), ""), aids=aids, phones=phones,
                       aid_confirm=aid_confirm)
    judge = WindowJudge(bundle, timeline, session_id=session_id, aid_confirm=aid_confirm)
    keep_s = history_s(bundle)
    rows, recent, records = [], deque(), []
    next_t, partial_s = None, None
    wall0 = time.perf_counter()
    stop_reason = "input ended"
    with open(os.path.join(out_dir, "windows.jsonl"), "w", encoding="utf-8") as out:
        def emit(t_end, seg_len=None):
            window_rows = [r for r in recent if float(r["t_s"]) >= t_end - keep_s]
            rec = judge.evaluate(window_rows, t_end, segment_s=seg_len)
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
        last_end = None if next_t is None else next_t - bundle.chain.segment_s
        if rows and last_end is not None and float(rows[-1]["t_s"]) > last_end:   # rows after the last full window
            partial_s = float(rows[-1]["t_s"]) - last_end
            emit(float(rows[-1]["t_s"]), partial_s)
    wall_s = time.perf_counter() - wall0
    write_rows(os.path.join(out_dir, "rows.csv"), rows)
    frame_counts = {"with_face": 0, "with_heads": 0, "with_direction": 0}
    for row in rows:
        add_frame_counts(frame_counts, row)
    tags, transitions, supports = {}, {}, {}
    session_resets = sum(rec["session_reset"] for rec in records)
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
            "counts": {"situation": tags, "transition": transitions, "opened_support": supports,
                       "frames": frame_counts, "session_resets": session_resets},
            "last_window_partial_s": None if partial_s is None else round(partial_s, 4),
            "jev_questions_recorded": len(judge.jev.log)}
    if aid_confirm is not None:
        meta["aid_confirm"] = aid_confirm.summary()
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
    ap.add_argument("--aid-model", default=None,
                    help="walking-aid detector ONNX (optional; off unless given, weights not in the repository)")
    add_aid_options(ap)
    add_aid_confirm_options(ap)
    ap.add_argument("--phone-model", default=None,
                    help="COCO YOLOX-Nano ONNX for the phone (optional; off unless given, weights not in the "
                         "repository; without --touch-log phone_use is never true, as the companion "
                         "path needs the touch counts too: false where the phone part or the body-still part is "
                         "false, otherwise unknown (column:tap_count when the phone part holds))")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)
    check_aid_options(ap, a)
    if os.path.isfile(os.path.join(a.out, "windows.jsonl")) and not a.overwrite:
        ap.error(f"{a.out} already holds a replay - choose another --out or add --overwrite")
    bundle = with_options(load_bundle(a.params), aid_values(a))
    check_aid_confirm_options(ap.error, a, bundle.chain.aid_rule)
    timeline = None
    if a.touch_log:
        from .touch import load_timeline
        timeline = load_timeline(a.touch_log, a.video, a.start_offset)
        for warning in timeline.meta.get("warnings", []):
            print(f"터치 로그 경고: {warning}", flush=True)
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
    aids, aid_info = load_aids(a.aid_model, bundle.chain, a.threads, print)
    info.update(aid_info)
    aid_confirm, confirm_info = load_aid_confirm(a.aid_confirm_model, a.aid_confirm_min, bundle, a.threads, print,
                                                 a.aid_confirm_hold, a.aid_confirm_hold_user, a.aid_start_only,
                                                 **stick_kwargs(a))
    info.update(confirm_info)
    phones, phone_info = load_phones(a.phone_model, bundle.chain, a.threads, print)
    info.update(phone_info)
    models = MediaPipeModels(a.models, blendshapes=a.blendshapes)
    settings = {"step": a.step, "width": a.width, "threads": a.threads, "blendshapes": a.blendshapes,
                "heads": detector is not None, "head_direction": direction is not None, "aids": aids is not None,
                "phones": phones is not None,
                **({"aid_confirm": {"files": len(a.aid_confirm_model), "cut": a.aid_confirm_min,
                                    "hold": a.aid_confirm_hold, "hold_user": a.aid_confirm_hold_user,
                                    **({"start_only": True} if a.aid_start_only else {}),
                                    **({"stick": {"files": len(a.aid_stick_model), "frames": a.aid_stick_frames}}
                                       if a.aid_stick_model else {})}}
                   if aid_confirm is not None else {}),
                "face_landmarker": "VIDEO, num_faces=1, transformation matrix on, blendshapes "
                                   + ("on" if a.blendshapes else "off"),
                "touch_log": a.touch_log, "start_offset_s": a.start_offset, "params_file": a.params}
    print(f"재생 시작: {source.name} → {a.out}", flush=True)
    try:
        meta = run_replay(source, a.out, bundle, timeline=timeline, models=models, detector=detector,
                          direction=direction, blendshapes=a.blendshapes, max_seconds=a.max_seconds,
                          session_id=a.session_id or os.path.splitext(os.path.basename(a.video))[0],
                          model_info=info, settings=settings, aids=aids, phones=phones, aid_confirm=aid_confirm)
    finally:
        models.close()
    tm = meta["timing_ms"].get("ms_chain") or {}
    print(f"끝: 프레임 {meta['frames']}장 · 창 {meta['windows']}개 · 상황 {meta['counts']['situation']} · "
          f"전이 {meta['counts']['transition']} · 프레임 처리 p50 {tm.get('p50')} ms → {a.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
