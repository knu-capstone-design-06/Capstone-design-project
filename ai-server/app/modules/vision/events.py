"""사건 (events) layer: the observation rows of one window -> events, the cues the situation rules combine.

Layers: 관측값 features.py -> 사건 this file -> 상황 situation.py. Plain Python: no numpy, OpenCV or MediaPipe.

An event is one thing that happened, with the observations that show it:
    {event_id, kind, t_start, t_end, obs: {name: value}, source_frames}
Observations with one cause make ONE event (sem section 4, '근거 중복'): a head turn whose yaw grows, whose face
points are then lost while the shoulders stay, and which comes back is one look_back - not a yaw event plus a
face-loss event. event_id = '<kind>@<frame_idx of the event's first frame>', unique within a window. source_frames =
the frames whose observations the event used (a bridged drop-out is not one of them).

Every window, count, angle and floor is a pilot value ([파일럿]): PilotParams has no defaults and this file sets
none (dec section 3: '모든 창 길이 · 횟수 · 각도는 [파일럿]', set from the distribution in the team's self-recording).

Input: one dict per frame in time order.
- columns features.py writes: frame_idx, t_s, face_state, body_state, yaw_deg, face_cx, pose_vis_shoulders
- optional columns that no code in this repository writes yet. An event kind that needs one is looked for only when
  every row of the window carries it (measured_columns); otherwise the cue is missing, not absent:
    people_behind_count       persons standing behind the main user (smaller box, behind), counted per frame by a
                              person / head detector (H1, not built); a number in every row
    companion_box             (x0, y0, x1, y1) as fractions of width / height: a second box of similar size beside
                              the main user, from the same detector; None = no such box in that frame
    mouth_motion              change of the blendshape mouth dials (jawOpen and others, decision 16: within-window
                              change after the person's baseline); blank where the face is not seen
    shoulder_cx, shoulder_cy  midpoint of pose points 11 and 12 as fractions of width / height; blank where the body
                              is not seen
    tap_count, miss_tap_count, back_count
                              touches, touches outside a button and back navigations since the previous row: the
                              names and meanings of TouchFeatures in contract/frontend-backend.openapi.yaml, counted
                              per frame interval instead of per window; a number in every row
    first_input_delay_ms      on the frame of the first input of a screen: time from entering the screen (not in
                              the contract); blank on the other frames

Source shorthands (notes kept in the project workspace, not in this repository):
  dec section 3 = the vision owner's decision list 2026-10-10, section 3: the rule table of the three situation
                  tags (00_planning/decisions/decisions_2026-10-10.md)
  sem section N = semantic-layer design note v1.1, 2026-10-11 (00_planning/design/semantic_layer_v1_2026-10-11.md)
  research/33   = situation-recognition note, section 1 (the observation tags these events implement)
  doc 28, [D1]  = as in features.py
"""
from __future__ import annotations

import math
import numbers
import statistics
from dataclasses import dataclass, fields

SEEN = "보임"   # = features.SEEN (doc 28 sections 1, 3); not imported because features loads OpenCV
YAW_POSITIVE_SIDE, YAW_NEGATIVE_SIDE = "right", "left"   # README 'CSV 열': yaw + = 화면 오른쪽 (from the MediaPipe
                                                         # geometry, fixed by a test; not checked on a real head turn)
SMOOTHED_NUM_FACES = 1   # the Face Landmarker smooths only with num_faces=1 [D1]; app/inference/vision.py runs 1

KINDS = ("look_back", "yaw_sweep_offscreen", "people_behind", "companion_present", "mouth_moving",
         "dwell_no_touch", "touch_miss", "back_navigation_loop", "first_input_delayed")
COUNT_COLUMNS = ("people_behind_count", "tap_count", "miss_tap_count", "back_count")     # a number in every row
VALUE_COLUMNS = ("companion_box", "mouth_motion", "shoulder_cx", "shoulder_cy",          # the key in every row,
                 "first_input_delay_ms")                                                 # blank where not seen
COUNT_FIELDS = ("look_back_min_count", "sweep_min_count", "back_loop_min_count", "min_events")


@dataclass(frozen=True)
class PilotParams:
    """The pilot values ([파일럿]) of the events and the situation rules - none has a default.

    No standard or measured data gives any of them (dec section 3), so they come from the distribution in the team's
    self-recording (decision 20-1) and every caller sets each one. Tests use values made for their synthetic frames.
    """
    window_s: float               # state window (s); also the expiry window: an event older than this drops out
    gap_s: float                  # flagged frames at most this far apart stay one event across unflagged frames
                                  # (doc 28 section 3: '잠깐 끊김을 거르는 시간 창')
    offscreen_yaw_deg: float      # |yaw| from which the face points off the screen; a head turn starts and ends here.
                                  # Smaller yaw = reading the menu (dec section 3, looking_around exclusion)
    shoulder_vis_min: float       # shoulder visibility from which the shoulders 'stay' while the face points are lost
    look_back_min_count: int      # look_backs in a window for 'repeated' (looking_back_with_people_behind)
    sweep_min_count: int          # off-screen head turns in a window (looking_around)
    stay_min_s: float             # a person behind or beside counts after staying this long; shorter = passing by
    dwell_min_s: float            # a stretch without touches for 'dwell without touching'
    mouth_motion_min: float       # mouth_motion from which a frame counts as mouth moving
    body_still_max: float         # largest spread of the shoulder midpoint (fraction of width or height): 'body still'
    back_loop_min_count: int      # back navigations in a window for back_navigation_loop
    first_input_delay_min_ms: float   # first-input delay for first_input_delayed
    min_events: int               # k: a tag with fewer supporting events is 'unknown' (sem section 4, check rule 2)
    face_visible_min: float       # face-visible ratio below which the cues that need the face are missing
    track_conf_min: float         # body-tracked ratio below which the window counts as a sensor failure ('unknown')

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if (isinstance(value, bool) or not isinstance(value, numbers.Real) or not math.isfinite(value)
                    or value < 0):
                raise ValueError(f"PilotParams.{f.name} must be a finite number >= 0, got {value!r}")
            if f.name in COUNT_FIELDS and not isinstance(value, numbers.Integral):
                raise ValueError(f"PilotParams.{f.name} is a count and must be an integer, got {value!r}")


def _num(row: dict, key: str):
    """The row's value as a finite float, or None (no key, None, blank, NaN, not a number)."""
    value = row.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _count(value: float):
    """A count as an int when it is whole (counts arrive as floats from _num)."""
    return int(value) if float(value).is_integer() else value


def _t(row: dict) -> float:
    return float(row["t_s"])


def _face(row: dict) -> bool:
    return row.get("face_state") == SEEN


def _body(row: dict) -> bool:
    return row.get("body_state") == SEEN


def _side(yaw: float):
    """Image side the face turns toward (README sign of yaw); None for yaw 0."""
    return YAW_POSITIVE_SIDE if yaw > 0 else YAW_NEGATIVE_SIDE if yaw < 0 else None


def _box(row: dict):
    """companion_box of the row as four floats, or None when the frame has no such box."""
    value = row.get("companion_box")
    if value is None or value == "" or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        box = tuple(float(v) for v in value)
    except (TypeError, ValueError):
        box = ()
    if len(box) != 4 or not all(math.isfinite(v) for v in box):
        raise ValueError(f"companion_box of frame {row.get('frame_idx')!r} is not (x0, y0, x1, y1): {value!r}")
    return box


def measured_columns(rows: list) -> frozenset:
    """The optional columns measured over these rows: every row carries the column (a count needs a number)."""
    if not rows:
        return frozenset()
    counts = {c for c in COUNT_COLUMNS if all(_num(r, c) is not None for r in rows)}
    values = {c for c in VALUE_COLUMNS if all(c in r for r in rows)}
    return frozenset(counts | values)


def _event(kind: str, rows: list, frames: list, obs: dict) -> dict:
    first, last = rows[frames[0]], rows[frames[-1]]
    return {"event_id": f"{kind}@{first['frame_idx']}", "kind": kind, "t_start": _t(first), "t_end": _t(last),
            "obs": obs, "source_frames": [rows[i]["frame_idx"] for i in frames]}


def _runs(rows: list, flags: list, gap_s: float, breaks: list | None = None) -> list:
    """Indices of the flagged frames grouped into runs. Adjacent flagged frames join; two flagged frames with
    unflagged frames between them join when they are at most gap_s apart and no break frame lies between."""
    runs, current, broken = [], None, False
    for i, flag in enumerate(flags):
        if breaks is not None and breaks[i]:
            broken = True
        if not flag:
            continue
        if current and (current[-1] == i - 1 or (not broken and _t(rows[i]) - _t(rows[current[-1]]) <= gap_s)):
            current.append(i)
        else:
            if current:
                runs.append(current)
            current = [i]
        broken = False
    if current:
        runs.append(current)
    return runs


def _run_events(kind, rows, flags, gap_s, min_s, obs, breaks=None) -> list:
    """One event per run lasting at least min_s (None = any length); obs(run, duration_s) gives its observations."""
    events = []
    for run in _runs(rows, flags, gap_s, breaks):
        duration = _t(rows[run[-1]]) - _t(rows[run[0]])
        if min_s is None or duration >= min_s:
            events.append(_event(kind, rows, run, obs(run, duration)))
    return events


# --- head turns: look_back and yaw_sweep_offscreen ----------------------------------------------------------------
FACING, OFF, LOST, UNTRACKED = "facing", "off", "lost", "untracked"


def _turn_class(row: dict, p: PilotParams) -> str:
    """facing = face seen inside the off-screen yaw; off = face seen beyond it; lost = face points lost while the
    shoulders stay (the body tracker still sees them); untracked = none of these (also a face without a yaw)."""
    if _face(row):
        yaw = _num(row, "yaw_deg")
        if yaw is None:
            return UNTRACKED
        return OFF if abs(yaw) >= p.offscreen_yaw_deg else FACING
    shoulders = _num(row, "pose_vis_shoulders")
    if _body(row) and shoulders is not None and shoulders >= p.shoulder_vis_min:
        return LOST
    return UNTRACKED


def _head_turns(rows: list, p: PilotParams) -> list:
    """One event per head turn: it starts when the visible face passes the off-screen yaw right after facing the
    screen and ends when the face is back inside it. A turn with face-lost frames is a look_back (research/33:
    'yaw가 커지다 얼굴 점이 사라지고 어깨 점은 남음 -> 얼굴이 돌아오면 1회'); a turn with the face seen throughout is a
    yaw_sweep_offscreen. A turn that does not come back inside the window, or loses all tracking for longer than
    gap_s, gives no event; so does a face that disappears without first turning (an occlusion, not a turn)."""
    classes = [_turn_class(r, p) for r in rows]
    events, turn, last = [], None, None
    for i, c in enumerate(classes):
        if c == UNTRACKED:
            continue
        joined = last is not None and (last == i - 1 or _t(rows[i]) - _t(rows[last]) <= p.gap_s)
        if turn is not None and not joined:
            turn = None                                      # tracking gone too long: no return seen
        if turn is None:
            if c == OFF and joined and classes[last] == FACING:
                turn = [i]                                   # onset
        elif c == FACING:
            events.append(_turn_event(rows, classes, turn + [i]))   # return
            turn = None
        else:
            turn.append(i)
        last = i
    return events


def _turn_event(rows: list, classes: list, frames: list) -> dict:
    off = [i for i in frames if classes[i] == OFF]
    lost = [i for i in frames if classes[i] == LOST]
    yaw = _num(rows[max(off, key=lambda i: abs(_num(rows[i], "yaw_deg")))], "yaw_deg")   # largest visible yaw
    back = _t(rows[frames[-1]])
    obs = {"yaw_deg": yaw, "side": _side(yaw)}
    if lost:
        obs["face_lost_s"] = back - _t(rows[lost[0]])                                 # loss -> return
        obs["pose_vis_shoulders"] = min(_num(rows[i], "pose_vis_shoulders") for i in lost)
        return _event("look_back", rows, frames, obs)
    obs["offscreen_s"] = back - _t(rows[frames[0]])
    return _event("yaw_sweep_offscreen", rows, frames, obs)


# --- all events of a window ----------------------------------------------------------------------------------------
def detect_events(rows: list, params: PilotParams, *, landmarker_num_faces: int) -> list:
    """Events of these rows (one window, in time order), sorted by start time.

    landmarker_num_faces = the num_faces setting of the Face Landmarker that produced the face columns. With more
    than one face it does not smooth [D1], so mouth_motion is not turned into events (dec section 3,
    consulting_companion exclusion: jitter is not counted as mouth motion)."""
    p = params
    measured = measured_columns(rows)
    events = _head_turns(rows, p)

    if "people_behind_count" in measured:
        counts = [_num(r, "people_behind_count") for r in rows]
        events += _run_events("people_behind", rows, [c > 0 for c in counts], p.gap_s, p.stay_min_s,
                              lambda run, s: {"people_behind_count": _count(max(counts[i] for i in run)),
                                              "stay_s": s})

    if "companion_box" in measured:
        boxes = [_box(r) for r in rows]
        face_x = [x for x in (_num(r, "face_cx") for r in rows if _face(r)) if x is not None]
        user_cx = statistics.median(face_x) if face_x else None      # the main user's face position in the window

        def companion_obs(run, s):
            cx = statistics.median((boxes[i][0] + boxes[i][2]) / 2 for i in run)
            side = (None if user_cx is None or cx == user_cx
                    else YAW_POSITIVE_SIDE if cx > user_cx else YAW_NEGATIVE_SIDE)   # image side, as for yaw
            return {"companion_cx": cx, "side": side, "stay_s": s}

        events += _run_events("companion_present", rows, [b is not None for b in boxes], p.gap_s, p.stay_min_s,
                              companion_obs)

    if "mouth_motion" in measured and landmarker_num_faces == SMOOTHED_NUM_FACES:
        motion = [_num(r, "mouth_motion") if _face(r) else None for r in rows]
        events += _run_events("mouth_moving", rows, [m is not None and m >= p.mouth_motion_min for m in motion],
                              p.gap_s, None,
                              lambda run, s: {"mouth_motion": max(motion[i] for i in run), "moving_s": s})

    if "tap_count" in measured:
        taps = [_num(r, "tap_count") > 0 for r in rows]
        present = [_face(r) or _body(r) for r in rows]
        events += _run_events("dwell_no_touch", rows, [pr and not tap for pr, tap in zip(present, taps)],
                              p.gap_s, p.dwell_min_s, lambda run, s: {"no_touch_s": s}, breaks=taps)

    if "miss_tap_count" in measured:
        misses = [_num(r, "miss_tap_count") for r in rows]
        events += _run_events("touch_miss", rows, [m > 0 for m in misses], p.gap_s, None,
                              lambda run, s: {"miss_tap_count": _count(sum(misses[i] for i in run))})

    if "back_count" in measured:
        backs = [i for i, r in enumerate(rows) if _num(r, "back_count") > 0]
        total = sum(_num(rows[i], "back_count") for i in backs)
        if backs and total >= p.back_loop_min_count:
            events.append(_event("back_navigation_loop", rows, backs, {"back_count": _count(total)}))

    if "first_input_delay_ms" in measured:
        for i, r in enumerate(rows):
            delay = _num(r, "first_input_delay_ms")
            if delay is not None and delay >= p.first_input_delay_min_ms:
                events.append(_event("first_input_delayed", rows, [i], {"first_input_delay_ms": delay}))

    return sorted(events, key=lambda e: (e["t_start"], e["kind"]))


# --- what the rules read for one window --------------------------------------------------------------------------
@dataclass(frozen=True)
class Cues:
    """The events of one window and its window-level checks - everything the situation rules read."""
    events: list
    face_visible_ratio: float | None   # frames with the face seen / frames (None: no frames)
    track_conf: float | None           # frames with the body tracked / frames: MediaPipe gave a pose, i.e. its own
                                       # confidence passed its pass mark (library default) (None: no frames)
    measured: frozenset                # optional columns carried by every row (measured_columns)
    face_ok: bool                      # face_visible_ratio >= face_visible_min: the cues that need the face count
    mouth_usable: bool                 # mouth_motion measured, smoothed landmarker [D1], face_ok
    any_tap: bool | None               # a touch in the window (None: no touch log)
    body_still: bool | None            # shoulder midpoint spread <= body_still_max (None: not measurable)

    def of(self, *kinds: str) -> list:
        return [e for e in self.events if e["kind"] in kinds]


def _body_still(rows: list, p: PilotParams):
    points = [(_num(r, "shoulder_cx"), _num(r, "shoulder_cy")) for r in rows if _body(r)]
    points = [(x, y) for x, y in points if x is not None and y is not None]
    if not points:
        return None
    xs, ys = zip(*points)
    return max(max(xs) - min(xs), max(ys) - min(ys)) <= p.body_still_max


def observe_window(rows: list, params: PilotParams, *, landmarker_num_faces: int) -> Cues:
    """Events and window-level checks of the rows of one window."""
    rows = sorted(rows, key=_t)
    n = len(rows)
    measured = measured_columns(rows)
    face_ratio = sum(map(_face, rows)) / n if n else None
    face_ok = face_ratio is not None and face_ratio >= params.face_visible_min
    return Cues(
        events=detect_events(rows, params, landmarker_num_faces=landmarker_num_faces),
        face_visible_ratio=face_ratio,
        track_conf=sum(map(_body, rows)) / n if n else None,
        measured=measured,
        face_ok=face_ok,
        mouth_usable="mouth_motion" in measured and landmarker_num_faces == SMOOTHED_NUM_FACES and face_ok,
        any_tap=any(_num(r, "tap_count") > 0 for r in rows) if "tap_count" in measured else None,
        body_still=_body_still(rows, params) if {"shoulder_cx", "shoulder_cy"} <= measured else None)
