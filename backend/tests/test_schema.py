"""Tests for the event and match schema (backend/app/schema)."""

import pytest
from pydantic import ValidationError

from app.schema import Match, PassEvent, PeriodStartEvent, ShotEvent, SubstitutionEvent

MATCH_ID = "m1"


def make_team(team_id: str, name: str) -> dict:
    """11 starters + 3 substitutes with ids like 'A-p7'."""
    return {
        "team_id": team_id,
        "name": name,
        "short_name": team_id * 3,
        "players": [
            {
                "player_id": f"{team_id}-p{n}",
                "name": f"{name} Player {n}",
                "shirt_number": n,
                "position": "GK" if n == 1 else "MID",
            }
            for n in range(1, 15)
        ],
    }


def ev(event_id: str, t: float, event_type: str, **fields) -> dict:
    base = {"event_id": event_id, "match_id": MATCH_ID, "period": 1, "timestamp_seconds": t}
    return {**base, "event_type": event_type, **fields}


def a_pass(event_id: str = "e2", t: float = 5.0, **overrides) -> dict:
    fields = {
        "team_id": "A",
        "player_id": "A-p4",
        "start_x": 40,
        "start_y": 50,
        "end_x": 55,
        "end_y": 60,
        "outcome": "complete",
        "recipient_id": "A-p8",
    }
    return ev(event_id, t, "pass", **{**fields, **overrides})


def make_match(events: list[dict]) -> Match:
    return Match.model_validate(
        {
            "match_id": MATCH_ID,
            "home": make_team("A", "Northbridge"),
            "away": make_team("B", "Eastvale"),
            "events": events,
        }
    )


def valid_events() -> list[dict]:
    return [
        ev("e1", 0, "period_start"),
        a_pass(),
        ev("e3", 9, "pressure", team_id="B", player_id="B-p9", start_x=40, start_y=55),
        a_pass("e4", 11, outcome="incomplete", recipient_id=None, under_pressure=True),
        ev("e5", 12, "ball_recovery", team_id="B", player_id="B-p6", start_x=45, start_y=42),
        ev("e6", 20, "shot", team_id="B", player_id="B-p9", start_x=88, start_y=50, outcome="goal"),
        ev("e7", 2400, "substitution", team_id="A", player_out_id="A-p8", player_in_id="A-p12"),
        ev("e8", 2700, "period_end"),
    ]


# --- Valid data ---------------------------------------------------------


def test_valid_match_parses_into_typed_events():
    match = make_match(valid_events())

    assert len(match.events) == 8
    assert isinstance(match.events[0], PeriodStartEvent)
    assert isinstance(match.events[1], PassEvent)
    assert isinstance(match.events[5], ShotEvent)
    assert isinstance(match.events[6], SubstitutionEvent)
    assert match.is_synthetic is True


def test_json_round_trip_is_lossless():
    match = make_match(valid_events())

    assert Match.model_validate_json(match.model_dump_json()) == match


# --- Single-event rules ---------------------------------------------------


@pytest.mark.parametrize(
    ("bad_event", "reason"),
    [
        (ev("e2", 5, "dribble_magic", team_id="A", player_id="A-p4"), "unknown event type"),
        (a_pass(end_x=None), "pass without end location"),
        (a_pass(start_x=101), "coordinate above 100"),
        (a_pass(start_y=-1), "coordinate below 0"),
        (a_pass(outcome="incomplete"), "incomplete pass with recipient"),
        (a_pass(recipient_id="A-p4"), "pass to self"),
        (ev("e2", 5, "shot", team_id="A", player_id="A-p9", start_x=90, start_y=50,
            outcome="wide"), "invalid shot outcome"),
        (ev("e2", 5, "substitution", team_id="A", player_out_id="A-p8", player_in_id="A-p12",
            start_x=50, start_y=50), "substitution with coordinates"),
        (ev("e2", 5, "substitution", team_id="A", player_out_id="A-p8", player_in_id="A-p8"),
            "substituting a player for themselves"),
        (ev("e2", 5, "tackle", team_id="A", player_id="A-p4", start_x=30, start_y=30),
            "tackle without outcome"),
        (a_pass(period=3), "invalid period"),
        (a_pass(t=-1), "negative timestamp"),
    ],
)
def test_invalid_single_event_is_rejected(bad_event, reason):
    events = [ev("e1", 0, "period_start"), bad_event]

    with pytest.raises(ValidationError):
        make_match(events)


# --- Cross-event (match-level) rules ------------------------------------


@pytest.mark.parametrize(
    ("events", "expected_message"),
    [
        ([a_pass("e1", 1), a_pass("e1", 2)], "duplicate event_id"),
        ([a_pass("e1", 5), a_pass("e2", 3)], "strictly increasing"),
        ([a_pass("e1", 5), a_pass("e2", 5)], "strictly increasing"),
        ([a_pass("e1", 2800, period=2), a_pass("e2", 2900, period=1)], "period goes backwards"),
        ([a_pass("e1", 1, match_id="other")], "match_id"),
        ([a_pass("e1", 1, team_id="C")], "unknown team_id"),
        ([a_pass("e1", 1, player_id="B-p4")], "does not play for"),
        ([a_pass("e1", 1, recipient_id="B-p8")], "does not play for"),
        ([a_pass("e1", 1, player_id="A-p99")], "unknown player_id"),
    ],
)
def test_inconsistent_match_is_rejected(events, expected_message):
    with pytest.raises(ValidationError, match=expected_message):
        make_match(events)


def test_all_problems_are_reported_together():
    events = [a_pass("e1", 5), a_pass("e1", 3, player_id="B-p4")]

    with pytest.raises(ValidationError) as exc_info:
        make_match(events)

    message = str(exc_info.value)
    assert "duplicate event_id" in message
    assert "strictly increasing" in message
    assert "does not play for" in message


def test_teams_need_eleven_players():
    short_team = make_team("B", "Eastvale")
    short_team["players"] = short_team["players"][:10]

    with pytest.raises(ValidationError):
        Match.model_validate(
            {"match_id": MATCH_ID, "home": make_team("A", "Northbridge"), "away": short_team,
             "events": []}
        )
