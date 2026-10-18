"""Run detectors minute by minute and manage alerts.

Rules:
- An alert is raised only after PERSISTENCE consecutive qualifying minutes.
- While a shift continues, the existing alert is UPDATED (not duplicated).
- If qualification lapses, the alert goes inactive; it is reactivated if the
  shift returns within QUIET_S, otherwise a new alert is created.

Detection is recomputed from the events up to `until_s`, so rewinding the
match is just calling detect_alerts with an earlier time.
"""

from typing import Literal, Sequence

from pydantic import BaseModel

from app.schema import Event
from app.stats import compute_window, find_turnovers

from .pressing import (
    DEFAULT_CONFIG,
    DetectorConfig,
    PressingAssessment,
    SignalCheck,
    assess_pressing,
    windows_at,
)

STEP_S = 60.0
# Persistence (consecutive qualifying minutes before alerting) lives in
# DetectorConfig. v1 used 2, which a 3-minute pressing burst could satisfy;
# "sustained" now means at least 4 minutes.
QUIET_S = 300.0  # minutes without qualification before a fresh alert is allowed
SMALL_SAMPLE_PASSES = 15
SMALL_SAMPLE_TURNOVERS = 5


class Alert(BaseModel):
    alert_id: str
    kind: Literal["pressing_increase"]
    team_id: str
    opponent_id: str
    title: str
    direction: Literal["increase"] = "increase"
    onset_s: float  # start of the recent window when first detected
    first_detected_s: float
    last_confirmed_s: float
    active: bool
    confidence: Literal["moderate", "strong"]
    signals: list[SignalCheck]  # from the latest confirmation
    evidence_event_ids: list[str]  # accumulated across confirmations, in match order
    sample_note: str | None


def _sample_note(assessment: PressingAssessment) -> str | None:
    s2, s3 = assessment.signals[1], assessment.signals[2]
    if s3.recent_sample_size < SMALL_SAMPLE_PASSES or s2.recent_sample_size < SMALL_SAMPLE_TURNOVERS:
        return (
            f"Small sample in the last 5 minutes: {s3.recent_sample_size} passes and "
            f"{s2.recent_sample_size} turnovers under pressure by {assessment.opponent}."
        )
    return None


def _apply(alert: Alert, assessment: PressingAssessment, order: dict[str, int]) -> None:
    alert.last_confirmed_s = assessment.at_s
    alert.active = True
    alert.signals = assessment.signals
    alert.confidence = "strong" if assessment.passed_count == 3 else "moderate"
    alert.sample_note = _sample_note(assessment)
    merged = set(alert.evidence_event_ids) | set(assessment.evidence_event_ids)
    alert.evidence_event_ids = sorted(merged, key=order.__getitem__)


def detect_alerts(
    events: Sequence[Event],
    team_ids: tuple[str, str],
    until_s: float,
    config: DetectorConfig = DEFAULT_CONFIG,
) -> list[Alert]:
    """All alerts raised from kick-off up to `until_s`, using only events before `until_s`."""
    events = [e for e in events if e.timestamp_seconds < until_s]
    turnovers = find_turnovers(events, team_ids)
    order = {e.event_id: i for i, e in enumerate(events)}
    opponent = {team_ids[0]: team_ids[1], team_ids[1]: team_ids[0]}

    alerts: list[Alert] = []
    latest: dict[str, Alert] = {}
    streak = {team_id: 0 for team_id in team_ids}

    t = STEP_S
    while t <= until_s:
        windows = windows_at(t)
        if windows is not None:
            recent_w, baseline_w = windows
            recent = compute_window(events, team_ids, *recent_w, all_turnovers=turnovers)
            baseline = compute_window(events, team_ids, *baseline_w, all_turnovers=turnovers)

            for team_id in team_ids:
                assessment = assess_pressing(
                    events, team_id, opponent[team_id], recent, baseline, config
                )
                streak[team_id] = streak[team_id] + 1 if assessment.qualifies else 0
                alert = latest.get(team_id)

                if streak[team_id] >= config.persistence:
                    if alert is None or t - alert.last_confirmed_s > QUIET_S:
                        alert = Alert(
                            alert_id=f"pressing_increase-{team_id}-{len(alerts) + 1}",
                            kind="pressing_increase",
                            team_id=team_id,
                            opponent_id=opponent[team_id],
                            title=f"{team_id} pressing increase",
                            onset_s=assessment.recent_window[0],
                            first_detected_s=t,
                            last_confirmed_s=t,
                            active=True,
                            confidence="moderate",
                            signals=[],
                            evidence_event_ids=[],
                            sample_note=None,
                        )
                        alerts.append(alert)
                        latest[team_id] = alert
                    _apply(alert, assessment, order)
                elif alert is not None and not assessment.qualifies:
                    alert.active = False
        t += STEP_S

    return alerts
