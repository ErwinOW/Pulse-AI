"""GeminiChatClient: Gemini's thought signature on a tool call must be sent back with that call.

Runs a full Agent Framework tool loop against a fake OpenAI SDK (no network). If an
agent-framework-openai update changes the private methods the adapter overrides, these fail.
"""

import asyncio

from agent_framework import Agent, tool
from openai.types.chat import ChatCompletion

from app.narrative.gemini_client import GeminiChatClient

SIGNATURE = {"google": {"thought_signature": "sig-123"}}


def completion(message: dict, finish_reason: str) -> ChatCompletion:
    return ChatCompletion.model_validate({
        "id": "c1", "object": "chat.completion", "created": 0, "model": "fake",
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": {"role": "assistant", **message}}],
    })


class FakeSDK:
    """Stands in for AsyncOpenAI: first a tool call (with extra_content), then a text answer."""

    base_url = "https://fake.invalid/"

    def __init__(self):
        self.requests: list[dict] = []
        self.chat = self
        self.completions = self

    async def create(self, **request):
        self.requests.append(request)
        if len(self.requests) == 1:
            return completion({"content": None, "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "match_goals", "arguments": "{}"},
                "extra_content": SIGNATURE,
            }]}, "tool_calls")
        return completion({"content": "Two goals."}, "stop")


@tool
def match_goals() -> str:
    """The goals of the match."""
    return '[{"minute": 35}, {"minute": 64}]'


def run_agent(client_class) -> FakeSDK:
    sdk = FakeSDK()
    agent = Agent(client=client_class(model="fake", async_client=sdk), tools=[match_goals])
    answer = asyncio.run(agent.run("How many goals?"))
    assert answer.text == "Two goals."
    return sdk


def sent_tool_calls(sdk: FakeSDK) -> list[dict]:
    return [call for m in sdk.requests[1]["messages"] for call in m.get("tool_calls") or []]


def test_thought_signature_is_sent_back_with_the_tool_call():
    sdk = run_agent(GeminiChatClient)

    calls = sent_tool_calls(sdk)
    assert len(sdk.requests) == 2 and len(calls) == 1
    assert calls[0]["id"] == "call_1" and calls[0]["extra_content"] == SIGNATURE


def test_tool_calls_without_extra_content_are_unchanged():
    sdk = FakeSDK()
    client = GeminiChatClient(model="fake", async_client=sdk)
    choice = completion({"content": None, "tool_calls": [{
        "id": "call_2", "type": "function", "function": {"name": "match_goals", "arguments": "{}"},
    }]}, "tool_calls").choices[0]

    [content] = client._parse_tool_calls_from_openai(choice)
    assert "extra_content" not in client._prepare_content_for_openai(content)
