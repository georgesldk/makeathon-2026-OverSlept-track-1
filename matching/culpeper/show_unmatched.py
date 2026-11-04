"""List the Culpeper herbs that have no plant species candidate, and what they did get.

Usage:  python3 matching/culpeper/show_unmatched.py

Reads matching/culpeper/candidates.json (from aggregate.py) and historical_texts/culpeper/herbs.json.
A herb is listed when none of its strong candidates is a species that is not a
known non-plant. For each, it prints the names Culpeper uses, then the best
of what the sources did return:
  genus/family   strong hits above species level (e.g. "Mentha")
  weak species   species found only by a loose match (name inside a longer name,
                 or a TaxTree similar-name hit)
so a person can tell why the herb is unmatched: old spelling, a heading that
names two plants, a name no modern source uses, ...
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def main() -> None:
    cands = json.load(open(HERE / "candidates.json", encoding="utf-8"))
    herbs = {h["id"]: h for h in json.load(open(ROOT / "historical_texts" / "culpeper" / "herbs.json", encoding="utf-8"))["herbs"]}
    ok = lambda x: x["kingdom_flag"] != "non-plant"
    unmatched = [(hid, c) for hid, c in cands.items()
                 if not any(x["level"] == "species" and x["culpeper_names"] and ok(x) for x in c["candidates"])]

    print(f"\n{len(unmatched)} of {len(cands)} herbs have no plant species candidate\n")
    for i, (hid, c) in enumerate(unmatched, 1):
        h = herbs[hid]
        print(f"{i:>2}. {c['name'].upper()}   (page {h.get('page')})")
        if h["other_names"]:
            print(f"    Culpeper also calls it: {', '.join(h['other_names'])}")
        higher = [x for x in c["candidates"] if x["level"] != "species" and x["culpeper_names"] and ok(x)]
        weak = sorted((x for x in c["candidates"] if x["level"] == "species" and not x["culpeper_names"]
                       and x["weak_rows"] and ok(x)), key=lambda x: -x["weak_rows"])
        if higher:
            print("    genus/family: " + "; ".join(
                f"{x['scientific_name']} (from {', '.join(x['culpeper_names'])}; {len(x['families'])} sources)"
                for x in higher[:4]))
        if weak:
            print("    weak species: " + "; ".join(
                f"{x['scientific_name']} (via {', '.join(x['weak_culpeper_names'])})" for x in weak[:4]))
        if not higher and not weak:
            print("    nothing usable from any source")
        print()


if __name__ == "__main__":
    main()
