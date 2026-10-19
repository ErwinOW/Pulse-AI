"""Match data service: loads committed fixtures and computes the match state at any time t.

Every state uses only events before t, so live replay, rewind and jumps are
consistent by construction. Alerts and momentum change only on whole match
minutes (the detector steps every 60 s), so they are computed for the last
completed minute and cached per (match, minute).
"""

from bisect import bisect_left
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.detection import Alert, detect_alerts
from app.narrative import match_minute
from app.schema import Match
from app.stats import (
    GoalTurningPoint,
    WindowStats,
    compute_window,
    goal_turning_points,
    rolling_windows,
    score,
)

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "matches"
RECENT_EVENTS = 30
STATS_WINDOW_S = 300.0
ALERT_LINK_S = 600.0  # alerts confirmed within 10 minutes before a goal are linked (timing only)


class TeamInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    team_id: str
    name: str
    short_name: str


class MatchSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    match_id: str
    home: TeamInfo
    away: TeamInfo
    duration_s: float
    is_synthetic: bool


class MomentumPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    end_s: float
    home: float
    away: float
    diff: float  # home - away (indicator, not a measurement)


class MatchState(BaseModel):
    match_id: str
    t: float
    minute: int
    period: int | None
    score: dict[str, int]
    recent_events: list[dict]  # newest last
    window: WindowStats  # last 5 minutes before t
    totals: WindowStats  # kick-off to t
    momentum: list[MomentumPoint]  # per completed minute
    alerts: list[Alert]  # raised by the last completed minute


@lru_cache(maxsize=None)
def load_match(match_id: str) -> Match:
    path = DATA_DIR / f"{match_id}.json"
    if not path.exists() or path.name.endswith(".ground_truth.json"):
        raise KeyError(match_id)
    return Match.model_validate_json(path.read_text(encoding="utf-8"))


def list_match_ids() -> list[str]:
    return sorted(p.stem for p in DATA_DIR.glob("*.json") if not p.name.endswith(".ground_truth.json"))


def summary(match: Match) -> MatchSummary:
    def info(team) -> TeamInfo:
        return TeamInfo(team_id=team.team_id, name=team.name, short_name=team.short_name)

    return MatchSummary(
        match_id=match.match_id, home=info(match.home), away=info(match.away),
        duration_s=match.events[-1].timestamp_seconds, is_synthetic=match.is_synthetic,
    )


def teams_of(match: Match) -> tuple[str, str]:
    return match.home.team_id, match.away.team_id


def events_before(match: Match, t: float) -> list:
    timestamps = [e.timestamp_seconds for e in match.events]
    return match.events[: bisect_left(timestamps, t)]


@lru_cache(maxsize=4096)
def _minute_products(match_id: str, minute_end_s: float) -> tuple[list[Alert], list[MomentumPoint]]:
    match = load_match(match_id)
    teams = teams_of(match)
    events = events_before(match, minute_end_s)
    alerts = detect_alerts(events, teams, minute_end_s) if minute_end_s > 0 else []
    momentum = [
        MomentumPoint(
            end_s=w.end_s,
            home=w.teams[teams[0]].momentum.value,
            away=w.teams[teams[1]].momentum.value,
            diff=w.teams[teams[0]].momentum.value - w.teams[teams[1]].momentum.value,
        )
        for w in rolling_windows(events, teams, minute_end_s)
    ]
    return alerts, momentum


def state_at(match_id: str, t: float) -> MatchState:
    match = load_match(match_id)
    teams = teams_of(match)
    events = events_before(match, t)
    period = next((e.period for e in reversed(events) if e.event_type == "period_start"), None)
    alerts, momentum = _minute_products(match_id, float(int(t // 60) * 60))

    return MatchState(
        match_id=match_id,
        t=t,
        minute=match_minute(t),
        period=period,
        score=score(events, teams, t),
        recent_events=[e.model_dump(mode="json") for e in events[-RECENT_EVENTS:]],
        window=compute_window(events, teams, max(0.0, t - STATS_WINDOW_S), t),
        totals=compute_window(events, teams, 0.0, t),
        momentum=momentum,
        alerts=alerts,
    )


def turning_points_at(match_id: str, t: float) -> list[GoalTurningPoint]:
    """Goals before t, each linked to alerts that were known and active shortly before it.

    The link is a timing link only; it does not claim the alert caused the goal.
    """
    match = load_match(match_id)
    points = goal_turning_points(events_before(match, t), teams_of(match))
    linked = []
    for p in points:
        alerts, _ = _minute_products(match_id, float(int(p.timestamp_seconds // 60) * 60))
        ids = [a.alert_id for a in alerts if a.last_confirmed_s >= p.timestamp_seconds - ALERT_LINK_S]
        linked.append(p.model_copy(update={"related_alert_ids": ids}))
    return linked
