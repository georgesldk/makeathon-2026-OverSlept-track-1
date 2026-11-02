"""Hand-check extracted claims, one at a time.

    uv run python -m ethnohack.review --limit 5

Shows the passage, then each claim. For every claim you answer:

    y  a real therapeutic claim, correctly extracted
    n  not a claim, or wrong (an action, an organ, a fragment, astrology)
    q  quote is not word for word from the passage
    ?  unsure

At the end of each passage you say how many real claims it MISSED. That is the
number nothing else can tell us: a missed claim leaves no trace in the output.

Answers are saved to data/review/ and can be resumed. Running it again skips
passages already reviewed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from ethnohack.config import REPO_ROOT, load
from ethnohack.schema import StoredExtraction

CACHE_DIR = REPO_ROOT / "data" / "cache" / "extractions"
PASSAGES_PATH = REPO_ROOT / "data" / "passages" / "culpeper_1653.jsonl"
REVIEW_DIR = REPO_ROOT / "data" / "review"

VERDICTS = {
    "y": "correct",
    "w": "wrong_label",
    "n": "not_a_claim",
    "q": "bad_quote",
    "?": "unsure",
}

# wrong_label is a real claim the model found but named badly: the organ instead
# of the complaint ("spleen"), the action instead of the condition ("draws forth
# the dead child"), or an unresolved fragment ("pains thereof"). These are
# recoverable, because the quote is right — a prompt fix or a normalisation step
# rescues them. not_a_claim is not recoverable.

KEY_HELP = "y correct · w real claim but wrong label · n not a claim · q bad quote · ? unsure"


def wrap(text: str, width: int = 88, indent: str = "  ") -> str:
    words, line, out = text.split(), "", []
    for word in words:
        if len(line) + len(word) + 1 > width:
            out.append(indent + line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(indent + line)
    return "\n".join(out)


def passages() -> dict[str, dict]:
    if not PASSAGES_PATH.exists():
        sys.exit(f"No passages at {PASSAGES_PATH}")
    with PASSAGES_PATH.open(encoding="utf-8") as handle:
        return {row["passage_id"]: row for row in (json.loads(line) for line in handle)}


def ask(prompt: str, allowed: set[str]) -> str:
    while True:
        answer = input(prompt).strip().lower()
        if answer in allowed:
            return answer
        print(f"  please answer one of: {', '.join(sorted(allowed))}")


def show_claim(i: int, total: int, claim) -> None:
    bits = [claim.plant_part, claim.preparation, claim.route]
    detail = ", ".join(b for b in bits if b) or "unspecified"
    print(f"\n[{i}/{total}]  {claim.plant_name_verbatim} -> {claim.condition_verbatim}")
    print(f"       {detail}")
    print(wrap(f'"{claim.quote}"', indent="       "))


def ask_all_at_once(count: int) -> list[str]:
    """Take every verdict for a passage in one line, e.g. yynwq?y..."""
    print("\n" + "-" * 92)
    print(KEY_HELP)
    print(f"Type {count} letters, one per claim, in order. Spaces and commas are ignored.")
    while True:
        raw = input(f"{count} verdicts > ").strip().lower()
        letters = [c for c in raw if not c.isspace() and c != ","]
        bad = sorted({c for c in letters if c not in VERDICTS})
        if bad:
            print(f"  not a key: {', '.join(bad)}")
            continue
        if len(letters) != count:
            print(f"  got {len(letters)}, need {count}")
            continue
        return letters


def review_one(stored: StoredExtraction, passage: dict, reviewer: str, one_by_one: bool) -> dict:
    total = len(stored.claims)
    print("\n" + "=" * 92)
    print(f"{stored.heading}   ({stored.passage_id})   {total} claims")
    print("=" * 92 + "\n")
    print(wrap(passage["text"]))
    print("\n" + "-" * 92)

    rows = []
    if one_by_one:
        for i, claim in enumerate(stored.claims, 1):
            show_claim(i, total, claim)
            print(f"       {KEY_HELP}")
            answer = ask("       > ", set(VERDICTS))
            rows.append(
                {"index": i, "condition": claim.condition_verbatim, "verdict": VERDICTS[answer]}
            )
    else:
        for i, claim in enumerate(stored.claims, 1):
            show_claim(i, total, claim)
        for i, (claim, answer) in enumerate(
            zip(stored.claims, ask_all_at_once(total), strict=True), 1
        ):
            rows.append(
                {"index": i, "condition": claim.condition_verbatim, "verdict": VERDICTS[answer]}
            )

    # A wrong label is recoverable, so capture the right one while the passage is in view.
    for row in rows:
        if row["verdict"] == "wrong_label":
            fixed = input(f"  [{row['index']}] {row['condition']!r} should be > ").strip()
            if fixed:
                row["corrected_condition"] = fixed

    print("\n" + "-" * 92)
    print("Now re-read the passage above. Claims the model NEVER listed — how many?")
    print(f"(Usually 0. It already found {len(stored.claims)}. Press Enter for 0.)")
    while True:
        raw = input("Claims MISSED > ").strip()
        if raw == "":
            missed = 0
            break
        if raw.isdigit():
            missed = int(raw)
            if missed > len(stored.claims):
                print(f"  {missed} missed but only {len(stored.claims)} found — sure? y to confirm")
                if input("  > ").strip().lower() != "y":
                    continue
            break
        print("  a number, or Enter for 0")

    return {
        "passage_id": stored.passage_id,
        "heading": stored.heading,
        "model": stored.model,
        "reviewer": reviewer,
        "reviewed_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "claims": rows,
        "missed": missed,
    }


def summarise(all_rows: list[dict]) -> None:
    claims = [c for row in all_rows for c in row["claims"]]
    if not claims:
        return
    counts = {v: sum(1 for c in claims if c["verdict"] == v) for v in VERDICTS.values()}
    missed = sum(row["missed"] for row in all_rows)
    correct = counts["correct"]
    total = len(claims)

    print("\n" + "=" * 92)
    print(f"{len(all_rows)} passages, {total} claims reviewed\n")
    for name, count in counts.items():
        print(f"  {name:<14} {count}")
    print(f"  {'missed':<14} {missed}")

    recoverable = correct + counts["wrong_label"]
    precision = correct / total if total else 0.0
    recall = correct / (correct + missed) if (correct + missed) else 0.0
    print(f"\n  precision   {precision:.0%}   (of extracted claims, how many were right)")
    print(f"  recall      {recall:.0%}   (of real claims, how many were caught)")
    if counts["wrong_label"]:
        print(
            f"  recoverable {recoverable / total:.0%}   "
            f"(right quote, fixable label: {recoverable}/{total})"
        )

    print("\nGo / no-go: if precision is below about 70%, fix the prompt before")
    print("the full sweep. If recall is low, the problem is the passage split.")
    print("A large gap between precision and recoverable means the labels are the")
    print("problem, not the extraction — a prompt fix, not a redesign.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hand-check extracted claims.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--reviewer", default="", help="Your name, for inter-annotator agreement")
    parser.add_argument(
        "--one-by-one",
        action="store_true",
        help="Answer each claim as it appears, instead of all at once per passage",
    )
    args = parser.parse_args()

    reviewer = args.reviewer or input("Your name (for the record): ").strip() or "anon"
    settings = load()
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(CACHE_DIR.glob("*.json"))
    if not files:
        sys.exit(f"No extractions in {CACHE_DIR}\nRun: uv run python -m ethnohack.extract --limit 5")

    corpus = passages()
    done: list[dict] = []
    reviewed = 0

    for path in files:
        if reviewed >= args.limit:
            break
        stored = StoredExtraction.model_validate_json(path.read_text(encoding="utf-8"))
        out_path = REVIEW_DIR / f"{stored.passage_id.replace(':', '__')}__{reviewer}.json"
        if out_path.exists():
            done.append(json.loads(out_path.read_text(encoding="utf-8")))
            continue
        passage = corpus.get(stored.passage_id)
        if passage is None:
            continue
        row = review_one(stored, passage, reviewer, args.one_by_one)
        out_path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        done.append(row)
        reviewed += 1

    summarise(done)
    print(f"\nSaved to {REVIEW_DIR}")
    print(f"Model reviewed: {settings.gemini_model}")


if __name__ == "__main__":
    main()
