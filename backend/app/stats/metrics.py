"""Deterministic match metrics.

Every number shown in the UI or cited by the AI comes from this module.
Stats are recomputed from the event list for a time window instead of being
updated incrementally: cheap at our scale (~1,500 events), impossible to
drift, and rewinding is just "compute up to an earlier time".

Each metric carries its definition id and sample size so the UI can show how
it was computed and flag small samples. A value of None means "unavailable"
(e.g. pass completion with zero passes) and must never be displayed as 0.
"""

from typing import Sequence

from pydantic import BaseModel, ConfigDict

from app.schema import CarryEvent, Event, PassEvent, PressureEvent, ShotEvent

from .turnovers import Turnover, find_turnovers

FINAL_THIRD_X = 200 / 3
BOX_MIN_X = 83.0  # approximate penalty area on the 0-100 pitch
BOX_Y_RANGE = (21.0, 79.0)
HIGH_PRESS_MIN_X = 60.0  # pressure in the opponent's build-up area (presser's frame)
ON_BALL_TYPES = {"pass", "carry", "shot"}

MOMENTUM_WEIGHTS = {
    "shot": 3.0,
    "shot_on_target_bonus": 2.0,
    "box_entry": 2.0,
    "final_third_ball_win": 1.5,
    "final_third_pass": 0.5,
}

DEFINITIONS: dict[str, str] = {
    "possession_share": "Estimated possession: the team's on-ball actions (passes, carries, shots) "
    "as a percentage of both teams' on-ball actions in the window.",
    "pass_completion": "Completed passes as a percentage of all passes in the window.",
    "turnovers": "Open-play losses of the ball: an incomplete pass won by the opponent, or a tackle "
    "won by the opponent. Out-of-play passes and shots are excluded.",
    "turnovers_under_pressure": "Turnovers where the losing pass was under pressure, or the ball "
    "was lost to a tackle.",
    "shots": "Shot attempts.",
    "shots_on_target": "Shots with outcome goal or saved.",
    "box_entries": "Completed passes or carries that move the ball from outside into the "
    "approximate penalty area (x >= 83, 21 <= y <= 79).",
    "pressures_per_min": "Pressure events per minute (estimate; no tracking data).",
    "high_pressures_per_min": "Pressure events per minute located at x >= 60 in the presser's "
    "frame, i.e. in the opponent's build-up area (estimate).",
    "momentum": "Indicator, not a measurement. Weighted sum: shot 3 (+2 if on target), box entry 2, "
    "ball won in the final third 1.5, completed pass into the final third 0.5.",
}


class Metric(BaseModel):
    model_config = ConfigDict(frozen=True)

    definition_id: str
    value: float | None  # None = unavailable
    sample_size: int


class TeamStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    team_id: str
    possession_share: Metric
    pass_completion: Metric
    turnovers: Metric
    turnovers_under_pressure: Metric
    turnovers_by_zone: dict[str, int]
    shots: Metric
    shots_on_target: Metric
    box_entries: Metric
    pressures_per_min: Metric
    high_pressures_per_min: Metric
    momentum: Metric


class WindowStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_s: float
    end_s: float
    teams: dict[str, TeamStats]
    turnovers: list[Turnover]  # evidence for detectors and narratives


def _percent(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def _in_box(x: float, y: float) -> bool:
    return x >= BOX_MIN_X and BOX_Y_RANGE[0] <= y <= BOX_Y_RANGE[1]


def _is_box_entry(event: Event) -> bool:
    """Completed pass or carry that moves the ball from outside the box into it."""
    if isinstance(event, PassEvent) and event.outcome != "complete":
        return False
    if not isinstance(event, (PassEvent, CarryEvent)):
        return False
    return _in_box(event.end_x, event.end_y) and not _in_box(event.start_x, event.start_y)


def _is_final_third_pass(event: Event) -> bool:
    return (
        isinstance(event, PassEvent)
        and event.outcome == "complete"
        and event.start_x < FINAL_THIRD_X <= event.end_x
    )


def compute_window(
    events: Sequence[Event], team_ids: tuple[str, str], start_s: float, end_s: float
) -> WindowStats:
    """Metrics for each team over events with start_s <= timestamp < end_s."""
    in_window = [e for e in events if start_s <= e.timestamp_seconds < end_s]
    turnovers = [t for t in find_turnovers(events, team_ids) if start_s <= t.timestamp_seconds < end_s]
    minutes = (end_s - start_s) / 60
    total_on_ball = sum(1 for e in in_window if e.event_type in ON_BALL_TYPES)

    teams: dict[str, TeamStats] = {}
    for team_id in team_ids:
        own = [e for e in in_window if getattr(e, "team_id", None) == team_id]
        passes = [e for e in own if isinstance(e, PassEvent)]
        shots = [e for e in own if isinstance(e, ShotEvent)]
        on_target = [s for s in shots if s.outcome in ("goal", "saved")]
        box_entries = [e for e in own if _is_box_entry(e)]
        final_third_passes = [e for e in own if _is_final_third_pass(e)]
        pressures = [e for e in own if isinstance(e, PressureEvent)]
        high_pressures = [p for p in pressures if p.start_x >= HIGH_PRESS_MIN_X]
        lost = [t for t in turnovers if t.lost_by == team_id]
        won_in_final_third = [t for t in turnovers if t.won_by == team_id and t.zone == "defensive"]
        on_ball = sum(1 for e in own if e.event_type in ON_BALL_TYPES)

        w = MOMENTUM_WEIGHTS
        momentum = (
            w["shot"] * len(shots)
            + w["shot_on_target_bonus"] * len(on_target)
            + w["box_entry"] * len(box_entries)
            + w["final_third_ball_win"] * len(won_in_final_third)
            + w["final_third_pass"] * len(final_third_passes)
        )
        momentum_sample = (
            len(shots) + len(box_entries) + len(won_in_final_third) + len(final_third_passes)
        )

        def per_min(count: int) -> float | None:
            return round(count / minutes, 2) if minutes > 0 else None

        teams[team_id] = TeamStats(
            team_id=team_id,
            possession_share=Metric(
                definition_id="possession_share",
                value=_percent(on_ball, total_on_ball),
                sample_size=total_on_ball,
            ),
            pass_completion=Metric(
                definition_id="pass_completion",
                value=_percent(sum(p.outcome == "complete" for p in passes), len(passes)),
                sample_size=len(passes),
            ),
            turnovers=Metric(definition_id="turnovers", value=len(lost), sample_size=len(lost)),
            turnovers_under_pressure=Metric(
                definition_id="turnovers_under_pressure",
                value=sum(t.under_pressure for t in lost),
                sample_size=len(lost),
            ),
            turnovers_by_zone={
                zone: sum(t.zone == zone for t in lost) for zone in ("defensive", "middle", "final")
            },
            shots=Metric(definition_id="shots", value=len(shots), sample_size=len(shots)),
            shots_on_target=Metric(
                definition_id="shots_on_target", value=len(on_target), sample_size=len(shots)
            ),
            box_entries=Metric(
                definition_id="box_entries", value=len(box_entries), sample_size=len(box_entries)
            ),
            pressures_per_min=Metric(
                definition_id="pressures_per_min",
                value=per_min(len(pressures)),
                sample_size=len(pressures),
            ),
            high_pressures_per_min=Metric(
                definition_id="high_pressures_per_min",
                value=per_min(len(high_pressures)),
                sample_size=len(high_pressures),
            ),
            momentum=Metric(definition_id="momentum", value=momentum, sample_size=momentum_sample),
        )

    return WindowStats(start_s=start_s, end_s=end_s, teams=teams, turnovers=turnovers)


def rolling_windows(
    events: Sequence[Event],
    team_ids: tuple[str, str],
    until_s: float,
    window_s: float = 300.0,
    step_s: float = 60.0,
) -> list[WindowStats]:
    """Stats for windows ending every `step_s` seconds up to `until_s`.

    Early windows are shorter than `window_s` (they start at kick-off).
    """
    results = []
    end = step_s
    while end <= until_s:
        results.append(compute_window(events, team_ids, max(0.0, end - window_s), end))
        end += step_s
    return results


def score(events: Sequence[Event], team_ids: tuple[str, str], until_s: float) -> dict[str, int]:
    """Goals per team scored before `until_s`."""
    goals = {team_id: 0 for team_id in team_ids}
    for e in events:
        if isinstance(e, ShotEvent) and e.outcome == "goal" and e.timestamp_seconds < until_s:
            goals[e.team_id] += 1
    return goals
