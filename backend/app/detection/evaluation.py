"""Score detector output against scenario ground truth."""

from dataclasses import dataclass, replace

from app.schema import Match
from app.simulator import Scenario, generate

from .engine import Alert, detect_alerts
from .pressing import DEFAULT_CONFIG, DetectorConfig


@dataclass(frozen=True)
class MatchEvaluation:
    match_id: str
    seed: int
    expected: int  # expected alerts in ground truth
    detected: int  # expected alerts matched by a real alert
    false_alerts: list[Alert]  # alerts not matching any expected alert
    alerts: list[Alert]


def evaluate(match: Match, ground_truth: dict, config: DetectorConfig = DEFAULT_CONFIG) -> MatchEvaluation:
    teams = (match.home.team_id, match.away.team_id)
    until_s = match.events[-1].timestamp_seconds + 1
    alerts = detect_alerts(match.events, teams, until_s, config)

    matched: set[str] = set()
    detected = 0
    for expected in ground_truth["expected_alerts"]:
        hit = next(
            (
                a for a in alerts
                if a.kind == expected["kind"]
                and a.team_id == expected["team_id"]
                and expected["earliest_s"] <= a.first_detected_s <= expected["latest_s"]
                and a.alert_id not in matched
            ),
            None,
        )
        if hit is not None:
            detected += 1
            matched.add(hit.alert_id)

    return MatchEvaluation(
        match_id=match.match_id,
        seed=ground_truth["seed"],
        expected=len(ground_truth["expected_alerts"]),
        detected=detected,
        false_alerts=[a for a in alerts if a.alert_id not in matched],
        alerts=alerts,
    )


def evaluate_seeds(
    scenario: Scenario, seeds: range, config: DetectorConfig = DEFAULT_CONFIG
) -> list[MatchEvaluation]:
    results = []
    for seed in seeds:
        match, truth = generate(replace(scenario, seed=seed))
        results.append(evaluate(match, truth, config))
    return results
