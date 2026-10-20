"""Key-event labels: which events are worth showing in the "Key events" feed.

Every event stays in the data (statistics and the detector need routine passes);
these labels only decide what the UI highlights. All rules are deterministic.

Some labels depend on what happened next (a pass is only a key pass once the
shot happens), so every label has `revealed_s`: the time of the latest event it
depends on. At match time t, only labels with revealed_s < t are visible, which
keeps the feed free of future information.
"""

from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict

from app.schema import Event, PassEvent, ShotEvent

from .metrics import _is_box_entry
from .turnovers import find_turnovers

KeyTag = Literal[
    "goal",  # shot that scored
    "shot",  # any other shot
    "key_pass",  # completed pass to the player who then shot
    "box_entry",  # pass or carry from outside into the penalty box
    "ball_won_high",  # ball won in the opponent's defensive third
    "lost_under_pressure",  # ball lost while under pressure
    "winning_press",  # pressure shortly before the pressing team won the ball
    "foul",
    "substitution",
    "period",  # kick-off, half-time, full-time
]

KEY_PASS_LOOKBACK_S = 20.0
WINNING_PRESS_LOOKBACK_S = 5.0
_CONTROL_TYPES = {"pass", "carry", "shot", "interception", "ball_recovery", "tackle"}


class KeyEventTag(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    tag: KeyTag
    revealed_s: float  # visible only for match times after this


def key_event_tags(events: Sequence[Event], team_ids: tuple[str, str]) -> list[KeyEventTag]:
    tags: list[KeyEventTag] = []

    def add(event: Event, tag: KeyTag, revealed_s: float | None = None) -> None:
        tags.append(KeyEventTag(event_id=event.event_id, tag=tag,
                                revealed_s=event.timestamp_seconds if revealed_s is None else revealed_s))

    for i, e in enumerate(events):
        if isinstance(e, ShotEvent):
            add(e, "goal" if e.outcome == "goal" else "shot")
            # Key pass: walk back through the shooting team's possession to the last pass.
            for prev in reversed(events[max(0, i - 15):i]):
                if e.timestamp_seconds - prev.timestamp_seconds > KEY_PASS_LOOKBACK_S:
                    break
                team = getattr(prev, "team_id", None)
                if team != e.team_id:
                    if prev.event_type in _CONTROL_TYPES:
                        break  # opponent had the ball: no key pass in this possession
                    continue
                if isinstance(prev, PassEvent):
                    if prev.outcome == "complete" and prev.recipient_id == e.player_id:
                        add(prev, "key_pass", revealed_s=e.timestamp_seconds)
                    break
        elif _is_box_entry(e):
            add(e, "box_entry")
        elif e.event_type == "foul":
            add(e, "foul")
        elif e.event_type == "substitution":
            add(e, "substitution")
        elif e.event_type in ("period_start", "period_end"):
            add(e, "period")

    by_id = {e.event_id: e for e in events}
    pressures = [e for e in events if e.event_type == "pressure"]
    for turnover in find_turnovers(events, team_ids):
        loser = by_id[turnover.evidence_event_ids[0]]
        winner = by_id[turnover.evidence_event_ids[-1]]
        won_at = winner.timestamp_seconds
        if turnover.under_pressure and loser is not winner:
            add(loser, "lost_under_pressure", revealed_s=won_at)
        if turnover.zone == "defensive":  # the loser's defensive third = the winner's final third
            add(winner, "ball_won_high", revealed_s=won_at)
            for p in pressures:
                if p.team_id == turnover.won_by and won_at - WINNING_PRESS_LOOKBACK_S <= p.timestamp_seconds <= won_at:
                    add(p, "winning_press", revealed_s=won_at)

    return sorted(tags, key=lambda tag: (tag.revealed_s, tag.event_id, tag.tag))


def visible_tags(tags: Sequence[KeyEventTag], t: float) -> dict[str, list[str]]:
    """event_id -> labels visible at match time t."""
    out: dict[str, list[str]] = {}
    for tag in tags:
        if tag.revealed_s < t and tag.tag not in out.get(tag.event_id, []):
            out.setdefault(tag.event_id, []).append(tag.tag)
    return out
