"""Backend/AI envelopes; shared feature schemas are not available yet.

The external OpenAPI references must be supplied before replacing JsonObject
with the team's TouchFeatures, VisionFeatures and StateScores definitions.
Example values alone do not establish their required fields or constraints.
"""

from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, JsonValue, model_validator


JsonObject = dict[str, JsonValue]


class AnalyzeRequest(BaseModel):
    session_id: str
    screen_id: str
    window_start: AwareDatetime
    window_end: AwareDatetime
    touch: JsonObject
    vision: JsonObject | None = None

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be later than window_start")
        return self


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    session_id: str
    measurable: bool
    states: JsonObject | None = None
    model_version: str

    @model_validator(mode="after")
    def validate_measurement(self) -> Self:
        # Follow the prose contract even though states is not marked required
        # in the supplied OpenAPI. Never treat missing scores as a judgment.
        if self.measurable and not self.states:
            raise ValueError("measurable=true requires nonempty states")
        if not self.measurable and self.states is not None:
            raise ValueError("measurable=false requires states=null or omitted")
        return self


class AiHealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["ai-server"]
