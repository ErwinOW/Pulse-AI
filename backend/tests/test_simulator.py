"""Tests for the synthetic match simulator (backend/app/simulator).

These check that the generated data is valid, deterministic, and that the
planted scenario is actually present in the events — without that, later
detector tests would be meaningless.
"""

from dataclasses import replace
from functools import cache

import pytest

from app.schema import Match, PassEvent, ShotEvent, SubstitutionEvent
from app.simulator import BALANCED, DEMO_HIGH_PRESS, generate


@cache
def generated(match_id: str):
    scenario = {"demo-high-press": DEMO_HIGH_PRESS, "balanced": BALANCED}[match_id]
    return generate(scenario)


def per_minute(match: Match, start: float, end: float, event_type: str, team_id: str | None = None):
    count = sum(
        1
        for e in match.events
        if e.event_type == event_type
        and start <= e.timestamp_seconds < end
        and (team_id is None or getattr(e, "team_id", None) == team_id)
    )
    return count / ((end - start) / 60)


def events_per_minute(match: Match, start: float, end: float) -> float:
    count = sum(1 for e in match.events if start <= e.timestamp_seconds < end)
    return count / ((end - start) / 60)


def pass_completion(match: Match, team_id: str, start: float, end: float) -> float:
    passes = [
        e for e in match.events
        if isinstance(e, PassEvent) and e.team_id == team_id and start <= e.timestamp_seconds < end
    ]
    assert passes, "no passes in window"
    return sum(p.outcome == "complete" for p in passes) / len(passes)


# --- Validity and determinism -----------------------------------------------------


@pytest.mark.parametrize("match_id", ["demo-high-press", "balanced"])
def test_generated_match_is_valid_and_realistically_sized(match_id):
    match, _ = generated(match_id)

    assert isinstance(match, Match)  # already validated by the schema inside generate()
    assert 500 <= len(match.events) <= 2500


@pytest.mark.parametrize("match_id", ["demo-high-press", "balanced"])
def test_match_has_two_periods(match_id):
    match, _ = generated(match_id)
    types = [e.event_type for e in match.events]

    assert types[0] == "period_start"
    assert types[-1] == "period_end"
    assert types.count("period_start") == 2
    assert types.count("period_end") == 2


def test_same_seed_gives_identical_match():
    first, first_truth = generate(DEMO_HIGH_PRESS)
    second, second_truth = generate(DEMO_HIGH_PRESS)

    assert first.model_dump_json() == second.model_dump_json()
    assert first_truth == second_truth


def test_different_seed_gives_different_match():
    other, _ = generate(replace(DEMO_HIGH_PRESS, seed=43))
    demo, _ = generated("demo-high-press")

    assert other.model_dump_json() != demo.model_dump_json()


# --- Scripted events -------------------------------------------------------------


@pytest.mark.parametrize("scenario", [DEMO_HIGH_PRESS, BALANCED], ids=lambda s: s.match_id)
def test_only_scripted_goals_occur(scenario):
    match, truth = generated(scenario.match_id)
    goals = [e for e in match.events if isinstance(e, ShotEvent) and e.outcome == "goal"]

    assert [g.event_id for g in goals] == [g["event_id"] for g in truth["goals"]]
    for goal, scripted in zip(goals, scenario.goals):
        assert goal.team_id == (scenario.home if scripted.side == "home" else scenario.away).team_id
        # Inserted at the first possession boundary after the scripted time.
        assert scripted.time_s <= goal.timestamp_seconds <= scripted.time_s + 300


@pytest.mark.parametrize("match_id", ["demo-high-press", "balanced"])
def test_ground_truth_event_ids_exist(match_id):
    match, truth = generated(match_id)
    ids = {e.event_id for e in match.events}

    for goal in truth["goals"]:
        assert goal["event_id"] in ids
        assert set(goal["sequence_event_ids"]) <= ids
    assert truth["is_synthetic"] is True


@pytest.mark.parametrize("scenario", [DEMO_HIGH_PRESS, BALANCED], ids=lambda s: s.match_id)
def test_scripted_substitutions_occur(scenario):
    match, _ = generated(scenario.match_id)
    subs = [e for e in match.events if isinstance(e, SubstitutionEvent)]

    assert len(subs) == len(scenario.substitutions)


def test_demo_equaliser_follows_a_pressured_turnover():
    match, truth = generated("demo-high-press")
    equaliser = truth["goals"][1]
    by_id = {e.event_id: e for e in match.events}
    sequence = [by_id[i] for i in equaliser["sequence_event_ids"]]

    assert any(
        isinstance(e, PassEvent) and e.team_id == "NBR" and e.outcome == "incomplete" and e.under_pressure
        for e in sequence
    )
    assert any(e.event_type == "ball_recovery" and e.team_id == "EAS" for e in sequence)


# --- The planted patterns are visible in the data --------------------------------


def test_demo_high_press_is_visible():
    match, _ = generated("demo-high-press")
    baseline = per_minute(match, 0, 1200, "pressure", "EAS")
    shift = per_minute(match, 3300, 4200, "pressure", "EAS")

    assert shift >= 1.8 * baseline
    assert pass_completion(match, "NBR", 3300, 4200) <= pass_completion(match, "NBR", 0, 1200) - 0.05


def test_demo_false_alarm_burst_is_visible_but_short():
    match, truth = generated("demo-high-press")
    burst = truth["false_alarms"][0]

    assert burst["end_s"] - burst["start_s"] <= 240
    assert per_minute(match, burst["start_s"], burst["end_s"], "pressure", "EAS") > 1.5 * per_minute(
        match, 0, 1200, "pressure", "EAS"
    )


def test_demo_low_activity_period_is_quieter():
    match, _ = generated("demo-high-press")

    assert events_per_minute(match, 4800, 5400) < 0.75 * events_per_minute(match, 0, 4800)


def test_balanced_match_has_no_pressing_shift():
    match, truth = generated("balanced")

    assert truth["tactical_shifts"] == []
    assert per_minute(match, 3300, 4200, "pressure", "EAS") < 1.5 * per_minute(
        match, 0, 1200, "pressure", "EAS"
    )
