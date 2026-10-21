"""Touch log -> touch counts on the video time axis (replay).

Input: the raw touch log the order screen keeps in development mode and exports as JSON ('JSON 내보내기' ->
touch-log-draft.json -> <take>_touch.json; frontend/src/features/order/touchLog.ts SavedLog: {version, sessionId,
serverSessionId, startedAt, events[]}, every event with sessionId, occurredAt (ISO 8601 UTC, Date.now()), screen, kind,
data). The raw log is a local draft, not a contract (docs/Touch-Log-Review.md 1, 7).

Video time of an event (recording script 2026-10-14 section 4, '시각 맞추기'):
  with <video>.clock.json (record_clip.py, 2026-10-13):  t = (occurredAt ms - first_frame.wall_epoch_ms) / 1000
                                                          + start_offset_s   (start_offset_s = a measured correction)
  without it:                                             t = (occurredAt ms - first event's occurredAt ms) / 1000
                                                          + start_offset_s   (start_offset_s = the video time of the
                                                          log's first event, found with the phone clock / clap)
Without the clock file and without start_offset_s the log cannot be placed: an error.

Counting - a [설계 제안] mapping, because the team has not decided how presses, misses and backs are counted
(Touch-Log-Review T01, T02, T07, T08; AGENTS.md: undecided items are not guessed silently). It follows the frontend's
own summary (touchLogSummary.ts) where that exists:
  tap_count       pointer_start events (the summary's `presses`; a press is counted once, click is not logged)
  miss_tap_count  pointer_start events whose data.target is null: outside every button and link (the summary's
                  `outsideTargetPresses`; contract TouchFeatures.miss_tap_count = '버튼 밖 터치 횟수'). A press on a
                  disabled button is on a button and is not a miss (the summary counts it apart). None when a press in
                  the interval has no target field (unknown_target_presses > 0): the count would only be a lower bound,
                  and the summary's outsidePressRatio is null in that case too.
  near_miss_fix_count  misses fixed at once (tree table 3-가 4-1 '같은 버튼 근처 빗나감 · 바로 고침'): a miss whose
                  data.nearestCandidates (the enabled buttons nearest to a press outside every button, useTouchLog.ts;
                  no distance limit, T03 undecided) holds the target id of the next press of the same session. Counted
                  at the miss's time, and only once the fixing press lies at or before the interval's end, so no count
                  reads a press after t1; a miss without candidates is never a fix. None under the same condition as
                  miss_tap_count. Linking a near press to the next press is T07, undecided: this is the proposal.
  back_count      screen_enter events from 'review' to 'menu' (OrderPage.tsx: '← 메뉴 더 고르기' review-back and the
                  menu-home link set the screen from review to menu). 'complete' -> 'menu' starts a new order (a new
                  session), not a back.
  repeat_tap_count, dwell_ms   not computed: their thresholds / meaning are undecided (T04, T05); always None.
Observation spans: the log observes the page from its first event, and again from a session_start / session_resume
event, until the next session_end / session_suspend event (useTouchLog.ts: reload, a new server session, pagehide).
After the last event with no such stop the span stays open: the page was open until the export at the end of the take.
A count exists only for an interval that lies wholly inside one span: rows before the first event, intervals that start
before it and intervals that reach past a stop event have no count (None = not measured); inside a span an interval
without touches counts 0. After a stop event the page is not observed, so screen_at gives no screen.
Truncation: the frontend keeps only its last LOG_LIMIT events, so a log that long may have lost its earliest events.
With the clock file meta['warnings'] says so (counts before the first remaining event are unknown, as above); without it
the log cannot be placed (--start-offset anchors on the first remaining event, which is then not the log's start).
Sessions: every event carries the frontend's sessionId (a random id, not personal data); meta['sessions'] lists them in
time order and session_at(t) names the session of the last event at or before t.
"""
from __future__ import annotations

import bisect
import dataclasses
import datetime
import json
import math
import os
from dataclasses import dataclass, field

CLOCK_SUFFIX = ".clock.json"              # record_clip.py: <clip> + ".clock.json"
SCREEN_FLOW = ("menu", "review", "complete")   # OrderPage.tsx screen order: menu -> review -> complete
BACK_TRANSITIONS = {("review", "menu")}        # see the module docstring
CART_ADD_TARGET = "cart-add"                   # OrderPage.tsx data-log-target of the '담기' button
LOG_LIMIT = 1000                               # touchLog.ts logLimit: the log keeps only its last 1,000 events
RESUME_KINDS = ("session_start", "session_resume")   # useTouchLog.ts: page load / new server session; bfcache return
STOP_KINDS = ("session_end", "session_suspend")      # useTouchLog.ts: reload / new server session; pagehide


@dataclass(frozen=True)
class TouchEvent:
    t: float                  # video time (s)
    kind: str
    screen: str | None
    press: bool = False
    miss: bool = False        # press outside every button / link (data.target null)
    target_unknown: bool = False   # press whose data has no target field (cannot tell)
    back: bool = False
    forward: bool = False
    cart_add: bool = False
    screen_enter: bool = False
    session: str | None = None     # the event's sessionId
    target_id: str | None = None   # press on a button / link: its data-log-target id
    candidates: tuple = ()         # miss: the ids of data.nearestCandidates
    fixed_next: bool = False       # miss whose next press of the same session hits one of its candidates
    fix_t: float | None = None     # fixed miss: video time of that next press
    resume: bool = False           # session_start / session_resume: observation (re)starts
    stop: bool = False             # session_end / session_suspend: observation stops
    options_open: bool = False
    options_close: bool = False


def _epoch_ms(iso: str) -> float | None:
    try:
        dt = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        return None
    return dt.timestamp() * 1000.0


def clock_anchor_ms(video_path: str) -> float | None:
    """first_frame.wall_epoch_ms of <video>.clock.json, or None when the file is not there."""
    p = video_path + CLOCK_SUFFIX
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        clock = json.load(f)
    value = (clock.get("first_frame") or {}).get("wall_epoch_ms")
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{p}: first_frame.wall_epoch_ms is missing or not a number")
    return float(value)


def _ids(items) -> tuple:
    """The non-empty string ids of a nearestCandidates list; anything else is skipped."""
    if not isinstance(items, list):
        return ()
    return tuple(c["id"] for c in items if isinstance(c, dict) and isinstance(c.get("id"), str) and c["id"])


def _classify(ev: dict, t: float) -> TouchEvent:
    kind, data = ev.get("kind"), ev.get("data")
    screen = ev.get("screen") if isinstance(ev.get("screen"), str) and ev.get("screen") else None
    sid = ev.get("sessionId")
    session = sid if isinstance(sid, str) and sid else None
    if kind == "pointer_start":
        has_target = isinstance(data, dict) and "target" in data
        target = data.get("target") if has_target else None
        target_id = target.get("id") if isinstance(target, dict) else None
        target_id = target_id if isinstance(target_id, str) and target_id else None
        disabled = isinstance(target, dict) and target.get("disabled") is True
        miss = has_target and target is None
        return TouchEvent(t, kind, screen, press=True, miss=miss, target_unknown=not has_target,
                          cart_add=target_id == CART_ADD_TARGET and not disabled, session=session,
                          target_id=target_id, candidates=_ids(data.get("nearestCandidates")) if miss else ())
    if kind == "screen_enter":
        src = data.get("from") if isinstance(data, dict) else None
        back = (src, screen) in BACK_TRANSITIONS
        forward = src in SCREEN_FLOW and screen in SCREEN_FLOW and SCREEN_FLOW.index(screen) == SCREEN_FLOW.index(src) + 1
        return TouchEvent(t, kind, screen, back=back, forward=forward, screen_enter=True, session=session)
    kind = str(kind)
    return TouchEvent(t, kind, screen, screen_enter=kind == "session_start", session=session,
                      resume=kind in RESUME_KINDS, stop=kind in STOP_KINDS, options_open=kind == "options_open",
                      options_close=kind == "options_close")


def mark_fixes(events: list) -> list:
    """The events (in time order) with fixed_next set on every miss whose next press of the same session hits one of
    its nearest candidates (module docstring, near_miss_fix_count)."""
    out = list(events)
    next_press = {}                       # session -> the first press after the current position
    for i in range(len(out) - 1, -1, -1):
        e = out[i]
        if e.miss and e.candidates:
            nxt = next_press.get(e.session)
            if nxt is not None and nxt.target_id in e.candidates:
                out[i] = dataclasses.replace(e, fixed_next=True, fix_t=nxt.t)
        if e.press:
            next_press[e.session] = e
    return out


def observed_spans(events: list) -> list:
    """[(start, end)] of the stretches the log observed, events in time order (module docstring): from the first event
    and from each resume event after a stop, to the next stop event; end None = open until the export."""
    spans, start = [], None
    for i, e in enumerate(events):
        if start is None and (i == 0 or e.resume):
            start = e.t
        if start is not None and e.stop:
            spans.append((start, e.t))
            start = None
    if start is not None:
        spans.append((start, None))
    return spans


@dataclass
class TouchTimeline:
    """Classified events in time order, with counting helpers (intervals are (t0, t1])."""
    events: list
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.events = sorted(self.events, key=lambda e: e.t)
        self.times = [e.t for e in self.events]
        self.first_t = self.times[0] if self.times else None
        self.spans = observed_spans(self.events)

    def covered(self, t: float) -> bool:
        """Whether the log was observing the page at video time t (inside an observation span)."""
        return any(s <= t and (e is None or t <= e) for s, e in self.spans)

    def covered_interval(self, t0: float | None, t1: float) -> bool:
        """Whether the whole interval (t0, t1] (t0 None: [0, t1]) lies inside one observation span."""
        lo = 0.0 if t0 is None else t0
        return lo <= t1 and any(s <= lo and (e is None or t1 <= e) for s, e in self.spans)

    def _between(self, t0: float | None, t1: float) -> list:
        """Events of (t0, t1]; t0 None = from the video start: [0, t1] (earlier events precede the recording)."""
        lo = bisect.bisect_left(self.times, 0.0) if t0 is None else bisect.bisect_right(self.times, t0)
        return self.events[lo:bisect.bisect_right(self.times, t1)]

    def counts(self, t0: float | None, t1: float) -> dict | None:
        """Touch counts of (t0, t1] (t0 None: [0, t1]); None unless the whole interval lies inside one observation
        span. miss_tap_count and near_miss_fix_count are None when a press in it has no target field."""
        if not self.covered_interval(t0, t1):
            return None
        evs = self._between(t0, t1)
        unknown = sum(e.target_unknown for e in evs)
        return {"tap_count": sum(e.press for e in evs), "miss_tap_count": None if unknown else sum(e.miss for e in evs),
                "near_miss_fix_count": None if unknown else sum(e.fixed_next and e.fix_t <= t1 for e in evs),
                "back_count": sum(e.back for e in evs), "unknown_target_presses": unknown,
                "repeat_tap_count": None, "dwell_ms": None}

    def flags(self, t0: float, t1: float) -> dict:
        evs = self._between(t0, t1)
        return {"forward": any(e.forward for e in evs), "cart_add": any(e.cart_add for e in evs),
                "screen_enter": any(e.screen_enter for e in evs)}

    def screen_at(self, t: float) -> tuple:
        """(screen, video time the current screen visit began) at time t; (None, None) before the first event and
        while the page is not observed (the last event at or before t is a stop event, or t is outside every span)."""
        k = bisect.bisect_right(self.times, t)
        if k == 0 or self.events[k - 1].stop or not self.covered(t):
            return None, None
        screen = next((e.screen for e in reversed(self.events[:k]) if e.screen), None)
        since = next((e.t for e in reversed(self.events[:k]) if e.screen_enter), self.first_t)
        return screen, since

    def session_at(self, t: float) -> str | None:
        """The sessionId of the last event at or before t; None before the first event."""
        k = bisect.bisect_right(self.times, t)
        return self.events[k - 1].session if k else None

    def options_open_at(self, t: float) -> bool | None:
        """Whether the options dialog is open at t: the last options_open / options_close / screen_enter / stop event
        at or before t is an options_open; None before the first event."""
        k = bisect.bisect_right(self.times, t)
        if k == 0:
            return None
        last = next((e for e in reversed(self.events[:k])
                     if e.options_open or e.options_close or e.screen_enter or e.stop), None)
        return last is not None and last.options_open

    def last_press(self, t: float) -> float | None:
        k = bisect.bisect_right(self.times, t)
        return next((e.t for e in reversed(self.events[:k]) if e.press), None)


def _sessions(events: list) -> list:
    """[{session_id, events, first_t, last_t}] in time order (events in time order)."""
    out = {}
    for e in events:
        s = out.setdefault(e.session, {"session_id": e.session, "events": 0, "first_t": e.t, "last_t": e.t})
        s["events"] += 1
        s["last_t"] = e.t
    return sorted(out.values(), key=lambda s: s["first_t"])


def load_timeline(log_path: str, video_path: str | None = None, start_offset_s: float | None = None) -> TouchTimeline:
    """The touch log on the video time axis (module docstring). video_path is used to find <video>.clock.json."""
    with open(log_path, encoding="utf-8-sig") as f:
        saved = json.load(f)
    if not isinstance(saved, dict) or not isinstance(saved.get("events"), list):
        raise ValueError(f"{log_path}: not a touch log export ({{version, sessionId, startedAt, events[]}})")
    n_saved = len(saved["events"])
    truncated = n_saved >= LOG_LIMIT
    raw = [(ev, _epoch_ms(ev.get("occurredAt"))) for ev in saved["events"] if isinstance(ev, dict)]
    timed = [(ev, ms) for ev, ms in raw if ms is not None]
    anchor = clock_anchor_ms(video_path) if video_path else None
    if anchor is not None:
        how, offset = f"{os.path.basename(video_path)}{CLOCK_SUFFIX} first_frame.wall_epoch_ms", start_offset_s or 0.0
    elif start_offset_s is not None:
        if truncated:
            raise ValueError(f"{log_path}: the log holds {n_saved} events, the frontend's limit (touchLog.ts logLimit "
                             f"= {LOG_LIMIT}), so its earliest events may be gone and its first remaining event is not "
                             "the log's start; --start-offset anchors on that event, so the log cannot be placed. "
                             "Record with the clock file (record_clip.py) or export the log before it reaches "
                             f"{LOG_LIMIT} events")
        if not timed:
            raise ValueError(f"{log_path}: no event with a valid occurredAt")
        anchor = min(ms for _, ms in timed)
        how, offset = "first event of the log at --start-offset", float(start_offset_s)
    else:
        raise ValueError("the touch log cannot be placed on the video time axis: no <video>.clock.json next to the "
                         "video and no --start-offset (recording script section 4, '시각 맞추기')")
    events = sorted((_classify(ev, (ms - anchor) / 1000.0 + offset) for ev, ms in timed), key=lambda e: e.t)
    tl = TouchTimeline(mark_fixes(events))
    warnings = []
    if truncated:
        where = "" if tl.first_t is None else f" (video time {tl.first_t:.3f} s)"
        warnings.append(f"the log holds {n_saved} events, the frontend's limit (touchLog.ts logLimit = {LOG_LIMIT}): "
                        f"its earliest events may have been dropped, so touch counts before its first remaining "
                        f"event{where} are unknown")
    tl.meta = {"log": os.path.basename(log_path), "anchor": how, "anchor_epoch_ms": anchor, "start_offset_s": offset,
               "events": len(raw), "events_without_time": len(raw) - len(timed),
               "first_t": tl.first_t, "last_t": tl.times[-1] if tl.times else None,
               "sessions": _sessions(tl.events), "spans": [[s, e] for s, e in tl.spans],
               "truncated_possible": truncated, "warnings": warnings,
               "mapping": "tap = pointer_start; miss = pointer_start with data.target null (None when a press has no "
                          "target field); fix = a miss whose next press of the same session hits one of its "
                          "nearestCandidates; back = screen_enter review -> menu ([설계 제안]; T01 / T02 / T07 / T08 "
                          "undecided)"}
    return tl
