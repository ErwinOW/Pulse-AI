"""Fact-checker for "Ask the analyst" answers: the report rules, applied to one short answer.

Deterministic: the agent must have looked something up, every number must be in that question's
ledger (or be a minute, score or window bound), cause-and-effect only hedged, no claims about
intent, no hypotheticals, and Indonesian answers use decimal commas and no English terms. An
off-topic question gets the fixed decline below, which needs no tool call.
"""

import re

from app.narrative.schema import Language, ValidationResult
from app.narrative.validator import (
    CAUSAL_RE,
    ENGLISH_IN_ID_RE,
    HEDGE_RE,
    HYPOTHETICAL_RE,
    WRONG_DECIMAL_RE,
    _variants,
    numbers_in,
)

from .analyst_tools import MatchTools
from .checker import ENGLISH_IN_ID_REPORT_RE, INTENT_RE

MAX_CHARS = 400
MAX_SENTENCES = 3
DECLINE = {
    "en": "I can only answer questions about this match's data.",
    "id": "Saya hanya bisa menjawab pertanyaan tentang data pertandingan ini.",
}
SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)")


def check_answer(answer: str, tools: MatchTools, language: Language) -> ValidationResult:
    text = answer.strip()
    if text == DECLINE[language]:
        return ValidationResult(ok=True, problems=[])

    problems: list[str] = []
    if not tools.calls:
        problems.append("look the facts up with a tool before answering")
    if not text:
        problems.append("empty answer")
    if len(text) > MAX_CHARS:
        problems.append(f"answer is {len(text)} characters; use at most {MAX_CHARS}")
    if (sentences := len(SENTENCE_END_RE.findall(text))) > MAX_SENTENCES:
        problems.append(f"answer has {sentences} sentences; use at most {MAX_SENTENCES}")

    if WRONG_DECIMAL_RE[language].search(text):
        expected = "a decimal point (2.2)" if language == "en" else "a decimal comma (2,2)"
        problems.append(f"numbers in language {language!r} must use {expected}")
    if language == "id" and (leaked := ENGLISH_IN_ID_RE.search(text) or ENGLISH_IN_ID_REPORT_RE.search(text)):
        problems.append(f"English term {leaked.group(0)!r} in Indonesian text")
    if HYPOTHETICAL_RE.search(text):
        problems.append("no hypotheticals; describe what happened")
    if match := INTENT_RE.search(text):
        problems.append(f"{match.group(0)!r} claims a decision or intent the data cannot show")
    if (match := CAUSAL_RE.search(text)) and not HEDGE_RE.search(text):
        problems.append(f"causal wording {match.group(0)!r} must be hedged (e.g. 'may have')")

    allowed = set(tools.context)
    for fact in tools.ledger:
        allowed |= _variants(fact.value)
    for number in numbers_in(text):
        if not any(abs(number - a) < 1e-6 for a in allowed):
            problems.append(f"number {number:g} is not in the data you looked up")
    return ValidationResult(ok=not problems, problems=problems)
