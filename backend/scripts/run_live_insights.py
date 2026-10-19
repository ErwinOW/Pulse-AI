"""Run the real narrative pipeline (Gemini via Agent Framework) for the demo alert.

Run from the backend folder (venv active):
    python -m scripts.run_live_insights

Makes at most 8 API requests (4 versions x up to 2 attempts), spaced out to
respect free-tier per-minute limits. Prints what was shown, who wrote it, and
every validator rejection.
"""

import asyncio
import os

from app.detection import detect_alerts
from app.narrative import facts_from_alert
from app.narrative.pipeline import generate_insight
from app.narrative.storyteller import storyteller_from_env
from app.simulator import DEMO_HIGH_PRESS, generate

PAUSE_S = 4.0


async def main() -> None:
    storyteller = storyteller_from_env()
    if storyteller is None:
        print("AI disabled: GEMINI_API_KEY / GEMINI_MODEL missing in backend/.env")
        return
    mode = "schema" if storyteller.use_schema else "prompt-JSON"
    print(f"Model: {storyteller.model_name} | output mode: {mode} "
          f"(set STORYTELLER_USE_SCHEMA=false to switch)")

    match, _ = generate(DEMO_HIGH_PRESS)
    (alert,) = detect_alerts(match.events, (match.home.team_id, match.away.team_id), 6000)
    facts = facts_from_alert(match, alert)

    for audience in ("casual", "analyst"):
        for language in ("en", "id"):
            insight = await generate_insight(facts, audience, language, storyteller)
            n = insight.narrative
            print(f"\n=== {audience} / {language}: source={insight.source}, attempts={insight.attempts}"
                  + (f", fallback_reason={insight.fallback_reason}" if insight.fallback_reason else ""))
            for i, problems in enumerate(insight.rejected_attempts, 1):
                print(f"  rejected attempt {i}: " + " | ".join(problems))
            print(f"HEADLINE: {n.headline}")
            print(f"SUMMARY:  {n.summary}")
            print(f"WHY:      {n.interpretation}")
            print(f"CITED:    {len(n.event_ids)} events, claims: "
                  + ", ".join(f"{c.fact_id}={c.value:g}" for c in n.metric_claims))
            await asyncio.sleep(PAUSE_S)

    if os.environ.get("STORYTELLER_USE_SCHEMA"):
        print(f"\n(STORYTELLER_USE_SCHEMA was set to {os.environ['STORYTELLER_USE_SCHEMA']!r})")


if __name__ == "__main__":
    asyncio.run(main())
