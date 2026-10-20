"""WebSocket replay: streams a committed match in time order.

Server -> client messages:
  {"type": "control", "t", "speed", "paused", "duration_s"}  on connect and after every command
  {"type": "tick", "t", "minute", "period", "score", "events", "new_alerts", "new_tags"}  while playing
     (new_tags: key-event labels revealed in this tick, possibly for events sent earlier,
      e.g. a pass becomes a key pass when the shot happens)
  {"type": "end", "t", "score"}  when the final whistle is reached (replay pauses, seek still works)
  {"type": "error", "detail"}
Client -> server: {"action": "pause" | "play"}, {"action": "seek", "t": 3600},
                  {"action": "speed", "value": 20}

Ticks are light (only what is new since the last tick). After a "control"
message the client re-fetches /state?t= for the full picture; the same
endpoint is the polling fallback when a host blocks WebSockets.
"""

import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from . import service

TICK_S = 0.25  # real seconds between ticks; match time advances speed * TICK_S per tick
TICK_SLEEP_S = TICK_S  # tests set this to 0 to run without waiting
MIN_SPEED, MAX_SPEED = 1.0, 60.0


def tick_payload(match_id: str, prev_t: float, t: float) -> dict:
    """Everything that happened in [prev_t, t), plus the clock and score at t."""
    match = service.load_match(match_id)
    teams = service.teams_of(match)
    events = service.events_before(match, t)
    new_events = events[len(service.events_before(match, prev_t)):]
    # Alerts are visible from the whole minute they were raised (as in /state).
    alerts, _ = service._minute_products(match_id, float(int(t // 60) * 60))
    seen_until = float(int(prev_t // 60) * 60)
    new_tags: dict[str, list[str]] = {}
    for tag in service.key_tags(match_id):
        if prev_t <= tag.revealed_s < t and tag.tag not in new_tags.get(tag.event_id, []):
            new_tags.setdefault(tag.event_id, []).append(tag.tag)
    return {
        "type": "tick",
        "t": t,
        "minute": service.match_minute(t),
        "period": next((e.period for e in reversed(events) if e.event_type == "period_start"), None),
        "score": service.score(events, teams, t),
        "events": [e.model_dump(mode="json") for e in new_events],
        "new_alerts": [a.model_dump(mode="json") for a in alerts if a.first_detected_s > seen_until],
        "new_tags": new_tags,
    }


async def run_replay(websocket: WebSocket, match_id: str, speed: float, start_t: float) -> None:
    await websocket.accept()
    try:
        match = service.load_match(match_id)
    except KeyError:
        await websocket.send_json({"type": "error", "detail": f"unknown match {match_id!r}"})
        await websocket.close(code=4404)
        return

    end_t = match.events[-1].timestamp_seconds + 1
    state = {"t": min(start_t, end_t), "speed": speed, "paused": False}
    commands: asyncio.Queue = asyncio.Queue()

    async def control() -> None:
        await websocket.send_json({"type": "control", "t": state["t"], "speed": state["speed"],
                                   "paused": state["paused"], "duration_s": end_t - 1})

    async def read_commands() -> None:
        while True:
            try:
                await commands.put(await websocket.receive_json())
            except ValueError:  # not JSON
                await commands.put(None)

    def apply(command) -> str | None:
        """Apply a client command; returns an error message if it is invalid."""
        action = command.get("action") if isinstance(command, dict) else None
        if action in ("pause", "play"):
            state["paused"] = action == "pause"
        elif action == "seek" and isinstance(command.get("t"), (int, float)) and command["t"] >= 0:
            state["t"] = min(float(command["t"]), end_t)
        elif action == "speed" and isinstance(command.get("value"), (int, float)) \
                and MIN_SPEED <= command["value"] <= MAX_SPEED:
            state["speed"] = float(command["value"])
        else:
            return f"invalid command {command!r}"
        return None

    reader = asyncio.create_task(read_commands())
    try:
        await control()
        while True:
            await asyncio.sleep(TICK_SLEEP_S)
            if reader.done():  # client disconnected (or sent non-JSON)
                return
            while not commands.empty():
                error = apply(commands.get_nowait())
                if error:
                    await websocket.send_json({"type": "error", "detail": error})
                else:
                    await control()
            if state["paused"]:
                continue

            prev_t = state["t"]
            state["t"] = min(prev_t + state["speed"] * TICK_S, end_t)
            await websocket.send_json(tick_payload(match_id, prev_t, state["t"]))
            if state["t"] >= end_t:
                state["paused"] = True
                await websocket.send_json({"type": "end", "t": state["t"],
                                           "score": service.score(match.events, service.teams_of(match), end_t)})
    except WebSocketDisconnect:
        return
    except Exception:
        if reader.done():  # sending raced with the client closing
            return
        raise
    finally:
        reader.cancel()
        if reader.done() and not reader.cancelled():
            reader.exception()  # mark the disconnect as handled
