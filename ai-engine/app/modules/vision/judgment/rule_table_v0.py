"""판단 층 규칙표 v0 for the scenes 3-1 뒤에 줄, 3-2 일행 상의 · 딴 일, 4-1 손 떨림, 4-2 헤맴.

Sources: JP = 3_design/jev_pipeline_2026-10-13.md v2.2 (section 0-1 session state, 0-2 the rule table, 0-3 transitions
and the rank table, 0-4 the Jev places, 0-9 shadow mode, the scene table, 2-1 / 2-2 the code and request sketch);
tree = 3_design/scenario_tree_v1_2026-10-13.md v1.7 (table 3-가 opening signals and supports, 3-나 withdraw times,
section 4 the order). Only these four scenes are built: session signals (2-2, absence), start supports (1-1, 1-2),
2-1 and the automatic staff call (rank 9, conditions undecided in JP) are not.

decide(window input, session state, params) is a pure function of its arguments and returns ONE decision per window
(JP 0-2 '행 하나'): the support, its output form (기다림 · 묻기 · 바로 적용; 직원 호출 has no row yet), the transition of
the held decision (open | replace | keep | withdraw | none), scope, rank, withdraw condition, policy values and, in
shadow mode, the Jev question (jev_stub.ShadowJev records it; the screen follows the rule result). apply() / tick() /
react() emulate the backend's part of JP 0-1 (held · active · refused · withdrawn) so a replay can run windows in a row.

Rows (JP scene table; rank = JP 0-3 rank table):
  scene  support                 output (intervention)  rank  opens when                                   Jev
  3-2    wait_hold_timer         wait (기다림)            2     tag consulting_companion (일행 길; the 고개 숙임  none
                                                                길 needs a look_down event that does not exist)
  3-1    remaining_steps_notice  apply (바로 적용)        3     tag looking_back_with_people_behind and steps  2 options: choice;
         (delay_responsibility_notice when the condition switch is on)  left (or unknown)                   1: fit / none
  4-1    large_button            propose (묻기)           4     misses in the last touch_span_s >=            fit (facing);
                                                                tremor_miss_min while facing the screen;     none (gaze
                                                                >= tremor_miss_min_no_gaze when the camera    unknown)
                                                                cannot tell; no row while looking away
  4-2    highlight_next_action   apply (바로 적용, 조용히)  7     a back, or a pause >= lost_pause_s            fit
                                                                (lost_pause_s_vision with looking_around or
                                                                facing the screen), on a screen with steps left
Withdraw conditions (tree 3-나): 3-2 'touch_resumed' (터치가 이어짐), 3-1 and 4-2 'cart_progress' (장바구니가 나아감 /
다음 단계로 나아감: a press on the cart-add button or a screen forward), 4-1 none (반응 · 무응답으로 끝남).
A tag that is 'unknown' (or not judged) opens no tag row: the touch rows still run (JP 0-2: 상황 근거만 빼고).

The fit criteria of large_button and highlight_next_action are worded here as a draft (JP 2-2 gives only the 3-1 texts).
Every count and time compared here is a params.PilotParams field (its source text says [파일럿] where no standard
exists); this file holds no threshold.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace

from ..situation import TAGS, UNKNOWN
from .jev_stub import JEV_MODEL

QUEUE, BUSY, AROUND = "looking_back_with_people_behind", "consulting_companion", "looking_around"
SCENE_OF_TAG = {QUEUE: "queue", BUSY: "busy", AROUND: "lost"}   # tree 5-1 index 1 (looking_around: 4-2's aid)
WAIT, NOTICE, DELAY, BIG, HIGHLIGHT = ("wait_hold_timer", "remaining_steps_notice", "delay_responsibility_notice",
                                       "large_button", "highlight_next_action")
DEFER = "defer_big_button_question"       # JP 0-2: an option of the 3-1 choice, not a row
INTERVENTION = {"wait": "기다림", "propose": "묻기", "apply": "바로 적용", "call_staff": "직원 호출"}
# contract FeatureWindowResponse.support (UIPreset, requires_confirmation) per support: JP 2-5 table
CONTRACT_FORM = {WAIT: ("none", False), NOTICE: ("step_guide", False), DELAY: ("step_guide", False),
                 BIG: ("large_button", True), HIGHLIGHT: ("none", False), "call_staff": ("none", False)}
QUIET_APPLY = {NOTICE, DELAY, HIGHLIGHT}  # JP 2-1: notices and highlights
WHAT = {   # one English line per support for Jev (JP 2-2: names and English only)
    NOTICE: "Tell the user how many steps are left before payment, without a popup",
    DELAY: "Tell the user that waiting customers are the store's matter, without a popup",
    BIG: "Ask the user whether the buttons should become bigger",
    HIGHLIGHT: "Highlight the next action on this screen with one line of guidance, without changing the layout",
    DEFER: "Show nothing now and do not ask about bigger buttons while people wait behind the user",
}
FIT_CRITERIA = {
    NOTICE: {"true": "People are waiting behind the user and the user still has steps left before payment, so telling "
                     "them the remaining steps helps them finish",                                  # JP 2-2
             "false": "Nobody is waiting behind the user, no steps are left, or the user already has or refused this "
                      "support"},
    BIG: {"true": "Presses keep landing just outside the buttons while the user faces the screen, so bigger buttons "
                  "would help",
          "false": "The misses come from scrolling or quick quantity taps, the user is not facing the screen, or the "
                   "user already has or refused bigger buttons"},
    HIGHLIGHT: {"true": "The user faces the screen but goes back or pauses without choosing, so pointing at the next "
                        "action helps",
                "false": "The user reads or chooses steadily, talks with a companion, or already has or refused this "
                         "help"},
}
CHOICE_CRITERIA = {   # JP 2-2, the 3-1 Choice
    NOTICE: "Tell the user how many steps are left before payment, without a popup, and keep the bigger-button question "
            "for a later window; fits when near misses keep repeating on the same button or quick corrections follow "
            "them",
    DEFER: "Show nothing now and do not ask about bigger buttons while people wait behind the user; fits when near "
           "misses on the same button are few and the user keeps looking back at the people waiting",
}


@dataclass(frozen=True)
class WindowInput:
    """What one window gives the rule table (JP 0-2 '입력 한 줄': the parts these four scenes read)."""
    t: float                               # window end (s, video time)
    measurable: bool                       # contract AnalyzeResponse.measurable of this segment
    situation: dict | None = None          # situation.assess output; None = not judged (no value bundle)
    screen: str | None = None              # screen id at t from the touch log; None = no log
    steps_left: int | None = None          # screens left before the order ends; None = unknown
    gaze: bool | None = None               # facing the screen at the segment end; None = the camera cannot tell
    misses_recent: int | None = None       # presses outside every button in the last touch_span_s; None = no log
    backs_recent: int | None = None        # backs (review -> menu) in the last touch_span_s
    pause_s: float | None = None           # seconds without a press on this screen visit
    taps_segment: int | None = None        # presses in this segment
    progress_segment: bool | None = None   # a cart-add press or a screen forward in this segment


@dataclass(frozen=True)
class Row:
    support: str
    scene: str
    action: str
    rank: int
    from_tag: bool
    withdraw_on: str | None
    ask_jev: bool
    jev_kind: str | None = None            # 'fit' | 'choice'
    lowered_action: str | None = None
    options: tuple = ()                    # 3-1 group: allowed options, default first
    cues: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Held:
    decision_id: str
    support: str
    action: str
    rank: int
    scope: tuple
    withdraw_on: str | None
    status: str          # 'shown': in shadow mode a decision is shown in the response of the window it opens
    shown_t: float


@dataclass
class SessionState:
    """The backend's session state of JP 0-1 (the parts these scenes use); a replay emulates it window by window."""
    held: Held | None = None
    active: list = field(default_factory=list)
    refused: list = field(default_factory=list)
    withdrawn: list = field(default_factory=list)   # {"support", "scope", "reason", "replaced_by"}
    tag_last: str | None = None
    tag_since: float | None = None
    screen_last: str | None = None
    screen_since: float | None = None
    next_id: int = 1

    def snapshot(self) -> dict:
        held = None if self.held is None else {"decision_id": self.held.decision_id, "support": self.held.support,
                                               "action": self.held.action, "status": self.held.status,
                                               "scope": list(self.held.scope)}
        return {"held": held, "active": list(self.active), "refused": list(self.refused),
                "withdrawn": [{**w, "scope": list(w["scope"])} for w in self.withdrawn]}


@dataclass(frozen=True)
class Decision:
    transition: str                        # open | replace | keep | withdraw | none
    meta: dict
    support: str | None = None
    scene: str | None = None
    action: str | None = None
    rank: int | None = None
    scope: tuple | None = None
    withdraw_on: str | None = None
    policy: dict | None = None
    jev_request: dict | None = None
    cues: dict = field(default_factory=dict)
    decision_id: str | None = None         # keep / withdraw: the held decision's id; open / replace: set by apply()
    reason: str = ""

    def form(self) -> tuple:
        """(preset, requires_confirmation) of contract SupportDecision for this decision (JP 2-5)."""
        if self.transition in ("open", "replace", "keep") and self.support in CONTRACT_FORM:
            return CONTRACT_FORM[self.support]
        return "none", False

    def to_dict(self) -> dict:
        preset, confirm = self.form()
        return {"transition": self.transition, "support": self.support, "scene": self.scene, "action": self.action,
                "intervention": INTERVENTION.get(self.action), "rank": self.rank,
                "scope": None if self.scope is None else list(self.scope), "withdraw_on": self.withdraw_on,
                "decision_id": self.decision_id, "preset": preset, "requires_confirmation": confirm,
                "policy": self.policy, "jev_request": self.jev_request, "cues": self.cues, "meta": self.meta,
                "reason": self.reason}


def _withdrawn(state: SessionState, support: str, scope: tuple) -> bool:
    return any(w["support"] == support and tuple(w["scope"]) == tuple(scope) for w in state.withdrawn)


def _withdraw_met(condition: str | None, inp: WindowInput) -> bool:
    if condition == "touch_resumed":
        return bool(inp.taps_segment)
    if condition == "cart_progress":
        return inp.progress_segment is True
    return False


def candidate_rows(inp: WindowInput, state: SessionState, p, tag: str | None, tag_scope: tuple,
                   screen_scope: tuple) -> list:
    """The rows this window opens, after the JP 0-2 filter (active, refused, the held support, the same scope's
    withdrawn). tag = the situation tag of this window, None when unknown / not judged."""
    excluded = set(state.active) | set(state.refused) | ({state.held.support} if state.held else set())

    def free(support: str, scope: tuple) -> bool:
        return support not in excluded and not _withdrawn(state, support, scope)

    rows = []
    if tag == BUSY and free(WAIT, tag_scope):                                       # 3-2
        rows.append(Row(WAIT, "3-2", "wait", 2, True, "touch_resumed", False, cues={"tag": tag}))

    steps_open = inp.steps_left is None or inp.steps_left > 0
    tremor = None                                                                    # 4-1
    deferred = _withdrawn(state, DEFER, tag_scope)
    if inp.misses_recent is not None and not deferred and free(BIG, screen_scope):
        cues = {"misses_recent": inp.misses_recent, "facing_screen": inp.gaze}
        if inp.gaze is True and inp.misses_recent >= p.tremor_miss_min:
            tremor = Row(BIG, "4-1", "propose", 4, False, None, True, "fit", "wait", cues=cues)
        elif inp.gaze is None and inp.misses_recent >= p.tremor_miss_min_no_gaze:   # raised criterion, no Jev
            tremor = Row(BIG, "4-1", "propose", 4, False, None, False, None, None, cues={**cues, "raised": True})
    if tremor is not None:
        rows.append(tremor)

    group_held = state.held is not None and state.held.support in (NOTICE, DELAY)
    if tag == QUEUE and steps_open and not group_held:                               # 3-1
        if p.delay_notice_on:
            options = (DELAY,) if free(DELAY, tag_scope) else ()
        else:
            options = (NOTICE,) if free(NOTICE, tag_scope) else ()
            if options and p.defer_option_on and tremor is not None and free(DEFER, tag_scope):
                options += (DEFER,)
        if options:
            kind = "choice" if len(options) == 2 else ("fit" if options[0] == NOTICE else None)
            rows.append(Row(options[0], "3-1", "apply", 3, True, "cart_progress", kind is not None, kind,
                            "wait" if kind == "fit" else None, options,
                            cues={"tag": tag, "steps_left": inp.steps_left, "options": list(options)}))

    if steps_open and free(HIGHLIGHT, screen_scope):                                 # 4-2
        raised = tag == AROUND or inp.gaze is True
        pause_min = p.lost_pause_s_vision if raised else p.lost_pause_s
        back = inp.backs_recent is not None and inp.backs_recent >= p.lost_back_min
        pause = inp.pause_s is not None and inp.pause_s >= pause_min
        if back or pause:
            rows.append(Row(HIGHLIGHT, "4-2", "apply", 7, False, "cart_progress", True, "fit", "wait",
                            cues={"backs_recent": inp.backs_recent, "pause_s": inp.pause_s, "pause_min_s": pause_min,
                                  "looking_around": tag == AROUND, "facing_screen": inp.gaze}))
    return rows


def _evidence_counts(situation: dict) -> dict:
    """{event kind: number of events} behind the situation tag (names and counts only, JP 0-4)."""
    kinds = {}
    for eid in {item["event_id"] for item in situation.get("evidence", [])}:
        kind = eid.split("@")[0]
        kinds[kind] = kinds.get(kind, 0) + 1
    return dict(sorted(kinds.items()))


def jev_request(row: Row, kind: str, inp: WindowInput, state: SessionState) -> dict:
    """The Jev question of a decision (JP 2-2): state = code-made names and values only, questions in English."""
    sit = inp.situation or {}
    conf = sit.get("confidence")
    st = {"situation": {"tag": sit.get("name"), "evidence": _evidence_counts(sit),
                        "dropped_cues": ["mouth_moving"] if isinstance(conf, dict) and not conf.get("quality_ok")
                        else []},
          "screen": {"name": inp.screen, "steps_left": inp.steps_left},
          "touch": {"misses_recent": inp.misses_recent, "backs_recent": inp.backs_recent,
                    "pause_s": None if inp.pause_s is None else round(inp.pause_s, 1)},
          "vision": {"facing_screen": inp.gaze, "looking_around": sit.get("name") == AROUND},
          "session": {"active": list(state.active), "held": state.held.support if state.held else None,
                      "refused": list(state.refused), "withdrawn": [w["support"] for w in state.withdrawn]}}
    if kind == "choice":
        q = {"queue_support": {"type": "choice",
                               "instructions": "Choose the one support the kiosk gives the user described in "
                                               "`situation`, `screen` and `touch` in this window.",
                               "criteria": {o: CHOICE_CRITERIA[o] for o in row.options}}}
    else:
        q = {"proposal_fits": {"type": "noul",
                               "instructions": {"proposed_support": {"name": row.support, "what": WHAT[row.support]},
                                                "question": "Does `proposed_support` fit the user described in "
                                                            "`situation`, `screen`, `touch`, `vision` and `session`?"},
                               "criteria": FIT_CRITERIA[row.support]}}
    return {"model": JEV_MODEL, "state": st, "questions": q}


def _policy(row: Row, asked: bool, p) -> dict:
    """JP 2-1 policy: None thresholds = 기준 없음 (shadow); the backend reads the rest."""
    choice = row.jev_kind == "choice"
    return {"kind": row.jev_kind if asked else None, "ask_jev": asked, "lowered_action": row.lowered_action,
            "raised_action": None, "T_LOWER": None, "T_AID": None, "T_CHOICE": None,
            "default_choice": row.options[0] if row.options else None,
            "choice_actions": {o: ("apply" if o != DEFER else "wait") for o in row.options} if choice else None,
            "jev_deadline": "next_segment", "no_response_s": p.no_response_s}


def decide(inp: WindowInput, state: SessionState, params) -> Decision:
    """One decision for one window (JP 0-3 check order: 0'' not measurable -> keep / none; ① withdraw; ② no row ->
    keep / none; ④ nothing held -> open; ⑤ a held ask stays unless a 3-2 wait ranked ahead comes; otherwise replace
    when the row ranks ahead or a shown quiet notice meets an ask; ⑥ keep)."""
    sit = inp.situation
    known = sit is not None and sit.get("name") != UNKNOWN
    name = sit.get("name") if known else None
    tag = name if known else state.tag_last                 # an unknown window continues the previous tag (JP 0-1)
    screen_changed = inp.screen != state.screen_last
    tag_since = inp.t if (tag != state.tag_last or screen_changed or state.tag_since is None) else state.tag_since
    screen_since = inp.t if (screen_changed or state.screen_since is None) else state.screen_since
    meta = {"t": inp.t, "tag": tag, "tag_since": tag_since, "screen": inp.screen, "screen_since": screen_since,
            "situation_known": known}
    held = state.held
    if not inp.measurable:                                                          # 0''
        if held is not None and held.status == "shown":
            return _keep(held, meta, "window not measurable")
        return Decision("none", meta, reason="window not measurable")
    if held is not None and _withdraw_met(held.withdraw_on, inp):                   # ①
        return Decision("withdraw", meta, held.support, None, held.action, held.rank, held.scope, held.withdraw_on,
                        decision_id=held.decision_id, reason=f"withdraw condition {held.withdraw_on}")
    tag_scope = ("tag", tag, tag_since)
    screen_scope = ("screen", inp.screen, screen_since)
    rows = candidate_rows(inp, state, params, name if name in TAGS else None, tag_scope, screen_scope)
    if not rows:                                                                    # ②
        return _keep(held, meta, "no candidate row") if held is not None else Decision("none", meta,
                                                                                       reason="no candidate row")
    row = min(rows, key=lambda r: r.rank)
    if held is None:                                                                # ④
        transition = "open"
    elif held.action == "propose":                                                  # ⑤ an open ask stays
        transition = "replace" if (row.action == "wait" and row.rank < held.rank) else "keep"
    else:
        quiet_shown = held.status == "shown" and held.action == "apply" and held.support in QUIET_APPLY
        transition = "replace" if (row.rank < held.rank or (quiet_shown and row.action == "propose")) else "keep"
    if transition == "keep":                                                        # ⑥
        return _keep(held, meta, f"held {held.support} stays; row {row.support} waits")
    scope = tag_scope if row.from_tag else screen_scope
    asked = row.ask_jev and known                           # fit / choice need a known situation (JP 0-4)
    return Decision(transition, meta, row.support, row.scene, row.action, row.rank, scope, row.withdraw_on,
                    _policy(row, asked, params), jev_request(row, row.jev_kind, inp, state) if asked else None,
                    row.cues, reason=f"row {row.scene} rank {row.rank}")


def _keep(held: Held, meta: dict, reason: str) -> Decision:
    return Decision("keep", meta, held.support, None, held.action, held.rank, held.scope, held.withdraw_on,
                    decision_id=held.decision_id, reason=reason)


# --- the backend's part, emulated for replay (JP 0-1, transition table) -------------------------------------------
def _end(state: SessionState, decision_id: str):
    """The end of a decision (JP 0-1 '결정의 끝'): withdrawn items it displaced become candidates again."""
    state.withdrawn = [w for w in state.withdrawn if w.get("replaced_by") != decision_id]


def apply(state: SessionState, decision: Decision) -> tuple:
    """(new state, decision with its id): store the transition as the backend would in shadow mode."""
    s = copy.deepcopy(state)
    m = decision.meta
    s.tag_last, s.tag_since, s.screen_last, s.screen_since = m["tag"], m["tag_since"], m["screen"], m["screen_since"]
    if decision.transition in ("open", "replace"):
        new_id = f"d{s.next_id:04d}"
        s.next_id += 1
        if decision.transition == "replace" and s.held is not None:
            s.withdrawn.append({"support": s.held.support, "scope": s.held.scope, "reason": "replace",
                                "replaced_by": new_id})
            for w in s.withdrawn:                                   # items bound to the replaced decision move on
                if w.get("replaced_by") == s.held.decision_id:
                    w["replaced_by"] = new_id
        s.held = Held(new_id, decision.support, decision.action, decision.rank, decision.scope, decision.withdraw_on,
                      "shown", m["t"])
        decision = replace(decision, decision_id=new_id)
    elif decision.transition == "withdraw" and s.held is not None:
        s.withdrawn.append({"support": s.held.support, "scope": s.held.scope, "reason": "withdraw",
                            "replaced_by": None})
        _end(s, s.held.decision_id)
        s.held = None
    return s, decision


def tick(state: SessionState, t: float, params) -> tuple:
    """No response (JP 0-6: the backend's policy time): a shown ask unanswered for no_response_s seconds is withdrawn.
    Returns (new state, withdrawn decision id or None)."""
    h = state.held
    if h is None or h.action != "propose" or h.status != "shown" or t - h.shown_t < params.no_response_s:
        return state, None
    s = copy.deepcopy(state)
    s.withdrawn.append({"support": h.support, "scope": h.scope, "reason": "no_response", "replaced_by": None})
    _end(s, h.decision_id)
    s.held = None
    return s, h.decision_id


def react(state: SessionState, reaction: str, decision_id: str | None = None, support: str | None = None
          ) -> SessionState:
    """A reaction from the front end (JP transition table). On the held decision (decision_id): accept -> active,
    refuse / revert -> refused. On an active support (support): revert -> out of active into refused. Anything else is
    only recorded by the caller (no change; JP 0-1: 반응이 가리키는 결정이 held에도 active에도 없으면 기록만)."""
    if reaction not in ("accept", "refuse", "revert"):
        raise ValueError(f"unknown reaction {reaction!r}")
    s = copy.deepcopy(state)
    if decision_id is not None and s.held is not None and s.held.decision_id == decision_id:
        held_support = s.held.support
        _end(s, decision_id)
        s.held = None
        (s.active if reaction == "accept" else s.refused).append(held_support)
    elif reaction == "revert" and support is not None and support in s.active:
        s.active.remove(support)
        s.refused.append(support)
    return s
