"""Tests for the match API (backend/app/api): listing, state at time t, no future leakage."""

import json

from fastapi.testclient import TestClient

from app.api import service
from app.main import app

client = TestClient(app)
DEMO = "demo-high-press"


def state(t: float, match_id: str = DEMO) -> dict:
    response = client.get(f"/api/matches/{match_id}/state", params={"t": t})
    assert response.status_code == 200, response.text
    return response.json()


def test_lists_committed_matches():
    matches = {m["match_id"]: m for m in client.get("/api/matches").json()}

    assert set(matches) == {"balanced", DEMO}
    assert matches[DEMO]["home"]["name"] == "Northbridge FC"
    assert matches[DEMO]["is_synthetic"] is True


def test_unknown_match_is_404():
    assert client.get("/api/matches/nope").status_code == 404
    assert client.get("/api/matches/nope/state", params={"t": 10}).status_code == 404


def test_negative_time_is_rejected():
    assert client.get(f"/api/matches/{DEMO}/state", params={"t": -1}).status_code == 422


def test_kickoff_state_is_empty():
    s = state(0)

    assert s["score"] == {"NBR": 0, "EAS": 0}
    assert s["recent_events"] == [] and s["momentum"] == [] and s["alerts"] == []


def test_state_at_50_minutes_contains_nothing_from_the_future():
    t = 3000.0
    s = state(t)

    assert s["recent_events"] and all(e["timestamp_seconds"] < t for e in s["recent_events"])
    assert all(a["first_detected_s"] <= t for a in s["alerts"])
    assert all(p["end_s"] <= t for p in s["momentum"])
    assert s["window"]["end_s"] == t and s["totals"]["end_s"] == t
    assert s["score"] == {"NBR": 1, "EAS": 0}  # Northbridge scored ~35', equaliser comes ~64'
    assert [g["team_id"] for g in s["goals"]] == ["NBR"]
    assert s["alerts"] == []  # the press is detected after 60'
    assert s["minute"] == 51 and s["period"] == 2


def test_full_match_state_has_final_score_and_the_alert():
    duration = client.get(f"/api/matches/{DEMO}").json()["duration_s"]
    s = state(duration + 1)

    assert s["score"] == {"NBR": 1, "EAS": 1}
    assert [a["team_id"] for a in s["alerts"]] == ["EAS"]


def test_momentum_has_one_point_per_completed_minute_and_diff_is_home_minus_away():
    s = state(1830)  # 30.5 minutes in

    assert len(s["momentum"]) == 30
    for point in s["momentum"]:
        assert point["diff"] == point["home"] - point["away"]


def test_rewound_state_matches_state_computed_directly():
    late, early = state(4000), state(2500)

    assert early == state(2500)  # same answer however we got there
    assert len(early["momentum"]) < len(late["momentum"])


def turning_points(t: float, match_id: str = DEMO) -> list[dict]:
    response = client.get(f"/api/matches/{match_id}/turning-points", params={"t": t})
    assert response.status_code == 200, response.text
    return response.json()


def ground_truth_goals(match_id: str = DEMO) -> list[dict]:
    # Only tests read ground truth; the app never does.
    return json.loads((service.DATA_DIR / f"{match_id}.ground_truth.json").read_text())["goals"]


def test_turning_points_only_include_goals_before_t():
    first_goal, second_goal = ground_truth_goals()

    assert [p["goal_event_id"] for p in turning_points(3000)] == [first_goal["event_id"]]
    assert [p["goal_event_id"] for p in turning_points(9999)] == [
        first_goal["event_id"], second_goal["event_id"]
    ]
    assert turning_points(first_goal["timestamp_seconds"]) == []  # goal at exactly t is not yet "before t"


def test_equaliser_traces_back_to_northbridge_pass_lost_under_pressure():
    truth = ground_truth_goals()[1]  # scripted high-turnover goal ~63'
    point = turning_points(9999)[1]

    assert point["team_id"] == "EAS" and point["possession_start"] == "turnover"
    turnover = point["turnover"]
    assert turnover["lost_by"] == "NBR" and turnover["under_pressure"] is True
    # The misplaced pass and the recovery are both part of the scripted sequence.
    assert set(turnover["evidence_event_ids"]) <= set(truth["sequence_event_ids"])
    assert set(point["possession_event_ids"]) <= set(truth["sequence_event_ids"])
    assert point["possession_event_ids"][-1] == truth["event_id"]
    assert point["pressure_event_ids"] and set(point["pressure_event_ids"]) <= set(truth["sequence_event_ids"])
    assert point["score_before"] == {"NBR": 1, "EAS": 0} and point["score_after"] == {"NBR": 1, "EAS": 1}


def test_opener_is_a_patient_move_with_no_recorded_ball_win():
    truth = ground_truth_goals()[0]  # scripted patient-possession goal ~35'
    point = turning_points(9999)[0]

    assert point["possession_event_ids"] == truth["sequence_event_ids"]
    assert point["possession_passes"] == 5
    assert point["possession_start"] == "not_recorded" and point["turnover"] is None


def test_turning_points_carry_their_build_up_events_for_the_pitch_view():
    equaliser = turning_points(9999)[1]
    chain = [e["event_id"] for e in equaliser["chain_events"]]
    expected = set(equaliser["possession_event_ids"]) | set(equaliser["pressure_event_ids"]) | set(
        equaliser["turnover"]["evidence_event_ids"]
    )

    assert set(chain) == expected
    assert [e["timestamp_seconds"] for e in equaliser["chain_events"]] == sorted(
        e["timestamp_seconds"] for e in equaliser["chain_events"]
    )
    assert all(e["timestamp_seconds"] <= equaliser["timestamp_seconds"] for e in equaliser["chain_events"])


def test_only_the_equaliser_is_linked_to_the_pressing_alert():
    alerts = state(9999)["alerts"]
    opener, equaliser = turning_points(9999)

    assert opener["related_alert_ids"] == []
    assert equaliser["related_alert_ids"] == [alerts[0]["alert_id"]]


def test_alert_after_the_window_is_not_linked_in_the_balanced_match():
    # balanced: a (false) NBR alert last confirmed ~15 minutes before NBR's goal -> outside the 10-minute link.
    assert all(p["related_alert_ids"] == [] for p in turning_points(9999, "balanced"))


def test_unknown_match_turning_points_is_404():
    assert client.get("/api/matches/nope/turning-points", params={"t": 10}).status_code == 404


def test_definitions_are_published():
    definitions = client.get("/api/definitions").json()

    assert "pass_completion" in definitions and "momentum" in definitions
