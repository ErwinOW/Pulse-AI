"""Derive turnovers from the event sequence.

Turnovers are never stored as events (see app/schema/events.py); they are
derived here so there is a single source of truth.

A turnover is an open-play loss of the ball:
- an incomplete pass whose next ball-control event belongs to the opponent, or
- a tackle won by the opponent.
Passes that go out of play and shots are NOT turnovers.
"""

from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict

from app.schema import Event, PassEvent, TackleEvent

Zone = Literal["defensive", "middle", "final"]

# Events that show which team controls the ball.
BALL_CONTROL_TYPES = {"pass", "carry", "shot", "interception", "ball_recovery", "tackle"}


def zone_of(x: float) -> Zone:
    """Pitch third in the acting team's frame (attacking towards x = 100)."""
    if x < 100 / 3:
        return "defensive"
    if x < 200 / 3:
        return "middle"
    return "final"


class Turnover(BaseModel):
    model_config = ConfigDict(frozen=True)

    lost_by: str
    won_by: str
    timestamp_seconds: float
    x: float  # where the ball was lost, in the losing team's frame
    y: float
    zone: Zone
    under_pressure: bool
    evidence_event_ids: tuple[str, ...]  # losing action, then winning action


def find_turnovers(events: Sequence[Event], team_ids: tuple[str, str]) -> list[Turnover]:
    home, away = team_ids
    opponent = {home: away, away: home}
    turnovers: list[Turnover] = []

    for i, event in enumerate(events):
        if isinstance(event, TackleEvent) and event.outcome == "won":
            x, y = round(100 - event.start_x, 1), round(100 - event.start_y, 1)
            turnovers.append(
                Turnover(
                    lost_by=opponent[event.team_id],
                    won_by=event.team_id,
                    timestamp_seconds=event.timestamp_seconds,
                    x=x,
                    y=y,
                    zone=zone_of(x),
                    under_pressure=True,  # being tackled is direct pressure
                    evidence_event_ids=(event.event_id,),
                )
            )
            continue

        if not (isinstance(event, PassEvent) and event.outcome == "incomplete"):
            continue

        winner = None
        for later in events[i + 1:]:
            if later.event_type == "period_end":
                break
            if later.event_type in BALL_CONTROL_TYPES:
                winner = later
                break

        # No turnover if the passer's team kept the ball, the data ends, or the
        # ball was won by a tackle (counted by the tackle branch above).
        if winner is None or winner.team_id == event.team_id or winner.event_type == "tackle":
            continue

        turnovers.append(
            Turnover(
                lost_by=event.team_id,
                won_by=winner.team_id,
                timestamp_seconds=event.timestamp_seconds,
                x=event.start_x,
                y=event.start_y,
                zone=zone_of(event.start_x),
                under_pressure=event.under_pressure,
                evidence_event_ids=(event.event_id, winner.event_id),
            )
        )

    return turnovers
