"""Tests for the match API (backend/app/api): listing, state at time t, no future leakage."""

from fastapi.testclient import TestClient

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


def test_definitions_are_published():
    definitions = client.get("/api/definitions").json()

    assert "pass_completion" in definitions and "momentum" in definitions
