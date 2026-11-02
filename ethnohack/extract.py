"""Sends passages to Gemini and gets candidate claims back.

One passage:

    uv run python -m ethnohack.extract --passage culpeper_1653:agrimony

A handful:

    uv run python -m ethnohack.extract --limit 5

Every result is cached to data/cache/extractions/ keyed by passage id and model,
so re-running costs nothing and a prompt change only reprocesses what you ask for.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError, ServerError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ethnohack.config import REPO_ROOT, load
from ethnohack.prompts import EXTRACTION_SYSTEM, build_user_prompt
from ethnohack.schema import CandidateClaim, ExtractionResult, StoredExtraction

PASSAGES_PATH = REPO_ROOT / "data" / "passages" / "culpeper_1653.jsonl"
CACHE_DIR = REPO_ROOT / "data" / "cache" / "extractions"


def load_passages() -> list[dict]:
    if not PASSAGES_PATH.exists():
        sys.exit(f"No passages at {PASSAGES_PATH}\nRun first:  uv run python -m ethnohack.corpus")
    with PASSAGES_PATH.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def cache_path(passage_id: str, model: str) -> Path:
    safe = passage_id.replace(":", "__")
    return CACHE_DIR / f"{safe}__{model}.json"


def is_transient(error: BaseException) -> bool:
    """503 high demand, 504 deadline, 429 rate limit: worth waiting out."""
    if isinstance(error, ServerError):
        return True
    if isinstance(error, ClientError):
        return error.code == 429
    return False


@retry(
    retry=retry_if_exception(is_transient),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(6),
    reraise=True,
)
def call_model(client: genai.Client, model: str, passage: dict):
    return client.models.generate_content(
        model=model,
        contents=build_user_prompt(
            heading=passage["heading"],
            passage_id=passage["passage_id"],
            text=passage["text"],
        ),
        config=types.GenerateContentConfig(
            system_instruction=EXTRACTION_SYSTEM,
            response_mime_type="application/json",
            response_schema=ExtractionResult,
            temperature=0.0,
            http_options=types.HttpOptions(timeout=60_000),
        ),
    )


def extract_one(client: genai.Client, model: str, passage: dict) -> StoredExtraction:
    path = cache_path(passage["passage_id"], model)
    if path.exists():
        return StoredExtraction.model_validate_json(path.read_text(encoding="utf-8"))

    response = call_model(client, model, passage)

    parsed = response.parsed
    claims: list[CandidateClaim]
    if isinstance(parsed, ExtractionResult):
        claims = parsed.claims
    else:
        claims = ExtractionResult.model_validate_json(response.text).claims

    stored = StoredExtraction(
        passage_id=passage["passage_id"],
        corpus_id=passage["corpus_id"],
        heading=passage["heading"],
        model=model,
        extracted_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        claims=claims,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stored.model_dump_json(indent=2), encoding="utf-8")
    return stored


def show(stored: StoredExtraction) -> None:
    print(f"\n{stored.heading}  ({stored.passage_id})")
    print(f"{len(stored.claims)} candidate claims\n")
    for i, claim in enumerate(stored.claims, 1):
        bits = [claim.plant_part, claim.preparation, claim.route]
        detail = ", ".join(b for b in bits if b) or "unspecified"
        print(f"  {i}. {claim.plant_name_verbatim} -> {claim.condition_verbatim}")
        print(f"     {detail}")
        print(f'     "{claim.quote[:110]}{"..." if len(claim.quote) > 110 else ""}"')


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract candidate claims from passages.")
    parser.add_argument("--passage", help="One passage id, e.g. culpeper_1653:agrimony")
    parser.add_argument("--limit", type=int, default=1, help="How many passages (default 1)")
    args = parser.parse_args()

    settings = load()
    if not settings.gemini_ready:
        sys.exit("GEMINI_API_KEY is not set. Run: uv run python -m ethnohack.config")

    passages = load_passages()
    if args.passage:
        chosen = [p for p in passages if p["passage_id"] == args.passage]
        if not chosen:
            sys.exit(f"No passage with id {args.passage}")
    else:
        chosen = passages[: args.limit]

    client = genai.Client(api_key=settings.gemini_api_key)
    print(f"Model: {settings.gemini_model}")

    total = 0
    for passage in chosen:
        try:
            stored = extract_one(client, settings.gemini_model, passage)
        except APIError as error:
            print(f"\n{passage['passage_id']}: API error {error.code} - {error.message}")
            continue
        show(stored)
        total += len(stored.claims)

    print(f"\n{total} claims from {len(chosen)} passage(s). Cached in {CACHE_DIR}")


if __name__ == "__main__":
    main()
