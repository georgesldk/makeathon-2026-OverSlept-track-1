"""Wikipedia descriptions for every candidate species of a book (WEAK evidence, rule D7).

Usage:  python3 description_sources/wikipedia/source_wikipedia.py --book culpeper
        python3 description_sources/wikipedia/source_wikipedia.py --book dioscorides

Which species: description_sources/targets.py (top 3 species candidates per herb, plus
the first that fits the geography check). One official MediaWiki API call per species,
no key; redirects are followed, so the scientific name finds a page filed under its
common name ("Inula helenium" -> "Elecampane"). From each article it keeps the
description section ("Description", "Botany", "Morphology" ...), or the lead with a note.
Wikipedia can lower confidence in a candidate but never lifts one to tier A on its own.
Output: description_sources/wikipedia/<book>/wikipedia.json. Cache: wikipedia/cache/
(shared by both books and by test_wikipedia.py, so nothing is fetched twice).
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import test_wikipedia as W            # article(), description(): the tested fetch and cut
from targets import targets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="culpeper", choices=["culpeper", "dioscorides"])
    book = ap.parse_args().book
    todo = targets(book)
    out_path = HERE / book / "wikipedia.json"
    out_path.parent.mkdir(exist_ok=True)
    species, counts = {}, {"description section": 0, "lead only": 0, "no article": 0, "error": 0}
    for n, (name, t) in enumerate(sorted(todo.items()), 1):
        try:
            page = W.article(name)
        except Exception as e:
            species[name] = {"evidence": "weak", "found": False, "error": str(e)[:200], "herbs": t["herbs"]}
            counts["error"] += 1
            continue
        if page.get("missing"):
            species[name] = {"evidence": "weak", "found": False, "herbs": t["herbs"]}
            counts["no article"] += 1
        else:
            head, text = W.description(page.get("extract") or "")
            lead = head.startswith("lead")
            species[name] = {"evidence": "weak", "found": True, "article": page["title"], "url": page.get("fullurl"),
                             "section": head, "text": text, "herbs": t["herbs"]}
            counts["lead only" if lead else "description section"] += 1
        if n % 50 == 0:
            print(f"  {n}/{len(todo)} · {W.CALLS[0]} new calls · {counts}")
    out_path.write_text(json.dumps({"book": book, "source": "Wikipedia (en), MediaWiki API", "licence": "CC BY-SA 4.0",
                                    "evidence": "weak", "counts": counts, "species": species},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{book}: {len(todo)} species · {counts}\n{W.CALLS[0]} new Wikipedia calls. "
          f"Saved to description_sources/wikipedia/{book}/wikipedia.json")


if __name__ == "__main__":
    main()
