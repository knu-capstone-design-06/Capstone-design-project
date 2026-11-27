from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, JsonValue, StrictBool, model_serializer, model_validator

Count = Annotated[int, Field(strict=True, ge=0)]
Score = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
Name = Annotated[str, Field(min_length=1)]
Seconds = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Millis = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class TouchFeatures(BaseModel):
    tap_count: Count
    miss_tap_count: Count
    repeat_tap_count: Count
    back_count: Count
    dwell_ms: Count
    # The order screen's pilot block (frontend interactionFeatures.ts), not in the contract. Kept as sent, never
    # validated here (a malformed block must not fail the window) and never forwarded (excluded from dumps, so the
    # ai-engine request stays the contract's five counts). Read only with DECISION_SEND_SUPPORT (InteractionPilot).
    interaction: Any = Field(default=None, exclude=True)
    # The order screen's second pilot block (SceneSignalsPilot), handled like interaction: kept as sent, never
    # validated here, never forwarded; read only with DECISION_SEND_SUPPORT.
    scene_signals: Any = Field(default=None, exclude=True)


class InteractionPilot(BaseModel):
    """The fields of touch.interaction the demonstration mapping reads (frontend interactionFeatures.ts, schema
    touch-interaction-pilot-v1). Other fields are ignored; a block that fails this model is not read at all."""

    schema_version: Literal["touch-interaction-pilot-v1"]
    options_open: StrictBool | None = None
    since_last_input_excluding_system_busy_ms: Millis | None = None
    voice_phase: Literal["idle", "listening", "processing", "speaking"] | None = None
    microphone_active: StrictBool | None = None


class PilotUiSettings(BaseModel):
    """touch.interaction.ui_settings: the three screen settings the scene rows read (frontend Settings largeText,
    largeButton, lowScreen as the window builder sends them)."""

    large_text: StrictBool | None = None
    large_button: StrictBool | None = None
    low_screen: StrictBool | None = None


class PilotSettings(BaseModel):
    """What the customer has on at the window end, from touch.interaction (schema touch-interaction-pilot-v1):
    ui_settings and voice_enabled. Read apart from InteractionPilot, so a block whose settings are malformed still
    gives the pause and the options dialog, and the reverse. Other fields are ignored."""

    schema_version: Literal["touch-interaction-pilot-v1"]
    ui_settings: PilotUiSettings | None = None
    voice_enabled: StrictBool | None = None


class SceneSignalsPilot(BaseModel):
    """touch.scene_signals (schema touch-scene-signals-pilot-v1): what the scene rows read of this window.

    near_miss_fix_count: presses in the window that fix the press before them (the press before hit no target and
    this one, the next press of the session, hits one of its nearest candidates; the vision module's definition,
    ai-engine touch.py near_miss_fix_count). zoom_attempt_count: zoom attempts in the window (a double tap on text:
    two presses in a row that hit no target, the second within the order screen's double-click interval and
    same-place distance). null: not observable in this window. can_offer: whether the order screen could show an ask
    when it built the window (its own gate: no sheet, dialog or preview card open, voice ordering off, no message,
    writing allowed; OrderPage canOfferSupport); null: not known. The three keys are required; a block that fails this model or names
    another version is not read. Other fields are ignored.
    """

    schema_version: Literal["touch-scene-signals-pilot-v1"]
    near_miss_fix_count: Count | None
    zoom_attempt_count: Count | None
    can_offer: StrictBool | None


class VisionFeatures(BaseModel):
    face_detected: StrictBool
    face_size_ratio: Score | None = None
    assistive_device: StrictBool | None = None
    confidence: Score


class StateScores(BaseModel):
    normal: Score
    touch_difficulty: Score
    navigation_difficulty: Score
    visual_difficulty: Score
    hesitation: Score


class FeatureWindowRequest(BaseModel):
    screen_id: str
    window_start: AwareDatetime
    window_end: AwareDatetime
    touch: TouchFeatures
    vision: VisionFeatures | None = None

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be later than window_start")
        return self


class VisionEvidence(BaseModel):
    """One evidence item of a situation or scene tag, as the vision situation rules give it (event_id, obs, value,
    t). The rule table reads event_id only (rule_table.evidence_counts)."""

    event_id: Name
    obs: str | None = None
    value: JsonValue = None
    t: Seconds | None = None


class VisionConfidence(BaseModel):
    events: Count
    quality_ok: StrictBool


class VisionSituation(BaseModel):
    """The window's situation in the keys the rule table reads from WindowInput.situation: name (unknown = not
    judged), evidence, confidence ("unknown" when the name is unknown or too few events back it)."""

    name: Name
    evidence: list[VisionEvidence] = []
    confidence: VisionConfidence | Literal["unknown"]


class SceneTag(BaseModel):
    name: Name
    status: StrictBool | Literal["unknown"]
    unknown_reason: str | None = None
    evidence: list[VisionEvidence] = []


class VisionObservations(BaseModel):
    gaze: StrictBool | None = None    # facing the screen at the window end; None = the camera cannot tell
    face_seen: StrictBool             # a face on a row of the window
    scene_tags: list[SceneTag] = []


class VisionWindowRequest(BaseModel):
    """One window the AI engine's live runner posts (ai-engine app/modules/vision/tag_sender.py). The window times
    are the kiosk PC's wall clock, the clock the order screen's /features windows are on."""

    session_id: str | None = None     # the engine repeats the path's session here; when present it must match
    window_start: AwareDatetime
    window_end: AwareDatetime
    situation: VisionSituation
    observations: VisionObservations
    model_version: str

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be later than window_start")
        return self


class VisionWindowAccepted(BaseModel):
    status: Literal["accepted"] = "accepted"


class SessionCreateResponse(BaseModel):
    session_id: str
    started_at: AwareDatetime


UIPreset = Literal["none", "large_text", "large_button", "simple_screen", "step_guide", "voice_guide"]
# The fields a rule-table support carries for the screen; left out of the answer when empty.
EXECUTION_FIELDS = ("name", "decision_id", "steps_left", "target_id", "message_id")


class SupportDecision(BaseModel):
    # Default: the placeholder answer of connection verification (preset none, the screen stays as it is). With
    # DECISION_SEND_SUPPORT on (demonstration), the rule table's decision: its contract form (rule_table.CONTRACT_FORM)
    # and the execution fields the decision holds (JP 2-5).
    preset: UIPreset = "none"
    requires_confirmation: bool = False
    decided_by: Literal["rule_placeholder", "jev"] = "rule_placeholder"
    name: str | None = None          # the rule table's support name, e.g. large_button, highlight_next_action
    # The decision's id (rule table, d0001...): the same in every answer while that decision is held (keep), a new
    # one when the table opens or replaces a support.
    decision_id: str | None = None
    steps_left: int | None = None    # screens left before the order ends
    target_id: str | None = None     # what the support points at (cart-add, cart:*:decrease, cart_progress)
    message_id: str | None = None    # the notice text's id (steps_left_notice, delay_responsibility_notice)

    @model_serializer(mode="wrap")
    def leave_out_empty_execution_fields(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None or key not in EXECUTION_FIELDS}


class FeatureWindowResponse(BaseModel):
    session_id: str
    ai_available: bool
    states: StateScores | None = None
    model_version: str | None = None
    support: SupportDecision = Field(default_factory=SupportDecision)
