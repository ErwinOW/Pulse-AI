"""Cache of validated AI insights (data/narratives/cache.json).

The demo match is deterministic, so a validated narrative for the same facts,
audience, language, model and prompt version can be reused. That keeps the
public demo within free-tier limits. Cached insights keep their original
model, prompt version and timestamp, so the UI can label them honestly.
Only AI-written, validated insights are stored; fallbacks are recomputed.
"""

import hashlib
import json
from pathlib import Path

from .facts import InsightFacts
from .pipeline import Insight
from .schema import Audience, Language

CACHE_FILE = Path(__file__).resolve().parents[3] / "data" / "narratives" / "cache.json"


def cache_key(
    facts: InsightFacts, audience: Audience, language: Language, model: str, prompt_version: str
) -> str:
    payload = json.dumps(
        {"facts": facts.model_dump(mode="json"), "audience": audience, "language": language,
         "model": model, "prompt_version": prompt_version},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class InsightCache:
    def __init__(self, path: Path = CACHE_FILE):
        self.path = path
        self.entries: dict[str, dict] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        )

    def get(self, facts: InsightFacts, audience: Audience, language: Language,
            model: str, prompt_version: str) -> Insight | None:
        entry = self.entries.get(cache_key(facts, audience, language, model, prompt_version))
        return Insight.model_validate(entry) if entry else None

    def put(self, facts: InsightFacts, insight: Insight) -> bool:
        """Store a validated AI insight. Returns False (and stores nothing) for fallbacks."""
        if insight.source != "ai" or insight.model is None or insight.prompt_version is None:
            return False
        key = cache_key(facts, insight.audience, insight.language, insight.model,
                        insight.prompt_version)
        self.entries[key] = insight.model_dump(mode="json")
        return True

    def prune(self, prompt_version: str) -> int:
        """Drop entries written with another prompt version. Returns how many were removed."""
        stale = [k for k, v in self.entries.items() if v.get("prompt_version") != prompt_version]
        for key in stale:
            del self.entries[key]
        return len(stale)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.entries, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8", newline="\n")
