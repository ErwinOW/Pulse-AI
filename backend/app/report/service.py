"""Serving full-time reports: cached validated AI text, or the labelled template. Never calls the model."""

from functools import lru_cache

from pydantic import BaseModel

from app.narrative.schema import Audience, Language

from .facts import ReportFacts, build_report_facts
from .writer import PROMPT_VERSION, ReportResult, generate_report, report_cache


class ReportResponse(BaseModel):
    report: ReportResult
    cached: bool
    facts: ReportFacts


@lru_cache(maxsize=None)
def report_facts(match_id: str) -> ReportFacts:
    return build_report_facts(match_id)


class ReportService:
    def __init__(self, cache=None):
        self.cache = cache if cache is not None else report_cache()

    def _cached(self, facts: ReportFacts, audience: Audience, language: Language) -> ReportResult | None:
        models = {e.get("model") for e in self.cache.entries.values() if e.get("model")}
        hits = [r for m in models if (r := self.cache.get(facts, audience, language, m, PROMPT_VERSION))]
        return max(hits, key=lambda r: r.generated_at, default=None)

    async def get(self, match_id: str, audience: Audience, language: Language) -> ReportResponse:
        facts = report_facts(match_id)
        cached = self._cached(facts, audience, language)
        if cached is not None:
            return ReportResponse(report=cached, cached=True, facts=facts)
        template = await generate_report(facts, audience, language, None)
        template = template.model_copy(update={"fallback_reason": "not_generated_yet"})
        return ReportResponse(report=template, cached=False, facts=facts)


report_service = ReportService()


def get_report_service() -> ReportService:
    return report_service
