"""Jev (TypeSafe AI) System One request and answer shapes.

Source: https://docs.typesafe.ai/api/system-one.md (2026-11-01). The request is what
the backend judgment layer builds (app/modules/decision: model, state, questions);
the answer is validated here so callers only ever see a well-formed one or None.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class JevRequest(BaseModel):
    """model is the version to ask; state is a string, object or array; questions map a name to a question."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    state: str | dict[str, JsonValue] | list[JsonValue]
    questions: dict[str, dict[str, JsonValue]] = Field(min_length=1)


class _Answer(BaseModel):
    # The API may add fields; unknown ones are ignored, known ones are checked.
    model_config = ConfigDict(extra="ignore")


class NoulAnswer(_Answer):
    """Yes/no: noul is the probability of "yes"."""

    type: Literal["noul"]
    noul: Probability


class ChoiceAnswer(_Answer):
    type: Literal["choice"]
    choice: str
    confidence: Probability
    probabilities: dict[str, Probability]


class ScoreAnswer(_Answer):
    """score is a number on the scale the question gave; legend names each step."""

    type: Literal["score"]
    score: float = Field(strict=True, allow_inf_nan=False)  # a JSON number: "3" and true are refused
    confidence: Probability
    probabilities: dict[str, Probability]
    legend: dict[str, JsonValue]


JevAnswer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]


class JevUsage(_Answer):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class JevResponse(_Answer):
    """model is the version that actually answered (an alias resolves to one)."""

    model: str
    answers: dict[str, JevAnswer] = Field(min_length=1)
    usage: JevUsage
