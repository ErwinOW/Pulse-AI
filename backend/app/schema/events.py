"""Match event schema.

Conventions (see docs/PROGRESS.md):
- Coordinates are 0-100 on both axes, normalised so the acting team always
  attacks towards x = 100. y = 0 is the attacking team's right touchline.
- `timestamp_seconds` is the match clock from kick-off (2700 = 45:00) and
  keeps running across periods; events in a match are strictly increasing.
- Goals are shots with outcome "goal". Turnovers and possession changes are
  derived by the statistics engine, never stored as events.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Coordinate = Annotated[float, Field(ge=0, le=100)]
Identifier = Annotated[str, Field(min_length=1)]


class _EventBase(BaseModel):
    # extra="forbid" rejects fields that do not belong to an event type,
    # e.g. coordinates on a substitution.
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: Identifier
    match_id: Identifier
    period: Literal[1, 2]
    timestamp_seconds: float = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class _TeamEvent(_EventBase):
    team_id: Identifier


class _PlayerEvent(_TeamEvent):
    player_id: Identifier
    start_x: Coordinate
    start_y: Coordinate


class _MovingEvent(_PlayerEvent):
    end_x: Coordinate
    end_y: Coordinate
    under_pressure: bool = False


# --- On-ball events -------------------------------------------------------


class PassEvent(_MovingEvent):
    event_type: Literal["pass"] = "pass"
    outcome: Literal["complete", "incomplete", "out"]
    recipient_id: Identifier | None = None

    @model_validator(mode="after")
    def _recipient_only_when_complete(self) -> "PassEvent":
        if self.outcome != "complete" and self.recipient_id is not None:
            raise ValueError("recipient_id is only allowed on complete passes")
        if self.recipient_id == self.player_id:
            raise ValueError("a player cannot pass to themselves")
        return self


class CarryEvent(_MovingEvent):
    event_type: Literal["carry"] = "carry"


class ShotEvent(_PlayerEvent):
    event_type: Literal["shot"] = "shot"
    outcome: Literal["goal", "saved", "off_target", "blocked"]
    under_pressure: bool = False


# --- Defensive / contest events ------------------------------------------


class PressureEvent(_PlayerEvent):
    event_type: Literal["pressure"] = "pressure"


class TackleEvent(_PlayerEvent):
    event_type: Literal["tackle"] = "tackle"
    outcome: Literal["won", "lost"]


class InterceptionEvent(_PlayerEvent):
    event_type: Literal["interception"] = "interception"


class BallRecoveryEvent(_PlayerEvent):
    event_type: Literal["ball_recovery"] = "ball_recovery"


class FoulEvent(_PlayerEvent):
    event_type: Literal["foul"] = "foul"
    card: Literal["yellow", "red"] | None = None


# --- Non-spatial events ---------------------------------------------------


class SubstitutionEvent(_TeamEvent):
    event_type: Literal["substitution"] = "substitution"
    player_out_id: Identifier
    player_in_id: Identifier

    @model_validator(mode="after")
    def _different_players(self) -> "SubstitutionEvent":
        if self.player_out_id == self.player_in_id:
            raise ValueError("player_out_id and player_in_id must differ")
        return self


class PeriodStartEvent(_EventBase):
    event_type: Literal["period_start"] = "period_start"


class PeriodEndEvent(_EventBase):
    event_type: Literal["period_end"] = "period_end"


# Pydantic picks the right model from `event_type`; unknown types are rejected.
Event = Annotated[
    PassEvent
    | CarryEvent
    | ShotEvent
    | PressureEvent
    | TackleEvent
    | InterceptionEvent
    | BallRecoveryEvent
    | FoulEvent
    | SubstitutionEvent
    | PeriodStartEvent
    | PeriodEndEvent,
    Field(discriminator="event_type"),
]
