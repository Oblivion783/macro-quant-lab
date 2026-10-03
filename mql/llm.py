"""Optional AI writer using Google's Gemini API free tier.

- Get a free key at Google AI Studio (https://aistudio.google.com/apikey) with a personal Google account.
- Store it as the GitHub Actions secret GEMINI_API_KEY (and in your local .env if you want).
- No key: everything still runs; the template writer is used.

Never send anything from work to any AI service. This module only ever sends the public
market-data table built by monitor.py.
"""
from __future__ import annotations

import os

import requests

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def gemini_generator(model: str | None = None, temperature: float = 0.3):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    model = model or os.environ.get("MQL_GEMINI_MODEL", "gemini-flash-latest")

    def generate(prompt: str) -> str:
        r = requests.post(
            ENDPOINT.format(model=model),
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"}},
            timeout=60,
        )
        if r.status_code != 200:
            raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)

    return generate
