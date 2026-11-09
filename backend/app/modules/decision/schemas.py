"""Decision-layer data: the window input, the rule table's decision, the session state, the Jev record.

Ported from ai-engine/app/modules/vision/judgment/rule_table_v0.py, the vision owner's reference
implementation of the JP design (0-1 session state, 0-2 the rule table, 0-3 transitions, 0-4 the
Jev places). The names, rows and ranks there are the spec; this is where they run, because the
backend owns the session state and is the only caller of Jev (AGENTS.md 4, decision 2026-11-04).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Situation tags the vision situation layer produces (vision README '상황 태그 3개').
QUEUE, BUSY, AROUND = "looking_back_with_people_behind", "consulting_companion", "looking_around"
UNKNOWN = "unknown"
TAGS = frozenset({QUEUE, BUSY, AROUND})

# Supports (JP scene table); DEFER is an option of the 3-1 choice, not a row.
WAIT, NOTICE, DELAY, BIG, HIGHLIGHT = (
    "wait_hold_timer", "remaining_steps_notice", "delay_responsibility_notice", "large_button", "highlight_next_action",
)
DEFER = "defer_big_button_question"
HOLD_TIMER = "hold_timer"  # session_signal name of an opened or kept 3-2 wait
INTERVENTION = {"wait": "기다림", "propose": "묻기", "apply": "바로 적용", "call_staff": "직원 호출"}
# contract SupportDecision (UIPreset, requires_confirmation) per support, JP 2-5
CONTRACT_FORM = {
    WAIT: ("none", False), NOTICE: ("step_guide", False), DELAY: ("step_guide", False),
    BIG: ("large_button", True), HIGHLIGHT: ("none", False), "call_staff": ("none", False),
}
QUIET_APPLY = frozenset({NOTICE, DELAY, HIGHLIGHT})


@dataclass(frozen=True)
class DecisionParams:
    """Every count and time the rule table compares. The values are pilot values, not agreed thresholds."""

    touch_span_s: float          # the recent span the touch cues (misses, fixes, backs) are counted over
    tremor_miss_min: int         # 4-1: near misses fixed at once, while facing the screen
    tremor_miss_min_no_gaze: int  # 4-1: the raised criterion when the camera cannot tell the gaze
    lost_back_min: int           # 4-2: backs in the recent span
    lost_pause_s: float          # 4-2: pause after choosing, on a screen with steps left
    lost_pause_s_vision: float   # 4-2: the lowered pause with looking_around or a gaze at the screen
    no_response_s: float         # an unanswered ask is withdrawn after this
    delay_notice_on: bool        # evaluation switch: 3-1 offers the delay-responsibility notice instead
    defer_option_on: bool        # evaluation switch: 3-1 may defer the big-button question


# The same values as ai-engine/app/modules/vision/params.py, source by source (that file quotes each):
PILOT_PARAMS = DecisionParams(
    touch_span_s=5.0,            # [파일럿] starting value: the recent span for the touch cues
    tremor_miss_min=2,           # [파일럿] reading of tree table 3-가 4-1 '반복' as two or more
    tremor_miss_min_no_gaze=3,   # [파일럿] starting value: one more than tremor_miss_min when the gaze is unknown
    lost_back_min=1,             # definition: tree table 3-가 4-2 '되돌아감이 한 번이라도 있음'
    lost_pause_s=8.0,            # [파일럿] starting value: 4-2 '고른 뒤 멈춤'
    lost_pause_s_vision=4.0,     # [파일럿] starting value: the lowered pause with looking_around or a gaze
    no_response_s=10.0,          # [파일럿] starting value: JP 0-6 '무응답은 policy의 시간'
    delay_notice_on=False,       # evaluation switch (decision list 2026-10-10 §14)
    defer_option_on=True,        # evaluation switch (JP 0-2)
)

# Screen order of the kiosk, taken from the frontend: frontend/src/features/order/OrderPage.tsx keeps
# screen as 'menu' | 'review' | 'complete' (:36) and draws its step bar in that order (:172); the same
# tuple as vision touch.py SCREEN_FLOW. Gives steps_left and screen progress.
SCREEN_FLOW = ("menu", "review", "complete")

# Shadow-stage settings with no source yet ("기준 없음"): experiment settings, not agreed thresholds.
HISTORY_WINDOWS = 5         # windows kept for the trajectory stage (2 s windows: about ten seconds)
FORECAST_HORIZON_S = 10     # how far ahead next_difficulty asks about

# The only stage answers the trajectory reads (docs 9.6): stage-1 state scores. A forecast never reads the
# forecasts or support choices of the windows before it.
HISTORY_STAGES = ("state_scores",)
# Of those answers, the five contract state scores only (jev_questions.STATE_QUESTIONS): the rule table's own
# question asked in the same call (proposal_fits, queue_support) stays out of the trajectory.
HISTORY_SCORES = ("touch_difficulty", "navigation_difficulty", "visual_difficulty", "hesitation", "normal")
STALE = "stale"   # WindowRecord.jev of a window that ended before the session's last judged window


@dataclass(frozen=True)
class WindowInput:
    """What one window gives the rule table (JP 0-2 '입력 한 줄'). None = not known this window."""

    t: float                               # window end, seconds (epoch)
    measurable: bool                       # the analysis found something to judge in this window
    situation: dict | None = None          # vision situation output (name, evidence, confidence); None = not judged
    screen: str | None = None              # screen id at t
    steps_left: int | None = None          # screens left before the order ends; None = unknown
    gaze: bool | None = None               # facing the screen at the window end; None = the camera cannot tell
    misses_recent: int | None = None       # presses outside every button in the recent span
    fixes_recent: int | None = None        # near misses fixed at once in the recent span
    backs_recent: int | None = None        # backs (review -> menu) in the recent span
    pause_s: float | None = None           # seconds since the last press of this screen visit; None before a press
    taps_segment: int | None = None        # presses in this window
    progress_segment: bool | None = None   # a screen forward in this window; None = not known
    options_open: bool | None = None       # the options dialog is open at t


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
    jev_request: dict | None = None        # {"state", "questions"}; the model is the backend setting
    cues: dict = field(default_factory=dict)
    decision_id: str | None = None
    reason: str = ""
    session_signal: dict | None = None     # {name: hold_timer} on an opened or kept 3-2 wait
    execution: dict = field(default_factory=dict)   # steps_left · target_id · message_id (JP 2-5)

    def form(self) -> tuple[str, bool]:
        """(preset, requires_confirmation) of contract SupportDecision for this decision."""
        if self.transition in ("open", "replace", "keep") and self.support in CONTRACT_FORM:
            return CONTRACT_FORM[self.support]
        return "none", False

    def to_dict(self) -> dict:
        preset, confirm = self.form()
        return {
            "transition": self.transition, "support": self.support, "scene": self.scene, "action": self.action,
            "intervention": INTERVENTION.get(self.action), "rank": self.rank,
            "scope": None if self.scope is None else list(self.scope), "withdraw_on": self.withdraw_on,
            "decision_id": self.decision_id, "preset": preset, "requires_confirmation": confirm,
            "policy": self.policy, "jev_request": self.jev_request, "cues": self.cues, "meta": self.meta,
            "reason": self.reason, "session_signal": self.session_signal,
            "steps_left": self.execution.get("steps_left"), "target_id": self.execution.get("target_id"),
            "message_id": self.execution.get("message_id"),
        }


@dataclass(frozen=True)
class Held:
    decision_id: str
    support: str
    action: str
    rank: int
    scope: tuple
    withdraw_on: str | None
    status: str          # 'shown'
    shown_t: float
    decision: Decision   # the applied decision with its id (held keeps the whole decision)


@dataclass
class SessionState:
    """The backend's session state of JP 0-1 (the parts the four scenes use)."""

    held: Held | None = None
    active: list = field(default_factory=list)
    refused: list = field(default_factory=list)
    withdrawn: list = field(default_factory=list)   # {"support", "scope", "reason", "replaced_by"}
    tag_last: str | None = None
    tag_since: float | None = None
    screen_last: str | None = None
    screen_since: float | None = None
    next_id: int = 1
    last_t: float | None = None   # end of the last judged window; a window ending before it is recorded only

    def snapshot(self) -> dict:
        held = None if self.held is None else {
            "decision_id": self.held.decision_id, "support": self.held.support, "scene": self.held.decision.scene,
            "action": self.held.action, "status": self.held.status, "scope": list(self.held.scope),
        }
        return {"held": held, "active": list(self.active), "refused": list(self.refused),
                "withdrawn": [{**w, "scope": list(w["scope"])} for w in self.withdrawn]}


@dataclass(frozen=True)
class JevRecord:
    """One shadow call: what was asked, what came back, how long it took. No state, no key."""

    session_id: str
    window_end: datetime
    questions: tuple[str, ...]
    request_model: str
    outcome: str                           # answered | no_answer
    latency_ms: int
    response_model: str | None = None
    answers: dict = field(default_factory=dict)   # name -> noul probability, or the whole choice / score answer
    usage: dict | None = None
    decision_id: str | None = None
    stage: str = "state_scores"            # which Jev stage asked (stages can be stacked)
    previous_missing: tuple[str, ...] = ()  # earlier stages that had no answer when this one ran


@dataclass
class WindowRecord:
    """One judged window, kept for the whole session: the comparison row of the experiment (docs 7.1).

    inputs is the rule table's input line, decision the rule table's result, jev why Jev was or was not asked
    ("off", "no_client", "not_measurable", "skipped_in_flight", "asked", or STALE for a window that arrived after
    a later one and was recorded without being judged), answers the stage answers as they arrive (the validated
    answer as Jev gave it). Windows the rule table alone judged are rows too, so the rule-only arm has the same
    denominator.
    """

    session_id: str
    window_end: datetime
    t: float
    inputs: dict
    decision: dict
    stages: tuple[str, ...]
    jev: str
    model: str | None = None
    timed_out: str | None = None           # a shown ask withdrawn for no response before this window
    answers: dict = field(default_factory=dict)   # stage name -> {question: answer}
    outcomes: dict = field(default_factory=dict)  # stage name -> answered | no_answer | skipped
