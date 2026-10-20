"""Run the real narrative pipeline (Gemini via Agent Framework) for the demo alert.

Run from the backend folder (venv active):
    python -m scripts.run_live_insights

    python -m scripts.run_live_insights --save   # also store validated AI texts in the cache
    python -m scripts.run_live_insights --save --fresh   # empty the cache first

Makes at most 8 API requests (4 versions x up to 2 attempts), spaced out to
respect free-tier per-minute limits. Prints what was shown, who wrote it, and
every validator rejection.
"""

import asyncio
import os
import sys
import time

from app.api.insights import detection_facts
from app.narrative.cache import InsightCache
from app.narrative.pipeline import generate_insight
from app.narrative.storyteller import PROMPT_VERSION, storyteller_from_env

PAUSE_S = 4.0
OFFLINE_TIMEOUT_S = 45.0  # nobody is waiting during cache generation


async def main() -> None:
    storyteller = storyteller_from_env(timeout_s=OFFLINE_TIMEOUT_S)
    if storyteller is None:
        print("AI disabled: GEMINI_API_KEY / GEMINI_MODEL missing in backend/.env")
        return
    mode = "schema" if storyteller.use_schema else "prompt-JSON"
    print(f"Model: {storyteller.model_name} | output mode: {mode} "
          f"(set STORYTELLER_USE_SCHEMA=false to switch)")

    # Same detection-time facts the API serves (committed fixture), so cache keys match.
    facts = detection_facts("demo-high-press", "pressing_increase-EAS-1")
    save = "--save" in sys.argv
    store = InsightCache() if save else None
    if store is not None:
        removed = store.prune(PROMPT_VERSION)
        if "--fresh" in sys.argv:
            removed += len(store.entries)
            store.entries.clear()
        print(f"Cache: removed {removed} old entries")

    for audience in ("casual", "analyst"):
        for language in ("en", "id"):
            if store is not None and store.get(facts, audience, language,
                                               storyteller.model_name, PROMPT_VERSION):
                print(f"\n=== {audience} / {language}: already cached, skipped (no request made)")
                continue
            started = time.perf_counter()
            insight = await generate_insight(facts, audience, language, storyteller)
            elapsed = time.perf_counter() - started
            n = insight.narrative
            print(f"\n=== {audience} / {language}: source={insight.source}, attempts={insight.attempts}, "
                  f"{elapsed:.1f}s"
                  + (f", fallback_reason={insight.fallback_reason}" if insight.fallback_reason else ""))
            for i, problems in enumerate(insight.rejected_attempts, 1):
                print(f"  rejected attempt {i}: " + " | ".join(problems))
            print(f"HEADLINE: {n.headline}")
            print(f"SUMMARY:  {n.summary}")
            print(f"WHY:      {n.interpretation}")
            print(f"CITED:    {len(n.event_ids)} events, claims: "
                  + ", ".join(f"{c.fact_id}={c.value:g}" for c in n.metric_claims))
            if store is not None:
                print("CACHED:   yes" if store.put(facts, insight) else "CACHED:   no (fallback)")
            await asyncio.sleep(PAUSE_S)

    if store is not None:
        store.save()
        print(f"\nCache saved: {store.path} ({len(store.entries)} entries)")

    if os.environ.get("STORYTELLER_USE_SCHEMA"):
        print(f"\n(STORYTELLER_USE_SCHEMA was set to {os.environ['STORYTELLER_USE_SCHEMA']!r})")


if __name__ == "__main__":
    asyncio.run(main())
