"""Tests for the validated-insight cache (backend/app/narrative/cache.py)."""

import asyncio
from functools import cache

from app.detection import detect_alerts
from app.narrative import facts_from_alert, fallback_narrative
from app.narrative.cache import InsightCache, cache_key
from app.narrative.pipeline import generate_insight
from app.simulator import DEMO_HIGH_PRESS, generate


@cache
def demo_facts():
    match, _ = generate(DEMO_HIGH_PRESS)
    (alert,) = detect_alerts(match.events, ("NBR", "EAS"), 6000)
    return facts_from_alert(match, alert)


class OneShotStoryteller:
    model_name = "fake-model"

    async def write(self, facts, audience, language, feedback=None):
        return fallback_narrative(facts, audience, language)  # known-valid content


def ai_insight():
    return asyncio.run(generate_insight(demo_facts(), "casual", "en", OneShotStoryteller()))


def test_round_trip_through_file(tmp_path):
    path = tmp_path / "cache.json"
    insight = ai_insight()
    store = InsightCache(path)
    assert store.put(demo_facts(), insight)
    store.save()

    reloaded = InsightCache(path).get(demo_facts(), "casual", "en", "fake-model", insight.prompt_version)

    assert reloaded == insight  # same text, model, prompt version, and timestamp


def test_fallbacks_are_not_cached(tmp_path):
    fallback = asyncio.run(generate_insight(demo_facts(), "casual", "en", None))

    assert InsightCache(tmp_path / "cache.json").put(demo_facts(), fallback) is False


def test_key_changes_with_prompt_version_language_and_model():
    facts = demo_facts()
    base = cache_key(facts, "casual", "en", "m", "v3")

    assert base != cache_key(facts, "casual", "en", "m", "v4")
    assert base != cache_key(facts, "casual", "id", "m", "v3")
    assert base != cache_key(facts, "casual", "en", "other-model", "v3")
    assert base == cache_key(facts, "casual", "en", "m", "v3")  # deterministic


def test_prune_removes_other_prompt_versions(tmp_path):
    store = InsightCache(tmp_path / "cache.json")
    insight = ai_insight()
    store.put(demo_facts(), insight)

    assert store.prune(insight.prompt_version) == 0
    assert store.prune("some-newer-version") == 1
    assert store.entries == {}


def test_missing_entry_returns_none(tmp_path):
    assert InsightCache(tmp_path / "none.json").get(demo_facts(), "analyst", "id", "m", "v3") is None
