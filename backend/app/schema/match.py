"""Match container: teams, players, and the ordered event list.

Cross-event rules that a single event cannot check on its own live here.
All problems are collected and reported together, so a broken fixture shows
every error in one test run.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .events import Event, Identifier


class Player(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    player_id: Identifier
    name: Identifier
    shirt_number: int = Field(ge=1, le=99)
    position: Literal["GK", "DEF", "MID", "FWD"]


class Team(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    team_id: Identifier
    name: Identifier
    short_name: str = Field(min_length=2, max_length=4)
    players: list[Player] = Field(min_length=11)


class Match(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    match_id: Identifier
    # All PULSE data is synthetic (hackathon rule). Kept explicit so it
    # travels with every exported match file.
    is_synthetic: Literal[True] = True
    home: Team
    away: Team
    events: list[Event]

    @model_validator(mode="after")
    def _check_consistency(self) -> "Match":
        problems: list[str] = []

        if self.home.team_id == self.away.team_id:
            problems.append("home and away must have different team_id")

        # player_id -> team_id
        player_team: dict[str, str] = {}
        for team in (self.home, self.away):
            for player in team.players:
                if player.player_id in player_team:
                    problems.append(f"duplicate player_id {player.player_id!r}")
                player_team[player.player_id] = team.team_id

        team_ids = {self.home.team_id, self.away.team_id}
        seen_event_ids: set[str] = set()
        previous = None

        for event in self.events:
            label = f"event {event.event_id!r}"

            if event.event_id in seen_event_ids:
                problems.append(f"{label}: duplicate event_id")
            seen_event_ids.add(event.event_id)

            if event.match_id != self.match_id:
                problems.append(f"{label}: match_id {event.match_id!r} != {self.match_id!r}")

            if previous is not None:
                if event.timestamp_seconds <= previous.timestamp_seconds:
                    problems.append(
                        f"{label}: timestamp {event.timestamp_seconds} is not after "
                        f"{previous.timestamp_seconds} (events must be strictly increasing)"
                    )
                if event.period < previous.period:
                    problems.append(f"{label}: period goes backwards")
            previous = event

            team_id = getattr(event, "team_id", None)
            if team_id is None:
                continue
            if team_id not in team_ids:
                problems.append(f"{label}: unknown team_id {team_id!r}")
                continue

            for field in ("player_id", "recipient_id", "player_out_id", "player_in_id"):
                pid = getattr(event, field, None)
                if pid is None:
                    continue
                if pid not in player_team:
                    problems.append(f"{label}: unknown {field} {pid!r}")
                elif player_team[pid] != team_id:
                    problems.append(f"{label}: {field} {pid!r} does not play for {team_id!r}")

        if problems:
            raise ValueError("invalid match:\n- " + "\n- ".join(problems))
        return self
