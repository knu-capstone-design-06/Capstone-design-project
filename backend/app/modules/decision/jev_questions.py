"""The shadow questions: the five state scores of the contract, plus the rule table's own question.

Jev gets one state (the rule table's field names, docs/Jev-Integration.md 9장) and answers each question
with a probability. The scores are recorded only; thresholds and what to do with them are code and are
not agreed yet. Wording is a draft to be revised against pilot recordings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.modules.decision.schemas import (
    FORECAST_HORIZON_S, PILOT_PARAMS, Decision, DecisionParams, SessionState, WindowInput,
)
from app.modules.decision.rule_table import WHAT, allowed_supports, jev_state
from app.modules.sessions.schemas import StateScores, TouchFeatures

# One noul question per contract StateScores field, in the field's name.
STATE_QUESTIONS: dict[str, dict] = {
    "touch_difficulty": {
        "type": "noul",
        "instructions": "Is the user having trouble physically hitting the buttons in this window?",
        "criteria": {"true": "Taps land outside targets near their edges, repeated taps on the same spot, the user "
                             "keeps facing the screen.",
                     "false": "Taps land on targets, or there are no taps because the user is reading or talking."},
    },
    "navigation_difficulty": {
        "type": "noul",
        "instructions": "Is the user lost in the order flow?",
        "criteria": {"true": "Going back, revisiting screens, long pauses with no selection while facing the screen.",
                     "false": "Steady progress through the screens, or a pause explained by the system being busy."},
    },
    "visual_difficulty": {
        "type": "noul",
        "instructions": "Does the user seem unable to read or see the screen well?",
        "criteria": {"true": "Leaning in, large text or high contrast already on, taps far from any target.",
                     "false": "Normal distance and accurate taps."},
    },
    "hesitation": {
        "type": "noul",
        "instructions": "Is the user hesitating rather than acting?",
        "criteria": {"true": "No input for a long time while facing the screen, options opened and closed without "
                             "choosing.",
                     "false": "The user is talking to a companion, looking behind, or the kiosk is processing."},
    },
    "normal": {
        "type": "noul",
        "instructions": "Is the user ordering without any sign of trouble?",
        "criteria": {"true": "Accurate taps, steady progress, no long pauses.", "false": "Any of the difficulties above."},
    },
}
assert set(STATE_QUESTIONS) == set(StateScores.model_fields), "one question per contract state score"


def shadow_state(inp: WindowInput, state: SessionState, touch: TouchFeatures | None) -> dict:
    """The rule table's state plus the window's raw touch counts (the contract's five fields)."""
    result = jev_state(inp, state)
    if touch is not None:
        result["touch"] = {**result["touch"], **touch.model_dump()}
    return result


def shadow_questions(decision: Decision) -> dict[str, dict]:
    """The five state questions, and the decision's own question (fit / choice) when it opened one."""
    questions = dict(STATE_QUESTIONS)
    if decision.jev_request is not None:
        questions.update(decision.jev_request["questions"])
    return questions


@dataclass(frozen=True)
class StageInput:
    """What a Jev stage sees: the window, the session state, the rule table's decision, and the answers of
    the stages before it ({stage name: {question name: answer}})."""

    inp: WindowInput
    state: SessionState
    decision: Decision
    touch: TouchFeatures | None
    previous: dict[str, dict] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)   # the windows before this one, oldest first


class JevStage(Protocol):
    """One Jev call in a chain. Stages run in order; each may read the earlier answers and puts them into its
    own state, so judgments can be stacked (state scores -> support choice -> ...) without touching the service.
    build() returns (state, questions), or None to skip this window."""

    name: str

    def build(self, ctx: StageInput) -> tuple[dict, dict[str, dict]] | None: ...


def with_previous(state: dict, previous: dict[str, dict]) -> dict:
    """Earlier stages' answers under "jev", beside the raw cues, so a later stage can re-read the source."""
    return {**state, "jev": previous} if previous else state


class ScoreStage:
    """Stage 1: the five contract state scores, plus the rule table's own question when it asked one."""

    name = "state_scores"

    def build(self, ctx: StageInput) -> tuple[dict, dict[str, dict]]:
        return with_previous(shadow_state(ctx.inp, ctx.state, ctx.touch), ctx.previous), shadow_questions(ctx.decision)


NO_SUPPORT = "none"


class SupportChoiceStage:
    """Stage 2 (docs 9.5): choose one support among this window's allowed candidates, or none.

    The candidates are what the rule table would open after its filter (active, refused, withdrawn, the held
    one), so Jev never picks a support the rules forbid. Stage 1's scores, when present, are in state.jev.
    Skipped when no row could open this window.
    """

    name = "support_choice"

    def __init__(self, params: DecisionParams = PILOT_PARAMS):
        self._params = params

    def build(self, ctx: StageInput) -> tuple[dict, dict[str, dict]] | None:
        candidates = allowed_supports(ctx.inp, ctx.state, self._params)
        if not candidates:
            return None
        criteria = {support: WHAT[support] for support in candidates if support in WHAT}
        criteria[NO_SUPPORT] = "Show nothing new in this window; the user is doing fine or already has the help they need"
        state = with_previous(shadow_state(ctx.inp, ctx.state, ctx.touch), ctx.previous)
        state["candidates"] = candidates
        return state, {"support_choice": {
            "type": "choice",
            "instructions": "Choose the one support the kiosk should give the user described in this state in this "
                            "window, or `none`. Earlier judgments of the same window are under `jev`.",
            "criteria": criteria,
        }}


DIFFICULTIES = {
    "touch_difficulty": "The user will keep missing or re-tapping buttons",
    "navigation_difficulty": "The user will go back, revisit screens or stall without choosing",
    "visual_difficulty": "The user will struggle to read or see the screen",
    "hesitation": "The user will stop acting without a visible reason",
    NO_SUPPORT: "The user will carry on and finish without trouble",
}


class NextDifficultyStage:
    """Trajectory stage: from the recent windows, which difficulty comes next if nothing changes.

    The state carries the last windows (tag, screen, decision, touch counts and, when stage 1 ran, its
    scores) oldest first, with their time offsets, beside the current window. Skipped on a session's first
    window: there is no trajectory yet. The answer is a forecast to be scored against the windows that
    follow, which the records already hold.
    """

    name = "next_difficulty"

    def build(self, ctx: StageInput) -> tuple[dict, dict[str, dict]] | None:
        if not ctx.history:
            return None
        state = with_previous(shadow_state(ctx.inp, ctx.state, ctx.touch), ctx.previous)
        state["history"] = [
            {**{k: v for k, v in window.items() if k != "t"}, "t_offset_s": round(window["t"] - ctx.inp.t, 1)}
            for window in ctx.history
        ]
        return state, {"next_difficulty": {
            "type": "choice",
            "instructions": "`history` lists the previous windows of this session, oldest first, ending just before the "
                            "current state. If nothing changes, which difficulty will this user most likely run into "
                            f"within the next {FORECAST_HORIZON_S} seconds?",
            "criteria": dict(DIFFICULTIES),
        }}


DEFAULT_STAGES: tuple[JevStage, ...] = (ScoreStage(),)
STAGE_REGISTRY: dict[str, type] = {
    ScoreStage.name: ScoreStage, SupportChoiceStage.name: SupportChoiceStage, NextDifficultyStage.name: NextDifficultyStage,
}
OFF = "off"


def build_stages(names: str) -> tuple[JevStage, ...]:
    """The stages named in JEV_STAGES ("state_scores,support_choice"); "off" or empty = none (rule table only)."""
    wanted = [name.strip() for name in names.split(",") if name.strip()]
    if not wanted or wanted == [OFF]:
        return ()
    unknown = [name for name in wanted if name not in STAGE_REGISTRY]
    if unknown:
        raise ValueError(f"JEV_STAGES has unknown stage(s) {unknown}; known: {sorted(STAGE_REGISTRY)}")
    if len(set(wanted)) != len(wanted):
        raise ValueError("JEV_STAGES repeats a stage")
    return tuple(STAGE_REGISTRY[name]() for name in wanted)
