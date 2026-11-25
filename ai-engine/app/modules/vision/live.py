"""Live: the replay chain on a webcam, one printed line per window, rows kept in a ring buffer.

From ai-engine/:
  python -m app.modules.vision.live --camera 0 --no-window [--seconds 60] [--params BUNDLE.json] [--out DIR]
                                    [--threads 1] [--cam-width 640 --cam-height 480] [--backend any|msmf|dshow]
                                    [--blendshapes] [--no-heads] [--serve PORT [--allow-origin ORIGIN ...]
                                                                  [--backend-url URL]]

- --no-window: nothing appears on the screen (tests, headless use). Without it a window shows the frame with the main
  user's head box (green) and the companion's (blue) and the frame time; q or closing it stops.
- --blendshapes turns the Face Landmarker's blendshapes on (default off, decision list 2026-10-10 §16); while off,
  mouth_motion stays blank.
- Stop: --seconds, q in the window, or Ctrl+C. Without a window the run needs --seconds or Ctrl+C.
- Without --serve there is no touch input in live use: tap_count / miss_tap_count are missing, so every tag that
  needs 'no touch' stays 'unknown' (its reason says column:tap_count) and the rule table's touch rows do not open.
  That is the rules' missing-cue path, not an error.
- --serve PORT: the local touch entry on 127.0.0.1:PORT (touch_entry.py; PORT 0 = a free port the OS chooses,
  printed at the start). The order screen POSTs each touch window to /touch-windows and gets an acknowledgement only
  (no vision value goes back). The reported counts are placed on the rows of every window this runner evaluates
  (touch_entry.place_touch) and anchor the face-size reference's first press; the session of a window is the one
  its touch windows name. The rule table of the console line reads no touch counts (its touch rows stay closed; the
  backend judges the support). --allow-origin names an order screen origin, exactly as in its address bar (for
  example http://127.0.0.1:5173, where frontend/package.json's dev script serves the order screen; http://localhost:5173
  is another origin), whose page may post the windows; give it once per origin, as often as needed. Each touch window
  adds one line.
- When a window is evaluated. Without --serve, or while no touch window has named a session for the window's end,
  every segment_s on the runner's own cadence, as before. Once a session is known, a segment waits until a touch
  window of that session whose end is at or after the segment's end has arrived (LiveTouch.touch_until), so its
  'no touch' cues read complete touch; the order screen's 2 s windows thus release two 1 s segments at once, at the
  first frame after the touch window came. A segment still waiting when its own start is about to leave the kept
  history (the ring buffer's keep_s, counted from the latest frame) is evaluated as it is (touch missing: the rules'
  missing-cue path). A waiting segment is also evaluated as it is when a later one is ready (only after a change of
  session: the older session's windows no longer come), and at the end of the input. Segments are evaluated in
  time order. While a segment waits, the buffer keeps the rows its window needs (keep_s before its end), so a late
  window reads the same rows as an immediate one; the buffer thus spans at most keep_s + (keep_s - segment_s).
  Each record says how it was released (record 'evaluated': how, at, session_id, touch_until, touch_complete;
  touch_complete = the rules' touch cue of the situation window is settled, events.window_any_tap is not None: a
  press on a row of it, or a count on every row).
- --backend-url URL (needs --serve): every evaluated window whose end lies in a session the touch windows named goes
  to URL/api/v1/sessions/{session_id}/vision-windows (tag_sender.py: session, the window on the wall clock, the
  situation in the decision layer's keys, the observations block, the version mark). One sender thread with a
  one-slot mailbox of releases: the windows one evaluation releases together (the segments one touch window
  released) are one item and are posted in order; the camera loop never waits, a newer release replaces an unsent
  one as a whole, a failed send is counted and dropped; the timeout is segment_s. The counts go into meta.json
  (tag_sender) and the last console line. The console's decision column is then labelled "로컬 규칙표": it is this runner's own table, while the backend's judgment
  is the one that reaches the screen.
- The ring buffer keeps the rows a window needs (chain.history_s: window_s + 2 x gap_s of the value bundle).
- When the run stops, the rows after the last full window get one shorter window (record 'partial').
- --out DIR: windows.jsonl and meta.json only. The camera picture is never saved.
- --aid-model AID.onnx (optional) with --aid-rule owner_box | head_centre | head_centre_carry and --aid-head-min
  SCORE: as in replay.py (the reading of the walking-aid detector and the aid_use cut of the two head_centre
  readings, which has no default; they override the value bundle and are recorded in meta.json with origin 'option').
- A run with neither --seconds nor --out (unbounded, e.g. the kiosk's all-day run) keeps no per-frame or per-window
  timing rows (RunTiming(keep=False)); at exit it prints the frame and window counts, the stop reason and the tag
  sender's counts, with no timing percentiles; with --serve it says so in one start line (unbounded_note). The local
  rule table's Jev questions are never logged in live use.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import deque

from .chain import SOURCE_KIND, FrameChain, WindowJudge, history_s
from .events import window_any_tap
from .judgment.jev_stub import ShadowJev
from .params import load_bundle, with_options
from .replay import (MODELS_DIR, TIMING_COLUMNS, add_aid_options, add_frame_counts, aid_values, check_aid_options,
                     environment, jsonable, load_aids, load_perception, load_phones, timing_summary)
from .tag_sender import TagSender, check_base_url, vision_window

WINDOW = "vision chain live (q = stop)"   # ASCII: OpenCV window titles may not show Korean on Windows


def window_line(rec: dict, ms_frame: float | None, local: bool = False) -> str:
    """One console line per window (Korean labels, the values as they are). local = the tags go to a backend
    (--backend-url): the decision column is this runner's local rule table, labelled so; the backend's judgment is
    the one that reaches the screen."""
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
            f"입 {mouth} · 화면 봄 {gaze} | {'로컬 규칙표' if local else '판단'} {decision} | 프레임 처리 {ms} ms")


class RunTiming:
    """The per-frame and per-window timing rows that only the end-of-run summary (meta timing_ms, meta.json) reads.
    keep=False (a run without --seconds and without --out: unbounded, and no file reads them): only the counts are
    kept and the summary is None, so a run can stay up all day without growing."""

    def __init__(self, keep: bool = True):
        self.keep, self.rows, self.windows, self.frames, self.n_windows = keep, [], [], 0, 0

    def frame(self, row: dict):
        self.frames += 1
        if self.keep:
            self.rows.append({k: row.get(k) for k in ("ms_total",) + TIMING_COLUMNS})   # timing_summary's keys

    def window(self, rec: dict):
        self.n_windows += 1
        if self.keep:
            self.windows.append({"ms_window": rec["ms_window"]})

    def summary(self) -> dict | None:
        return timing_summary(self.rows, self.windows) if self.keep else None


def entry_lines(port: int, origins) -> list:
    """The lines printed at start with --serve: the entry's address and allowed origins, the exact line the order
    screen's environment needs, and what this address is not (the backend's AI_ENGINE_URL is another process)."""
    from .touch_entry import HOST, ORIGIN_HINT_KO, TOUCH_PATH
    allowed = ", ".join(origins) or "없음(브라우저 페이지는 터치 창을 보내지 못함)"
    return [f"터치 입구 http://{HOST}:{port}{TOUCH_PATH} · 허용 출처 {allowed}",
            f"출처 주의: {ORIGIN_HINT_KO}",
            f"VITE_AI_ENGINE_URL=http://{HOST}:{port}",
            "↑ 주문 화면 환경 변수에 그대로 넣을 줄입니다. 이 주소는 실시간 실행기의 터치 입구이고, backend가 "
            "AI_ENGINE_URL로 부르는 ai-engine 앱(/v1/analyze)이 아닙니다."]


def keeps_timing(args) -> bool:
    """Whether a run keeps its timing rows: bounded (--seconds) or writing files (--out)."""
    return args.seconds is not None or args.out is not None


def unbounded_note(args) -> str | None:
    """The start line that says an unbounded run keeps no timing rows: printed only with --serve (the kiosk's all-day
    run), so a run with every new option unset prints what it printed before."""
    if keeps_timing(args) or args.serve is None:
        return None
    return ("시간 제한(--seconds)도 기록 폴더(--out)도 없는 실행: 처리 시간 표본을 남기지 않습니다. 끝날 때는 "
            "프레임 수 · 창 수 · 멈춘 이유(와 상황 태그 보내기의 수)만 찍습니다.")


class UnloggedJev(ShadowJev):
    """The shadow Jev of the local rule table without its question log: the live runner never reads the log (the
    window record carries each question), so it is not kept."""

    def ask(self, kind: str, request: dict) -> dict:
        entry = super().ask(kind, request)
        self.log.clear()
        return entry


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
             out_dir: str | None = None, blendshapes: bool = False, print_fn=print, aids=None,
             model_info: dict | None = None, phones=None, entry=None, sender=None, on_window=None,
             timing: RunTiming | None = None) -> dict:
    """Run the chain on a live frame source (sources.LiveCameraSource or any iterable of sources.Frame). entry = a
    touch_entry.TouchEntry (the runner's touch entry): it gets every processed row (frames need Frame.epoch_s), its
    reported touch windows are the chain's touch input and are placed on the rows of every window evaluated here
    (TouchEntry.window_rows), a segment of a known session waits for its touch (module docstring, 'When a window
    is evaluated'), and it is stopped when the loop ends. sender = a tag_sender.TagSender (needs the entry): every
    evaluated window whose end lies in a session the touch windows named is offered to it (tag_sender.vision_window);
    it is closed after the camera, and its counts go into meta['tag_sender']. on_window(record, body) is called after
    each evaluation, before the offer, with the body offered to the sender (None when nothing is offered). timing =
    a RunTiming (default: kept, as before); live.main passes RunTiming(keeps_timing(args))."""
    if sender is not None and entry is None:
        raise ValueError("the tag sender needs the touch entry: a window's session comes from its touch windows")
    chain = FrameChain(models, bundle.chain, detector, direction, None if entry is None else entry.touch,
                       blendshapes=blendshapes, source_kind=SOURCE_KIND.get(getattr(source, "kind", ""), ""),
                       aids=aids, phones=phones)
    judge = WindowJudge(bundle, None, session_id="live", jev=UnloggedJev())
    seg_s = bundle.chain.segment_s
    keep_s = history_s(bundle) + seg_s
    timing = RunTiming() if timing is None else timing
    buf = deque()
    pending = deque()                     # due segments not evaluated yet: (t_end, seg_len or None), in time order
    frame_counts = {"with_face": 0, "with_heads": 0, "with_direction": 0}
    out = open(os.path.join(out_dir, "windows.jsonl"), "w", encoding="utf-8") if out_dir else None
    next_t, stop_reason, last_t, partial_s = None, "input ended", None, None
    if show_window:
        import cv2
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    def readiness(t_end, state):
        """('cadence' | 'touch' | None = waits, session, touch_until) of the segment ending at t_end, read from the
        release's copy of the touch state."""
        session = None if state is None else state.session_at(t_end)
        if session is None:
            return "cadence", None, None
        until = state.touch_until(session)
        return ("touch" if until is not None and until >= t_end else None), session, until

    def emit(t_end, ms_frame, seg_len, how, at, session, until, state):
        rows = list(buf) if entry is None else entry.window_rows(list(buf), t_end, state)
        rec = judge.evaluate(rows, t_end, segment_s=seg_len)
        w0 = t_end - (bundle.situation.window_s if bundle.situation is not None else (seg_len or seg_s))
        rec["evaluated"] = {"how": how, "at": round(at, 4), "session_id": session, "touch_until": until,
                            "touch_complete": window_any_tap(rows, (w0, t_end)) is not None}   # the rules' own cue
        timing.window(rec)
        print_fn(window_line(rec, ms_frame, local=sender is not None))
        if out:
            out.write(json.dumps(jsonable(rec), ensure_ascii=False) + "\n")
            out.flush()
        body = None
        if sender is not None and session is not None:   # no session named yet: nothing is sent
            body = vision_window(rec, session, entry.wall)
        if on_window is not None:                        # before the offer: the body may arrive at once
            on_window(rec, body)
        return body

    def flush(t, ms_frame, final=False):
        """Evaluates the due segments that are ready, in time order (module docstring, 'When a window is
        evaluated'); final = the input ended, every segment goes. The windows released in one call go to the sender
        as one release (TagSender.offer_release), so the segments one touch window released are sent together.
        One copy of the touch state (LiveTouch.state, taken once here) gives the release its readiness, its rows and
        its session ids: a window an HTTP thread adds meanwhile is read by the next release."""
        state = None if entry is None or not pending else entry.touch.state()
        states = [readiness(t_end, state) for t_end, _ in pending]
        last_ready = max((i for i, s in enumerate(states) if s[0] is not None), default=-1)
        release = []
        for i, (how, session, until) in enumerate(states):
            t_end, seg_len = pending[0]
            if how is None:
                if i < last_ready:
                    how = "later_ready"                # an older session's segment: its windows no longer come
                elif final:
                    how = "input_end"
                elif t - keep_s >= t_end - (seg_len or seg_s):
                    how = "kept_history"               # its start is about to leave the kept history
                else:
                    break
            pending.popleft()
            body = emit(t_end, ms_frame, seg_len, how, t, session, until, state)
            if body is not None:
                release.append(body)
        if release:
            sender.offer_release(release)

    frames = iter(source)
    sent = None
    try:
        try:
            for frame in frames:
                row = chain.process(frame)
                buf.append(row)
                add_frame_counts(frame_counts, row)
                timing.frame(row)
                t = last_t = float(row["t_s"])
                floor = t - keep_s if not pending else min(t - keep_s, pending[0][0] - keep_s)
                while buf and float(buf[0]["t_s"]) < floor:   # a waiting segment keeps the rows its window needs
                    buf.popleft()
                if entry is not None:
                    entry.add_row(row, frame, kept_from=float(buf[0]["t_s"]))
                if next_t is None:
                    next_t = t + seg_s
                while t >= next_t:
                    pending.append((next_t, None))
                    next_t += seg_s
                flush(t, row.get("ms_chain"))
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
        if next_t is not None and last_t > next_t - seg_s:   # rows after the last full window
            partial_s = last_t - (next_t - seg_s)
            pending.append((last_t, partial_s))
        if last_t is not None:
            flush(last_t, None, final=True)
    finally:
        close = getattr(frames, "close", None)
        if close:
            close()
        if entry is not None:
            entry.stop(getattr(source, "end_reason", None) or stop_reason)
        if sender is not None:
            sent = sender.close()
        if out:
            out.close()
        if show_window:
            import cv2
            cv2.destroyAllWindows()
            cv2.waitKey(1)
    if stop_reason == "input ended":
        stop_reason = getattr(source, "end_reason", None) or stop_reason
    meta = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "frames": timing.frames, "windows": timing.n_windows,
            "stop_reason": stop_reason, "bundle": bundle.to_dict(), "environment": environment(),
            "timing_ms": timing.summary(), "window_shown": bool(show_window),
            "counts": {"frames": frame_counts}, "models": model_info or {},
            "last_window_partial_s": None if partial_s is None else round(partial_s, 4),
            "source": {k: getattr(source, k) for k in ("name", "size_wh", "reported_fps", "time_source")
                       if hasattr(source, k)},
            "tag_sender": sent}
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
    ap.add_argument("--aid-model", default=None,
                    help="walking-aid detector ONNX (optional; off unless given, weights not in the repository)")
    add_aid_options(ap)
    ap.add_argument("--phone-model", default=None,
                    help="COCO YOLOX-Nano ONNX for the phone (optional; off unless given, weights not in the "
                         "repository; without --serve live has no touch log, so phone_use is never true, as the companion "
                         "path needs the touch counts too: false where the phone part or the body-still part is "
                         "false, otherwise unknown (column:tap_count when the phone part holds))")
    ap.add_argument("--serve", type=int, default=None, metavar="PORT",
                    help="local touch entry on 127.0.0.1:PORT (0 = a free port the OS chooses); off unless given")
    ap.add_argument("--allow-origin", action="append", default=[], metavar="ORIGIN",
                    help="order screen origin whose page may post touch windows (CORS); once per origin")
    ap.add_argument("--backend-url", default=None, metavar="URL",
                    help="backend base address (for example http://127.0.0.1:8000, the Compose backend); each "
                         "window's situation tags go "
                         "to URL/api/v1/sessions/{session_id}/vision-windows (tag_sender.py); needs --serve, off "
                         "unless given")
    a = ap.parse_args(argv)
    check_aid_options(ap, a)
    if a.serve is not None and not 0 <= a.serve <= 65535:
        ap.error("--serve needs a port from 0 to 65535")
    if a.allow_origin and a.serve is None:
        ap.error("--allow-origin needs --serve")
    if a.backend_url is not None:
        if a.serve is None:
            ap.error("--backend-url needs --serve (a window's session comes from the touch windows)")
        try:
            check_base_url(a.backend_url)
        except ValueError as e:
            ap.error(f"--backend-url: {e}")
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
    bundle = with_options(load_bundle(a.params), aid_values(a))
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    import cv2
    cv2.setNumThreads(1)
    from app.inference.vision import MediaPipeModels
    from .sources import LiveCameraSource
    detector, direction, info = load_perception(a.models, bundle.chain, a.threads, not a.no_heads, print)
    aids, aid_info = load_aids(a.aid_model, bundle.chain, a.threads, print)
    info.update(aid_info)                        # every model file in meta.json, as replay.py writes it
    phones, phone_info = load_phones(a.phone_model, bundle.chain, a.threads, print)
    info.update(phone_info)
    models = MediaPipeModels(a.models, blendshapes=a.blendshapes)
    entry = server = None
    try:
        source = LiveCameraSource(a.camera, a.cam_width, a.cam_height, a.backend, a.fps, a.seconds)
        if a.serve is not None:
            from .touch_entry import TouchEntry, start_server
            entry = TouchEntry(bundle, log=lambda line: print(line, flush=True))
            server = start_server(entry, a.serve, a.allow_origin)
            for line in entry_lines(server.server_address[1], a.allow_origin):
                print(line, flush=True)
        sender = None
        if a.backend_url is not None:            # the send timeout = the window cadence (tag_sender.py)
            sender = TagSender(a.backend_url, bundle.chain.segment_s, log=lambda line: print(line, flush=True))
            print(f"상황 태그 보내기 {sender.stats()['target']} · 제한 시간 {sender.timeout_s:g}초(창 간격)",
                  flush=True)
        timing = RunTiming(keeps_timing(a))
        note = unbounded_note(a)
        if note:
            print(note, flush=True)
        print(f"카메라 {a.camera} 시작 — 창마다 한 줄씩 나옵니다", flush=True)
        meta = run_live(source, bundle, models=models, detector=detector, direction=direction,
                        show_window=not a.no_window, out_dir=a.out, blendshapes=a.blendshapes, aids=aids,
                        model_info=info, phones=phones, entry=entry, sender=sender, timing=timing)
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        models.close()
    print(f"끝: 프레임 {meta['frames']}장 · 창 {meta['windows']}개 · 멈춘 이유 {meta['stop_reason']}", flush=True)
    if meta["tag_sender"] is not None:
        s = meta["tag_sender"]
        print(f"상황 태그: 보냄 {s['sent']} · 실패 {s['failed']} · 새 창으로 바뀜 {s['replaced']} · "
              f"끝에 못 보냄 {s['unsent_at_close']} · 끝난 세션의 답 404 {s['ended_404']} · 410 {s['ended_410']} · "
              f"끝난 세션이라 안 보냄 {s['skipped_ended']}"
              + (f" · 마지막 오류 {s['last_error']}" if s["last_error"] else ""), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
