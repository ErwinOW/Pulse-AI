"""Tests for the Storyteller prompt and the generate -> validate -> retry -> fallback pipeline.

A fake storyteller stands in for Gemini: no API calls, deterministic results.
"""

import asyncio
from functools import cache

from app.detection import detect_alerts
from app.narrative import MetricClaim, facts_from_alert, fallback_narrative
from app.narrative.pipeline import generate_insight
from app.narrative.storyteller import StorytellerError, build_prompt, parse_json_narrative
from app.simulator import DEMO_HIGH_PRESS, generate


@cache
def demo_facts():
    match, _ = generate(DEMO_HIGH_PRESS)
    (alert,) = detect_alerts(match.events, ("NBR", "EAS"), 6000)
    return facts_from_alert(match, alert)


def good_narrative():
    # A narrative known to pass validation (same content the AI would need to produce).
    return fallback_narrative(demo_facts(), "casual", "en")


def bad_narrative():
    facts = demo_facts()
    wrong = facts.fact("S1.recent").value + 5
    return good_narrative().model_copy(update={"metric_claims": [MetricClaim(fact_id="S1.recent", value=wrong)]})


class FakeStoryteller:
    """Returns queued narratives (or raises queued errors) and records the feedback it gets."""

    model_name = "fake-model"

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.feedback_seen = []

    async def write(self, facts, audience, language, feedback=None):
        self.feedback_seen.append(feedback)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def run(storyteller):
    return asyncio.run(generate_insight(demo_facts(), "casual", "en", storyteller))


# --- Pipeline -----------------------------------------------------------------------


def test_valid_ai_narrative_is_used_on_first_attempt():
    insight = run(FakeStoryteller(good_narrative()))

    assert insight.source == "ai"
    assert insight.model == "fake-model"
    assert insight.attempts == 1
    assert insight.rejected_attempts == []


def test_rejected_narrative_is_retried_with_validator_feedback():
    storyteller = FakeStoryteller(bad_narrative(), good_narrative())

    insight = run(storyteller)

    assert insight.source == "ai" and insight.attempts == 2
    assert storyteller.feedback_seen[0] is None
    assert any("does not match" in p for p in storyteller.feedback_seen[1])
    assert len(insight.rejected_attempts) == 1


def test_twice_rejected_falls_back_to_deterministic_insight():
    insight = run(FakeStoryteller(bad_narrative(), bad_narrative()))

    assert insight.source == "fallback"
    assert insight.fallback_reason == "validation_failed"
    assert len(insight.rejected_attempts) == 2
    assert insight.narrative == fallback_narrative(demo_facts(), "casual", "en")


def test_ai_error_falls_back_and_records_reason():
    insight = run(FakeStoryteller(StorytellerError("RateLimitError: 429")))

    assert insight.source == "fallback"
    assert insight.fallback_reason.startswith("ai_error: RateLimitError")


def test_no_storyteller_means_ai_disabled_fallback():
    insight = run(None)

    assert insight.source == "fallback"
    assert insight.fallback_reason == "ai_disabled"
    assert insight.attempts == 0


# --- Prompt and parsing ----------------------------------------------------------------


def test_prompt_contains_facts_evidence_and_settings():
    facts = demo_facts()
    prompt = build_prompt(facts, "analyst", "id")

    assert "Audience: analyst. Language: id." in prompt
    assert "S1.recent" in prompt and facts.evidence_event_ids[0] in prompt
    assert "Eastvale Athletic" in prompt


def test_prompt_includes_feedback_and_optional_json_shape():
    prompt = build_prompt(demo_facts(), "casual", "en", feedback=["number 99 is not supported"],
                          json_shape=True)

    assert "number 99 is not supported" in prompt
    assert '"metric_claims"' in prompt


def test_parse_json_narrative_tolerates_code_fences():
    text = "```json\n" + good_narrative().model_dump_json() + "\n```"

    assert parse_json_narrative(text) == good_narrative()
