"""Scripted synthetic match scenarios and their ground-truth labels.

Teams, players, and results are fictional. Times are match-clock seconds
(60 s = 1 minute; 3300 s = 55:00).
"""

from dataclasses import replace

from .generator import Phase, Scenario, ScriptedGoal, ScriptedSubstitution, TeamSpec, TeamStyle

NORTHBRIDGE = TeamSpec(team_id="NBR", name="Northbridge FC", short_name="NBR", name_offset=0)
EASTVALE = TeamSpec(team_id="EAS", name="Eastvale Athletic", short_name="EAS", name_offset=13)

# --- Team styles --------------------------------------------------------------

# Northbridge: patient, possession-heavy build-up.
NBR_BASE = TeamStyle(pass_success=0.86, progression=5.5, carry_rate=0.2, shot_rate=0.12,
                     press_rate=0.08, high_press_rate=0.05)
# Eastvale: more direct, mid-block by default.
EAS_BASE = TeamStyle(pass_success=0.79, progression=7.5, carry_rate=0.25, shot_rate=0.14,
                     press_rate=0.10, high_press_rate=0.05)
# Short pressing burst that fades (false alarm).
EAS_BURST = replace(EAS_BASE, press_rate=0.15, high_press_rate=0.35)
# Sustained high press (the planted tactical shift).
EAS_HIGH_PRESS = replace(EAS_BASE, press_rate=0.18, high_press_rate=0.50)
# Closing minutes: slower, safer, fewer chances.
NBR_LOW = replace(NBR_BASE, progression=4.0, shot_rate=0.07, press_rate=0.05, high_press_rate=0.0,
                  tempo=1.6)
EAS_LOW = replace(EAS_BASE, progression=4.0, shot_rate=0.07, press_rate=0.05, high_press_rate=0.0,
                  tempo=1.6)

COMMON_LIMITATIONS = [
    "Synthetic data: patterns exist because they were planted, not discovered.",
    "No player-tracking data: pressing is approximated from pressure events and turnover locations.",
    "Simplified event set: no throw-ins, goal kicks, offsides, or aerial duels.",
    "Open-play shots are never goals; all goals are scripted sequences.",
]

# --- Demo match: high-press turning point --------------------------------------

DEMO_HIGH_PRESS = Scenario(
    match_id="demo-high-press",
    scenario="high_press_turning_point",
    seed=42,
    home=NORTHBRIDGE,
    away=EASTVALE,
    phases=(
        Phase(0, "baseline", NBR_BASE, EAS_BASE),
        Phase(1200, "false_alarm_burst", NBR_BASE, EAS_BURST),
        Phase(1380, "normal_play", NBR_BASE, EAS_BASE),
        Phase(3300, "eastvale_high_press", NBR_BASE, EAS_HIGH_PRESS),
        Phase(4200, "normal_play", NBR_BASE, EAS_BASE),
        Phase(4800, "low_activity", NBR_LOW, EAS_LOW, dead_time_s=(15.0, 30.0)),
    ),
    goals=(
        ScriptedGoal(2040, "home", "patient_possession"),  # ~34'
        ScriptedGoal(3780, "away", "high_turnover"),  # ~63', during the high press
    ),
    substitutions=(
        ScriptedSubstitution(3600, "home", out_number=10, in_number=14),
        ScriptedSubstitution(4200, "away", out_number=11, in_number=19),
        ScriptedSubstitution(4500, "home", out_number=9, in_number=19),
    ),
    labels={
        "tactical_shifts": [
            {
                "kind": "pressing_increase",
                "team_id": "EAS",
                "start_s": 3300,
                "end_s": 4200,
                "description": "Eastvale presses high; Northbridge build-up is disrupted.",
            }
        ],
        "false_alarms": [
            {
                "kind": "pressing_burst",
                "team_id": "EAS",
                "start_s": 1200,
                "end_s": 1380,
                "description": "Three-minute pressing burst that fades; should NOT trigger an alert.",
            }
        ],
        "low_activity": [{"start_s": 4800, "end_s": 5400}],
        "expected_alerts": [
            {"kind": "pressing_increase", "team_id": "EAS", "earliest_s": 3300, "latest_s": 3900}
        ],
        "limitations": COMMON_LIMITATIONS,
    },
)

# --- Balanced match: no tactical shift (false-alarm control) ---------------------

BALANCED_STYLE = TeamStyle(pass_success=0.82, progression=6.5, carry_rate=0.22, shot_rate=0.13,
                           press_rate=0.10, high_press_rate=0.06)

BALANCED = Scenario(
    match_id="balanced",
    scenario="balanced_no_shift",
    seed=7,
    home=NORTHBRIDGE,
    away=EASTVALE,
    phases=(Phase(0, "balanced", BALANCED_STYLE, BALANCED_STYLE),),
    goals=(
        ScriptedGoal(1500, "away", "patient_possession"),  # ~25'
        ScriptedGoal(4100, "home", "patient_possession"),  # ~68'
    ),
    substitutions=(
        ScriptedSubstitution(3900, "home", out_number=10, in_number=14),
        ScriptedSubstitution(4300, "away", out_number=9, in_number=19),
    ),
    labels={
        "tactical_shifts": [],
        "false_alarms": [],
        "low_activity": [],
        "expected_alerts": [],
        "limitations": COMMON_LIMITATIONS,
    },
)

SCENARIOS = {s.match_id: s for s in (DEMO_HIGH_PRESS, BALANCED)}
