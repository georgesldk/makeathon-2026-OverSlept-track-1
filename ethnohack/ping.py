"""Smallest possible Gemini call, to tell a hang apart from a bad model.

    uv run python -m ethnohack.ping

Tries plain text first, then structured output. Whichever step stalls or fails
is the one to fix; each has its own 30 second timeout.
"""

from __future__ import annotations

import argparse
import sys
import time

from google import genai
from google.genai import types
from pydantic import BaseModel

from ethnohack.config import load


class Answer(BaseModel):
    colour: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Check a Gemini model responds.")
    parser.add_argument("--model", help="Override GEMINI_MODEL for this run")
    args = parser.parse_args()

    settings = load()
    if not settings.gemini_ready:
        sys.exit("GEMINI_API_KEY is not set. Run: uv run python -m ethnohack.config")

    client = genai.Client(api_key=settings.gemini_api_key)
    model = args.model or settings.gemini_model
    opts = types.HttpOptions(timeout=30_000)
    print(f"Model: {model}\n")

    print("1. plain text ...", flush=True)
    start = time.monotonic()
    try:
        reply = client.models.generate_content(
            model=model,
            contents="Reply with the single word: ok",
            config=types.GenerateContentConfig(http_options=opts),
        )
        print(f"   {time.monotonic() - start:.1f}s -> {reply.text!r}")
    except Exception as error:  # noqa: BLE001 - we want the class name shown
        print(f"   {time.monotonic() - start:.1f}s -> FAILED {type(error).__name__}: {error}")
        print("\nPlain text failed, so this is the key, the network, or the model name.")
        return

    print("\n2. structured output ...", flush=True)
    start = time.monotonic()
    try:
        reply = client.models.generate_content(
            model=model,
            contents="What colour is a ripe lemon?",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Answer,
                http_options=opts,
            ),
        )
        print(f"   {time.monotonic() - start:.1f}s -> {reply.text!r}")
        print("\nBoth work. The extractor should run.")
    except Exception as error:  # noqa: BLE001
        print(f"   {time.monotonic() - start:.1f}s -> FAILED {type(error).__name__}: {error}")
        print(f"\nPlain text works but structured output does not on {model}.")
        print("Set GEMINI_MODEL=gemini-2.5-flash in .env and run this again.")


if __name__ == "__main__":
    main()
