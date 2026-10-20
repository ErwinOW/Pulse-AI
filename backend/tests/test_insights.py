"""Tests for the insight endpoints (backend/app/api/insights.py). No network: storytellers are fakes."""

import pytest
from fastapi.testclient import TestClient

from app.api.insights import InsightService, get_insight_service, get_storyteller
from app.main import app
from app.narrative import fallback_narrative
from app.narrative.cache import InsightCache

client = TestClient(app)
DEMO, DEMO_ALERT = "demo-high-press", "pressing_increase-EAS-1"
DETECTED_S = 3720.0  # demo alert first raised at 62:00 (minute 63)


class FakeStoryteller:
    """Writes the known-valid fallback text, or a broken version of it."""

    model_name = "fake-model"

    def __init__(self, valid: bool = True):
        self.valid = valid
        self.calls = 0

    async def write(self, facts, audience, language, feedback=None):
        self.calls += 1
        narrative = fallback_narrative(facts, audience, language)
        return narrative if self.valid else narrative.model_copy(update={"event_ids": ["not-an-event"]})


@pytest.fixture
def insights(tmp_path):
    service = InsightService(InsightCache(tmp_path / "cache.json"))
    app.dependency_overrides[get_insight_service] = lambda: service
    app.dependency_overrides[get_storyteller] = lambda: None  # never the real model
    yield service
    app.dependency_overrides.clear()


def use_storyteller(storyteller):
    app.dependency_overrides[get_storyteller] = lambda: storyteller


def get(alert_id=DEMO_ALERT, match_id=DEMO, **params):
    return client.get(f"/api/matches/{match_id}/insights/{alert_id}", params=params)


def regenerate(alert_id=DEMO_ALERT, match_id=DEMO, **params):
    return client.post(f"/api/matches/{match_id}/insights/{alert_id}/regenerate", params=params)


def test_uncached_insight_is_the_labelled_fallback(insights):
    alert_id = client.get("/api/matches/balanced/state", params={"t": 9999}).json()["alerts"][0]["alert_id"]
    body = get(alert_id, "balanced", audience="analyst", language="id").json()

    assert body["insight"]["source"] == "fallback"
    assert body["insight"]["fallback_reason"] == "not_generated_yet"
    assert body["cached"] is False and body["facts"]["insight_id"] == alert_id


def test_alert_not_raised_by_t_is_404(insights):
    assert get(t=DETECTED_S - 60).status_code == 404
    assert get(t=DETECTED_S).status_code == 200


def test_unknown_alert_or_match_is_404(insights):
    assert get("pressing_increase-EAS-9").status_code == 404
    assert get(match_id="nope").status_code == 404
    assert regenerate("pressing_increase-EAS-9").status_code == 404


def test_bad_audience_or_language_is_422(insights):
    assert get(audience="expert").status_code == 422
    assert get(language="fr").status_code == 422


def test_insight_facts_are_detection_time_and_do_not_depend_on_t(insights):
    at_detection, at_end = get(t=DETECTED_S).json()["facts"], get(t=9999).json()["facts"]

    assert at_detection == at_end
    assert at_end["last_confirmed_minute"] == at_end["detected_minute"] == 63


def test_regenerated_valid_text_is_ai_and_then_served_from_cache(insights):
    use_storyteller(FakeStoryteller())
    made = regenerate(audience="analyst", language="en").json()
    served = get(audience="analyst", language="en").json()

    assert made["insight"]["source"] == "ai" and made["insight"]["model"] == "fake-model"
    assert served["cached"] is True and served["insight"] == made["insight"]
    assert get(audience="casual", language="en").json()["cached"] is False  # other versions untouched


def test_rejected_regeneration_falls_back_and_keeps_the_cached_text(insights):
    use_storyteller(FakeStoryteller())
    good = regenerate().json()["insight"]
    broken = FakeStoryteller(valid=False)
    use_storyteller(broken)
    result = regenerate().json()

    assert result["insight"]["source"] == "fallback"
    assert result["insight"]["fallback_reason"] == "validation_failed" and broken.calls == 2
    assert get().json()["insight"] == good


def test_regenerate_without_a_key_is_503(insights):
    assert regenerate().status_code == 503


def test_regenerate_while_another_is_running_is_429(insights):
    use_storyteller(FakeStoryteller())
    insights.busy = True

    assert regenerate().status_code == 429


def test_daily_cap_blocks_further_regenerations(insights):
    insights.cap = 1
    storyteller = FakeStoryteller()
    use_storyteller(storyteller)

    first, second = regenerate(), regenerate()

    assert first.status_code == 200 and first.json()["regenerations_left_today"] == 0
    assert second.status_code == 429 and storyteller.calls == 1


def test_committed_cache_covers_the_demo_alert_in_all_four_versions():
    # Fixture freshness: the shipped cache must match the facts the API serves today.
    service = InsightService(InsightCache())
    app.dependency_overrides[get_insight_service] = lambda: service
    try:
        for audience in ("casual", "analyst"):
            for language in ("en", "id"):
                body = get(audience=audience, language=language, t=DETECTED_S).json()
                assert body["cached"] is True, f"{audience}/{language} not cached"
                assert body["insight"]["source"] == "ai"
    finally:
        app.dependency_overrides.clear()
