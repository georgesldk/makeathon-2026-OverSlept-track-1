"""Downloads Culpeper's Complete Herbal (1653) from Project Gutenberg.

    uv run python -m ethnohack.fetch_culpeper

Saves the raw text to data/corpora/ (gitignored) and writes a rights record
beside it. Culpeper is our first corpus because it is clean plain text in
English — the fastest way to see extraction working. Dioscorides comes next.
"""

from __future__ import annotations

import datetime as dt
import json

import httpx

from ethnohack.config import REPO_ROOT

SOURCE_URL = "https://www.gutenberg.org/ebooks/49513.txt.utf-8"
LANDING_URL = "https://www.gutenberg.org/ebooks/49513"

CORPUS_DIR = REPO_ROOT / "data" / "corpora"
RAW_PATH = CORPUS_DIR / "culpeper_1653.txt"
RIGHTS_PATH = CORPUS_DIR / "culpeper_1653.rights.json"

RIGHTS = {
    "corpus_id": "culpeper_1653",
    "title": "The Complete Herbal",
    "author": "Nicholas Culpeper",
    "first_published": 1653,
    "edition_source": "Project Gutenberg ebook 49513",
    "source_url": SOURCE_URL,
    "landing_url": LANDING_URL,
    "rights_statement": "Public domain in the USA (Project Gutenberg)",
    "lineage": "western_vernacular",
    "descends_from": "dioscorides",
    "notes": (
        "Gutenberg texts are public domain in the USA; check local status before "
        "redistribution. Gutenberg header and licence footer are stripped at parse time, "
        "not here, so the raw file stays a faithful copy."
    ),
}


def main() -> None:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    if RAW_PATH.exists():
        size = RAW_PATH.stat().st_size
        print(f"Already downloaded: {RAW_PATH} ({size:,} bytes)")
    else:
        print(f"Downloading {SOURCE_URL} ...")
        response = httpx.get(SOURCE_URL, timeout=60.0, follow_redirects=True)
        response.raise_for_status()
        RAW_PATH.write_text(response.text, encoding="utf-8")
        print(f"Saved {RAW_PATH} ({len(response.text):,} characters)")

    record = dict(RIGHTS, retrieved_at=dt.datetime.now(dt.UTC).date().isoformat())
    RIGHTS_PATH.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Rights record: {RIGHTS_PATH}")

    text = RAW_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    print(f"\n{len(lines):,} lines. First 40 after the Gutenberg header:\n")

    start = 0
    for i, line in enumerate(lines):
        if line.startswith("*** START"):
            start = i + 1
            break

    for line in lines[start : start + 40]:
        print(f"  {line}")

    print("\nPaste this output back to Claude so the passage splitter matches the real layout.")


if __name__ == "__main__":
    main()
