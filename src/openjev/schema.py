"""SystemOne wire contract plus an explicit image-input extension."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

Content = str | dict[str, JsonValue] | list[JsonValue]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class BinaryCriteria(Strict):
    positive: Content = Field(default="Yes", alias="true")
    negative: Content = Field(default="No", alias="false")


class Noul(Strict):
    type: Literal["noul"]
    instructions: Content | None = None
    criteria: BinaryCriteria = Field(default_factory=BinaryCriteria)


class Choice(Strict):
    type: Literal["choice"]
    instructions: Content | None = None
    criteria: dict[str, Content | None] = Field(min_length=2, max_length=255)


class Score(Strict):
    type: Literal["score"]
    instructions: Content | None = None
    criteria: list[Content] = Field(min_length=2, max_length=64)


Question = Annotated[Noul | Choice | Score, Field(discriminator="type")]


class Evaluation(Strict):
    model: str = Field(default="jev-latest", min_length=1)
    state: Content
    questions: dict[str, Question] = Field(min_length=1, max_length=64)
    images: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Inline PNG/JPEG/WebP data URLs. Never fetched from the network.",
    )


class NoulResult(Strict):
    type: Literal["noul"] = "noul"
    noul: float = Field(ge=0, le=1)


class ChoiceResult(Strict):
    type: Literal["choice"] = "choice"
    choice: str
    probabilities: dict[str, float]
    confidence: float = Field(ge=0, le=1)


class ScoreResult(Strict):
    type: Literal["score"] = "score"
    score: float = Field(ge=0)
    legend: dict[str, str]
    probabilities: dict[str, float]
    confidence: float = Field(ge=0, le=1)


class Usage(Strict):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class Result(Strict):
    model: str
    answers: dict[str, NoulResult | ChoiceResult | ScoreResult]
    usage: Usage
