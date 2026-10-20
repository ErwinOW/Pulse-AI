"""Fact-checker for full-time reports (and Analyst answers): the same rules as insights.

Deterministic: every number must come from the fact sheet (or be a minute, score or
window length), claims must match the computed values, cause-and-effect is only allowed
hedged in the closing line, and Indonesian text uses decimal commas and no English terms.
"""

import re

from pydantic import BaseModel, ConfigDict, Field

from app.narrative.schema import Audience, Language, MetricClaim, ValidationResult
from app.narrative.validator import (
    CAUSAL_RE,
    ENGLISH_IN_ID_RE,
    HEDGE_RE,
    HYPOTHETICAL_RE,
    VALUE_TOLERANCE,
    WRONG_DECIMAL_RE,
    _variants,
    numbers_in,
)

from .facts import ReportFacts

CASUAL_MAX_CLAIMS = 4  # a whole match gets a little more room than a single insight
# Event data shows what happened, never what anyone decided or intended.
INTENT_RE = re.compile(
    r"\b(tactical (change|changes|switch|shift|decision)s?|strateg(y|ies|ic)|game ?plan|decided|chose|"
    r"opted|intention|intended|adjust(ed|ment|ments)?|perubahan taktik|strategi|memutuskan|memilih untuk|"
    r"rencana permainan|niat untuk)\b",
    re.IGNORECASE,
)
LEADING_MINUTE_RE = re.compile(r"^\s*(\d+)'")
# English words that leaked into Indonesian reports (beyond the shared insight list).
ENGLISH_IN_ID_REPORT_RE = re.compile(r"\b(the|and|with|flagged|detector|rise|ball won|unknown)\b", re.IGNORECASE)


class MatchReport(BaseModel):
    """What the Commentator must return."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    headline: str = Field(min_length=1, max_length=120)
    moments: list[str] = Field(min_length=3, max_length=5)  # key moments in match order
    closing: str = Field(min_length=1, max_length=600)  # hedged takeaway, 2 sentences asked
    metric_claims: list[MetricClaim]


def allowed_numbers(facts: ReportFacts) -> set[float]:
    allowed = set(facts.context_numbers())
    for fact in facts.facts:
        allowed |= _variants(fact.value)
    return allowed


def check_texts(
    factual: dict[str, str],
    hedged: dict[str, str],
    claims: list[MetricClaim],
    facts: ReportFacts,
    language: Language,
    audience: Audience | None,
) -> list[str]:
    """Shared rules. `factual` fields may not suggest causes; `hedged` fields may, if hedged."""
    problems: list[str] = []
    texts = {**factual, **hedged}

    for field, text in texts.items():
        if WRONG_DECIMAL_RE[language].search(text):
            expected = "a decimal point (2.2)" if language == "en" else "a decimal comma (2,2)"
            problems.append(f"{field}: numbers in language {language!r} must use {expected}")
        if language == "id" and (leaked := ENGLISH_IN_ID_RE.search(text) or ENGLISH_IN_ID_REPORT_RE.search(text)):
            problems.append(f"{field}: English term {leaked.group(0)!r} in Indonesian text")
        if HYPOTHETICAL_RE.search(text):
            problems.append(f"{field}: no hypotheticals; describe what happened")
        if match := INTENT_RE.search(text):
            problems.append(f"{field}: {match.group(0)!r} claims a decision or intent the data cannot show")

    for claim in claims:
        fact = facts.fact(claim.fact_id)
        if fact is None:
            problems.append(f"unknown fact id {claim.fact_id!r}")
        elif not (abs(claim.value - fact.value) <= VALUE_TOLERANCE or claim.value == round(fact.value)):
            problems.append(f"claim {claim.fact_id}={claim.value} does not match computed {fact.value}")

    allowed = allowed_numbers(facts)
    for field, text in texts.items():
        for number in numbers_in(text):
            if not any(abs(number - a) < 1e-6 for a in allowed):
                problems.append(f"{field}: number {number:g} is not supported by the facts")

    for field, text in factual.items():
        if match := CAUSAL_RE.search(text):
            problems.append(f"{field}: causal wording {match.group(0)!r} is not allowed in factual text")
    for field, text in hedged.items():
        if (match := CAUSAL_RE.search(text)) and not HEDGE_RE.search(text):
            problems.append(f"{field}: causal wording {match.group(0)!r} must be hedged")

    if audience == "casual":
        if len(claims) > CASUAL_MAX_CLAIMS:
            problems.append(f"casual text uses {len(claims)} statistics; use at most {CASUAL_MAX_CLAIMS}")
        for claim in claims:
            fact = facts.fact(claim.fact_id)
            if fact is not None and fact.unit == "per_min":
                problems.append(f"casual text must not use per-minute rates ({claim.fact_id})")
        ok = {float(c.value) for c in claims} | facts.context_numbers()
        for field, text in texts.items():
            for number in numbers_in(text):
                if not any(abs(number - a) < 1e-6 for a in ok):
                    problems.append(f"{field}: casual text may only use claimed statistics, not {number:g}")
    return problems


def validate_report(
    report: MatchReport, facts: ReportFacts, language: Language, audience: Audience | None = None
) -> ValidationResult:
    factual = {"headline": report.headline, **{f"moment {i}": m for i, m in enumerate(report.moments, 1)}}
    problems = check_texts(factual, {"closing": report.closing}, report.metric_claims, facts, language, audience)
    if not report.metric_claims:
        problems.append("no metric claims")
    minutes = [int(m.group(1)) for text in report.moments if (m := LEADING_MINUTE_RE.match(text))]
    if len(minutes) != len(report.moments):
        problems.append("every moment must start with its minute, e.g. \"64'\"")
    elif minutes != sorted(minutes):
        problems.append(f"moments must be in match order (got minutes {minutes})")
    return ValidationResult(ok=not problems, problems=problems)
