"""Wheelchair confirm step (optional, off unless --aid-confirm-model is given): a window whose aid_use is true with the
class wheelchair keeps that answer only when the confirm reader (app/inference/aid_confirm.py) also reads a wheelchair
in the same window; otherwise aid_use becomes false (no aid). Other answers (a stick class, false, unknown) are not
touched. Needs a head_centre reading of the walking-aid detector (params.aid_rule head_centre or head_centre_carry).

Rows (FrameChain, after the detector's own reading of the row): the main user's person box = on a row with the main
user's head box, the highest-scoring detector person box (Aids.boxes, any class) that holds the head box centre; on a
row whose value was carried (aid_head_from carried) the detector person box with the highest IoU to the carried
aid box; otherwise none. The reader's input image of that box (the crop it was trained with) is kept for the rows of
the last keep_s seconds.

Windows (WindowJudge, after the situation): only when aid_use is true with the class wheelchair, the reader's values
of the window's rows are used (each row read once). The window's reader value is judged by the same window logic as
aid_use (events.observe_scene and situation's head reading on the window's rows, with the row value = P(wheelchair)
and the row's class wheelchair; rows without a person box have no value): its median above the confirm cut keeps the
answer. The confirm cut has no value of its own in the engine: the runner gives it (--aid-confirm-min; default 0.5 =
the reader's own decision point, the cut of every table of the measurement).

Read-ahead (start_readahead; live.py): rows are read on one reader thread before their window ends, but only while
the detector's own reading of a row inside the current window span (the last window_s seconds) is a wheelchair
reading by the window rule's own values: aid_head_class wheelchair and aid_head_score above aid_head_min. When such a
row comes, the kept rows of that span not read yet are queued in time order (the oldest rows belong to the window that
ends first), and every new row is queued while a triggering row lies inside its span. A window check then waits only
for reads still in flight. Without read-ahead (replay.py) the check reads its rows itself. The values are the same
either way.

Hold (--aid-confirm-hold, off by default): once the reader has agreed with a wheelchair window, every later window
with the engine's wheelchair answer is kept without reading, until the engine ends the user's stretch: a window whose
scene tag user_changed is true with a main_user_changed event not seen before (the engine's change of main user,
situation.user_changed), a window that starts a new touch session (the record's session_reset in replay; in live,
where the judge has no touch log, a window whose release names another session id than the last one named: live.py
passes each window's own session id, and with the touch entry the first named session counts as new too
(first_session_resets), because FrameChain resets the main-user tracker there), or a window whose aid_use is unknown
with the engine's reason no_main_user_box (no main user in the window) or no_frames (no rows). That window keeps the
engine's own answer, and the ones after it need a new agreement. No timer. After a hold ends, read-ahead starts again
from the rows of that window (the session's rows), never from older rows. A hold starts only on a window whose rows
inside the window span all lie at or after FrameChain's last per-session reset (FrameChain sets reset = (row time,
session id) where it resets its main-user tracker), and, where the window's release names a session (live.py), only
when that is the session of that reset (with the touch entry, a named session before any reset has none yet: the
touch window can arrive on its HTTP thread after FrameChain read the session of a frame and before the same loop
releases the window, so no hold starts there): before its reset the chain's rows still carry the earlier main user (a
wheelchair user still in view while another person starts the session). The window's own answer (confirmed or
withdrawn) does not change; such a window is read like any other, so a hold starts at the earliest one window
length after the reset.

User hold (--aid-confirm-hold-user, off by default; includes the hold): after that agreement EVERY later window of the
same user answers aid_use true, whatever the engine's own window answer is, until the same end signals (a window
with no rows or no main user is never answered true). The tag's
evidence and unknown reason stay the engine's own (its aid_class is the engine's class behind its median, possibly
another class or none); the record's aid_confirm says hold_user true and gives the engine's own status and class.
A window at which a hold ended carries hold_end (session | user_changed | no_main_user_box | no_frames) in its
aid_confirm.

Reader errors: an exception of the reader after the start (its crop in add_row or its read) makes every window whose
rows include that row "not confirmed" (aid_use false, as a withdrawn window) with aid_confirm.error; the first one is
logged once per run and the count goes to the summary. A withdrawn window's aid_confirm.reason says why: the
engine's own window rule's reason (too_few_rows, no_main_user_box), "median" (the median is not above the cut) or
"reader_error". Loading the files at the start is not covered: a missing or
unreadable file stops the start (app/inference/aid_confirm.py).

Start only (--aid-start-only, off by default; not with the two holds): the walking aid is judged once at the start of
a user's stretch. A stretch starts where FrameChain's session changes (the touch log's or the touch entry's session
id; also the first known one) and at a row whose change columns carry a change of main user that
events.user_since counts (new_user on events._change_obs of the row); FrameChain calls new_start there, on the frame
thread, before the row's walking-aid detector would run. Without a session nothing is switched off. WindowJudge calls
check_start with the window's session (live.py: the session its release names; replay: the touch log's). A window of
the stretch passes the row test when every row inside its span lies at or after the stretch's start and the hold's
own test (_after_reset) holds for that session. The first placed press of the stretch is the time of its first row
at or after the stretch's start with a press (events.window_any_tap on that row). A window of the session answered
aid_use true (a wheelchair window the reader agreed with, or a stick-class window) whose end lies at or after the
stretch's start, also one whose span starts before it, marks the stretch as one with an aid, which is never switched
off. The start judgment is the first passing window whose span starts at or after the first press
and whose answer is a judged false: the engine's own false, or a wheelchair window the reader read and did not agree
with (reason "median"); an unknown window and a withdrawal for another reason are no judgment. There, unless the
stretch is marked, the stretch is switched off: the judge publishes (stretch, session, start) under start_lock, and
only while the frame thread is still in that stretch (a late one is dropped). While the frame thread's current stretch
is off, FrameChain does not call the walking-aid detector nor add_row (no crop, no read-ahead; blank aid columns, as
for a skipped detector), and every window of that session whose end lies in the stretch answers aid_use false with no
evidence (aid_confirm start_off true). The judgment window's record carries start_judgment true. The next stretch
starts the judgment again, with the detector on from its first row.

Stick at the start (stick readers given, --aid-stick-model with --aid-stick-frames N; needs start only; off by
default): every row for which add_row makes the main user's crop is read by each stick file (one person-crop reader
per file, app/inference/aid_confirm.py) on the reader thread (live, the read-ahead pool) or in place (replay, no pool).
A row is a stick frame when any file's stick value max(P(crutch), P(cane)) lies above STICK_P. Wheelchair first, at
row level: the first row of a main user that the detector itself reads as a wheelchair (aid_head_class wheelchair,
aid_head_score above aid_head_min, the read-ahead's row test) clears that user's count and stops the stick files for
that user; only rows before it count (on the measured clips of wheelchair users the readers' stick rows all came
after that row). The stick frames are counted per main user: a stretch started by a counted change of main user
starts a new count, and so does a new session, except that a new session carries the count of the stretch before it
when that stretch was the walk-in (rows before the first known
session, or a stretch started by a counted change of main user): the walk-in before the first press is the same
user's. In check_start, before the start judgment, a window of the stretch's session that ends in the stretch, whose
answer is not true after the wheelchair check, that has rows and a main user (its unknown reason not no_frames or
no_main_user_box) and whose user has at least N stick frames answers aid_use true with the class cane (evidence
aid_head@<frame> aid_class cane, the form the backend reads); its record's aid_confirm carries stick true,
stick_frames and stick_min. From then on every such window of the same user answers so without reading (the stick
files stop for that user), and the stretch counts as one with an aid. A user with a window the reader agreed is a
wheelchair never gets the stick answer, and the stick files stop for that user. In live the check first waits for the
stick reads of the rows up to the window's end. A stick reader error is logged once per run; the row is no stick frame.
"""
from __future__ import annotations

import sys
import threading
from concurrent.futures import CancelledError

from .columns import _contains
from .events import _blank, _change_obs, new_user, observe_scene, window_any_tap

WHEELCHAIR = "wheelchair"
STICK_CLASSES = ("crutch", "cane")    # the stick classes of the person-crop readers' class list
STICK_CLASS = "cane"                  # the class a stick answer names (module docstring, 'Stick at the start')
STICK_P = 0.5                         # each stick file's own decision point (the confirm cut's default, CONFIRM_MIN_DEFAULT)


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def person_box(aids, row: dict):
    """The main user's person box of a row (fractions of the frame), or None (module docstring)."""
    head = row.get("primary_box")
    if head is not None:
        h = [float(v) for v in head]
        centre = [((h[0] + h[2]) / 2.0, (h[1] + h[3]) / 2.0)]
        best, score = None, -1.0
        for box, s in zip(aids.boxes, aids.scores):
            if _contains(box, centre) and float(s) > score:
                best, score = tuple(float(v) for v in box), float(s)
        return best
    carried = row.get("aid_head_box")
    if row.get("aid_head_from") == "carried" and carried is not None:
        best, overlap = None, 0.0
        for box in aids.boxes:
            v = _iou(box, carried)
            if v > overlap:
                best, overlap = tuple(float(x) for x in box), v
        return best
    return None


class AidConfirm:
    """The confirm step shared by FrameChain (add_row) and WindowJudge (check). reader = an AidConfirmReader (or a
    stand-in with crop(bgr, box_px) and probs(image)); cut = the confirm cut; keep_s = seconds of rows kept; hold /
    hold_user = the two holds (module docstring; hold_user includes hold); start_only = --aid-start-only (module
    docstring, 'Start only')."""

    def __init__(self, reader, cut: float, keep_s: float, hold: bool = False, hold_user: bool = False, log=None,
                 start_only: bool = False, stick=None, stick_min: int | None = None,
                 stick_row_min: float | None = None):
        self.reader, self.cut, self.keep_s = reader, float(cut), float(keep_s)
        self.stick = list(stick) if stick else None   # stick at the start: one reader per file (module docstring)
        self.stick_min = None if stick_min is None else int(stick_min)
        self.stick_row_min = stick_row_min    # stick: aid_head_min, the detector's wheelchair row test
        self.stick_key = {0: 0}               # stick, frame thread: stretch -> the user whose count it adds to
        self.stick_kind = {0: "walk_in"}      # stick, frame thread: stretch -> how it started
        self.stick_counts = {}                # stick: user -> stick frames
        self.stick_answered = set()           # stick: users answered cane
        self.stick_wheelchair = set()         # stick: users with a confirmed wheelchair window
        self.stick_pending = []               # stick, live: (row time, Future) of reads not waited for yet
        self.stick_times = []                 # stick: row times of the stick frames (summary)
        self.stick_reads = 0                  # stick: crops read (all files of a row = one)
        self.stick_errors = 0                 # stick: rows whose read raised
        self.stick_windows = 0                # stick: windows answered cane
        self.log = log if log is not None else (lambda line: print(line, file=sys.stderr, flush=True))
        self.hold_user = bool(hold_user)
        self.hold = bool(hold) or self.hold_user
        self.held = False                     # hold: the reader has agreed with this user's wheelchair answer
        self.changes = set()                  # hold: main_user_changed event ids already seen
        self.held_windows = 0                 # hold: windows kept without reading
        self.user_held_windows = 0            # user hold: windows answered true that the engine did not answer so
        self.images = {}                      # frame_idx -> (t_s, input image)
        self.wheelchair = {}                  # frame_idx -> P(wheelchair), read once
        self.reads = 0                        # reader calls
        self.checked = 0                      # windows checked (aid_use true with the class wheelchair)
        self.withdrawn = 0                    # of them, windows whose answer became false
        self.pool = None                      # read-ahead: one reader thread (start_readahead)
        self.futures = {}                     # read-ahead: frame_idx -> Future of P(wheelchair)
        self.waited = []                      # read-ahead: per check, the reads it had to wait for
        self.lock = threading.Lock()
        self.session = None                   # hold: the last session id a window's release named (live.py)
        self.hold_ends = {}                   # hold: end signal -> how often a hold ended there
        self.failed = {}                      # frame_idx -> the reader error of that row (crop or read)
        self.errors = 0                       # windows made "not confirmed" by a reader error
        self.first_session_resets = False     # live.run_live with the touch entry: the first named session is new
        self.kept_from = None                 # live.run_live: the first row time its buffer still keeps
        self.readahead_from = None            # after a hold ended: read-ahead reads no row before this time
        self.trigger_until = None             # read-ahead goes on for rows up to this time
        self.reset = None                     # FrameChain: (row time, session id) of its last per-session reset
        self.start_only = bool(start_only)    # start only (module docstring)
        self.start_lock = threading.Lock()
        self.stretch = 0                      # start only, frame thread: rises at every new_start
        self.start_from = None                # start only, frame thread: (row time, session id, stretch) of the last
        self.off = None                       # start only: (stretch, session id, its start) switched off
        self.off_until = None                 # start only: the start of the stretch after the one switched off
        self.judged_stretch = None            # start only, judge: the stretch its press and mark below belong to
        self.press_t = None                   # start only, judge: the stretch's first placed press
        self.aid_seen = False                 # start only, judge: the stretch had a window answered aid_use true
        self.sessions_off = 0                 # start only: stretches switched off
        self.start_off_windows = 0            # start only: windows answered by start_off
        self.frames_skipped = 0               # start only: rows on which the walking-aid detector did not run

    def start_readahead(self, row_min: float, window_s: float) -> None:
        """Read rows ahead on one reader thread (module docstring); row_min = aid_head_min, window_s = the
        situation window."""
        from concurrent.futures import ThreadPoolExecutor
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aid-confirm-read")
        self.row_min, self.window_s = float(row_min), float(window_s)

    def stop_readahead(self) -> None:
        if self.pool is not None:
            self.pool.shutdown(wait=True)

    def summary(self) -> dict:
        """The step's counts and the reader's call time (meta.json 'aid_confirm')."""
        ms = sorted(getattr(self.reader, "ms", []))
        waited = sorted(self.waited)
        start = ({"start_only": True, "sessions_off": self.sessions_off, "windows_start_off": self.start_off_windows,
                  "frames_aid_skipped": self.frames_skipped} if self.start_only else {})
        if self.stick is not None:
            start["stick"] = {"files": len(self.stick), "stick_p": STICK_P, "min_frames": self.stick_min,
                              "reads": self.stick_reads, "stick_frames": len(self.stick_times),
                              "stick_frame_t": [round(t, 3) for t in sorted(self.stick_times)],
                              "per_user": {str(k): v for k, v in sorted(self.stick_counts.items())},
                              "users_answered": len(self.stick_answered), "windows_answered": self.stick_windows,
                              "reader_errors": self.stick_errors}
        return {**start, "cut": self.cut, "hold": self.hold, "hold_user": self.hold_user, "windows_held": self.held_windows,
                "windows_user_held": self.user_held_windows,
                "windows_checked": self.checked, "windows_withdrawn": self.withdrawn,
                "hold_ends": dict(self.hold_ends), "reader_errors": self.errors,
                "reads": self.reads, "ms_read_p50": ms[len(ms) // 2] if ms else None,
                "ms_read_max": ms[-1] if ms else None, "readahead": self.pool is not None,
                "reads_waited_per_check": ({"n": len(waited), "p50": waited[len(waited) // 2], "max": waited[-1]}
                                           if waited else None)}

    def _read(self, frame_idx: int, image) -> float:
        with self.lock:
            self.reads += 1                   # every call, also one that raises
        try:
            p = self.reader.probs(image)
            v = float(p[list(self.reader_classes()).index(WHEELCHAIR)])
        except Exception as e:                # module docstring, 'Reader errors'
            if frame_idx in self.images:
                self.failed[frame_idx] = f"{type(e).__name__}: {e}"
            raise
        if frame_idx in self.images:          # a row pruned meanwhile keeps no value (no growth)
            self.wheelchair[frame_idx] = v
        return v

    def _submit(self, frame_idx: int, image):
        if frame_idx not in self.futures and frame_idx not in self.wheelchair:
            self.futures[frame_idx] = self.pool.submit(self._read, frame_idx, image)

    def add_row(self, row: dict, bgr, aids) -> None:
        t = float(row["t_s"])
        floor = t - self.keep_s if self.kept_from is None else min(t - self.keep_s, self.kept_from)
        for k in [k for k, (tk, _) in self.images.items() if tk < floor]:   # rows a waiting window needs stay
            del self.images[k]
            self.wheelchair.pop(k, None)
            future = self.futures.pop(k, None)
            if future is not None:            # a queued read no window will use; a running one finishes unused
                future.cancel()
            self.failed.pop(k, None)
        box = person_box(aids, row)
        if box is not None:
            H, W = bgr.shape[:2]
            try:
                self.images[int(row["frame_idx"])] = (t, self.reader.crop(bgr, (box[0] * W, box[1] * H, box[2] * W,
                                                                               box[3] * H)))
            except Exception as e:            # no image; a window with this row is not confirmed (check)
                self.failed[int(row["frame_idx"])] = f"{type(e).__name__}: {e}"
                box = None
        if self.stick is not None:
            self._stick_row(row, t, box)
        if self.pool is None or self.held:
            return
        score = row.get("aid_head_score")
        if row.get("aid_head_class") == WHEELCHAIR and score is not None and float(score) > self.row_min:
            first = self.trigger_until is None or t > self.trigger_until
            self.trigger_until = t + self.window_s
            if first:                         # backfill the span's kept rows not read yet, oldest first
                start = t - self.window_s if self.readahead_from is None else max(t - self.window_s,
                                                                                    self.readahead_from)
                for k, (tk, image) in sorted(self.images.items(), key=lambda kv: kv[1][0]):
                    if tk >= start:
                        self._submit(k, image)
        if self.trigger_until is not None and t <= self.trigger_until and box is not None:
            self._submit(int(row["frame_idx"]), self.images[int(row["frame_idx"])][1])

    # --- stick at the start (module docstring, 'Stick at the start') -------------------------------------------------
    def _stick_row(self, row: dict, t: float, box) -> None:
        """add_row, frame thread: the row's wheelchair test and its stick read (queued on the pool, or in place)."""
        key = self.stick_key.get(self.stretch, self.stretch)
        if key in self.stick_answered or key in self.stick_wheelchair:
            return
        score = row.get("aid_head_score")
        if (row.get("aid_head_class") == WHEELCHAIR and score is not None and self.stick_row_min is not None
                and float(score) > self.stick_row_min):
            with self.lock:                   # wheelchair first: the user's count is cleared and stays so
                self.stick_wheelchair.add(key)
                self.stick_counts[key] = 0
            return
        if box is None:
            return
        image = self.images[int(row["frame_idx"])][1]
        if self.pool is not None:
            self.stick_pending.append((t, self.pool.submit(self._stick_read, key, t, image)))
        else:
            self._stick_read(key, t, image)

    def _stick_read(self, key, t: float, image) -> None:
        if key in self.stick_answered or key in self.stick_wheelchair:
            return                            # the user's answer is settled: no more reads
        try:
            values = []
            for r in self.stick:
                p = r.probs(image)
                classes = list(getattr(r, "classes", self.reader_classes()))
                values.append(max(float(p[classes.index(c)]) for c in STICK_CLASSES))
        except Exception as e:                # module docstring: the row is no stick frame
            with self.lock:
                self.stick_errors += 1
                first = self.stick_errors == 1
            if first:
                self.log(f"지팡이 분류기 오류(이 실행에서 한 번만 찍습니다): {type(e).__name__}: {e}. 이 행은 지팡이 "
                         "행으로 세지 않습니다.")
            return
        with self.lock:
            self.stick_reads += 1
            if any(v > STICK_P for v in values) and key not in self.stick_wheelchair:
                self.stick_counts[key] = self.stick_counts.get(key, 0) + 1
                self.stick_times.append(t)

    def _stick_answer(self, tag: dict, record, rows: list, t_end: float, stretch: int):
        """check_start: the window's stick answer (its aid_confirm record), or None (module docstring)."""
        key = self.stick_key.get(stretch, stretch)
        if record is not None and record.get("confirmed") is True:
            self.stick_wheelchair.add(key)    # the reader agreed with a wheelchair: that answer stays
            return None
        if key in self.stick_wheelchair or tag["status"] is True:
            return None
        if tag["status"] == "unknown" and tag["unknown_reason"] in ("no_frames", "no_main_user_box"):
            return None
        if key not in self.stick_answered:
            pending, self.stick_pending = self.stick_pending, []
            for t, future in pending:         # live: the reads of the rows up to the window's end
                if t <= t_end:
                    future.result()
                else:
                    self.stick_pending.append((t, future))
            if self.stick_counts.get(key, 0) < self.stick_min:
                return None
            self.stick_answered.add(key)
        inside = [r for r in rows if float(r["t_s"]) <= t_end]
        last = inside[-1] if inside else None
        tag.update(status=True, unknown_reason=None,
                   evidence=[{"event_id": f"aid_head@{'' if last is None else last['frame_idx']}", "obs": "aid_class",
                              "value": STICK_CLASS, "t": t_end if last is None else float(last["t_s"])}])
        self.stick_windows += 1
        return {**(record or {"confirmed": None}), "stick": True, "stick_frames": self.stick_counts.get(key, 0),
                "stick_min": self.stick_min}

    def snapshot(self, rows: list) -> dict:
        """{frame_idx: input image} of the rows that have one: taken where the rows are taken (the frame loop), so a
        window read later on a worker thread (live.py) reads the same images though add_row has dropped them since."""
        out = {}
        for r in rows:
            kept = self.images.get(int(r["frame_idx"]))
            if kept is not None:
                out[int(r["frame_idx"])] = kept[1]
        return out

    def _value(self, frame_idx: int, images: dict | None = None):
        failed = self.failed.get(frame_idx)   # .get: the frame thread may prune between a test and a lookup
        if failed is not None:
            raise RuntimeError(failed)
        v = self.wheelchair.get(frame_idx)
        if v is not None:
            return v
        future = self.futures.get(frame_idx)
        if future is not None:
            try:
                return future.result()
            except CancelledError:            # pruned meanwhile (add_row): read again from the image below
                pass
        if images is not None:
            image = images.get(frame_idx)
        else:
            kept = self.images.get(frame_idx)
            image = None if kept is None else kept[1]
        if image is None:
            return None
        if self.pool is not None:             # one reader thread reads every row; this read stays out of futures:
            return self.pool.submit(self._read, frame_idx, image).result()   # add_row's prune never sees it
        return self._read(frame_idx, image)

    def _after_reset(self, inside: list, session: str | None) -> bool:
        """Whether a hold may start on a window (module docstring, 'Hold'): every row inside its span lies at or after
        FrameChain's last per-session reset, and a session the window's release names is the session of that reset."""
        reset = self.reset                    # one read: FrameChain writes it on the frame thread
        if reset is None:                     # a named session with the touch entry: its reset is still to come
            return not (session is not None and self.first_session_resets)
        t_reset, reset_session = reset
        if session is not None and session != reset_session:
            return False
        return all(float(r["t_s"]) >= t_reset for r in inside)

    def reader_classes(self):
        from app.inference.aid_confirm import CLASSES
        return getattr(self.reader, "classes", CLASSES)

    def check(self, out: dict, rows: list, t_end: float, situation_params, chain_params,
              images: dict | None = None, session_reset: bool = False, session: str | None = None) -> dict | None:
        """Applies the step to a window's situation output (its aid_use tag, in place). Returns None when the window
        was not a wheelchair answer (and no user hold answered it, and no hold ended at it: then {confirmed None,
        held False, hold_end}), else the window record's aid_confirm. images =
        snapshot(rows) taken earlier (None: the kept images now). session = the session id the window's release
        names (live.py; None = not named): another id than the last one named is a new session, by the same rule as
        WindowJudge's session_reset (replay passes session_reset itself)."""
        from .situation import _aid_use_by_head
        tag = next(t for t in out["tags"] if t["name"] == "aid_use")
        cls = next((e["value"] for e in tag["evidence"] if e["obs"] == "aid_class"), None)
        engine_wheelchair = tag["status"] is True and cls == WHEELCHAIR
        new_session = (session is not None and session != self.session
                       and (self.session is not None or self.first_session_resets))
        if session is not None:
            self.session = session
        end = None
        if self.hold:                         # the engine ends the user's stretch: a new agreement is needed
            change = next(t for t in out["tags"] if t["name"] == "user_changed")
            ids = {e["event_id"] for e in change["evidence"]} if change["status"] is True else set()
            if session_reset or new_session:
                end = "session"
            elif ids - self.changes:
                end = "user_changed"
            elif tag["status"] == "unknown" and tag["unknown_reason"] in ("no_main_user_box", "no_frames"):
                end = tag["unknown_reason"]
            self.changes |= ids
            if end is not None and self.held:
                self.held = False
                self.hold_ends[end] = self.hold_ends.get(end, 0) + 1
                self.trigger_until = None     # read-ahead starts again, from this window's rows only
                self.readahead_from = min((float(r["t_s"]) for r in rows), default=t_end)
            else:
                end = None
        ended = {} if end is None else {"hold_end": end}
        if self.hold_user and self.held:
            engine = {"engine_status": tag["status"], "engine_class": cls,
                      "engine_unknown_reason": tag["unknown_reason"]}
            if not engine_wheelchair:
                self.user_held_windows += 1
                tag["status"] = True
                tag["unknown_reason"] = None
            else:
                self.checked += 1
                self.held_windows += 1
            return {"confirmed": True, "held": True, "hold_user": True, **engine, "cut": self.cut, "median": None,
                    "rows": 0, "reads": 0}
        if not engine_wheelchair:             # the engine's own answer stays; a hold that ended here is recorded
            return None if end is None else {"confirmed": None, "held": False, **ended}
        if self.held:
            self.checked += 1
            self.held_windows += 1
            return {"confirmed": True, "held": True, "cut": self.cut, "median": None, "rows": 0, "reads": 0}
        window = (t_end - situation_params.window_s, t_end)
        inside = [r for r in rows if window[0] <= float(r["t_s"]) <= window[1]]
        before = self.reads
        if self.pool is not None:
            self.waited.append(sum(1 for r in inside if int(r["frame_idx"]) not in self.wheelchair))
        error = None
        try:
            read = []
            for r in rows:
                q = dict(r)
                v = self._value(int(r["frame_idx"]), images) if window[0] <= float(r["t_s"]) <= window[1] else None
                q.update(aid_head_score=v, aid_head_class=None if v is None else WHEELCHAIR)
                read.append(q)
        except Exception as e:                # module docstring, 'Reader errors': not confirmed
            error = f"{type(e).__name__}: {e}"
            self.errors += 1
            if self.errors == 1:
                self.log(f"휠체어 확인 분류기 오류(이 실행에서 한 번만 찍습니다): {error}. 이 행이 든 창은 확인되지 "
                         "않은 창으로 답합니다(보조기구 사용 아님).")
        if error is None:
            scene = observe_scene(read, window, chain_params.approach_ratio_min,
                                  chain_params.head_approach_ratio_min, chain_params.segment_s)
            status, events, reason = _aid_use_by_head(scene, self.cut, situation_params.face_visible_min)
        else:
            status, events, reason = None, [], "reader_error"
        median = events[0]["obs"]["aid_head_median"] if events else None
        confirmed = status is True
        if confirmed and self.hold and self._after_reset(inside, session):
            self.held = True
        self.checked += 1
        if not confirmed:
            self.withdrawn += 1
            tag["status"] = False
            tag["unknown_reason"] = None
        return {"confirmed": confirmed, **({"held": False} if self.hold else {}),
                **({"hold_user": False} if self.hold_user else {}), **ended, "cut": self.cut, "median": median,
                "rows": events[0]["obs"]["rows"] if events else 0, "reads": self.reads - before,
                **({} if confirmed else {"reason": reason or "median"}),
                **({} if error is None else {"error": error})}

    # --- start only (module docstring, 'Start only') ------------------------------------------------------------------
    def new_start(self, t: float, session: str, kind: str = "session") -> None:
        """FrameChain, frame thread: a new stretch starts at row time t (kind session: a new session; user: a counted
        change of main user); an off stretch it ends keeps its windows up to t. With the stick files a new session
        keeps the walk-in's count (module docstring, 'Stick at the start')."""
        if not self.start_only:
            return
        with self.start_lock:
            if self.off is not None and self.off[0] == self.stretch and self.off_until is None:
                self.off_until = t
            prev = self.stretch
            self.stretch += 1
            if self.stick is not None:
                walk_in = kind == "session" and self.stick_kind.get(prev) in ("walk_in", "user")
                self.stick_key[self.stretch] = self.stick_key.get(prev, prev) if walk_in else self.stretch
                self.stick_kind[self.stretch] = kind
            self.start_from = (t, session, self.stretch)

    def row_change(self, row: dict, session: str | None) -> None:
        """FrameChain, frame thread, after the row's change columns: a change of main user that events.user_since
        counts starts a new stretch at that row."""
        if (self.start_only and session is not None and not _blank(row.get("main_user_prev_track"))
                and new_user(_change_obs(row))):
            self.new_start(float(row["t_s"]), session, "user")

    def start_skip(self) -> bool:
        """FrameChain, frame thread: whether the current stretch is switched off (the row's detector is not run)."""
        off = self.off
        if not self.start_only or off is None or off[0] != self.stretch:
            return False
        self.frames_skipped += 1
        return True

    def check_start(self, out: dict, rows: list, t_end: float, situation_params, chain_params,
                    images: dict | None = None, session: str | None = None) -> dict | None:
        """check() under --aid-start-only; session = the window's session (None: check() alone). Returns the window
        record's aid_confirm (None as check() does)."""
        tag = next(t for t in out["tags"] if t["name"] == "aid_use")
        with self.start_lock:
            off, until = self.off, self.off_until
        if (session is not None and off is not None and off[1] == session and t_end >= off[2]
                and (until is None or t_end < until)):
            self.start_off_windows += 1
            tag.update(status=False, unknown_reason=None, evidence=[])
            return {"confirmed": None, "start_off": True}
        status = tag["status"]
        cls = next((e["value"] for e in tag["evidence"] if e["obs"] == "aid_class"), None)
        record = self.check(out, rows, t_end, situation_params, chain_params, images)
        start = self.start_from
        if session is None or start is None or start[1] != session:
            return record
        t0, _, stretch = start
        if stretch != self.judged_stretch:
            self.judged_stretch, self.press_t, self.aid_seen = stretch, None, False
        for r in rows:
            t = float(r["t_s"])
            if t >= t0 and (self.press_t is None or t < self.press_t) and window_any_tap([r], (t, t)) is True:
                self.press_t = t
        if self.stick is not None and t_end >= t0 and not (off is not None and off[0] == stretch):
            stick = self._stick_answer(tag, record, rows, t_end, stretch)   # before the start judgment
            if stick is not None:
                record = stick
        if tag["status"] is True and t_end >= t0:   # an answer true that ends in the stretch keeps it on
            self.aid_seen = True
        w0 = t_end - situation_params.window_s
        inside = [r for r in rows if w0 <= float(r["t_s"]) <= t_end]
        if (not inside or any(float(r["t_s"]) < t0 for r in inside) or not self._after_reset(inside, session)
                or (off is not None and off[0] == stretch)):
            return record
        if tag["status"] is True:
            return record
        judged = status is False or (status is True and cls == WHEELCHAIR and record is not None
                                     and record.get("reason") == "median")
        if not judged or self.aid_seen or self.press_t is None or w0 < self.press_t:
            return record
        if not self.switch_off(stretch, session, t0):
            return record
        return {**(record or {"confirmed": None}), "start_judgment": True}

    def switch_off(self, stretch: int, session: str, t0: float) -> bool:
        """The judge's OFF for a stretch (start_from's values); dropped when the frame thread has moved on to
        another stretch meanwhile. Whether it was applied."""
        with self.start_lock:
            if self.stretch != stretch:
                return False
            self.off, self.off_until = (stretch, session, t0), None
        self.sessions_off += 1
        return True
