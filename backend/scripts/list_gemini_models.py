"""List the Gemini models your API key can use (also proves the key works).

Run from the backend folder (venv active):
    python -m scripts.list_gemini_models

The key is sent in a request header, never in the URL, and is never printed.
"""

import json
import sys
import urllib.error
import urllib.request

from app.config import setting

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def main() -> None:
    key = setting("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY is empty: fill it in backend/.env")

    base_url = setting("GEMINI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    request = urllib.request.Request(
        f"{base_url}/models", headers={"Authorization": f"Bearer {key}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        # Error bodies from Google do not contain the key; show them for diagnosis.
        sys.exit(f"HTTP {error.code}: {error.read().decode('utf-8', 'replace')[:500]}")

    ids = sorted(m["id"] for m in payload.get("data", []))
    flash = [i for i in ids if "flash" in i.lower()]
    print(f"{len(ids)} models available to this key.")
    print("Flash / Flash-Lite models (candidates for GEMINI_MODEL):")
    for model_id in flash:
        print(f"  {model_id}")


if __name__ == "__main__":
    main()
