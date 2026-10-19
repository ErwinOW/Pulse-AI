"""Settings loaded from environment variables and backend/.env.

A tiny loader instead of a dependency: KEY=VALUE lines, '#' comments,
optional surrounding quotes. Real environment variables win over .env,
so hosting platforms can inject secrets without a file.
"""

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_env(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def setting(name: str, default: str | None = None) -> str | None:
    load_env()
    return os.environ.get(name) or default
