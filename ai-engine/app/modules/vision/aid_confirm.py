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
"""
from __future__ import annotations

import sys
import threading
from concurrent.futures import CancelledError

from .columns import _contains
from .events import observe_scene

WHEELCHAIR = "wheelchair"


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
    hold_user = the two holds (module docstring; hold_user includes hold)."""

    def __init__(self, reader, cut: float, keep_s: float, hold: bool = False, hold_user: bool = False, log=None):
        self.reader, self.cut, self.keep_s = reader, float(cut), float(keep_s)
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
        return {"cut": self.cut, "hold": self.hold, "hold_user": self.hold_user, "windows_held": self.held_windows,
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
