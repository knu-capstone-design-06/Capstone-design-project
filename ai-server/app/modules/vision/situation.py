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
     alternatives: [{name, display_text, evidence, confidence}], source: "rules_v1"}
  name          a tag; "unknown" = cannot tell; "none" = an observed cue rules every tag out
  display_text  the fixed text of the name (DISPLAY_TEXT), never free text; "" for unknown and none
  evidence      one item per observation of each supporting event, whose observation rows all lie inside the window
                (dec section 3: '전부 같은 창 안'; sem section 4, rule 1: '시간 범위(창 안)'); t = the event's end (s)
  confidence    rule satisfaction, not a probability (nothing is calibrated against labels yet): events = number of
                supporting events, quality_ok = no cue of the rule was left out as missing
  alternatives  the other tags that no measured cue ruled out and that have supporting events, most events first;
                one with fewer than min_events supporting events has confidence "unknown"

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
- missing mouth motion is left out and the tag is judged on the rest (sem section 3 says so; quality_ok says false)
"""
from __future__ import annotations

from dataclasses import dataclass

from .events import Cues, PilotParams, is_number, is_ratio, observe_window

SOURCE = "rules_v1"
UNKNOWN, NONE = "unknown", "none"
DISPLAY_TEXT = {                                   # dec section 3 table, '표시 문구'
    "looking_back_with_people_behind": "뒤에 사람이 있어 서두르는 듯함",
    "consulting_companion": "일행과 상의하는 듯함",
    "looking_around": "무언가를 찾는 듯함",
    UNKNOWN: "",
    NONE: "",
}
OUTPUT_KEYS = ("name", "display_text", "window_s", "evidence", "quality", "confidence", "alternatives", "source")
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
    out and the tag is judged on the rest (sem section 3). A yaw toward the companion seen counts; none needs the
    companion's side known on every face frame with a yaw, otherwise that cue is missing."""
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


def assess(rows: list, t_end: float, params: PilotParams, *, landmarker_num_faces: int) -> tuple:
    """(output, events) for the window [t_end - window_s, t_end] of the observation rows (features.COLUMNS plus the
    optional columns of events.py). Events come from all rows up to t_end and are kept when their time (end) lies in
    the window; the evidence ids point into the returned events. The output passes check_output, or this raises
    ValueError.

    landmarker_num_faces = the num_faces setting of the Face Landmarker behind the rows (app/inference/vision.py: 1)."""
    window = (t_end - params.window_s, t_end)
    cues = observe_window(rows, window, params, landmarker_num_faces=landmarker_num_faces)
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
    }
    problems = check_output(out, cues.events, params)
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


def _check_entry(entry: dict, by_id: dict, t0: float, t1: float, params: PilotParams) -> tuple:
    """(problems, event ids) of the output or of one alternative: display text, evidence, the min_events floor."""
    name = entry.get("name")
    problems = []
    if entry.get("display_text") != DISPLAY_TEXT.get(name):
        problems.append(f"{name}: display_text {entry.get('display_text')!r} is not the fixed text of the name")
    evidence = entry.get("evidence", [])
    if not isinstance(evidence, list):
        return problems + [f"{name}: evidence {evidence!r} is not a list"], set()
    ids = set()
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


def check_output(out: dict, events: list, params: PilotParams) -> list:
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
      and every alternative at least one event of this window."""
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
    return problems
