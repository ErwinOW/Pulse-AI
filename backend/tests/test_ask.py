"""Ask the analyst: answer pipeline, model-call cap and the endpoint (no network)."""

import asyncio

import pytest
from agent_framework import Agent
from fastapi.testclient import TestClient

from app.main import app
from app.narrative.gemini_client import GeminiChatClient
from app.report.analyst import answer_question
from app.report.analyst_tools import MatchTools
from app.report.answer_checker import DECLINE
from app.report.ask_service import AskService, DailyCapReached, get_analyst, get_ask_service
from app.report.facts import end_time
from app.report.suggested import SUGGESTED, AnswerCache
from tests.test_gemini_client import FakeSDK, match_goals

DEMO = "demo-high-press"
GOOD = "Eastvale Athletic equalised in the 64th minute, 8 seconds after winning the ball."
BAD = "Eastvale Athletic equalised 12 seconds after winning the ball."


class FakeConversation:
    def __init__(self, tools: MatchTools, replies: list):
        self.tools, self.replies, self.prompts = tools, list(replies), []

    async def send(self, text: str) -> str:
        self.prompts.append(text)
        self.tools.goals()  # what a real agent would look up
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class FakeAnalyst:
    model_name = "fake"

    def __init__(self, *replies):
        self.replies = replies
        self.conversation: FakeConversation | None = None

    def open(self, tools, middleware):
        self.conversation = FakeConversation(tools, self.replies)
        return self.conversation


def ask(analyst, question="How did the equaliser happen?", language="en"):
    return asyncio.run(answer_question(question, MatchTools(DEMO), "casual", language, analyst))


def test_checked_answer_is_returned_with_what_was_looked_at():
    result = ask(FakeAnalyst(GOOD))

    assert result.source == "ai" and result.answer == GOOD and result.attempts == 1
    assert result.looked_at == ["goals"]


def test_rejected_answer_is_retried_with_the_checker_feedback():
    analyst = FakeAnalyst(BAD, GOOD)
    result = ask(analyst)

    assert result.source == "ai" and result.attempts == 2
    assert "number 12" in analyst.conversation.prompts[1] and "number 12" in result.rejected[0][0]


def test_two_rejections_give_an_honest_fallback_with_the_data_found():
    result = ask(FakeAnalyst(BAD, BAD))

    assert result.source == "fallback" and result.fallback_reason == "validation_failed"
    assert result.answer.startswith("I couldn't give an answer that passed the fact check")
    assert result.data_found and len(result.rejected) == 2


def test_api_errors_fall_back():
    result = ask(FakeAnalyst(TimeoutError()))

    assert result.source == "fallback" and result.fallback_reason == "ai_error: TimeoutError"


def test_off_topic_question_is_declined():
    result = ask(FakeAnalyst(DECLINE["id"]), "Siapa juara liga tahun lalu?", "id")

    assert result.source == "declined"


def test_every_model_call_counts_towards_the_daily_cap():
    service = AskService(cap=60)
    sdk = FakeSDK()  # one tool round, then the answer: 2 model calls
    agent = Agent(client=GeminiChatClient(model="fake", async_client=sdk), tools=[match_goals],
                  middleware=[service._count_model_calls()])
    asyncio.run(agent.run("How many goals?"))

    assert service.calls_left() == 58


def test_cap_stops_further_model_calls():
    service = AskService(cap=1)
    agent = Agent(client=GeminiChatClient(model="fake", async_client=FakeSDK()), tools=[match_goals],
                  middleware=[service._count_model_calls()])

    with pytest.raises(Exception) as error:
        asyncio.run(agent.run("How many goals?"))
    assert isinstance(error.value, DailyCapReached) or "DailyCapReached" in repr(error.value)
    assert service.calls_left() == 0


# --- endpoint --------------------------------------------------------------------------------

client = TestClient(app)


@pytest.fixture
def asks(tmp_path):
    service = AskService(answers=AnswerCache(tmp_path / "answers.json"))
    app.dependency_overrides[get_ask_service] = lambda: service
    yield service
    app.dependency_overrides.clear()


def post(question="How did the equaliser happen?", t=None, match_id=DEMO):
    t = end_time(DEMO) if t is None else t
    return client.post(f"/api/matches/{match_id}/ask", json={"question": question, "t": t})


def test_ask_endpoint_answers_at_full_time(asks):
    app.dependency_overrides[get_analyst] = lambda: FakeAnalyst(GOOD)
    body = post().json()

    assert body["answer"]["source"] == "ai" and body["answer"]["looked_at"] == ["goals"]
    assert body["model_calls_left_today"] == 60  # the fake makes no model calls


def test_ask_endpoint_guards(asks):
    app.dependency_overrides[get_analyst] = lambda: FakeAnalyst(GOOD)
    assert post(t=end_time(DEMO) - 600).status_code == 409
    assert post(question="x" * 201).status_code == 422
    assert post(question="").status_code == 422
    assert post(match_id="nope").status_code == 404
    asks.busy = True
    assert post().status_code == 429


def test_ask_endpoint_without_ai_or_quota(asks):
    app.dependency_overrides[get_analyst] = lambda: None
    assert post().status_code == 503
    app.dependency_overrides[get_analyst] = lambda: FakeAnalyst(GOOD)
    asks.cap = 0
    assert post().status_code == 429


def test_suggested_questions_are_listed_per_language():
    for language in ("en", "id"):
        assert client.get("/api/suggested-questions", params={"language": language}).json() == SUGGESTED[language]


def test_approved_answer_is_served_without_ai_or_quota(asks):
    question = SUGGESTED["en"][0]
    approved = ask(FakeAnalyst(GOOD), question)
    asks.answers.put(DEMO, "casual", "en", approved)
    app.dependency_overrides[get_analyst] = lambda: None  # no AI at all
    asks.cap = 0

    body = post(question=f"  {question.upper()} ").json()  # same question, different spacing/case
    assert body["cached"] is True and body["answer"]["answer"] == GOOD


def test_only_checked_ai_answers_can_be_saved(tmp_path):
    with pytest.raises(ValueError):
        AnswerCache(tmp_path / "a.json").put(DEMO, "casual", "en", ask(FakeAnalyst(BAD, BAD)))


def test_committed_answers_are_approved_ai_answers_for_suggested_questions():
    questions = {q for qs in SUGGESTED.values() for q in qs}
    for entry in AnswerCache().entries.values():
        assert entry["source"] == "ai" and entry["question"] in questions
