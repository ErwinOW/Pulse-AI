"""Deterministic template narratives: shown when the AI is unavailable or fails validation.

Built only from the fact sheet, in English and Indonesian, for both audiences.
Tests check that every fallback passes the same validator as AI output.
"""

from .facts import InsightFacts, MetricFact
from .schema import Audience, Language, MetricClaim, Narrative

CONFIDENCE_ID = {"moderate": "sedang", "strong": "kuat"}


def fmt(value: float, language: Language) -> str:
    # One decimal: counts over 5-15 minutes do not support more precision.
    text = f"{round(value, 1):g}"
    return text.replace(".", ",") if language == "id" else text


def fallback_narrative(facts: InsightFacts, audience: Audience, language: Language) -> Narrative:
    used: list[MetricFact] = []

    def v(fact_id: str) -> str | None:
        fact = facts.fact(fact_id)
        if fact is None or fact.value is None:
            return None
        used.append(fact)
        return fmt(fact.value, language)

    team, opp = facts.team_name, facts.opponent_name
    r, bw = facts.recent_window_minutes, facts.baseline_window_minutes
    if audience == "casual":
        # Fans get at most 2 statistics, as event totals (the validator enforces this).
        hp_n, hp_base_n = v("S1.recent_count"), v("S1.baseline_count")
        s2 = facts.fact("S2.recent"), facts.fact("S2.baseline")
        more_losses = all(f is not None and f.value is not None for f in s2) and s2[0].value > s2[1].value
        if language == "en":
            headline = f"{team} turn up the pressure on {opp}"
            summary = (f"In the last {r} minutes, {team} pressed high {hp_n} times, compared with "
                       f"{hp_base_n} times in the {bw} minutes before.")
            if more_losses:
                summary += f" {opp} also lost the ball under pressure more often in that spell."
            interpretation = (f"This may make it harder for {opp} to play out from the back. "
                              "Event data shows the pattern, not the coach's intent.")
        else:
            headline = f"{team} meningkatkan tekanan terhadap {opp}"
            summary = (f"Dalam {r} menit terakhir, {team} melakukan pressing tinggi sebanyak {hp_n} kali, "
                       f"dibanding {hp_base_n} kali pada {bw} menit sebelumnya.")
            if more_losses:
                summary += f" {opp} juga lebih sering kehilangan bola saat ditekan pada periode itu."
            interpretation = (f"Hal ini mungkin menyulitkan {opp} membangun serangan dari belakang. "
                              "Data event menunjukkan polanya, bukan niat pelatih.")
    else:
        hp, hp_base, hp_n = v("S1.recent"), v("S1.baseline"), v("S1.recent_count")
        to, to_base, to_n = v("S2.recent"), v("S2.baseline"), v("S2.recent_count")
        pc, pc_base, pc_n = v("S3.recent"), v("S3.baseline"), v("S3.recent_count")
        if language == "en":
            headline = f"Pressing increase: {team} from minute {facts.onset_minute}"
            summary = (f"Last {r} min vs previous {bw} min. {team} high pressures: {hp_base} to {hp} "
                       f"per min ({hp_n} events). {opp} turnovers under pressure: {to_base} to {to} "
                       f"per min ({to_n}).")
            if pc is not None and pc_base is not None:
                summary += f" {opp} pass completion: {pc_base}% to {pc}% ({pc_n} passes)."
            interpretation = (f"The pattern is consistent with a higher press by {team}; confidence "
                              f"{facts.confidence}. Event data cannot confirm tactical intent.")
        else:
            headline = f"Peningkatan pressing: {team} sejak menit {facts.onset_minute}"
            summary = (f"{r} menit terakhir dibanding {bw} menit sebelumnya. Pressing tinggi {team}: "
                       f"{hp_base} menjadi {hp} per menit ({hp_n} kejadian). Kehilangan bola {opp} di "
                       f"bawah tekanan: {to_base} menjadi {to} per menit ({to_n}).")
            if pc is not None and pc_base is not None:
                summary += f" Akurasi umpan {opp}: {pc_base}% menjadi {pc}% ({pc_n} umpan)."
            interpretation = (f"Pola ini konsisten dengan pressing yang lebih tinggi oleh {team}; "
                              f"tingkat keyakinan {CONFIDENCE_ID[facts.confidence]}. Data event tidak "
                              "dapat memastikan niat taktis.")

    claims = {f.fact_id: MetricClaim(fact_id=f.fact_id, value=f.value) for f in used}
    return Narrative(
        headline=headline,
        summary=summary,
        event_ids=list(facts.evidence_event_ids),
        metric_claims=list(claims.values()),
        interpretation=interpretation,
        confidence=facts.confidence,
        is_hypothetical=False,
    )
