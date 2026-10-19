"""Build the verified fact sheet an insight narrative may use.

The fact sheet is the ONLY input the Storyteller sees, and the reference the
validator checks against. Everything in it is computed by deterministic code.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.detection import Alert
from app.detection.pressing import windows_at
from app.schema import Match
from app.stats import score

Unit = Literal["per_min", "percent", "count"]

# What the sample size of each signal counts.
COUNT_LABELS = {
    "high_pressures_per_min": "high pressures",
    "turnovers_under_pressure": "turnovers under pressure",
    "pass_completion": "passes attempted",
}


def match_minute(seconds: float) -> int:
    """Football convention: 61:30 on the clock is the 62nd minute."""
    return int(seconds // 60) + 1


class MetricFact(BaseModel):
    model_config = ConfigDict(frozen=True)

    fact_id: str  # e.g. "S1.recent", "S1.recent_count"
    label: str
    metric_id: str  # key into app.stats.DEFINITIONS
    team_id: str
    window_start_s: float
    window_end_s: float
    value: float | None  # None = unavailable
    unit: Unit


class InsightFacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    insight_id: str
    kind: Literal["pressing_increase"]
    team_id: str
    team_name: str
    opponent_id: str
    opponent_name: str
    onset_minute: int
    detected_minute: int
    last_confirmed_minute: int
    recent_window_minutes: int
    baseline_window_minutes: int
    score: dict[str, int]  # team_id -> goals at detection time
    confidence: Literal["moderate", "strong"]
    sample_note: str | None
    signals_met: list[str]  # human-readable names of the signals that passed
    facts: list[MetricFact]
    evidence_event_ids: list[str]

    def fact(self, fact_id: str) -> MetricFact | None:
        return next((f for f in self.facts if f.fact_id == fact_id), None)


def facts_from_alert(match: Match, alert: Alert) -> InsightFacts:
    windows = windows_at(alert.last_confirmed_s)
    if windows is None:  # cannot happen for a raised alert; guard anyway
        raise ValueError(f"alert {alert.alert_id} has no assessable window")
    recent_w, baseline_w = windows
    names = {match.home.team_id: match.home.name, match.away.team_id: match.away.name}

    facts: list[MetricFact] = []
    for signal in alert.signals:
        for part, window, value, count in (
            ("baseline", baseline_w, signal.baseline_value, signal.baseline_sample_size),
            ("recent", recent_w, signal.recent_value, signal.recent_sample_size),
        ):
            span = f"{part} window, minutes {match_minute(window[0])}-{match_minute(window[1]) - 1}"
            common = {"metric_id": signal.metric_id, "team_id": signal.team_id,
                      "window_start_s": window[0], "window_end_s": window[1]}
            facts.append(MetricFact(fact_id=f"{signal.signal_id}.{part}", unit=signal.unit,
                                    label=f"{signal.description} ({span})", value=value, **common))
            facts.append(MetricFact(
                fact_id=f"{signal.signal_id}.{part}_count", unit="count",
                label=f"{names[signal.team_id]} {COUNT_LABELS[signal.metric_id]} ({span})",
                value=count, **common))

    return InsightFacts(
        insight_id=alert.alert_id,
        kind=alert.kind,
        team_id=alert.team_id,
        team_name=names[alert.team_id],
        opponent_id=alert.opponent_id,
        opponent_name=names[alert.opponent_id],
        onset_minute=match_minute(alert.onset_s),
        detected_minute=match_minute(alert.first_detected_s),
        last_confirmed_minute=match_minute(alert.last_confirmed_s),
        recent_window_minutes=round((recent_w[1] - recent_w[0]) / 60),
        baseline_window_minutes=round((baseline_w[1] - baseline_w[0]) / 60),
        score=score(match.events, (match.home.team_id, match.away.team_id), alert.first_detected_s),
        confidence=alert.confidence,
        sample_note=alert.sample_note,
        signals_met=[s.description for s in alert.signals if s.passed],
        facts=facts,
        evidence_event_ids=alert.evidence_event_ids,
    )
