"""Insight serving: instant cached/fallback text, plus a guarded live regenerate.

Insights describe an alert as it was when first raised (detection-time facts),
so the same text is valid at any t after detection and never mentions later
confirmations. GET never calls the model; regenerate does, one at a time and
within a daily cap, so a public demo link cannot exhaust the free tier.
"""

from datetime import date

from pydantic import BaseModel

from app.config import setting
from app.narrative import InsightFacts, facts_from_alert
from app.narrative.cache import InsightCache
from app.narrative.pipeline import Insight, generate_insight
from app.narrative.schema import Audience, Language
from app.narrative.storyteller import PROMPT_VERSION, Storyteller, storyteller_from_env

from . import service

DAILY_REGENERATE_CAP = 20  # live regenerations per server day (each is up to 2 model calls)


class InsightResponse(BaseModel):
    insight: Insight
    cached: bool  # served from the validated-AI cache
    facts: InsightFacts  # what the text was allowed to use (numbers + evidence ids)
    regenerations_left_today: int


class InsightError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def detection_facts(match_id: str, alert_id: str, t: float | None = None) -> InsightFacts:
    """Facts for an alert as first raised. KeyError if unknown or not yet raised by t."""
    match = service.load_match(match_id)
    end = float(int((match.events[-1].timestamp_seconds + 1) // 60) * 60)
    alert = next((a for a in service._minute_products(match_id, end)[0] if a.alert_id == alert_id), None)
    if alert is None or (t is not None and alert.first_detected_s > t):
        raise KeyError(alert_id)
    at_detection = next(
        a for a in service._minute_products(match_id, alert.first_detected_s)[0] if a.alert_id == alert_id
    )
    return facts_from_alert(match, at_detection)


class InsightService:
    def __init__(self, cache: InsightCache, cap: int = DAILY_REGENERATE_CAP, save: bool = False):
        self.cache = cache
        self.cap = cap
        self.save = save
        self.busy = False
        self._day = date.today()
        self._used = 0

    def regenerations_left(self) -> int:
        if date.today() != self._day:
            self._day, self._used = date.today(), 0
        return max(0, self.cap - self._used)

    def _cached(self, facts: InsightFacts, audience: Audience, language: Language) -> Insight | None:
        # Any model's validated text for these exact facts; newest wins.
        models = {e.get("model") for e in self.cache.entries.values() if e.get("model")}
        hits = [i for m in models if (i := self.cache.get(facts, audience, language, m, PROMPT_VERSION))]
        return max(hits, key=lambda i: i.generated_at, default=None)

    async def get(self, facts: InsightFacts, audience: Audience, language: Language) -> InsightResponse:
        cached = self._cached(facts, audience, language)
        if cached is None:
            fallback = await generate_insight(facts, audience, language, None)
            cached_flag, insight = False, fallback.model_copy(update={"fallback_reason": "not_generated_yet"})
        else:
            cached_flag, insight = True, cached
        return InsightResponse(insight=insight, cached=cached_flag, facts=facts,
                               regenerations_left_today=self.regenerations_left())

    async def regenerate(self, facts: InsightFacts, audience: Audience, language: Language,
                         storyteller: Storyteller | None) -> InsightResponse:
        if storyteller is None:
            raise InsightError(503, "AI is not configured on this server; showing saved text instead")
        if self.busy:
            raise InsightError(429, "another insight is being generated; try again in a few seconds")
        if self.regenerations_left() == 0:
            raise InsightError(429, "daily live-generation limit reached; showing saved text instead")

        self.busy = True
        self._used += 1
        try:
            insight = await generate_insight(facts, audience, language, storyteller)
        finally:
            self.busy = False
        if self.cache.put(facts, insight) and self.save:  # only validated AI text is stored
            self.cache.save()
        return InsightResponse(insight=insight, cached=False, facts=facts,
                               regenerations_left_today=self.regenerations_left())


insight_service = InsightService(
    InsightCache(), save=(setting("PULSE_SAVE_CACHE", "0") or "0") == "1"
)

_storyteller: list[Storyteller | None] = []


def get_storyteller() -> Storyteller | None:
    """FastAPI dependency: the real storyteller, built once (None when no key)."""
    if not _storyteller:
        _storyteller.append(storyteller_from_env())
    return _storyteller[0]


def get_insight_service() -> InsightService:
    return insight_service
