"""Tests for key-event labels (backend/app/stats/key_events.py) and how the API exposes them."""

import pytest
from fastapi.testclient import TestClient

from app.api import replay, service
from app.main import app
from app.stats import key_event_tags, visible_tags

client = TestClient(app)
DEMO = "demo-high-press"


def eid(n: int) -> str:
    return f"{DEMO}-e{n:04d}"


@pytest.fixture(scope="module")
def demo():
    match = service.load_match(DEMO)
    return match, key_event_tags(match.events, service.teams_of(match))


def test_equaliser_sequence_is_labelled_from_press_to_goal(demo):
    _, tags = demo
    visible = visible_tags(tags, 9999)

    assert visible[eid(1298)] == ["winning_press"]  # Eastvale pressure
    assert visible[eid(1299)] == ["lost_under_pressure"]  # Northbridge pass lost
    assert visible[eid(1300)] == ["ball_won_high"]  # Eastvale recovery at x 62 (Northbridge's third)
    assert visible[eid(1301)] == ["key_pass"]
    assert visible[eid(1302)] == ["box_entry"]
    assert visible[eid(1303)] == ["goal"]


def test_opener_build_up_passes_are_not_labelled_only_the_final_ones(demo):
    _, tags = demo
    visible = visible_tags(tags, 9999)

    assert all(eid(n) not in visible for n in range(690, 694))  # routine build-up passes
    assert sorted(visible[eid(694)]) == ["box_entry", "key_pass"]
    assert visible[eid(695)] == ["goal"]


def test_labels_never_reveal_the_future(demo):
    match, tags = demo
    teams = service.teams_of(match)
    for t in (600.0, 2085.3, 3804.4, 3813.7, 4500.0):
        from_past_only = visible_tags(key_event_tags(service.events_before(match, t), teams), t)
        assert visible_tags(tags, t) == from_past_only


def test_key_pass_appears_only_once_the_shot_happens(demo):
    _, tags = demo
    shot_t = service.load_match(DEMO).events[1302].timestamp_seconds  # e1303, the equaliser

    assert eid(1301) not in visible_tags(tags, shot_t)  # shot not yet "before t"
    assert "key_pass" in visible_tags(tags, shot_t + 0.1)[eid(1301)]


def test_key_events_are_a_small_share_of_all_events(demo):
    match, tags = demo
    share = len({t.event_id for t in tags}) / len(match.events)

    assert 0.05 < share < 0.30  # a highlight feed, not every pass


def test_state_sends_key_events_with_their_labels():
    s = client.get(f"/api/matches/{DEMO}/state", params={"t": 3900}).json()

    key_ids = [e["event_id"] for e in s["key_events"]]
    assert eid(1303) in key_ids and eid(1301) in key_ids
    assert all(event_id in s["event_tags"] for event_id in key_ids)
    assert all(e["timestamp_seconds"] < 3900 for e in s["key_events"])
    assert len(key_ids) <= service.KEY_EVENTS


def test_replay_ticks_carry_newly_revealed_labels(monkeypatch):
    monkeypatch.setattr(replay, "TICK_SLEEP_S", 0.0)
    with client.websocket_connect(f"/api/matches/{DEMO}/replay", params={"speed": 60, "from": 3780}) as ws:
        ws.receive_json()
        ticks = []
        while not ticks or ticks[-1]["t"] < 3830:
            message = ws.receive_json()
            if message["type"] == "tick":
                ticks.append(message)

    labelled = {event_id: (m["t"], tags) for m in ticks for event_id, tags in m["new_tags"].items()}
    assert labelled[eid(1303)][1] == ["goal"]
    assert "key_pass" in labelled[eid(1301)][1]
    assert labelled[eid(1301)][0] == labelled[eid(1303)][0]  # revealed together with the shot
