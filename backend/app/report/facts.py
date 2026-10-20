"""Full-time fact sheet: everything the post-match commentary may say, computed without AI.

Built only at full time from the same deterministic pieces the dashboard uses:
final totals, goal turning points, pressing alerts and a momentum summary per
15-minute block. Every number the Commentator may write is a ReportFact here.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.api import service
from app.api.insights import detection_facts

Unit = Literal["count", "percent", "per_min", "seconds", "ratio"]
BLOCK_MIN = 15
# Turnover zones are in the losing team's frame; the report speaks from the scorer's view.
WON_IN = {"defensive": "their attacking third", "middle": "the middle third", "final": "their own third"}
ON_TOP_THRESHOLD = 1.5  # mean momentum difference per minute needed to call a block for a team


class ReportFact(BaseModel):
    model_config = ConfigDict(frozen=True)

    fact_id: str
    label: str
    value: int | float  # counts and seconds are whole numbers, rates and % one decimal
    unit: Unit


class GoalSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    fact_prefix: str  # e.g. "G2": its numbers are G2.seconds and G2.passes
    minute: int
    team_name: str
    score_after: str  # "1-1", home first
    start: Literal["ball_won", "unknown"]  # unknown: the data does not record how the ball was won
    lost_by_name: str | None
    loser_under_pressure: bool | None  # the team that lost the ball was under pressure
    ball_won_in: Literal["their attacking third", "the middle third", "their own third"] | None  # scorer's view
    during_alert_by: str | None  # team whose press alert was active shortly before (timing only)


class AlertSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    fact_prefix: str  # e.g. "A1"
    kind: Literal["pressing increase"] = "pressing increase"  # from PULSE's pressing detector
    team_name: str
    opponent_name: str
    detected_minute: int
    confidence: Literal["moderate", "strong"]


class Phase(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_minute: int
    to_minute: int
    on_top: str | None  # team name, or None when even (momentum indicator, not a measurement)


class ReportFacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    match_id: str
    home_name: str
    away_name: str
    final_score: str  # "1-1", home first
    goals: list[GoalSummary]
    alerts: list[AlertSummary]
    phases: list[Phase]
    facts: list[ReportFact]

    def fact(self, fact_id: str) -> ReportFact | None:
        return next((f for f in self.facts if f.fact_id == fact_id), None)

    def context_numbers(self) -> set[float]:
        """Minutes, block bounds, window lengths and goals: allowed without a metric claim."""
        numbers = {float(n) for n in (1, 5, 15, 45, 46, 90)}  # windows and half bounds
        numbers |= {float(g.minute) for g in self.goals}
        numbers |= {float(a.detected_minute) for a in self.alerts}
        for p in self.phases:
            numbers |= {float(p.from_minute), float(p.to_minute)}
        for score in [self.final_score, *(g.score_after for g in self.goals)]:
            numbers |= {float(s) for s in score.split("-")}
        return numbers


def end_time(match_id: str) -> float:
    return service.load_match(match_id).events[-1].timestamp_seconds + 1


def build_report_facts(match_id: str) -> ReportFacts:
    match = service.load_match(match_id)
    home, away = service.teams_of(match)
    names = {home: match.home.name, away: match.away.name}
    end = end_time(match_id)
    state = service.state_at(match_id, end)
    facts: list[ReportFact] = []

    def add(fact_id: str, label: str, value: float | None, unit: Unit) -> None:
        if value is not None:
            shown = int(round(value)) if unit in ("count", "seconds") else round(value, 1)
            facts.append(ReportFact(fact_id=fact_id, label=label, value=shown, unit=unit))

    for team in (home, away):
        stats = state.totals.teams[team]
        n = names[team]
        add(f"{team}.possession", f"{n} estimated possession, whole match", stats.possession_share.value, "percent")
        add(f"{team}.pass_completion", f"{n} pass completion, whole match", stats.pass_completion.value, "percent")
        add(f"{team}.shots", f"{n} shots", stats.shots.value, "count")
        add(f"{team}.shots_on_target", f"{n} shots on target", stats.shots_on_target.value, "count")
        add(f"{team}.box_entries", f"{n} entries into the penalty box", stats.box_entries.value, "count")
        add(f"{team}.lost_under_pressure", f"{n} balls lost under pressure", stats.turnovers_under_pressure.value, "count")
        high = stats.high_pressures_per_min.value
        add(f"{team}.high_presses_per_min", f"{n} high presses per minute, whole match",
            None if high is None else round(high, 1), "per_min")

    def score_text(score: dict[str, int]) -> str:
        return f"{score.get(home, 0)}-{score.get(away, 0)}"

    alert_by_id = {}
    alerts: list[AlertSummary] = []
    for i, alert in enumerate(state.alerts, 1):
        prefix = f"A{i}"
        alert_by_id[alert.alert_id] = alert
        sheet = detection_facts(match_id, alert.alert_id)
        team, opp = names[alert.team_id], names[alert.opponent_id]
        for src, dst, label, unit in (
            ("S1.recent_count", "press_recent", f"{team} high presses in the 5 minutes before the alert", "count"),
            ("S1.baseline_count", "press_baseline", f"{team} high presses in the 15 minutes before that", "count"),
            ("S3.recent", "opp_pass_completion_recent",
             f"{opp} pass completion in the 5 minutes before the alert", "percent"),
            ("S3.baseline", "opp_pass_completion_baseline",
             f"{opp} pass completion in the 15 minutes before that", "percent"),
        ):
            f = sheet.fact(src)
            add(f"{prefix}.{dst}", label, None if f is None else f.value, unit)
        recent, base = sheet.fact("S1.recent_count"), sheet.fact("S1.baseline_count")
        if recent and base and recent.value and base.value:
            # Exact rate ratio: (recent / 5 min) / (baseline / 15 min) = 3 x recent / baseline.
            add(f"{prefix}.press_ratio", f"{team} high presses per minute, 5 minutes before the alert, "
                "as a multiple of the 15 minutes before that", 3 * recent.value / base.value, "ratio")
        alerts.append(AlertSummary(
            fact_prefix=prefix,
            team_name=names[alert.team_id], opponent_name=names[alert.opponent_id],
            detected_minute=sheet.detected_minute, confidence=sheet.confidence,
        ))

    goals: list[GoalSummary] = []
    for i, p in enumerate(service.turning_points_at(match_id, end), 1):
        prefix = f"G{i}"
        add(f"{prefix}.seconds", f"seconds from winning the ball to goal {i}" if p.turnover
            else f"seconds of the move before goal {i}", round(p.possession_duration_s), "seconds")
        add(f"{prefix}.passes", f"passes in the move before goal {i}", p.possession_passes, "count")
        related = [alert_by_id[a] for a in p.related_alert_ids if a in alert_by_id]
        goals.append(GoalSummary(
            fact_prefix=prefix,
            minute=int(p.timestamp_seconds // 60) + 1,
            team_name=names[p.team_id],
            score_after=score_text(p.score_after),
            start="ball_won" if p.possession_start == "turnover" else "unknown",
            lost_by_name=names[p.turnover.lost_by] if p.turnover else None,
            loser_under_pressure=p.turnover.under_pressure if p.turnover else None,
            ball_won_in=WON_IN[p.turnover.zone] if p.turnover else None,
            during_alert_by=names[related[0].team_id] if related else None,
        ))

    phases: list[Phase] = []
    for start in range(0, 90, BLOCK_MIN):
        diffs = [m.diff for m in state.momentum if start * 60 < m.end_s <= (start + BLOCK_MIN) * 60]
        mean = sum(diffs) / len(diffs) if diffs else 0.0
        on_top = names[home] if mean >= ON_TOP_THRESHOLD else names[away] if mean <= -ON_TOP_THRESHOLD else None
        phases.append(Phase(from_minute=start, to_minute=start + BLOCK_MIN, on_top=on_top))

    return ReportFacts(
        match_id=match_id, home_name=names[home], away_name=names[away],
        final_score=score_text(state.score), goals=goals, alerts=alerts, phases=phases, facts=facts,
    )


CASUAL_FACTS = 4


def audience_view(facts: ReportFacts, audience: str) -> ReportFacts:
    """Fans get a pre-selected sheet of at most 4 statistics: per goal the seconds to goal (or the
    passes when we don't know how the ball was won), then per alert how many times more often the
    team pressed. The code picks the numbers; the agent only words them. Analysts get everything."""
    if audience != "casual":
        return facts
    picked: list[str] = []
    for g in facts.goals:
        picked.append(f"{g.fact_prefix}.seconds" if g.start == "ball_won" else f"{g.fact_prefix}.passes")
    picked += [f"{a.fact_prefix}.press_ratio" for a in facts.alerts]
    keep = [f for fid in picked[:CASUAL_FACTS] if (f := facts.fact(fid)) is not None]
    return facts.model_copy(update={"facts": keep})
