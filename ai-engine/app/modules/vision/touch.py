"""Touch log -> touch counts on the video time axis (replay).

Input: the raw touch log the order screen keeps in development mode and exports as JSON ('JSON 내보내기' ->
touch-log-draft.json -> <take>_touch.json; frontend/src/features/order/touchLog.ts SavedLog: {version, sessionId,
serverSessionId, startedAt, events[]}, every event with occurredAt (ISO 8601 UTC, Date.now()), screen, kind, data).
The raw log is a local draft, not a contract (docs/Touch-Log-Review.md 1, 7).

Video time of an event (recording script 2026-10-14 section 4, '시각 맞추기'):
  with <video>.clock.json (record_clip.py, 2026-10-13):  t = (occurredAt ms - first_frame.wall_epoch_ms) / 1000
                                                          + start_offset_s   (start_offset_s = a measured correction)
  without it:                                             t = (occurredAt ms - first event's occurredAt ms) / 1000
                                                          + start_offset_s   (start_offset_s = the video time of the
                                                          log's first event, found with the phone clock / clap)
Without the clock file and without start_offset_s the log cannot be placed: an error.

Counting - a [설계 제안] mapping, because the team has not decided how presses, misses and backs are counted
(Touch-Log-Review T01, T02, T08; AGENTS.md: undecided items are not guessed silently). It follows the frontend's own
summary (touchLogSummary.ts) where that exists:
  tap_count       pointer_start events (the summary's `presses`; a press is counted once, click is not logged)
  miss_tap_count  pointer_start events whose data.target is null: outside every button and link (the summary's
                  `outsideTargetPresses`; contract TouchFeatures.miss_tap_count = '버튼 밖 터치 횟수'). A press on a
                  disabled button is on a button and is not a miss (the summary counts it apart).
  back_count      screen_enter events from 'review' to 'menu' (OrderPage.tsx: '← 메뉴 더 고르기' review-back and the
                  menu-home link set the screen from review to menu). 'complete' -> 'menu' starts a new order (a new
                  session), not a back.
  repeat_tap_count, dwell_ms   not computed: their thresholds / meaning are undecided (T04, T05); always None.
Coverage: rows before the log's first event have no count (None = not measured); after its last event the page was
still open until the export at the end of the take, so the count is 0.
"""
from __future__ import annotations

import bisect
import datetime
import json
import math
import os
from dataclasses import dataclass, field

CLOCK_SUFFIX = ".clock.json"              # record_clip.py: <clip> + ".clock.json"
SCREEN_FLOW = ("menu", "review", "complete")   # OrderPage.tsx screen order: menu -> review -> complete
BACK_TRANSITIONS = {("review", "menu")}        # see the module docstring
CART_ADD_TARGET = "cart-add"                   # OrderPage.tsx data-log-target of the '담기' button


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


def _classify(ev: dict, t: float) -> TouchEvent:
    kind, data = ev.get("kind"), ev.get("data")
    screen = ev.get("screen") if isinstance(ev.get("screen"), str) and ev.get("screen") else None
    if kind == "pointer_start":
        has_target = isinstance(data, dict) and "target" in data
        target = data.get("target") if has_target else None
        target_id = target.get("id") if isinstance(target, dict) else None
        disabled = isinstance(target, dict) and target.get("disabled") is True
        return TouchEvent(t, kind, screen, press=True, miss=has_target and target is None,
                          target_unknown=not has_target, cart_add=target_id == CART_ADD_TARGET and not disabled)
    if kind == "screen_enter":
        src = data.get("from") if isinstance(data, dict) else None
        back = (src, screen) in BACK_TRANSITIONS
        forward = src in SCREEN_FLOW and screen in SCREEN_FLOW and SCREEN_FLOW.index(screen) == SCREEN_FLOW.index(src) + 1
        return TouchEvent(t, kind, screen, back=back, forward=forward, screen_enter=True)
    return TouchEvent(t, str(kind), screen, screen_enter=kind == "session_start")


@dataclass
class TouchTimeline:
    """Classified events in time order, with counting helpers (intervals are (t0, t1])."""
    events: list
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.events = sorted(self.events, key=lambda e: e.t)
        self.times = [e.t for e in self.events]
        self.first_t = self.times[0] if self.times else None

    def covered(self, t: float) -> bool:
        """Whether the log was running at video time t (from its first event on)."""
        return self.first_t is not None and t >= self.first_t

    def _between(self, t0: float | None, t1: float) -> list:
        """Events of (t0, t1]; t0 None = from the video start: [0, t1] (earlier events precede the recording)."""
        lo = bisect.bisect_left(self.times, 0.0) if t0 is None else bisect.bisect_right(self.times, t0)
        return self.events[lo:bisect.bisect_right(self.times, t1)]

    def counts(self, t0: float | None, t1: float) -> dict | None:
        """Touch counts of (t0, t1] (t0 None: [0, t1]); None when the log did not cover t1 yet."""
        if not self.covered(t1):
            return None
        evs = self._between(t0, t1)
        return {"tap_count": sum(e.press for e in evs), "miss_tap_count": sum(e.miss for e in evs),
                "back_count": sum(e.back for e in evs), "unknown_target_presses": sum(e.target_unknown for e in evs),
                "repeat_tap_count": None, "dwell_ms": None}

    def flags(self, t0: float, t1: float) -> dict:
        evs = self._between(t0, t1)
        return {"forward": any(e.forward for e in evs), "cart_add": any(e.cart_add for e in evs),
                "screen_enter": any(e.screen_enter for e in evs)}

    def screen_at(self, t: float) -> tuple:
        """(screen, video time the current screen visit began) at time t; (None, None) before the first event."""
        k = bisect.bisect_right(self.times, t)
        if k == 0:
            return None, None
        screen = next((e.screen for e in reversed(self.events[:k]) if e.screen), None)
        since = next((e.t for e in reversed(self.events[:k]) if e.screen_enter), self.first_t)
        return screen, since

    def last_press(self, t: float) -> float | None:
        k = bisect.bisect_right(self.times, t)
        return next((e.t for e in reversed(self.events[:k]) if e.press), None)


def load_timeline(log_path: str, video_path: str | None = None, start_offset_s: float | None = None) -> TouchTimeline:
    """The touch log on the video time axis (module docstring). video_path is used to find <video>.clock.json."""
    with open(log_path, encoding="utf-8-sig") as f:
        saved = json.load(f)
    if not isinstance(saved, dict) or not isinstance(saved.get("events"), list):
        raise ValueError(f"{log_path}: not a touch log export ({{version, sessionId, startedAt, events[]}})")
    raw = [(ev, _epoch_ms(ev.get("occurredAt"))) for ev in saved["events"] if isinstance(ev, dict)]
    timed = [(ev, ms) for ev, ms in raw if ms is not None]
    anchor = clock_anchor_ms(video_path) if video_path else None
    if anchor is not None:
        how, offset = f"{os.path.basename(video_path)}{CLOCK_SUFFIX} first_frame.wall_epoch_ms", start_offset_s or 0.0
    elif start_offset_s is not None:
        if not timed:
            raise ValueError(f"{log_path}: no event with a valid occurredAt")
        anchor = min(ms for _, ms in timed)
        how, offset = "first event of the log at --start-offset", float(start_offset_s)
    else:
        raise ValueError("the touch log cannot be placed on the video time axis: no <video>.clock.json next to the "
                         "video and no --start-offset (recording script section 4, '시각 맞추기')")
    events = [_classify(ev, (ms - anchor) / 1000.0 + offset) for ev, ms in timed]
    sessions = sorted({str(ev.get("sessionId")) for ev, _ in timed})
    meta = {"log": os.path.basename(log_path), "anchor": how, "anchor_epoch_ms": anchor, "start_offset_s": offset,
            "events": len(raw), "events_without_time": len(raw) - len(timed), "sessions": len(sessions),
            "first_t": min((e.t for e in events), default=None), "last_t": max((e.t for e in events), default=None),
            "mapping": "tap = pointer_start; miss = pointer_start with data.target null; back = screen_enter "
                       "review -> menu ([설계 제안]; T01 / T02 / T08 undecided)"}
    return TouchTimeline(events, meta)
