"""Analyst tools and the answer checker (no AI)."""

import pytest

from app.api import service
from app.report.analyst_tools import MAX_KEY_EVENTS, MatchTools
from app.report.answer_checker import DECLINE, MAX_CHARS, check_answer
from app.report.facts import end_time
from app.stats import compute_window

DEMO = "demo-high-press"


def looked_up(*calls: str) -> MatchTools:
    tools = MatchTools(DEMO)
    for call in calls:
        getattr(tools, call)()
    return tools


def test_team_stats_match_the_statistics_engine_and_fill_the_ledger():
    tools = MatchTools(DEMO)
    text = tools.team_stats(45, 90)

    match = service.load_match(DEMO)
    home, away = service.teams_of(match)
    window = compute_window(match.events, (home, away), 2700.0, end_time(DEMO))
    eas = window.teams[away]
    assert f"{eas.high_pressures_per_min.sample_size} high presses" in text
    assert f"{eas.shots.value:g} shots" in text
    assert {f.value for f in tools.ledger} >= {eas.shots.value, eas.high_pressures_per_min.sample_size}
    assert tools.calls == ["team_stats 45'-90'"]


@pytest.mark.parametrize("bad", [(-1, 10), (50, 50), (60, 30), (0, 91)])
def test_tools_refuse_impossible_minute_ranges(bad):
    tools = MatchTools(DEMO)

    assert tools.team_stats(*bad).startswith("Minutes must")
    assert tools.key_events(*bad).startswith("Minutes must")
    assert tools.calls == [] and tools.ledger == []


def test_goals_say_who_lost_the_ball_in_plain_words():
    text = looked_up("goals").goals()

    assert "Northbridge FC lost the ball under pressure from Eastvale Athletic, in Northbridge FC's own third" in text
    assert "8 seconds after winning it, with 1 pass in the move" in text
    assert "does not record how Northbridge FC got the ball" in text
    assert "does not show that the pressing caused it" in text


def test_pressing_alerts_report_the_detection_numbers():
    text = MatchTools(DEMO).pressing_alerts()

    assert "11 high presses, against 5" in text and "6.6 times as often" in text


def test_key_events_are_capped():
    tools = MatchTools(DEMO)
    text = tools.key_events(0, 90)

    assert len(text.splitlines()) == MAX_KEY_EVENTS + 1
    assert "Showing the first 15 of" in text


def test_agent_tools_are_exposed_by_name():
    names = [t.name for t in MatchTools(DEMO).agent_tools()]

    assert names == ["team_stats", "goals", "pressing_alerts", "momentum_phases", "key_events"]


def test_accurate_answers_pass():
    tools = looked_up("goals", "pressing_alerts")

    en = ("Eastvale Athletic equalised in the 64th minute, 8 seconds after Northbridge FC lost the ball under "
          "pressure in their own third. Eastvale had been pressing 6.6 times as often, which may have helped.")
    assert check_answer(en, tools, "en").ok, check_answer(en, tools, "en").problems
    id_ = "Eastvale Athletic menyamakan skor pada menit 64, 8 detik setelah merebut bola. Mereka menekan 6,6 kali lebih sering."
    assert check_answer(id_, tools, "id").ok, check_answer(id_, tools, "id").problems


@pytest.mark.parametrize("answer, problem", [
    ("Eastvale scored 12 seconds after winning the ball.", "number 12"),
    ("Eastvale pressed 6,6 times as often.", "decimal point"),
    ("The pressing caused the equaliser.", "must be hedged"),
    ("Eastvale pressed more. As a result, Northbridge lost the ball.", "must be hedged"),
    ("Eastvale decided to press higher after the hour.", "intent"),
    ("Northbridge would have won if they had kept the ball.", "hypotheticals"),
    ("One. Two. Three. Four.", "sentences"),
    ("x" * (MAX_CHARS + 1), "characters"),
])
def test_bad_answers_are_rejected(answer, problem):
    result = check_answer(answer, looked_up("goals", "pressing_alerts"), "en")

    assert not result.ok and any(problem in p for p in result.problems), result.problems


def test_numbers_must_come_from_tools_used_for_this_question():
    answer = "Eastvale Athletic scored 8 seconds after winning the ball."

    assert any("tool" in p for p in check_answer(answer, MatchTools(DEMO), "en").problems)
    assert check_answer(answer, looked_up("goals"), "en").ok


def test_indonesian_unhedged_cause_is_rejected():
    # Real approved-then-caught answer: "Akibatnya" (= "as a result") slipped past the "akibat" rule.
    answer = "Eastvale Athletic menekan 6,6 kali lebih sering. Akibatnya, operan Northbridge FC menurun."
    result = check_answer(answer, looked_up("pressing_alerts"), "id")

    assert any("must be hedged" in p for p in result.problems), result.problems


def test_indonesian_answer_with_english_terms_is_rejected():
    result = check_answer("Eastvale merebut bola and mencetak gol.", looked_up("goals"), "id")

    assert any("English term" in p for p in result.problems)


@pytest.mark.parametrize("language", ["en", "id"])
def test_decline_needs_no_tool_call(language):
    assert check_answer(DECLINE[language], MatchTools(DEMO), language).ok
