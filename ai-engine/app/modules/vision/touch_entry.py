"""Local touch entry of the live runner: the order screen sends each touch window it measured, one way.

Path (the team paper's figure 1, project owner's decision 2026-11-25): the order screen on the same kiosk PC POSTs
each window's touch statistics - window_start, window_end, touch, the session and the screen - to
http://127.0.0.1:<port>/touch-windows. The answer is an acknowledgement only: nothing of the camera goes back to the
order screen; it is written once the tag sender has finished with the engine windows that touch window released
(at the latest segment_s after acceptance; 'Acknowledgement'). The camera loop and the entry run in one process:
live.run_live adds one row per frame (TouchEntry.add_row) and reads the reported touch into its own window
evaluation (TouchEntry.window_rows); the window's situation tags go to the backend from the runner (tag_sender.py), not
through the order screen. The entry listens on 127.0.0.1 only; no picture leaves the camera loop.

Request  POST /touch-windows, a JSON object (the FeatureWindowRequest fields read here; other keys are ignored):
  window_start, window_end  ISO 8601 date-time with a zone (the order screen builds them with Date.toISOString());
                            window_end after window_start
  touch                     {tap_count, miss_tap_count, back_count, ...} of that window: whole numbers >= 0 (contract
                            TouchFeatures)
  session_id                optional string, the order screen's session: a new one starts the per-session state again;
                            the backend's session the runner's windows are sent to (tag_sender.py)
  screen_id                 optional string, the current screen (contract FeatureWindowRequest.screen_id); kept with
                            the window and shown by GET /status
Answer   JSON {status, reason}; no vision value (no situation, tag, gaze, summary or measurable) in any answer.
  202 {status: accepted}          the window is placed on the camera's time axis and kept (RFC 9110 15.3.3: accepted
                                  for processing; the runner reads it at its next windows), and the answer is written
                                  once the window is settled, at most segment_s later ('Acknowledgement')
  400 {status: refused, reason}   a malformed body (the reason names the first problem), or a Content-Length that
                                  is not a length (negative, not a number); 411 without Content-Length
  403 {status: refused, reason}   a Host header that is not 127.0.0.1:<port> or localhost:<port> (every method;
                                  the usual defence against DNS rebinding), or a browser page whose Origin is not one
                                  of --allow-origin (a request without an Origin header, a local tool, is not refused);
                                  the first refusal of each Host and each origin is logged once, with what to fix
  503 {status: refused, reason}   no camera frame yet (the window cannot be placed on the camera's time axis), or the
                                  camera loop has stopped (no later window will read it)
  404 {status: not_found, reason} another path; 500 {status: error, reason} a fault of this code (logged)
  Host, path, Origin and Content-Length are checked on the headers alone: a request refused for one of them gets its
  answer with Connection: close, its body is never read and the connection ends; only an accepted request's body is
  read.
Acknowledgement. Every accepted window gets a number, 1, 2, ... in the order of acceptance (LiveTouch.report, under the
lock that stores it). Window n is settled when both hold:
  (a) the camera loop has processed a frame whose camera time is at or after n's end on the camera axis, and a flush
      (live.run_live, one per frame, also when no segment is pending) whose copy of the touch state holds n has run at
      that frame or later: every segment ending at or before n's end has been released by then (TouchEntry.due);
  (b) the tag sender has finished what that flush released and every release before it (TagSender.offer_release's
      done: each window posted, failed or skipped, or the release replaced unsent, or the sender closing). A flush that
      released nothing settles once the releases before it are finished (at once when the sender is idle); a run
      without a sender settles at once.
  Each window is settled on its own: two requests in flight at once can be accepted in another order than their ends,
  so a flush settles only the windows that have ended by its frame (TouchEntry.due, TouchEntry.settle). The handler of
  an accepted window writes its 202 once its own window is settled, at most segment_s of the value bundle after
  acceptance (the tag sender's own timeout; TouchEntry.wait_settled), and at once when the camera loop stops
  (TouchEntry.stop); refusals are answered at once. A 202 thus says: accepted, and the engine windows this touch window
  released have been handed to the tag sender and it has finished with them ((b)), or segment_s has passed, or the
  camera loop has stopped. A /features request the order screen sends after it thus usually reads those engine
  windows, but handing them on and reading them are best effort: an engine window whose send ended in a failure may
  or may not have reached the backend (a send that times out while reading the answer counts as failed, also when the
  backend has accepted the window), and one that was replaced before it was sent reaches no request. The wait holds
  no lock that the camera loop or the sender needs, and the camera loop never waits for an answer.
GET /status: whether the camera runs, its frame count, latest frame time, the kept history, the last touch window
received (its times, session and screen) and settling: the number of the latest accepted touch window and the highest
number n such that every window 1..n is settled (TouchEntry.settle). It carries no CORS header: local tools read it,
pages cannot.

Time axis. Window times are on the order screen's clock (Date.now()); on one machine that is the wall clock that
time.time() reads. Every camera frame carries its wall time (sources.Frame.epoch_s, read right after its monotonic
capture time); a request time E is placed on the camera axis as E - (epoch_s - t_s) of the latest frame, rounded to
the rows' 0.1 ms. The runner maps its windows back to the wall clock the same way (TouchEntry.wall). One offset (the
latest frame's) serves every time: a wall-clock step during the run (set by hand, or stepped by time sync) is not
corrected, so the rows kept before it, a late touch window and the segments still waiting for their touch are placed
or stamped with the new offset (a known limit, vision README).

Touch. The reported counts (the order screen's window, frontend interactionFeatures.ts FEATURE_WINDOW_MS, 1 s since
2026-11-26; the entry reads each window's own times) are the only touch input; every reported window is kept as long
as the rows. They reach the chain in two ways:
- the press anchor of the face-size reference (columns.FaceSizeRef, '첫 누름'): a window with tap_count > 0 says the
  session had a press by its end, so from the next frame on the reference collects with the press anchor; before the
  session's first reported press nothing is collected, as in a replay with a touch log;
- the per-row touch columns of the situation window [t1 - window_s, t1] of each window the runner evaluates. The
  rules count per row and a report is a total over its window, so the counts are placed on copies of the rows
  ([설계 제안]; press times in the request would make this exact): a row inside one reported window with zero counts
  gets 0; a reported
  window with counts that lies wholly inside the situation window puts its count on its last row there and leaves its
  other rows blank; a reported window across the situation window's start leaves its rows blank (where its presses
  were is not known); a row in no reported window, or in two, is blank. Blank means 'not measured', so the
  three-valued rules say 'cannot tell' where the counts do not settle a cue: rows after the latest reported window
  (the order screen sends a window when it ends) are blank, so while a session is known live.run_live evaluates a
  window only once that session's reported windows reach its end (LiveTouch.touch_until). A repeated request for
  the same window replaces its report.
Sessions. A new session_id starts the chain's per-session state again at the next frame (FrameChain via session_at,
as with a touch log), and the windows of every session, the first one after the runner starts included, read only
the rows after the start of its first reported window (a window (t0, t1] holds the times after t0). The rows between
that start and the request were processed with the previous session's state (for the first session: the state the
runner had built before it).
"""
from __future__ import annotations

import bisect
import json
import math
import re
import threading
from collections import deque, namedtuple
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .chain import history_s
from .replay import jsonable
from .touch import _epoch_ms

HOST = "127.0.0.1"
TOUCH_PATH = "/touch-windows"
TOUCH_KEYS = ("tap_count", "miss_tap_count", "back_count")   # contract TouchFeatures fields the entry reads

# one reported window on the camera axis, (t0, t1]; screen = the body's screen_id when it carries one
Report = namedtuple("Report", "t0 t1 tap miss back session screen", defaults=(None,))
Request = namedtuple("Request", "start end start_text end_text touch session screen")


def iso(epoch_s: float | None) -> str | None:
    """Wall-clock seconds -> ISO 8601 UTC with milliseconds, the form Date.toISOString() gives."""
    if epoch_s is None:
        return None
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def plain(value):
    """json.dumps fallback for numpy scalars in the rows (their .item() is the Python number)."""
    item = getattr(value, "item", None)
    if item is None:
        raise TypeError(f"not JSON: {type(value).__name__}")
    return item()


def parse_request(body) -> Request:
    """The request (module docstring) or ValueError naming the first problem."""
    if not isinstance(body, dict):
        raise ValueError("the body is not a JSON object")
    times = {}
    for key in ("window_start", "window_end"):
        value = body.get(key)
        ms = _epoch_ms(value) if isinstance(value, str) else None
        if ms is None or not math.isfinite(ms):
            raise ValueError(f"{key} is not an ISO 8601 date-time with a zone: {value!r}")
        times[key] = ms / 1000.0
    if times["window_end"] <= times["window_start"]:
        raise ValueError("window_end is not after window_start")
    touch = body.get("touch")
    if not isinstance(touch, dict):
        raise ValueError("touch is missing or not an object (contract TouchFeatures)")
    counts = {}
    for key in TOUCH_KEYS:
        value = touch.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"touch.{key} is not a whole number >= 0: {value!r}")
        counts[key] = value
    found = {}
    for key in ("session_id", "screen_id"):
        value = body.get(key)
        if value is not None and not (isinstance(value, str) and value):
            raise ValueError(f"{key} is not a non-empty string: {value!r}")
        found[key] = value
    return Request(times["window_start"], times["window_end"], body["window_start"], body["window_end"], counts,
                   found["session_id"], found["screen_id"])


@dataclass(frozen=True)
class TouchState:
    """One immutable copy of the touch state (LiveTouch.state): the reports, the session boundaries and each
    session's completion bound. A release of the runner reads its readiness, its rows and its session ids from one
    copy, so an HTTP thread that adds a window meanwhile cannot change what that release reads."""
    reports: tuple = ()        # Report, sorted by (t0, t1)
    sessions: tuple = ()       # ((session_id, since), ...) sorted by since
    until: tuple = ()          # ((session_id, latest end of its reported windows), ...)
    accepted: int = 0          # the number of the latest touch window stored before this copy (LiveTouch.report)

    def _index(self, t: float) -> int:
        """Number of sessions that started before t (a reported window (t0, t1] holds the times after t0)."""
        return sum(1 for _, since in self.sessions if since < t)

    def session_at(self, t: float) -> str | None:
        k = self._index(t)
        return self.sessions[k - 1][0] if k else None

    def session_since(self, t: float) -> float | None:
        """Start of the session at t (its first reported window's start); None before any. Unlike
        touch.TouchTimeline.session_since, the first session has one too: a touch log starts with its first session,
        while the live runner has been running before it, and those rows belong to no session."""
        k = self._index(t)
        return self.sessions[k - 1][1] if k else None

    def touch_until(self, session: str) -> float | None:
        """The latest end of the reported windows of this session (camera axis), None before its first one. Only the
        session's own windows count: an older session's windows say nothing about a newer one's touch."""
        return dict(self.until).get(session)


class LiveTouch:
    """The order screen's reported windows on the camera axis, with the TouchTimeline methods FrameChain reads
    (session_at, session_since, last_press, counts). Written by the HTTP threads, read by the camera loop; state()
    gives one immutable copy (TouchState) for the runner's releases."""

    # chain.FrameChain resets its per-session state (tracks, the main user, the references) also when the first known
    # session arrives: the live runner was running before any order session, and that state belongs to no session.
    FIRST_SESSION_RESETS = True

    def __init__(self):
        self.lock = threading.Lock()
        self.reports = []      # Report, sorted by (t0, t1); one per window
        self.sessions = []     # [(session_id, since)] sorted by since: a session holds the times after its first
                               # reported window's start
        self.presses = []      # sorted, no repeats: the anchor and the ends of the kept reports with a press (the
                               # latest time a window's presses can have); rebuilt with every change of the reports
        self.anchor = None     # the latest press of the reports already dropped: the session's first-press anchor
        self.until = {}        # session_id -> the latest end of its reported windows (its touch is known up to there)
        self.accepted = 0      # touch windows stored so far = the number of the latest one (LiveTouch.report)

    def _rebuild_presses(self):
        """With the lock held: the presses follow the reports, so a replaced report takes its press with it."""
        ends = sorted({r.t1 for r in self.reports if r.tap > 0})
        if self.anchor is not None and (not ends or self.anchor < ends[0]):
            ends.insert(0, self.anchor)
        self.presses = ends

    def report(self, t0: float, t1: float, touch: dict, session: str | None, screen: str | None = None) -> int:
        """Stores one reported window and returns its number: 1, 2, ... in the order the windows are stored, given
        under the lock that stores it, so a copy (state) holds exactly the windows numbered up to its accepted."""
        with self.lock:
            self.reports = [r for r in self.reports if (r.t0, r.t1) != (t0, t1)]   # a repeated window replaces
            self.reports.append(Report(t0, t1, touch["tap_count"], touch["miss_tap_count"], touch["back_count"],
                                       session, screen))
            self.reports.sort(key=lambda r: (r.t0, r.t1))
            if session is not None and all(s != session for s, _ in self.sessions):
                self.sessions.append((session, t0))
                self.sessions.sort(key=lambda s: s[1])
            if session is not None:
                self.until[session] = max(t1, self.until.get(session, t1))
            self._rebuild_presses()
            self.accepted += 1
            return self.accepted

    def state(self) -> TouchState:
        """One immutable copy, taken under the lock (the lock is not held while the copy is read)."""
        with self.lock:
            return TouchState(tuple(self.reports), tuple(self.sessions), tuple(self.until.items()), self.accepted)

    def touch_until(self, session: str) -> float | None:
        return self.state().touch_until(session)

    def prune(self, kept_from: float):
        """Drops what the kept rows (from kept_from on) no longer need: the reports that end before them (their last
        press stays as the anchor), and the sessions that ended before them. Kept: the session at kept_from (the
        boundary before the earliest kept time), every later one, and the session of every kept report; the
        pending segments of the runner end after kept_from, so their sessions are among these."""
        with self.lock:
            dropped = [r.t1 for r in self.reports if r.t1 < kept_from and r.tap > 0]
            if dropped:
                self.anchor = max(dropped + ([] if self.anchor is None else [self.anchor]))
            self.reports = [r for r in self.reports if r.t1 >= kept_from]
            k = sum(1 for _, since in self.sessions if since < kept_from)
            needed = {r.session for r in self.reports}
            self.sessions = [s for i, s in enumerate(self.sessions) if i >= k - 1 or s[0] in needed]
            names = {s for s, _ in self.sessions}
            self.until = {s: u for s, u in self.until.items() if s in names}
            self._rebuild_presses()

    def snapshot(self) -> list:
        with self.lock:
            return list(self.reports)

    def session_at(self, t: float) -> str | None:
        return self.state().session_at(t)

    def session_since(self, t: float) -> float | None:
        return self.state().session_since(t)

    def last_press(self, t: float) -> float | None:
        with self.lock:
            k = bisect.bisect_right(self.presses, t)
            return self.presses[k - 1] if k else None

    def counts(self, t0, t1):
        """Per-row counts are not known when a frame is processed; each window places them (place_touch)."""
        return None


def place_touch(rows: list, reports: list, w0: float, w1: float) -> list:
    """Copies of the rows of the situation window [w0, w1] with tap_count / miss_tap_count placed from the reported
    windows (module docstring, 'Touch'); the other rows are returned as they are."""
    times = [float(r["t_s"]) for r in rows]
    inside = [i for i, t in enumerate(times) if w0 <= t <= w1]
    owners = {i: [rep for rep in reports if rep.t0 < times[i] <= rep.t1] for i in inside}
    values = {i: {"tap_count": None, "miss_tap_count": None} for i in inside}
    for i in inside:
        if len(owners[i]) == 1:
            rep = owners[i][0]
            for key, n in (("tap_count", rep.tap), ("miss_tap_count", rep.miss)):
                if n == 0:
                    values[i][key] = 0
    for rep in reports:
        own = [i for i in inside if owners[i] == [rep]]
        if not own or rep.t0 < w0 or rep.t1 > w1:
            continue
        for key, n in (("tap_count", rep.tap), ("miss_tap_count", rep.miss)):
            if n > 0:
                values[own[-1]][key] = n
    out = list(rows)
    for i in inside:
        out[i] = {**rows[i], **values[i]}
    return out


class TouchEntry:
    """The touch entry's state (module docstring): the reported touch windows, the camera's clock and kept history."""

    def __init__(self, bundle, log=None):
        self.bundle = bundle
        self.keep_s = history_s(bundle) + bundle.chain.segment_s     # = live.run_live's ring buffer
        self.touch = LiveTouch()
        self.log = log
        self.lock = threading.Lock()
        self.times = deque()                   # camera times of the kept rows (the runner keeps the rows)
        self.offset = None                     # wall-clock s minus camera s, of the latest frame
        self.latest_t = None
        self.frames = 0
        self.stopped = None                    # the stop reason once the camera loop has ended
        self.last = None                       # the last touch window received (times as sent, session, screen)
        # the acknowledgement (module docstring, 'Acknowledgement'): the longest an accepted window's answer waits is
        # the value bundle's segment_s, the tag sender's own timeout (live.main); no other bound
        self.settle_s = bundle.chain.segment_s
        self.acks = threading.Condition()      # guards waiting, finished and settled; the HTTP threads wait on it
        self.waiting = {}                      # number -> camera-axis end of the accepted windows no flush has taken
        self.finished = set()                  # the settled windows numbered above `settled` (an earlier one is not)
        self.settled = 0                       # every accepted window up to this number is settled

    # --- camera loop ------------------------------------------------------------------------------------------
    def add_row(self, row: dict, frame, kept_from: float | None = None):
        """One processed frame: its row and its wall time (frame.epoch_s; the camera source sets it). kept_from = the
        time of the first row the runner still keeps (live.run_live keeps longer while a window waits for its touch);
        without it, the rows of the last keep_s seconds. The reports that end before it are dropped."""
        if getattr(frame, "epoch_s", None) is None:
            raise ValueError("the touch entry needs frames with a wall-clock time (sources.LiveCameraSource "
                             "sets Frame.epoch_s)")
        t = float(row["t_s"])
        with self.lock:
            self.times.append(t)
            self.offset = float(frame.epoch_s) - float(frame.t_s)
            self.latest_t = t
            self.frames += 1
            while self.times and self.times[0] < (t - self.keep_s if kept_from is None else kept_from):
                self.times.popleft()
            kept_from = self.times[0] if self.times else t
        self.touch.prune(kept_from)

    def stop(self, reason: str):
        with self.lock:
            self.stopped = reason
        with self.acks:                        # every answer still waiting is written at once
            self.acks.notify_all()

    def due(self, t: float, state: TouchState) -> tuple:
        """Camera loop, once per flush (live.run_live): the numbers of the accepted windows this flush settles (module
        docstring, 'Acknowledgement', (a)), in order: those in the flush's copy of the touch state (number <=
        state.accepted) that end at or before t, the time of the frame just processed; () when there is none. Each
        number is given to one flush only. A window that ends after t keeps waiting, also when a later number has
        ended: two requests in flight at once can be accepted in another order than their ends."""
        with self.acks:
            numbers = tuple(sorted(n for n, end in self.waiting.items() if n <= state.accepted and end <= t))
            for n in numbers:
                del self.waiting[n]
        return numbers

    def settle(self, numbers):
        """The windows `numbers` are settled and their waiting answers are written; `settled` moves up over every
        number up to the first window not yet settled."""
        with self.acks:
            self.finished.update(n for n in numbers if n > self.settled)
            while self.settled + 1 in self.finished:
                self.settled += 1
                self.finished.remove(self.settled)
            self.acks.notify_all()

    def _is_settled(self, number: int) -> bool:
        """With acks held."""
        return number <= self.settled or number in self.finished

    def wait_settled(self, number: int) -> bool:
        """HTTP thread: waits until window `number` itself is settled, at most settle_s, and not at all once the camera
        loop has stopped; True when it was settled. The wait holds no lock (threading.Condition.wait releases it)."""
        with self.acks:
            self.acks.wait_for(lambda: self._is_settled(number) or self.stopped is not None, self.settle_s)
            return self._is_settled(number)

    def wall(self, t: float | None) -> float | None:
        """A camera time on the wall clock (the latest frame's offset, as the touch windows are placed)."""
        with self.lock:
            offset = self.offset
        return None if t is None or offset is None else t + offset

    def window_rows(self, rows: list, t_end: float, state: TouchState | None = None) -> list:
        """The rows the runner's window at t_end reads: nothing after t_end, nothing before the session at t_end
        (its first reported window's start), and the reported touch placed on the situation window (place_touch).
        state = the release's copy of the touch state (LiveTouch.state); without it, a fresh copy."""
        state = self.touch.state() if state is None else state
        since = state.session_since(t_end)
        rows = [r for r in rows if float(r["t_s"]) <= t_end and (since is None or float(r["t_s"]) > since)]
        sp = self.bundle.situation
        if sp is None:
            return rows
        return place_touch(rows, list(state.reports), t_end - sp.window_s, t_end)

    # --- answers ----------------------------------------------------------------------------------------------
    def status(self) -> dict:
        with self.lock:
            offset, latest_t, frames, stopped, last = self.offset, self.latest_t, self.frames, self.stopped, self.last
            kept_from = self.times[0] if self.times else None
        wall = (lambda t: None if t is None or offset is None else iso(t + offset))
        with self.acks:
            settled = self.settled
        return {"status": "stopped" if stopped else "running", "frames": frames,
                "camera": {"latest_frame_at": wall(latest_t), "kept_from_at": wall(kept_from),
                           "keep_s": self.keep_s, "stopped": stopped},
                "touch": {"windows": len(self.touch.snapshot()), "last": last},
                "settling": {"accepted": self.touch.state().accepted, "settled": settled}}

    def receive(self, body) -> tuple:
        """(HTTP code, JSON body) of one touch window: an acknowledgement, never a vision value (accept, without the
        window's number)."""
        code, out, _ = self.accept(body)
        return code, out

    def accept(self, body) -> tuple:
        """(HTTP code, JSON body, number) of one touch window: number = the accepted window's number (LiveTouch.report),
        None for a refusal. The HTTP handler waits for that number to be settled (wait_settled)."""
        try:
            req = parse_request(body)
        except ValueError as e:
            return 400, {"status": "refused", "reason": str(e)}, None
        with self.lock:
            offset, stopped = self.offset, self.stopped
        if stopped is not None:
            return 503, {"status": "refused", "reason": f"the camera loop has stopped ({stopped})"}, None
        if offset is None:
            return 503, {"status": "refused",
                         "reason": "no camera frame yet: the window cannot be placed on the camera's time axis"}, None
        t0, t1 = round(req.start - offset, 4), round(req.end - offset, 4)
        with self.acks:                        # stored, numbered and waiting before a flush can look for it (due)
            number = self.touch.report(t0, t1, req.touch, req.session, req.screen)
            self.waiting[number] = t1
        with self.lock:
            self.last = {"window_start": req.start_text, "window_end": req.end_text, "session_id": req.session,
                         "screen_id": req.screen}
        if self.log:
            self.log(f"[터치 창 {req.end_text}] 받음 | 세션 {req.session or '-'} | 화면 {req.screen or '-'} | "
                     f"누름 {req.touch['tap_count']} · 버튼 밖 {req.touch['miss_tap_count']} · "
                     f"되돌아감 {req.touch['back_count']}")
        return 202, {"status": "accepted"}, number


ORIGIN_HINT = ("--allow-origin must be the exact origin in the order screen's address bar "
               "(http://127.0.0.1:5173 and http://localhost:5173 are different origins)")   # 5173: Vite's default port;
# (frontend/package.json's dev script, vite --host 127.0.0.1, serves the order screen on http://127.0.0.1:5173)
ORIGIN_HINT_KO = ("--allow-origin에는 주문 화면 주소창의 출처를 그대로 적어야 합니다"
                  "(http://127.0.0.1:5173과 http://localhost:5173은 다른 출처입니다)")


def host_allowed(host: str | None, port: int) -> bool:
    """The request's Host header names this entry: 127.0.0.1:<port> or localhost:<port> (the bound loopback address;
    host names compare without case). Anything else - another name that resolves here, as a DNS-rebinding page sends
    it, or no Host at all - is refused."""
    return host is not None and host.strip().lower() in (f"{HOST}:{port}", f"localhost:{port}")


def start_server(entry: TouchEntry, port: int, origins=(), host: str = HOST) -> ThreadingHTTPServer:
    """The HTTP server on host:port, serving in a daemon thread; port 0 = a free port the OS chooses (the usual meaning
    of port 0 in a bind), read back from server.server_address[1]. origins = the order screen origins whose pages may
    post touch windows (CORS); a POST with another Origin header is refused, one without an Origin (a local tool) is
    not (OWASP CSRF Prevention Cheat Sheet: verifying the origin with standard headers). Every request must name this
    entry in its Host header (host_allowed: the usual defence against DNS rebinding). CORS headers go on the answers
    of POST /touch-windows and its preflight only; GET /status is for local tools. The first refusal of each origin and
    of each Host is logged once, with what to fix."""
    allowed = frozenset(origins)
    told, told_lock = set(), threading.Lock()

    def tell(key, line: str):
        with told_lock:
            if key in told:
                return
            told.add(key)
        if entry.log:
            entry.log(line)

    class Handler(BaseHTTPRequestHandler):
        server_version = "vision-touch-entry/1"

        def log_message(self, fmt, *args):      # the entry logs one line per touch window instead
            pass

        def _cors(self):
            origin = self.headers.get("Origin")
            if origin is not None and origin in allowed:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

        def _send(self, code: int, body: dict, cors: bool = False, close: bool = False):
            self._send_text(code, json.dumps(jsonable(body), ensure_ascii=False, default=plain), cors, close)

        def _send_text(self, code: int, text: str, cors: bool = False, close: bool = False):
            data = text.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if cors:
                self._cors()
            if close:                              # a refusal before any body is read: the connection ends here
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def _refuse(self, code: int, body: dict):
            """An answer before the request's body is read; the body is never read and the connection is closed (a
            refused page cannot make this entry read or wait for what it sends)."""
            self._send(code, body, close=True)

        def _host_ok(self) -> bool:
            port = self.server.server_address[1]
            host = self.headers.get("Host")
            if host_allowed(host, port):
                return True
            tell(("host", host), f"[터치 입구] Host {host}인 요청을 거절함: 이 입구는 {HOST}:{port} · localhost:{port}로만 "
                                 f"받습니다")
            self._refuse(403, {"status": "refused",
                               "reason": f"Host {host!r} is not this entry ({HOST}:{port} or localhost:{port})"})
            return False

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is None or origin in allowed:
                return True
            tell(("origin", origin), f"[터치 입구] 허용하지 않은 출처 {origin}의 요청을 거절함: {ORIGIN_HINT_KO}")
            return False

        def do_OPTIONS(self):
            """CORS preflight of the order screen's JSON POST. Access-Control-Allow-Private-Network answers Chrome's
            Private Network Access preflight (WICG Private Network Access draft) for an allowed origin."""
            if not self._host_ok():
                return
            origin_ok = self._origin_ok()
            self.send_response(204)
            if origin_ok and self.path.split("?")[0] == TOUCH_PATH and self.headers.get("Origin") is not None:
                self._cors()
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                if self.headers.get("Access-Control-Request-Private-Network") == "true":
                    self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if not self._host_ok():
                return
            if self.path.split("?")[0] == "/status":
                self._send(200, entry.status())          # no CORS header: local tools read it, not pages
            else:
                self._send(404, {"status": "not_found", "reason": f"no {self.path}"})

        def do_POST(self):
            """Host, path, Origin and Content-Length are checked on the headers alone; only an accepted request's
            body is read."""
            if not self._host_ok():
                return
            if self.path.split("?")[0] != TOUCH_PATH:
                self._refuse(404, {"status": "not_found", "reason": f"no {self.path}"})
                return
            if not self._origin_ok():
                self._refuse(403, {"status": "refused",
                                   "reason": f"origin {self.headers.get('Origin')} is not allowed: {ORIGIN_HINT}"})
                return
            given = self.headers.get("Content-Length")
            if given is None:
                self._refuse(411, {"status": "refused", "reason": "Content-Length is missing"})
                return
            if re.fullmatch(r"[0-9]+", given.strip()) is None:   # RFC 9110 8.6: 1*DIGIT; no sign, no other form
                self._refuse(400, {"status": "refused", "reason": f"Content-Length is not a length: {given!r}"})
                return
            raw = self.rfile.read(int(given))
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                self._send(400, {"status": "refused", "reason": f"the body is not JSON: {e}"}, cors=True)
                return
            try:
                code, out, number = entry.accept(body)
                data = json.dumps(jsonable(out), ensure_ascii=False, default=plain)   # fails here, not mid-send
            except Exception as e:    # a fault of this code: say so instead of dropping the connection
                if entry.log:
                    entry.log(f"[터치 입구] 받지 못함: {type(e).__name__}: {e}")
                self._send(500, {"status": "error", "reason": f"{type(e).__name__}: {e}"}, cors=True)
                return
            if number is not None:     # accepted: answered once settled (module docstring, 'Acknowledgement')
                entry.wait_settled(number)
            self._send_text(code, data, cors=True)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="vision-touch-entry", daemon=True).start()
    return server
