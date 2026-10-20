"""Serving "Ask the analyst": one question at a time, within a daily cap of model calls.

Every model request (each tool round and each answer) counts towards DAILY_MODEL_CALL_CAP,
counted by an Agent Framework chat middleware, so a public demo link cannot exhaust the free
tier. Insights keep their own cap (app/api/insights.py). Human-approved answers to suggested
questions (app/report/suggested.py) are served first, without a model call.
"""

from datetime import date

from agent_framework import chat_middleware
from pydantic import BaseModel, Field

from app.narrative.schema import Audience, Language

from .analyst import MAX_QUESTION_CHARS, Analyst, AnswerResult, analyst_from_env, answer_question
from .analyst_tools import MatchTools
from .suggested import AnswerCache

DAILY_MODEL_CALL_CAP = 60


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    t: float = Field(ge=0, description="Match clock; questions open at the final whistle")
    audience: Audience = "casual"
    language: Language = "en"


class AskResponse(BaseModel):
    answer: AnswerResult
    cached: bool  # a human-approved saved answer, no model call
    model_calls_left_today: int


class AskError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class DailyCapReached(Exception):
    pass


class AskService:
    def __init__(self, answers: AnswerCache | None = None, cap: int = DAILY_MODEL_CALL_CAP):
        self.answers = answers if answers is not None else AnswerCache()
        self.cap = cap
        self.busy = False
        self._day = date.today()
        self._used = 0

    def calls_left(self) -> int:
        if date.today() != self._day:
            self._day, self._used = date.today(), 0
        return max(0, self.cap - self._used)

    def _count_model_calls(self):
        @chat_middleware
        async def count(context, call_next):
            if self.calls_left() == 0:
                raise DailyCapReached()
            self._used += 1
            await call_next()

        return count

    async def ask(self, match_id: str, request: AskRequest, analyst: Analyst | None) -> AskResponse:
        saved = self.answers.get(match_id, request.question, request.audience, request.language)
        if saved is not None:
            return AskResponse(answer=saved, cached=True, model_calls_left_today=self.calls_left())
        if analyst is None:
            raise AskError(503, "AI is not configured on this server")
        if self.busy:
            raise AskError(429, "another question is being answered; try again in a few seconds")
        if self.calls_left() == 0:
            raise AskError(429, "daily question limit reached; try again tomorrow")

        self.busy = True
        try:
            answer = await answer_question(request.question.strip(), MatchTools(match_id), request.audience,
                                           request.language, analyst, [self._count_model_calls()])
        finally:
            self.busy = False
        return AskResponse(answer=answer, cached=False, model_calls_left_today=self.calls_left())


ask_service = AskService()
_analyst: list[Analyst | None] = []


def get_analyst() -> Analyst | None:
    """FastAPI dependency: the real analyst, built once (None when no key)."""
    if not _analyst:
        _analyst.append(analyst_from_env())
    return _analyst[0]


def get_ask_service() -> AskService:
    return ask_service
