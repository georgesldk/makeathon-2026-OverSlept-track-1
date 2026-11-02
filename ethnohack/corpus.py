"""Splits a raw corpus file into passages, one per herb.

    uv run python -m ethnohack.corpus

Culpeper's layout: each herb is a four-space-indented ALL CAPS heading, and the
body is divided into sections marked _Descript._] _Place._] _Time._] and
_Government and virtues._]. Therapeutic claims live almost entirely in the last
one, so that section becomes the passage we extract from. Keeping description
and habitat out matters: Jev degrades when the state carries irrelevant material.

Writes data/passages/culpeper_1653.jsonl — one JSON object per line.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass

from ethnohack.config import REPO_ROOT

RAW_PATH = REPO_ROOT / "data" / "corpora" / "culpeper_1653.txt"
OUT_PATH = REPO_ROOT / "data" / "passages" / "culpeper_1653.jsonl"
CORPUS_ID = "culpeper_1653"

HEADING = re.compile(r"^ {4}([A-Z][A-Z0-9 ,’'()&.-]{2,60})\.$")
HEADING_CONT = re.compile(r"^ {4}([A-Z][A-Z0-9 ,’'()&-]{2,60})$")
# Two marker styles appear in this edition: the usual _Government and virtues._]
# and a plain capitals form, GOVERNMENT AND VIRTUES.]
SECTION = re.compile(r"_([A-Za-z][A-Za-z ]*)\._\]|^([A-Z][A-Z ]{2,40})\.\]", re.MULTILINE)
VIRTUES = re.compile(r"government and virtues|virtues and use", re.IGNORECASE)

# The herb entries are followed by chapters on preparing medicines and by the
# transcriber's list of corrections. Without this, the last herb's section runs
# on to the end of the book.
BACKMATTER = re.compile(
    r"^(?: {4,}CHAP\.|SECTION [IVX]+\.|DIRECTIONS FOR|Page \d+, |\[Transcriber)",
    re.MULTILINE,
)

# Where the herb entries stop and the manual on preparing medicines begins.
END_OF_HERBS = re.compile(r"^(?:DIRECTIONS FOR|SECTION [IVX]+\.$)")


@dataclass(frozen=True)
class Passage:
    passage_id: str
    corpus_id: str
    heading: str
    section: str
    text: str
    word_count: int


def slugify(heading: str) -> str:
    text = unicodedata.normalize("NFKD", heading).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "untitled"


def strip_gutenberg(lines: list[str]) -> list[str]:
    start, end = 0, len(lines)
    for i, line in enumerate(lines):
        if line.startswith("*** START"):
            start = i + 1
        elif line.startswith("*** END"):
            end = i
            break
    return lines[start:end]


def join_wrapped_headings(lines: list[str]) -> list[str]:
    """A long heading wraps onto a second line; join it back into one."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        cont = HEADING_CONT.match(lines[i])
        if cont and i + 1 < len(lines):
            tail = HEADING.match(lines[i + 1])
            if tail:
                out.append(f"    {cont.group(1).strip()} {tail.group(1).strip()}.")
                i += 2
                continue
        out.append(lines[i])
        i += 1
    return out


def split_entries(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Return (heading, body lines) for every ALL CAPS heading."""
    lines = join_wrapped_headings(lines)
    entries: list[tuple[str, list[str]]] = []
    heading: str | None = None
    body: list[str] = []
    for line in lines:
        match = HEADING.match(line)
        if match:
            if heading is not None:
                entries.append((heading, body))
            heading, body = match.group(1).strip(), []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        entries.append((heading, body))
    return entries


def sections(body: list[str]) -> list[tuple[str, str]]:
    """Split an entry body on its _Section._] markers."""
    text = "\n".join(body)
    marks = list(SECTION.finditer(text))
    if not marks:
        return []
    out = []
    for i, mark in enumerate(marks):
        stop = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        chunk = text[mark.end() : stop]
        cut = BACKMATTER.search(chunk)
        if cut:
            chunk = chunk[: cut.start()]
        name = (mark.group(1) or mark.group(2) or "").strip()
        out.append((name, chunk.strip()))
    return out


def clean(text: str) -> str:
    text = re.sub(r"\[Illustration:[^\]]*\]", " ", text)
    text = text.replace("_", "")
    text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def trim_to_herbs(lines: list[str]) -> list[str]:
    """Drop everything from the end of the herb entries onwards.

    Only END_OF_HERBS is used here, not BACKMATTER: the transcriber's note sits
    at the top of the file, so trimming on it would discard the whole book.
    """
    for i, line in enumerate(lines):
        if END_OF_HERBS.match(line):
            return lines[:i]
    return lines


def passages_in(heading: str, body: list[str]) -> list[tuple[str, str]]:
    """The virtues section, or the whole entry when it carries no section markers.

    Roughly one entry in six (Camomile, Elder, Primroses and others) is written
    as unbroken prose with no _Government and virtues._] marker. Requiring the
    marker silently dropped them.
    """
    found = sections(body)
    if found:
        return [(name, chunk) for name, chunk in found if VIRTUES.search(name)]

    text = "\n".join(body)
    cut = BACKMATTER.search(text)
    if cut:
        text = text[: cut.start()]
    return [("unsectioned", text.strip())]


def build() -> list[Passage]:
    raw = RAW_PATH.read_text(encoding="utf-8")
    lines = [line.rstrip("\r") for line in raw.split("\n")]
    entries = split_entries(trim_to_herbs(strip_gutenberg(lines)))

    # Front matter before the first properly sectioned entry is not a herb.
    first = next((i for i, (_, body) in enumerate(entries) if sections(body)), 0)
    entries = entries[first:]

    passages: list[Passage] = []
    seen: dict[str, int] = {}
    for heading, body in entries:
        for name, chunk in passages_in(heading, body):
            text = clean(chunk)
            if len(text.split()) < 20:
                continue
            slug = slugify(heading)
            seen[slug] = seen.get(slug, 0) + 1
            suffix = f"-{seen[slug]}" if seen[slug] > 1 else ""
            passages.append(
                Passage(
                    passage_id=f"{CORPUS_ID}:{slug}{suffix}",
                    corpus_id=CORPUS_ID,
                    heading=heading,
                    section=name,
                    text=text,
                    word_count=len(text.split()),
                )
            )
    return passages


def main() -> None:
    if not RAW_PATH.exists():
        print(f"No corpus at {RAW_PATH}")
        print("Run first:  uv run python -m ethnohack.fetch_culpeper")
        return

    passages = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as handle:
        for passage in passages:
            handle.write(json.dumps(asdict(passage), ensure_ascii=False) + "\n")

    counts = sorted(p.word_count for p in passages)
    median = counts[len(counts) // 2] if counts else 0
    print(f"{len(passages)} passages -> {OUT_PATH}")
    print(f"words per passage: min {counts[0]}, median {median}, max {counts[-1]}\n")

    print("First three headings:")
    for passage in passages[:3]:
        print(f"  {passage.passage_id}  ({passage.word_count} words)")

    sample = next((p for p in passages if "agrimony" in p.passage_id), passages[0])
    print(f"\nSample — {sample.passage_id}:\n")
    print("  " + sample.text[:400] + " ...")


if __name__ == "__main__":
    main()
