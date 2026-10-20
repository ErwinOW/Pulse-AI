"""Full-time report: Commentator agent -> fact-checker -> one retry -> template fallback.

Same contract as the in-match insights: the agent only words the fact sheet, nothing is
shown without passing the checker, and every result says who wrote it.
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from agent_framework import Agent
from pydantic import BaseModel, ConfigDict, ValidationError

from app.narrative.cache import InsightCache
from app.narrative.fallback import fmt
from app.narrative.schema import Audience, Language, MetricClaim
from app.narrative.storyteller import MAX_OUTPUT_TOKENS, StorytellerError, chat_client_from_env

from .checker import MatchReport, validate_report
from .facts import ReportFacts, audience_view

# r2: alerts come from the pressing detector, scorer-view locations, whole-number counts,
#     cover every goal and alert, sentence case, no intent words, match order
# r3: casual gets a pre-selected sheet (max 4 statistics), press ratio, no English sentences in
#     the sheet, loser_under_pressure, short analyst closing, momentum is not possession
PROMPT_VERSION = "r3"
MAX_ATTEMPTS = 2
REPORT_CACHE_FILE = Path(__file__).resolve().parents[3] / "data" / "narratives" / "reports.json"

INSTRUCTIONS = """You are PULSE's Commentator: after the final whistle you write a short post-match
report from a verified fact sheet. You never compute statistics; you only word the facts given.

Hard rules (checked automatically; breaking one gets the report rejected):
1. Use ONLY numbers that appear in the fact sheet, written as digits: fact values, minutes,
   scores, the 5 and 15 minute windows and the 15-minute block bounds. Never invent numbers.
2. For every statistic you use (a fact from "facts"), add {fact_id, value} to metric_claims.
3. headline and moments describe what happened only. No cause and effect there: no "caused",
   "led to", "because", "due to", "resulted in", "forced", "made it", "in response"; in
   Indonesian no "menyebabkan", "karena", "akibat", "sehingga", "memaksa", "membuat".
   The closing may suggest a link, but only hedged ("may", "might" / "mungkin").
4. No hypotheticals ("would have", "what if"). No intentions, decisions, tactics changes,
   strategies, emotions or injuries: event data cannot show them.
5. moments: 3 to 5 items, strictly in match order, each one or two sentences, each starting
   with its minute (e.g. "64'"; a phase starts with its first minute, e.g. "46'"). Cover every
   goal and every alert. For a goal, say how the move started (ball_won_in, seconds, passes).
   loser_under_pressure describes the team that LOST the ball, not the scoring move.
   For an alert (kind "pressing increase"), say PULSE's pressing detector found that team
   pressing high much more often; press_ratio is how many times more often per minute. In
   Indonesian say e.g. "PULSE mendeteksi peningkatan pressing tinggi Eastvale Athletic".
   Alerts are NOT from the momentum indicator. Momentum phases are a separate indicator: say
   "by PULSE's momentum indicator"; it is not possession or territory.
   Write totals as whole numbers ("17 shots", never "17.0").
6. Number format: English 57.1, Indonesian 57,1. Rates "per minute"/"per menit"; totals as a
   number plus what was counted ("11 high presses"); percentages with "%".

Audiences:
- casual: lively commentator language for fans. The fact sheet has been cut down to the only
  statistics you may use; use no other numbers except minutes and the score. The headline has
  no numbers except the score. Use sentence case for the headline.
- analyst: tactical detail, time windows, before/after comparisons and match totals. The
  closing is at most 2 sentences.

Languages:
- en: natural English.
- id: natural Bahasa Indonesia as Indonesian commentators speak it ("pressing tinggi",
  "kehilangan bola", "akurasi umpan", "penguasaan bola"). Keep team names unchanged. Do not
  copy English fact-sheet words such as "turnover", "baseline", "recent" or "build-up".
"""

JSON_SHAPE = ('{"headline": str, "moments": [str, str, str], "closing": str, '
              '"metric_claims": [{"fact_id": str, "value": number}]}')


class ReportResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_id: str  # match id
    audience: Audience
    language: Language
    report: MatchReport
    source: Literal["ai", "fallback"]
    model: str | None
    prompt_version: str | None
    attempts: int
    rejected_attempts: list[list[str]]
    fallback_reason: str | None
    generated_at: str


def report_cache() -> InsightCache:
    return InsightCache(REPORT_CACHE_FILE, entry_model=ReportResult)


def build_prompt(facts: ReportFacts, audience: Audience, language: Language,
                 feedback: list[str] | None = None, json_shape: bool = False) -> str:
    parts = [f"Audience: {audience}. Language: {language}.",
             "Fact sheet (the only source you may use):",
             json.dumps(facts.model_dump(mode="json"), ensure_ascii=False, indent=1)]
    if feedback:
        parts.append("Your previous report was rejected by the fact checker for these reasons. "
                     "Fix all of them:\n- " + "\n- ".join(feedback))
    if json_shape:
        parts.append(f"Reply with ONLY a JSON object of this shape, no code fences:\n{JSON_SHAPE}")
    return "\n\n".join(parts)


class AgentCommentator:
    def __init__(self, client, model_name: str, use_schema: bool = True, timeout_s: float = 30.0):
        self.model_name = model_name
        self.use_schema = use_schema
        self.timeout_s = timeout_s
        self.agent = Agent(client=client, name="commentator", instructions=INSTRUCTIONS)

    async def write(self, facts, audience, language, feedback=None) -> MatchReport:
        prompt = build_prompt(facts, audience, language, feedback, json_shape=not self.use_schema)
        options: dict = {"temperature": 0.5, "max_tokens": MAX_OUTPUT_TOKENS * 2}
        if self.use_schema:
            options["response_format"] = MatchReport
        try:
            response = await asyncio.wait_for(self.agent.run(prompt, options=options), self.timeout_s)
            if self.use_schema:
                if response.value is None:
                    raise StorytellerError("empty structured response")
                return response.value
            cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", response.text.strip())
            return MatchReport.model_validate_json(cleaned)
        except StorytellerError:
            raise
        except asyncio.TimeoutError as error:
            raise StorytellerError(f"timed out after {self.timeout_s:g}s") from error
        except (ValidationError, ValueError) as error:
            raise StorytellerError(f"unparseable response: {str(error)[:200]}") from error
        except Exception as error:  # API errors (rate limit, bad request, network)
            raise StorytellerError(f"{type(error).__name__}: {str(error)[:200]}") from error


def commentator_from_env(timeout_s: float | None = None) -> AgentCommentator | None:
    config = chat_client_from_env(timeout_s)
    if config is None:
        return None
    client, model, use_schema, timeout = config
    return AgentCommentator(client, model, use_schema, max(timeout, timeout_s or 0))


# --- Template fallback (also the "no AI" version) ----------------------------------------

WON_IN_TEXT = {
    "en": {"their attacking third": "their attacking third", "the middle third": "the middle third",
           "their own third": "their own third"},
    "id": {"their attacking third": "sepertiga serang mereka", "the middle third": "sepertiga tengah",
           "their own third": "sepertiga pertahanan mereka"},
}


def _half_line(facts: ReportFacts, half: int, language: Language) -> str | None:
    blocks = facts.phases[:3] if half == 1 else facts.phases[3:]
    leaders = [p.on_top for p in blocks if p.on_top]
    top = max(set(leaders), key=leaders.count) if leaders else None
    if top is not None and leaders.count(top) < 2:
        top = None
    start, end = (1, 45) if half == 1 else (46, 90)
    if language == "en":
        who = f"{top} were on top for most of it" if top else "neither team was on top for long"
        return f"{start}'-{end}': by PULSE's momentum indicator, {who}."
    who = f"{top} lebih dominan di sebagian besar waktunya" if top else "tidak ada tim yang lama mendominasi"
    return f"{start}'-{end}': menurut indikator momentum PULSE, {who}."


def fallback_report(facts: ReportFacts, audience: Audience, language: Language) -> MatchReport:
    facts = audience_view(facts, audience)
    claims: dict[str, MetricClaim] = {}
    budget = 4 if audience == "casual" else 99

    def use(fact_id: str) -> str | None:
        fact = facts.fact(fact_id)
        if fact is None or (fact_id not in claims and len(claims) >= budget):
            return None
        claims[fact_id] = MetricClaim(fact_id=fact_id, value=fact.value)
        return fmt(fact.value, language)

    events: list[tuple[int, str]] = []
    for g in facts.goals:
        p = g.fact_prefix
        if g.start == "ball_won":
            pressure = (" under pressure" if language == "en" else " saat ditekan") if g.loser_under_pressure else ""
            secs = use(f"{p}.seconds")
            where = WON_IN_TEXT[language][g.ball_won_in or "the middle third"]
            if language == "en":
                text = (f"{g.minute}' {g.team_name} score ({g.score_after}): they won the ball in {where} "
                        f"after {g.lost_by_name} lost it{pressure}")
                text += f", and scored {secs} seconds later." if secs else "."
            else:
                text = (f"{g.minute}' {g.team_name} mencetak gol ({g.score_after}): bola direbut di {where} "
                        f"setelah {g.lost_by_name} kehilangan bola{pressure}")
                text += f", lalu gol tercipta {secs} detik kemudian." if secs else "."
        else:
            passes = use(f"{p}.passes")
            if language == "en":
                text = (f"{g.minute}' {g.team_name} score ({g.score_after})"
                        + (f" at the end of a {passes}-pass move." if passes else "."))
            else:
                text = (f"{g.minute}' {g.team_name} mencetak gol ({g.score_after})"
                        + (f" lewat rangkaian {passes} umpan." if passes else "."))
        events.append((g.minute, text))

    for a in facts.alerts:
        p = a.fact_prefix
        ratio = use(f"{p}.press_ratio")
        if language == "en":
            text = f"{a.detected_minute}' PULSE flags a pressing increase by {a.team_name}"
            text += f": they pressed high {ratio} times as often as in the 15 minutes before." if ratio else "."
        else:
            text = f"{a.detected_minute}' PULSE mendeteksi peningkatan pressing tinggi {a.team_name}"
            text += f": {ratio} kali lebih sering dibanding 15 menit sebelumnya." if ratio else "."
        if audience == "analyst":
            recent, before = use(f"{p}.press_recent"), use(f"{p}.press_baseline")
            if recent and before:
                text += (f" ({recent} high presses in 5 minutes vs {before} in 15.)" if language == "en"
                         else f" ({recent} kali dalam 5 menit dibanding {before} kali dalam 15 menit.)")
        if audience == "analyst":
            r, b = use(f"{p}.opp_pass_completion_recent"), use(f"{p}.opp_pass_completion_baseline")
            if r and b:
                text += (f" {a.opponent_name} pass completion went from {b}% to {r}% over the same windows."
                         if language == "en" else
                         f" Akurasi umpan {a.opponent_name} turun dari {b}% menjadi {r}% pada periode yang sama.")
        events.append((a.detected_minute, text))

    # Half summaries sit at minutes 1 and 46 so every moment stays in match order. If there are
    # more than 5 moments, drop half summaries first (latest first), then the latest events.
    items = [(m, 1, text) for m, text in events]
    for half, minute in ((1, 1), (2, 46)):
        line = _half_line(facts, half, language)
        if line:
            items.append((minute, 0, line))
    while len(items) > 5:
        phases = [i for i in items if i[1] == 0]
        items.remove(max(phases or items, key=lambda i: i[0]))
    moments = [text for _, _, text in sorted(items, key=lambda i: (i[0], i[1]))]

    home, away, score = facts.home_name, facts.away_name, facts.final_score
    a_goals, b_goals = (int(x) for x in score.split("-"))
    if language == "en":
        if audience == "casual":
            headline = (f"{home} and {away} share the points" if a_goals == b_goals
                        else f"{home if a_goals > b_goals else away} win {score}")
        else:
            headline = f"{home} {score} {away}: full-time report"
    else:
        if audience == "casual":
            headline = (f"{home} dan {away} berbagi angka" if a_goals == b_goals
                        else f"{home if a_goals > b_goals else away} menang {score}")
        else:
            headline = f"{home} {score} {away}: laporan akhir laga"

    closing_en = "The data shows when the game turned; it may not show why."
    closing_id = "Data menunjukkan kapan laga berbalik, tetapi mungkin tidak menjelaskan alasannya."
    if audience == "analyst":
        home_id = next((f.fact_id.split(".")[0] for f in facts.facts if f.label.startswith(home)), None)
        away_id = next((f.fact_id.split(".")[0] for f in facts.facts if f.label.startswith(away)), None)
        hp, ap = use(f"{home_id}.possession"), use(f"{away_id}.possession")
        if hp and ap:
            closing_en = (f"Over the match {home} had {hp}% estimated possession and {away} {ap}%. "
                          "Pressing may have mattered, but event data cannot confirm intent.")
            closing_id = (f"Sepanjang laga {home} menguasai bola sekitar {hp}% dan {away} {ap}%. "
                          "Pressing mungkin berpengaruh, tetapi data event tidak bisa memastikan niat.")
    closing = closing_en if language == "en" else closing_id

    return MatchReport(headline=headline, moments=moments, closing=closing, metric_claims=list(claims.values()))


# --- Pipeline ------------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def generate_report(facts: ReportFacts, audience: Audience, language: Language,
                          commentator: AgentCommentator | None) -> ReportResult:
    rejected: list[list[str]] = []

    def fallback(reason: str, attempts: int) -> ReportResult:
        return ReportResult(report_id=facts.match_id, audience=audience, language=language,
                            report=fallback_report(facts, audience, language), source="fallback",
                            model=None, prompt_version=None, attempts=attempts, rejected_attempts=rejected,
                            fallback_reason=reason, generated_at=_now())

    if commentator is None:
        return fallback("ai_disabled", 0)
    view = audience_view(facts, audience)  # what the agent sees and is checked against
    feedback: list[str] | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            report = await commentator.write(view, audience, language, feedback)
        except StorytellerError as error:
            if "unparseable" in str(error) and attempt < MAX_ATTEMPTS:
                # Wrong format (e.g. a field too long) is fixable: retry with the reason.
                rejected.append([str(error)[:300]])
                feedback = [f"Your output did not match the required format: {str(error)[:300]}"]
                continue
            return fallback(f"ai_error: {error}", attempt)
        result = validate_report(report, view, language, audience)
        if result.ok:
            return ReportResult(report_id=facts.match_id, audience=audience, language=language, report=report,
                                source="ai", model=commentator.model_name, prompt_version=PROMPT_VERSION,
                                attempts=attempt, rejected_attempts=rejected, fallback_reason=None,
                                generated_at=_now())
        rejected.append(result.problems)
        feedback = result.problems
    return fallback("validation_failed", MAX_ATTEMPTS)
