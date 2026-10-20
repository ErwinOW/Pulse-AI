"""Analyst agent: answers a fan's question about one finished match by calling PULSE's tools.

Pipeline per question: the agent looks facts up (tools in analyst_tools.py) and answers ->
deterministic answer checker -> one retry in the same conversation with the checker's feedback ->
otherwise an honest fallback that shows the numbers it found. The agent never sees data it did
not look up, and the checker only accepts numbers from those lookups.
"""

import asyncio
from datetime import datetime, timezone
from typing import Literal, Protocol

from agent_framework import Agent
from pydantic import BaseModel

from app.narrative.schema import Audience, Language
from app.narrative.storyteller import chat_client_from_env

from .analyst_tools import LedgerFact, MatchTools
from .answer_checker import DECLINE, MAX_CHARS, MAX_SENTENCES, check_answer

PROMPT_VERSION = "q1"
MAX_QUESTION_CHARS = 200
MAX_ROUNDS = 4  # model round trips per attempt (tool rounds + the answer)
MAX_TOOL_CALLS = 6
ATTEMPT_TIMEOUT_S = 45.0
FALLBACK_FACTS = 6

INSTRUCTIONS = f"""You are PULSE's analyst for one finished football match (synthetic data).
Answer the user's question about this match using only facts from your tools.

- Always call the tools you need before answering.
- At most {MAX_SENTENCES} sentences and {MAX_CHARS} characters, plain text, no lists or markdown.
- Every number you write must appear in a tool result (minutes and the score are fine). Do not
  calculate new numbers: no differences, totals, averages or percentages of your own.
- Describe what the data shows. Only suggest a cause if you hedge it ("may have", "suggests").
- Never claim what a team or player decided, intended or planned; the data cannot show it.
- No hypotheticals ("would have", "what if").
- Read who did what carefully: the team that lost the ball is not the team that won it.
- If the tools do not contain the answer, say the data does not show it.
- If the question is not about this match (other matches, real clubs, betting, anything else),
  answer exactly: "{DECLINE['en']}" (in Indonesian: "{DECLINE['id']}").

Audience: "casual" = a fan, lively and simple, at most 2 numbers; "analyst" = precise and tactical.
Language: "en" = English with a decimal point (6.6); "id" = Bahasa Indonesia with a decimal comma
(6,6), no English words, team and player names unchanged."""

FALLBACK_TEXT = {
    "en": ("I couldn't give an answer that passed the fact check.", "Here is what I found in the data:"),
    "id": ("Saya tidak bisa memberi jawaban yang lolos cek fakta.", "Ini data yang saya temukan (dalam bahasa Inggris):"),
}


class AnswerResult(BaseModel):
    question: str
    answer: str
    source: Literal["ai", "declined", "fallback"]
    fallback_reason: str | None
    looked_at: list[str]  # tool calls, e.g. "team_stats 45'-90'"
    data_found: list[LedgerFact]  # shown with a fallback
    attempts: int
    rejected: list[list[str]]  # checker problems per rejected attempt
    model: str | None
    prompt_version: str
    generated_at: str


class Conversation(Protocol):
    async def send(self, text: str) -> str: ...


class Analyst(Protocol):
    model_name: str

    def open(self, tools: MatchTools, middleware: list) -> Conversation: ...


class _AgentConversation:
    def __init__(self, agent: Agent, timeout_s: float):
        self.agent, self.timeout_s = agent, timeout_s
        self.session = agent.create_session()  # the retry sees the earlier tool results

    async def send(self, text: str) -> str:
        response = await asyncio.wait_for(self.agent.run(text, session=self.session), self.timeout_s)
        return response.text or ""


class AgentAnalyst:
    """Microsoft Agent Framework agent over Gemini, with PULSE's tools."""

    def __init__(self, timeout_s: float = 20.0):
        config = chat_client_from_env(timeout_s)
        if config is None:
            raise RuntimeError("AI is not configured")
        self.client, self.model_name, _, _ = config
        self.client.function_invocation_configuration["max_iterations"] = MAX_ROUNDS
        self.client.function_invocation_configuration["max_function_calls"] = MAX_TOOL_CALLS

    def open(self, tools: MatchTools, middleware: list) -> Conversation:
        agent = Agent(client=self.client, name="analyst", instructions=INSTRUCTIONS,
                      tools=tools.agent_tools(), middleware=middleware)
        return _AgentConversation(agent, ATTEMPT_TIMEOUT_S)


def analyst_from_env() -> AgentAnalyst | None:
    try:
        return AgentAnalyst()
    except RuntimeError:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_prompt(question: str, audience: Audience, language: Language) -> str:
    return f"Audience: {audience}. Language: {language}.\nQuestion: {question}"


def feedback_prompt(problems: list[str], language: Language) -> str:
    return ("Your answer did not pass PULSE's fact check:\n- " + "\n- ".join(problems)
            + f"\nWrite a corrected answer (language: {language}). Look facts up again if you need to.")


def fallback_answer(question: str, tools: MatchTools, language: Language, reason: str, attempts: int,
                    rejected: list[list[str]], model: str | None) -> AnswerResult:
    sorry, found = FALLBACK_TEXT[language]
    data = tools.ledger[:FALLBACK_FACTS]
    return AnswerResult(
        question=question, answer=f"{sorry} {found}" if data else sorry, source="fallback",
        fallback_reason=reason, looked_at=list(tools.calls), data_found=data, attempts=attempts,
        rejected=rejected, model=model, prompt_version=PROMPT_VERSION, generated_at=_now(),
    )


async def answer_question(question: str, tools: MatchTools, audience: Audience, language: Language,
                          analyst: Analyst, middleware: list | None = None) -> AnswerResult:
    model = analyst.model_name
    conversation = analyst.open(tools, middleware or [])
    prompt = build_prompt(question, audience, language)
    rejected: list[list[str]] = []
    for attempt in (1, 2):
        try:
            text = (await conversation.send(prompt)).strip()
        except Exception as error:  # API errors, timeouts, the daily cap
            return fallback_answer(question, tools, language, f"ai_error: {type(error).__name__}", attempt,
                                   rejected, model)
        result = check_answer(text, tools, language)
        if result.ok:
            return AnswerResult(
                question=question, answer=text, source="declined" if text == DECLINE[language] else "ai",
                fallback_reason=None, looked_at=list(tools.calls), data_found=[], attempts=attempt,
                rejected=rejected, model=model, prompt_version=PROMPT_VERSION, generated_at=_now(),
            )
        rejected.append(result.problems)
        prompt = feedback_prompt(result.problems, language)
    return fallback_answer(question, tools, language, "validation_failed", 2, rejected, model)
