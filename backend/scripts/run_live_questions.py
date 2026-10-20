"""Ask the real Analyst agent a few questions about the demo match and print what happened.

Run from the backend folder (venv active):
    python -m scripts.run_live_questions
    python -m scripts.run_live_questions --language id

Each question costs 2-8 model requests (tool rounds, answer, maybe one retry). Nothing is saved.
"""

import argparse
import asyncio
import sys

from app.report.analyst import analyst_from_env, answer_question
from app.report.analyst_tools import MatchTools

MATCH = "demo-high-press"
QUESTIONS = {
    "en": [
        "How did Eastvale Athletic equalise?",
        "Who pressed more in the second half?",
        "Was the first goal a quick counter-attack?",
        "Who will win the Champions League?",
    ],
    "id": [
        "Bagaimana Eastvale Athletic menyamakan skor?",
        "Tim mana yang lebih banyak melakukan pressing di babak kedua?",
    ],
}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", choices=["en", "id"], default="en")
    parser.add_argument("--audience", choices=["casual", "analyst"], default="casual")
    args = parser.parse_args()
    analyst = analyst_from_env()
    if analyst is None:
        sys.exit("Fill GEMINI_API_KEY and GEMINI_MODEL in backend/.env")
    print(f"model: {analyst.model_name}, audience: {args.audience}, language: {args.language}")
    for question in QUESTIONS[args.language]:
        result = await answer_question(question, MatchTools(MATCH), args.audience, args.language, analyst)
        print(f"\nQ: {question}")
        print(f"looked at: {result.looked_at or 'nothing'}")
        for i, problems in enumerate(result.rejected, 1):
            print(f"rejected attempt {i}: {problems}")
        print(f"[{result.source}{', ' + result.fallback_reason if result.fallback_reason else ''}] {result.answer}")
        for fact in result.data_found:
            print(f"   - {fact.label}: {fact.value}")


if __name__ == "__main__":
    asyncio.run(main())
