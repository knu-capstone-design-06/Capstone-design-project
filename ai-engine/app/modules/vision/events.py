"""사건 (events) layer: observation rows -> events, the cues the situation rules combine.

Layers: 관측값 features.py -> 사건 this file -> 상황 situation.py. Plain Python: no numpy, OpenCV or MediaPipe.

An event is one thing that happened, with the observations that show it:
    {event_id, kind, t_start, t_end, obs: {name: value}, source_frames}
Observations with one cause make ONE event (sem section 4, '근거 중복'): a head turn whose yaw grows, whose face
points are then lost while the shoulders stay, and which comes back is one look_back - not a yaw event plus a
face-loss event. event_id = '<kind>@<frame_idx of the event's first frame>'. source_frames = the frames whose
observations the event used.

Windows (dec section 3: '전부 같은 창 안'; sem section 4, rule 1: '시간 범위(창 안)'): an event is evidence for a
window only when all of its observation rows lie inside it. Head turns are found on every row up to the window end -
the rows before the window are detection context only, so a turn whose facing frame lies just before the window keeps
its onset - and a turn counts when its rows (onset to return) are all inside. The other events (a person behind, a
companion, the yaw toward it, mouth motion, dwell, misses) are found on the rows
inside the window, so a state that began earlier gives its part inside the window, and its length conditions
(stay_min_s, dwell_min_s) are judged on that part. Nothing after the window end is used, so a replay gives what the
kiosk would have given. Finding every event again for each window is for offline replay; a live runner needs an
incremental version.

Every window, count, angle and floor is a pilot value ([파일럿]): PilotParams has no defaults and this file sets
none (dec section 3: '모든 창 길이 · 횟수 · 각도는 [파일럿]', set from the distribution in the team's self-recording).

Input: one dict per frame.
- columns features.py writes: frame_idx, t_s, face_state, body_state, yaw_deg, face_cx, pose_vis_shoulders
- optional columns that no code in this repository writes yet. Events come from wherever a column has values; a cue
  seen there counts even if other rows lack the column. That a cue is absent is concluded only when every row that
  should carry it does (otherwise the cue is missing):
    people_behind_count       persons standing behind the main user (smaller box, behind), counted per frame by a
                              person / head detector (H1, not built); a whole number >= 0 in every row
    companion_box             (x0, y0, x1, y1) as fractions of width / height: a second box of similar size beside
                              the main user, from the same detector; None = no such box in that frame
    mouth_motion              change of the blendshape mouth dials (jawOpen and others, decision list 2026-10-10 §16: within-window
                              change after the person's baseline); blank where the face is not seen
    shoulder_cx, shoulder_cy  midpoint of pose points 11 and 12 as fractions of width / height; blank where the body
                              is not seen
    tap_count, miss_tap_count touches and touches outside a button in the interval that ends at the row's time
                              (since the previous row): the names and meanings of TouchFeatures in
                              contract/frontend-backend.openapi.yaml (integer, minimum 0), counted per frame interval
                              instead of the API's 1-3 s window (how the two aggregations map is a contract matter);
                              a row belongs to a window when its time does, so a touch in the last interval before
                              the window start can be counted inside it (raw touch times would remove this)
  A count column with a value that is not a whole number >= 0 is an error (the contract's type), not a missing value.
  The two touch columns take whole numbers or digit strings only (the contract's integer); people_behind_count also
  takes an integral float.

Source shorthands (notes kept in the project workspace, not in this repository; the README quotes the parts used):
  dec section 3 = the vision owner's decision list 2026-10-10, section 3: the rule table of the three situation
                  tags (00_planning/decisions/decisions_2026-10-10.md)
  sem section N = semantic-layer design note v1.1, 2026-10-11 (00_planning/design/semantic_layer_v1_2026-10-11.md)
  research/33   = situation-recognition note, section 1 (the observation tags these events implement)
  doc 28, [D1]  = as in features.py
"""
from __future__ import annotations

import bisect
import math
import numbers
import statistics
from dataclasses import dataclass, fields

SEEN = "보임"   # = features.SEEN (doc 28 sections 1, 3); not imported because features loads OpenCV
YAW_POSITIVE_SIDE, YAW_NEGATIVE_SIDE = "right", "left"   # README 'CSV 열': yaw + = 화면 오른쪽 (from the MediaPipe
                                                         # geometry, fixed by a test; not checked on a real head turn)
SMOOTHED_NUM_FACES = 1   # the Face Landmarker smooths only with num_faces=1 [D1]; app/inference/vision.py runs 1

KINDS = ("look_back", "yaw_sweep_offscreen", "people_behind", "companion_present", "yaw_toward_companion",
         "mouth_moving", "dwell_no_touch", "touch_miss")
COUNT_COLUMNS = ("people_behind_count", "tap_count", "miss_tap_count")   # measured: a count in every row
TOUCH_COLUMNS = ("tap_count", "miss_tap_count")   # TouchFeatures integers: whole numbers or digit strings only
KEY_COLUMNS = ("companion_box",)    # measured: the key in every row (None / blank = nothing)
COUNT_FIELDS = ("look_back_min_count", "sweep_min_count", "min_events")
RATIO_FIELDS = ("shoulder_vis_min", "face_visible_min", "track_conf_min")   # compared with shares / visibility in 0..1
POSITIVE_FIELDS = ("window_s", "gap_s")    # 0 makes an empty window or splits every event into single frames


@dataclass(frozen=True)
class PilotParams:
    """The pilot values ([파일럿]) of the events and the situation rules - none has a default.

    No standard or measured data gives any of them (dec section 3), so they come from the distribution in the team's
    self-recording (decision 20-1) and every caller sets each one. Tests use values made for their synthetic frames.
    The three counts must be whole numbers of at least 1: a count of 0 would let a rule pass without the observation
    the decision table names (or name a tag without evidence); the rules also check that the cue is there at all.
    The three floors compared with a share of frames must be at most 1, and the two lengths of time above 0.
    """
    window_s: float               # state window (s); also the expiry window: an event with a row before the window
                                  # is no longer evidence
    gap_s: float                  # longest time between two observations that still belong to one event (doc 28
                                  # section 3: '잠깐 끊김을 거르는 시간 창'); also between adjacent rows, so it has to
                                  # be at least the normal frame interval. A longer gap ends the event
    offscreen_yaw_deg: float      # |yaw| from which the face points off the screen: head turns start and end here.
                                  # Smaller yaw = reading the menu (dec section 3, looking_around exclusion)
    shoulder_vis_min: float       # shoulder visibility from which the shoulders 'stay' while the face points are lost
    look_back_min_count: int      # look_backs in a window for 'repeated' (looking_back_with_people_behind)
    sweep_min_count: int          # off-screen head turns in a window (looking_around)
    stay_min_s: float             # a person behind counts after staying this long; shorter = passing by
                                  # (dec section 3: '멈춰 선 사람만')
    dwell_min_s: float            # a stretch without touches for 'dwell without touching'
    mouth_motion_min: float       # mouth_motion from which a frame counts as mouth moving
    body_still_max: float         # largest spread of the shoulder midpoint on either axis (fraction of width or
                                  # height): 'body still'
    min_events: int               # k: a tag with fewer supporting events is 'unknown' (sem section 4, check rule 2)
    face_visible_min: float       # face-visible ratio below which the cues that need the face are missing
    track_conf_min: float         # body-tracked ratio below which the window counts as a sensor failure ('unknown')

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if not is_number(value) or value < 0:
                raise ValueError(f"PilotParams.{f.name} must be a finite number >= 0, got {value!r}")
            if f.name in COUNT_FIELDS and (not isinstance(value, numbers.Integral) or value < 1):
                raise ValueError(f"PilotParams.{f.name} is a count of events and must be a whole number >= 1, "
                                 f"got {value!r}")
            if f.name in RATIO_FIELDS and value > 1:
                raise ValueError(f"PilotParams.{f.name} is compared with a ratio from 0 to 1 and must be at most 1, "
                                 f"got {value!r}")
            if f.name in POSITIVE_FIELDS and value == 0:
                raise ValueError(f"PilotParams.{f.name} is a length of time and must be greater than 0, got {value!r}")


def is_number(value) -> bool:
    """A finite real number (not a bool)."""
    return isinstance(value, numbers.Real) and not isinstance(value, bool) and math.isfinite(value)


def is_ratio(value) -> bool:
    """A share of frames: a finite number from 0 to 1."""
    return is_number(value) and 0 <= value <= 1


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


def _count_value(row: dict, key: str):
    """A count column of the row: None when blank (no key, None, "", NaN); otherwise it must be a whole number >= 0,
    as the contract's TouchFeatures counts are (integer, minimum 0) - anything else is an error. The touch columns
    take only an integer or a digit string (a CSV cell), not 1.0 or "1.0" (the contract's strict integer, as the
    backend validates it); people_behind_count also takes an integral float."""
    value = row.get(key)
    if value is None or value == "" or (isinstance(value, float) and math.isnan(value)):
        return None
    if key in TOUCH_COLUMNS:
        if isinstance(value, bool) or not (
            isinstance(value, numbers.Integral)
            or (isinstance(value, str) and value.isascii() and value.isdigit())
        ) or int(value) < 0:
            raise ValueError(f"{key} of frame {row.get('frame_idx')!r} is not a whole number >= 0: {value!r}")
        return int(value)
    number = _num(row, key)
    if number is None or number < 0 or not number.is_integer():
        raise ValueError(f"{key} of frame {row.get('frame_idx')!r} is not a whole number >= 0: {value!r}")
    return int(number)


def _t(row: dict) -> float:
    return float(row["t_s"])


def _face(row: dict) -> bool:
    return row.get("face_state") == SEEN


def _body(row: dict) -> bool:
    return row.get("body_state") == SEEN


def _side(value: float):
    """Image side of a signed value: yaw (README sign) or an x offset; None for 0."""
    return YAW_POSITIVE_SIDE if value > 0 else YAW_NEGATIVE_SIDE if value < 0 else None


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
    """The optional columns every one of these rows carries: counts need a count in every row; companion_box the
    key in every row. Only then can the absence of their cue be concluded."""
    if not rows:
        return frozenset()
    measured = {c for c in COUNT_COLUMNS if all(_count_value(r, c) is not None for r in rows)}
    measured |= {c for c in KEY_COLUMNS if all(c in r for r in rows)}
    return frozenset(measured)


def _event(kind: str, rows: list, frames: list, obs: dict) -> dict:
    first, last = rows[frames[0]], rows[frames[-1]]
    return {"event_id": f"{kind}@{first['frame_idx']}", "kind": kind, "t_start": _t(first), "t_end": _t(last),
            "obs": obs, "source_frames": [rows[i]["frame_idx"] for i in frames]}


def _runs(rows: list, flags: list, gap_s: float, breaks: list | None = None) -> list:
    """Indices of the flagged frames grouped into runs. A flagged frame joins the run of the previous flagged frame
    when their times (t_s) are at most gap_s apart and no break frame lies between - adjacent rows included, so a
    long gap in the record ends the run."""
    runs, current, broken = [], None, False
    for i, flag in enumerate(flags):
        if breaks is not None and breaks[i]:
            broken = True
        if not flag:
            continue
        if current and not broken and _t(rows[i]) - _t(rows[current[-1]]) <= gap_s:
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


def _hides_head(stretch: list) -> bool:
    """Whether a stretch between two tracked frames hides what the head did: no rows at all (a gap in the record), a
    row with neither face nor body, or a row whose yaw or shoulder value is missing. Shoulders seen below
    shoulder_vis_min hide nothing: they did not stay, so it was no look-back."""
    if not stretch:
        return True
    return any((not _face(r) and not _body(r))
               or (_face(r) and _num(r, "yaw_deg") is None)
               or (not _face(r) and _body(r) and _num(r, "pose_vis_shoulders") is None) for r in stretch)


def _head_turn_scan(rows: list, p: PilotParams) -> tuple:
    """(events, onsets of broken turns). One event per head turn: it starts when the visible face passes the
    off-screen yaw right after facing the screen and ends when the face is back inside it. A turn with face-lost
    frames is a look_back (research/33: 'yaw가 커지다 얼굴 점이 사라지고 어깨 점은 남음 -> 얼굴이 돌아오면 1회'); a turn
    with the face seen throughout is a yaw_sweep_offscreen. Two tracked frames more than gap_s apart (time, adjacent
    rows too) break the turn: no event, and when the stretch between them hides the head (_hides_head) the turn's
    onset time is returned - whether it was a look_back cannot be told. A turn that has not come back yet gives no
    event; nor does a face that disappears without first turning (an occlusion, not a turn)."""
    classes = [_turn_class(r, p) for r in rows]
    events, broken, turn, last = [], [], None, None
    for i, c in enumerate(classes):
        if c == UNTRACKED:
            continue
        joined = last is not None and _t(rows[i]) - _t(rows[last]) <= p.gap_s
        if turn is not None and not joined:
            if _hides_head(rows[last + 1:i]):
                broken.append(_t(rows[turn[0]]))
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
    if turn is not None and _t(rows[-1]) - _t(rows[last]) > p.gap_s and _hides_head(rows[last + 1:]):
        broken.append(_t(rows[turn[0]]))                     # lost at the end for longer than gap_s
    return events, broken


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


# --- companion: present, and the main user's yaw toward it ---------------------------------------------------------
def companion_sides(rows: list, p: PilotParams) -> tuple:
    """(sides, undetermined), per row in time order. sides: the image side of the companion box relative to the main
    user's face at that frame, or, when the frame lacks one of the two, at the nearest frame at most gap_s away that
    has both; None when there is none (positions from longer ago never decide a frame). undetermined: no side, yet a
    companion may be there - a box, or a row without the companion_box column, lies within gap_s."""
    times = [_t(r) for r in rows]
    boxes = [_box(r) for r in rows]
    own = []
    for r, box in zip(rows, boxes):
        user = _num(r, "face_cx") if _face(r) else None
        own.append(None if box is None or user is None else _side((box[0] + box[2]) / 2 - user))
    known = [i for i, side in enumerate(own) if side is not None]
    known_t = [times[i] for i in known]
    maybe_t = [times[i] for i, r in enumerate(rows) if boxes[i] is not None or "companion_box" not in r]
    sides, undetermined = [], []
    for i, t in enumerate(times):
        side = own[i]
        if side is None:
            k = bisect.bisect_left(known_t, t)
            near = [j for j in (k - 1, k) if 0 <= j < len(known) and abs(known_t[j] - t) <= p.gap_s]
            side = own[known[min(near, key=lambda j: abs(known_t[j] - t))]] if near else None
        sides.append(side)
        k = bisect.bisect_left(maybe_t, t - p.gap_s)
        undetermined.append(side is None and k < len(maybe_t) and maybe_t[k] <= t + p.gap_s)
    return sides, undetermined


def _companion_events(rows: list, sides: list, p: PilotParams) -> list:
    """companion_present: the frames with a companion box (no minimum stay: the decision table asks none).
    yaw_toward_companion: the face seen with its yaw on the companion's side at that frame (dec section 3: '주
    사용자 yaw가 일행 쪽'; the sign against the companion's position, any size), held over frames at most gap_s apart.
    A turn toward the companion that comes back is also a yaw_sweep_offscreen; that event is looking_around's cue,
    this one consulting_companion's. sides = companion_sides(...)[0] for these rows."""
    boxes = [_box(r) for r in rows]
    companions = _run_events("companion_present", rows, [b is not None for b in boxes], p.gap_s, None,
                             lambda run, s: {"companion_cx": statistics.median((boxes[i][0] + boxes[i][2]) / 2
                                                                               for i in run),
                                             "present_s": s})
    yaws = [_num(r, "yaw_deg") if _face(r) else None for r in rows]
    toward = [y is not None and side is not None and _side(y) == side for y, side in zip(yaws, sides)]

    def toward_obs(run, s):
        yaw = max((yaws[i] for i in run), key=abs)
        return {"yaw_deg": yaw, "side": _side(yaw), "toward_s": s}

    return companions + _run_events("yaw_toward_companion", rows, toward, p.gap_s, None, toward_obs)


# --- all events -----------------------------------------------------------------------------------------------------
def _split(rows: list, window: tuple | None) -> tuple:
    """(rows up to the window end in time order, index of the first row inside the window)."""
    t0, t1 = window if window is not None else (-math.inf, math.inf)
    rows = sorted((r for r in rows if _t(r) <= t1), key=_t)
    return rows, next((i for i, r in enumerate(rows) if _t(r) >= t0), len(rows))


def detect_events(rows: list, params: PilotParams, *, landmarker_num_faces: int, window: tuple | None = None) -> list:
    """Events of these rows, sorted by start time. With window = (t0, t1): rows after t1 are dropped first, head
    turns use the rows before t0 as context and count when their rows all lie inside, and every other event is found
    on the rows inside the window (see the module docstring). Without a window: all rows.

    landmarker_num_faces = the num_faces setting of the Face Landmarker that produced the face columns. With more
    than one face it does not smooth [D1], so mouth_motion is not turned into events (dec section 3,
    consulting_companion exclusion: jitter is not counted as mouth motion)."""
    p = params
    rows, first = _split(rows, window)
    inside = rows[first:]
    t0 = _t(inside[0]) if inside else math.inf
    events = [e for e in _head_turn_scan(rows, p)[0] if e["t_start"] >= t0]
    events += _companion_events(inside, companion_sides(rows, p)[0][first:], p)

    counts = [_count_value(r, "people_behind_count") for r in inside]
    events += _run_events("people_behind", inside, [c is not None and c > 0 for c in counts], p.gap_s, p.stay_min_s,
                          lambda run, s: {"people_behind_count": max(counts[i] for i in run), "stay_s": s})

    if landmarker_num_faces == SMOOTHED_NUM_FACES:
        motion = [_num(r, "mouth_motion") if _face(r) else None for r in inside]
        events += _run_events("mouth_moving", inside, [m is not None and m >= p.mouth_motion_min for m in motion],
                              p.gap_s, None,
                              lambda run, s: {"mouth_motion": max(motion[i] for i in run), "moving_s": s})

    taps = [_count_value(r, "tap_count") for r in inside]
    present = [_face(r) or _body(r) for r in inside]
    events += _run_events("dwell_no_touch", inside, [pr and t == 0 for pr, t in zip(present, taps)], p.gap_s,
                          p.dwell_min_s, lambda run, s: {"no_touch_s": s},
                          breaks=[t is not None and t > 0 for t in taps])

    misses = [_count_value(r, "miss_tap_count") for r in inside]
    events += _run_events("touch_miss", inside, [m is not None and m > 0 for m in misses], p.gap_s, None,
                          lambda run, s: {"miss_tap_count": sum(misses[i] for i in run)})

    return sorted(events, key=lambda e: (e["t_start"], e["kind"]))


# --- what the rules read for one window --------------------------------------------------------------------------
@dataclass(frozen=True)
class Cues:
    """The events of one window and its window-level checks - everything the situation rules read. A cue seen in
    the window counts even where a column is partly missing; that it is absent needs every row (or every frame that
    should carry it) observed, otherwise the check says so."""
    events: list
    face_visible_ratio: float | None   # frames with the face seen / frames in the window (None: no frames)
    track_conf: float | None           # frames with the body tracked / frames: MediaPipe gave a pose, i.e. its own
                                       # confidence passed its pass mark (library default) (None: no frames)
    measured: frozenset                # optional columns every row of the window carries (measured_columns)
    face_ok: bool                      # face_visible_ratio >= face_visible_min: the cues that need the face count
    yaw_ok: bool                       # a face frame in the window, and a yaw on every face frame: turns can be seen
    shoulders_ok: bool                 # a shoulder visibility on every frame with the face lost and the body seen
    turns_unresolved: bool             # a turn that started in the window was broken by a stretch hiding the head
    mouth_usable: bool                 # smoothed landmarker [D1] and face_ok: mouth motion can be read
    mouth_observed: bool               # a mouth_motion value on every face frame: 'no mouth motion' can be concluded
    companion_side_unknown: bool       # a face frame with a nonzero yaw where a companion may be but its side is not
                                       # known: 'no yaw toward the companion' cannot be concluded
    any_tap: bool | None               # a touch on a row of the window; False needs a count on every row
    body_still: bool | None            # False: the shoulder midpoint spread beyond body_still_max on an axis where it
                                       # was seen; True: within it on both axes, observed on every body frame (two
                                       # or more); None otherwise

    def of(self, *kinds: str) -> list:
        return [e for e in self.events if e["kind"] in kinds]


def _observed_on(rows: list, key: str, where) -> bool:
    """At least one row passes `where`, and every such row has a value for key."""
    chosen = [r for r in rows if where(r)]
    return bool(chosen) and all(_num(r, key) is not None for r in chosen)


def _body_still(rows: list, p: PilotParams):
    body = [r for r in rows if _body(r)]
    axes = [[v for v in (_num(r, key) for r in body) if v is not None] for key in ("shoulder_cx", "shoulder_cy")]
    if any(len(values) >= 2 and max(values) - min(values) > p.body_still_max for values in axes):
        return False                                         # it moved on an axis where it was seen
    if len(body) >= 2 and all(len(values) == len(body) for values in axes):
        return True                                          # still, seen on every body frame on both axes
    return None


def observe_window(rows: list, window: tuple, params: PilotParams, *, landmarker_num_faces: int) -> Cues:
    """Events and window-level checks for window = (t0, t1): rows after t1 are never read; detect_events says which
    rows each event comes from; the checks read the rows inside the window."""
    t0, t1 = window
    rows, first = _split(rows, window)
    inside = rows[first:]
    n = len(inside)
    measured = measured_columns(inside)
    face_ratio = sum(map(_face, inside)) / n if n else None
    face_ok = face_ratio is not None and face_ratio >= params.face_visible_min
    taps = [_count_value(r, "tap_count") for r in inside]
    any_tap = True if any(t is not None and t > 0 for t in taps) else (False if "tap_count" in measured else None)
    undetermined = companion_sides(rows, params)[1][first:]
    broken = _head_turn_scan(rows, params)[1]
    return Cues(
        events=detect_events(rows, params, landmarker_num_faces=landmarker_num_faces, window=window),
        face_visible_ratio=face_ratio,
        track_conf=sum(map(_body, inside)) / n if n else None,
        measured=measured,
        face_ok=face_ok,
        yaw_ok=_observed_on(inside, "yaw_deg", _face),
        shoulders_ok=all(_num(r, "pose_vis_shoulders") is not None for r in inside if _body(r) and not _face(r)),
        turns_unresolved=any(t0 <= t <= t1 for t in broken),
        mouth_usable=landmarker_num_faces == SMOOTHED_NUM_FACES and face_ok,
        mouth_observed=_observed_on(inside, "mouth_motion", _face),
        companion_side_unknown=any(u and _face(r) and (_num(r, "yaw_deg") or 0) != 0
                                   for r, u in zip(inside, undetermined)),
        any_tap=any_tap,
        body_still=_body_still(inside, params))
