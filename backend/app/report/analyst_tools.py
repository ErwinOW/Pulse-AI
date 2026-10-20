"""Analyst tools: what the "Ask the analyst" agent may look up about one finished match.

Read-only, this match only, full-time data, no AI. Every tool returns plain English sentences that
say who did what (never raw fields: in the live check the model read `loser_under_pressure` as
the scorers being under pressure). Every number a tool shows goes into the question's fact
ledger; the answer checker only accepts numbers from that ledger, minutes and scores.

One MatchTools per question, so the ledger only holds what the agent looked up for it.
"""

from typing import Annotated

from agent_framework import tool
from pydantic import BaseModel, ConfigDict

from app.api import service
from app.api.insights import detection_facts
from app.stats import compute_window

from .facts import end_time

MAX_KEY_EVENTS = 15
BASE_CONTEXT = (0, 1, 5, 15, 45, 46, 90)  # half and window bounds, allowed in any answer
# Turnover zones are in the losing team's frame (attacking towards x = 100).
LOSER_ZONE = {"defensive": "{loser}'s own third", "middle": "the middle third", "final": "{loser}'s attacking third"}
TAG_TEXT = {
    "goal": "scored a goal",
    "shot": "shot",
    "key_pass": "made the pass that set up a shot",
    "box_entry": "got into the penalty box",
    "ball_won_high": "won the ball high up the pitch",
    "lost_under_pressure": "lost the ball under pressure",
    "winning_press": "pressed just before their team won the ball back",
    "foul": "committed a foul",
    "substitution": "made a substitution",
}


class LedgerFact(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float
    label: str


def plural(count: str, one: str, many: str) -> str:
    return f"{count} {one if count == '1' else many}"


def minute_of(seconds: float) -> int:
    return int(seconds // 60) + 1


class MatchTools:
    def __init__(self, match_id: str):
        self.match_id = match_id
        self.match = service.load_match(match_id)
        self.home, self.away = service.teams_of(self.match)
        self.names = {self.home: self.match.home.name, self.away: self.match.away.name}
        self.players = {p.player_id: p.name for team in (self.match.home, self.match.away) for p in team.players}
        self.end_s = end_time(match_id)
        final = service.state_at(match_id, self.end_s).score
        self.final_score = f"{final.get(self.home, 0)}-{final.get(self.away, 0)}"
        self.ledger: list[LedgerFact] = []
        self.context: set[float] = {float(n) for n in BASE_CONTEXT} | {float(n) for n in final.values()}
        self.calls: list[str] = []  # shown to the user as "Looked at: ..."

    def _n(self, value: float, label: str) -> str:
        """Record a number in the ledger and return it as text (whole numbers stay whole)."""
        shown = int(value) if float(value).is_integer() else round(value, 1)
        self.ledger.append(LedgerFact(value=shown, label=label))
        return str(shown)

    def _minute(self, minute: int) -> str:
        self.context.add(float(minute))
        return f"{minute}'"

    # --- tools -------------------------------------------------------------------------------

    def team_stats(self, from_minute: int, to_minute: int) -> str:
        if not (0 <= from_minute < to_minute <= 90):
            return "Minutes must satisfy 0 <= from_minute < to_minute <= 90 (90 means full time)."
        self.calls.append(f"team_stats {from_minute}'-{to_minute}'")
        self.context |= {float(from_minute), float(to_minute)}
        end_s = self.end_s if to_minute == 90 else to_minute * 60.0
        window = compute_window(self.match.events, (self.home, self.away), from_minute * 60.0, end_s)
        until = "full time" if to_minute == 90 else f"{to_minute}:00"
        lines = [f"Statistics from {from_minute}:00 to {until} of the match clock:"]
        for team in (self.home, self.away):
            s, name = window.teams[team], self.names[team]
            parts = []
            if s.possession_share.value is not None:
                parts.append(f"estimated possession {self._n(s.possession_share.value, f'{name} possession %')}%")
            if s.pass_completion.value is not None:
                parts.append(f"{self._n(s.pass_completion.value, f'{name} pass completion %')}% of "
                             f"{self._n(s.pass_completion.sample_size, f'{name} passes')} passes completed")
            parts.append(f"{self._n(s.shots.value, f'{name} shots')} shots, "
                         f"{self._n(s.shots_on_target.value, f'{name} shots on target')} on target")
            parts.append(f"{self._n(s.box_entries.value, f'{name} box entries')} entries into the penalty box")
            parts.append(f"lost the ball under pressure "
                         f"{self._n(s.turnovers_under_pressure.value, f'{name} balls lost under pressure')} times")
            parts.append(f"{self._n(s.high_pressures_per_min.sample_size, f'{name} high presses')} high presses "
                         "(pressure in the opponent's build-up area)")
            lines.append(f"- {name}: " + "; ".join(parts) + ".")
        return "\n".join(lines)

    def goals(self) -> str:
        self.calls.append("goals")
        points = service.turning_points_at(self.match_id, self.end_s)
        if not points:
            return f"There were no goals. Final score {self.final_score}."
        alert_teams = {a.alert_id: self.names[a.team_id] for a in service.state_at(self.match_id, self.end_s).alerts}
        lines = []
        for i, p in enumerate(points, 1):
            scorer = self.names[p.team_id]
            after = f"{p.score_after.get(self.home, 0)}-{p.score_after.get(self.away, 0)}"
            self.context |= {float(v) for v in p.score_after.values()}
            text = f"Goal {i}, {self._minute(minute_of(p.timestamp_seconds))}: {scorer} scored, making it {after}."
            seconds = self._n(round(p.possession_duration_s), f"seconds of the move before goal {i}")
            passes = self._n(p.possession_passes, f"passes in the move before goal {i}")
            if p.turnover is not None:
                loser = self.names[p.turnover.lost_by]
                where = LOSER_ZONE[p.turnover.zone].format(loser=loser)
                how = f"under pressure from {scorer}" if p.turnover.under_pressure else "without being under pressure"
                text += (f" The move started when {loser} lost the ball {how}, in {where}."
                         f" {scorer} scored {plural(seconds, 'second', 'seconds')} after winning it,"
                         f" with {plural(passes, 'pass', 'passes')} in the move.")
            else:
                text += (f" The data does not record how {scorer} got the ball."
                         f" The move lasted {plural(seconds, 'second', 'seconds')} with"
                         f" {plural(passes, 'pass', 'passes')}.")
            for alert_id in p.related_alert_ids:
                if alert_id in alert_teams:
                    text += (f" Timing only: a pressing alert for {alert_teams[alert_id]} was active shortly before"
                             " this goal; the data does not show that the pressing caused it.")
            lines.append(text)
        return "\n".join(lines) + f"\nFinal score {self.final_score} ({self.names[self.home]} first)."

    def pressing_alerts(self) -> str:
        self.calls.append("pressing_alerts")
        alerts = service.state_at(self.match_id, self.end_s).alerts
        if not alerts:
            return "PULSE's pressing detector raised no alerts in this match."
        lines = []
        for i, alert in enumerate(alerts, 1):
            sheet = detection_facts(self.match_id, alert.alert_id)
            team, opp = self.names[alert.team_id], self.names[alert.opponent_id]
            text = (f"Alert {i}, {self._minute(sheet.detected_minute)} ({sheet.confidence} confidence): PULSE's "
                    f"pressing detector found {team} pressing high much more often.")
            recent, base = sheet.fact("S1.recent_count"), sheet.fact("S1.baseline_count")
            if recent and base and recent.value and base.value:
                ratio = self._n(round(3 * recent.value / base.value, 1), f"alert {i} press ratio")
                text += (f" In the 5 minutes before the alert {team} made "
                         f"{self._n(recent.value, f'alert {i} high presses, last 5 min')} high presses, against "
                         f"{self._n(base.value, f'alert {i} high presses, 15 min before')} in the 15 minutes before"
                         f" that: {ratio} times as often per minute.")
            pc_recent, pc_base = sheet.fact("S3.recent"), sheet.fact("S3.baseline")
            if pc_recent and pc_base and pc_recent.value is not None and pc_base.value is not None:
                text += (f" {opp}'s pass completion was "
                         f"{self._n(pc_recent.value, f'alert {i} {opp} pass completion, last 5 min')}% in those 5 "
                         f"minutes and {self._n(pc_base.value, f'alert {i} {opp} pass completion, 15 min before')}%"
                         " in the 15 minutes before.")
            lines.append(text + " This describes what happened, not why.")
        return "\n".join(lines)

    def momentum_phases(self) -> str:
        self.calls.append("momentum_phases")
        from .service import report_facts  # cached full-time fact sheet

        lines = ["PULSE's momentum indicator per 15 minutes (an indicator from weighted shots, box entries and "
                 "final-third actions; not a measurement and not possession):"]
        for phase in report_facts(self.match_id).phases:
            self.context |= {float(phase.from_minute), float(phase.to_minute)}
            who = f"{phase.on_top} on top" if phase.on_top else "neither team clearly on top"
            lines.append(f"- {phase.from_minute}'-{phase.to_minute}': {who}.")
        return "\n".join(lines)

    def key_events(self, from_minute: int, to_minute: int) -> str:
        if not (0 <= from_minute < to_minute <= 90):
            return "Minutes must satisfy 0 <= from_minute < to_minute <= 90 (90 means full time)."
        self.calls.append(f"key_events {from_minute}'-{to_minute}'")
        self.context |= {float(from_minute), float(to_minute)}
        end_s = self.end_s if to_minute == 90 else to_minute * 60.0
        labels: dict[str, list[str]] = {}
        for tag in service.key_tags(self.match_id):
            if tag.tag != "period" and tag.tag not in labels.get(tag.event_id, []):
                labels.setdefault(tag.event_id, []).append(tag.tag)
        events = [e for e in self.match.events
                  if e.event_id in labels and from_minute * 60 <= e.timestamp_seconds < end_s]
        if not events:
            return f"No key events between {from_minute}' and {to_minute}'."
        lines = []
        for e in events[:MAX_KEY_EVENTS]:
            who = self.players.get(getattr(e, "player_id", ""), "")
            team = self.names.get(getattr(e, "team_id", ""), "")
            actor = f"{who} ({team})" if who else team
            did = []
            for tag in labels[e.event_id]:
                text = TAG_TEXT[tag]
                if tag == "shot":
                    text += f" ({e.outcome.replace('_', ' ')})"
                if tag == "foul" and getattr(e, "card", None):
                    text += f" ({e.card} card)"
                did.append(text)
            lines.append(f"{self._minute(minute_of(e.timestamp_seconds))} {actor} " + " and ".join(did) + ".")
        if len(events) > MAX_KEY_EVENTS:
            lines.append(f"(Showing the first {MAX_KEY_EVENTS} of {len(events)} key events; ask for a shorter range.)")
            self.context |= {float(MAX_KEY_EVENTS), float(len(events))}
        return "\n".join(lines)

    # --- Agent Framework wrappers --------------------------------------------------------------

    def agent_tools(self) -> list:
        Minute = Annotated[int, "match minute, 0-90; 90 means full time (including stoppage time)"]

        @tool
        def team_stats(from_minute: Minute, to_minute: Minute) -> str:
            """Both teams' statistics between two match minutes: estimated possession, pass completion,
            shots, shots on target, penalty-box entries, balls lost under pressure and high presses.
            Use 0-90 for the whole match, 0-45 / 45-90 for the halves."""
            return self.team_stats(from_minute, to_minute)

        @tool
        def goals() -> str:
            """Every goal: minute, scorer, score after, how the move started (who lost the ball, where,
            under whose pressure), seconds and passes in the move."""
            return self.goals()

        @tool
        def pressing_alerts() -> str:
            """The pressing alerts PULSE raised: minute, team, confidence and the before/after numbers."""
            return self.pressing_alerts()

        @tool
        def momentum_phases() -> str:
            """Which team PULSE's momentum indicator had on top in each 15-minute block."""
            return self.momentum_phases()

        @tool
        def key_events(from_minute: Minute, to_minute: Minute) -> str:
            """Key events (goals, shots, key passes, box entries, balls won high, balls lost under pressure,
            fouls, substitutions) between two match minutes, at most 15."""
            return self.key_events(from_minute, to_minute)

        return [team_stats, goals, pressing_alerts, momentum_phases, key_events]
