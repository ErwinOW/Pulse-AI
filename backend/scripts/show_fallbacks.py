"""Print the four fallback narratives for the demo alert, with validation results.

Run from the backend folder (venv active):
    python -m scripts.show_fallbacks
"""

from app.detection import detect_alerts
from app.narrative import facts_from_alert, fallback_narrative, validate
from app.simulator import DEMO_HIGH_PRESS, generate


def main() -> None:
    match, _ = generate(DEMO_HIGH_PRESS)
    (alert,) = detect_alerts(match.events, (match.home.team_id, match.away.team_id), 6000)
    facts = facts_from_alert(match, alert)
    print(f"Alert {facts.insight_id}: onset {facts.onset_minute}', detected {facts.detected_minute}', "
          f"confidence {facts.confidence}, {len(facts.evidence_event_ids)} evidence events")

    for audience in ("casual", "analyst"):
        for language in ("en", "id"):
            narrative = fallback_narrative(facts, audience, language)
            result = validate(narrative, facts)
            print(f"\n--- {audience} / {language} (valid: {result.ok}) ---")
            print(f"HEADLINE: {narrative.headline}")
            print(f"SUMMARY:  {narrative.summary}")
            print(f"WHY:      {narrative.interpretation}")


if __name__ == "__main__":
    main()
