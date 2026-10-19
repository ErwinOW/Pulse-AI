"""Structured narrative output (what the Storyteller must return) and validation results."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Audience = Literal["casual", "analyst"]
Language = Literal["en", "id"]
Confidence = Literal["moderate", "strong"]


class MetricClaim(BaseModel):
    """A number the narrative relies on, tied to a specific computed fact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str  # must match InsightFacts.facts[*].fact_id
    value: float


class Narrative(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    headline: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=700)
    event_ids: list[str]
    metric_claims: list[MetricClaim]
    interpretation: str = Field(max_length=400)  # the inferred part, kept separate from facts
    confidence: Confidence
    is_hypothetical: bool


class ValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool
    problems: list[str]
