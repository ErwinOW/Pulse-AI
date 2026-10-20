"""Evidence validator: checks a narrative against its fact sheet before display.

Deterministic on purpose: an LLM checking an LLM is not trustworthy enough
for numbers. Checks (brief, Feature F):
  1. event ids exist in the insight's evidence
  2. metric claims match computed facts (fact id => metric, team and window)
  3. every number written in the text is supported by the facts
  4. confidence is not upgraded
  5. no unhedged causal language; none at all in headline/summary
  6. hypothetical content is labelled; observed insights are never hypothetical
Indonesian decimals use a comma (71,4%), so both separators are accepted.
"""

import re

from .facts import InsightFacts, match_minute
from .schema import Audience, Language, Narrative, ValidationResult

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")

# Phrases rather than bare verbs, so "made 11 high presses" / "membuat 11 pressing" still pass.
# v2 additions came from real Gemini output that slipped through v1 (see docs/PROGRESS.md).
CAUSAL_RE = re.compile(
    r"\b(caus(e|es|ed|ing)|led to|leads? to|leading to|because of|due to|result(s|ed)? in|"
    r"(made|makes|making) (it|them|him|her)|forc(e|es|ed|ing)|responded|in response|"
    r"menyebabkan|mengakibatkan|disebabkan|karena|akibat|"
    r"(hal ini|ini|itu|tersebut) membuat|memaksa|sehingga|merespons|merespon|berdampak)\b",
    re.IGNORECASE,
)
# Decimal separators by language: English 2.2, Indonesian 2,2.
WRONG_DECIMAL_RE = {"en": re.compile(r"\d,\d"), "id": re.compile(r"\d\.\d")}
# English fact-sheet terms that leaked into real Indonesian output.
ENGLISH_IN_ID_RE = re.compile(r"\b(count|turnovers?|baseline|recent|build-up)\b", re.IGNORECASE)
HEDGE_RE = re.compile(
    r"\b(may|might|could|possibly|likely|perhaps|suggests?|mungkin|bisa jadi|kemungkinan|"
    r"diduga|tampaknya)\b",
    re.IGNORECASE,
)
HYPOTHETICAL_RE = re.compile(
    r"\b(what if|would have|could have|had they|seandainya|jika saja|andai)\b", re.IGNORECASE
)
VALUE_TOLERANCE = 0.051  # claims may round to one decimal


def _variants(value: float) -> set[float]:
    return {round(value, 2), round(value, 1), float(round(value))}


def allowed_numbers(facts: InsightFacts) -> set[float]:
    """Every number a narrative may legitimately write."""
    allowed: set[float] = set()
    for fact in facts.facts:
        if fact.value is not None:
            allowed |= _variants(fact.value)
        allowed.add(float(match_minute(fact.window_start_s)))
        allowed.add(float(match_minute(fact.window_end_s) - 1))

    # Changes and ratios between a signal's baseline and recent windows.
    for fact in facts.facts:
        if not fact.fact_id.endswith(".recent"):
            continue
        base = facts.fact(fact.fact_id.replace(".recent", ".baseline"))
        if base is None or base.value is None or fact.value is None:
            continue
        allowed |= _variants(abs(fact.value - base.value))
        if base.value > 0:
            allowed |= _variants(fact.value / base.value)

    allowed |= {float(m) for m in (facts.onset_minute, facts.detected_minute,
                                   facts.last_confirmed_minute, facts.recent_window_minutes,
                                   facts.baseline_window_minutes)}
    allowed |= {float(g) for g in facts.score.values()}
    return allowed


def numbers_in(text: str) -> list[float]:
    return [float(m.replace(",", ".")) for m in NUMBER_RE.findall(text)]


CASUAL_MAX_CLAIMS = 2


def context_numbers(facts: InsightFacts) -> set[float]:
    """Minutes, window lengths and the score: allowed in any text without a metric claim."""
    return {float(n) for n in (facts.onset_minute, facts.detected_minute, facts.last_confirmed_minute,
                               facts.recent_window_minutes, facts.baseline_window_minutes,
                               *facts.score.values())}


def validate(
    narrative: Narrative, facts: InsightFacts, language: Language | None = None,
    audience: Audience | None = None,
) -> ValidationResult:
    problems: list[str] = []

    # 0. Decimal separator matches the language (checked when the language is known)
    if language is not None:
        for field in ("headline", "summary", "interpretation"):
            if WRONG_DECIMAL_RE[language].search(getattr(narrative, field)):
                expected = "a decimal point (2.2)" if language == "en" else "a decimal comma (2,2)"
                problems.append(f"{field}: numbers in language {language!r} must use {expected}")
            if language == "id":
                leaked = ENGLISH_IN_ID_RE.search(getattr(narrative, field))
                if leaked:
                    problems.append(f"{field}: English term {leaked.group(0)!r} in Indonesian text")

    # 1. Evidence
    if not narrative.event_ids:
        problems.append("no supporting event ids cited")
    evidence = set(facts.evidence_event_ids)
    for event_id in narrative.event_ids:
        if event_id not in evidence:
            problems.append(f"event id {event_id!r} is not part of this insight's evidence")

    # 2. Metric claims
    if not narrative.metric_claims:
        problems.append("no metric claims")
    for claim in narrative.metric_claims:
        fact = facts.fact(claim.fact_id)
        if fact is None:
            problems.append(f"unknown fact id {claim.fact_id!r}")
        elif fact.value is None:
            problems.append(f"fact {claim.fact_id!r} is unavailable and cannot be claimed")
        elif not (abs(claim.value - fact.value) <= VALUE_TOLERANCE
                  or claim.value == round(fact.value)):
            problems.append(f"claim {claim.fact_id}={claim.value} does not match computed {fact.value}")

    # 3. Numbers in the text
    allowed = allowed_numbers(facts)
    for field in ("headline", "summary", "interpretation"):
        for number in numbers_in(getattr(narrative, field)):
            if not any(abs(number - a) < 1e-6 for a in allowed):
                problems.append(f"{field}: number {number:g} is not supported by the facts")

    # 4. Confidence
    if narrative.confidence != facts.confidence:
        problems.append(f"confidence {narrative.confidence!r} differs from computed {facts.confidence!r}")

    # 5. Causal language
    for field in ("headline", "summary"):
        match = CAUSAL_RE.search(getattr(narrative, field))
        if match:
            problems.append(f"{field}: causal wording {match.group(0)!r} is not allowed in factual text")
    causal = CAUSAL_RE.search(narrative.interpretation)
    if causal and not HEDGE_RE.search(narrative.interpretation):
        problems.append(f"interpretation: causal wording {causal.group(0)!r} must be hedged")

    # 6. Hypotheticals
    text = " ".join((narrative.headline, narrative.summary, narrative.interpretation))
    if HYPOTHETICAL_RE.search(text) and not narrative.is_hypothetical:
        problems.append("hypothetical wording present but is_hypothetical is false")
    if narrative.is_hypothetical and facts.kind == "pressing_increase":
        problems.append("an observed pattern cannot be marked hypothetical")

    # 7. Casual readers get at most 2 statistics, as event totals (no rates or percentages)
    if audience == "casual":
        if len(narrative.metric_claims) > CASUAL_MAX_CLAIMS:
            problems.append(f"casual text uses {len(narrative.metric_claims)} statistics; "
                            f"use at most {CASUAL_MAX_CLAIMS}")
        claimed: set[float] = set()
        for claim in narrative.metric_claims:
            fact = facts.fact(claim.fact_id)
            if fact is not None and fact.unit != "count":
                problems.append(f"casual text must use event totals, not {fact.unit} ({claim.fact_id})")
            claimed.add(float(claim.value))
        ok_numbers = claimed | context_numbers(facts)
        for field in ("headline", "summary", "interpretation"):
            for number in numbers_in(getattr(narrative, field)):
                if not any(abs(number - a) < 1e-6 for a in ok_numbers):
                    problems.append(f"{field}: casual text may only use the claimed totals, "
                                    f"not {number:g}")

    return ValidationResult(ok=not problems, problems=problems)
