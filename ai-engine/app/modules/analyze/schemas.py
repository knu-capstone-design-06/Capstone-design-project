"""Request/response models of POST /v1/analyze.

Mirrors contract/backend-ai.openapi.yaml (0.1.0). The feature items there are
still provisional, so change this file together with the contract.
"""

from pydantic import AwareDatetime, BaseModel, Field


class TouchFeatures(BaseModel):
    tap_count: int = Field(ge=0, strict=True)
    miss_tap_count: int = Field(ge=0, strict=True)
    repeat_tap_count: int = Field(ge=0, strict=True)
    back_count: int = Field(ge=0, strict=True)
    dwell_ms: int = Field(ge=0, strict=True)


class VisionFeatures(BaseModel):
    face_detected: bool = Field(strict=True)
    face_size_ratio: float | None = Field(default=None, ge=0, le=1, strict=True)
    assistive_device: bool | None = Field(default=None, strict=True)
    confidence: float = Field(ge=0, le=1, strict=True)


class AnalyzeRequest(BaseModel):
    session_id: str = Field(strict=True)
    screen_id: str = Field(strict=True)
    # date-time in the contract: an offset is required, a naive value is rejected.
    window_start: AwareDatetime
    window_end: AwareDatetime
    touch: TouchFeatures
    vision: VisionFeatures | None = None


class StateScores(BaseModel):
    """One score per state (0~1). Several states can be high at once."""

    normal: float = Field(ge=0, le=1)
    touch_difficulty: float = Field(ge=0, le=1)
    navigation_difficulty: float = Field(ge=0, le=1)
    visual_difficulty: float = Field(ge=0, le=1)
    hesitation: float = Field(ge=0, le=1)


class AnalyzeResponse(BaseModel):
    session_id: str
    measurable: bool
    states: StateScores | None = None
    model_version: str
