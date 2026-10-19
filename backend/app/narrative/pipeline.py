"""Generate -> validate -> retry with feedback -> deterministic fallback.

Nothing reaches the user without passing validate(). If the AI is disabled,
fails, or is rejected twice, the deterministic fallback is shown instead and
the reason is recorded, so the UI can say which one it is.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .facts import InsightFacts
from .fallback import fallback_narrative
from .schema import Audience, Language, Narrative
from .storyteller import PROMPT_VERSION, Storyteller, StorytellerError
from .validator import validate

MAX_ATTEMPTS = 2  # first try + one retry with the validator's feedback


class Insight(BaseModel):
    model_config = ConfigDict(frozen=True)

    insight_id: str
    audience: Audience
    language: Language
    narrative: Narrative
    source: Literal["ai", "fallback"]
    model: str | None  # model that wrote it (None for fallback)
    prompt_version: str | None
    attempts: int  # AI attempts made
    rejected_attempts: list[list[str]]  # validator problems per rejected attempt
    fallback_reason: str | None
    generated_at: str  # ISO timestamp (UTC)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def generate_insight(
    facts: InsightFacts, audience: Audience, language: Language,
    storyteller: Storyteller | None,
) -> Insight:
    rejected: list[list[str]] = []

    def fallback(reason: str, attempts: int) -> Insight:
        return Insight(
            insight_id=facts.insight_id, audience=audience, language=language,
            narrative=fallback_narrative(facts, audience, language), source="fallback",
            model=None, prompt_version=None, attempts=attempts, rejected_attempts=rejected,
            fallback_reason=reason, generated_at=_now(),
        )

    if storyteller is None:
        return fallback("ai_disabled", 0)

    feedback: list[str] | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            narrative = await storyteller.write(facts, audience, language, feedback)
        except StorytellerError as error:
            return fallback(f"ai_error: {error}", attempt)

        result = validate(narrative, facts)
        if result.ok:
            return Insight(
                insight_id=facts.insight_id, audience=audience, language=language,
                narrative=narrative, source="ai", model=storyteller.model_name,
                prompt_version=PROMPT_VERSION, attempts=attempt, rejected_attempts=rejected,
                fallback_reason=None, generated_at=_now(),
            )
        rejected.append(result.problems)
        feedback = result.problems

    return fallback("validation_failed", MAX_ATTEMPTS)
