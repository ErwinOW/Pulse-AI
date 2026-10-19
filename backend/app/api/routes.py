"""HTTP routes for matches and match state."""

from fastapi import APIRouter, HTTPException, Query

from app.stats import DEFINITIONS

from . import service

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


@router.get("/definitions")
def get_definitions() -> dict[str, str]:
    """How every displayed metric is calculated (shown in the UI)."""
    return DEFINITIONS
