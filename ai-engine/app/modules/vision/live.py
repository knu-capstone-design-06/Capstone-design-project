"""Live: the replay chain on a webcam, one printed line per window, rows kept in a ring buffer.

From ai-engine/:
  python -m app.modules.vision.live --camera 0 --no-window [--seconds 60] [--params BUNDLE.json] [--out DIR]
                                    [--threads 1] [--cam-width 640 --cam-height 480] [--backend any|msmf|dshow]
                                    [--blendshapes] [--no-heads]

- --no-window: nothing appears on the screen (tests, headless use). Without it a window shows the frame with the main
  user's head box (green) and the companion's (blue) and the frame time; q or closing it stops.
- --blendshapes turns the Face Landmarker's blendshapes on (default off, decision list 2026-10-10 §16); while off,
  mouth_motion stays blank.
- Stop: --seconds, q in the window, or Ctrl+C. Without a window the run needs --seconds or Ctrl+C.
- There is no touch log in live use (the order screen is not wired to this runner): tap_count / miss_tap_count are
  missing, so every tag that needs 'no touch' stays 'unknown' (its reason says column:tap_count) and the rule table's
  touch rows do not open. That is the rules' missing-cue path, not an error.
- The ring buffer keeps the rows a window needs (chain.history_s: window_s + 2 x gap_s of the value bundle).
- When the run stops, the rows after the last full window get one shorter window (record 'partial').
- --out DIR: windows.jsonl and meta.json only. The camera picture is never saved.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import deque

from .chain import SOURCE_KIND, FrameChain, WindowJudge, history_s
from .params import load_bundle
from .replay import MODELS_DIR, add_frame_counts, environment, jsonable, load_perception, timing_summary

WINDOW = "vision chain live (q = stop)"   # ASCII: OpenCV window titles may not show Korean on Windows


def window_line(rec: dict, ms_frame: float | None) -> str:
    """One console line per window (Korean labels, the values as they are)."""
    sit, d, v = rec["situation"], rec["decision"], rec["vision"]
    name = sit["name"]
    if name == "unknown" and sit["unknown_reason"]:
        codes = []
        for r in sit["unknown_reason"]:
            codes += r.get("missing", [r["code"]]) if r["code"] == "missing_cue" else [r["code"]]
        uniq = list(dict.fromkeys(codes))
        name += f"(모름: {', '.join(uniq[:3])}{' 외' if len(uniq) > 3 else ''})"
    heads = "-" if v["head_count_max"] is None else int(v["head_count_max"])
    behind = "-" if v["people_behind_max"] is None else int(v["people_behind_max"])
    mouth = "-" if v["mouth_motion_max"] is None else f"{v['mouth_motion_max']:.2f}"
    gaze = {True: "예", False: "아니오", None: "모름"}[v["facing_screen"]]
    decision = d["transition"] + (f" {d['support']}({d['intervention']})" if d["support"] else "")
    ms = "-" if ms_frame is None else f"{ms_frame:.0f}"
    return (f"[{rec['t']:7.1f}초] 상황 {name} | 머리 {heads} · 뒤 {behind} · 동행 프레임 {v['companion_frames']} · "
            f"입 {mouth} · 화면 봄 {gaze} | 판단 {decision} | 프레임 처리 {ms} ms")


def _draw(img, row: dict, text: str):
    import cv2
    out = img.copy()
    H, W = out.shape[:2]
    boxes = [("primary_box", (0, 200, 0))]
    if row.get("companion_box") is not None:
        boxes.append(("companion_box", (200, 120, 0)))
    for key, col in boxes:
        b = row.get(key)
        if b is not None:
            cv2.rectangle(out, (int(b[0] * W), int(b[1] * H)), (int(b[2] * W), int(b[3] * H)), col, 2)
    cv2.putText(out, text[:90], (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return out


def run_live(source, bundle, *, models, detector=None, direction=None, show_window: bool = False,
             out_dir: str | None = None, blendshapes: bool = False, print_fn=print) -> dict:
    """Run the chain on a live frame source (sources.LiveCameraSource or any iterable of sources.Frame)."""
    chain = FrameChain(models, bundle.chain, detector, direction, None, blendshapes=blendshapes,
                       source_kind=SOURCE_KIND.get(getattr(source, "kind", ""), ""))
    judge = WindowJudge(bundle, None, session_id="live")
    keep_s = history_s(bundle) + bundle.chain.segment_s
    buf, all_ms, records = deque(), [], []
    frame_counts = {"with_face": 0, "with_heads": 0, "with_direction": 0}
    out = open(os.path.join(out_dir, "windows.jsonl"), "w", encoding="utf-8") if out_dir else None
    next_t, stop_reason, last_t, partial_s = None, "input ended", None, None
    if show_window:
        import cv2
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    def emit(t_end, ms_frame, seg_len=None):
        rec = judge.evaluate(list(buf), t_end, segment_s=seg_len)
        records.append({"ms_window": rec["ms_window"]})
        print_fn(window_line(rec, ms_frame))
        if out:
            out.write(json.dumps(jsonable(rec), ensure_ascii=False) + "\n")
            out.flush()

    frames = iter(source)
    try:
        try:
            for frame in frames:
                row = chain.process(frame)
                buf.append(row)
                add_frame_counts(frame_counts, row)
                all_ms.append({"ms_total": row.get("ms_total"), "ms_heads": row.get("ms_heads"),
                               "ms_head_dir": row.get("ms_head_dir"), "ms_chain": row.get("ms_chain"),
                               "cpu_ms_chain": row.get("cpu_ms_chain")})
                t = last_t = float(row["t_s"])
                while buf and float(buf[0]["t_s"]) < t - keep_s:
                    buf.popleft()
                if next_t is None:
                    next_t = t + bundle.chain.segment_s
                while t >= next_t:
                    emit(next_t, row.get("ms_chain"))
                    next_t += bundle.chain.segment_s
                if show_window:
                    import cv2
                    cv2.imshow(WINDOW, _draw(frame.image, row, f"t={t:.1f}s"))
                    if (cv2.waitKey(1) & 0xFF) == ord("q"):
                        stop_reason = "q in the window"
                        break
                    if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                        stop_reason = "window closed"
                        break
        except KeyboardInterrupt:
            stop_reason = "Ctrl+C"
        if next_t is not None and last_t > next_t - bundle.chain.segment_s:   # rows after the last full window
            partial_s = last_t - (next_t - bundle.chain.segment_s)
            emit(last_t, None, partial_s)
    finally:
        close = getattr(frames, "close", None)
        if close:
            close()
        if out:
            out.close()
        if show_window:
            import cv2
            cv2.destroyAllWindows()
            cv2.waitKey(1)
    if stop_reason == "input ended":
        stop_reason = getattr(source, "end_reason", None) or stop_reason
    meta = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "frames": len(all_ms), "windows": len(records),
            "stop_reason": stop_reason, "bundle": bundle.to_dict(), "environment": environment(),
            "timing_ms": timing_summary(all_ms, records), "window_shown": bool(show_window),
            "counts": {"frames": frame_counts},
            "last_window_partial_s": None if partial_s is None else round(partial_s, 4)}
    if out_dir:
        with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(jsonable(meta), f, ensure_ascii=False, indent=2)
    return meta


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", type=int, required=True, help="camera index; 0 = default camera (OpenCV)")
    ap.add_argument("--no-window", action="store_true", help="show nothing on the screen")
    ap.add_argument("--seconds", type=float, default=None, help="stop after this many seconds")
    ap.add_argument("--params", default=None, help="value bundle JSON (params.py)")
    ap.add_argument("--out", default=None, help="folder for windows.jsonl and meta.json (no pictures)")
    ap.add_argument("--threads", type=int, default=1, help="ONNX Runtime intra-op threads (default 1)")
    ap.add_argument("--models", default=MODELS_DIR)
    ap.add_argument("--cam-width", type=int, default=None)
    ap.add_argument("--cam-height", type=int, default=None)
    ap.add_argument("--backend", default="any", choices=["any", "msmf", "dshow"])
    ap.add_argument("--fps", type=float, default=None, help="overrides the frame rate the driver reports")
    ap.add_argument("--blendshapes", action="store_true",
                    help="blendshapes on (default off, decision list 2026-10-10 §16); off: mouth_motion stays blank")
    ap.add_argument("--no-heads", action="store_true")
    a = ap.parse_args(argv)
    if a.no_window and a.seconds is None:
        print("창 없이 돌리면 Ctrl+C로만 멈춥니다(--seconds로 시간을 정할 수 있습니다).", file=sys.stderr)
    return a


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    a = parse_args(argv)
    bundle = load_bundle(a.params)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    import cv2
    cv2.setNumThreads(1)
    from app.inference.vision import MediaPipeModels
    from .sources import LiveCameraSource
    detector, direction, _ = load_perception(a.models, bundle.chain, a.threads, not a.no_heads, print)
    models = MediaPipeModels(a.models, blendshapes=a.blendshapes)
    try:
        source = LiveCameraSource(a.camera, a.cam_width, a.cam_height, a.backend, a.fps, a.seconds)
        print(f"카메라 {a.camera} 시작 — 창마다 한 줄씩 나옵니다", flush=True)
        meta = run_live(source, bundle, models=models, detector=detector, direction=direction,
                        show_window=not a.no_window, out_dir=a.out, blendshapes=a.blendshapes)
    finally:
        models.close()
    print(f"끝: 프레임 {meta['frames']}장 · 창 {meta['windows']}개 · 멈춘 이유 {meta['stop_reason']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
