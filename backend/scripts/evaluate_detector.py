"""Compare detector versions on the fixed seeds and on fresh seeds 300-309.

Seed history (see docs/PROGRESS.md):
- 100-109: development set (inspected while revising v1 -> v2)
- 200-209: v2 held-out test (now used up; it motivated v3)
- 300-309: fresh test set for the v2 vs v3 decision

Decision rule, fixed before running: v3 replaces v2 only if, on seeds 300-309,
its total errors (missed planted presses + false alerts, both scenarios) are
lower than v2's AND it still gets the fixed demo match exactly right.

Run from the backend folder (venv active):
    python -m scripts.evaluate_detector
"""

from app.detection.evaluation import evaluate_seeds
from app.detection.pressing import V2_RATIO, V3_RATE_TEST
from app.simulator import BALANCED, DEMO_HIGH_PRESS

FRESH_SEEDS = range(300, 310)


def report(label, results) -> tuple[int, int]:
    expected = sum(r.expected for r in results)
    detected = sum(r.detected for r in results)
    false_alerts = sum(len(r.false_alerts) for r in results)
    print(f"  {label}")
    for r in results:
        found = ", ".join(f"{a.team_id}@{a.first_detected_s / 60:.0f}'({a.confidence})" for a in r.alerts)
        print(f"    seed {r.seed:>3}: detected {r.detected}/{r.expected}, "
              f"false {len(r.false_alerts)}  alerts: {found or 'none'}")
    rate = f"{detected}/{expected}" if expected else "n/a"
    print(f"    TOTAL: detection {rate}, false alerts {false_alerts} in {len(results)} matches")
    return expected - detected, false_alerts


def main() -> None:
    totals = {}
    for config in (V2_RATIO, V3_RATE_TEST):
        print(f"\n=== {config.name} ===")
        demo_fixed = evaluate_seeds(DEMO_HIGH_PRESS, range(42, 43), config)
        report("Demo, fixed seed 42", demo_fixed)
        report("Balanced, fixed seed 7", evaluate_seeds(BALANCED, range(7, 8), config))
        missed_d, false_d = report("Demo, FRESH seeds 300-309",
                                   evaluate_seeds(DEMO_HIGH_PRESS, FRESH_SEEDS, config))
        missed_b, false_b = report("Balanced, FRESH seeds 300-309",
                                   evaluate_seeds(BALANCED, FRESH_SEEDS, config))
        demo_ok = demo_fixed[0].detected == 1 and not demo_fixed[0].false_alerts
        totals[config.name] = (missed_d + missed_b + false_d + false_b, demo_ok)
        print(f"  ERRORS on fresh seeds: {missed_d} missed + {false_d + false_b} false = "
              f"{totals[config.name][0]}; fixed demo exactly right: {demo_ok}")

    v2_errors, _ = totals[V2_RATIO.name]
    v3_errors, v3_demo_ok = totals[V3_RATE_TEST.name]
    winner = V3_RATE_TEST.name if (v3_errors < v2_errors and v3_demo_ok) else V2_RATIO.name
    print(f"\nDECISION (rule fixed in advance): keep {winner}")


if __name__ == "__main__":
    main()
