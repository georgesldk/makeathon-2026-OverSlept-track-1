"""Lists the Gemini models your key can actually use.

    uv run python -m ethnohack.models

Put the one you want in .env as GEMINI_MODEL.
"""

from __future__ import annotations

from google import genai

from ethnohack.config import load


def main() -> None:
    settings = load()
    if not settings.gemini_ready:
        print("GEMINI_API_KEY is not set. Run: uv run python -m ethnohack.config")
        return

    client = genai.Client(api_key=settings.gemini_api_key)

    usable = []
    for model in client.models.list():
        actions = getattr(model, "supported_actions", None) or []
        if "generateContent" in actions:
            usable.append(model)

    if not usable:
        print("No text-generation models came back for this key.")
        return

    print(f"{len(usable)} models available for generateContent:\n")
    for model in sorted(usable, key=lambda m: m.name):
        name = model.name.removeprefix("models/")
        limit = getattr(model, "input_token_limit", None)
        context = f"{limit:,} in" if limit else ""
        marker = "  <- current" if name == settings.gemini_model else ""
        print(f"  {name:<42} {context:>12}{marker}")

    print("\nSet your pick in .env:  GEMINI_MODEL=<name from this list>")


if __name__ == "__main__":
    main()
