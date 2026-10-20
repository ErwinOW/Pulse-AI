"""Tool-calling check: can the Gemini model call a PULSE tool through Microsoft Agent Framework?

Run from the backend folder (venv active):
    python -m scripts.check_tools

Two questions (2-4 model requests). The agent gets one tool that returns the demo match's goals from
the full-time fact sheet. It passes if the tool was called and the answer uses the tool's numbers.
The API key is read from backend/.env and never printed.
"""

import asyncio
import json
import sys
import time

from agent_framework import Agent, tool

from app.narrative.storyteller import chat_client_from_env
from app.report.facts import build_report_facts

MATCH = "demo-high-press"
calls: list[str] = []


@tool
def match_goals() -> str:
    """The goals of the match being discussed: minute, scorer, score after, how the ball was won,
    and the seconds and passes of the move before each goal."""
    calls.append("match_goals")
    facts = build_report_facts(MATCH)
    goals = []
    for g in facts.goals:
        goal = g.model_dump(exclude={"fact_prefix"})
        for key in ("seconds", "passes"):
            if f := facts.fact(f"{g.fact_prefix}.{key}"):
                goal[key] = f.value
        goals.append(goal)
    return json.dumps(goals)


QUESTIONS = [
    "How did the equaliser happen, and how many seconds did it take?",
    "How many passes were in the move before the first goal?",
]


async def main() -> None:
    configured = chat_client_from_env(timeout_s=30)
    if configured is None:
        sys.exit("Fill GEMINI_API_KEY and GEMINI_MODEL in backend/.env")
    client, model, _, timeout_s = configured
    agent = Agent(
        client=client, name="analyst", tools=[match_goals],
        instructions="You answer questions about one football match. Use the tools for every fact; "
                     "never guess numbers. Answer in at most 2 sentences.",
    )
    print(f"model: {model}")
    for question in QUESTIONS:
        calls.clear()
        started = time.perf_counter()
        try:
            answer = await asyncio.wait_for(agent.run(question), timeout_s)
        except Exception as e:  # report and keep going: this is a check, not the app
            print(f"\nQ: {question}\nERROR: {type(e).__name__}: {e}")
            continue
        print(f"\nQ: {question}")
        print(f"tool calls: {calls or 'none'}  ({time.perf_counter() - started:.1f}s)")
        print(f"A: {answer}")


if __name__ == "__main__":
    asyncio.run(main())
