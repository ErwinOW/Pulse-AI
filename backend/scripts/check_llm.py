"""One request through Microsoft Agent Framework to Gemini (connection check).

Run from the backend folder (venv active):
    python -m scripts.check_llm

Uses the chat-completions client because Gemini exposes an OpenAI-compatible
chat-completions endpoint. The API key is read from backend/.env and never printed.
"""

import asyncio
import sys
import time

from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient

from app.config import setting

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


async def main() -> None:
    key = setting("GEMINI_API_KEY")
    model = setting("GEMINI_MODEL")
    if not key or not model:
        sys.exit("Fill GEMINI_API_KEY and GEMINI_MODEL in backend/.env")
    # The model list returns "models/<id>"; the chat endpoint expects the bare id.
    model = model.removeprefix("models/")

    client = OpenAIChatCompletionClient(
        model=model, api_key=key, base_url=setting("GEMINI_BASE_URL", DEFAULT_BASE_URL)
    )
    agent = Agent(client=client, instructions="You are a concise football commentator.")

    started = time.perf_counter()
    result = await agent.run(
        "In one short sentence, say that a team increased its pressing. "
        "Then give the same sentence in Indonesian on a new line."
    )
    elapsed = time.perf_counter() - started

    print(f"model: {model}")
    print(f"latency: {elapsed:.2f}s")
    print("response:")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
