"""Deterministic template narratives: shown when the AI is unavailable or fails validation.

Built only from the fact sheet, in English and Indonesian, for both audiences.
Tests check that every fallback passes the same validator as AI output.
"""

from .facts import InsightFacts, MetricFact
from .schema import Audience, Language, MetricClaim, Narrative

CONFIDENCE_ID = {"moderate": "sedang", "strong": "kuat"}


def fmt(value: float, language: Language) -> str:
    text = f"{value:g}"
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
    hp, hp_base, hp_n = v("S1.recent"), v("S1.baseline"), v("S1.recent_count")
    to, to_base, to_n = v("S2.recent"), v("S2.baseline"), v("S2.recent_count")

    if audience == "casual":
        if language == "en":
            headline = f"{team} turn up the pressure on {opp}"
            summary = (f"Over the last {r} minutes, {team} pressed high {hp_n} times ({hp} per minute, "
                       f"up from {hp_base} per minute in the {bw} minutes before). {opp} lost the "
                       f"ball under pressure {to_n} times in that spell.")
            interpretation = (f"This may make it harder for {opp} to play out from the back. "
                              "Event data shows the pattern, not the coach's intent.")
        else:
            headline = f"{team} meningkatkan tekanan terhadap {opp}"
            summary = (f"Dalam {r} menit terakhir, {team} melakukan pressing tinggi sebanyak {hp_n} kali "
                       f"({hp} per menit, naik dari {hp_base} per menit pada {bw} menit sebelumnya). "
                       f"{opp} kehilangan bola di bawah tekanan sebanyak {to_n} kali pada periode itu.")
            interpretation = (f"Hal ini mungkin menyulitkan {opp} membangun serangan dari belakang. "
                              "Data event menunjukkan polanya, bukan niat pelatih.")
    else:
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
