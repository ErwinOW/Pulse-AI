"""Tests for the statistics engine (backend/app/stats).

Most tests use tiny hand-built event lists whose correct answers can be
worked out on paper; the final tests check the generated demo match.
"""

import pytest

from app.schema import (
    BallRecoveryEvent,
    CarryEvent,
    PassEvent,
    PressureEvent,
    ShotEvent,
    TackleEvent,
)
from app.simulator import BALANCED, DEMO_HIGH_PRESS, generate
from app.stats import DEFINITIONS, compute_window, find_turnovers, rolling_windows, score

A, B = "A", "B"
TEAMS = (A, B)


def _base(t: float) -> dict:
    return {"event_id": f"e{t:g}", "match_id": "m", "period": 1, "timestamp_seconds": t}


def pass_(t, team, sx=50.0, sy=50.0, ex=60.0, ey=50.0, outcome="complete", pressure=False):
    return PassEvent(
        **_base(t), team_id=team, player_id=f"{team}-1",
        start_x=sx, start_y=sy, end_x=ex, end_y=ey, outcome=outcome, under_pressure=pressure,
        recipient_id=f"{team}-2" if outcome == "complete" else None,
    )


def carry(t, team, sx=50.0, sy=50.0, ex=55.0, ey=50.0):
    return CarryEvent(**_base(t), team_id=team, player_id=f"{team}-1",
                      start_x=sx, start_y=sy, end_x=ex, end_y=ey)


def shot(t, team, outcome="saved", x=88.0, y=50.0):
    return ShotEvent(**_base(t), team_id=team, player_id=f"{team}-9", start_x=x, start_y=y,
                     outcome=outcome)


def recovery(t, team, x=50.0, y=50.0):
    return BallRecoveryEvent(**_base(t), team_id=team, player_id=f"{team}-4", start_x=x, start_y=y)


def pressure(t, team, x=50.0, y=50.0):
    return PressureEvent(**_base(t), team_id=team, player_id=f"{team}-7", start_x=x, start_y=y)


def stats(events, start=0.0, end=300.0):
    return compute_window(events, TEAMS, start, end)


# --- Pass completion and possession --------------------------------------------


def test_pass_completion_is_completed_over_attempted():
    events = [pass_(1, A), pass_(2, A), pass_(3, A), pass_(4, A, outcome="incomplete")]

    result = stats(events).teams[A].pass_completion

    assert result.value == 75.0
    assert result.sample_size == 4


def test_pass_completion_is_unavailable_without_passes():
    result = stats([pass_(1, A)]).teams[B].pass_completion

    assert result.value is None  # unavailable, not 0%
    assert result.sample_size == 0


def test_possession_share_counts_on_ball_actions():
    events = [pass_(1, A), pass_(2, A), carry(3, A), shot(4, B), pressure(5, B)]  # pressure ignored

    window = stats(events)

    assert window.teams[A].possession_share.value == 75.0
    assert window.teams[B].possession_share.value == 25.0
    assert window.teams[A].possession_share.sample_size == 4


def test_possession_is_unavailable_in_empty_window():
    assert stats([]).teams[A].possession_share.value is None


# --- Turnovers ---------------------------------------------------------------------


def test_incomplete_pass_won_by_opponent_is_a_turnover():
    events = [pass_(1, A, sx=20, ex=30, outcome="incomplete", pressure=True), recovery(2, B, x=70)]

    (turnover,) = find_turnovers(events, TEAMS)
    team = stats(events).teams[A]

    assert turnover.lost_by == A and turnover.won_by == B
    assert turnover.zone == "defensive"  # lost at x = 20 in A's frame
    assert turnover.under_pressure is True
    assert turnover.evidence_event_ids == ("e1", "e2")
    assert team.turnovers.value == 1
    assert team.turnovers_under_pressure.value == 1
    assert team.turnovers_by_zone == {"defensive": 1, "middle": 0, "final": 0}


def test_pressure_between_pass_and_recovery_does_not_hide_turnover():
    events = [pass_(1, A, outcome="incomplete"), pressure(2, A), recovery(3, B)]

    (turnover,) = find_turnovers(events, TEAMS)

    assert turnover.evidence_event_ids == ("e1", "e3")


@pytest.mark.parametrize(
    "events",
    [
        [pass_(1, A, outcome="incomplete"), recovery(2, A)],  # own team regains the ball
        [pass_(1, A, outcome="out"), pass_(2, B)],  # out of play: not open-play loss
        [shot(1, A), pass_(2, B)],  # shot: not a turnover
        [pass_(1, A, outcome="incomplete")],  # no later event yet (live data)
    ],
    ids=["own-team-regains", "out-of-play", "shot", "no-winner-yet"],
)
def test_non_turnovers(events):
    assert find_turnovers(events, TEAMS) == []


def test_tackle_won_is_a_turnover_in_the_losers_frame():
    tackle = TackleEvent(**_base(1), team_id=B, player_id="B-4", start_x=80, start_y=30,
                         outcome="won")

    (turnover,) = find_turnovers([tackle], TEAMS)

    assert turnover.lost_by == A
    assert (turnover.x, turnover.y) == (20.0, 70.0)
    assert turnover.zone == "defensive"
    assert turnover.under_pressure is True


# --- Shots, box entries, pressure ----------------------------------------------------


def test_shots_and_shots_on_target():
    team = stats([shot(1, A, "goal"), shot(2, A, "saved"), shot(3, A, "off_target")]).teams[A]

    assert team.shots.value == 3
    assert team.shots_on_target.value == 2


def test_box_entries():
    events = [
        pass_(1, A, ex=85, ey=50),  # yes
        pass_(2, A, ex=85, ey=10),  # no: wide of the box
        pass_(3, A, ex=90, ey=50, outcome="incomplete"),  # no: not completed
        carry(4, A, sx=78, ex=84, ey=30),  # yes
        pass_(5, A, sx=85, sy=50, ex=90, ey=45),  # no: already inside the box
    ]

    assert stats(events).teams[A].box_entries.value == 2


def test_pressure_rates_per_minute():
    events = [pressure(1, B, x=70), pressure(2, B, x=65), pressure(3, B, x=40)]

    team = stats(events, 0, 300).teams[B]  # 5-minute window

    assert team.pressures_per_min.value == 0.6
    assert team.high_pressures_per_min.value == 0.4
    assert team.high_pressures_per_min.sample_size == 2


def test_momentum_uses_documented_weights():
    # Pass 60 -> 85 is a box entry (2) AND a pass into the final third (0.5);
    # a saved shot is 3 + 2 on target.  Total 7.5.
    events = [pass_(1, A, sx=60, ex=85, ey=50), shot(2, A, "saved")]

    momentum = stats(events).teams[A].momentum

    assert momentum.value == 7.5
    assert momentum.sample_size == 3


def test_every_metric_has_a_definition():
    team = stats([pass_(1, A)]).teams[A]
    metric_ids = {
        getattr(team, name).definition_id
        for name in type(team).model_fields
        if name not in ("team_id", "turnovers_by_zone")
    }

    assert metric_ids <= set(DEFINITIONS)


# --- Windows and score ------------------------------------------------------------


def test_window_excludes_events_outside_it():
    events = [pass_(10, A), pass_(400, A)]

    assert stats(events, 0, 300).teams[A].pass_completion.sample_size == 1


def test_rolling_windows_cover_the_match_so_far():
    windows = rolling_windows([], TEAMS, until_s=600, window_s=300, step_s=60)

    assert len(windows) == 10
    assert (windows[0].start_s, windows[0].end_s) == (0.0, 60.0)
    assert (windows[-1].start_s, windows[-1].end_s) == (300.0, 600.0)


def test_score_counts_goals_before_time():
    events = [shot(10, A, "goal"), shot(20, B, "saved"), shot(30, B, "goal")]

    assert score(events, TEAMS, until_s=25) == {A: 1, B: 0}
    assert score(events, TEAMS, until_s=31) == {A: 1, B: 1}


# --- Generated matches ------------------------------------------------------------


def test_demo_match_stats_reflect_the_high_press():
    match, _ = generate(DEMO_HIGH_PRESS)
    teams = ("NBR", "EAS")
    baseline = compute_window(match.events, teams, 0, 900)  # 15 minutes
    press = compute_window(match.events, teams, 3300, 4200)  # 15 minutes

    assert press.teams["NBR"].turnovers.value > baseline.teams["NBR"].turnovers.value
    assert (
        press.teams["EAS"].high_pressures_per_min.value
        > baseline.teams["EAS"].high_pressures_per_min.value
    )
    assert score(match.events, teams, until_s=10_000) == {"NBR": 1, "EAS": 1}


def test_balanced_match_stats_are_available_for_both_teams():
    match, _ = generate(BALANCED)
    window = compute_window(match.events, ("NBR", "EAS"), 0, 5400)

    for team in window.teams.values():
        assert team.pass_completion.value is not None
        assert 30 <= team.possession_share.value <= 70
