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
def demo_alert():
    match, _ = generate(DEMO_HIGH_PRESS)
    (alert,) = detect_alerts(match.events, ("NBR", "EAS"), 6000)
    return match, alert


@cache
def demo_facts():
    return facts_from_alert(*demo_alert())


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


def test_fact_sheet_uses_the_pre_shift_baseline_from_first_detection():
    # Later confirmations' baselines already contain the press, hiding the contrast.
    _, alert = demo_alert()
    facts = demo_facts()
    recent, baseline = facts.fact("S1.recent"), facts.fact("S1.baseline")

    assert recent.window_end_s == alert.first_detected_s
    assert baseline.window_end_s == recent.window_start_s
    assert recent.value > baseline.value  # the increase the alert claims is visible


def test_fact_sheet_confidence_matches_its_own_signals():
    # Confidence and signals must come from the same moment: strong iff all 3 passed.
    facts = demo_facts()
    expected = "strong" if len(facts.signals_met) == 3 else "moderate"

    assert facts.confidence == expected


# --- Fallbacks must pass the same validator as AI output ----------------------------


@pytest.mark.parametrize(("audience", "language"), COMBOS)
def test_fallback_narratives_pass_validation(audience, language):
    narrative = fallback_narrative(demo_facts(), audience, language)
    result = validate(narrative, demo_facts(), language, audience)

    assert result.ok, result.problems


def test_casual_text_is_limited_to_two_totals():
    facts = demo_facts()
    casual = fallback_narrative(facts, "casual", "en")
    rates = casual.model_copy(update={
        "summary": f"{facts.team_name} pressed high 2.2 per minute.",
        "metric_claims": [MetricClaim(fact_id="S1.recent", value=2.2)],
    })
    too_many = casual.model_copy(update={
        "metric_claims": [MetricClaim(fact_id=f, value=facts.fact(f).value)
                          for f in ("S1.recent_count", "S1.baseline_count", "S2.recent_count")],
    })

    assert len(casual.metric_claims) <= 2
    assert all(facts.fact(c.fact_id).unit == "count" for c in casual.metric_claims)
    assert any("event totals" in p for p in validate(rates, facts, "en", "casual").problems)
    assert any("at most 2" in p for p in validate(too_many, facts, "en", "casual").problems)
    assert validate(rates, facts, "en", "analyst").ok  # analysts may use rates


def test_audiences_differ_but_share_the_same_facts():
    casual = fallback_narrative(demo_facts(), "casual", "en")
    analyst = fallback_narrative(demo_facts(), "analyst", "en")

    assert casual.summary != analyst.summary
    assert casual.event_ids == analyst.event_ids
    assert casual.confidence == analyst.confidence


def test_indonesian_uses_decimal_comma():
    assert fmt(71.4, "id") == "71,4"
    assert fmt(71.4, "en") == "71.4"
    assert fmt(1.13, "en") == "1.1"  # one decimal is the honest precision
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


@pytest.mark.parametrize(
    "sentence",
    [
        # Real Gemini phrasings that passed validator v1:
        " This aggressive approach made it much harder for Northbridge FC to keep possession.",
        " Hal ini membuat Northbridge FC mengalami kehilangan bola.",
        " Northbridge FC merespons dengan penurunan akurasi umpan.",
        " The press forced Northbridge FC long.",
        " Northbridge FC kehilangan bola sehingga akurasi umpan turun.",
    ],
    ids=["made-it", "hal-ini-membuat", "merespons", "forced", "sehingga"],
)
def test_rejects_causal_phrasings_found_in_live_output(sentence):
    summary = base_narrative().summary + sentence

    assert any("causal" in p for p in problems_for(summary=summary))


def test_allows_non_causal_make():
    summary = base_narrative().summary + " Eastvale Athletic made 11 high presses."

    assert not any("causal" in p for p in problems_for(summary=summary))


def test_rejects_wrong_decimal_separator_for_language():
    facts = demo_facts()
    en = fallback_narrative(facts, "analyst", "en")
    id_ = fallback_narrative(facts, "analyst", "id")

    assert any("decimal point" in p for p in
               validate(en.model_copy(update={"summary": "Rate 2,2 per min."}), facts, "en").problems)
    assert any("decimal comma" in p for p in
               validate(id_.model_copy(update={"summary": "Laju 2.2 per menit."}), facts, "id").problems)


@pytest.mark.parametrize("leak", ["dengan total 5 count", "turnover di bawah tekanan"])
def test_rejects_english_terms_in_indonesian(leak):
    facts = demo_facts()
    narrative = fallback_narrative(facts, "analyst", "id")
    leaked = narrative.model_copy(update={"summary": narrative.summary + f" Catatan: {leak}."})

    assert any("English term" in p for p in validate(leaked, facts, "id").problems)


def test_rejects_unhedged_causal_interpretation():
    assert any("hedged" in p for p in problems_for(interpretation="The press led to turnovers."))


def test_accepts_hedged_causal_interpretation():
    assert problems_for(interpretation="The press may have led to more turnovers.") == []


def test_rejects_unlabelled_hypothetical():
    problems = problems_for(interpretation="What if they had pressed earlier?")

    assert any("hypothetical" in p for p in problems)


def test_rejects_observed_pattern_marked_hypothetical():
    assert any("hypothetical" in p for p in problems_for(is_hypothetical=True))
