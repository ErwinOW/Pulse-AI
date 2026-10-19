"""Narrative layer: fact sheets, structured output, validation, and fallbacks."""

from .facts import InsightFacts, MetricFact, facts_from_alert, match_minute
from .fallback import fallback_narrative
from .schema import Audience, Language, MetricClaim, Narrative, ValidationResult
from .validator import validate

__all__ = [
    "Audience",
    "InsightFacts",
    "Language",
    "MetricClaim",
    "MetricFact",
    "Narrative",
    "ValidationResult",
    "facts_from_alert",
    "fallback_narrative",
    "match_minute",
    "validate",
]
