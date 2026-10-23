"""The runtime chain shared by replay.py and live.py.

Per frame (FrameChain.process): features.Observer row (MediaPipe face / face detector / pose, plus blendshapes when
on) -> H1 head boxes (app/inference/head.py) -> main user, companion, people behind and the main user's P1 direction
(columns.py) -> shoulders, mouth_motion -> touch counts since the previous row (touch.py). Each part that is not
available (no ONNX model, blendshapes off, no touch log) leaves its columns blank or absent, so the events layer treats
the cue as missing ('모름'), never as 'absent'.

Per window (WindowJudge.evaluate, one every params.segment_s; the runners add one shorter window for the input's last
stretch, marked 'partial'): situation.assess over [t - window_s, t] with the reasons of an 'unknown' (unknown_reasons),
touch counts of the segment (t - segment_s, t], the rule table v0 (judgment/rule_table_v0.py) on the emulated session
state, the Jev question recorded in shadow mode, and the contract view (contract_view.py). When the touch log's
sessionId changes (a new order or a reload), the emulated session state starts again (tree section 4 ①: 새 세션은
처음부터 다시 판정) and that window's record says session_reset; from then on a window reads only the rows from the
new session's first event (touch.TouchTimeline.session_since), so the previous user's observations stay out of it.
Nothing after t is read, so a replay gives what the kiosk would have given at t.
"""
from __future__ import annotations

import math
import time

from . import columns as C
from .contract_view import to_contract
from .events import SEEN, observe_window
from .judgment import rule_table_v0 as R
from .judgment.jev_stub import ShadowJev
from .situation import RULES, TAGS, UNKNOWN, assess
from .touch import SCREEN_FLOW

LANDMARKER_NUM_FACES = 1        # app/inference/vision.py runs the Face Landmarker with num_faces=1 (smoothing on)
SOURCE_KIND = {"video": "영상", "folder": "이미지", "camera": "카메라"}   # run.py's source_kind column values
BEHIND, COMPANION, AROUND = TAGS


def finite(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


class _Capture:
    """The models behind features.Observer, keeping the last FrameInference (pose, blendshapes) for the columns."""

    def __init__(self, models):
        self.models, self.last = models, None

    def infer(self, frame):
        self.last = self.models.infer(frame)
        return self.last


class FrameChain:
    """One frame -> one row: features.COLUMNS + columns.OPTIONAL_COLUMNS (when their source ran) + touch counts +
    timing (ms_heads, ms_head_dir, ms_chain = wall time of this whole step, cpu_ms_chain = process CPU time)."""

    def __init__(self, models, params, heads=None, direction=None, timeline=None, blendshapes: bool = False,
                 source_kind: str = ""):
        from .features import Observer          # OpenCV; imported here so the window part loads without it
        self.capture = _Capture(models)
        self.observer = Observer(self.capture)
        self.p = params
        self.heads, self.direction, self.timeline = heads, direction, timeline
        self.blendshapes = bool(blendshapes)
        self.source_kind = source_kind
        self.mouth = C.MouthMotion(params.mouth_dials, params.mouth_baseline_s)
        self.prev_t = None

    def process(self, frame) -> dict:
        wall0, cpu0 = time.perf_counter(), time.process_time()
        row, _ = self.observer.process(frame, source_kind=self.source_kind)
        inf = self.capture.last
        t = float(row["t_s"])
        if self.heads is not None:
            heads = self.heads(frame.image)
            roles = C.assign_heads(heads.boxes, heads.frame_wh, C.face_xy(row), self.p)
            probs = None
            row["ms_head_dir"] = 0.0
            if self.direction is not None and roles.primary is not None:
                probs = self.direction.probs(frame.image, heads.boxes_px[[roles.primary]])[0]
                row["ms_head_dir"] = sum(self.direction.last_ms.values())
            row.update(C.head_columns(heads, roles, probs))
            row["ms_heads"] = sum(heads.ms.values())
        row.update(C.shoulder_columns(inf.pose if inf is not None else None))
        face_seen = row.get("face_state") == SEEN
        scores = inf.blendshapes if (self.blendshapes and face_seen and inf is not None) else None
        row["mouth_motion"] = self.mouth.update(t, scores)
        if self.timeline is not None:
            counts = self.timeline.counts(self.prev_t, t)
            row["tap_count"] = None if counts is None else counts["tap_count"]
            row["miss_tap_count"] = None if counts is None else counts["miss_tap_count"]
        self.prev_t = t
        row["ms_chain"] = (time.perf_counter() - wall0) * 1000.0
        row["cpu_ms_chain"] = (time.process_time() - cpu0) * 1000.0
        return row


# --- why a window is 'unknown' (mirrors the rules of situation.py; tests check it against assess) ------------------
def _turn_gaps(c) -> list:
    out = []
    if not c.yaw_ok:
        out.append("yaw_missing")                    # no face frame, or a face frame without a yaw
    if not c.shoulders_ok:
        out.append("shoulder_visibility_missing")    # face lost, body seen, no shoulder visibility
    if c.turns_unresolved:
        out.append("turn_unresolved")                # a head turn broken by a stretch that hides the head
    return out


def missing_cues(tag: str, c, sp) -> list:
    """The cues that keep a tag at 'cannot tell' (status None) in one window, as codes."""
    out = []
    behind_unknown = not c.of("people_behind") and "people_behind_count" not in c.measured
    turns_ok = c.yaw_ok and c.shoulders_ok and not c.turns_unresolved
    if tag == BEHIND:
        if behind_unknown:
            out.append("column:people_behind_count")
        if len(c.of("look_back")) < sp.look_back_min_count and not turns_ok:
            out += _turn_gaps(c)
    elif tag == COMPANION:
        if not c.of("companion_present") and "companion_box" not in c.measured:
            out.append("column:companion_box")
        toward = c.of("yaw_toward_companion") if c.face_ok else []
        if not toward and not (c.face_ok and c.yaw_ok and not c.companion_side_unknown):
            if not c.face_ok:
                out.append("face_visible_ratio<face_visible_min")
            if not c.yaw_ok:
                out.append("yaw_missing")
            if c.companion_side_unknown:
                out.append("companion_side_unknown")
        if c.any_tap is None:
            out.append("column:tap_count")
        if c.body_still is None:
            out.append("body_position_missing")
    elif tag == AROUND:
        turns = c.of("look_back") + (c.of("yaw_sweep_offscreen") if c.face_ok else [])
        if len(turns) < sp.sweep_min_count and not (c.face_ok and turns_ok):
            if not c.face_ok:
                out.append("face_visible_ratio<face_visible_min")
            out += _turn_gaps(c)
        if c.any_tap is None:
            out.append("column:tap_count")
        if c.body_still is None:
            out.append("body_position_missing")
        if behind_unknown:
            out.append("column:people_behind_count")
    return out


def unknown_reasons(rows: list, t_end: float, sp, landmarker_num_faces: int = LANDMARKER_NUM_FACES) -> list:
    """Why the window [t_end - window_s, t_end] is 'unknown' (sem section 4 check rule 2 and the tie row), as a list of
    {code, ...}: no_frames | sensor_failure | tie | missing_cue (per tag, with the missing cues) | too_few_events."""
    t0 = t_end - sp.window_s
    if not any(t0 <= float(r["t_s"]) <= t_end for r in rows):
        return [{"code": "no_frames"}]
    cues = observe_window(rows, (t0, t_end), sp, landmarker_num_faces=landmarker_num_faces)
    if cues.track_conf is None or cues.track_conf < sp.track_conf_min:
        return [{"code": "sensor_failure", "track_conf": cues.track_conf, "track_conf_min": sp.track_conf_min}]
    verdicts = {name: rule(cues, sp) for name, rule in RULES.items()}
    reasons = []
    strong = [n for n in TAGS if verdicts[n].status is True and len(verdicts[n].support) >= sp.min_events]
    if len(strong) >= 2:
        top = max(len(verdicts[n].support) for n in strong)
        tied = [n for n in strong if len(verdicts[n].support) == top]
        if len(tied) >= 2:
            reasons.append({"code": "tie", "tags": tied, "events": top})
    for n in TAGS:
        v = verdicts[n]
        if v.status is None:
            reasons.append({"code": "missing_cue", "tag": n, "missing": missing_cues(n, cues, sp)})
        elif v.status is True and len(v.support) < sp.min_events:
            reasons.append({"code": "too_few_events", "tag": n, "events": len(v.support), "min_events": sp.min_events})
    return reasons


def history_s(bundle) -> float:
    """Seconds of rows a window needs: the window plus gap_s of context before it (a head turn's facing frame, the
    companion's side), doubled for safety; segment_s when there are no situation values."""
    sp = bundle.situation
    if sp is None:
        return max(bundle.chain.segment_s, bundle.chain.touch_span_s)
    return sp.window_s + 2.0 * sp.gap_s


def facing(seg_rows: list, sp) -> bool | None:
    """The rule table's gaze gate (JP 0-2 '고개 방향이 화면 안'): at the last frame of the segment that saw the face or
    the body - True = face seen with |yaw| below offscreen_yaw_deg, False = face seen with |yaw| at or beyond it;
    None = that frame saw the body without the face (the head direction cannot be measured: covered, turned beyond
    the landmarker's range, or lost), no such frame, no yaw, or no situation values. A None window takes the raised
    criterion of the tap rows (tree section 4 ⑦), not the 'looking away' path."""
    if sp is None:
        return None
    for r in reversed(seg_rows):
        if r.get("face_state") == SEEN:
            yaw = finite(r.get("yaw_deg"))
            return None if yaw is None else abs(yaw) < sp.offscreen_yaw_deg
        if r.get("body_state") == SEEN:
            return None
    return None


def _ids(evidence: list) -> list:
    seen = []
    for item in evidence:
        if item["event_id"] not in seen:
            seen.append(item["event_id"])
    return seen


def situation_view(out: dict | None, reasons: list) -> dict:
    """The situation part of a window record: the assess output with its evidence ids listed apart; alternatives keep
    name, confidence and evidence ids."""
    if out is None:
        return {"name": UNKNOWN, "display_text": "", "evidence_ids": [], "evidence": [], "confidence": UNKNOWN,
                "alternatives": [],
                "quality": None, "unknown_reason": reasons, "window_s": None, "source": None}
    return {"name": out["name"], "display_text": out["display_text"], "evidence_ids": _ids(out["evidence"]),
            "evidence": out["evidence"], "confidence": out["confidence"],
            "alternatives": [{"name": a["name"], "confidence": a["confidence"], "evidence_ids": _ids(a["evidence"])}
                             for a in out["alternatives"]],
            "quality": out["quality"], "unknown_reason": reasons, "window_s": out["window_s"],
            "source": out["source"]}


class WindowJudge:
    """Per-window evaluation with the session state of the rule table carried from window to window; a new sessionId
    in the touch log starts the state again and limits the rows to that session (tree section 4 ①)."""

    def __init__(self, bundle, timeline=None, session_id: str = "replay", jev=None):
        self.b = bundle
        self.timeline = timeline
        self.session_id = session_id          # the contract view's session_id
        self.state = R.SessionState()
        self.jev = jev or ShadowJev()
        self.log_session = None               # the touch log's last sessionId seen at a window end

    def _touch(self, t_end: float, seg_len: float) -> tuple:
        p, tl = self.b.chain, self.timeline
        if tl is None:
            return None, None, {"name": None, "steps_left": None, "pause_s": None, "options_open": None}, None, None
        seg = tl.counts(t_end - seg_len, t_end)
        recent = tl.counts(t_end - p.touch_span_s, t_end)
        screen, since = tl.screen_at(t_end)
        steps_left = (len(SCREEN_FLOW) - 1 - SCREEN_FLOW.index(screen)) if screen in SCREEN_FLOW else None
        last_press = tl.last_press(t_end)
        # tree 4-2 '고른 뒤 멈춤': the pause counts from a press of this screen visit; reading a screen without
        # choosing anything yet is not a pause after choosing
        chosen = last_press is not None and since is not None and last_press >= since
        pause = t_end - last_press if chosen else None
        flags = tl.flags(t_end - seg_len, t_end) if seg is not None else None
        progress = None if flags is None else (flags["forward"] or flags["cart_add"])
        return seg, recent, {"name": screen, "steps_left": steps_left, "pause_s": pause,
                             "options_open": tl.options_open_at(t_end)}, progress, flags

    def evaluate(self, rows: list, t_end: float, segment_s: float | None = None) -> dict:
        """One window record. segment_s = the length of this window's segment (rows and touch counts); default the
        bundle's segment_s. A shorter one (the input's last stretch) is recorded as record['partial']."""
        w0 = time.perf_counter()
        p, sp = self.b.chain, self.b.situation
        seg_len = p.segment_s if segment_s is None else segment_s
        # tree section 4 ①: a new session is judged from the start - its state and its rows. The session is read
        # before the situation: after a change of session a window reads only the rows from the session's first event,
        # so the previous user's observations reach neither the situation nor measurable nor the gaze gate
        log_session = None if self.timeline is None else self.timeline.session_at(t_end)
        session_reset = log_session is not None and self.log_session is not None and log_session != self.log_session
        if session_reset:
            self.state = R.SessionState()
        if log_session is not None:
            self.log_session = log_session
        session_start = None if self.timeline is None else self.timeline.session_since(t_end)
        if session_start is not None:
            rows = [r for r in rows if float(r["t_s"]) >= session_start]
        seg_rows = [r for r in rows if t_end - seg_len < float(r["t_s"]) <= t_end]
        if sp is None:
            out, reasons = None, [{"code": "no_value_bundle"}]
        else:
            out, _ = assess(rows, t_end, sp, landmarker_num_faces=LANDMARKER_NUM_FACES)
            reasons = unknown_reasons(rows, t_end, sp) if out["name"] == UNKNOWN else []
        situation = situation_view(out, reasons)
        seg, recent, screen, progress, _ = self._touch(t_end, seg_len)
        face_seen = any(r.get("face_state") == SEEN for r in seg_rows)
        has_touch = seg is not None and (seg["tap_count"] > 0 or seg["back_count"] > 0)
        measurable = bool(has_touch or face_seen)
        gaze = facing(seg_rows, sp)
        self.state, expired = R.tick(self.state, t_end, p)
        held_before = self.state.held.decision_id if self.state.held else None
        inp = R.WindowInput(t=t_end, measurable=measurable, situation=out, screen=screen["name"],
                            steps_left=screen["steps_left"], gaze=gaze,
                            misses_recent=None if recent is None else recent["miss_tap_count"],
                            fixes_recent=None if recent is None else recent["near_miss_fix_count"],
                            backs_recent=None if recent is None else recent["back_count"], pause_s=screen["pause_s"],
                            taps_segment=None if seg is None else seg["tap_count"], progress_segment=progress,
                            options_open=screen["options_open"])
        decision = R.decide(inp, self.state, p)
        self.state, decision = R.apply(self.state, decision)
        withdrawn_id = expired
        if decision.transition == "withdraw":
            withdrawn_id = decision.decision_id
        elif decision.transition == "replace":
            withdrawn_id = held_before
        jev = None
        if decision.jev_request:   # the request itself stays in decision.jev_request and in the ShadowJev log
            entry = self.jev.ask(decision.policy["kind"], decision.jev_request)
            jev = {k: v for k, v in entry.items() if k != "request"}
        d = decision.to_dict() | {"withdrawn_id": withdrawn_id}
        record = {
            "t": round(t_end, 4), "segment_s": [round(t_end - seg_len, 4), round(t_end, 4)],
            "frames": len(seg_rows), "situation": situation, "touch": seg,
            "screen": {**screen, "pause_s": None if screen["pause_s"] is None else round(screen["pause_s"], 3)},
            "vision": vision_summary(seg_rows, gaze), "measurable": measurable, "decision": d,
            "session": self.state.snapshot(), "session_reset": session_reset, "jev": jev,
        }
        if seg_len != p.segment_s:
            record["partial"] = {"segment_s": round(seg_len, 4)}
        record["contract"] = to_contract(record, self.session_id)
        record["ms_window"] = (time.perf_counter() - w0) * 1000.0
        return record


def vision_summary(seg_rows: list, gaze) -> dict:
    """What the camera saw in the segment (observation only)."""
    n = len(seg_rows)

    def mx(key):
        vals = [v for v in (finite(r.get(key)) for r in seg_rows) if v is not None]
        return max(vals) if vals else None
    return {"frames": n,
            "face_seen_ratio": sum(r.get("face_state") == SEEN for r in seg_rows) / n if n else None,
            "body_seen_ratio": sum(r.get("body_state") == SEEN for r in seg_rows) / n if n else None,
            "head_count_max": mx("head_count"), "people_behind_max": mx("people_behind_count"),
            "companion_frames": sum(r.get("companion_box") is not None for r in seg_rows),
            "mouth_motion_max": mx("mouth_motion"), "facing_screen": gaze}
