"""Rules-based "pressing increase" signals.

For a pressing team P and its opponent O, compare the last 5 minutes
("recent") with the 15 minutes before that ("baseline"):

  S1  P presses more (two versions, chosen by DetectorConfig):
        v2 "ratio":     high pressures/min >= 2x baseline AND >= 1.0/min
        v3 "rate_test": the rise in high pressures would happen by chance < 1% of
                        the time if P's pressing rate had not changed (one-sided
                        conditional binomial test on the two counts)
  S2  O loses the ball under it: >= 3 turnovers under pressure AND rate >= 2x baseline
  S3  O's build-up suffers:      pass completion drops >= 8 points (>= 10 passes in both windows)

A minute "qualifies" when S1 passes AND at least one of S2 / S3 passes. S1 is
required because an alert claiming "P is pressing more" must rest on P's own
pressing; S2 and S3 are its consequences and largely overlap (one misplaced
pass under pressure moves both), so they cannot confirm each other alone.
The engine (engine.py) only raises an alert after consecutive qualifying
minutes.

Revision history (see docs/PROGRESS.md): v1 used "any 2 of 3" and produced
25 false alerts in 10 balanced matches on development seeds 100-109. v2 made
S1 required and missed the targets on held-out seeds 200-209. v3 replaced
S1's fixed ratio with a rate test; on fresh seeds 300-309 it was more
conservative but missed the fixed demo, so v2 remains the default
(scripts/evaluate_detector.py).
"""

from dataclasses import dataclass
from math import comb
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict

from app.schema import Event, PressureEvent
from app.stats import WindowStats
from app.stats.metrics import HIGH_PRESS_MIN_X

RECENT_S = 300.0
BASELINE_S = 900.0
MIN_BASELINE_S = 600.0  # do not assess until there are 10 minutes of baseline

PRESSURE_RATIO = 2.0
MIN_HIGH_PRESSURES_PER_MIN = 1.0
MIN_TURNOVERS_UNDER_PRESSURE = 3
TURNOVER_RATIO = 2.0
PASS_DROP_POINTS = 8.0
MIN_PASSES = 10
RATE_TEST_ALPHA = 0.01


@dataclass(frozen=True)
class DetectorConfig:
    name: str
    s1_method: Literal["ratio", "rate_test"]
    persistence: int  # consecutive qualifying minutes before alerting


V2_RATIO = DetectorConfig(name="v2-ratio", s1_method="ratio", persistence=4)
V3_RATE_TEST = DetectorConfig(name="v3-rate-test", s1_method="rate_test", persistence=4)
# v2 kept by the decision rule fixed before the seeds 300-309 comparison: v3 had fewer
# total errors (6 vs 11) but missed the fixed demo match, which the rule required.
DEFAULT_CONFIG = V2_RATIO


def rate_increase_p_value(n_recent: int, t_recent: float, n_base: int, t_base: float) -> float:
    """Chance of seeing >= n_recent of all events in the recent window if the rate never changed.

    Given n = n_recent + n_base events, under "no change" each event falls in the
    recent window with probability t_recent / (t_recent + t_base), so n_recent is
    Binomial(n, p). Returns P(X >= n_recent); 1.0 when there are no events.
    """
    n = n_recent + n_base
    if n == 0:
        return 1.0
    p = t_recent / (t_recent + t_base)
    tail = sum(comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(n_recent, n + 1))
    return min(1.0, tail)


class SignalCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_id: str
    description: str
    team_id: str  # whose metric this is
    metric_id: str  # key into app.stats.DEFINITIONS
    unit: str
    baseline_value: float | None
    recent_value: float | None
    baseline_sample_size: int
    recent_sample_size: int
    passed: bool
    p_value: float | None = None  # set when the signal uses the rate test


class PressingAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    pressing_team: str
    opponent: str
    at_s: float
    recent_window: tuple[float, float]
    baseline_window: tuple[float, float]
    signals: list[SignalCheck]
    evidence_event_ids: list[str]

    @property
    def passed_count(self) -> int:
        return sum(s.passed for s in self.signals)

    @property
    def qualifies(self) -> bool:
        s1, s2, s3 = self.signals
        return s1.passed and (s2.passed or s3.passed)


def windows_at(at_s: float) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """(recent, baseline) windows ending at `at_s`, or None if the baseline is too short."""
    recent_start = at_s - RECENT_S
    baseline_start = max(0.0, recent_start - BASELINE_S)
    if recent_start - baseline_start < MIN_BASELINE_S:
        return None
    return (recent_start, at_s), (baseline_start, recent_start)


def _per_min(count: float, window: tuple[float, float]) -> float:
    return round(count / ((window[1] - window[0]) / 60), 2)


def assess_pressing(
    events: Sequence[Event],
    pressing_team: str,
    opponent: str,
    recent: WindowStats,
    baseline: WindowStats,
    config: DetectorConfig = DEFAULT_CONFIG,
) -> PressingAssessment:
    recent_w = (recent.start_s, recent.end_s)
    baseline_w = (baseline.start_s, baseline.end_s)
    p_recent, p_base = recent.teams[pressing_team], baseline.teams[pressing_team]
    o_recent, o_base = recent.teams[opponent], baseline.teams[opponent]

    # S1: the pressing team's high pressures per minute.
    hp_recent = p_recent.high_pressures_per_min.value or 0.0
    hp_base = p_base.high_pressures_per_min.value or 0.0
    n_recent = p_recent.high_pressures_per_min.sample_size
    n_base = p_base.high_pressures_per_min.sample_size
    p_value = None
    if config.s1_method == "rate_test":
        p_value = rate_increase_p_value(
            n_recent, recent_w[1] - recent_w[0], n_base, baseline_w[1] - baseline_w[0]
        )
        s1_passed = p_value < RATE_TEST_ALPHA
    else:
        s1_passed = hp_recent >= MIN_HIGH_PRESSURES_PER_MIN and hp_recent >= PRESSURE_RATIO * hp_base
    s1 = SignalCheck(
        signal_id="S1",
        description=f"{pressing_team} high pressures per minute",
        team_id=pressing_team,
        metric_id="high_pressures_per_min",
        unit="per_min",
        baseline_value=hp_base,
        recent_value=hp_recent,
        baseline_sample_size=n_base,
        recent_sample_size=n_recent,
        passed=s1_passed,
        p_value=None if p_value is None else round(p_value, 4),
    )

    # S2: the opponent's turnovers under pressure, compared as rates per minute.
    to_recent_n = int(o_recent.turnovers_under_pressure.value or 0)
    to_base_n = int(o_base.turnovers_under_pressure.value or 0)
    to_recent, to_base = _per_min(to_recent_n, recent_w), _per_min(to_base_n, baseline_w)
    s2 = SignalCheck(
        signal_id="S2",
        description=f"{opponent} turnovers under pressure per minute",
        team_id=opponent,
        metric_id="turnovers_under_pressure",
        unit="per_min",
        baseline_value=to_base,
        recent_value=to_recent,
        baseline_sample_size=to_base_n,
        recent_sample_size=to_recent_n,
        passed=to_recent_n >= MIN_TURNOVERS_UNDER_PRESSURE and to_recent >= TURNOVER_RATIO * to_base,
    )

    # S3: the opponent's pass completion; unavailable with too few passes.
    pc_recent, pc_base = o_recent.pass_completion, o_base.pass_completion
    enough_passes = pc_recent.sample_size >= MIN_PASSES and pc_base.sample_size >= MIN_PASSES
    s3 = SignalCheck(
        signal_id="S3",
        description=f"{opponent} pass completion (%)",
        team_id=opponent,
        metric_id="pass_completion",
        unit="percent",
        baseline_value=pc_base.value,
        recent_value=pc_recent.value,
        baseline_sample_size=pc_base.sample_size,
        recent_sample_size=pc_recent.sample_size,
        passed=enough_passes and pc_recent.value <= pc_base.value - PASS_DROP_POINTS,
    )

    # Evidence: the pressing team's high pressures and the opponent's
    # turnovers under pressure inside the recent window, in match order.
    evidence: set[str] = {
        e.event_id
        for e in events
        if isinstance(e, PressureEvent)
        and e.team_id == pressing_team
        and e.start_x >= HIGH_PRESS_MIN_X
        and recent_w[0] <= e.timestamp_seconds < recent_w[1]
    }
    for turnover in recent.turnovers:
        if turnover.lost_by == opponent and turnover.under_pressure:
            evidence.update(turnover.evidence_event_ids)
    # Keep evidence strictly inside the assessed window (a ball-winning event can
    # land a second after the window closes).
    by_id = {e.event_id: e for e in events}
    evidence = {i for i in evidence if recent_w[0] <= by_id[i].timestamp_seconds < recent_w[1]}
    order = {e.event_id: i for i, e in enumerate(events)}

    return PressingAssessment(
        pressing_team=pressing_team,
        opponent=opponent,
        at_s=recent.end_s,
        recent_window=recent_w,
        baseline_window=baseline_w,
        signals=[s1, s2, s3],
        evidence_event_ids=sorted(evidence, key=order.__getitem__),
    )
