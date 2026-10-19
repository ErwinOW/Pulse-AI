"""Tests for fact sheets, the evidence validator, and fallback narratives (no LLM)."""

from functools import cache

import pytest

from app.detection import detect_alerts
from app.narrative import MetricClaim, facts_from_alert, fallback_narrative, validate
from app.narrative.fallback import fmt
from app.narrative.validator import numbers_in
from app.simulator import DEMO_HIGH_PRESS, generate

COMBOS = [(a, l) for a in ("casual", "analyst") for l in ("en", "id")]


@cache
def demo_facts():
    match, _ = generate(DEMO_HIGH_PRESS)
    (alert,) = detect_alerts(match.events, ("NBR", "EAS"), 6000)
    return facts_from_alert(match, alert)


def base_narrative():
    return fallback_narrative(demo_facts(), "analyst", "en")


def problems_for(**update) -> list[str]:
    return validate(base_narrative().model_copy(update=update), demo_facts()).problems


# --- Fact sheet --------------------------------------------------------------------


def test_fact_sheet_describes_the_demo_alert():
    facts = demo_facts()

    assert (facts.team_name, facts.opponent_name) == ("Eastvale Athletic", "Northbridge FC")
    assert facts.evidence_event_ids
    for signal in ("S1", "S2", "S3"):
        for part in ("baseline", "recent", "baseline_count", "recent_count"):
            assert facts.fact(f"{signal}.{part}") is not None
    assert facts.recent_window_minutes == 5
    assert facts.onset_minute <= facts.detected_minute <= facts.last_confirmed_minute


# --- Fallbacks must pass the same validator as AI output ----------------------------


@pytest.mark.parametrize(("audience", "language"), COMBOS)
def test_fallback_narratives_pass_validation(audience, language):
    narrative = fallback_narrative(demo_facts(), audience, language)
    result = validate(narrative, demo_facts())

    assert result.ok, result.problems


def test_audiences_differ_but_share_the_same_facts():
    casual = fallback_narrative(demo_facts(), "casual", "en")
    analyst = fallback_narrative(demo_facts(), "analyst", "en")

    assert casual.summary != analyst.summary
    assert casual.event_ids == analyst.event_ids
    assert casual.confidence == analyst.confidence


def test_indonesian_uses_decimal_comma():
    assert fmt(71.4, "id") == "71,4"
    assert fmt(71.4, "en") == "71.4"
    assert numbers_in("akurasi 71,4% dan 2.5 per menit") == [71.4, 2.5]


# --- The validator rejects bad narratives (the brief's "trust check") ---------------


def test_rejects_claim_that_does_not_match_computed_value():
    facts = demo_facts()
    true_value = facts.fact("S1.recent").value
    claims = [MetricClaim(fact_id="S1.recent", value=true_value + 1)]

    assert any("does not match" in p for p in problems_for(metric_claims=claims))


def test_rejects_claim_about_unknown_fact():
    claims = [MetricClaim(fact_id="S9.recent", value=1.0)]

    assert any("unknown fact" in p for p in problems_for(metric_claims=claims))


def test_rejects_invented_number_in_text():
    summary = base_narrative().summary + " They pressed 987 times."

    assert any("987" in p for p in problems_for(summary=summary))


def test_rejects_event_ids_outside_the_evidence():
    assert any("not part of" in p for p in problems_for(event_ids=["demo-high-press-e0001"]))


def test_rejects_confidence_upgrade():
    upgraded = "strong" if demo_facts().confidence == "moderate" else "moderate"

    assert any("confidence" in p for p in problems_for(confidence=upgraded))


@pytest.mark.parametrize(
    "summary_suffix",
    [" The press caused the goal.", " Pressing ini menyebabkan gol."],
    ids=["english", "indonesian"],
)
def test_rejects_causal_wording_in_factual_text(summary_suffix):
    summary = base_narrative().summary + summary_suffix

    assert any("causal" in p for p in problems_for(summary=summary))


def test_rejects_unhedged_causal_interpretation():
    assert any("hedged" in p for p in problems_for(interpretation="The press led to turnovers."))


def test_accepts_hedged_causal_interpretation():
    assert problems_for(interpretation="The press may have led to more turnovers.") == []


def test_rejects_unlabelled_hypothetical():
    problems = problems_for(interpretation="What if they had pressed earlier?")

    assert any("hypothetical" in p for p in problems)


def test_rejects_observed_pattern_marked_hypothetical():
    assert any("hypothetical" in p for p in problems_for(is_hypothetical=True))
