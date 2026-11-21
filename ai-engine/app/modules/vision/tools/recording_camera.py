"""Recording camera: a recorded clip played into the live runner in real time, as a camera would deliver it.

From ai-engine/:
  python -m app.modules.vision.tools.recording_camera --video CLIP [--label NAME] [--step 1] [--width W]
                                                      [--start-file PATH] [--tail-s 0] [--seconds S]
                                                      [--params BUNDLE.json] [--out DIR] [--models DIR] [--threads 1]
                                                      [--no-heads] [--serve PORT [--allow-origin ORIGIN ...]
                                                                                  [--backend-url URL]]

- RecordingCamera plays the clip in real time on its own reader thread, as a camera driver captures whether or not
  anyone reads: the thread decodes each clip frame at its time in the clip (frame index / the clip's frame rate, from
  the moment the clip starts) and keeps only the newest one. The chain is handed the newest frame when it asks: when
  the chain is slower than the clip, the frames in between are never handed on (counted as skipped), and when it is
  faster it waits for the next one. The decoding thus does not slow the chain's loop, as a webcam's does not. Each
  frame carries t_s from a monotonic clock since the source started and epoch_s, the wall time read right after it,
  both read when the frame is handed out, as sources.LiveCameraSource stamps a webcam frame; the touch entry places
  the order screen's windows with it (touch_entry.py, 'Time axis'). src_ref is the clip's frame number, 'preroll' or
  'tail'.
- step: only every step-th frame of the clip can be handed out, the meaning of replay.py --step (3 on a 30 fps clip:
  at most 10 frames per second).
- start_file: until this file exists, black frames of the clip's size are handed out at the clip's rate divided by
  step (a camera looking at an empty kiosk), so the order screen can start its session before the clip begins; the
  clip starts when the file appears. Without it the clip starts at once.
- tail_s: black frames for this long after the clip's last frame (the customer has left), so the windows of the clip's
  end are still evaluated and sent.
- The command runs live.run_live on this source with the live runner's options (touch entry, tag sender, value
  bundle, models). No window is shown and no picture is saved; --out writes windows.jsonl and meta.json as live.py
  does, with --label (default: the clip's file name) as the source name.
"""
from __future__ import annotations

import argparse
import os
import sys
import time


class RecordingCamera:
    """A clip played in real time (module docstring). Reads with OpenCV; frames are BGR uint8."""

    kind = "camera"           # the chain treats it as a live source (chain.SOURCE_KIND)
    measured_times = True     # t_s is the monotonic time at which each frame was handed out
    time_source = "monotonic clock when the recorded frame is handed out (real-time playback)"

    def __init__(self, path: str, step: int = 1, width: int | None = None, start_file: str | None = None,
                 tail_s: float = 0.0, seconds: float | None = None, label: str | None = None):
        import cv2
        if not isinstance(path, str) or not os.path.isfile(path):
            raise FileNotFoundError(f"not a video file: {path!r}")
        if step < 1:
            raise ValueError("step must be >= 1")
        if tail_s < 0:
            raise ValueError("tail_s must be >= 0")
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise IOError(f"OpenCV cannot open {path}")
        self.reported_fps = float(cap.get(cv2.CAP_PROP_FPS))
        ok, first = cap.read()
        cap.release()
        if self.reported_fps <= 0:
            raise ValueError("the video reports no frame rate")
        if not ok:
            raise IOError(f"no frame in {path}")
        from app.modules.vision.sources import resize_keep_aspect
        h, w = resize_keep_aspect(first, width).shape[:2]
        self.path, self.step, self.width = path, step, width
        self.start_file, self.tail_s, self.seconds = start_file, float(tail_s), seconds
        self.size_wh = (w, h)
        self.fps = self.reported_fps / step          # the most frames per second this source hands out
        self.name = label or os.path.basename(path)
        self.synthetic, self.manifest = False, None
        self.clip_started_epoch = self.clip_ended_epoch = None   # wall times of the clip's first and last frame
        self.clip_start_t_s = None   # the moment the clip started playing, on the frames' t_s axis
        self.counts = {"preroll": 0, "clip": 0, "skipped": 0, "tail": 0}

    def expected_frames(self) -> int:
        return int(self.seconds * self.fps) if self.seconds else 0

    def _due(self, t0: float) -> bool:
        """False once --seconds has passed (end_reason set)."""
        if self.seconds is not None and time.monotonic() - t0 > self.seconds:
            self.end_reason = "--seconds reached"
            return False
        return True

    def _reader(self, latest: dict, cond, stop, t0: float):
        """The camera's capture thread: decodes the clip in real time from the moment it starts and keeps the newest
        step-th frame in `latest` (k = clip frame number, img); `done` once the clip has no more frames."""
        import cv2
        from app.modules.vision.sources import resize_keep_aspect
        cap = cv2.VideoCapture(self.path)
        clip_t0, k = time.monotonic(), 0
        self.clip_start_t_s = clip_t0 - t0
        try:
            while not stop.is_set():
                wait = clip_t0 + k / self.reported_fps - time.monotonic()
                if wait > 0 and stop.wait(wait):              # not due yet; a camera cannot deliver it earlier
                    break
                if k % self.step:
                    if not cap.grab():                         # a frame between the step-th ones: not kept
                        break
                else:
                    ok, img = cap.read()
                    if not ok:
                        break
                    img = resize_keep_aspect(img, self.width)
                    with cond:
                        latest["k"], latest["img"] = k, img
                        cond.notify_all()
                k += 1
        finally:
            cap.release()
            with cond:
                latest["done"] = True
                cond.notify_all()

    def __iter__(self):
        import threading
        import numpy as np
        from app.modules.vision.sources import Frame
        black = np.zeros((self.size_wh[1], self.size_wh[0], 3), np.uint8)
        period = 1.0 / self.fps
        t0, i = time.monotonic(), 0
        stop, cond = threading.Event(), threading.Condition()
        reader = None
        try:
            # 1. preroll: black frames until the start file exists
            slot = t0
            while self.start_file is not None and not os.path.exists(self.start_file):
                if not self._due(t0):
                    return
                now = time.monotonic()
                if now < slot:
                    time.sleep(slot - now)
                    continue
                now, wall = time.monotonic(), time.time()
                yield Frame(i, now - t0, black, "preroll", 0.0, wall)
                self.counts["preroll"] += 1
                i += 1
                slot = max(slot + period, now)
            # 2. the clip in real time: the reader thread keeps the newest frame; each request gets the newest one
            latest = {"k": None, "img": None, "done": False}
            reader = threading.Thread(target=self._reader, args=(latest, cond, stop, t0), name="recording-camera",
                                      daemon=True)
            reader.start()
            last_k = None
            while True:
                t_wait = time.perf_counter()
                with cond:
                    while latest["k"] == last_k and not latest["done"]:
                        if not self._due(t0):
                            return
                        cond.wait(period)
                    if latest["k"] == last_k:                  # the clip has ended and its last frame was handed on
                        break
                    k, img = latest["k"], latest["img"]
                self.counts["skipped"] += (k - (-self.step if last_k is None else last_k)) // self.step - 1
                last_k = k
                if not self._due(t0):
                    return
                now, wall = time.monotonic(), time.time()
                if self.clip_started_epoch is None:
                    self.clip_started_epoch = wall
                self.clip_ended_epoch = wall
                yield Frame(i, now - t0, img, str(k), (time.perf_counter() - t_wait) * 1000.0, wall)
                self.counts["clip"] += 1
                i += 1
            # 3. tail: black frames after the clip's last frame
            end, slot = time.monotonic() + self.tail_s, time.monotonic()
            while time.monotonic() < end:
                if not self._due(t0):
                    return
                now = time.monotonic()
                if now < slot:
                    time.sleep(min(slot, end) - now)
                    continue
                now, wall = time.monotonic(), time.time()
                yield Frame(i, now - t0, black, "tail", 0.0, wall)
                self.counts["tail"] += 1
                i += 1
                slot = max(slot + period, now)
            self.end_reason = "end of the recording" + (f" and {self.tail_s:g} s of black frames" if self.tail_s else "")
        finally:
            stop.set()
            if reader is not None:
                reader.join()


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", required=True, help="the recorded clip to play in real time")
    ap.add_argument("--label", default=None, help="source name in meta.json (default: the clip's file name)")
    ap.add_argument("--step", type=int, default=1, help="hand out only every step-th clip frame (replay.py --step)")
    ap.add_argument("--width", type=int, default=None, help="resize to this width, keeping the aspect ratio")
    ap.add_argument("--start-file", default=None, help="black frames until this file exists, then the clip")
    ap.add_argument("--tail-s", type=float, default=0.0, help="black frames for this long after the clip")
    ap.add_argument("--seconds", type=float, default=None, help="stop after this many seconds")
    ap.add_argument("--params", default=None, help="value bundle JSON (params.py)")
    ap.add_argument("--out", default=None, help="folder for windows.jsonl and meta.json (no pictures)")
    ap.add_argument("--models", default=None, help="model folder (default: the live runner's)")
    ap.add_argument("--threads", type=int, default=1, help="ONNX Runtime intra-op threads (default 1, as live.py)")
    ap.add_argument("--blendshapes", action="store_true")
    ap.add_argument("--no-heads", action="store_true")
    ap.add_argument("--serve", type=int, default=None, metavar="PORT", help="touch entry port (live.py --serve)")
    ap.add_argument("--allow-origin", action="append", default=[], metavar="ORIGIN",
                    help="order screen origin, exactly as in its address bar (live.py --allow-origin)")
    ap.add_argument("--backend-url", default=None, metavar="URL", help="backend base address (live.py --backend-url)")
    a = ap.parse_args(argv)
    if a.serve is not None and not 0 <= a.serve <= 65535:
        ap.error("--serve needs a port from 0 to 65535")
    if a.allow_origin and a.serve is None:
        ap.error("--allow-origin needs --serve")
    if a.backend_url is not None:
        if a.serve is None:
            ap.error("--backend-url needs --serve (a window's session comes from the touch windows)")
        from app.modules.vision.tag_sender import check_base_url
        try:
            check_base_url(a.backend_url)
        except ValueError as e:
            ap.error(f"--backend-url: {e}")
    return a


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    a = parse_args(argv)
    import cv2
    cv2.setNumThreads(1)                                      # as live.main
    from app.inference.vision import MediaPipeModels
    from app.modules.vision.live import RunTiming, entry_lines, keeps_timing, run_live
    from app.modules.vision.params import load_bundle
    from app.modules.vision.replay import MODELS_DIR, load_perception
    bundle = load_bundle(a.params)
    models_dir = a.models or MODELS_DIR
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    source = RecordingCamera(a.video, a.step, a.width, a.start_file, a.tail_s, a.seconds, a.label)
    detector, direction, info = load_perception(models_dir, bundle.chain, a.threads, not a.no_heads, print)
    models = MediaPipeModels(models_dir, blendshapes=a.blendshapes)
    entry = server = sender = None
    try:
        if a.serve is not None:
            from app.modules.vision.touch_entry import TouchEntry, start_server
            entry = TouchEntry(bundle, log=lambda line: print(line, flush=True))
            server = start_server(entry, a.serve, a.allow_origin)
            for line in entry_lines(server.server_address[1], a.allow_origin):
                print(line, flush=True)
        if a.backend_url is not None:
            from app.modules.vision.tag_sender import TagSender
            sender = TagSender(a.backend_url, bundle.chain.segment_s, log=lambda line: print(line, flush=True))
            print(f"상황 태그 보내기 {sender.stats()['target']} · 제한 시간 {sender.timeout_s:g}초(창 간격)", flush=True)
        print(f"녹화 재생 {source.name} · {source.size_wh[0]}x{source.size_wh[1]} · 최대 {source.fps:g}장/초"
              + (" · 시작 파일을 기다리는 동안 검은 프레임" if a.start_file else ""), flush=True)
        meta = run_live(source, bundle, models=models, detector=detector, direction=direction, out_dir=a.out,
                        blendshapes=a.blendshapes, model_info=info, entry=entry, sender=sender,
                        print_fn=lambda line: print(line, flush=True), timing=RunTiming(keeps_timing(a)))
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        models.close()
    print(f"끝: 프레임 {meta['frames']}장 · 창 {meta['windows']}개 · 멈춘 이유 {meta['stop_reason']} · "
          f"녹화 프레임 {source.counts['clip']} · 건너뜀 {source.counts['skipped']} · 앞 검은 프레임 "
          f"{source.counts['preroll']} · 뒤 검은 프레임 {source.counts['tail']}", flush=True)
    if meta["tag_sender"] is not None:
        s = meta["tag_sender"]
        print(f"상황 태그: 보냄 {s['sent']} · 실패 {s['failed']} · 새 창으로 바뀜 {s['replaced']} · "
              f"끝에 못 보냄 {s['unsent_at_close']}" + (f" · 마지막 오류 {s['last_error']}" if s["last_error"] else ""),
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
