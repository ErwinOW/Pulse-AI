"""Generate all synthetic match fixtures into <repo>/data/matches/.

Run from the backend folder (venv active):
    python -m scripts.generate_matches
"""

import json
from pathlib import Path

from app.simulator import SCENARIOS, generate

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "matches"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for match_id, scenario in SCENARIOS.items():
        match, ground_truth = generate(scenario)

        match_path = OUTPUT_DIR / f"{match_id}.json"
        truth_path = OUTPUT_DIR / f"{match_id}.ground_truth.json"
        match_path.write_text(match.model_dump_json(indent=2) + "\n", encoding="utf-8")
        truth_path.write_text(json.dumps(ground_truth, indent=2) + "\n", encoding="utf-8")

        goals = ", ".join(
            f"{g['team_id']} {g['timestamp_seconds'] / 60:.0f}'" for g in ground_truth["goals"]
        )
        print(f"{match_id}: {len(match.events)} events | goals: {goals} -> {match_path}")


if __name__ == "__main__":
    main()
