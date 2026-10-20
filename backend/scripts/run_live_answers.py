"""Generate answers to the suggested questions and save the ones a person approves.

Run from the backend folder (venv active):
    python -m scripts.run_live_answers --match demo-high-press --review
    python -m scripts.run_live_answers --match demo-high-press --language id --audience casual --review

Without --review it only prints (nothing saved). With --review it asks y/n for each checked AI
answer and saves approved ones to data/narratives/answers.json right away. Answers already saved
are skipped unless --fresh. Each answer costs about 2-8 model requests.
"""

import argparse
import asyncio
import sys

from app.api import service
from app.report.analyst import analyst_from_env, answer_question
from app.report.analyst_tools import MatchTools
from app.report.suggested import SUGGESTED, AnswerCache


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--match", choices=service.list_match_ids())
    parser.add_argument("--language", choices=["en", "id"])
    parser.add_argument("--audience", choices=["casual", "analyst"])
    parser.add_argument("--review", action="store_true", help="ask y/n per answer and save approved ones")
    parser.add_argument("--fresh", action="store_true", help="regenerate answers that are already saved")
    args = parser.parse_args()
    analyst = analyst_from_env()
    if analyst is None:
        sys.exit("Fill GEMINI_API_KEY and GEMINI_MODEL in backend/.env")

    cache = AnswerCache()
    saved = skipped = 0
    for match_id in [args.match] if args.match else service.list_match_ids():
        for language in [args.language] if args.language else ["en", "id"]:
            for audience in [args.audience] if args.audience else ["casual", "analyst"]:
                for question in SUGGESTED[language]:
                    if not args.fresh and cache.get(match_id, question, audience, language):
                        skipped += 1
                        continue
                    result = await answer_question(question, MatchTools(match_id), audience, language, analyst)
                    print(f"\n[{match_id} | {audience} | {language}] Q: {question}")
                    print(f"looked at: {result.looked_at or 'nothing'}")
                    for i, problems in enumerate(result.rejected, 1):
                        print(f"rejected attempt {i}: {problems}")
                    print(f"[{result.source}{', ' + result.fallback_reason if result.fallback_reason else ''}] "
                          f"{result.answer}")
                    if not args.review or result.source != "ai":
                        continue
                    if input("Approve this answer? [y/N] ").strip().lower() == "y":
                        cache.put(match_id, audience, language, result)
                        cache.save()
                        saved += 1
    print(f"\nsaved {saved} new answers, skipped {skipped} already saved; total {len(cache.entries)} in answers.json")


if __name__ == "__main__":
    asyncio.run(main())
