"""Run the vision skeleton on one video file or image folder - or, only when asked with --camera, on the webcam.

From ai-server/, after python app/modules/vision/models/download_models.py:
  python -m app.modules.vision.run INPUT [--out DIR] [--fps 15] [--step 2] [--width 640] [--show]
  python -m app.modules.vision.run --camera 0 --show [--seconds 30] [--cam-width 640 --cam-height 480]
  python -m app.modules.vision.run --replot DIR   (rebuild timing.csv, plots, contact sheet, meta.json from the CSV)

Without --out the run folder is runs/live_<YYYY-MM-DD>_<HHMM> (camera) or runs/<input name>_<YYYY-MM-DD>_<HHMM>
(file or folder) next to this file (git-ignored), local time; seconds are added only if that folder exists. It is
printed at the start and the end.

overlay.mp4 plays at the effective frame rate when frame times are measured (camera, a recorded clip with its
sidecar), so a camera run that processed fewer frames than the camera offers plays in real time; file inputs keep
their source rate. meta.json keeps both rates (fps_nominal, fps_effective) and overlay_fps.

--show opens a window with the same composed frames as overlay.mp4 (render.compose_frame), sized to fit the screen
and letterboxed when resized; q, closing the window or Ctrl+C stops early, and the frames processed so far are saved.
The run folder is written the same with or without --show.

Layers (README.md): sources.py (입력) -> inference.py (추론) -> features.py (관측값) -> situation.py (상황, a
placeholder, not called yet) -> outputs here; 전달 to other services is not built yet.

Writes into the run folder: observations.csv, overlay.mp4, contact_sheet.png, plot_observations.png,
plot_quality_timing.png, timing.csv, meta.json (+ manifest.json for synthetic input) and run.log (start and end of
every step, the full traceback of any error, and a native-crash dump if the process dies without a Python error).
Each output is written on its own, so one failing step does not stop the others; on a failure a one-line Korean
message names the failed steps and the log. README.md explains the files.
"""
from __future__ import annotations

import argparse
import csv
import faulthandler
import hashlib
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import time

import cv2
import numpy as np

from app.modules.vision import render
from app.modules.vision.features import COLUMNS, Observer
from app.modules.vision.inference import (FACE_DETECTOR_MODELS, FACE_LANDMARKER_MODEL, POSE_LANDMARKER_MODEL,
                                          MediaPipeModels, environment)
from app.modules.vision.sources import LiveCameraSource, effective_fps, open_source

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
WINDOW = "vision live (q = stop)"   # ASCII title: OpenCV window titles on Windows may not show Korean
LOG_NAME = "run.log"
STEP_KO = {"setup": "입력 · 모델 열기", "frames": "프레임 처리", "close models": "모델 닫기",
           "overlay video": "오버레이 영상", "observations.csv": "관측 CSV", "timing.csv": "시간 표",
           "plot_observations": "관측 그래프", "plot_quality_timing": "품질 · 시간 그래프",
           "contact_sheet": "모아 보기", "meta.json": "meta.json", "read observations.csv": "관측 CSV 읽기",
           "overlay re-time": "오버레이 영상 속도 맞추기"}
KIND_FROM_KO = {"영상": "video", "이미지": "folder", "합성": "folder", "카메라": "camera"}   # source_kind column
TEXT_COLUMNS = {"src_frame", "source_kind", "syn_phase", "face_state", "body_state"}
INT_COLUMNS = {"frame_idx", "face_count"}


def workspace_path(p: str) -> str:
    """Path relative to this folder when the file is inside it (so runs/ survives a move of the folder),
    otherwise absolute."""
    ap = os.path.abspath(p)
    try:
        rel = os.path.relpath(ap, CODE_DIR)
    except ValueError:          # another drive
        return ap
    return ap if rel.startswith("..") else rel


def _cell(v):
    if isinstance(v, float):
        return "" if math.isnan(v) else f"{v:.6g}"
    return v


def _pin_process(mask: int | None, high: bool) -> dict:
    """Optional measurement condition (Windows): restrict the process to the logical CPUs in `mask` and/or raise
    its priority. Team convention for timing on the i5-1340P dev PC: P-cores = logical CPUs 0-7 (mask 0xFF) and
    high priority, because unpinned runs were 2-2.5x slower (workspace note research/13, section 5-2 footnote)."""
    done = {"affinity_mask": None, "high_priority": False}
    if os.name != "nt" or (mask is None and not high):
        return done
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    h = ctypes.c_void_p(k32.GetCurrentProcess())
    if mask is not None and k32.SetProcessAffinityMask(h, ctypes.c_size_t(mask)):
        done["affinity_mask"] = hex(mask)
    if high and k32.SetPriorityClass(h, 0x00000080):   # HIGH_PRIORITY_CLASS
        done["high_priority"] = True
    return done


def _finish_overlay(tmp_path: str, out_path: str, rate: float | None = None) -> tuple[str, bool]:
    """Turn the MPEG-4 Part 2 file written during the run into H.264, after all timing is done (so encoding
    never competes with the measured stages). Uses the ffmpeg binary of imageio-ffmpeg with libx264 defaults;
    H.264 plays in browsers and on phones and was about 5x smaller here. `rate` (the effective frame rate of
    measured frame times) replaces the rate the file was written at: ffmpeg's input option -r "ignores any
    timestamps stored in the file and generates timestamps assuming constant frame rate" (ffmpeg docs), so every
    frame is kept and playback speed follows the measured times. Without imageio-ffmpeg the MPEG-4 Part 2 file is
    kept as it is (written rate). The ffmpeg process gets no window. Returns (codec text, rate applied)."""
    try:
        import imageio_ffmpeg
    except ImportError:
        os.replace(tmp_path, out_path)
        return "MPEG-4 Part 2 (OpenCV FFmpeg backend)", False
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error"]
    if rate:
        cmd += ["-r", f"{rate:.6f}"]
    cmd += ["-i", tmp_path,
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",          # yuv420p needs even width and height
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path]
    subprocess.run(cmd, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    os.remove(tmp_path)
    return "H.264 (libx264 defaults, ffmpeg from imageio-ffmpeg)", bool(rate)


def _retime_overlay(path: str, from_fps: float, to_fps: float):
    """Change the playback rate of an existing overlay video without re-encoding: ffmpeg -itsscale scales every
    input timestamp, -c copy keeps the compressed frames as they are."""
    import imageio_ffmpeg
    tmp = os.path.join(os.path.dirname(path), "overlay_retime_tmp.mp4")
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-itsscale", f"{from_fps / to_fps:.9f}",
           "-i", path, "-c", "copy", "-movflags", "+faststart", tmp]
    subprocess.run(cmd, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    os.replace(tmp, path)


def _video_info(path: str) -> tuple:
    """(width, height, container frame rate, frame count) as OpenCV reads them."""
    cap = cv2.VideoCapture(path)
    out = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
           float(cap.get(cv2.CAP_PROP_FPS)) or None, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    cap.release()
    return out


def default_out(input_path: str | None, camera: int | None) -> str | None:
    """Run folder when --out is not given: runs/live_<YYYY-MM-DD>_<HHMM> for the camera, runs/<input name>_<YYYY-MM-DD>
    _<HHMM> for a video file (name without extension) or an image folder, in local time - no running numbers
    (vision owner's choice, 2026-10-08). Seconds are added only when that folder already exists; None if that one exists too."""
    if camera is not None:
        name = "live"
    else:
        base = os.path.basename(os.path.normpath(input_path))
        name = os.path.splitext(base)[0] if os.path.isfile(input_path) else base
    now = time.localtime()
    folder = os.path.join(CODE_DIR, "runs", f"{name}_{time.strftime('%Y-%m-%d_%H%M', now)}")
    if not os.path.exists(folder):
        return folder
    folder += time.strftime("%S", now)
    return None if os.path.exists(folder) else folder


def nominal_fps(meta: dict):
    """The rate the source states; `fps_processed` in run folders made before fps_nominal / fps_effective."""
    return meta.get("fps_nominal", meta.get("fps_processed"))


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------------------------------- log and steps
def _open_log(folder: str) -> logging.Logger:
    """run.log in the run folder, appended (one header line per call). Every record is flushed at once, so the
    log shows the last step that started even if the process is killed. faulthandler writes the Python stack
    of a native crash (no Python exception) into the same file."""
    log = logging.getLogger("vision.run")
    log.setLevel(logging.INFO)
    log.propagate = False
    if log.handlers:
        faulthandler.disable()
        for h in list(log.handlers):
            log.removeHandler(h)
            h.close()
    h = logging.FileHandler(os.path.join(folder, LOG_NAME), mode="a", encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.info("=== run.py %s (pid %d; a native-crash dump from faulthandler would also appear here)",
             " ".join(sys.argv[1:]), os.getpid())
    faulthandler.enable(file=h.stream, all_threads=True)
    return log


def _step(log, failed: list, name: str, fn):
    """Run one step; log its start, end and any exception with the full traceback. A failure is recorded in
    `failed` and the caller goes on with the next step. Ctrl+C is logged with the step name and passed on."""
    log.info("start: %s", name)
    t0 = time.perf_counter()
    try:
        out = fn()
    except KeyboardInterrupt:
        log.warning("INTERRUPTED (Ctrl+C) during: %s - the later steps did not run", name)
        failed.append(name)
        raise
    except Exception:
        log.exception("FAILED: %s", name)
        failed.append(name)
        return None
    log.info("end: %s (%.2f s)", name, time.perf_counter() - t0)
    return out


def _report_failures(failed: list, folder: str) -> int:
    if not failed:
        return 0
    names = ", ".join(STEP_KO.get(n, n) for n in failed)
    print(f"실패한 단계: {names} — 오류 전문은 {os.path.join(folder, LOG_NAME)}", file=sys.stderr)
    return 1


def _guarded(fn, folder: str) -> int:
    """Turn Ctrl+C during saving, or an error outside a step, into a logged event and a one-line Korean message."""
    log_path = os.path.join(folder, LOG_NAME)
    log = logging.getLogger("vision.run")
    try:
        return fn()
    except KeyboardInterrupt:
        log.warning("stopped by Ctrl+C")
        hint = (f" 남은 결과는 'python -m app.modules.vision.run --replot {folder}'로 다시 만들 수 있습니다."
                if os.path.isfile(os.path.join(folder, "observations.csv")) else "")
        print(f"Ctrl+C로 중간에 멈췄습니다 — 어느 단계에서 멈췄는지: {log_path}.{hint}", file=sys.stderr)
        return 130
    except Exception:
        if not log.handlers:          # failed before the log existed: plain traceback
            raise
        log.exception("FAILED (outside a step)")
        print(f"오류로 멈췄습니다 — 오류 전문은 {log_path}", file=sys.stderr)
        return 1


# ------------------------------------------------------------------------------------------- output writers
def _write_observations(folder: str, rows: list):
    with open(os.path.join(folder, "observations.csv"), "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        wr.writerow(COLUMNS)
        for r in rows:
            wr.writerow([_cell(r[c]) for c in COLUMNS])


def _write_timing(folder: str, rows: list) -> list:
    stats = render.timing_stats(rows)
    with open(os.path.join(folder, "timing.csv"), "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=list(stats[0].keys()))
        wr.writeheader()
        for s in stats:
            wr.writerow({k: _cell(v) for k, v in s.items()})
    return stats


def _plots(log, failed, folder, rows, header, phase_labels):
    _step(log, failed, "plot_observations", lambda: render.plot_observations(
        rows, f"{header} — 관측 시계열", os.path.join(folder, "plot_observations.png"), phase_labels))
    _step(log, failed, "plot_quality_timing", lambda: render.plot_quality_timing(
        rows, f"{header} — 측정 신뢰도 재료 · 처리 시간", os.path.join(folder, "plot_quality_timing.png"), phase_labels))


# ------------------------------------------------------------------------------------------- live window (--show)
def _work_area():
    """(x, y, width, height) of the screen without the taskbar (Windows SPI_GETWORKAREA), in the pixels OpenCV's
    windows use (this process is not DPI-aware, so Windows scales both the same way); None elsewhere."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    r = wintypes.RECT()
    if not ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):   # SPI_GETWORKAREA
        return None
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def _frame_extra() -> tuple:
    """Width and height a resizable top-level window adds around its picture (title bar, sizing border):
    AdjustWindowRectEx for WS_OVERLAPPEDWINDOW."""
    import ctypes
    from ctypes import wintypes
    r = wintypes.RECT(0, 0, 0, 0)
    ctypes.windll.user32.AdjustWindowRectEx(ctypes.byref(r), 0x00CF0000, False, 0)   # WS_OVERLAPPEDWINDOW
    return r.right - r.left, r.bottom - r.top


def fit_size(img_wh, avail_wh) -> tuple:
    """Largest size with the picture's aspect ratio inside avail_wh, never larger than the picture itself
    (enlarging would only blur the panel text; the window can still be enlarged by hand)."""
    (w, h), (aw, ah) = img_wh, avail_wh
    s = min(1.0, aw / w, ah / h)
    return max(1, int(w * s)), max(1, int(h * s))


def letterbox(img: np.ndarray, size_wh, color) -> np.ndarray:
    """img scaled to fit size_wh with its aspect ratio kept, centred on a `color` background. OpenCV's Win32 window
    stretches the picture to the window, so a window resized by hand would otherwise distort it. INTER_AREA to
    shrink, INTER_LINEAR to enlarge (OpenCV resize docs)."""
    W, H = size_wh
    h, w = img.shape[:2]
    s = min(W / w, H / h)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    out = np.empty((H, W, 3), np.uint8)
    out[:] = color
    x, y = (W - nw) // 2, (H - nh) // 2
    out[y:y + nh, x:x + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    return out


def _place_window(name: str, w: int, h: int, log):
    """Size the window to the picture, shrunk to fit the work area if needed, at the work area's top-left."""
    area = _work_area()
    if area is None:
        return
    ex_w, ex_h = _frame_extra()
    fw, fh = fit_size((w, h), (area[2] - ex_w, area[3] - ex_h))
    cv2.resizeWindow(name, fw, fh)
    cv2.moveWindow(name, area[0], area[1])
    log.info("window: picture %dx%d, work area %dx%d, window picture area %dx%d", w, h, area[2], area[3], fw, fh)


# ------------------------------------------------------------------------------------------- one run
def run(args) -> int:
    pinned = _pin_process(int(args.affinity, 0) if args.affinity else None, args.high_priority)
    os.makedirs(args.out, exist_ok=True)
    log = _open_log(args.out)
    print(f"결과 폴더: {workspace_path(args.out)}", flush=True)
    return _run(args, log, pinned)


def _run(args, log, pinned) -> int:
    log_path = os.path.join(args.out, LOG_NAME)
    failed: list = []

    def _setup():
        if args.camera is not None:
            src = LiveCameraSource(args.camera, args.cam_width, args.cam_height, args.backend, args.fps, args.seconds)
        else:
            src = open_source(args.input, fps=args.fps, step=args.step, width=args.width)
        models = MediaPipeModels(args.models, face_detector=args.face_detector)
        return src, models, Observer(models)

    opened = _step(log, failed, "setup", _setup)
    if opened is None:
        return _report_failures(failed, args.out)
    src, models_rt, obs = opened
    env = environment()
    if src.manifest is not None:   # keep the generator's parameters with the run
        shutil.copyfile(os.path.join(args.input, "manifest.json"), os.path.join(args.out, "manifest.json"))
    kind = {"video": "영상", "folder": "이미지", "camera": "카메라"}[src.kind]
    kind = "합성" if src.synthetic else kind
    phase_labels = (src.manifest or {}).get("phase_labels", {})
    header = f"[합성 입력] {src.name}" if src.synthetic else src.name
    if args.face_detector != "short_range":
        header += f" · 얼굴 검출 {args.face_detector.replace('_', '-')}"
    n_expected = src.expected_frames()
    tile_idx = set(np.linspace(0, max(n_expected - 1, 0), args.tiles).round().astype(int).tolist())

    rows, tiles, last, writer = [], [], None, None
    frame_shape = None   # the overlay video keeps the first frame's size, so a size change is an error
    overlay_tmp = os.path.join(args.out, "overlay_tmp.mp4")
    # Output-only costs, timed apart from the measured stages (ms_* in observations.csv).
    out_ms = {"compose": [], "video_write": [], "window": []}
    stopped_early, stop_reason = False, None
    log.info("start: frames (input %s, %d expected)", src.name, n_expected)
    if args.show:   # live window; never used by the offline commands or the tests
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    placed = False
    frames = iter(src)
    t_run = time.perf_counter()
    try:
        for fr in frames:
            shape = fr.image.shape[:2]
            if frame_shape is None:
                frame_shape = shape
            elif shape != frame_shape:
                raise ValueError(f"frame size changed within the input: {frame_shape[::-1]} -> {shape[::-1]} "
                                 "(frames of one run must have one size)")
            phase = src.phase_of(fr.src_ref) if src.kind == "folder" else ""
            row, draw = obs.process(fr, source_kind=kind, syn_phase=phase)
            rows.append(row)
            t0 = time.perf_counter()
            ann, ov = render.compose_frame(fr.image, draw, row, header, phase_labels.get(phase, ""))
            out_ms["compose"].append((time.perf_counter() - t0) * 1000.0)
            if writer is None:
                h, w = ov.shape[:2]
                # In-process MPEG-4 Part 2 between frames (outside the timed stages); H.264 conversion comes after
                # the run. OpenCV's own H.264 path (Media Foundation) gave no size control and ~2x the bitrate here.
                writer = cv2.VideoWriter(overlay_tmp, cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*"mp4v"), src.fps, (w, h))
                if not writer.isOpened():
                    raise IOError("cannot open the overlay video writer")
            t0 = time.perf_counter()
            writer.write(ov)
            out_ms["video_write"].append((time.perf_counter() - t0) * 1000.0)
            if fr.index in tile_idx:
                tiles.append((ann, row))
            last = (ann, row)
            if args.show:
                t0 = time.perf_counter()
                if not placed:
                    _place_window(WINDOW, ov.shape[1], ov.shape[0], log)
                    placed = True
                shown = ov
                try:
                    _, _, ww, wh = cv2.getWindowImageRect(WINDOW)
                    if ww > 0 and wh > 0 and (ww, wh) != (ov.shape[1], ov.shape[0]):
                        shown = letterbox(ov, (ww, wh), render.PANEL_BG)
                except cv2.error:
                    pass
                cv2.imshow(WINDOW, shown)
                key = cv2.waitKey(1) & 0xFF
                out_ms["window"].append((time.perf_counter() - t0) * 1000.0)
                if key == ord("q"):
                    stopped_early, stop_reason = True, "q in the window"
                    log.info("stopped early: q in the window")
                    break
                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    stopped_early, stop_reason = True, "window closed"
                    log.info("stopped early: the window was closed")
                    break
    except KeyboardInterrupt:
        stopped_early, stop_reason = True, "Ctrl+C"
        log.info("stopped early: Ctrl+C - going on with the %d frames processed", len(rows))
    except Exception:
        stop_reason = "error (run.log)"
        log.exception("FAILED: frames (after %d frames) - going on with the frames processed", len(rows))
        failed.append("frames")
    finally:
        frames.close()          # releases a camera / video file even after an early stop
        if args.show:
            cv2.destroyAllWindows()
            cv2.waitKey(1)      # let the window message loop run once so the window really closes
    stop_reason = stop_reason or getattr(src, "end_reason", None) or "input ended"
    wall_s = time.perf_counter() - t_run
    log.info("end: frames (%d frames, %.1f s, stopped early: %s, reason: %s)", len(rows), wall_s, stopped_early,
             stop_reason)
    _step(log, failed, "close models", models_rt.close)
    if not rows:
        log.error("no frame was processed - nothing to save")
        print(f"처리한 프레임이 없어 저장할 결과가 없습니다 — 기록: {log_path}", file=sys.stderr)
        return 1
    print(f"프레임 {len(rows)}장 처리 끝 — 결과 파일을 저장하는 중입니다. 끝났다는 줄이 나올 때까지 콘솔을 닫지 "
          f"마세요(진행 기록: {log_path})", flush=True)
    if last is not None and all(r["frame_idx"] != last[1]["frame_idx"] for _, r in tiles):
        tiles.append(last)   # container frame counts can be approximate: keep the real last frame
    # Frame rates: nominal = what the source states; effective = from measured frame times (camera, a recorded
    # clip's sidecar), so a camera run that processed fewer frames than the camera offers plays back in real time.
    fps_eff = effective_fps([r["t_s"] for r in rows]) if src.measured_times else None
    log.info("frame rate: nominal %.3f fps, effective %s", src.fps,
             f"{fps_eff:.3f} fps (from measured frame times)" if fps_eff else "- (frame times are index / fps)")
    overlay_fps = None

    def _overlay():
        nonlocal overlay_fps
        if writer is not None:
            writer.release()
        codec, retimed = _finish_overlay(overlay_tmp, os.path.join(args.out, "overlay.mp4"), fps_eff)
        overlay_fps = fps_eff if retimed else src.fps
        log.info("overlay.mp4 at %.3f fps (%s)", overlay_fps, "effective" if retimed else "as written")
        return codec

    # Each output on its own: one failing step does not skip the others (run.log names the failed ones).
    overlay_codec = _step(log, failed, "overlay video", _overlay) or "not written - see run.log"
    _step(log, failed, "observations.csv", lambda: _write_observations(args.out, rows))
    stats = _step(log, failed, "timing.csv", lambda: _write_timing(args.out, rows))
    _plots(log, failed, args.out, rows, header, phase_labels)
    syn_note = " · 사진을 키우고·옮기고·돌리고·지운 프레임" if src.synthetic else ""

    def _sheet():
        sheet = tiles
        ov_path = os.path.join(args.out, "overlay.mp4")
        if len(rows) != n_expected and tiles and os.path.isfile(ov_path):
            # The run ended at another frame count than the source announced (stopped early, or a camera slower than
            # its nominal rate), so the tiles picked during the loop do not spread over what was processed: take
            # evenly spaced frames of the processed run from the overlay video instead.
            picked = _tiles_from_video(ov_path, rows, args.tiles, tiles[0][0].shape[1])
            if picked:
                sheet = picked
                log.info("contact sheet: %d frames re-picked from overlay.mp4 (%d processed, %d expected)",
                         len(picked), len(rows), n_expected)
        render.contact_sheet(sheet, f"{header} — 프레임 {len(sheet)}장 (고르게 뽑음){syn_note}",
                             os.path.join(args.out, "contact_sheet.png"), phase_labels)

    _step(log, failed, "contact_sheet", _sheet)

    def _meta():
        H, W = tiles[0][0].shape[:2] if tiles else (0, 0)
        models = {}
        for name in (FACE_LANDMARKER_MODEL, models_rt.face_detector_model, POSE_LANDMARKER_MODEL):
            p = os.path.join(args.models, name)
            models[name] = {"path": workspace_path(p), "bytes": os.path.getsize(p), "sha256": _sha256(p)}
        meta = {
            "input": workspace_path(args.input) if args.input else f"camera {args.camera}",
            "input_name": src.name, "input_kind": src.kind, "synthetic": src.synthetic,
            "frame_time_source": src.time_source,
            "source_note": args.source_note or (src.manifest or {}).get("note", ""),
            # nominal = rate the source states: camera driver (or --fps), video container / --step, image-folder
            # manifest / --fps. effective = (frames - 1) / (last - first frame time), only for measured frame times
            # (camera, a recorded clip's sidecar); null when frame times are index / fps. overlay_fps = overlay.mp4.
            "fps_nominal": src.fps, "fps_effective": fps_eff, "overlay_fps": overlay_fps,
            "step": args.step, "width_arg": args.width, "frame_size_wh": [W, H],
            "frames_processed": len(rows), "frames_expected_from_source": n_expected,
            "session_reference_t_s": obs.ref["t_s"] if obs.ref else None,
            "settings": {"face_landmarker": "VIDEO, num_faces=1, transformation matrix on, blendshapes off, "
                                            "confidences library default 0.5",
                         "face_detector": f"VIDEO, {args.face_detector.replace('_', '-')}, library defaults",
                         "pose_landmarker": "VIDEO, lite, num_poses=1, library defaults"},
            "models": models, "environment": env, "timing_condition": pinned,
            "wall_time_s": wall_s, "stopped_early": stopped_early, "stop_reason": stop_reason,
            "shown_in_window": bool(args.show),
            # output-only costs per frame, NOT part of the measured stages: drawing the overlay frame, writing it to
            # the video, showing it in the window (--show). p50 / p95 over all frames.
            "output_ms": {k: ({"p50": float(np.percentile(v, 50)), "p95": float(np.percentile(v, 95)), "n": len(v)}
                              if v else None) for k, v in out_ms.items()},
            "overlay_codec": overlay_codec,
            "failed_steps": list(failed),           # steps that failed before meta.json was written (run.log)
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(os.path.join(args.out, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta

    meta = _step(log, failed, "meta.json", _meta)
    seen = sum(r["face_state"] == "보임" for r in rows)
    line = f"{src.name}: {len(rows)} frames ({n_expected} expected), face seen {seen}/{len(rows)}"
    if stats:
        tot = next(s for s in stats if s["stage"] == "ms_total")
        line += f", total p50 {tot['p50_ms']:.1f} ms p95 {tot['p95_ms']:.1f} ms"
    comp = ((meta or {}).get("output_ms") or {}).get("compose")
    if comp:
        line += f" | overlay drawing (not in total) p50 {comp['p50']:.1f} ms p95 {comp['p95']:.1f} ms"
    if fps_eff:
        line += f" | {fps_eff:.1f} fps measured (nominal {src.fps:g})"
    print(line + f" | wall {wall_s:.1f} s" + (f" | stopped early ({stop_reason})" if stopped_early else "")
          + f" -> {args.out}", flush=True)
    log.info("done (failed steps: %s)", ", ".join(failed) or "none")
    print(f"저장 끝 — 결과 폴더: {workspace_path(args.out)}", flush=True)
    return _report_failures(failed, args.out)

# ------------------------------------------------------------------------------------------- --replot
def _read_rows(path: str) -> list:
    """observations.csv back into rows: blank -> NaN, numbers -> float (frame_idx, face_count -> int)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        raw = list(csv.DictReader(f))

    def conv(k, v):
        if k in TEXT_COLUMNS:
            return v
        if v == "":
            return float("nan")
        return int(float(v)) if k in INT_COLUMNS else float(v)
    return [{k: conv(k, v) for k, v in r.items()} for r in raw]


def _even_indices(n_rows: int, n_tiles: int) -> set:
    return set(np.linspace(0, n_rows - 1, n_tiles).round().astype(int).tolist())


def _tiles_from_video(path: str, rows: list, n_tiles: int, crop_w: int | None) -> list:
    """Evenly spaced frames read back from the overlay video (frame i = CSV row i), cut to the image part."""
    want = _even_indices(len(rows), n_tiles)
    cap = cv2.VideoCapture(path)
    tiles = []
    for i in range(max(want) + 1):
        ok, fr = cap.read()
        if not ok:
            break
        if i in want:
            tiles.append((fr[:, :crop_w] if crop_w else fr, rows[i]))
    cap.release()
    return tiles


def _tiles_from_source(src, rows: list, n_tiles: int) -> list:
    """Evenly spaced frames from the run's own input, opened again the way the run opened it (no drawing)."""
    want = _even_indices(len(rows), n_tiles)
    tiles, frames = [], iter(src)
    try:
        for fr in frames:
            if fr.index > max(want):
                break
            if fr.index in want:
                tiles.append((fr.image, rows[fr.index]))
    finally:
        frames.close()
    return tiles


def _input_source(meta: dict | None):
    """The run's input opened again (video or image folder with the recorded step / width / fps), or None when the
    input is not recorded, is a camera, or is gone."""
    if not meta or meta.get("input_kind") not in ("video", "folder"):
        return None
    p = meta.get("input", "")
    p = p if os.path.isabs(p) else os.path.join(CODE_DIR, p)
    if not os.path.exists(p):
        return None
    return open_source(p, fps=nominal_fps(meta), step=meta.get("step") or 1, width=meta.get("width_arg"))


def replot(folder: str, n_tiles: int) -> int:
    """Rebuild timing.csv, the plots, the contact sheet and meta.json of an existing run folder from its
    observations.csv. observations.csv is only read; overlay.mp4 is only read, except that an overlay an older
    run.py wrote at the nominal rate of a camera run is re-timed to the effective rate (frames unchanged)."""
    csv_path = os.path.join(folder, "observations.csv")
    if not os.path.isfile(csv_path):
        print(f"observations.csv가 없어 다시 만들 수 없습니다 — {folder}", file=sys.stderr)
        return 1
    files_before = sorted(os.listdir(folder))
    log = _open_log(folder)
    failed, skipped = [], []
    log.info("--replot; files before: %s", ", ".join(files_before))
    rows = _step(log, failed, "read observations.csv", lambda: _read_rows(csv_path))
    if not rows:
        log.error("observations.csv could not be read or has no rows")
        return _report_failures(failed or ["read observations.csv"], folder)

    def _json(name):
        p = os.path.join(folder, name)
        if not os.path.isfile(p):
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    old_meta, manifest = _json("meta.json"), _json("manifest.json")
    kind_ko = rows[0].get("source_kind", "")
    synthetic = kind_ko == "합성"
    name = (old_meta or {}).get("input_name") or os.path.basename(os.path.normpath(folder))
    phase_labels = (manifest or {}).get("phase_labels", {})
    header = ("[합성 입력] " if synthetic else "") + f"{name} · 관측 CSV에서 다시 그림"
    video = next((os.path.join(folder, v) for v in ("overlay.mp4", "overlay_tmp.mp4")
                  if os.path.isfile(os.path.join(folder, v))), None)
    vid_wh, vid_fps = None, None
    if video:
        vw, vh, vid_fps, vid_n = _video_info(video)
        vid_wh = (vw, vh)
        log.info("overlay video %s: %dx%d, %s fps, %d frames (container count); CSV rows %d",
                 os.path.basename(video), vw, vh, vid_fps, vid_n, len(rows))
    frame_wh = (old_meta or {}).get("frame_size_wh")
    if (not frame_wh or not frame_wh[0]) and vid_wh:
        frame_wh = [vid_wh[0] - render.PANEL_W, vid_wh[1]]       # overlay = frame + value panel (render.PANEL_W)

    # Frame rates. A folder whose meta.json has no overlay_fps, or that has neither meta.json nor run.log, was made
    # by run.py before the effective-rate change: its overlay was written at the source's stated (nominal) rate.
    old = old_meta or {}
    old_overlay = "overlay_fps" not in old if old_meta is not None else "run.log" not in files_before
    measured = (old.get("fps_effective") is not None or old.get("input_kind") == "camera"
                or str(old.get("frame_time_source", "")).startswith("sidecar")
                or (old_meta is None and kind_ko == "카메라"))
    fps_eff = old.get("fps_effective") or (effective_fps([r["t_s"] for r in rows]) if measured else None)
    fps_nom = nominal_fps(old) if old_meta is not None else (vid_fps if old_overlay else None)
    overlay_fps = old.get("overlay_fps") or vid_fps
    log.info("frame rate: nominal %s, effective %s, overlay %s", fps_nom, fps_eff, overlay_fps)

    _step(log, failed, "timing.csv", lambda: _write_timing(folder, rows))
    _plots(log, failed, folder, rows, header, phase_labels)

    retimed = None
    if video and video.endswith("overlay.mp4") and fps_eff and old_overlay and vid_fps:
        def _retime():
            nonlocal overlay_fps, retimed
            _retime_overlay(video, vid_fps, fps_eff)
            overlay_fps = _video_info(video)[2]
            retimed = {"from_fps": vid_fps, "to_fps": fps_eff, "read_back_fps": overlay_fps}
            log.info("overlay.mp4 re-timed %.3f -> %.3f fps (read back %.3f), frames unchanged",
                     vid_fps, fps_eff, overlay_fps)
        _step(log, failed, "overlay re-time", _retime)

    src = None if video else _input_source(old_meta)
    sheet_from = os.path.basename(video) if video else ("input frames" if src is not None else None)
    if sheet_from is None:
        log.info("skipped: contact_sheet (no overlay video and no readable input to take frames from)")
        skipped.append("contact_sheet")
    else:
        def _sheet():
            if video:
                tiles = _tiles_from_video(video, rows, n_tiles, frame_wh[0] if frame_wh else None)
                note = " · 오버레이 영상에서 뽑음"
            else:
                tiles = _tiles_from_source(src, rows, n_tiles)
                note = " · 입력 프레임에서 뽑음(점 · 선 없음)"
            if not tiles:
                raise IOError(f"no frame could be read from {sheet_from}")
            render.contact_sheet(tiles, f"{header} — 프레임 {len(tiles)}장 (고르게 뽑음){note}",
                                 os.path.join(folder, "contact_sheet.png"), phase_labels)
        _step(log, failed, "contact_sheet", _sheet)

    def _meta():
        meta = dict(old_meta or {})
        meta.pop("fps_processed", None)                            # older name of fps_nominal
        meta.update({
            "input": meta.get("input", "not recorded (rebuilt by --replot)"),
            "input_name": name, "input_kind": meta.get("input_kind") or KIND_FROM_KO.get(kind_ko, "unknown"),
            "synthetic": synthetic,
            "fps_nominal": fps_nom, "fps_effective": fps_eff, "overlay_fps": overlay_fps,
            "frame_size_wh": frame_wh, "frames_processed": len(rows),
            "environment": meta.get("environment") or environment(),
            "timing_condition": meta.get("timing_condition"),     # None = not recorded
            "replot": {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "files_before": files_before,
                       "rebuilt_from": "observations.csv", "contact_sheet_from": sheet_from,
                       "overlay_retimed": retimed,
                       "failed_steps": list(failed), "skipped_steps": list(skipped)},
        })
        if old_meta is None:
            meta["replot"]["note"] = (
                "the run left no meta.json: environment = the PC and packages --replot ran with; timing condition, "
                "models, settings, output_ms and the stop reason were not recorded"
                + ("; fps_nominal = the rate the overlay was written at (run.py before run.log wrote it at the "
                   "source's stated rate)" if old_overlay else "; fps_nominal not recorded")
                + ("; fps_effective = from t_s in observations.csv" if fps_eff else ""))
        with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    _step(log, failed, "meta.json", _meta)
    log.info("done --replot (failed: %s; skipped: %s)", ", ".join(failed) or "none", ", ".join(skipped) or "none")
    done = [n for n in ("timing.csv", "plot_observations", "plot_quality_timing", "contact_sheet", "meta.json")
            if n not in failed and n not in skipped]
    print(f"--replot {folder}: {len(rows)} rows; rebuilt {', '.join(done)}"
          + (f"; overlay.mp4 re-timed {retimed['from_fps']:g} -> {retimed['to_fps']:.2f} fps" if retimed else "")
          + (f"; skipped {', '.join(skipped)}" if skipped else "") + (f"; failed {', '.join(failed)}" if failed else ""))
    return _report_failures(failed, folder)


# ------------------------------------------------------------------------------------------- command line
def main():
    # Output redirected to a file or pipe uses the locale code page on Windows (cp949 here), which lacks some
    # characters of the Korean messages (e.g. the dash): replace them instead of failing.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", help="video file or folder of images")
    ap.add_argument("--out", help="output folder of this run (default: runs/live_<YYYY-MM-DD>_<HHMM> for the camera, "
                                  "runs/<input name>_<YYYY-MM-DD>_<HHMM> for a file or folder, local time; seconds are "
                                  "added only if that folder exists)")
    ap.add_argument("--replot", metavar="RUN_FOLDER",
                    help="rebuild timing.csv, plots, contact sheet and meta.json of a run from its observations.csv")
    ap.add_argument("--models", default=os.path.join(CODE_DIR, "models"))
    ap.add_argument("--fps", type=float, default=None,
                    help="frame rate of an image folder without manifest.json; with --camera: overrides the driver's")
    ap.add_argument("--step", type=int, default=1, help="video: use every N-th frame (1 = all)")
    ap.add_argument("--width", type=int, default=None, help="resize to this width, aspect ratio kept")
    ap.add_argument("--tiles", type=int, default=12, help="contact sheet: number of evenly spaced frames")
    ap.add_argument("--source-note", default="", help="origin / licence line stored in meta.json")
    ap.add_argument("--affinity", default=None, help="Windows: logical-CPU mask, e.g. 0xFF = CPUs 0-7")
    ap.add_argument("--high-priority", action="store_true", help="Windows: run at high priority")
    ap.add_argument("--face-detector", default="short_range", choices=sorted(FACE_DETECTOR_MODELS),
                    help="Face Detector variant for face_count / face_det_score (default short_range)")
    cam = ap.add_argument_group("webcam (instead of INPUT)")
    cam.add_argument("--camera", type=int, default=None, help="camera index; 0 = default camera (OpenCV)")
    cam.add_argument("--seconds", type=float, default=None,
                     help="how long to run on the camera; required unless --show (then the run goes on until q "
                          "or Ctrl+C)")
    cam.add_argument("--cam-width", type=int, default=None, help="requested capture width (default: driver's)")
    cam.add_argument("--cam-height", type=int, default=None, help="requested capture height (default: driver's)")
    cam.add_argument("--backend", default="any", choices=["any", "msmf", "dshow"], help="OpenCV capture backend")
    ap.add_argument("--show", action="store_true",
                    help="live window with the same frames as overlay.mp4 (q, closing the window or Ctrl+C stops early)")
    ap.add_argument("--overwrite", action="store_true", help="allow writing into a folder that already holds a run")
    args = ap.parse_args()
    if args.replot:
        if args.input or args.camera is not None or args.out:
            ap.error("--replot takes only the run folder (no INPUT, --camera or --out)")
        sys.exit(_guarded(lambda: replot(args.replot, args.tiles), args.replot))
    if (args.input is None) == (args.camera is None):
        ap.error("give either INPUT or --camera")
    if args.camera is not None and not args.seconds and not args.show:
        # with --show the run goes on until q / Ctrl+C (or --seconds when given)
        ap.error("카메라 실행에는 멈추는 방법이 필요합니다. 두 가지 중 하나를 붙이세요: "
                 "① --seconds 60 처럼 시간을 정한다, "
                 "② --show(창에서 q)로 직접 멈춘다.")
    if not args.out:
        args.out = default_out(args.input, args.camera)
        if args.out is None:
            ap.error("같은 이름의 결과 폴더가 이미 있습니다(같은 초에 두 번 시작) — 잠시 뒤 다시 시작하거나 --out을 주세요")
    if not args.overwrite and any(os.path.exists(os.path.join(args.out, f)) for f in ("meta.json", "observations.csv")):
        ap.error(f"{args.out} already holds a run - choose another --out, or add --overwrite to replace it")
    sys.exit(_guarded(lambda: run(args), args.out))


if __name__ == "__main__":
    main()
