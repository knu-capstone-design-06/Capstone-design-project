"""Smoke run of the two links without a camera: the live runner on a fake camera, a stand-in order screen that posts
touch windows to the touch entry, and a stub backend that prints every window the tag sender delivers.

From ai-engine/:
  python -m app.modules.vision.tools.integration_smoke --seconds 30 [--params BUNDLE.json] [--out DIR]
                                                       [--models DIR] [--threads 1] [--width 640 --height 480]
                                                       [--no-heads]

- One process, as on the kiosk PC: live.run_live with the touch entry (touch_entry.py, 127.0.0.1, a port the OS
  chooses) and the tag sender (tag_sender.py, timeout = segment_s) pointed at the stub backend (127.0.0.1, a port the
  OS chooses). The real models run (MediaPipe, and H1 / P1 unless --no-heads); no aid or phone detector.
- Fake camera: black frames of --width x --height (default 640 x 480, the synthetic input of the vision README's
  '처리 시간' measurement), stamped like sources.LiveCameraSource (monotonic time, wall time), handed on as fast as the
  chain takes them, for --seconds. Nobody is in the picture, so the situation stays none or unknown: the run checks
  the links (what is sent, when, to which session), not the camera.
- Stand-in order screen: once the camera delivers frames, every FEATURE_WINDOW_MS (2,000 ms, frontend
  interactionFeatures.ts) it POSTs the window (end - 2 s, end] that has just ended to /touch-windows, with zero touch
  counts (nobody touches a screen here), session_id SESSION and screen_id 'menu' (the first screen of touch.py's
  SCREEN_FLOW). The windows the runner evaluated before the first touch window named the session are not sent.
- Stub backend: answers 202 to POST /api/v1/sessions/{session_id}/vision-windows and prints one line per window: its
  segment (window_start ~ window_end), the session, the situation, whether its touch-dependent conditions were judged
  (the rules' touch cue of its situation window is settled: a press on a row, or a count on every row; the runner's record['evaluated'].touch_complete) and when the
  runner evaluated it (after the touch window came, on its own cadence, at the kept-history bound, ...), the gaze,
  the face seen, the scene tags true or unknown, and how long after the segment's end it arrived (the stub's wall
  clock minus window_end; one machine, one clock). Since a segment waits for the touch window that covers it, the
  first of the two segments of a 2 s touch window arrives about 1 s after its own end.
- --out DIR: DIR/smoke_summary.json (the settings, the sender's counts, the windows by evaluation and by judged touch,
  the arrival delays p50 / p95, every received body) and DIR/live/ (the runner's windows.jsonl and meta.json). No
  picture is saved anywhere.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.modules.vision.touch import SCREEN_FLOW

FEATURE_WINDOW_MS = 2000       # frontend/src/features/order/interactionFeatures.ts FEATURE_WINDOW_MS
SESSION = "smoke"              # the stand-in order screen's session id (a label of this tool)
SCREEN = SCREEN_FLOW[0]        # the order screen's first screen ('menu')
FAKE_SIZE = (640, 480)         # vision README '처리 시간': the synthetic input frames 640 x 480


def percentiles(values: list) -> dict | None:
    """p50 / p95 / max / n with linear interpolation (replay.percentiles, kept here so this part loads no model code)."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None

    def q(p):
        k = (len(vals) - 1) * p
        lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
        return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)
    return {"p50": round(q(0.50), 3), "p95": round(q(0.95), 3), "max": round(vals[-1], 3), "n": len(vals)}


def cpu_name() -> str:
    """The processor's marketing name (Windows registry ProcessorNameString), else platform.processor()."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    except (ImportError, OSError):
        return platform.processor()


def epoch_of(text: str) -> float:
    """ISO 8601 with a zone ('Z' included) -> wall-clock seconds."""
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


class FakeCamera:
    """Black frames stamped like sources.LiveCameraSource (t_s from a monotonic clock, epoch_s the wall time read
    right after it), handed on as fast as they are taken; stops after `seconds` or after `frames` frames."""

    kind = "camera"
    measured_times = True
    name = "fake camera"
    time_source = "monotonic clock at the fake frame"

    def __init__(self, seconds: float | None, width: int, height: int, frames: int | None = None):
        import numpy as np
        self.seconds, self.limit = seconds, frames
        self.image = np.zeros((height, width, 3), np.uint8)
        self.size_wh = (width, height)

    def __iter__(self):
        from app.modules.vision.sources import Frame
        t0, i = None, 0
        while self.limit is None or i < self.limit:
            now, wall = time.monotonic(), time.time()
            if t0 is None:
                t0 = now
            if self.seconds is not None and now - t0 > self.seconds:
                self.end_reason = "--seconds reached"
                return
            yield Frame(i, now - t0, self.image, str(i), 0.0, wall)
            i += 1
        self.end_reason = "frame limit reached"


HOW = {"touch": "터치 창이 온 뒤", "cadence": "실행기 간격", "kept_history": "기억 구간 끝에서",
       "later_ready": "다음 창이 먼저 준비됨", "input_end": "입력 끝에서"}   # live.run_live record['evaluated']['how']


def window_line(body: dict, delay_ms: float, evaluated: dict | None) -> str:
    """One console line per window the stub backend received: the segment, the session, the situation, whether its
    touch-dependent conditions were judged (record['evaluated'].touch_complete: the rules' touch cue is settled) and when the
    runner evaluated it, the gaze, the face, the scene tags, the arrival after the segment's end."""
    sit, obs = body["situation"], body["observations"]
    true = [t["name"] for t in obs["scene_tags"] if t["status"] is True]
    unknown = sum(t["status"] == "unknown" for t in obs["scene_tags"])
    gaze = {True: "예", False: "아니오", None: "모름"}[obs["gaze"]]
    if evaluated is None:
        touch = "터치 단서 ?"
    else:
        touch = (f"터치 단서 {'판정함' if evaluated['touch_complete'] else '못 판정함(터치 모자람)'}"
                 f"({HOW.get(evaluated['how'], evaluated['how'])})")
    return (f"[backend 받음] 구간 {body['window_start'][11:23]}~{body['window_end'][11:23]} | "
            f"세션 {body['session_id']} | 상황 {sit['name']} | {touch} | 화면 봄 {gaze} · "
            f"얼굴 {'예' if obs['face_seen'] else '아니오'} | 장면 태그 참 {', '.join(true) or '없음'} · 모름 {unknown}개 | "
            f"구간 끝 뒤 {delay_ms:.0f} ms")


class StubBackend:
    """127.0.0.1, a port the OS chooses: records every POST (path, body, arrival delay, the runner's 'evaluated'
    block of that window) and prints its line. evaluated = {window_end: record['evaluated']}, filled by the runner."""

    def __init__(self, print_fn=print, evaluated=None):
        self.received = []
        self.evaluated = {} if evaluated is None else evaluated
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def do_POST(self):
                arrived = time.time()
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
                delay_ms = (arrived - epoch_of(body["window_end"])) * 1000.0
                evaluated = stub.evaluated.get(body["window_end"])
                stub.received.append({"path": self.path, "delay_ms": round(delay_ms, 3), "evaluated": evaluated,
                                      "body": body})
                print_fn(window_line(body, delay_ms, evaluated))
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, name="stub-backend", daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _call(opener, url: str, body: dict | None = None) -> tuple:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="GET" if body is None else "POST")
    try:
        with opener.open(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def order_screen(entry_url: str, stop: threading.Event, posted: list, print_fn=print):
    """The stand-in order screen (module docstring): waits for the camera's first frame, then posts each 2 s window
    when it ends, until the camera stops (503) or `stop` is set."""
    from app.modules.vision.touch_entry import TOUCH_PATH, iso
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 127.0.0.1 directly
    step = FEATURE_WINDOW_MS / 1000.0
    started = None
    while started is None and not stop.is_set():
        try:
            if _call(opener, entry_url + "/status")[1]["frames"] > 0:
                started = time.time()
        except OSError:
            pass
        if started is None:
            stop.wait(step)
    end = None if started is None else started + step
    while end is not None and not stop.wait(max(0.0, end - time.time())):
        body = {"window_start": iso(end - step), "window_end": iso(end), "screen_id": SCREEN, "session_id": SESSION,
                "touch": {"tap_count": 0, "miss_tap_count": 0, "repeat_tap_count": 0, "back_count": 0,
                          "dwell_ms": 0}}
        code, out = _call(opener, entry_url + TOUCH_PATH, body)
        posted.append({"window_end": body["window_end"], "code": code, "status": out.get("status")})
        if code != 202:
            print_fn(f"[주문 화면 대역] 터치 창 {body['window_end']} 거절 {code}: {out.get('reason')}")
            if code == 503:
                return
        end += step


def run_smoke(source, bundle, *, models, detector=None, direction=None, out_dir: str | None = None,
              print_fn=print) -> dict:
    """The links on one source (FakeCamera): entry, sender, stub backend, stand-in order screen; the summary."""
    from app.modules.vision.live import run_live
    from app.modules.vision.tag_sender import TagSender
    from app.modules.vision.touch_entry import HOST, TouchEntry, start_server
    evaluated = {}                                 # window_end as sent -> the runner's record['evaluated']

    def remember(rec, body):                       # called by the runner before it offers the body
        if body is not None:
            evaluated[body["window_end"]] = rec["evaluated"]
    stub = StubBackend(print_fn, evaluated)
    entry = TouchEntry(bundle, log=print_fn)
    server = start_server(entry, 0)
    sender = TagSender(stub.url, bundle.chain.segment_s, log=print_fn)
    entry_url = f"http://{HOST}:{server.server_address[1]}"
    print_fn(f"터치 입구 {entry_url} · 시험 backend {stub.url} · 제한 시간 {sender.timeout_s:g}초(창 간격)")
    stop, posted = threading.Event(), []
    screen = threading.Thread(target=order_screen, args=(entry_url, stop, posted, print_fn), name="order-screen",
                              daemon=True)
    screen.start()
    live_out = None if out_dir is None else os.path.join(out_dir, "live")
    if live_out:
        os.makedirs(live_out, exist_ok=True)
    try:
        meta = run_live(source, bundle, models=models, detector=detector, direction=direction, out_dir=live_out,
                        print_fn=print_fn, entry=entry, sender=sender, on_window=remember)
    finally:
        stop.set()
        screen.join()
        server.shutdown()
        server.server_close()
        stub.close()
    names, hows, judged = {}, {}, {"judged": 0, "not_judged": 0}
    for item in stub.received:
        name = item["body"]["situation"]["name"]
        names[name] = names.get(name, 0) + 1
        ev = item["evaluated"] or {}
        hows[ev.get("how")] = hows.get(ev.get("how"), 0) + 1
        judged["judged" if ev.get("touch_complete") else "not_judged"] += 1
    return {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "cpu": cpu_name(), "logical_cpus": os.cpu_count(),
            "platform": platform.platform(),
            "settings": {"size_wh": list(getattr(source, "size_wh", ())), "window_ms": FEATURE_WINDOW_MS,
                         "session_id": SESSION, "screen_id": SCREEN, "timeout_s": sender.timeout_s,
                         "bundle_id": bundle.bundle_id or None},
            "touch_windows": {"posted": len(posted), "accepted": sum(p["code"] == 202 for p in posted)},
            "sender": meta["tag_sender"],
            "received": {"count": len(stub.received), "by_situation": names, "by_evaluation": hows,
                         "touch_conditions": judged,
                         "paths": sorted({item["path"] for item in stub.received}),
                         "delay_after_window_end_ms": percentiles([item["delay_ms"] for item in stub.received])},
            "live": {k: meta[k] for k in ("frames", "windows", "stop_reason", "timing_ms", "source")},
            "per_window": stub.received}


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, required=True, help="length of the fake camera run")
    ap.add_argument("--params", default=None, help="value bundle JSON (params.py); without it the situation is "
                                                   "unknown (no_value_bundle)")
    ap.add_argument("--out", default=None, help="folder for smoke_summary.json and the runner's live/ files")
    ap.add_argument("--models", default=None, help="model folder (default: the live runner's)")
    ap.add_argument("--threads", type=int, default=1, help="ONNX Runtime intra-op threads (default 1, as live.py)")
    ap.add_argument("--width", type=int, default=FAKE_SIZE[0])
    ap.add_argument("--height", type=int, default=FAKE_SIZE[1])
    ap.add_argument("--no-heads", action="store_true")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    a = parse_args(argv)
    import cv2
    cv2.setNumThreads(1)                           # as live.main
    from app.inference.vision import MediaPipeModels
    from app.modules.vision.params import load_bundle
    from app.modules.vision.replay import MODELS_DIR, load_perception
    bundle = load_bundle(a.params)
    models_dir = a.models or MODELS_DIR
    detector, direction, _ = load_perception(models_dir, bundle.chain, a.threads, not a.no_heads, print)
    models = MediaPipeModels(models_dir, blendshapes=False)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    try:
        summary = run_smoke(FakeCamera(a.seconds, a.width, a.height), bundle, models=models, detector=detector,
                            direction=direction, out_dir=a.out, print_fn=lambda line: print(line, flush=True))
    finally:
        models.close()
    if a.out:
        with open(os.path.join(a.out, "smoke_summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    s, r = summary["sender"], summary["received"]
    print(f"끝: 터치 창 {summary['touch_windows']['accepted']}/{summary['touch_windows']['posted']}개 받음 · "
          f"backend가 받은 창 {r['count']}개 {r['by_situation']} · 터치 단서 {r['touch_conditions']} · "
          f"보냄 {s['sent']} · 실패 {s['failed']} · "
          f"바뀜 {s['replaced']} · 창 끝 뒤 도착 {r['delay_after_window_end_ms']}", flush=True)
    return 0 if r["count"] else 1


if __name__ == "__main__":
    sys.exit(main())
