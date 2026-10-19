"""Goal turning points: how each goal's possession started and what led to it.

Built only from the event data (no AI). For each goal we trace the scoring
team's possession back to the last moment the opponent controlled the ball,
then check whether that possession began with a derived turnover.

Some possessions have no recorded start (e.g. the simulator's scripted
build-ups begin straight after an opponent action without a ball-winning
event); these are reported as "not_recorded" rather than guessed.
"""

from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict

from app.schema import Event, ShotEvent, TackleEvent

from .turnovers import Turnover, find_turnovers

# Opponent events that mean the opponent had the ball (a lost tackle does not).
_CONTROL_TYPES = {"pass", "carry", "shot", "interception", "ball_recovery"}
PRESSURE_LOOKBACK_S = 5.0


class GoalTurningPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    turning_point_id: str
    kind: Literal["goal"] = "goal"
    team_id: str
    goal_event_id: str
    timestamp_seconds: float
    score_before: dict[str, int]
    score_after: dict[str, int]
    possession_event_ids: list[str]  # possession start to the goal, in match order
    possession_duration_s: float
    possession_passes: int
    possession_start: Literal["turnover", "not_recorded"]
    turnover: Turnover | None  # how the ball was won, when recorded
    pressure_event_ids: list[str]  # scoring team's pressures just before the turnover
    related_alert_ids: list[str] = []  # filled by the API: alerts active before the goal


def _controls_ball(event: Event) -> bool:
    if isinstance(event, TackleEvent):
        return event.outcome == "won"
    return event.event_type in _CONTROL_TYPES


def goal_turning_points(events: Sequence[Event], team_ids: tuple[str, str]) -> list[GoalTurningPoint]:
    """One turning point per goal in `events` (pass only events before t to stay time-safe)."""
    turnovers_by_winner = {t.evidence_event_ids[-1]: t for t in find_turnovers(events, team_ids)}
    goals = {team_id: 0 for team_id in team_ids}
    points: list[GoalTurningPoint] = []

    for g, goal in enumerate(events):
        if not (isinstance(goal, ShotEvent) and goal.outcome == "goal"):
            continue

        start = g
        for i in range(g - 1, -1, -1):
            e = events[i]
            if e.event_type in ("period_start", "period_end"):
                break
            if getattr(e, "team_id", None) == goal.team_id:
                if _controls_ball(e):
                    start = i
            elif _controls_ball(e):
                break
        possession = events[start: g + 1]

        turnover = turnovers_by_winner.get(events[start].event_id)
        if turnover is not None and turnover.won_by != goal.team_id:
            turnover = None
        pressures = []
        if turnover is not None:
            pressures = [
                e.event_id for e in events[:start]
                if e.event_type == "pressure" and e.team_id == goal.team_id
                and turnover.timestamp_seconds - PRESSURE_LOOKBACK_S <= e.timestamp_seconds
                <= turnover.timestamp_seconds
            ]

        before = dict(goals)
        goals[goal.team_id] += 1
        points.append(
            GoalTurningPoint(
                turning_point_id=f"goal-{goal.event_id}",
                team_id=goal.team_id,
                goal_event_id=goal.event_id,
                timestamp_seconds=goal.timestamp_seconds,
                score_before=before,
                score_after=dict(goals),
                possession_event_ids=[e.event_id for e in possession],
                possession_duration_s=round(goal.timestamp_seconds - events[start].timestamp_seconds, 1),
                possession_passes=sum(
                    1 for e in possession if e.event_type == "pass" and e.team_id == goal.team_id
                ),
                possession_start="turnover" if turnover else "not_recorded",
                turnover=turnover,
                pressure_event_ids=pressures,
            )
        )

    return points
