from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator

Count = Annotated[int, Field(strict=True, ge=0)]
Score = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
DistancePx = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class TouchUiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    large_text: StrictBool
    large_button: StrictBool
    simple_screen: StrictBool
    step_guide: StrictBool
    low_screen: StrictBool
    high_contrast: StrictBool


class TouchInteraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["touch-interaction-pilot-v1"]
    visit_id: Annotated[str, Field(strict=True, min_length=1)]
    window_sequence: Count
    outside_tap_ratio: Score | None
    outside_nearest_distance_mean_px: DistancePx | None
    outside_nearest_distance_sample_count: Count
    pointer_cancel_count: Count
    pointer_interrupted_count: Count
    scroll_event_count: Count
    category_change_count: Count
    options_open_count: Count
    options_close_count: Count
    screen_transition_count: Count
    screen_revisit_count: Count | None
    cart_change_count: Count
    selection_change_count: Count | None
    ui_settings_change_count: Count
    voice_state_change_count: Count
    since_last_input_ms: Count | None
    order_busy_ms: Count | None
    options_open: StrictBool | None
    order_busy: StrictBool
    voice_enabled: StrictBool | None
    microphone_active: StrictBool | None
    voice_processing: StrictBool | None
    voice_auto_off: Literal["silence", "idle"] | None
    ui_settings: TouchUiSettings
    voice_phase: Literal["idle", "listening", "processing", "speaking"] | None = None
    voice_speaking: StrictBool | None = None
    voice_busy: StrictBool | None = None
    voice_busy_ms: Count | None = None
    since_last_input_excluding_system_busy_ms: Count | None = None


class TouchFeatures(BaseModel):
    tap_count: Count
    miss_tap_count: Count
    repeat_tap_count: Count
    back_count: Count
    dwell_ms: Count
    interaction: TouchInteraction | None = None


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


class SessionCreateResponse(BaseModel):
    session_id: str
    started_at: AwareDatetime


class SupportDecision(BaseModel):
    # Connection verification only; no support selection rule has been agreed.
    preset: Literal["none"] = "none"
    requires_confirmation: Literal[False] = False
    decided_by: Literal["rule_placeholder"] = "rule_placeholder"


class FeatureWindowResponse(BaseModel):
    session_id: str
    ai_available: bool
    states: StateScores | None = None
    model_version: str | None = None
    support: SupportDecision = Field(default_factory=SupportDecision)


class FeatureValidationIssue(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class FeatureValidationError(BaseModel):
    detail: list[FeatureValidationIssue]
