"""Rule table v0 for the scenes 3-1 뒤에 줄, 3-2 일행 상의, 4-1 손 떨림, 4-2 헤맴, run in the backend.

A port of ai-engine/app/modules/vision/judgment/rule_table_v0.py (vision owner, 2026-10-22), kept row for
row so the two agree: the table and its names are the spec. decide() is a pure function of (window input,
session state, params) and returns one decision per window; apply() / tick() / react() change the session state
the way JP 0-1 describes. Thresholds come from DecisionParams only; this file holds none.

  scene  support                 output   rank  opens when                                              Jev
  3-2    wait_hold_timer         wait     2     tag consulting_companion                                none
  3-1    remaining_steps_notice  apply    3     tag looking_back_with_people_behind, steps left/unknown  fit, or choice
         (delay_responsibility_notice with the switch on)                                               with DEFER
  4-1    large_button            propose  4     near misses fixed at once >= tremor_miss_min (facing),  fit (facing)
                                                >= tremor_miss_min_no_gaze (gaze unknown); steps left
  4-2    highlight_next_action   apply    7     a back, or a pause after choosing >= lost_pause_s      fit
                                                (lost_pause_s_vision with looking_around or a gaze)
Withdraw: 3-2 touch_resumed; 3-1, 4-2 cart_progress; 4-1 none. An unknown tag opens no tag row; the touch rows
still run. The 3-2 wait is a session action: the withdrawn filter skips it and it carries session_signal
{name: hold_timer} when opened and in every measurable window that keeps it.
"""

from __future__ import annotations

import copy
from dataclasses import replace

from app.modules.decision.schemas import (
    AROUND, BIG, BUSY, DEFER, DELAY, HIGHLIGHT, HOLD_TIMER, NOTICE, QUEUE, QUIET_APPLY, TAGS, UNKNOWN, WAIT,
    Decision, DecisionParams, Held, Row, SessionState, WindowInput,
)

WHAT = {   # one English line per support for Jev (names and English only)
    WAIT: "Wait and show nothing while the user talks with a companion",
    NOTICE: "Tell the user how many steps are left before payment, without a popup",
    DELAY: "Tell the user that waiting customers are the store's matter, without a popup",
    BIG: "Ask the user whether the buttons should become bigger",
    HIGHLIGHT: "Highlight the next action on this screen with one line of guidance, without changing the layout",
    DEFER: "Show nothing now and do not ask about bigger buttons while people wait behind the user",
}
FIT_CRITERIA = {
    NOTICE: {"true": "People are waiting behind the user and the user still has steps left before payment, so telling "
                     "them the remaining steps helps them finish",
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
CHOICE_CRITERIA = {   # the 3-1 choice
    NOTICE: "Tell the user how many steps are left before payment, without a popup, and keep the bigger-button question "
            "for a later window; fits when near misses keep repeating on the same button or quick corrections follow "
            "them",
    DEFER: "Show nothing now and do not ask about bigger buttons while people wait behind the user; fits when near "
           "misses on the same button are few and the user keeps looking back at the people waiting",
}

# Execution fields (JP 2-5 decision_meta): notices carry the progress line and a text id; the 4-2 highlight targets
# the options dialog's cart-add button on the menu and the cart rows' decrease buttons on the review screen.
NOTICE_EXECUTION = {NOTICE: ("cart_progress", "steps_left_notice"), DELAY: ("cart_progress", "delay_responsibility_notice")}
CART_ADD_TARGET = "cart-add"
CART_DECREASE_TARGETS = "cart:*:decrease"


def execution(support: str | None, inp: WindowInput) -> dict:
    target, message = NOTICE_EXECUTION.get(support, (None, None))
    if support == HIGHLIGHT:
        if inp.screen == "menu" and inp.options_open is True:
            target = CART_ADD_TARGET
        elif inp.screen == "review":
            target = CART_DECREASE_TARGETS
    return {"steps_left": inp.steps_left, "target_id": target, "message_id": message}


def _withdrawn(state: SessionState, support: str, scope: tuple) -> bool:
    return any(w["support"] == support and tuple(w["scope"]) == tuple(scope) for w in state.withdrawn)


def _withdraw_met(condition: str | None, inp: WindowInput) -> bool:
    if condition == "touch_resumed":
        return bool(inp.taps_segment)
    if condition == "cart_progress":
        return inp.progress_segment is True
    return False


def candidate_rows(inp: WindowInput, state: SessionState, p: DecisionParams, tag: str | None, tag_scope: tuple,
                   screen_scope: tuple) -> list[Row]:
    """The rows this window opens after the JP 0-2 filter (active, refused, the held support, the same scope's
    withdrawn; the withdrawn filter is for supports shown on the screen, not for the 3-2 wait)."""
    excluded = set(state.active) | set(state.refused) | ({state.held.support} if state.held else set())

    def free(support: str, scope: tuple) -> bool:
        return support not in excluded and not _withdrawn(state, support, scope)

    rows: list[Row] = []
    if tag == BUSY and WAIT not in excluded:                     # 3-2: a session action, re-opened at every trigger
        rows.append(Row(WAIT, "3-2", "wait", 2, True, "touch_resumed", False, cues={"tag": tag}))

    steps_open = inp.steps_left is None or inp.steps_left > 0
    tremor = None                                                                    # 4-1 (steps left)
    deferred = _withdrawn(state, DEFER, tag_scope)
    if steps_open and inp.fixes_recent is not None and not deferred and free(BIG, screen_scope):
        cues = {"misses_recent": inp.misses_recent, "fixes_recent": inp.fixes_recent, "facing_screen": inp.gaze}
        if inp.gaze is True and inp.fixes_recent >= p.tremor_miss_min:
            tremor = Row(BIG, "4-1", "propose", 4, False, None, True, "fit", "wait", cues=cues)
        elif inp.gaze is None and inp.fixes_recent >= p.tremor_miss_min_no_gaze:    # raised criterion, no Jev
            tremor = Row(BIG, "4-1", "propose", 4, False, None, False, None, None, cues={**cues, "raised": True})
    if tremor is not None:
        rows.append(tremor)
    gated = tremor is not None and inp.gaze is True   # a 4-1 row without the gaze gate is no defer premise

    group_held = state.held is not None and state.held.support in (NOTICE, DELAY)
    if tag == QUEUE and steps_open and not group_held:                               # 3-1
        if p.delay_notice_on:
            options = (DELAY,) if free(DELAY, tag_scope) else ()
        else:
            options = (NOTICE,) if free(NOTICE, tag_scope) else ()
            if options and p.defer_option_on and gated and free(DEFER, tag_scope):
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


def evidence_counts(situation: dict | None) -> dict:
    """{event kind: number of events} behind the situation tag (names and counts only)."""
    kinds: dict[str, int] = {}
    for eid in {item["event_id"] for item in (situation or {}).get("evidence", []) if "event_id" in item}:
        kind = eid.split("@")[0]
        kinds[kind] = kinds.get(kind, 0) + 1
    return dict(sorted(kinds.items()))


def situation_known(situation: dict | None) -> bool:
    """A judged situation with a tag other than unknown. Not judged and unknown both mean "do not know"."""
    return situation is not None and situation.get("name") not in (None, UNKNOWN)


def jev_state(inp: WindowInput, state: SessionState) -> dict:
    """The Jev state of a window: code-made names and values only, in the vision rule table's field names.

    Nothing is asserted that was not observed: without a known situation the tag and looking_around are null,
    not "no tag" and "not looking around".
    """
    sit = inp.situation or {}
    known = situation_known(inp.situation)
    conf = sit.get("confidence")
    return {
        "situation": {"tag": sit.get("name") if known else None, "evidence": evidence_counts(sit) if known else {},
                      "dropped_cues": ["mouth_moving"] if isinstance(conf, dict) and not conf.get("quality_ok") else []},
        "screen": {"name": inp.screen, "steps_left": inp.steps_left},
        "touch": {"misses_recent": inp.misses_recent, "fixes_recent": inp.fixes_recent, "backs_recent": inp.backs_recent,
                  "pause_s": None if inp.pause_s is None else round(inp.pause_s, 1)},
        "vision": {"facing_screen": inp.gaze, "looking_around": (sit.get("name") == AROUND) if known else None},
        "session": {"active": list(state.active), "held": state.held.support if state.held else None,
                    "refused": list(state.refused), "withdrawn": [w["support"] for w in state.withdrawn]},
    }


def jev_request(row: Row, kind: str, inp: WindowInput, state: SessionState) -> dict:
    """The Jev question of a decision: {"state", "questions"}. The model is added by the caller (backend setting)."""
    if kind == "choice":
        questions = {"queue_support": {
            "type": "choice",
            "instructions": "Choose the one support the kiosk gives the user described in `situation`, `screen` and "
                            "`touch` in this window.",
            "criteria": {o: CHOICE_CRITERIA[o] for o in row.options},
        }}
    else:
        questions = {"proposal_fits": {
            "type": "noul",
            "instructions": {"proposed_support": {"name": row.support, "what": WHAT[row.support]},
                             "question": "Does `proposed_support` fit the user described in `situation`, `screen`, "
                                         "`touch`, `vision` and `session`?"},
            "criteria": FIT_CRITERIA[row.support],
        }}
    return {"state": jev_state(inp, state), "questions": questions}


def _policy(row: Row, asked: bool, p: DecisionParams) -> dict:
    """JP 2-1 policy: None thresholds = no criterion yet (shadow)."""
    choice = row.jev_kind == "choice"
    return {"kind": row.jev_kind if asked else None, "ask_jev": asked, "lowered_action": row.lowered_action,
            "raised_action": None, "T_LOWER": None, "T_AID": None, "T_CHOICE": None,
            "default_choice": row.options[0] if row.options else None,
            "choice_actions": {o: ("apply" if o != DEFER else "wait") for o in row.options} if choice else None,
            "jev_deadline": "next_segment", "no_response_s": p.no_response_s}


def _window_scopes(inp: WindowInput, state: SessionState) -> tuple[bool, str | None, tuple, tuple, dict]:
    """(situation known, tag of this window, tag scope, screen scope, meta): the one place the scopes are made."""
    known = situation_known(inp.situation)
    name = inp.situation.get("name") if known else None
    tag = name if known else state.tag_last                 # an unknown window continues the previous tag
    screen_changed = inp.screen != state.screen_last
    tag_since = inp.t if (tag != state.tag_last or screen_changed or state.tag_since is None) else state.tag_since
    screen_since = inp.t if (screen_changed or state.screen_since is None) else state.screen_since
    meta = {"t": inp.t, "tag": tag, "tag_since": tag_since, "screen": inp.screen, "screen_since": screen_since,
            "situation_known": known}
    return known, name, ("tag", tag, tag_since), ("screen", inp.screen, screen_since), meta


def _transition(held: Held | None, row: Row) -> str:
    """open | replace | keep for the best row against the held decision (JP 0-3 ④⑤⑥)."""
    if held is None:
        return "open"
    if held.action == "propose":                                                    # an open ask stays
        return "replace" if (row.action == "wait" and row.rank < held.rank) else "keep"
    quiet_shown = held.status == "shown" and held.action == "apply" and held.support in QUIET_APPLY
    return "replace" if (row.rank < held.rank or (quiet_shown and row.action == "propose")) else "keep"


def decide(inp: WindowInput, state: SessionState, params: DecisionParams) -> Decision:
    """One decision for one window (JP 0-3 order: not measurable -> keep / none; withdraw; no row -> keep / none;
    nothing held -> open; a held ask stays unless a 3-2 wait ranked ahead comes; otherwise replace when the row ranks
    ahead or a shown quiet notice meets an ask; else keep)."""
    known, name, tag_scope, screen_scope, meta = _window_scopes(inp, state)
    held = state.held
    if not inp.measurable:
        if held is not None and held.status == "shown":
            return _keep(held, meta, "window not measurable", measurable=False)
        return Decision("none", meta, reason="window not measurable")
    if held is not None and _withdraw_met(held.withdraw_on, inp):
        return Decision("withdraw", meta, held.support, None, held.action, held.rank, held.scope, held.withdraw_on,
                        decision_id=held.decision_id, reason=f"withdraw condition {held.withdraw_on}")
    rows = candidate_rows(inp, state, params, name if name in TAGS else None, tag_scope, screen_scope)
    if not rows:
        return _keep(held, meta, "no candidate row", measurable=True) if held is not None else Decision(
            "none", meta, reason="no candidate row")
    row = min(rows, key=lambda r: r.rank)
    transition = _transition(held, row)
    if transition == "keep":
        return _keep(held, meta, f"held {held.support} stays; row {row.support} waits", measurable=True)
    scope = tag_scope if row.from_tag else screen_scope
    asked = row.ask_jev and known                           # fit / choice need a known situation
    return Decision(transition, meta, row.support, row.scene, row.action, row.rank, scope, row.withdraw_on,
                    _policy(row, asked, params), jev_request(row, row.jev_kind, inp, state) if asked else None,
                    row.cues, reason=f"row {row.scene} rank {row.rank}",
                    session_signal={"name": HOLD_TIMER} if row.support == WAIT else None,
                    execution=execution(row.support, inp))


def allowed_supports(inp: WindowInput, state: SessionState, params: DecisionParams) -> list[str]:
    """What the rule table could open in this window, ranked, options included: the choice set for a Jev stage.

    The same scopes, filter and transition as decide(): nothing when the window is not measurable or the held
    decision is being withdrawn. Each candidate row is checked with the same transition rule decide() applies
    (_transition(held, row)); a row the table would answer with keep is left out, so a row that cannot displace
    the held decision (e.g. 4-2 against an open ask) is never offered. Nothing when no row is left. The 3-1 row's
    options (notice, defer) are listed as separate choices.
    """
    if not inp.measurable:
        return []
    known, name, tag_scope, screen_scope, _ = _window_scopes(inp, state)
    held = state.held
    if held is not None and _withdraw_met(held.withdraw_on, inp):
        return []
    rows = candidate_rows(inp, state, params, name if name in TAGS else None, tag_scope, screen_scope)
    rows = [row for row in rows if _transition(held, row) != "keep"]
    if not rows:
        return []
    supports: list[str] = []
    for row in sorted(rows, key=lambda r: r.rank):
        for support in (row.options or (row.support,)):
            if support not in supports:
                supports.append(support)
    return supports


def _keep(held: Held, meta: dict, reason: str, measurable: bool) -> Decision:
    """The held decision again: same id, support, policy, cues and execution fields, no new Jev question."""
    signal = {"name": HOLD_TIMER} if (held.action == "wait" and measurable) else None
    return replace(held.decision, transition="keep", meta=meta, reason=reason, jev_request=None, session_signal=signal)


def _end(state: SessionState, decision_id: str) -> None:
    """The end of a decision: withdrawn items it displaced become candidates again."""
    state.withdrawn = [w for w in state.withdrawn if w.get("replaced_by") != decision_id]


def apply(state: SessionState, decision: Decision) -> tuple[SessionState, Decision]:
    """(new state, decision with its id): store the transition (JP 0-1 transition table)."""
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
        decision = replace(decision, decision_id=new_id)
        s.held = Held(new_id, decision.support, decision.action, decision.rank, decision.scope, decision.withdraw_on,
                      "shown", m["t"], decision)
    elif decision.transition == "withdraw" and s.held is not None:
        s.withdrawn.append({"support": s.held.support, "scope": s.held.scope, "reason": "withdraw",
                            "replaced_by": None})
        _end(s, s.held.decision_id)
        s.held = None
    return s, decision


def tick(state: SessionState, t: float, params: DecisionParams) -> tuple[SessionState, str | None]:
    """No response: a shown ask unanswered for no_response_s seconds is withdrawn. (new state, withdrawn id)."""
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
    """A reaction from the front end. On the held decision (decision_id): accept -> active, refuse / revert ->
    refused. On an active support (support): revert -> out of active into refused. Anything else changes nothing."""
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
