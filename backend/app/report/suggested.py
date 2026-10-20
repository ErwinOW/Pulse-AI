"""Suggested questions and their human-approved answers (data/narratives/answers.json).

The suggested-question buttons are what most visitors (and the demo video) will see, so their
answers are generated once with scripts/run_live_answers.py --review and saved only after a person
has read them: the checker catches wrong numbers, not wrong meaning. A question that matches a
saved answer (same match, audience, language and prompt version) is served without a model call.
"""

import json
from pathlib import Path

from app.narrative.schema import Audience, Language

from .analyst import PROMPT_VERSION, AnswerResult

ANSWERS_FILE = Path(__file__).resolve().parents[3] / "data" / "narratives" / "answers.json"
SUGGESTED = {
    "en": [
        "How were the goals scored?",
        "Who pressed more in the second half?",
        "Which team created more chances?",
        "What did PULSE's pressing alert show?",
    ],
    "id": [
        "Bagaimana gol-gol dicetak?",
        "Tim mana yang lebih banyak melakukan pressing di babak kedua?",
        "Tim mana yang menciptakan lebih banyak peluang?",
        "Apa yang ditunjukkan peringatan pressing PULSE?",
    ],
}


def normalise(question: str) -> str:
    return " ".join(question.lower().split()).rstrip("?").strip()


def answer_key(match_id: str, question: str, audience: Audience, language: Language) -> str:
    return f"{match_id}|{audience}|{language}|{PROMPT_VERSION}|{normalise(question)}"


class AnswerCache:
    def __init__(self, path: Path = ANSWERS_FILE):
        self.path = path
        self.entries: dict[str, dict] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def get(self, match_id: str, question: str, audience: Audience, language: Language) -> AnswerResult | None:
        entry = self.entries.get(answer_key(match_id, question, audience, language))
        return AnswerResult.model_validate(entry) if entry else None

    def put(self, match_id: str, audience: Audience, language: Language, result: AnswerResult) -> None:
        """Store an approved answer. Only checked AI answers are worth approving."""
        if result.source != "ai":
            raise ValueError("only checked AI answers can be saved")
        self.entries[answer_key(match_id, result.question, audience, language)] = result.model_dump(mode="json")

    def save(self) -> None:
        self.path.write_text(json.dumps(self.entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
