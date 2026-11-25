"""사건 (events) layer: observation rows -> events, the cues the situation rules combine.

Layers: 관측값 features.py -> 사건 this file -> 상황 situation.py. Plain Python: no numpy, OpenCV or MediaPipe.

An event is one thing that happened, with the observations that show it:
    {event_id, kind, t_start, t_end, obs: {name: value}, source_frames}
Observations with one cause make ONE event (sem section 4, '근거 중복'): a head turn whose yaw grows (or whose face
points are lost straight from facing the screen) while the shoulders stay, and which comes back is one look_back - not
a yaw event plus a face-loss event. event_id = '<kind>@<frame_idx of the event's first frame>'. source_frames = the frames whose
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

The scene tags of situation.py (seated height, face approach, user change, nothing seen, aid use; 2026-11-22) read a second,
separate set of measurement events (observe_scene, SCENE_KINDS); they do not change the events above.

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
    min_events: int               # k: a tag with fewer supporting events is 'unknown' (sem section 4, check rule 2);
                                  # situation.phone_use reuses it as the number of segment_s segments with the phone
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


def _head_turn_scan(rows: list, p: PilotParams, baseline_s: float | None = None) -> tuple:
    """(events, onsets of broken turns). One event per head turn. It starts right after a frame facing the screen,
    on either of two paths: the visible face passes the off-screen yaw (OFF), or the face points are lost while the
    shoulders stay (LOST: body seen, shoulder visibility at least shoulder_vis_min). It ends when the face is back
    inside the off-screen yaw. The second path follows the decision table's look-back (dec section 3: '고개 방향 변화와
    얼굴 점의 소실, 어깨 점의 유지 및 복귀를 함께 읽는다'): a head turned far enough loses the face points before any
    yaw beyond offscreen_yaw_deg is seen. It adds no value: LOST, the return and gap_s are the yaw path's own. A turn
    on this path that never shows an off-screen yaw counts only when the face stays lost for longer than gap_s (from
    the first lost frame to the return): a shorter loss is the brief break gap_s bridges (doc 28 section 3: '잠깐 끊김을
    거르는 시간 창'; gap_s is a [파일럿] value of the bundle), not a turn. A turn
    with face-lost frames is a look_back (research/33: 'yaw가 커지다 얼굴 점이 사라지고 어깨 점은 남음 -> 얼굴이
    돌아오면 1회'); a turn with the face seen throughout is a yaw_sweep_offscreen. Two tracked frames more than gap_s
    apart (time, adjacent rows too) break the turn: no event, and when the stretch between them hides the head
    (_hides_head) the turn's onset time is returned - whether it was a look_back cannot be told. A turn that has not
    come back yet gives no event; nor does a face lost together with the body or the shoulders (UNTRACKED: no
    onset). baseline_s: see _loss_context."""
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
            if c in (OFF, LOST) and joined and classes[last] == FACING:
                turn = [i]                                   # onset: yaw path (OFF) or face-lost path (LOST)
        elif c == FACING:                                    # return
            event = _turn_event(rows, classes, turn + [i], baseline_s)
            if event["obs"]["yaw_deg"] is not None or event["obs"]["face_lost_s"] > p.gap_s:
                events.append(event)                         # (a face-lost-only turn: longer than gap_s)
            turn = None
        else:
            turn.append(i)
        last = i
    if turn is not None and _t(rows[-1]) - _t(rows[last]) > p.gap_s and _hides_head(rows[last + 1:]):
        broken.append(_t(rows[turn[0]]))                     # lost at the end for longer than gap_s
    return events, broken


def _loss_context(rows: list, classes: list, frames: list, lost: list, baseline_s: float | None) -> dict:
    """Context of a face-lost turn, recorded so that a look-back can be told from looking down or a covered face
    without a value here: pre_loss_yaw_deg / pre_loss_pitch_deg = the median yaw / pitch of the facing frames in the
    baseline_s seconds before the turn's first frame (the caller's per-person baseline window: the chain passes
    params.mouth_baseline_s; None leaves both empty, as does a window without such frames or values),
    loss_duration_s = first to last face-lost frame of the turn (face_lost_s runs to the return), shoulder_vis_mean =
    the mean shoulder visibility over the face-lost frames."""
    before = []
    if baseline_s is not None:
        onset = _t(rows[frames[0]])
        before = [r for r, c in zip(rows[:frames[0]], classes[:frames[0]])
                  if c == FACING and _t(r) >= onset - baseline_s]

    def median(key):
        values = [v for v in (_num(r, key) for r in before) if v is not None]
        return statistics.median(values) if values else None
    return {"pre_loss_yaw_deg": median("yaw_deg"), "pre_loss_pitch_deg": median("pitch_deg"),
            "loss_duration_s": _t(rows[lost[-1]]) - _t(rows[lost[0]]),
            "shoulder_vis_mean": statistics.fmean(_num(rows[i], "pose_vis_shoulders") for i in lost)}


def _turn_event(rows: list, classes: list, frames: list, baseline_s: float | None = None) -> dict:
    off = [i for i in frames if classes[i] == OFF]
    lost = [i for i in frames if classes[i] == LOST]
    # largest visible yaw; None on the face-lost path when no off-screen yaw was seen (then the side is not known)
    yaw = _num(rows[max(off, key=lambda i: abs(_num(rows[i], "yaw_deg")))], "yaw_deg") if off else None
    back = _t(rows[frames[-1]])
    obs = {"yaw_deg": yaw, "side": None if yaw is None else _side(yaw)}
    if lost:
        obs["face_lost_s"] = back - _t(rows[lost[0]])                                 # loss -> return
        obs["pose_vis_shoulders"] = min(_num(rows[i], "pose_vis_shoulders") for i in lost)
        obs.update(_loss_context(rows, classes, frames, lost, baseline_s))
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


def _companion_present(rows: list, p: PilotParams) -> list:
    """companion_present: the frames with a companion box (no minimum stay: the decision table asks none). A scene
    cue: it reads every row of the window, also across a change of user."""
    boxes = [_box(r) for r in rows]
    return _run_events("companion_present", rows, [b is not None for b in boxes], p.gap_s, None,
                       lambda run, s: {"companion_cx": statistics.median((boxes[i][0] + boxes[i][2]) / 2
                                                                         for i in run),
                                       "present_s": s})


def _yaw_toward_companion(rows: list, sides: list, p: PilotParams) -> list:
    """yaw_toward_companion: the face seen with its yaw on the companion's side at that frame (dec section 3: '주
    사용자 yaw가 일행 쪽'; the sign against the companion's position, any size), held over frames at most gap_s apart.
    A turn toward the companion that comes back is also a yaw_sweep_offscreen; that event is looking_around's cue,
    this one consulting_companion's. rows = the main user's rows (detect_events), sides = companion_sides(...)[0] for
    them."""
    yaws = [_num(r, "yaw_deg") if _face(r) else None for r in rows]
    toward = [y is not None and side is not None and _side(y) == side for y, side in zip(yaws, sides)]

    def toward_obs(run, s):
        yaw = max((yaws[i] for i in run), key=abs)
        return {"yaw_deg": yaw, "side": _side(yaw), "toward_s": s}

    return _run_events("yaw_toward_companion", rows, toward, p.gap_s, None, toward_obs)


# --- all events -----------------------------------------------------------------------------------------------------
def _split(rows: list, window: tuple | None) -> tuple:
    """(rows up to the window end in time order, index of the first row inside the window)."""
    t0, t1 = window if window is not None else (-math.inf, math.inf)
    rows = sorted((r for r in rows if _t(r) <= t1), key=_t)
    return rows, next((i for i, r in enumerate(rows) if _t(r) >= t0), len(rows))


def detect_events(rows: list, params: PilotParams, *, landmarker_num_faces: int, window: tuple | None = None,
                  baseline_s: float | None = None) -> list:
    """Events of these rows, sorted by start time. With window = (t0, t1): rows after t1 are dropped first, head
    turns use the rows before t0 as context and count when their rows all lie inside, and every other event is found
    on the rows inside the window (see the module docstring). Without a window: all rows.

    landmarker_num_faces = the num_faces setting of the Face Landmarker that produced the face columns. With more
    than one face it does not smooth [D1], so mouth_motion is not turned into events (dec section 3,
    consulting_companion exclusion: jitter is not counted as mouth motion). baseline_s = the window of a look_back's
    pre-loss head pose (_loss_context); None leaves those two observations empty.

    After a change of user inside the window (user_since) the main user's events - head turns, yaw toward the
    companion, mouth motion, dwell - read only the rows from that change on, with no context before it (_user_rows);
    the scene's events - companion present, people behind - and the touch misses read every row of the window."""
    p = params
    rows, first = _split(rows, window)
    inside = rows[first:]
    user, at = _user_rows(rows, first)
    own = user[at:]                              # the window's rows of its current main user
    t0 = _t(inside[0]) if inside else math.inf
    events = [e for e in _head_turn_scan(user, p, baseline_s)[0] if e["t_start"] >= t0]
    events += _companion_present(inside, p)
    events += _yaw_toward_companion(own, companion_sides(user, p)[0][at:], p)

    counts = [_count_value(r, "people_behind_count") for r in inside]
    events += _run_events("people_behind", inside, [c is not None and c > 0 for c in counts], p.gap_s, p.stay_min_s,
                          lambda run, s: {"people_behind_count": max(counts[i] for i in run), "stay_s": s})

    if landmarker_num_faces == SMOOTHED_NUM_FACES:
        motion = [_num(r, "mouth_motion") if _face(r) else None for r in own]
        events += _run_events("mouth_moving", own, [m is not None and m >= p.mouth_motion_min for m in motion],
                              p.gap_s, None,
                              lambda run, s: {"mouth_motion": max(motion[i] for i in run), "moving_s": s})

    taps = [_count_value(r, "tap_count") for r in own]
    present = [_face(r) or _body(r) for r in own]
    events += _run_events("dwell_no_touch", own, [pr and t == 0 for pr, t in zip(present, taps)], p.gap_s,
                          p.dwell_min_s, lambda run, s: {"no_touch_s": s},
                          breaks=[t is not None and t > 0 for t in taps])

    misses = [_count_value(r, "miss_tap_count") for r in inside]
    events += _run_events("touch_miss", inside, [m is not None and m > 0 for m in misses], p.gap_s, None,
                          lambda run, s: {"miss_tap_count": sum(misses[i] for i in run)})

    return sorted(events, key=lambda e: (e["t_start"], e["kind"]))


# --- the scene tags' measurements (situation.py SCENE_TAGS; 2026-11-22) ------------------------------------------
SCENE_KINDS = ("face_height", "face_size", "main_user_changed", "nothing_seen", "aid_score", "aid_head",
               "phone_at_head", "phone_in_hand")
# The readings of the walking-aid detector (params.PilotParams.aid_rule, 2026-11-26): OWNER_BOX = the main user's
# person box and its aid scores (the default, the rule of 2026-11-22); HEAD_CENTRE = the aid-class boxes that hold the
# centre of the main user's head box (the kiosk-view detector files: one aid-class box around the user and the aid);
# HEAD_CENTRE_CARRY = HEAD_CENTRE on the rows with the head box, and on the rows without it the aid box of the latest
# head row followed by the head tracker's rule (columns.AidCarry). AID_HEAD_RULES = the readings that write the
# aid_head columns and judge aid_use on them.
OWNER_BOX, HEAD_CENTRE, HEAD_CENTRE_CARRY = "owner_box", "head_centre", "head_centre_carry"
AID_RULES = (OWNER_BOX, HEAD_CENTRE, HEAD_CENTRE_CARRY)
AID_HEAD_RULES = (HEAD_CENTRE, HEAD_CENTRE_CARRY)


def _main_face(row: dict) -> bool:
    """The row's face is the main user's: seen, and matched to the main user's head box when the head detector ran
    (face_in_primary True; the key is absent without it). = columns.main_user_face (columns imports numpy)."""
    if not _face(row):
        return False
    return "face_in_primary" not in row or row["face_in_primary"] is True or row["face_in_primary"] == "True"


def _blank(value) -> bool:
    """A blank cell: None, "" or NaN (a CSV reader or a data frame may give any of them)."""
    return value is None or value == "" or (isinstance(value, float) and math.isnan(value))


def _box_cy(box) -> float | None:
    """The vertical centre of an (x0, y0, x1, y1) box (a tuple, or 'x0;y0;x1;y1' from rows.csv), or None."""
    if isinstance(box, str):
        box = box.split(";")
    try:
        cy = (float(box[1]) + float(box[3])) / 2.0
    except (TypeError, ValueError, IndexError):
        return None
    return cy if math.isfinite(cy) else None


def _track_value(value):
    """A track id as in a replay (an int): rows.csv gives '2', a data frame 2.0; a blank cell None."""
    if _blank(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if number.is_integer() else number


def _flag(value) -> bool | None:
    """A true / false cell: a bool in memory, 'True' / 'False' read back from rows.csv; anything else None."""
    if value is True or value == "True":
        return True
    if value is False or value == "False":
        return False
    return None


def user_change(obs: dict) -> bool:
    """Whether a main_user_changed event (its obs) is weighed as a change of user by situation.user_changed: the
    earlier main user had settled (previous_settled not False: a swap during the first approach is no change) and the
    break was not stitched back to the same user (stitched not True). An unknown flag (None) does not rule it out."""
    return obs.get("previous_settled") is not False and obs.get("stitched") is not True


def new_user(obs: dict) -> bool:
    """Whether a main_user_changed event (its obs) brings a new user, as situation.user_changed counts it: a
    user_change that is not the same user found again in the same place (reacquired not True)."""
    return user_change(obs) and obs.get("reacquired") is not True


def _change_obs(r: dict) -> dict:
    """The observations of the main_user_changed event of a row that carries main_user_prev_track (SceneCues)."""
    return {"track": _track_value(r.get("primary_track")),
            "previous_track": _track_value(r["main_user_prev_track"]),
            "gap_s": _num(r, "main_user_gap_s"), "body_kept": _flag(r.get("main_user_body_kept")),
            "body_gap_s": _num(r, "main_user_body_gap_s"),
            "previous_h": _num(r, "main_user_prev_h"), "new_h": _num(r, "main_user_new_h"),
            "h_ratio": _num(r, "main_user_h_ratio"),
            "new_was_role": None if _blank(r.get("main_user_new_was_role")) else r.get("main_user_new_was_role"),
            "new_rel_dist": _num(r, "main_user_new_rel_dist"),
            "new_growth": _num(r, "main_user_new_growth"),
            "reacquired": _flag(r.get("main_user_reacquired")),
            "previous_settled": _flag(r.get("main_user_prev_settled")),
            "stitched": _flag(r.get("main_user_stitched")),
            "new_start_s": _num(r, "main_user_new_start_s"),
            "start_shift": _num(r, "main_user_start_shift"),
            "start_size": _num(r, "main_user_start_size")}


def user_since(rows: list) -> int | None:
    """The index of the newest row of rows that starts a new user (a main_user_changed row that new_user counts, as
    situation.user_changed does), or None when there is none. 0 = the first row starts a new user: then the rows
    before these rows (a window's context) are the earlier user's, which None does not say. The per-user measures of a
    window (observe_scene, observe_window) and of a segment (chain) read the rows from there on: the earlier user's
    rows do not decide the new user's. A reacquired or stitched track, or a swap during the first approach, is no new
    user and keeps the rows before it."""
    return max((i for i, r in enumerate(rows) if not _blank(r.get("main_user_prev_track")) and new_user(_change_obs(r))),
               default=None)


def new_user_rows(rows: list) -> list:
    """rows from the newest new user's first row on (user_since); all of them when no row starts a new user."""
    since = user_since(rows)
    return rows if since is None else rows[since:]


def _user_rows(rows: list, first: int) -> tuple:
    """(the rows the main user's cues read, the index of the window's first row in them) for rows split at first
    (_split): after a change of user inside the window (user_since), the rows from that change on, with no context
    before it, also when the change is the window's first row; with no change, all rows, the context before the
    window included (head turns, the companion's side)."""
    since = user_since(rows[first:])
    return (rows, first) if since is None else (rows[first + since:], 0)


def _aid_head_obs(rows: list) -> dict:
    """The observations of an aid_head event over its rows (each with an aid_head_score): the median score (the
    statistic aid_score uses), the row count and aid_class = the class behind the median: aid_head_class of the row at
    the upper middle of the rows sorted by score (the row statistics.median_high takes; the middle row for an odd
    count; among equal scores the earlier row first), None when that row's score came from no box (0.0)."""
    scores = [_num(r, "aid_head_score") for r in rows]
    middle = rows[sorted(range(len(rows)), key=lambda i: scores[i])[len(rows) // 2]]
    name = middle.get("aid_head_class")
    return {"aid_head_median": statistics.median(scores), "rows": len(rows),
            "aid_class": None if _blank(name) else name}


@dataclass(frozen=True)
class SceneCues:
    """What the scene tags read for one window. Their events are measurements of the window's rows. The per-user
    measures (face_height, head_pitch, head_size, head_height, face_size, aid_score, aid_head, the phone segments and
    the counts near_rows, face_rows, aid_anchor_rows, head_near_rows) read only the rows from the window's newest new
    user on (user_since: after a change of user, the earlier user's rows are not the new user's); main_user_changed,
    nothing_seen, frames and the *_measured checks read the whole window:
      face_height        the main user's face rows (face values not blanked; with the head detector, face_in_primary
                         True) without the rows closer than
                         approach_ratio_min (leaning in moves the face down): face_cy_median, rows
      head_pitch         the main user's face rows with a dpitch_user_deg (pitch against the same main user's first
                         face, columns.PitchRef; + = down): dpitch_median, rows
      head_size          the rows with a head_ratio_user (columns.HeadSizeRef): head_ratio_median, rows
      head_height        the rows with the main user's head box, without the rows whose head_ratio_user is above
                         head_approach_ratio_min (a lean makes the head bigger) (primary_box, the head detector):
                         head_cy_median (the box's vertical centre), rows
      face_size          the main user's face rows with an iod_ratio_user (columns.FaceSizeRef): iod_ratio_median, rows
      main_user_changed  one per row that starts a new main-user track (columns.MainUserChange): track,
                         previous_track, gap_s, body_kept, body_gap_s (the longest stretch with neither the ended
                         track's box nor a body, which decides reacquired), reacquired (the same place: not a new
                         user), previous_settled (the earlier main user had settled; False = the first approach: not a
                         change), stitched (a break stitched by start time, place and size: not a new user), the break
                         measures new_start_s, start_shift, start_size and the size evidence previous_h, new_h, h_ratio,
                         new_was_role, new_rel_dist, new_growth (observation only)
      nothing_seen       one over the whole window when no row sees a face (landmarks or a face-detector box), a body,
                         a head box or a person box of the walking-aid detector above its person operating point
                         (aid_person_count, when it ran; its recording-floor boxes do not count): unseen_s =
                         min(face_unseen_s, body_unseen_s) at the window's last row
      aid_score          the rows with an aid_any_score (the walking-aid detector's box of the main user,
                         columns.aid_columns): aid_any_median, rows, owner_yes_rows
      aid_head           the rows with an aid_head_score (the head_centre reading: the aid-class box that holds the
                         centre of the main user's head box, columns.aid_head_columns; under head_centre_carry also the
                         rows whose value was carried, columns.AidCarry): aid_head_median, rows, aid_class
                         (_aid_head_obs: the class behind the median)
    No value is compared here except the two size boundaries that mark near rows (face: approach_ratio_min, head box:
    head_approach_ratio_min); situation.py compares the medians with the camera's boundaries."""
    events: list
    frames: int                  # rows inside the window (all of them, also after a change of user)
    track_measured: bool         # every row carries primary_track: the head detector ran, a change can be seen
    near_rows: int               # face rows left out of face_height as closer than approach_ratio_min
    face_rows: int = 0           # rows with the main user's face (face values not blanked)
    head_measured: bool = False  # every row carries head_count: 'no head box' can be concluded
    aid_measured: bool = False   # every row carries aid_owner: the walking-aid detector ran
    aid_anchor_rows: int = 0     # rows where the main user's anchor (shoulders or head box) was known
    aid_head_measured: bool = False  # every row carries aid_head_score: the detector ran with a head_centre reading
    head_near_rows: int = 0      # main-user head-box rows left out of head_height as grown beyond head_approach_ratio_min
    phone_measured: bool = False  # every row carries phone_owner: the phone detector ran
    phone_segments: tuple = ()    # 'yes' | 'no' | 'unknown' per segment_s bin of the window (_phone_segments)
    phone_head_segments: tuple = ()  # the same per bin for the phone at the main user's head only

    def of(self, *kinds: str) -> list:
        return [e for e in self.events if e["kind"] in kinds]


def observe_scene(rows: list, window: tuple, approach_ratio_min: float | None = None,
                  head_approach_ratio_min: float | None = None, segment_s: float | None = None) -> SceneCues:
    """SceneCues of window = (t0, t1) from the rows inside it (rows after t1 are never read). approach_ratio_min = the
    face-approach boundary of the bundle, or None (then no row is left out of face_height); head_approach_ratio_min =
    the head-box boundary, or None (then no row is left out of head_height). segment_s = the runners' window step
    (params.segment_s): the phone events are counted per segment; None = no phone segments. After a change of user in
    the window (a main_user_changed event that new_user counts, as situation.user_changed does) the per-user measures
    (SceneCues) read only the rows from the newest such change on (user_since). A reacquired or stitched track, or a
    swap during the first approach, keeps the rows before it."""
    rows, first = _split(rows, window)
    inside = rows[first:]
    since = user_since(inside) or 0         # the per-user measures read the rows from the newest new user on
                                            # (only rows inside the window: no change and a change on the first
                                            # row both read every one of them)
    events = [_event("main_user_changed", inside, [i], _change_obs(r)) for i, r in enumerate(inside)
              if not _blank(r.get("main_user_prev_track"))]
    own = [i >= since and _main_face(r) for i, r in enumerate(inside)]     # the window's current main user's face
    ratios = [_num(r, "iod_ratio_user") if own[i] else None for i, r in enumerate(inside)]
    near = [approach_ratio_min is not None and q is not None and q > approach_ratio_min for q in ratios]
    height = [i for i, r in enumerate(inside) if own[i] and _num(r, "face_cy") is not None and not near[i]]
    if height:
        events.append(_event("face_height", inside, height,
                             {"face_cy_median": statistics.median(_num(inside[i], "face_cy") for i in height),
                              "rows": len(height)}))
    head_ratios = [_num(r, "head_ratio_user") if i >= since else None for i, r in enumerate(inside)]
    boxed = [i for i, r in enumerate(inside) if i >= since and _box_cy(r.get("primary_box")) is not None]
    head = [i for i in boxed if not (head_approach_ratio_min is not None and head_ratios[i] is not None
                                     and head_ratios[i] > head_approach_ratio_min)]
    head_sized = [i for i, q in enumerate(head_ratios) if q is not None]
    if head_sized:
        events.append(_event("head_size", inside, head_sized,
                             {"head_ratio_median": statistics.median(head_ratios[i] for i in head_sized),
                              "rows": len(head_sized)}))
    if head:
        events.append(_event("head_height", inside, head,
                             {"head_cy_median": statistics.median(_box_cy(inside[i]["primary_box"]) for i in head),
                              "rows": len(head)}))
    pitched = [i for i, r in enumerate(inside) if own[i] and _num(r, "dpitch_user_deg") is not None]
    if pitched:
        events.append(_event("head_pitch", inside, pitched,
                             {"dpitch_median": statistics.median(_num(inside[i], "dpitch_user_deg") for i in pitched),
                              "rows": len(pitched)}))
    sized = [i for i, q in enumerate(ratios) if q is not None]
    if sized:
        events.append(_event("face_size", inside, sized,
                             {"iod_ratio_median": statistics.median(ratios[i] for i in sized), "rows": len(sized)}))
    aid = [i for i, r in enumerate(inside) if i >= since and _num(r, "aid_any_score") is not None]
    if aid:
        events.append(_event("aid_score", inside, aid,
                             {"aid_any_median": statistics.median(_num(inside[i], "aid_any_score") for i in aid),
                              "rows": len(aid),
                              "owner_yes_rows": sum(inside[i].get("aid_owner") == "yes" for i in aid)}))
    head_aid = [i for i, r in enumerate(inside) if i >= since and _num(r, "aid_head_score") is not None]
    if head_aid:
        events.append(_event("aid_head", inside, head_aid, _aid_head_obs([inside[i] for i in head_aid])))
    segments, head_segments = [], []
    if segment_s is not None and inside:
        segments, head_segments, phone_events = _phone_segments(inside[since:], window, segment_s)
        events += phone_events
    if inside and all(not _face(r) and not _body(r) and not (_num(r, "head_count") or 0) > 0
                      and not (_num(r, "aid_person_count") or 0) > 0 and not (_num(r, "face_count") or 0) > 0
                      for r in inside):
        last = inside[-1]
        unseen = [v for v in (_num(last, "face_unseen_s"), _num(last, "body_unseen_s")) if v is not None]
        events.append(_event("nothing_seen", inside, list(range(len(inside))),
                             {"unseen_s": min(unseen) if unseen else None}))
    return SceneCues(events=sorted(events, key=lambda e: (e["t_start"], e["kind"])), frames=len(inside),
                     track_measured=bool(inside) and all("primary_track" in r for r in inside),
                     aid_measured=bool(inside) and all("aid_owner" in r for r in inside),
                     face_rows=sum(own[i] and _num(r, "face_cy") is not None for i, r in enumerate(inside)),
                     head_measured=bool(inside) and all(_num(r, "head_count") is not None for r in inside),
                     aid_anchor_rows=sum(r.get("aid_owner") in ("yes", "no") for r in inside[since:]),
                     aid_head_measured=bool(inside) and all("aid_head_score" in r for r in inside),
                     near_rows=sum(n and _face(r) and _num(r, "face_cy") is not None for n, r in zip(near, inside)),
                     head_near_rows=len(boxed) - len(head),
                     phone_measured=bool(inside) and all("phone_owner" in r for r in inside),
                     phone_segments=tuple(segments), phone_head_segments=tuple(head_segments))


def _phone_segments(inside: list, window: tuple, segment_s: float) -> tuple:
    """(state per segment, head-only state per segment, phone events) of the window's segment_s bins
    (t1 - (k+1) segment_s, t1 - k segment_s], newest first, as many as window_s / segment_s (rounded; the runners'
    windows end on the segment grid, and every value bundle has window_s a whole multiple of segment_s: 3 s / 1 s; a
    bundle that is not would get round(window_s / segment_s) bins). Only the rows the detector ran on count (a blank
    phone_owner: not run on that frame, params.phone_every). 'yes' = such a row with the phone at the main user
    (phone_owner 'yes'), 'no' = such rows and every one 'no', 'unknown' otherwise (no such row, or a row that cannot
    tell). The head-only state reads the same rows for the phone at the head: 'yes' = such a row with phone_at 'head',
    'no' = such rows, none at the head and every one known ('no', or 'yes' in the hand), 'unknown' otherwise. One event
    per bin and place with such rows: phone_at_head (the box meets the head box: a call or the phone at the face),
    phone_in_hand (the box meets a hand of the main user: looking at it below the face): rows, score_max."""
    t0, t1 = window
    states, head_states, events = [], [], []
    for k in range(round((t1 - t0) / segment_s)):            # window_s / segment_s segments (3 s / 1 s: three)
        lo, hi = t1 - (k + 1) * segment_s, t1 - k * segment_s
        part = [i for i, r in enumerate(inside) if lo < _t(r) <= hi]
        ran = [i for i in part if not _blank(inside[i].get("phone_owner"))]                    # rows it ran on
        owners = [inside[i].get("phone_owner") for i in ran]
        states.append("yes" if "yes" in owners else ("no" if owners and all(o == "no" for o in owners)
                                                     else "unknown"))
        at_head = [inside[i].get("phone_owner") == "yes" and inside[i].get("phone_at") == "head" for i in ran]
        head_states.append("yes" if any(at_head) else ("no" if owners and all(o in ("yes", "no") for o in owners)
                                                       else "unknown"))
        for kind, where in (("phone_at_head", "head"), ("phone_in_hand", "hand")):
            rows = [i for i in part if inside[i].get("phone_owner") == "yes" and inside[i].get("phone_at") == where]
            if rows:
                events.append(_event(kind, inside, rows, {"rows": len(rows), "score_max": max(
                    (v for v in (_num(inside[i], "phone_score") for i in rows) if v is not None), default=None)}))
    return states, head_states, events


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


def _any_tap(inside: list, measured: frozenset) -> bool | None:
    """Cues.any_tap: True = a touch on a row of the window, False = no touch and a count on every row (measured), None
    = cannot tell (no touch seen and a row without a count)."""
    taps = [_count_value(r, "tap_count") for r in inside]
    return True if any(t is not None and t > 0 for t in taps) else (False if "tap_count" in measured else None)


def window_any_tap(rows: list, window: tuple) -> bool | None:
    """The window's touch cue as observe_window reads it (Cues.any_tap) for window = (t0, t1), without the events: the
    live runner's record says with it whether the window's touch was known to the rules."""
    rows, first = _split(rows, window)
    inside = rows[first:]
    return _any_tap(inside, measured_columns(inside))


def observe_window(rows: list, window: tuple, params: PilotParams, *, landmarker_num_faces: int,
                   baseline_s: float | None = None) -> Cues:
    """Events and window-level checks for window = (t0, t1): rows after t1 are never read; detect_events says which
    rows each event comes from; the checks read the rows inside the window. After a change of user inside the window
    (user_since) the checks of the main user - face_visible_ratio, track_conf, yaw_ok, shoulders_ok, turns_unresolved,
    mouth_observed, companion_side_unknown, body_still - read only the rows from that change on (_user_rows); the
    ratios keep the window's frames as the denominator, as the scene tags' shares do. measured and any_tap (the
    columns and the touch counts) read every row of the window."""
    t0, t1 = window
    rows, first = _split(rows, window)
    inside = rows[first:]
    user, at = _user_rows(rows, first)
    own = user[at:]                              # the window's rows of its current main user
    n = len(inside)
    measured = measured_columns(inside)
    face_ratio = sum(map(_face, own)) / n if n else None
    face_ok = face_ratio is not None and face_ratio >= params.face_visible_min
    any_tap = _any_tap(inside, measured)
    undetermined = companion_sides(user, params)[1][at:]
    broken = _head_turn_scan(user, params)[1]
    return Cues(
        events=detect_events(rows, params, landmarker_num_faces=landmarker_num_faces, window=window,
                             baseline_s=baseline_s),
        face_visible_ratio=face_ratio,
        track_conf=sum(map(_body, own)) / n if n else None,
        measured=measured,
        face_ok=face_ok,
        yaw_ok=_observed_on(own, "yaw_deg", _face),
        shoulders_ok=all(_num(r, "pose_vis_shoulders") is not None for r in own if _body(r) and not _face(r)),
        turns_unresolved=any(t0 <= t <= t1 for t in broken),
        mouth_usable=landmarker_num_faces == SMOOTHED_NUM_FACES and face_ok,
        mouth_observed=_observed_on(own, "mouth_motion", _face),
        companion_side_unknown=any(u and _face(r) and (_num(r, "yaw_deg") or 0) != 0
                                   for r, u in zip(own, undetermined)),
        any_tap=any_tap,
        body_still=_body_still(own, params))
