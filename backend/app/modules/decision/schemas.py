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
# Scene tags the vision situation layer sends in observations.scene_tags (vision situation.py SCENE_TAGS) that the rule
# table reads: 1-2 seated height, 1-1 walking aid, 2-1 face approach, 2-2 new customer.
SEATED, AID_USE, APPROACH, CHANGED = "seated_height", "aid_use", "face_approach", "user_changed"
SCENE_TAGS = (SEATED, AID_USE, APPROACH, CHANGED)
# The event behind a true user_changed: the vision chain puts items of its event main_user_changed into the tag's
# evidence, event_id "main_user_changed@<frame of the row that starts the new main-user track>". One change of customer
# stays true through the overlapping engine windows (the situation window_s 3 s with a 1 s step) with the same id, so 2-2
# counts its events by that id (DecisionRepository.note_user_changed).
CHANGE_EVENT = "main_user_changed"
# Why the new ids of an engine window were only remembered, not made 2-2 events (DecisionRepository.note_user_changed;
# the session service logs it under the demonstration switch).
NO_FIRST_PRESS = "no first press yet"
NO_PREVIOUS_WINDOW = "no previous engine window"
PREVIOUS_BEFORE_PRESS = "the previous engine window ended before the first-press window's end"
NOT_AFTER_PREVIOUS = "this engine window did not end after the previous one"


@dataclass(frozen=True)
class ChangeNote:
    """The new event ids of one engine window (2-2) and, when they were only remembered, why (reason; None = they
    became pending)."""

    ids: tuple
    reason: str | None
# The class behind aid_use: the vision chain's head-centre reading puts items of its event aid_head into the tag's
# evidence, obs aid_class with the class name as value (crutch, cane, walker, wheelchair, or null). A wheelchair also
# opens 1-2; the older reading (event aid_score) sends no class.
AID_CLASS_EVENT, AID_CLASS_OBS, WHEELCHAIR = "aid_head", "aid_class", "wheelchair"

# Supports (JP scene table); DEFER is an option of the 3-1 choice, not a row.
WAIT, NOTICE, DELAY, BIG, HIGHLIGHT = (
    "wait_hold_timer", "remaining_steps_notice", "delay_responsibility_notice", "large_button", "highlight_next_action",
)
DEFER = "defer_big_button_question"
# Supports of the scene rows (the vision rule table's draft names): 1-2 lower the screen, 1-1 order by voice, 2-2 ask
# whether to go on with the order in the cart or start a new one, 2-1 ask about 크게 보기 (code name large_text) and
# point at the help entry where it is (highlight_large_view_help).
LOWER, VOICE, SWAP = "lower_screen", "voice_order", "continue_or_new_order"
LARGE_TEXT, LARGE_VIEW = "large_text", "highlight_large_view_help"
# 크게 보기 is ONE support (text and buttons big together); large_text (2-1) and large_button (4-1) are its two code
# names, one per row that asks about it.
BIG_VIEW = frozenset({LARGE_TEXT, BIG})
HOLD_TIMER = "hold_timer"  # session_signal name of an opened or kept 3-2 wait
INTERVENTION = {"wait": "기다림", "propose": "묻기", "apply": "바로 적용", "call_staff": "직원 호출"}
# contract SupportDecision (UIPreset, requires_confirmation) per support, JP 2-5. The contract has no preset for the
# low screen, voice ordering or the new-customer question: those asks answer preset none, requires_confirmation true
# and the support's name.
CONTRACT_FORM = {
    WAIT: ("none", False), NOTICE: ("step_guide", False), DELAY: ("step_guide", False),
    BIG: ("large_button", True), HIGHLIGHT: ("none", False), "call_staff": ("none", False),
    LOWER: ("none", True), VOICE: ("none", True), SWAP: ("none", True),
    LARGE_TEXT: ("large_text", True), LARGE_VIEW: ("none", False),
}
QUIET_APPLY = frozenset({NOTICE, DELAY, HIGHLIGHT, LARGE_VIEW})


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
    delay_notice_on: bool        # evaluation switch: 3-1 offers the encouragement line (delay_responsibility_notice) instead
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
HISTORY_WINDOWS = 10        # windows read by the trajectory stage (the records themselves stay for the session) (1 s windows: about ten seconds)
FORECAST_HORIZON_S = 10     # how far ahead next_difficulty asks about

# The only stage answers the trajectory reads (docs 9.6): stage-1 state scores. A forecast never reads the
# forecasts or support choices of the windows before it.
HISTORY_STAGES = ("state_scores",)
# Of those answers, the five contract state scores only (jev_questions.STATE_QUESTIONS): the rule table's own
# question asked in the same call (proposal_fits, queue_support) stays out of the trajectory.
HISTORY_SCORES = ("touch_difficulty", "navigation_difficulty", "visual_difficulty", "hesitation", "normal")
STALE = "stale"   # WindowRecord.jev of a window recorded only: late, or off the session's timeline (service._place)


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
    cart_items: int | None = None          # items in the session's cart at t (its total quantity, the backend's own
                                           # cart; read under DECISION_SEND_SUPPORT for a window with a press); None = not read
    # The order screen's block touch.scene_signals, read under DECISION_SEND_SUPPORT: this window's own counts, and
    # zoom_attempt from the counts summed over the recent span like fixes_recent (service.recent_signals).
    fixes_segment: int | None = None       # presses in this window that fix the near miss before them
    zoom_attempts_segment: int | None = None   # zoom attempts in this window (a double tap on text)
    zoom_attempt: bool | None = None       # a zoom attempt in the recent span (2-1); None = not known
    can_offer: bool | None = None          # the order screen could show an ask when it built the window (1-1, 1-2)
    # The supports the customer already has on at t (touch.interaction ui_settings and voice_enabled, read under
    # DECISION_SEND_SUPPORT; sessions/service.settings_on): counted as active by the rows. None = not known.
    supports_on: tuple | None = None


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
    # The decision's scope when set (decide() and the candidate filter use it): ("session",) for an ask made at most
    # once per session. None: the tag scope for a row from a tag, else the screen scope.
    scope: tuple | None = None


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
    last_now: float | None = None  # the server clock when that window was judged: with last_t, the session's timeline
    alt_t: float | None = None     # a window that fell off the timeline, kept to see whether the next one follows it
    alt_now: float | None = None
    epoch: int = 0                 # goes up each time the frontend clock moved: windows of another epoch are another timeline
    first_press: bool = False      # the session has had a press (a judged window with taps)
    # The end of the touch window that held the session's first press: epoch seconds on the order screen's clock (its
    # /features window_end, the base of last_t, tag_since and screen_since; moved with them when that clock moves).
    first_press_t: float | None = None
    # 2-2: the new-customer events by the engine's event id (CHANGE_EVENT, DecisionRepository.note_user_changed): every
    # id the session has received, before its first press too (the same change seen again in a later overlapping window
    # is no new event), and of them the ids that came after the first press in time and that no press has used yet, in
    # the order they came; the first press after them uses them (rule_table.decide).
    user_changed_seen: list = field(default_factory=list)
    user_changed_pending: list = field(default_factory=list)

    def snapshot(self) -> dict:
        held = None if self.held is None else {
            "decision_id": self.held.decision_id, "support": self.held.support, "scene": self.held.decision.scene,
            "action": self.held.action, "status": self.held.status, "scope": list(self.held.scope),
        }
        return {"held": held, "active": list(self.active), "refused": list(self.refused),
                "withdrawn": [{**w, "scope": list(w["scope"])} for w in self.withdrawn]}


# Versions kept with every record (docs/Convention.md 7: the rule and question versions of an experiment).
# Bump RULES_VERSION when a row, a rank, a parameter or a transition of the rule table changes, and
# QUESTIONS_VERSION when the wording or the state given to Jev changes.
# v1, the one name of this pull request's table: the scene rows (1-1, 1-2, 2-1, 2-2) on the scene tags and the per-row
# scope; 1-1 and 1-2 also shut while the screen's ask gate is false (can_offer); the 2-2 event by the engine's event
# id, counted only when the session's previous received engine window ended at or after the end of the first-press
# touch window (DecisionRepository.note_user_changed), and kept while a held ask keeps the row shut; and the 4-2 guard: no 4-2 on the menu with the options dialog known closed (rule_table.candidate_rows
# plain_menu, a demonstration-switch difference from the vision table awaiting the owners' word).
RULES_VERSION = "rule_table_v1"
# v2: the 2-1 rows' fit questions (large_text, highlight_large_view_help) with their state keys touch.zoom_attempt and
# vision.face_approach, and support_choice's candidates limited to the supports its question offers.
QUESTIONS_VERSION = "jev_questions_v2"


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
    # Why there was no answer (None when answered), so a Jev fault is not counted as a wrong answer:
    # "unavailable" (the call failed: HTTP error, timeout, a body that is not a Jev answer; latency_ms near the
    # timeout tells a timeout apart), "mismatch" (Jev answered, but not what was asked: its model and usage
    # are kept, the tokens were billed) or "build_error" (the question could not be built: a fault here).
    reason: str | None = None
    answered_at: datetime | None = None    # server UTC when the call ended; None when no call was made (build_error)
    questions_version: str = QUESTIONS_VERSION


@dataclass(frozen=True)
class VisionWindow:
    """One window the AI engine posted (POST /sessions/{id}/vision-windows), kept for the session until a /features
    window has passed it (DecisionRepository.pair_vision)."""

    session_id: str
    window_start: datetime                 # the kiosk PC's wall clock, like the /features window times
    window_end: datetime
    situation: dict                        # name, evidence, confidence: the shape WindowInput.situation holds
    gaze: bool | None
    face_seen: bool
    scene_tags: list
    model_version: str
    received_at: datetime                  # server UTC when the backend received it


@dataclass(frozen=True)
class PairedVision:
    """The AI engine windows one /features window reads (DecisionService.paired_vision), all within its bound.

    The bound (two touch-window lengths) holds two 1 s engine segments and all are kept, so a tag that holds in one
    segment only may be the earlier of the two. The latest window in the bound gives the gaze, the face and the scene tags; the
    situation comes from the freshest window in the bound that names a tag (TAGS), the latest one when none does.
    A tag of the latest window always wins. The scene tags the rule table reads come from every window in the bound
    (scene_tag_states).
    """

    latest: VisionWindow
    named: VisionWindow                    # the window the situation comes from (the latest when no window names a tag)
    windows: tuple = ()                    # every engine window in the bound, the two above included

    def scene_tag_states(self, names: tuple[str, ...] = SCENE_TAGS) -> list[dict]:
        """The scene tags in `names` over every engine window in the bound, in the item form the rule table reads
        (rule_table.scene_tag): status true when ANY window in the bound says true, with t the end (epoch seconds) of
        the freshest such window; otherwise false when the latest window says false; otherwise "unknown". One item per
        name that some window in the bound carries. The aid_use item also carries aid_class: the class in the evidence
        of the window that gave it its true status (AID_CLASS_EVENT, AID_CLASS_OBS), None without one.

        A tag may hold in one 1 s segment only, and one touch window reads two segments: a true in the earlier one must
        not be lost behind the later one. No number: the bound is the pairing's own. (user_changed holds in about three
        windows in a row for one change; 2-2 counts its events by id when the engine window arrives, not from here.)
        """
        windows = self.windows or (self.latest,)
        states = []
        for name in names:
            carried = [(w, tag) for w in windows for tag in w.scene_tags if tag.get("name") == name]
            if not carried:
                continue
            trues = [(w.window_end, tag) for w, tag in carried if tag.get("status") is True]
            latest = next((tag.get("status") for tag in self.latest.scene_tags if tag.get("name") == name), None)
            status = True if trues else (False if latest is False else UNKNOWN)
            freshest = max(trues, key=lambda item: item[0]) if trues else None
            state = {"name": name, "status": status, "t": freshest[0].timestamp() if freshest else None}
            if name == AID_USE:
                state["aid_class"] = None if freshest is None else next(
                    (e.get("value") for e in freshest[1].get("evidence") or ()
                     if str(e.get("event_id", "")).startswith(AID_CLASS_EVENT + "@") and e.get("obs") == AID_CLASS_OBS),
                    None)
            states.append(state)
        return states

    @property
    def situation(self) -> dict:
        return self.named.situation

    @property
    def situation_window_end(self) -> datetime:
        return self.named.window_end

    @property
    def gaze(self) -> bool | None:
        return self.latest.gaze

    @property
    def face_seen(self) -> bool:
        return self.latest.face_seen

    @property
    def scene_tags(self) -> list:
        return self.latest.scene_tags

    @property
    def window_start(self) -> datetime:
        return self.latest.window_start

    @property
    def window_end(self) -> datetime:
        return self.latest.window_end

    @property
    def received_at(self) -> datetime:
        return self.latest.received_at

    @property
    def model_version(self) -> str:
        return self.latest.model_version


@dataclass
class WindowRecord:
    """One judged window, kept for the whole session: the comparison row of the experiment (docs 7.1).

    inputs is the rule table's input line, decision the rule table's result, jev why Jev was or was not asked
    ("off", "no_client", "not_measurable", "skipped_in_flight", "asked", or STALE for a window recorded only: one whose time was off the session's timeline, or that arrived after
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
    epoch: int = 0                         # SessionState.epoch when the window came: its times compare within one epoch only
    # What ai-engine gave for the window (docs/Convention.md 7: not measurable apart from a system fault):
    # "ok", "unmeasurable" (its own measurable=false), "unavailable" (no answer) or "invalid_scores" (scores the
    # response rejected). The last three all reach the table as a window that was not measurable. None: the
    # window did not come through /features (a direct caller of observe()).
    ai: str | None = None
    ai_model_version: str | None = None    # ai-engine's model_version for the window, when it answered
    received_at: datetime | None = None    # server UTC when /features received the window (window_end is the frontend's)
    rules_version: str = RULES_VERSION
    # The AI engine windows this /features window read (DecisionService.paired_vision): the latest one's window_start,
    # window_end, received_at, model_version, face_seen and scene_tags (for the later rows that read them), and
    # situation_window_end, the end of the window the situation came from (= window_end when the latest gave it); the
    # situation and gaze themselves are in inputs. None: no engine window read.
    vision_window: dict | None = None
