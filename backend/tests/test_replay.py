"""Tests for the WebSocket replay stream (backend/app/api/replay.py)."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import replay, service
from app.main import app

client = TestClient(app)
DEMO = "demo-high-press"


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(replay, "TICK_SLEEP_S", 0.0)


def connect(match_id=DEMO, **params):
    return client.websocket_connect(f"/api/matches/{match_id}/replay", params=params)


def read_until(ws, kind, limit=2000):
    """All messages up to and including the first one of `kind`."""
    messages = []
    for _ in range(limit):
        messages.append(ws.receive_json())
        if messages[-1]["type"] == kind:
            return messages
    raise AssertionError(f"no {kind!r} message in {limit} messages")


def test_stream_from_60_minutes_to_full_time_is_complete_ordered_and_has_no_future():
    match = service.load_match(DEMO)
    start = 3700.0
    with connect(speed=60, **{"from": start}) as ws:
        hello = ws.receive_json()
        messages = read_until(ws, "end")

    assert hello["type"] == "control" and hello["t"] == start and hello["paused"] is False
    ticks = [m for m in messages if m["type"] == "tick"]
    streamed = [e["event_id"] for m in ticks for e in m["events"]]
    expected = [e.event_id for e in match.events if e.timestamp_seconds >= start]
    assert streamed == expected  # every event once, in order
    assert all(e["timestamp_seconds"] < m["t"] for m in ticks for e in m["events"])
    assert messages[-1]["score"] == {"NBR": 1, "EAS": 1}


def test_alert_and_equaliser_each_appear_once_at_the_right_time():
    with connect(speed=60, **{"from": 3600}) as ws:
        ws.receive_json()
        ticks = [m for m in read_until(ws, "end") if m["type"] == "tick"]

    alert_ticks = [m for m in ticks if m["new_alerts"]]
    assert len(alert_ticks) == 1
    assert [a["alert_id"] for a in alert_ticks[0]["new_alerts"]] == ["pressing_increase-EAS-1"]
    assert alert_ticks[0]["t"] >= alert_ticks[0]["new_alerts"][0]["first_detected_s"]

    goal_ticks = [m for m in ticks if any(e.get("outcome") == "goal" for e in m["events"])]
    assert len(goal_ticks) == 1 and goal_ticks[0]["score"] == {"NBR": 1, "EAS": 1}


def test_pause_seek_and_play():
    with connect(speed=60) as ws:
        ws.receive_json()
        ws.send_json({"action": "pause"})
        paused = read_until(ws, "control")[-1]
        assert paused["paused"] is True

        ws.send_json({"action": "seek", "t": 1000})
        seeked = ws.receive_json()  # paused: nothing else arrives in between
        assert seeked == {"type": "control", "t": 1000.0, "speed": 60.0, "paused": True,
                          "duration_s": seeked["duration_s"]}

        ws.send_json({"action": "speed", "value": 20})
        assert ws.receive_json()["speed"] == 20.0
        ws.send_json({"action": "play"})
        assert ws.receive_json()["paused"] is False
        tick = ws.receive_json()

    assert tick["type"] == "tick" and tick["t"] == 1005.0  # 20x speed * 0.25 s tick
    assert all(1000 <= e["timestamp_seconds"] < 1005 for e in tick["events"])


def test_invalid_commands_get_an_error_and_the_stream_continues():
    with connect(speed=60) as ws:
        ws.receive_json()
        ws.send_json({"action": "pause"})
        read_until(ws, "control")
        for bad in ({"action": "rewind"}, {"action": "speed", "value": 500}, {"action": "seek", "t": -5}):
            ws.send_json(bad)
            assert ws.receive_json()["type"] == "error"
        ws.send_text("not json")
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"action": "play"})
        assert ws.receive_json()["type"] == "control"


def test_unknown_match_gets_an_error_then_close():
    with connect("nope") as ws:
        assert ws.receive_json()["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 4404


def test_out_of_range_speed_is_rejected():
    with pytest.raises(WebSocketDisconnect):
        with connect(speed=0) as ws:
            ws.receive_json()
