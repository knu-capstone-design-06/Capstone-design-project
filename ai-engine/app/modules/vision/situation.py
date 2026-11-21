"""상황 (situation) layer: the three situation tags of dec section 3 as rules over events (events.py), the
state-layer output of sem section 4 and its check rules. Plain Python: no numpy, OpenCV or MediaPipe.

Layers: 입력 sources.py -> 추론 inference.py -> 관측값 features.py -> 사건 events.py -> 상황 this file -> 전달 (contract/,
not built yet). Source shorthands (dec, sem, research/33): events.py; the README quotes dec section 3 and sem
section 4.

State (2026-10-12): the three tags are implemented as rules. Every value they compare against is a PilotParams field
([파일럿], no defaults; set from the team's self-recording) and this file holds no number - a test checks that. The
runner (run.py), the endpoints and the support choice do not call this layer yet; the tag vocabulary and how this
output reaches the other services (contract/) go to the team meeting of 2026-10-14.

Output for one window (sem section 4: dec section 3's output line plus quality, confidence, alternatives, event ids):
    {name, display_text, window_s: [t0, t1], evidence: [{event_id, obs, value, t}],
     quality: {face_visible_ratio, track_conf}, confidence: "unknown" | {events, quality_ok},
     alternatives: [{name, display_text, evidence, confidence}], source: "rules_v1",
     tags: [{name, display_text, status, evidence, unknown_reason}]}
  name          a tag; "unknown" = cannot tell; "none" = an observed cue rules every tag out
  display_text  the fixed text of the name (DISPLAY_TEXT), never free text; "" for unknown and none
  evidence      one item per observation of each supporting event, whose observation rows all lie inside the window
                (dec section 3: '전부 같은 창 안'; sem section 4, rule 1: '시간 범위(창 안)'); t = the event's end (s)
  confidence    rule satisfaction, not a probability (nothing is calibrated against labels yet): events = number of
                supporting events, quality_ok = no cue of the rule was left out as missing
  alternatives  the other tags that no measured cue ruled out and that have supporting events, most events first;
                one with fewer than min_events supporting events has confidence "unknown"
  tags          the six scene tags (SCENE_TAGS, 2026-11-22), each judged on its own and never competing with name:
                seated_height (1-2; window median of the main user's head-box centre > seated_head_cy_min with the
                head detector, else of the main user's face_cy > seated_face_cy_min), face_approach
                (2-1; window median of iod_ratio_user > approach_ratio_min), user_changed (2-2; a new main-user
                track starts in the window, not the same user found again or stitched back), none_seen (the absence node; no face, body, head box or aid-detector
                person box on any row),
                aid_use (1-1; window median of aid_any_score of the main user's person box > aid_use_min; only
                when the walking-aid detector ran), phone_use (3-2's phone path: the phone at the main user's head in
                min_events of the window's segment_s segments, or at the main user (head or hand) in min_events
                segments while not facing the screen; no touch, body still; only with the phone detector).
                status True | False | "unknown"; unknown_reason a code exactly when "unknown" (no_frames,
                no_value_for_camera, no_value, no_main_user_face, no_main_user_box, face_near, head_near, no_reference,
                too_few_rows (the rows
                behind a median are fewer than face_visible_min of the window), reacquired_same_place,
                column:primary_track, column:head_count, column:aid_owner, no_anchor, no_user_box, column:phone_owner,
                no_segments, phone_owner_unknown, gaze_unknown, column:tap_count, body_position_missing); evidence points into the
                window's scene events (events.observe_scene). The two boundaries are params.SCENE_BOUNDARIES (bundle
                values; None = unknown). Touch and duration (2-2's no-input trigger, the absence warning) are the
                judgment layer's, not these tags' - except phone_use, a whole path of the 3-2 row.

How a window is decided. From sem section 4: fewer than min_events supporting events -> "unknown"; quality per cue
(a face turned away is not a sensor failure: face loss is the look_back cue, and only the cues that need the face -
mouth motion, the yaw toward a companion, off-screen sweeps - become missing); body tracking below track_conf_min =
sensor failure -> "unknown"; two satisfied tags -> the one with more supporting events is the name and the other an
alternative; a tie -> "unknown" with both as alternatives (sem section 4 lists this tie row as [설계 제안] itself);
state lifetime: the window slides with t_end, a state starts with min_events events inside it, holds while they are
and ends when a row of theirs falls before the window (window_s is the expiry window; a state that goes on keeps its
part inside the window) or counter-evidence enters it (a touch, a person standing behind, the body moving). Added in
this code, [설계 제안] (not in sem section 4):
- three-valued logic: a cue that cannot be checked is None, not False; it decides only when nothing rules the tag out,
  so "none" needs every tag ruled out by an observed cue and missing optional columns keep the output "unknown"
- observed evidence first: a touch, a person behind, a mouth movement, a yaw toward the companion or a body movement
  seen in the window counts even where its column is partly missing; that one is absent needs the column (or the
  frames that should carry it) observed throughout - for the turns, no turn broken by a stretch that hides the head;
  for the yaw toward the companion, the companion's side known on every face frame with a yaw - otherwise the cue is
  missing
- missing mouth motion is left out and the tag is judged on the rest (sem section 3 says so; quality_ok says false):
  the decision table lists the mouth as one condition of consulting_companion's conjunction, and when its
  observation is absent the condition is treated as missing (결측) and dropped from the conjunction - the evidence
  then lists only the cues used (no mouth_moving event) and confidence.quality_ok is false
"""
from __future__ import annotations

from dataclasses import dataclass

from .events import Cues, PilotParams, SceneCues, is_number, is_ratio, observe_scene, observe_window

SOURCE = "rules_v1"
UNKNOWN, NONE = "unknown", "none"
DISPLAY_TEXT = {                                   # dec section 3 table, '표시 문구'
    "looking_back_with_people_behind": "뒤에 사람이 있어 서두르는 듯함",
    "consulting_companion": "일행과 상의하는 듯함",
    "looking_around": "무언가를 찾는 듯함",
    UNKNOWN: "",
    NONE: "",
}
OUTPUT_KEYS = ("name", "display_text", "window_s", "evidence", "quality", "confidence", "alternatives", "source",
               "tags")
QUALITY_KEYS = ("face_visible_ratio", "track_conf")
EVIDENCE_KEYS = ("event_id", "obs", "value", "t")


@dataclass(frozen=True)
class Verdict:
    """One rule on one window."""
    status: bool | None   # True = every condition holds; False = an observed cue rules the tag out; None = cannot tell
    support: list         # the events behind the tag (its evidence), auxiliary ones included
    skipped: tuple = ()   # cues left out as missing; the tag was judged on the rest


def _all(*conditions):
    """Three-valued AND: False if any condition is False, else None if any is None, else True."""
    if any(c is False for c in conditions):
        return False
    if any(c is None for c in conditions):
        return None
    return True


def _found(events: list, measurable: bool):
    """True when there are events; without events, False if the cue was measurable and None if it was not."""
    if events:
        return True
    return False if measurable else None


def _at_least(events: list, count: int, measurable: bool):
    """The cue is there (at least one event, whatever the count field says) and reaches count."""
    if events and len(events) >= count:
        return True
    return False if measurable else None


def _no_touch(c: Cues):
    """'터치 없음': no touch anywhere in the window (a touch seen rules it out; None: not every row has a count)."""
    return None if c.any_tap is None else not c.any_tap


def _dwell_without_touch(c: Cues, dwell: list):
    """'안 누르고 머묾': a dwell_no_touch event and no touch anywhere in the window."""
    no_touch = _no_touch(c)
    if no_touch is not True:
        return no_touch                          # a touch seen (False), or not every row counted (None)
    return _found(dwell, True)


# --- the three rules (dec section 3 table) ----------------------------------------------------------------------
def looking_back_with_people_behind(c: Cues, p: PilotParams) -> Verdict:
    """뒤에 사람이 있어 서두르는 듯함 (dec section 3, row 1).

    Combines: a person standing behind (people_behind, staying stay_min_s: '멈춰 선 사람만') + repeated look_backs
    (look_back_min_count or more). Auxiliary: touch_miss events add support and are never required. Excluded:
    passers-by only (they leave before stay_min_s, so there is no people_behind event); people behind without
    look-backs. No look-back is concluded only when every face frame had a yaw, every frame with the face lost and
    the body seen had a shoulder value, and no turn in the window was broken by a stretch hiding the head (face and
    body lost together, or a gap in the record); otherwise the cue is missing. Not built: touches getting faster and
    expression change (no input yet)."""
    behind = c.of("people_behind")
    looks = c.of("look_back")
    status = _all(_found(behind, "people_behind_count" in c.measured),
                  _at_least(looks, p.look_back_min_count, c.yaw_ok and c.shoulders_ok and not c.turns_unresolved))
    return Verdict(status, behind + looks + c.of("touch_miss"))


def consulting_companion(c: Cues, p: PilotParams) -> Verdict:
    """일행과 상의하는 듯함 (dec section 3, row 2).

    Combines: a companion (companion_present: a second box of similar size beside) + the main user's yaw toward the
    companion's side at that frame (yaw_toward_companion; the face is needed) + mouth moving (mouth_moving) + dwell
    without touching ('안 누르고 머묾': a dwell_no_touch event and no touch in the window) + body still. Excluded: a
    Face Landmarker that does not smooth (num_faces of 2 or more) - events.detect_events then makes no mouth_moving,
    so jitter is not counted as mouth motion. A mouth movement seen counts; no movement needs a mouth value on every
    face frame. Otherwise (no values, no smoothing, face_visible_ratio below face_visible_min) mouth motion is left
    out and the tag is judged on the rest (sem section 3): the decision table's conjunction lists the mouth, but an
    absent mouth observation is treated as missing (결측) and dropped from the conjunction, so the evidence shows the
    cues that were used (no mouth_moving) and Verdict.skipped / confidence.quality_ok record the drop. A yaw toward the
    companion seen counts; none needs the companion's side known on every face frame with a yaw, otherwise that cue is
    missing."""
    companions = c.of("companion_present")
    toward = c.of("yaw_toward_companion") if c.face_ok else []
    mouth = c.of("mouth_moving") if c.mouth_usable else []
    if mouth:
        mouth_seen, skipped = True, ()
    elif c.mouth_usable and c.mouth_observed:
        mouth_seen, skipped = False, ()
    else:
        mouth_seen, skipped = True, ("mouth_moving",)             # missing: left out, judged on the rest
    dwell = c.of("dwell_no_touch")
    status = _all(_found(companions, "companion_box" in c.measured),
                  _found(toward, c.face_ok and c.yaw_ok and not c.companion_side_unknown),
                  mouth_seen,
                  _dwell_without_touch(c, dwell),
                  c.body_still)
    return Verdict(status, companions + toward + mouth + dwell, skipped)


def looking_around(c: Cues, p: PilotParams) -> Verdict:
    """무언가를 찾는 듯함 (dec section 3, row 3).

    Combines: large off-screen head turns, sweep_min_count or more (look_back, and yaw_sweep_offscreen when the face
    is seen enough - a turn far enough to lose the face is counted by 'face lost + body remains', dec section 3
    note) + no touch in the window + body still + nobody standing behind (a people_behind event rules the tag out;
    'nobody' needs people_behind_count on every row). dwell_no_touch events add support and are not required.
    Excluded: the small yaw of reading the menu (it stays inside offscreen_yaw_deg, so it makes no turn event)."""
    turns = c.of("look_back") + (c.of("yaw_sweep_offscreen") if c.face_ok else [])
    behind = c.of("people_behind")
    nobody_behind = False if behind else (True if "people_behind_count" in c.measured else None)
    status = _all(_at_least(turns, p.sweep_min_count,
                            c.face_ok and c.yaw_ok and c.shoulders_ok and not c.turns_unresolved),
                  _no_touch(c), c.body_still, nobody_behind)
    return Verdict(status, turns + c.of("dwell_no_touch"))


RULES = {
    "looking_back_with_people_behind": looking_back_with_people_behind,
    "consulting_companion": consulting_companion,
    "looking_around": looking_around,
}
TAGS = tuple(RULES)


# --- the scene tags: a second list, judged one by one (2026-11-22) -----------------------------------------------
# They do not compete with the three tags above: a seated user can also look back at a queue, so each scene tag has
# its own status in `tags` and the single `name` is decided as before, without them.
SCENE_DISPLAY_TEXT = {                             # the scenario tree's terms (table 3-가)
    "seated_height": "앉은 높이",                   # 1-2 wheelchair: the face low in the frame
    "face_approach": "얼굴 접근",                   # 2-1 low vision: the face grown against the user's reference
    "user_changed": "사용자 교체 가능성",            # 2-2 new customer: a new main-user track
    "none_seen": "카메라에 사람이 안 보임",          # the absence node (nothing seen; not 'nobody')
    "aid_use": "보조기구 사용 중",                   # 1-1 aid (a wheelchair: 1-2, by aid_kind): the main user's box
    "phone_use": "잠시 딴 일 중(휴대폰)",            # 3-2 busy, the path besides the companion (table 3-가 3-2)
}
SCENE_TAGS = tuple(SCENE_DISPLAY_TEXT)
TAG_KEYS = ("name", "display_text", "status", "evidence", "unknown_reason")


def _enough(sc: SceneCues, rows: int, min_share: float | None) -> bool:
    """Whether a median stands on enough of the window: rows / frames >= min_share (params.face_visible_min, the share
    the three tags already ask of the face). None: no share asked."""
    return min_share is None or rows >= min_share * sc.frames


def seated_height(sc: SceneCues, seated_face_cy_min: float | None, min_share: float | None = None,
                  seated_head_cy_min: float | None = None) -> tuple:
    """(status, events, unknown reason): the median face_cy of the main user's face rows (face_height) below the
    camera's boundary seated_face_cy_min (face_cy grows downward). No frames, no value for this camera, no main-user face
    row, every face row left out as near (face_near) or too few rows behind the median: unknown - and then, with the
    head detector and the camera's head value, the median vertical centre of the main user's head box (head_height)
    below seated_head_cy_min decides instead (a seated user whose face is not seen); no main-user box in the window
    (no_main_user_box), every box row left out as grown by a lean (head_near) or too few box rows: unknown."""
    status, events, reason = _seated_by_face(sc, seated_face_cy_min, min_share)
    if status is not None or reason == "no_frames" or seated_head_cy_min is None or not sc.track_measured:
        return status, events, reason
    head = sc.of("head_height")
    if not head:
        return None, [], "head_near" if sc.head_near_rows else "no_main_user_box"
    (event,) = head
    if not _enough(sc, event["obs"]["rows"], min_share):
        return None, head, "too_few_rows"
    return event["obs"]["head_cy_median"] > seated_head_cy_min, head, None


def _seated_by_face(sc: SceneCues, seated_face_cy_min: float | None, min_share: float | None) -> tuple:
    """The face part of seated_height (its docstring)."""
    if not sc.frames:
        return None, [], "no_frames"
    if seated_face_cy_min is None:
        return None, [], "no_value_for_camera"
    height = sc.of("face_height")
    if not height:
        return None, [], "face_near" if sc.near_rows else "no_main_user_face"
    (event,) = height                         # observe_scene makes at most one per window
    if not _enough(sc, event["obs"]["rows"], min_share):
        return None, height, "too_few_rows"
    return event["obs"]["face_cy_median"] > seated_face_cy_min, height, None


def face_approach(sc: SceneCues, approach_ratio_min: float | None, min_share: float | None = None,
                  head_down_pitch_min: float | None = None) -> tuple:
    """(status, events, unknown reason): the median iod_ratio_user of the window (face_size) above the boundary. No
    frames, no value, no main-user face row (the face is lost, as when it is closest) or no reference yet: unknown.
    True asks no share of face rows: leaning in is what makes the landmarker lose the face, so a share would hide the
    scene it should show. False does (min_share, as seated_height): a few face rows before the face is lost say
    nothing about the rest of the window (too_few_rows). The head-down gate: a window whose face grew above the
    boundary while its median head pitch (head_pitch, + = down) is above head_down_pitch_min (the camera's head-down
    boundary), on a median of at least min_share of the window's frames (as the boundary was calibrated), is False:
    bowing to a phone or the counter is not leaning in to read, and the window is judged (the company-video check of
    the gate counted it so). The gate is read only when the face grew; a window whose face did not grow is decided by
    its size alone."""
    if not sc.frames:
        return None, [], "no_frames"
    if approach_ratio_min is None:
        return None, [], "no_value"
    size = sc.of("face_size")
    if not size:
        return None, [], "no_reference" if sc.face_rows else "no_main_user_face"
    (event,) = size
    if event["obs"]["iod_ratio_median"] > approach_ratio_min:
        pitch = [e for e in sc.of("head_pitch") if _enough(sc, e["obs"]["rows"], min_share)]
        if head_down_pitch_min is not None and any(e["obs"]["dpitch_median"] > head_down_pitch_min for e in pitch):
            return False, size + pitch, None
        return True, size, None
    if not _enough(sc, event["obs"]["rows"], min_share):
        return None, size, "too_few_rows"
    return False, size, None


def user_changed(sc: SceneCues) -> tuple:
    """(status, events, unknown reason): a row of the window starts a new main-user track (main_user_changed) that is
    not a reacquisition in the same place, not a track break stitched by start time, place and size (main_user_stitched:
    the same user's track broke in place, as under a cap or a deep bow), and whose earlier main user had settled at the
    kiosk (columns.MainUserChange, main_user_prev_settled; a swap during the first approach is no change). Only
    reacquisitions: unknown (reacquired_same_place). A break that is both stitched and reacquired counts as stitched
    (no change, not unknown): the stitch also meets a time bound, the new head first seen within track_max_gap_s after
    the earlier track's last box, which a reacquisition (the same place, kept by a body) does not ask. No change is
    concluded only when every row carries primary_track (the head detector ran)."""
    if not sc.frames:
        return None, [], "no_frames"
    changes = [e for e in sc.of("main_user_changed")          # a swap during the first approach is not a change,
               if e["obs"].get("previous_settled") is not False  # nor a track stitched back to the same user
               and e["obs"].get("stitched") is not True]
    new = [e for e in changes if e["obs"].get("reacquired") is not True]
    if new:
        return True, new, None
    if changes:
        return None, changes, "reacquired_same_place"
    return (False, [], None) if sc.track_measured else (None, [], "column:primary_track")


def none_seen(sc: SceneCues) -> tuple:
    """(status, events, unknown reason): no row of the window sees a face, a body, a head box or a person box of the
    aid detector above its person point (nothing_seen). That no
    head box was there needs head_count on every row (the head detector ran); otherwise unknown (column:head_count)."""
    if not sc.frames:
        return None, [], "no_frames"
    nothing = sc.of("nothing_seen")
    if nothing and not sc.head_measured:
        return None, nothing, "column:head_count"
    return bool(nothing), nothing, None


def aid_use(sc: SceneCues, aid_use_min: float | None, min_share: float | None = None) -> tuple:
    """(status, events, unknown reason): the median aid_any_score of the main user's person box (aid_score)
    above the boundary. The detector not run, no value, no anchor for the main user, no box around it or too few rows
    behind the median: unknown."""
    if not sc.frames:
        return None, [], "no_frames"
    if not sc.aid_measured:
        return None, [], "column:aid_owner"
    if aid_use_min is None:
        return None, [], "no_value"
    scores = sc.of("aid_score")
    if not scores:
        return None, [], "no_user_box" if sc.aid_anchor_rows else "no_anchor"
    (event,) = scores
    if not _enough(sc, event["obs"]["rows"], min_share):
        return None, scores, "too_few_rows"
    return event["obs"]["aid_any_median"] > aid_use_min, scores, None


def _any(*conditions):
    """Three-valued OR: True if any condition is True, else None if any is None, else False."""
    if any(c is True for c in conditions):
        return True
    if any(c is None for c in conditions):
        return None
    return False


def _segments_reach(states: tuple, min_events: int):
    """True when at least min_events segments are 'yes', False when even the 'unknown' ones could not make
    min_events, else None."""
    yes = states.count("yes")
    return True if yes >= min_events else (False if yes + states.count("unknown") < min_events else None)


def phone_use(sc: SceneCues, c: Cues | None, min_events: int | None, away: bool | None = None) -> tuple:
    """(status, events, unknown reason): 3-2's path besides the companion (tree table 3-가 3-2: the companion path or
    the second camera path, with no touch in the window). Two places of the phone: at the head (phone_at_head: the box
    meets the head box, a call) in at least min_events of the window's segment_s segments; or at the main user, head or
    hand (phone_in_hand: it meets a hand of the main user), in at least min_events segments while the main user is not
    facing the screen (away True, chain.away_from_screen: the gaze gate says away, or the main user's head box is seen
    without a face in it; tree 3-2 excludes a user who looks down at the screen, which is 4-2's pause). min_events is the value bundle's situation.min_events, reused ([파일럿]: the bundle
    marks the value so, and counting a segment with the phone as one supporting event is this path's own reading): the
    three situation tags ask that many supporting events (the detector misses frames, so the phone counts per segment,
    not per frame). Then no touch in the window and the body still -
    the touch and body conditions of consulting_companion and looking_around. Unlike the other scene tags this one is a
    whole path of the judgment layer's 3-2 row (rule_table_v0), so it reads the touch counts and the head direction.
    Unknown: no frames, the detector did not run (column:phone_owner), no segment_s given (no_segments), too many
    segments that cannot tell (phone_owner_unknown), the hand path needs the head direction and neither the gaze gate
    nor the head box tells it (gaze_unknown), no
    touch count on every row (column:tap_count), the shoulders not seen enough (body_position_missing)."""
    if not sc.frames:
        return None, [], "no_frames"
    if not sc.phone_measured or c is None or min_events is None:
        return None, [], "column:phone_owner"
    if not sc.phone_segments:
        return None, [], "no_segments"                       # assess was given no segment_s: nothing to count
    events = sc.of("phone_at_head", "phone_in_hand")
    head = _segments_reach(sc.phone_head_segments, min_events)
    anywhere = _segments_reach(sc.phone_segments, min_events)
    phone = _any(head, _all(anywhere, away))
    status = _all(phone, _no_touch(c), c.body_still)
    if status is not None:
        return status, events, None
    if phone is None:
        reason = "phone_owner_unknown" if (head is None or anywhere is None) else "gaze_unknown"
    else:
        reason = "column:tap_count" if _no_touch(c) is None else "body_position_missing"
    return None, events, reason


def scene_tags(sc: SceneCues, *, seated_face_cy_min: float | None = None, seated_head_cy_min: float | None = None,
               head_down_pitch_min: float | None = None,
               approach_ratio_min: float | None = None, aid_use_min: float | None = None,
               min_share: float | None = None, cues: Cues | None = None, min_events: int | None = None,
               away: bool | None = None) -> list:
    """The `tags` list of one window, in SCENE_TAGS order. min_share = the share of the window's frames a median must
    stand on (assess passes params.face_visible_min); cues / min_events / away = the window's Cues, params.min_events
    and whether the main user is not facing the screen at the segment end (chain.away_from_screen; None = cannot
    tell) for phone_use."""
    verdicts = {"seated_height": seated_height(sc, seated_face_cy_min, min_share, seated_head_cy_min),
                "face_approach": face_approach(sc, approach_ratio_min, min_share, head_down_pitch_min),
                "user_changed": user_changed(sc), "none_seen": none_seen(sc),
                "aid_use": aid_use(sc, aid_use_min, min_share), "phone_use": phone_use(sc, cues, min_events, away)}
    return [{"name": name, "display_text": SCENE_DISPLAY_TEXT[name],
             "status": UNKNOWN if status is None else status, "evidence": _evidence(events),
             "unknown_reason": reason}
            for name, (status, events, reason) in ((n, verdicts[n]) for n in SCENE_TAGS)]


# --- output -----------------------------------------------------------------------------------------------------
def _ordered(events: list) -> list:
    return sorted(events, key=lambda e: (e["t_start"], e["kind"]))


def _evidence(events: list) -> list:
    return [{"event_id": e["event_id"], "obs": key, "value": value, "t": e["t_end"]}
            for e in _ordered(events) for key, value in e["obs"].items()]


def _strong(v: Verdict, p: PilotParams) -> bool:
    return v.status is True and len(v.support) >= p.min_events


def _entry(name: str, v: Verdict, p: PilotParams) -> dict:
    """An alternative: below min_events (or not satisfied) its confidence is "unknown", as for the name."""
    confidence = {"events": len(v.support), "quality_ok": not v.skipped} if _strong(v, p) else UNKNOWN
    return {"name": name, "display_text": DISPLAY_TEXT[name], "evidence": _evidence(v.support),
            "confidence": confidence}


def _decide(c: Cues, verdicts: dict, p: PilotParams) -> tuple:
    """(name, alternative tags) of one window."""
    if c.track_conf is None or c.track_conf < p.track_conf_min:
        return UNKNOWN, []                                    # sensor failure: no rule is read
    open_tags = sorted((n for n in TAGS if verdicts[n].status is not False),
                       key=lambda n: len(verdicts[n].support), reverse=True)
    strong = [n for n in open_tags if _strong(verdicts[n], p)]
    if strong:
        leader, *rest = strong
        tied = [n for n in rest if len(verdicts[n].support) == len(verdicts[leader].support)]
        name = UNKNOWN if tied else leader                    # tie -> unknown: sem section 4 tie row, [설계 제안]
    else:
        name = UNKNOWN if open_tags else NONE
    return name, [n for n in open_tags if n != name and verdicts[n].support]   # no evidence, no alternative


def assess(rows: list, t_end: float, params: PilotParams, *, landmarker_num_faces: int,
           baseline_s: float | None = None, seated_face_cy_min: float | None = None,
           approach_ratio_min: float | None = None, aid_use_min: float | None = None,
           seated_head_cy_min: float | None = None, head_down_pitch_min: float | None = None,
           head_approach_ratio_min: float | None = None, segment_s: float | None = None,
           away: bool | None = None) -> tuple:
    """(output, events) for the window [t_end - window_s, t_end] of the observation rows (features.COLUMNS plus the
    optional columns of events.py). Events come from all rows up to t_end and are kept when their time (end) lies in
    the window; the evidence ids point into the returned events. The output passes check_output, or this raises
    ValueError.

    landmarker_num_faces = the num_faces setting of the Face Landmarker behind the rows (app/inference/vision.py: 1).
    baseline_s = the window of a look_back's pre-loss head pose (events._loss_context; observation only).
    seated_face_cy_min, approach_ratio_min, aid_use_min, seated_head_cy_min = the scene-tag boundaries of the bundle
    (params.SCENE_BOUNDARIES, AID_BOUNDARIES; None = no value: the tag says unknown, and for seated_head_cy_min the
    face decides alone); head_down_pitch_min, head_approach_ratio_min = the gates of face_approach and of the head-box
    path (None = not applied). segment_s = the runners' segment (phone_use counts the phone per segment; None = no
    segments); away = the main user not facing the screen at the segment end (chain.away_from_screen; None =
    cannot tell), read by phone_use's hand path only. The scene tags' evidence points into their own events (output['tags'], not in
    the returned events); the other keys of the output do not depend on them."""
    window = (t_end - params.window_s, t_end)
    cues = observe_window(rows, window, params, landmarker_num_faces=landmarker_num_faces, baseline_s=baseline_s)
    scene = observe_scene(rows, window, approach_ratio_min, head_approach_ratio_min, segment_s)
    verdicts = {name: rule(cues, params) for name, rule in RULES.items()}
    name, alternatives = _decide(cues, verdicts, params)
    chosen = verdicts.get(name)
    support = chosen.support if chosen else []
    out = {
        "name": name,
        "display_text": DISPLAY_TEXT[name],
        "window_s": list(window),
        "evidence": _evidence(support),
        "quality": {"face_visible_ratio": cues.face_visible_ratio, "track_conf": cues.track_conf},
        "confidence": (UNKNOWN if name == UNKNOWN
                       else {"events": len(support), "quality_ok": not (chosen and chosen.skipped)}),
        "alternatives": [_entry(n, verdicts[n], params) for n in alternatives],
        "source": SOURCE,
        "tags": scene_tags(scene, seated_face_cy_min=seated_face_cy_min, seated_head_cy_min=seated_head_cy_min,
                           head_down_pitch_min=head_down_pitch_min,
                           approach_ratio_min=approach_ratio_min,
                           aid_use_min=aid_use_min, min_share=params.face_visible_min, cues=cues,
                           min_events=params.min_events, away=away),
    }
    problems = check_output(out, cues.events, params, scene_events=scene.events)
    if problems:
        raise ValueError("situation output breaks the check rules: " + "; ".join(problems))
    return out, cues.events


# --- check rules ------------------------------------------------------------------------------------------------
def _window(value):
    """(t0, t1) when value is [start, end] with finite numbers and start <= end, else None."""
    try:
        t0, t1 = value
    except (TypeError, ValueError):
        return None
    return (t0, t1) if is_number(t0) and is_number(t1) and t0 <= t1 else None


def _check_evidence(name: str, evidence: list, by_id: dict, t0: float, t1: float) -> tuple:
    """(problems, event ids) of a list of evidence items against the events of the window."""
    problems, ids = [], set()
    for item in evidence:
        if not isinstance(item, dict) or set(item) != set(EVIDENCE_KEYS):
            problems.append(f"{name}: evidence item {item!r} does not have the keys {EVIDENCE_KEYS}")
            continue
        event = by_id.get(item["event_id"])
        if event is None:
            problems.append(f"{name}: evidence names no event of this window: {item['event_id']!r}")
            continue
        ids.add(item["event_id"])
        if not (t0 <= event["t_start"] and event["t_end"] <= t1):
            problems.append(f"{name}: event {item['event_id']} has rows outside the window {t0}..{t1}")
        if item["obs"] not in event["obs"] or event["obs"][item["obs"]] != item["value"]:
            problems.append(f"{name}: {item['obs']}={item['value']!r} is not an observation of {item['event_id']}")
        if item["t"] != event["t_end"]:
            problems.append(f"{name}: t {item['t']!r} is not the end of {item['event_id']}")
    return problems, ids


def _check_tags(tags, by_id: dict, t0: float, t1: float) -> list:
    """Problems of the scene-tag list: every SCENE_TAGS name once, in order, with its fixed display text; status
    True, False or 'unknown'; a reason exactly when unknown; evidence linked to this window's events."""
    if not isinstance(tags, list) or not all(isinstance(t, dict) and set(t) == set(TAG_KEYS) for t in tags):
        return [f"tags {tags!r} is not a list of entries with the keys {TAG_KEYS}"]
    if tuple(t["name"] for t in tags) != SCENE_TAGS:
        return [f"tags {[t['name'] for t in tags]} are not the scene tags {list(SCENE_TAGS)} in order"]
    problems = []
    for tag in tags:
        name, status, reason = tag["name"], tag["status"], tag["unknown_reason"]
        if tag["display_text"] != SCENE_DISPLAY_TEXT[name]:
            problems.append(f"{name}: display_text {tag['display_text']!r} is not the fixed text of the tag")
        if not (type(status) is bool or status == UNKNOWN):
            problems.append(f"{name}: status {status!r} is not true, false or {UNKNOWN!r}")
        if status == UNKNOWN and not (isinstance(reason, str) and reason):
            problems.append(f"{name}: status {UNKNOWN!r} needs a non-empty reason, got {reason!r}")
        elif status != UNKNOWN and reason is not None:
            problems.append(f"{name}: status {status!r} with unknown_reason {reason!r}: a definite status has none")
        if not isinstance(tag["evidence"], list):
            problems.append(f"{name}: evidence {tag['evidence']!r} is not a list")
            continue
        tag_problems, _ = _check_evidence(name, tag["evidence"], by_id, t0, t1)
        problems += tag_problems
    return problems


def _check_entry(entry: dict, by_id: dict, t0: float, t1: float, params: PilotParams) -> tuple:
    """(problems, event ids) of the output or of one alternative: display text, evidence, the min_events floor."""
    name = entry.get("name")
    problems = []
    if entry.get("display_text") != DISPLAY_TEXT.get(name):
        problems.append(f"{name}: display_text {entry.get('display_text')!r} is not the fixed text of the name")
    evidence = entry.get("evidence", [])
    if not isinstance(evidence, list):
        return problems + [f"{name}: evidence {evidence!r} is not a list"], set()
    evidence_problems, ids = _check_evidence(name, evidence, by_id, t0, t1)
    problems += evidence_problems
    confidence = entry.get("confidence")
    if isinstance(confidence, dict):
        count = confidence.get("events")
        if count != len(ids):
            problems.append(f"{name}: confidence events {count!r} != {len(ids)} evidence events")
        elif name in RULES and count < params.min_events:
            problems.append(f"{name}: {count} events, fewer than min_events, but confidence is not 'unknown'")
        if not isinstance(confidence.get("quality_ok"), bool):
            problems.append(f"{name}: quality_ok is not true or false")
    elif confidence != UNKNOWN:
        problems.append(f"{name}: confidence {confidence!r} is neither 'unknown' nor {{events, quality_ok}}")
    return problems, ids


def check_output(out: dict, events: list, params: PilotParams, scene_events: list | None = None) -> list:
    """Problems of one output against the events of its window; [] = it passes (a malformed output gives problems,
    not an exception). The check rules as code:
    - form: window_s is [start, end] with finite start <= end; quality has face_visible_ratio and track_conf, each a
      ratio in [0, 1] - or empty (None) only for "unknown" without alternatives, when the window has no frames;
    - rule 1, evidence linked to events (sem section 4; dec section 3 '전부 같은 창 안'): every evidence item names an
      event of this window whose rows all lie inside window_s, and repeats one of its observations (obs, value) at
      its end t;
    - display text: the fixed text of the name (DISPLAY_TEXT), never free text;
    - rule 2, 'unknown' (sem section 4): name "unknown" if and only if confidence "unknown"; the name and every
      alternative with a {events, quality_ok} confidence have at least min_events supporting events and come from a
      window that met track_conf_min; "unknown" and "none" carry no evidence of their own, "none" no alternatives,
      and every alternative at least one event of this window;
    - scene tags (`tags`, _check_tags): their evidence names events of this window too, from events or scene_events
      (the scene tags' own measurement events, events.observe_scene)."""
    if not isinstance(out, dict):
        return [f"output {out!r} is not a dict"]
    missing = [k for k in OUTPUT_KEYS if k not in out]
    if missing:
        return [f"missing keys {missing}"]
    problems = [] if out["source"] == SOURCE else [f"source {out['source']!r} is not {SOURCE!r}"]
    name, confidence, alternatives = out["name"], out["confidence"], out["alternatives"]
    if name not in DISPLAY_TEXT:
        return problems + [f"name {name!r} is not a tag, {UNKNOWN!r} or {NONE!r}"]
    window = _window(out["window_s"])
    if window is None:
        return problems + [f"window_s {out['window_s']!r} is not [start, end] with finite start <= end"]
    if not isinstance(alternatives, list) or not all(isinstance(a, dict) for a in alternatives):
        return problems + [f"alternatives {alternatives!r} is not a list of entries"]
    quality = out["quality"] if isinstance(out["quality"], dict) else {}
    if not isinstance(out["quality"], dict):
        problems.append(f"quality {out['quality']!r} is not {{face_visible_ratio, track_conf}}")
    for key in QUALITY_KEYS:
        if key not in quality:
            problems.append(f"quality.{key} is missing")
        elif quality[key] is None:
            if name != UNKNOWN or alternatives:
                problems.append(f"quality.{key} is empty, but the output reads a rule")
        elif not is_ratio(quality[key]):
            problems.append(f"quality.{key} {quality[key]!r} is not a ratio from 0 to 1")
    track = quality.get("track_conf")
    track_ok = is_number(track) and track >= params.track_conf_min
    t0, t1 = window
    by_id = {e["event_id"]: e for e in events}
    own_problems, _ = _check_entry(out, by_id, t0, t1, params)
    problems += own_problems
    if (name == UNKNOWN) != (confidence == UNKNOWN):
        problems.append(f"name {name!r} with confidence {confidence!r}: 'unknown' goes only with 'unknown'")
    if name in RULES:
        if not track_ok:
            problems.append(f"{name}: track_conf {track!r} below track_conf_min")
    elif out["evidence"]:
        problems.append(f"{name!r} carries evidence of its own")
    if name == NONE and alternatives:
        problems.append("'none' has alternatives")
    seen = set()
    for alt in alternatives:
        alt_name = alt.get("name")
        if alt_name not in RULES or alt_name == name or alt_name in seen:
            problems.append(f"alternative {alt_name!r} is not another tag")
            continue
        seen.add(alt_name)
        alt_problems, alt_ids = _check_entry(alt, by_id, t0, t1, params)
        problems += alt_problems
        if not alt_ids:
            problems.append(f"alternative {alt_name}: no evidence event of this window")
        if isinstance(alt.get("confidence"), dict) and not track_ok:
            problems.append(f"alternative {alt_name}: a definite confidence, but track_conf {track!r} is below "
                            f"track_conf_min")
    problems += _check_tags(out["tags"], {**by_id, **{e["event_id"]: e for e in scene_events or []}}, t0, t1)
    return problems
