"""Phase-based possession-chain simulator.

A team keeps the ball through a chain of passes and carries until the chain
ends in a turnover, a shot, or the ball going out. Each match phase sets
per-team style parameters (pass success, pressing, progression...), so a
tactical shift is produced by changing parameters at a scripted time rather
than by hand-writing events.

Honesty rules baked in:
- Goals happen ONLY in scripted sequences (open-play shots are never goals),
  so the scoreline is part of the documented scenario, not random luck.
- The output is validated by the Match schema before it is returned.
- Everything is driven by one seeded RNG: same scenario + seed -> same match.

Coordinates follow the schema convention: each event is in the acting team's
frame (attacking towards x = 100). The opponent's frame is the mirror image.
"""

import random
from dataclasses import dataclass, field
from typing import Literal

from app.schema import Match

Side = Literal["home", "away"]

PERIOD_ENDS_S = {1: 2700.0, 2: 5400.0}
PRESS_PENALTY = 0.30  # drop in pass completion when the passer is under pressure
TACKLE_RATE_UNDER_PRESSURE = 0.3  # chance a pressured carry is tackled
FOUL_RATE = 0.06  # chance a pressure event turns into a foul
OUT_OF_PLAY_RATE = 0.03  # chance a pass goes out of play
MAX_ACTIONS_PER_CHAIN = 30

# Likelihood of each position being on the ball by zone (own third, middle, final third).
ZONE_WEIGHTS = {
    "GK": (0.4, 0.0, 0.0),
    "DEF": (3.0, 1.0, 0.3),
    "MID": (2.0, 3.0, 2.0),
    "FWD": (0.3, 1.0, 3.0),
}


@dataclass(frozen=True)
class TeamStyle:
    pass_success: float = 0.82  # completion probability without pressure
    progression: float = 6.0  # mean metres-equivalent (0-100 scale) gained per pass
    carry_rate: float = 0.2  # share of actions that are carries
    shot_rate: float = 0.22  # chance of shooting per action once x >= 78
    press_rate: float = 0.10  # chance this team pressures an opponent action anywhere
    high_press_rate: float = 0.05  # extra chance when the opponent is in its own half
    tempo: float = 1.0  # multiplier on seconds per action (higher = slower)


@dataclass(frozen=True)
class Phase:
    start_s: float
    label: str
    home: TeamStyle
    away: TeamStyle
    dead_time_s: tuple[float, float] = (6.0, 20.0)  # stoppage after out / shot


@dataclass(frozen=True)
class ScriptedGoal:
    time_s: float  # inserted at the first chain boundary at or after this time
    side: Side
    build_up: Literal["high_turnover", "patient_possession"]


@dataclass(frozen=True)
class ScriptedSubstitution:
    time_s: float
    side: Side
    out_number: int
    in_number: int


@dataclass(frozen=True)
class TeamSpec:
    team_id: str
    name: str
    short_name: str
    name_offset: int  # picks a different slice of the fictional name pools


@dataclass(frozen=True)
class Scenario:
    match_id: str
    scenario: str
    seed: int
    home: TeamSpec
    away: TeamSpec
    phases: tuple[Phase, ...]
    goals: tuple[ScriptedGoal, ...] = ()
    substitutions: tuple[ScriptedSubstitution, ...] = ()
    labels: dict = field(default_factory=dict)  # ground-truth labels known up front


# --- Fictional squads -------------------------------------------------------

FIRST_NAMES = [
    "Aaron", "Bram", "Callum", "Dario", "Elias", "Felix", "Gideon", "Hugo", "Ivo", "Jonas",
    "Kian", "Luca", "Mateo", "Niko", "Oskar", "Pavel", "Rafael", "Soren", "Teo", "Viktor",
    "Wim", "Yusuf", "Zeno", "Adrian", "Benji", "Cyrus", "Dorian", "Emil",
]
LAST_NAMES = [
    "Ashdown", "Brennick", "Corvale", "Dunmore", "Elstree", "Fenwright", "Garrow", "Halsey",
    "Inglet", "Jarrow", "Kestley", "Lowden", "Marlow", "Norcott", "Oakham", "Pellow",
    "Quarry", "Rendle", "Stowell", "Thorne", "Upworth", "Varley", "Wexcombe", "Yardley",
    "Ambrey", "Brooksby", "Calder", "Delling",
]
# (shirt number, position); the first 11 start, the last 3 are substitutes.
SQUAD_LAYOUT = [
    (1, "GK"), (2, "DEF"), (3, "DEF"), (4, "DEF"), (5, "DEF"), (6, "MID"), (7, "MID"),
    (8, "MID"), (10, "MID"), (9, "FWD"), (11, "FWD"), (12, "DEF"), (14, "MID"), (19, "FWD"),
]
STARTERS = 11


def player_id(team_id: str, number: int) -> str:
    return f"{team_id}-{number:02d}"


def build_team(spec: TeamSpec) -> dict:
    n = len(FIRST_NAMES)
    return {
        "team_id": spec.team_id,
        "name": spec.name,
        "short_name": spec.short_name,
        "players": [
            {
                "player_id": player_id(spec.team_id, number),
                "name": f"{FIRST_NAMES[(i * 7 + spec.name_offset) % n]} "
                f"{LAST_NAMES[(i * 11 + spec.name_offset) % n]}",
                "shirt_number": number,
                "position": position,
            }
            for i, (number, position) in enumerate(SQUAD_LAYOUT)
        ],
    }


# --- Helpers -----------------------------------------------------------------


def _other(side: Side) -> Side:
    return "away" if side == "home" else "home"


def _clip(value: float, low: float = 1.0, high: float = 99.0) -> float:
    return round(min(max(value, low), high), 1)


def _mirror(x: float, y: float) -> tuple[float, float]:
    """Convert a location into the opponent's attacking frame."""
    return round(100 - x, 1), round(100 - y, 1)


class _Generator:
    def __init__(self, scenario: Scenario):
        self.sc = scenario
        self.rng = random.Random(scenario.seed)
        self.t = 0.0
        self.events: list[dict] = []
        self.teams = {"home": build_team(scenario.home), "away": build_team(scenario.away)}
        self.team_id = {side: self.teams[side]["team_id"] for side in ("home", "away")}
        self.on_pitch = {side: list(self.teams[side]["players"][:STARTERS]) for side in self.teams}
        self.pending_goals = sorted(scenario.goals, key=lambda g: g.time_s)
        self.pending_subs = sorted(scenario.substitutions, key=lambda s: s.time_s)
        self.goal_records: list[dict] = []

    # -- low-level ------------------------------------------------------------

    def _phase(self) -> Phase:
        current = self.sc.phases[0]
        for phase in self.sc.phases:
            if phase.start_s <= self.t:
                current = phase
        return current

    def _style(self, side: Side) -> TeamStyle:
        phase = self._phase()
        return phase.home if side == "home" else phase.away

    def _emit(self, event_type: str, period: int, dt: float, **fields) -> str:
        # Every emitted event advances the clock by >= 0.5 s, so timestamps are strictly increasing.
        self.t = round(self.t + dt, 1)
        event_id = f"{self.sc.match_id}-e{len(self.events) + 1:04d}"
        self.events.append(
            {
                "event_id": event_id,
                "match_id": self.sc.match_id,
                "period": period,
                "timestamp_seconds": self.t,
                "event_type": event_type,
                **fields,
            }
        )
        return event_id

    def _action_dt(self, side: Side) -> float:
        return self.rng.uniform(1.5, 4.0) * self._style(side).tempo

    def _pick(self, side: Side, x: float, exclude: str | None = None) -> str:
        zone = 0 if x < 35 else 1 if x < 70 else 2
        players = [p for p in self.on_pitch[side] if p["player_id"] != exclude]
        weights = [ZONE_WEIGHTS[p["position"]][zone] for p in players]
        return self.rng.choices(players, weights=weights)[0]["player_id"]

    def _pass(self, side, period, x, y, end_x, end_y, outcome, under_pressure=False, player=None):
        player = player or self._pick(side, x)
        fields = {
            "team_id": self.team_id[side], "player_id": player,
            "start_x": x, "start_y": y, "end_x": end_x, "end_y": end_y,
            "outcome": outcome, "under_pressure": under_pressure,
        }
        if outcome == "complete":
            fields["recipient_id"] = self._pick(side, end_x, exclude=player)
        return self._emit("pass", period, self._action_dt(side), **fields)

    # -- open play --------------------------------------------------------------

    def _play_chain(self, side: Side, x: float, y: float, period: int, holder: str | None):
        """Play one possession.

        `holder` is the player who already has the ball (e.g. after winning it back),
        or None for a dead-ball restart. Returns ((next_side, x, y, next_holder), ball_went_dead).
        """
        opp = _other(side)
        for action in range(MAX_ACTIONS_PER_CHAIN):
            att, dfn = self._style(side), self._style(opp)
            holder = holder or self._pick(side, x)

            press_chance = dfn.press_rate + (dfn.high_press_rate if x < 50 else 0.0)
            pressured = self.rng.random() < press_chance
            presser = None
            if pressured:
                presser = self._pick(opp, 100 - x)
                px, py = _mirror(x, y)
                self._emit("pressure", period, self.rng.uniform(0.5, 1.5),
                           team_id=self.team_id[opp], player_id=presser, start_x=px, start_y=py)
                if self.rng.random() < FOUL_RATE:
                    card = "yellow" if self.rng.random() < 0.12 else None
                    self._emit("foul", period, 0.5, team_id=self.team_id[opp], player_id=presser,
                               start_x=px, start_y=py, card=card)
                    self.t += self.rng.uniform(5, 12)  # free kick taken; attacker keeps the ball
                    continue

            # Shot
            if x >= 78 and self.rng.random() < att.shot_rate:
                outcome = self.rng.choices(["saved", "off_target", "blocked"], weights=[35, 40, 25])[0]
                self._emit("shot", period, self._action_dt(side), team_id=self.team_id[side],
                           player_id=holder, start_x=x, start_y=y,
                           outcome=outcome, under_pressure=pressured)
                return (opp, 8.0, _clip(self.rng.uniform(30, 70)), None), True

            # Carry
            if self.rng.random() < att.carry_rate:
                if presser and self.rng.random() < TACKLE_RATE_UNDER_PRESSURE:
                    tx, ty = _mirror(x, y)
                    self._emit("tackle", period, self._action_dt(side), team_id=self.team_id[opp],
                               player_id=presser, start_x=tx, start_y=ty, outcome="won")
                    return (opp, tx, ty, presser), False
                end_x = _clip(x + self.rng.uniform(3, 10))
                end_y = _clip(y + self.rng.gauss(0, 6))
                self._emit("carry", period, self._action_dt(side), team_id=self.team_id[side],
                           player_id=holder, start_x=x, start_y=y,
                           end_x=end_x, end_y=end_y, under_pressure=pressured)
                x, y = end_x, end_y
                continue

            # Pass
            success = att.pass_success - (PRESS_PENALTY if pressured else 0.0)
            if action == MAX_ACTIONS_PER_CHAIN - 1:
                success = 0.0  # safety valve: end overly long chains
            end_x = _clip(x + self.rng.gauss(att.progression, 8))
            end_y = _clip(y + self.rng.gauss(0, 15))
            roll = self.rng.random()

            if roll < success:
                self._pass(side, period, x, y, end_x, end_y, "complete", pressured, holder)
                holder = self.events[-1]["recipient_id"]
                x, y = end_x, end_y
                continue

            if roll < success + OUT_OF_PLAY_RATE:
                end_y = 0.0 if end_y < 50 else 100.0
                self._pass(side, period, x, y, end_x, end_y, "out", pressured, holder)
                rx, ry = _mirror(end_x, end_y)
                return (opp, rx, _clip(ry, 2, 98), None), True

            self._pass(side, period, x, y, end_x, end_y, "incomplete", pressured, holder)
            rx, ry = _mirror(end_x, end_y)
            kind = "interception" if self.rng.random() < 0.4 else "ball_recovery"
            winner = self._pick(opp, rx)
            self._emit(kind, period, self.rng.uniform(0.5, 1.5), team_id=self.team_id[opp],
                       player_id=winner, start_x=rx, start_y=ry)
            return (opp, rx, ry, winner), False

        raise AssertionError("unreachable: the last action always ends the chain")

    # -- scripted moments -------------------------------------------------------

    def _substitute(self, sub: ScriptedSubstitution, period: int) -> None:
        team_id = self.team_id[sub.side]
        out_id, in_id = player_id(team_id, sub.out_number), player_id(team_id, sub.in_number)
        incoming = next(p for p in self.teams[sub.side]["players"] if p["player_id"] == in_id)
        self.on_pitch[sub.side] = [p for p in self.on_pitch[sub.side] if p["player_id"] != out_id]
        self.on_pitch[sub.side].append(incoming)
        self._emit("substitution", period, self.rng.uniform(5, 10), team_id=team_id,
                   player_out_id=out_id, player_in_id=in_id)

    def _scripted_goal(self, goal: ScriptedGoal, period: int) -> None:
        side, opp = goal.side, _other(goal.side)
        first_event_index = len(self.events)

        if goal.build_up == "high_turnover":
            # Opponent builds up from the back, is pressed, and loses the ball in midfield.
            self._pass(opp, period, 22.0, 40.0, 30.0, 55.0, "complete")
            victim = self.events[-1]["recipient_id"]
            self._emit("pressure", period, 1.0, team_id=self.team_id[side],
                       player_id=self._pick(side, 70), start_x=70.0, start_y=45.0)
            self._pass(opp, period, 30.0, 55.0, 38.0, 50.0, "incomplete", True, player=victim)
            self._emit("ball_recovery", period, 1.0, team_id=self.team_id[side],
                       player_id=self._pick(side, 62), start_x=62.0, start_y=50.0)
            recoverer = self.events[-1]["player_id"]
            self._pass(side, period, 62.0, 50.0, 76.0, 42.0, "complete", player=recoverer)
            carrier = self.events[-1]["recipient_id"]
            self._emit("carry", period, 2.5, team_id=self.team_id[side], player_id=carrier,
                       start_x=76.0, start_y=42.0, end_x=84.0, end_y=48.0)
            shooter, sx, sy = carrier, 86.0, 50.0
        else:  # patient_possession
            route = [(25, 50), (38, 30), (52, 25), (64, 40), (75, 55), (83, 52)]
            passer = None
            for (x0, y0), (x1, y1) in zip(route, route[1:]):
                self._pass(side, period, float(x0), float(y0), float(x1), float(y1), "complete",
                           player=passer)
                passer = self.events[-1]["recipient_id"]
            shooter, sx, sy = passer, 87.0, 50.0

        goal_id = self._emit("shot", period, 2.0, team_id=self.team_id[side], player_id=shooter,
                             start_x=sx, start_y=sy, outcome="goal")
        self.goal_records.append(
            {
                "event_id": goal_id,
                "team_id": self.team_id[side],
                "timestamp_seconds": self.t,
                "build_up": goal.build_up,
                "sequence_event_ids": [e["event_id"] for e in self.events[first_event_index:]],
            }
        )

    def _run_due_scripts(self, period: int):
        """Run substitutions and goals whose time has come. Returns a restart if a goal was scored."""
        period_end = PERIOD_ENDS_S[period]
        while self.pending_subs and self.pending_subs[0].time_s <= self.t:
            self._substitute(self.pending_subs.pop(0), period)
        if self.pending_goals and self.pending_goals[0].time_s <= min(self.t, period_end):
            goal = self.pending_goals.pop(0)
            self._scripted_goal(goal, period)
            self.t += self.rng.uniform(40, 60)  # celebration before kick-off
            return _other(goal.side), 50.0, 50.0, None
        return None

    # -- whole match -------------------------------------------------------------

    def run(self) -> tuple[Match, dict]:
        for period, kickoff_side in ((1, "home"), (2, "away")):
            if period == 2:
                self.t = max(self.t, PERIOD_ENDS_S[1])  # second half cannot start before 45:00
            self._emit("period_start", period, 0.5 if self.events else 0.0)
            restart = (kickoff_side, 50.0, 50.0, None)

            # Stop starting new possessions shortly before the period ends;
            # a possession in progress may run on a little (stoppage time).
            while self.t < PERIOD_ENDS_S[period] - 15:
                restart = self._run_due_scripts(period) or restart
                side, x, y, holder = restart
                if holder not in {p["player_id"] for p in self.on_pitch[side]}:
                    holder = None  # the ball carrier was just substituted off
                restart, ball_dead = self._play_chain(side, x, y, period, holder)
                if ball_dead:
                    self.t += self.rng.uniform(*self._phase().dead_time_s)

            self._emit("period_end", period, 1.0)

        match = Match.model_validate(
            {
                "match_id": self.sc.match_id,
                "home": self.teams["home"],
                "away": self.teams["away"],
                "events": self.events,
            }
        )
        ground_truth = {
            "match_id": self.sc.match_id,
            "scenario": self.sc.scenario,
            "seed": self.sc.seed,
            "is_synthetic": True,
            **self.sc.labels,
            "goals": self.goal_records,
        }
        return match, ground_truth


def generate(scenario: Scenario) -> tuple[Match, dict]:
    """Generate a validated synthetic match and its ground-truth labels."""
    return _Generator(scenario).run()
