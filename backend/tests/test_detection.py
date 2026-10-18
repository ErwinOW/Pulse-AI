"""Tests for the pressing-increase detector (backend/app/detection).

Ground truth comes from the scenario labels, not from the detector's output.
"""

from functools import cache

import pytest

from app.detection import detect_alerts
from app.detection.evaluation import evaluate, evaluate_seeds
from app.detection.pressing import rate_increase_p_value
from app.simulator import BALANCED, DEMO_HIGH_PRESS, generate
from app.stats import DEFINITIONS

TEAMS = ("NBR", "EAS")
FULL_MATCH_S = 6000.0


@cache
def demo():
    return generate(DEMO_HIGH_PRESS)


@cache
def demo_alerts():
    match, _ = demo()
    return detect_alerts(match.events, TEAMS, FULL_MATCH_S)


# --- Fixed demo and balanced matches ------------------------------------------------


def test_demo_detects_the_planted_press_once():
    match, truth = demo()
    result = evaluate(match, truth)

    assert result.detected == result.expected == 1
    assert result.false_alerts == []


def test_demo_alert_is_eastvale_within_labelled_window():
    _, truth = demo()
    (alert,) = demo_alerts()
    expected = truth["expected_alerts"][0]

    assert alert.team_id == "EAS" and alert.opponent_id == "NBR"
    assert expected["earliest_s"] <= alert.first_detected_s <= expected["latest_s"]


def test_no_alert_during_false_alarm_or_low_activity():
    _, truth = demo()
    quiet = [(f["start_s"], f["end_s"] + 300) for f in truth["false_alarms"]]
    quiet += [(w["start_s"], w["end_s"]) for w in truth["low_activity"]]

    for alert in demo_alerts():
        for start, end in quiet:
            assert not start <= alert.first_detected_s <= end


# Known limitation, kept visible rather than deleted. strict=True: if this starts
# passing, the test fails so the documented numbers get updated.
@pytest.mark.xfail(strict=True, reason="v2 known limitation: 2 false alerts on balanced seed 7 "
                   "(NBR at 54' and 78'); see docs/PROGRESS.md")
def test_balanced_match_raises_no_alerts():
    match, truth = generate(BALANCED)

    assert evaluate(match, truth).alerts == []


# --- Alert content ----------------------------------------------------------------


def test_alert_evidence_exists_and_supports_the_claim():
    match, _ = demo()
    (alert,) = demo_alerts()
    by_id = {e.event_id: e for e in match.events}

    assert alert.evidence_event_ids
    evidence = [by_id[i] for i in alert.evidence_event_ids]  # KeyError if any id is invented
    assert any(e.event_type == "pressure" and e.team_id == "EAS" for e in evidence)
    assert any(e.event_type in ("pass", "tackle") for e in evidence)  # lost balls
    for e in evidence:
        assert alert.onset_s <= e.timestamp_seconds < alert.last_confirmed_s


def test_alert_signals_are_documented_and_sufficient():
    (alert,) = demo_alerts()

    s1, s2, s3 = alert.signals  # from the latest confirmation, so they qualified
    assert s1.passed and (s2.passed or s3.passed)
    assert alert.confidence in ("moderate", "strong")
    for signal in alert.signals:
        assert signal.metric_id in DEFINITIONS


def test_alert_is_updated_not_repeated_while_press_lasts():
    (alert,) = demo_alerts()

    # The press is labelled 55'-70'; one alert should cover several confirmed minutes.
    assert alert.last_confirmed_s - alert.first_detected_s >= 180


def test_rewind_gives_consistent_alerts():
    match, _ = demo()
    (full,) = demo_alerts()
    rewound = detect_alerts(match.events, TEAMS, until_s=full.first_detected_s + 120)

    assert len(rewound) == 1
    assert rewound[0].first_detected_s == full.first_detected_s
    assert set(rewound[0].evidence_event_ids) <= set(full.evidence_event_ids)


def test_no_alerts_before_baseline_exists():
    match, _ = demo()

    assert detect_alerts(match.events, TEAMS, until_s=899) == []


# --- Rate test -------------------------------------------------------------------


def test_rate_test_p_value_matches_hand_calculation():
    # 5 pressures in the last 5 min, none in the previous 15: all 5 events fall in a
    # window holding 25% of the time -> 0.25 ** 5.
    assert rate_increase_p_value(5, 300, 0, 900) == pytest.approx(0.25**5)
    # 2 recent vs 6 baseline is exactly the "no change" rate: P(X >= 2), X ~ Bin(8, 0.25).
    assert rate_increase_p_value(2, 300, 6, 900) == pytest.approx(
        1 - 0.75**8 - 8 * 0.25 * 0.75**7
    )


def test_rate_test_with_no_events_is_not_significant():
    assert rate_increase_p_value(0, 300, 0, 900) == 1.0


# --- Generalisation: fresh seeds 300-309 -------------------------------------------
# Seeds 100-109 (development) and 200-209 (v2 held-out) have been inspected and
# are no longer a fair test. Seeds 300-309 decided v2 vs v3 (v2 kept) and are
# the final reported test set for the default detector.
# Acceptance limits were fixed before the first run and must not be loosened.

HELD_OUT_SEEDS = range(300, 310)


@pytest.fixture(scope="module")
def unseen_demo():
    return evaluate_seeds(DEMO_HIGH_PRESS, HELD_OUT_SEEDS)


@pytest.fixture(scope="module")
def unseen_balanced():
    return evaluate_seeds(BALANCED, HELD_OUT_SEEDS)


def test_detection_rate_on_unseen_demo_seeds(unseen_demo):
    detected = sum(r.detected for r in unseen_demo)

    assert detected >= 8, f"detected {detected}/10"


@pytest.mark.xfail(strict=True, reason="v2 known limitation: 4 false alerts in 10 balanced "
                   "matches on seeds 300-309 (target <= 2); see docs/PROGRESS.md")
def test_false_alerts_on_unseen_balanced_seeds(unseen_balanced):
    false_alerts = sum(len(r.false_alerts) for r in unseen_balanced)

    assert false_alerts <= 2, f"{false_alerts} false alerts in 10 balanced matches"


@pytest.mark.xfail(strict=True, reason="v2 known limitation: 6 false alerts in 10 demo-scenario "
                   "matches on seeds 300-309 (target <= 3), 3 of them during the 20'-23' "
                   "pressing burst; see docs/PROGRESS.md")
def test_false_alerts_on_unseen_demo_seeds(unseen_demo):
    false_alerts = sum(len(r.false_alerts) for r in unseen_demo)

    assert false_alerts <= 3, f"{false_alerts} false alerts in 10 demo-scenario matches"
