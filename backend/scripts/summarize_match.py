"""Print per-phase statistics for a generated scenario (sanity check, not a test).

Run from the backend folder (venv active):
    python -m scripts.summarize_match               # demo match
    python -m scripts.summarize_match balanced
"""

import sys

from app.simulator import SCENARIOS, generate
from app.stats import compute_window, score

MATCH_END_S = 5400.0


def fmt(value, suffix=""):
    return "n/a" if value is None else f"{value:g}{suffix}"


def main(match_id: str = "demo-high-press") -> None:
    scenario = SCENARIOS[match_id]
    match, _ = generate(scenario)
    teams = (match.home.team_id, match.away.team_id)

    starts = [p.start_s for p in scenario.phases]
    ends = starts[1:] + [MATCH_END_S]
    print(f"{match_id} (seed {scenario.seed}) - final score {score(match.events, teams, 1e9)}")
    print(
        f"{'phase':<22}{'mins':>7}  {'team':<5}{'poss%':>7}{'pass%':>7}{'TO':>5}{'TO@P':>6}"
        f"{'hiP/min':>9}{'shots':>7}{'box':>5}{'mom':>6}"
    )
    for phase, start, end in zip(scenario.phases, starts, ends):
        window = compute_window(match.events, teams, start, end)
        for i, team_id in enumerate(teams):
            s = window.teams[team_id]
            label = f"{phase.label:<22}{f'{start / 60:.0f}-{end / 60:.0f}':>7}" if i == 0 else " " * 29
            print(
                f"{label}  {team_id:<5}{fmt(s.possession_share.value):>7}{fmt(s.pass_completion.value):>7}"
                f"{fmt(s.turnovers.value):>5}{fmt(s.turnovers_under_pressure.value):>6}"
                f"{fmt(s.high_pressures_per_min.value):>9}{fmt(s.shots.value):>7}"
                f"{fmt(s.box_entries.value):>5}{fmt(s.momentum.value):>6}"
            )
    print("TO = turnovers, TO@P = under pressure, hiP/min = high pressures per minute, mom = momentum")


if __name__ == "__main__":
    main(*sys.argv[1:])
