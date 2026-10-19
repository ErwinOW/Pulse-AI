"""Storyteller: a Microsoft Agent Framework agent that writes a narrative from a fact sheet.

It only words verified facts; numbers are checked afterwards by validator.py.
Two output modes, because providers differ in structured-output support:
- schema mode: response_format=Narrative (strict JSON schema, parsed by Agent Framework)
- prompt mode: JSON requested in the prompt, parsed here
"""

import asyncio
import json
import re
from typing import Protocol

from agent_framework import Agent
from pydantic import ValidationError

from app.config import setting

from .facts import InsightFacts
from .schema import Audience, Language, Narrative

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
TIMEOUT_S = 15.0
# v2: explicit causal phrasings, decimal separators, ID wording
# v3: rate units, no implied decisions/intent, fewer suggested stock phrases
# v4: counts written as number + noun (v3 leaked the word "count"); output length cap
PROMPT_VERSION = "v4"
MAX_OUTPUT_TOKENS = 900  # an insight never needs more; stops runaway generations

INSTRUCTIONS = """You are PULSE's Storyteller: you turn verified football match facts into short,
accurate insights. You never compute statistics; you only word the facts you are given.

Hard rules (your answer is checked automatically and rejected if any rule is broken):
1. Use ONLY numbers that appear in the fact sheet, written as digits. Never invent, estimate,
   or derive numbers yourself.
2. For every number you use, add an entry to metric_claims with that fact's fact_id and value.
3. event_ids: cite 3 to 8 ids, taken ONLY from the fact sheet's evidence_event_ids.
4. confidence must equal the fact sheet's confidence. is_hypothetical must be false.
5. Correlation is not causation. Headline and summary describe what was observed only, side
   by side, never one thing producing another. Forbidden there: "caused", "led to", "because
   of", "due to", "resulted in", "made it harder", "forced", "responded"; and in Indonesian
   "menyebabkan", "mengakibatkan", "karena", "akibat", "hal ini membuat", "memaksa",
   "sehingga", "merespons", "berdampak". The interpretation may suggest a link, but must be
   hedged ("may", "might", "could" / "mungkin", "bisa jadi").
6. Describe what the data shows, not what anyone decided: no "adjusted their approach",
   "tactical shift", "chose to", "strategy". Never claim intentions, emotions, or injuries.
7. Number format: copy values exactly as given. English uses a decimal point (2.2);
   Indonesian uses a decimal comma (2,2).
8. Units: rates (unit per_min) always get "per minute" / "per menit". Event totals are
   written as a number plus what was counted, e.g. "11 high presses" / "11 kali pressing
   tinggi", "21 passes" / "21 umpan" - never the word "count". Percentages get "%".

Audiences:
- casual: plain language, no jargon, explain why it matters; summary at most 2 sentences.
- analyst: tactical terms, explicit time windows and before/after comparisons; summary at most
  4 sentences.

Languages:
- en: natural English.
- id: natural Bahasa Indonesia as used by Indonesian football commentators (for example
  "pressing tinggi", "kehilangan bola", "akurasi umpan"). Keep team names unchanged. The fact
  sheet labels are in English: do not copy English words like "baseline", "recent",
  "build-up", or "turnover"; say "5 menit terakhir", "15 menit sebelumnya", "membangun
  serangan", "kehilangan bola". Use normal sentence case for headlines.
"""

JSON_SHAPE = (
    '{"headline": str, "summary": str, "event_ids": [str], '
    '"metric_claims": [{"fact_id": str, "value": number}], "interpretation": str, '
    '"confidence": "moderate" | "strong", "is_hypothetical": false}'
)


class StorytellerError(Exception):
    """The model could not produce a usable narrative (API error, timeout, bad JSON)."""


class Storyteller(Protocol):
    model_name: str

    async def write(
        self, facts: InsightFacts, audience: Audience, language: Language,
        feedback: list[str] | None = None,
    ) -> Narrative: ...


def build_prompt(
    facts: InsightFacts, audience: Audience, language: Language,
    feedback: list[str] | None = None, json_shape: bool = False,
) -> str:
    sheet = facts.model_dump(mode="json")
    parts = [
        f"Audience: {audience}. Language: {language}.",
        "Fact sheet (the only source you may use):",
        json.dumps(sheet, ensure_ascii=False, indent=1),
    ]
    if feedback:
        parts.append("Your previous answer was rejected by the fact checker for these reasons. "
                     "Fix all of them:\n- " + "\n- ".join(feedback))
    if json_shape:
        parts.append(f"Reply with ONLY a JSON object of this shape, no code fences:\n{JSON_SHAPE}")
    return "\n\n".join(parts)


def parse_json_narrative(text: str) -> Narrative:
    """Parse a narrative from model text, tolerating ```json fences."""
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
    return Narrative.model_validate_json(cleaned)


class AgentStoryteller:
    def __init__(self, client, model_name: str, use_schema: bool = True, timeout_s: float = TIMEOUT_S):
        self.model_name = model_name
        self.use_schema = use_schema
        self.timeout_s = timeout_s
        self.agent = Agent(client=client, name="storyteller", instructions=INSTRUCTIONS)

    async def write(self, facts, audience, language, feedback=None) -> Narrative:
        prompt = build_prompt(facts, audience, language, feedback, json_shape=not self.use_schema)
        options: dict = {"temperature": 0.4, "max_tokens": MAX_OUTPUT_TOKENS}
        if self.use_schema:
            options["response_format"] = Narrative
        try:
            response = await asyncio.wait_for(self.agent.run(prompt, options=options), self.timeout_s)
            if self.use_schema:
                narrative = response.value
                if narrative is None:
                    raise StorytellerError("empty structured response")
                return narrative
            return parse_json_narrative(response.text)
        except StorytellerError:
            raise
        except asyncio.TimeoutError as error:
            raise StorytellerError(f"timed out after {self.timeout_s:g}s") from error
        except (ValidationError, ValueError) as error:
            raise StorytellerError(f"unparseable response: {str(error)[:200]}") from error
        except Exception as error:  # API errors (rate limit, bad request, network)
            raise StorytellerError(f"{type(error).__name__}: {str(error)[:200]}") from error


def storyteller_from_env(timeout_s: float | None = None) -> AgentStoryteller | None:
    """Gemini via Agent Framework, or None when no key is configured (AI disabled)."""
    key, model = setting("GEMINI_API_KEY"), setting("GEMINI_MODEL")
    if not key or not model:
        return None
    from agent_framework.openai import OpenAIChatCompletionClient
    from openai import AsyncOpenAI

    timeout_s = timeout_s or float(setting("STORYTELLER_TIMEOUT_S", str(TIMEOUT_S)))
    model = model.removeprefix("models/")
    # max_retries=0: the SDK otherwise silently waits and retries on rate limits (429), which
    # surfaced as a timeout. Our pipeline already retries once and falls back.
    sdk = AsyncOpenAI(
        api_key=key, base_url=setting("GEMINI_BASE_URL", DEFAULT_BASE_URL),
        max_retries=0, timeout=timeout_s,
    )
    client = OpenAIChatCompletionClient(model=model, async_client=sdk)
    use_schema = (setting("STORYTELLER_USE_SCHEMA", "true") or "true").lower() == "true"
    return AgentStoryteller(client, model_name=model, use_schema=use_schema, timeout_s=timeout_s)
