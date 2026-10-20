"""HTTP routes for matches and match state."""

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket

from app.narrative.schema import Audience, Language
from app.narrative.storyteller import Storyteller
from app.stats import DEFINITIONS

from . import replay, service
from .insights import (
    InsightError,
    InsightResponse,
    InsightService,
    detection_facts,
    get_insight_service,
    get_storyteller,
)

router = APIRouter(prefix="/api")


def _match_or_404(match_id: str):
    try:
        return service.load_match(match_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown match {match_id!r}") from None


@router.get("/matches", response_model=list[service.MatchSummary])
def list_matches() -> list[service.MatchSummary]:
    return [service.summary(service.load_match(m)) for m in service.list_match_ids()]


@router.get("/matches/{match_id}", response_model=service.MatchSummary)
def get_match(match_id: str) -> service.MatchSummary:
    return service.summary(_match_or_404(match_id))


@router.get("/matches/{match_id}/state", response_model=service.MatchState)
def get_state(match_id: str, t: float = Query(ge=0, description="Match clock in seconds")) -> service.MatchState:
    match = _match_or_404(match_id)
    duration = match.events[-1].timestamp_seconds
    return service.state_at(match_id, min(t, duration + 1))


@router.get("/matches/{match_id}/turning-points", response_model=list[service.GoalTurningPoint])
def get_turning_points(
    match_id: str, t: float = Query(ge=0, description="Match clock in seconds")
) -> list[service.GoalTurningPoint]:
    match = _match_or_404(match_id)
    duration = match.events[-1].timestamp_seconds
    return service.turning_points_at(match_id, min(t, duration + 1))


def _facts_or_404(match_id: str, alert_id: str, t: float | None):
    _match_or_404(match_id)
    try:
        return detection_facts(match_id, alert_id, t)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no alert {alert_id!r} by this time") from None


@router.get("/matches/{match_id}/insights/{alert_id}", response_model=InsightResponse)
async def get_insight(
    match_id: str,
    alert_id: str,
    audience: Audience = "casual",
    language: Language = "en",
    t: float | None = Query(None, ge=0, description="Match clock; 404 if the alert is not raised yet"),
    insights: InsightService = Depends(get_insight_service),
) -> InsightResponse:
    """Cached validated AI text, or the labelled deterministic fallback. Never calls the model."""
    return await insights.get(_facts_or_404(match_id, alert_id, t), audience, language)


@router.post("/matches/{match_id}/insights/{alert_id}/regenerate", response_model=InsightResponse)
async def regenerate_insight(
    match_id: str,
    alert_id: str,
    audience: Audience = "casual",
    language: Language = "en",
    insights: InsightService = Depends(get_insight_service),
    storyteller: Storyteller | None = Depends(get_storyteller),
) -> InsightResponse:
    """Live write -> validate -> retry -> fallback; one at a time, capped per day."""
    facts = _facts_or_404(match_id, alert_id, None)
    try:
        return await insights.regenerate(facts, audience, language, storyteller)
    except InsightError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None


@router.websocket("/matches/{match_id}/replay")
async def replay_match(
    websocket: WebSocket,
    match_id: str,
    speed: float = Query(10.0, ge=replay.MIN_SPEED, le=replay.MAX_SPEED),
    start: float = Query(0.0, ge=0, alias="from"),
) -> None:
    """Live replay stream; see app/api/replay.py for the message protocol."""
    await replay.run_replay(websocket, match_id, speed, start)


@router.get("/definitions")
def get_definitions() -> dict[str, str]:
    """How every displayed metric is calculated (shown in the UI)."""
    return DEFINITIONS
