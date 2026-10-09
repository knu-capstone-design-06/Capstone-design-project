from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, StrictBool, model_validator

Count = Annotated[int, Field(strict=True, ge=0)]
Score = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]


class TouchFeatures(BaseModel):
    tap_count: Count
    miss_tap_count: Count
    repeat_tap_count: Count
    back_count: Count
    dwell_ms: Count


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
