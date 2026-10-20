"""Generate the full-time reports with the real Commentator agent (Gemini via Agent Framework).

Run from the backend folder (venv active):
    python -m scripts.run_live_reports            # print only
    python -m scripts.run_live_reports --save     # also store validated AI reports
    python -m scripts.run_live_reports --save --fresh   # empty the report cache first

At most 16 requests (2 matches x 4 versions x up to 2 attempts), spaced out for free-tier limits.
Already-cached versions are skipped.
"""

import asyncio
import sys
import time

from app.report.service import report_facts
from app.report.writer import PROMPT_VERSION, commentator_from_env, generate_report, report_cache

MATCHES = ("demo-high-press", "balanced")
PAUSE_S = 4.0


async def main() -> None:
    commentator = commentator_from_env(timeout_s=60.0)
    if commentator is None:
        print("AI disabled: GEMINI_API_KEY / GEMINI_MODEL missing in backend/.env")
        return
    save = "--save" in sys.argv
    store = report_cache() if save else None
    if store is not None:
        removed = store.prune(PROMPT_VERSION)
        if "--fresh" in sys.argv:
            removed += len(store.entries)
            store.entries.clear()
        print(f"Report cache: removed {removed} old entries")

    for match_id in MATCHES:
        facts = report_facts(match_id)
        for audience in ("casual", "analyst"):
            for language in ("en", "id"):
                label = f"{match_id} / {audience} / {language}"
                if store is not None and store.get(facts, audience, language, commentator.model_name, PROMPT_VERSION):
                    print(f"\n=== {label}: already cached, skipped")
                    continue
                started = time.perf_counter()
                result = await generate_report(facts, audience, language, commentator)
                print(f"\n=== {label}: source={result.source}, attempts={result.attempts}, "
                      f"{time.perf_counter() - started:.1f}s"
                      + (f", fallback_reason={result.fallback_reason}" if result.fallback_reason else ""))
                for i, problems in enumerate(result.rejected_attempts, 1):
                    print(f"  rejected attempt {i}: " + " | ".join(problems))
                r = result.report
                print(f"HEADLINE: {r.headline}")
                for moment in r.moments:
                    print(f"  - {moment}")
                print(f"CLOSING:  {r.closing}")
                if store is not None:
                    print("CACHED:   yes" if store.put(facts, result) else "CACHED:   no (fallback)")
                await asyncio.sleep(PAUSE_S)

    if store is not None:
        store.save()
        print(f"\nReport cache saved: {store.path} ({len(store.entries)} entries)")


if __name__ == "__main__":
    asyncio.run(main())
