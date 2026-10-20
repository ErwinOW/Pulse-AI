"""Tests for the full-time report: fact sheet, checker, template, pipeline and API. No network."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.narrative.cache import InsightCache
from app.narrative.schema import MetricClaim
from app.report.checker import validate_report
from app.report.facts import audience_view, build_report_facts, end_time
from app.report.service import ReportService, get_report_service, report_facts
from app.report.writer import ReportResult, fallback_report, generate_report

client = TestClient(app)
DEMO = "demo-high-press"
COMBOS = [(a, lang) for a in ("casual", "analyst") for lang in ("en", "id")]


class FakeCommentator:
    model_name = "fake-model"

    def __init__(self, valid: bool = True):
        self.valid = valid
        self.calls = 0

    async def write(self, facts, audience, language, feedback=None):
        self.calls += 1
        report = fallback_report(facts, audience, language)
        return report if self.valid else report.model_copy(update={"headline": "A 999 goal thriller"})


def test_fact_sheet_matches_the_demo_match():
    facts = build_report_facts(DEMO)

    assert facts.final_score == "1-1"
    assert [(g.minute, g.team_name, g.start) for g in facts.goals] == [
        (35, "Northbridge FC", "unknown"),
        (64, "Eastvale Athletic", "ball_won"),
    ]
    assert facts.goals[1].loser_under_pressure is True and facts.goals[1].during_alert_by == "Eastvale Athletic"
    assert [(a.team_name, a.detected_minute) for a in facts.alerts] == [("Eastvale Athletic", 63)]
    assert facts.fact("A1.press_recent").value == 11 and facts.fact("A1.press_baseline").value == 5
    assert len(facts.phases) == 6


@pytest.mark.parametrize("match_id", [DEMO, "balanced"])
@pytest.mark.parametrize(("audience", "language"), COMBOS)
def test_template_reports_pass_the_checker(match_id, audience, language):
    facts = build_report_facts(match_id)
    report = fallback_report(facts, audience, language)
    result = validate_report(report, facts, language, audience)

    assert result.ok, result.problems
    assert 3 <= len(report.moments) <= 5


def test_checker_rejects_invented_numbers_causes_and_casual_rates():
    facts = build_report_facts(DEMO)
    base = fallback_report(facts, "analyst", "en")
    invented = base.model_copy(update={"headline": "A 999 goal thriller"})
    causal = base.model_copy(update={"moments": [*base.moments[:2], "64' The press caused the goal."]})
    rates = fallback_report(facts, "casual", "en").model_copy(
        update={"metric_claims": [MetricClaim(fact_id="EAS.high_presses_per_min", value=0.7)]}
    )
    wrong_claim = base.model_copy(update={"metric_claims": [MetricClaim(fact_id="A1.press_recent", value=12)]})

    assert any("999" in p for p in validate_report(invented, facts, "en", "analyst").problems)
    assert any("causal" in p for p in validate_report(causal, facts, "en", "analyst").problems)
    assert any("per-minute" in p for p in validate_report(rates, facts, "en", "casual").problems)
    assert any("does not match" in p for p in validate_report(wrong_claim, facts, "en", "analyst").problems)


def test_checker_rejects_claimed_intent_and_moments_out_of_order():
    facts = build_report_facts(DEMO)
    base = fallback_report(facts, "analyst", "en")
    intent = base.model_copy(update={"closing": "Tactical changes might have influenced the second half."})
    shuffled = base.model_copy(update={"moments": list(reversed(base.moments))})

    assert any("intent" in p for p in validate_report(intent, facts, "en", "analyst").problems)
    assert any("match order" in p for p in validate_report(shuffled, facts, "en", "analyst").problems)


def test_counts_are_whole_numbers_and_alerts_name_their_detector():
    facts = build_report_facts(DEMO)

    assert facts.fact("NBR.shots").value == 17 and isinstance(facts.fact("NBR.shots").value, int)
    assert facts.alerts[0].kind == "pressing increase"
    assert facts.fact("A1.press_ratio").value == 6.6  # 11 in 5 min vs 5 in 15 min
    assert facts.goals[1].ball_won_in == "their attacking third"  # NBR lost it in their own third


@pytest.mark.parametrize("match_id", [DEMO, "balanced"])
def test_casual_agents_only_see_at_most_four_preselected_statistics(match_id):
    view = audience_view(build_report_facts(match_id), "casual")

    assert 1 <= len(view.facts) <= 4
    assert all(f.unit in ("count", "seconds", "ratio") for f in view.facts)
    assert len(audience_view(build_report_facts(match_id), "analyst").facts) > 4


def test_indonesian_report_with_english_words_is_rejected():
    facts = build_report_facts(DEMO)
    base = fallback_report(facts, "analyst", "id")
    leaked = base.model_copy(update={"moments": [*base.moments[:-1], "64' PULSE's detector flagged a rise."]})

    assert any("English term" in p for p in validate_report(leaked, facts, "id", "analyst").problems)


def test_pipeline_uses_valid_ai_text_and_falls_back_after_two_rejections():
    facts = build_report_facts(DEMO)
    good = asyncio.run(generate_report(facts, "casual", "en", FakeCommentator()))
    broken = FakeCommentator(valid=False)
    bad = asyncio.run(generate_report(facts, "casual", "en", broken))

    assert good.source == "ai" and good.model == "fake-model"
    assert bad.source == "fallback" and bad.fallback_reason == "validation_failed" and broken.calls == 2


@pytest.fixture
def reports(tmp_path):
    service = ReportService(InsightCache(tmp_path / "reports.json", entry_model=ReportResult))
    app.dependency_overrides[get_report_service] = lambda: service
    yield service
    app.dependency_overrides.clear()


def get_report(t, match_id=DEMO, **params):
    return client.get(f"/api/matches/{match_id}/report", params={"t": t, **params})


def test_report_is_only_available_at_full_time(reports):
    end = end_time(DEMO)

    assert get_report(end - 600).status_code == 409
    body = get_report(end, audience="analyst", language="id").json()
    assert body["report"]["source"] == "fallback" and body["report"]["fallback_reason"] == "template_by_design"
    assert body["facts"]["final_score"] == "1-1"


def test_cached_ai_report_is_served(reports):
    facts = report_facts(DEMO)
    result = asyncio.run(generate_report(facts, "casual", "en", FakeCommentator()))
    reports.cache.put(facts, result)

    body = get_report(end_time(DEMO), audience="casual", language="en").json()
    assert body["cached"] is True and body["report"]["source"] == "ai"


def test_bad_parameters_are_rejected(reports):
    assert get_report(end_time(DEMO), audience="expert").status_code == 422
    assert get_report(9999, match_id="nope").status_code == 404


def test_shipped_demo_serves_template_reports_only():
    # Decision: no AI reports are shipped (meaning errors the checker can't catch), so the committed
    # cache is empty and every version is the labelled template that passes the checker.
    service = ReportService()
    app.dependency_overrides[get_report_service] = lambda: service
    try:
        for audience, language in COMBOS:
            body = get_report(end_time(DEMO), audience=audience, language=language).json()
            assert body["cached"] is False and body["report"]["source"] == "fallback", f"{audience}/{language}"
    finally:
        app.dependency_overrides.clear()
