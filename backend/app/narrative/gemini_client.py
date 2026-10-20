"""Agent Framework chat client that keeps Gemini's thought signatures on tool calls.

Gemini 3 models attach `extra_content` ({"google": {"thought_signature": ...}}) to every tool call
on the OpenAI-compatible endpoint and reject the next request (400) unless it is sent back with
that call. The stock OpenAIChatCompletionClient drops unknown fields, so this subclass stores the
field on the function-call content when parsing and adds it back when serialising.

It overrides two private methods of agent-framework-openai (pinned in requirements.lock);
tests/test_gemini_client.py fails loudly if their shape changes.
"""

from typing import Any

from agent_framework import Content
from agent_framework.openai import OpenAIChatCompletionClient

EXTRA_KEY = "gemini_extra_content"


class GeminiChatClient(OpenAIChatCompletionClient):
    def _parse_tool_calls_from_openai(self, choice) -> list[Content]:
        contents = super()._parse_tool_calls_from_openai(choice)
        message = getattr(choice, "message", None) or getattr(choice, "delta", None)
        extras = {
            call.id: extra
            for call in (getattr(message, "tool_calls", None) or [])
            if call.id and (extra := (call.model_extra or {}).get("extra_content"))
        }
        for content in contents:
            if extra := extras.get(content.call_id):
                content.additional_properties = {**(content.additional_properties or {}), EXTRA_KEY: extra}
        return contents

    def _prepare_content_for_openai(self, content: Content) -> dict[str, Any]:
        prepared = super()._prepare_content_for_openai(content)
        if content.type == "function_call" and (extra := (content.additional_properties or {}).get(EXTRA_KEY)):
            prepared["extra_content"] = extra
        return prepared
