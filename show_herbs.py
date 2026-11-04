"""Print everything extracted for a few Culpeper herbs: the book and GBIF.

Usage:  python3 show_herbs.py                          # the first 3 herbs in the book
        python3 show_herbs.py "Carduus Benedictus" Alehoof
        python3 show_herbs.py --full                   # full text and every result

Reads only files already written (no network):
  historical_texts/culpeper/herbs.json   the herb as extracted from the book
  common_name_sources/gbif/culpeper/gbif.json

By default the book text is shortened, exact matches are printed in full and
look-alike results are only counted; --full prints all of it.
"""
import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FULL = "--full" in sys.argv
SHORT = 200        # characters of each book section shown without --full
LOOKALIKES = 5     # look-alike names listed per search without --full


def load(path: str):
    p = ROOT / path
    return json.load(open(p, encoding="utf-8")) if p.exists() else None


def say(text: str, indent: int = 2) -> None:
    pad = " " * indent
    print(textwrap.fill(str(text), 78, initial_indent=pad, subsequent_indent=pad))


def head(title: str) -> None:
    print(f"\n  {title}\n  {'-' * len(title)}")


def short(text: str) -> str:
    return text if FULL or len(text) <= SHORT else text[:SHORT].rsplit(" ", 1)[0] + " ..."


def pick_herbs(herbs: list[dict], wanted: list[str]) -> list[dict]:
    if not wanted:
        return herbs[:3]
    found = []
    for w in wanted:
        m = [h for h in herbs if w.lower() in (h["id"], h["name"].lower())]
        if not m:
            close = [h["name"] for h in herbs if w.lower() in h["name"].lower()][:8]
            sys.exit(f"No herb called {w!r}." + (f" Did you mean: {', '.join(close)}?" if close else ""))
        found.append(m[0])
    return found


def show_book(h: dict) -> None:
    head("THE BOOK  (historical_texts/culpeper/herbs.json)")
    say(f"id: {h['id']}    page: {h['page']}" + (f" (also printed on page {h['also_printed_on_page']})"
                                                  if h.get("also_printed_on_page") else ""))
    say(f"heading: {h['heading']}")
    say(f"name: {h['name']}")
    say(f"other names: {', '.join(h['other_names']) or '-'}")
    for ev in h["name_evidence"]:
        note = f"  [{ev['note']}]" if ev.get("note") else ""
        say(f'evidence: "{ev["quote"]}" -> {", ".join(ev["names"]) or "-"}{note}', 4)
    if h.get("intro"):
        say(f"intro: {short(h['intro'])}", 4)
    for k, v in h["sections"].items():
        say(f"{k}: {short(v)}", 4)
    for s in h.get("subsections", []):
        say(f"subsection: {s}", 4)


def describe(t: dict) -> str:
    bits = [t.get("scientificName", "?"), t.get("rank", "").lower(), t.get("family") or ""]
    if t.get("synonym") or t.get("taxonomicStatus", "ACCEPTED") != "ACCEPTED":
        bits.append(f"{t.get('taxonomicStatus', '').lower()} of {t.get('accepted', '?')}")
    return " | ".join(b for b in bits if b)


def show_gbif(h: dict, gbif) -> None:
    head("GBIF  (common_name_sources/gbif/culpeper/gbif.json)")
    if gbif is None or "taxa" not in gbif:
        say("No GBIF data in the new format yet. Run:  python3 common_name_sources/gbif/culpeper/source_gbif.py --limit 3")
        return
    entry, taxa = gbif["herbs"].get(h["id"]), gbif["taxa"]
    if entry is None:
        say("This herb has not been searched yet (run the GBIF script on all herbs).")
        return
    for nm in entry["names"]:
        say(f"name: {nm['name']}")
        for s in nm["searches"]:
            res = s["results"]
            exact = [r for r in res if r["exact_name_match"]]
            other = [r for r in res if not r["exact_name_match"]]
            if not s["searched"]:
                say(f"searched as {s['spelling']!r}: not searched yet", 4)
                continue
            say(f"searched as {s['spelling']!r}: {len(res)} results, {len(exact)} exact", 4)
            for r in exact:
                t = taxa[str(r["key"])]
                say(f"EXACT  {describe(t)}  [key {t['key']}, names in: {', '.join(r['match_languages'])}]", 6)
                if FULL:
                    en = sorted({v["name"] for v in t.get("vernacularNames", []) if v["language"] in ("eng", "")})
                    say(f"English names: {', '.join(en) or '-'}", 13)
            shown = other if FULL else other[:LOOKALIKES]
            for r in shown:
                say(f"other  {describe(taxa[str(r['key'])])}", 6)
            if len(other) > len(shown):
                say(f"... and {len(other) - len(shown)} more look-alikes (--full shows them)", 6)


def main() -> None:
    herbs = load("historical_texts/culpeper/herbs.json")["herbs"]
    gbif = load("common_name_sources/gbif/culpeper/gbif.json")
    for h in pick_herbs(herbs, [a for a in sys.argv[1:] if a != "--full"]):
        print(f"\n{'=' * 80}\n{h['name'].upper()}\n{'=' * 80}")
        show_book(h)
        show_gbif(h, gbif)
    print()


if __name__ == "__main__":
    main()
