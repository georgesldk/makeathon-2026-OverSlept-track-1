"""Loads settings from .env and tells you what is and is not configured.

Run it directly to check your setup:

    uv run python -m ethnohack.config
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(REPO_ROOT / ".env")


class MissingSetting(RuntimeError):
    """Raised when code needs a setting that .env does not provide."""


def _get(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def require(name: str) -> str:
    """Return a setting, or explain clearly what to do about it."""
    value = _get(name)
    if value is None:
        raise MissingSetting(
            f"{name} is not set.\n"
            f"Copy .env.example to .env and fill in {name}.\n"
            f"See the API key section of the README for where to get it."
        )
    return value


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    typesafe_api_key: str | None
    jev_model: str | None

    @property
    def gemini_ready(self) -> bool:
        return self.gemini_api_key is not None

    @property
    def jev_ready(self) -> bool:
        return self.typesafe_api_key is not None and self.jev_model is not None


def load() -> Settings:
    return Settings(
        gemini_api_key=_get("GEMINI_API_KEY"),
        gemini_model=_get("GEMINI_MODEL") or "gemini-2.5-flash",
        typesafe_api_key=_get("TYPESAFE_API_KEY"),
        jev_model=_get("JEV_MODEL"),
    )


def main() -> None:
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        print("No .env file found.")
        print(f"Create one:  cp .env.example .env    (in {REPO_ROOT})")
        return

    settings = load()
    print(f"Reading {env_file}\n")

    rows = [
        ("Gemini key", "set" if settings.gemini_ready else "MISSING"),
        ("Gemini model", settings.gemini_model),
        ("Jev key", "set" if settings.typesafe_api_key else "not set (fine for now)"),
        ("Jev model", settings.jev_model or "not set (fine for now)"),
    ]
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        print(f"  {label.ljust(width)}  {value}")

    print()
    if settings.gemini_ready:
        print("Ready to run extraction.")
    else:
        print("Add GEMINI_API_KEY to .env, then run this again.")


if __name__ == "__main__":
    main()
