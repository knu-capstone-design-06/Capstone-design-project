"""상황 (situation) layer: the three situation tags of dec section 3 as rules over events (events.py), the
state-layer output of sem section 4 and its check rules. Plain Python: no numpy, OpenCV or MediaPipe.

Layers: 입력 sources.py -> 추론 inference.py -> 관측값 features.py -> 사건 events.py -> 상황 this file -> 전달 (contract/,
not built yet). Source shorthands (dec, sem, research/33): events.py.

State (2026-10-11): the three tags are implemented as rules. Every value they compare against is a PilotParams field
([파일럿], no defaults; set from the team's self-recording) and this file holds no number - a test checks that. The tag
vocabulary and how this output reaches the other services (contract/) go to the team meeting of 2026-10-14; run.py
does not call this layer yet.

Output for one window (sem section 4: dec section 3's output line plus quality, confidence, alternatives, event ids):
    {name, display_text, window_s: [t0, t1], evidence: [{event_id, obs, value, t}],
     quality: {face_visible_ratio, track_conf}, confidence: "unknown" | {events, quality_ok},
     alternatives: [{name, display_text, evidence, confidence}], source: "rules_v1"}
  name          a tag; "unknown" = cannot tell; "none" = a measured cue rules every tag out
  display_text  the fixed text of the name (DISPLAY_TEXT), never free text; "" for unknown and none
  evidence      one item per observation of each supporting event; t = the event's start (s)
  confidence    rule satisfaction, not a probability (nothing is calibrated against labels yet): events = number of
                supporting events, quality_ok = no cue of the rule was left out as missing
  alternatives  the other tags that no measured cue ruled out and that have supporting events, most events first

How a window is decided (sem section 4):
- a cue that cannot be measured is None, not False (three-valued AND): it decides only when nothing rules the tag out.
  So "none" needs every tag ruled out by a measured cue; with the optional columns missing the output stays "unknown"
- the body tracker lost the person (track_conf below track_conf_min) -> sensor failure -> "unknown". A face turned away
  is not that: face loss is the look_back cue, and only the cues that need the face become missing
- missing mouth motion is left out and the tag is judged on the rest (sem section 3); quality_ok then says false
- a satisfied tag with fewer than min_events supporting events -> "unknown"; two satisfied tags -> the one with more
  supporting events is the name and the other an alternative; a tie -> "unknown" with both as alternatives
- state lifetime: the window slides with t_end. A state starts with min_events events in the window, holds while they
  stay in it and ends when they leave it (window_s is the expiry window) or when counter-evidence enters it (a touch,
  a person standing behind, the body moving)
"""
from __future__ import annotations

from dataclasses import dataclass

from .events import Cues, PilotParams, observe_window

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
EVIDENCE_KEYS = ("event_id", "obs", "value", "t")


@dataclass(frozen=True)
class Verdict:
    """One rule on one window."""
    status: bool | None   # True = every condition holds; False = a measured cue rules the tag out; None = cannot tell
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
    if len(events) >= count:
        return True
    return False if measurable else None


def _no_touch(c: Cues, dwell: list):
    """'안 누르고 머묾': a dwell_no_touch event and no touch anywhere in the window (None: no touch log)."""
    if c.any_tap is None:
        return None
    return bool(dwell) and not c.any_tap


# --- the three rules (dec section 3 table) ----------------------------------------------------------------------
def looking_back_with_people_behind(c: Cues, p: PilotParams) -> Verdict:
    """뒤에 사람이 있어 서두르는 듯함 (dec section 3, row 1).

    Combines: a person standing behind (people_behind, staying stay_min_s) + repeated look_backs (look_back_min_count
    or more). Auxiliary: touch_miss events add support and are never required. Excluded: passers-by only (they leave
    before stay_min_s, so there is no people_behind event); people behind without look-backs. Not built: touches
    getting faster and expression change (no input yet)."""
    behind = c.of("people_behind")
    looks = c.of("look_back")
    status = _all(_found(behind, "people_behind_count" in c.measured),
                  _at_least(looks, p.look_back_min_count, True))   # face loss is the cue; the tracking was checked
    return Verdict(status, behind + looks + c.of("touch_miss"))


def consulting_companion(c: Cues, p: PilotParams) -> Verdict:
    """일행과 상의하는 듯함 (dec section 3, row 2).

    Combines: a companion (companion_present: a second box of similar size beside, staying stay_min_s) + the main user
    turning toward the companion's side (yaw_sweep_offscreen with the face seen; research/33 3-3) + mouth moving
    (mouth_moving) + dwell without touching + body still. Excluded: a Face Landmarker that does not smooth
    (num_faces of 2 or more) - events.detect_events then makes no mouth_moving, so jitter is not counted as mouth
    motion. Missing mouth motion (no blendshape column, no smoothing, face_visible_ratio below face_visible_min) is
    left out and the tag is judged on the rest (sem section 3)."""
    companions = c.of("companion_present")
    sides = {e["obs"]["side"] for e in companions} - {None}
    turns = [e for e in c.of("yaw_sweep_offscreen") if e["obs"]["side"] in sides]
    mouth = c.of("mouth_moving") if c.mouth_usable else []
    dwell = c.of("dwell_no_touch")
    status = _all(_found(companions, "companion_box" in c.measured),
                  _found(turns, c.face_ok and bool(sides)),
                  _found(mouth, True) if c.mouth_usable else True,
                  _no_touch(c, dwell),
                  c.body_still)
    return Verdict(status, companions + turns + mouth + dwell, () if c.mouth_usable else ("mouth_moving",))


def looking_around(c: Cues, p: PilotParams) -> Verdict:
    """무언가를 찾는 듯함 (dec section 3, row 3).

    Combines: large off-screen head turns, sweep_min_count or more (yaw_sweep_offscreen, and look_back - a turn far
    enough to lose the face is counted by 'face lost + body remains', dec section 3 note) + dwell without touching +
    body still + nobody standing behind (no people_behind event). Excluded: the small yaw of reading the menu (it
    stays inside offscreen_yaw_deg, so it makes no turn event)."""
    turns = c.of("yaw_sweep_offscreen", "look_back")
    dwell = c.of("dwell_no_touch")
    nobody_behind = not c.of("people_behind") if "people_behind_count" in c.measured else None
    status = _all(_at_least(turns, p.sweep_min_count, c.face_ok), _no_touch(c, dwell), c.body_still, nobody_behind)
    return Verdict(status, turns + dwell)


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
    return [{"event_id": e["event_id"], "obs": key, "value": value, "t": e["t_start"]}
            for e in _ordered(events) for key, value in e["obs"].items()]


def _strong(v: Verdict, p: PilotParams) -> bool:
    return v.status is True and len(v.support) >= p.min_events


def _entry(name: str, v: Verdict, p: PilotParams) -> dict:
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
        name = UNKNOWN if tied else leader
    else:
        name = UNKNOWN if open_tags else NONE
    return name, [n for n in open_tags if n != name and verdicts[n].support]   # no evidence, no alternative


def assess(rows: list, t_end: float, params: PilotParams, *, landmarker_num_faces: int) -> tuple:
    """(output, events) for the window [t_end - window_s, t_end] of the observation rows (features.COLUMNS plus the
    optional columns of events.py). The evidence ids point into the returned events. The output passes check_output,
    or this raises ValueError.

    landmarker_num_faces = the num_faces setting of the Face Landmarker behind the rows (app/inference/vision.py: 1)."""
    t0 = t_end - params.window_s
    window = [r for r in rows if t0 <= float(r["t_s"]) <= t_end]
    cues = observe_window(window, params, landmarker_num_faces=landmarker_num_faces)
    verdicts = {name: rule(cues, params) for name, rule in RULES.items()}
    name, alternatives = _decide(cues, verdicts, params)
    chosen = verdicts.get(name)
    support = chosen.support if chosen else []
    out = {
        "name": name,
        "display_text": DISPLAY_TEXT[name],
        "window_s": [t0, t_end],
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
def _check_entry(entry: dict, by_id: dict, t0: float, t1: float) -> list:
    """Display text and evidence of the output or of one alternative."""
    name = entry.get("name")
    problems = []
    if entry.get("display_text") != DISPLAY_TEXT.get(name):
        problems.append(f"{name}: display_text {entry.get('display_text')!r} is not the fixed text of the name")
    ids = set()
    for item in entry.get("evidence", []):
        if set(item) != set(EVIDENCE_KEYS):
            problems.append(f"{name}: evidence item {item!r} does not have the keys {EVIDENCE_KEYS}")
            continue
        event = by_id.get(item["event_id"])
        if event is None:
            problems.append(f"{name}: evidence names no event of this window: {item['event_id']!r}")
            continue
        ids.add(item["event_id"])
        if not (t0 <= event["t_start"] and event["t_end"] <= t1):
            problems.append(f"{name}: event {item['event_id']} lies outside the window {t0}..{t1}")
        if item["obs"] not in event["obs"] or event["obs"][item["obs"]] != item["value"]:
            problems.append(f"{name}: {item['obs']}={item['value']!r} is not an observation of {item['event_id']}")
        if item["t"] != event["t_start"]:
            problems.append(f"{name}: t {item['t']!r} is not the start of {item['event_id']}")
    confidence = entry.get("confidence")
    if isinstance(confidence, dict):
        if confidence.get("events") != len(ids):
            problems.append(f"{name}: confidence events {confidence.get('events')!r} != {len(ids)} evidence events")
        if not isinstance(confidence.get("quality_ok"), bool):
            problems.append(f"{name}: quality_ok is not true or false")
    elif confidence != UNKNOWN:
        problems.append(f"{name}: confidence {confidence!r} is neither 'unknown' nor {{events, quality_ok}}")
    return problems


def check_output(out: dict, events: list, params: PilotParams) -> list:
    """Problems of one output against the events of its window; [] = it passes. The check rules as code:
    - rule 1, evidence linked to events (sem section 4): every evidence item names an event of this window that lies
      inside window_s and repeats one of that event's observations (obs, value) at the event's start t;
    - display text: the fixed text of the name (DISPLAY_TEXT), never free text;
    - rule 2, 'unknown' (sem section 4): name "unknown" if and only if confidence "unknown"; a named tag has at least
      min_events supporting events and a window that met track_conf_min; "unknown" and "none" carry no evidence of
      their own, and "none" no alternatives."""
    missing = [k for k in OUTPUT_KEYS if k not in out]
    if missing:
        return [f"missing keys {missing}"]
    problems = [] if out["source"] == SOURCE else [f"source {out['source']!r} is not {SOURCE!r}"]
    name, confidence = out["name"], out["confidence"]
    if name not in DISPLAY_TEXT:
        return problems + [f"name {name!r} is not a tag, {UNKNOWN!r} or {NONE!r}"]
    t0, t1 = out["window_s"]
    by_id = {e["event_id"]: e for e in events}
    problems += _check_entry(out, by_id, t0, t1)
    if (name == UNKNOWN) != (confidence == UNKNOWN):
        problems.append(f"name {name!r} with confidence {confidence!r}: 'unknown' goes only with 'unknown'")
    if name in RULES:
        count = confidence.get("events") if isinstance(confidence, dict) else None
        if isinstance(count, int) and count < params.min_events:   # a non-number is reported by _check_entry
            problems.append(f"{name}: {count} events, fewer than min_events")
        track = out["quality"].get("track_conf")
        if track is None or track < params.track_conf_min:
            problems.append(f"{name}: track_conf {track!r} below track_conf_min")
    elif out["evidence"]:
        problems.append(f"{name!r} carries evidence of its own")
    if name == NONE and out["alternatives"]:
        problems.append("'none' has alternatives")
    seen = set()
    for alt in out["alternatives"]:
        alt_name = alt.get("name")
        if alt_name not in RULES or alt_name == name or alt_name in seen:
            problems.append(f"alternative {alt_name!r} is not another tag")
            continue
        seen.add(alt_name)
        problems += _check_entry(alt, by_id, t0, t1)
    return problems
