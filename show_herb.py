"""Show one herb (Culpeper) or chapter (Dioscorides) through every step of the pipeline.

Usage:  python3 show_herb.py "Amara Dulcis"                     # Culpeper (default book)
        python3 show_herb.py --book dioscorides 4.75            # Dioscorides, by chapter
        python3 show_herb.py --book dioscorides mandragoras     # ... or by headword (Greek or Latin)
        add --all to list every candidate, the IDs and the weak evidence too

Read-only: it only reads files the pipeline has already written and changes nothing.
Sections: the answer first, then the book, which sources point to which plant, and each
candidate plant in plain words (name check, first publication, does it grow there).
"""
import json
import re
import sys
import textwrap
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
BOOK = sys.argv[sys.argv.index("--book") + 1] if "--book" in sys.argv else "culpeper"
if "--book" in sys.argv:
    ARGS.remove(BOOK)
ALL = "--all" in sys.argv
M = ROOT / "matching" / BOOK
WIDTH = 92
SOURCES = {  # column label for each source / bridge, in display order
    "culpeper": {"gbif": "GBIF", "wikidata": "Wikidata", "inaturalist": "iNat", "checklistbank": "Checklists",
                 "taxtree": "NCBI", "drduke": "Duke"},
    "dioscorides": {"lexicon_this_chapter": "LSJ here", "lexicon_headword": "LSJ", "lexicon_latin": "L&S",
                    "wikidata_grc": "WD grc", "wikidata_la": "WD la", "lexicon_synonym": "LSJ syn",
                    "wikidata_el": "WD el", "same_word_genus": "genus", "wikidata_la_same_word": "genus"}}
WORLD = {"culpeper": "Britain", "dioscorides": "his world"}


def load(path: Path):
    if not path.exists():
        return None
    if path.suffix == ".jsonl":
        return [json.loads(l) for l in open(path, encoding="utf-8")]
    return json.load(open(path, encoding="utf-8"))


def plain(s) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("ς", "σ")
    return re.sub(r"[^\w]", "", s)


def say(text, indent=2, hang=2):
    print(textwrap.fill(str(text), WIDTH, initial_indent=" " * indent, subsequent_indent=" " * (indent + hang)))


def title(text):
    print(f"\n  {text.upper()}\n  {'─' * len(text)}")


# --- finding the herb ------------------------------------------------------------------
def find(want):
    w = plain(want)
    if BOOK == "culpeper":
        herbs = load(ROOT / "historical_texts" / "culpeper" / "herbs.json")["herbs"]
        return next((h for h in herbs if w in (plain(h["id"]), plain(h["name"]))), None) or \
            next((h for h in herbs if any(plain(n) == w for n in h["other_names"])), None)
    chapters = [c for c in load(ROOT / "historical_texts" / "dioscorides" / "chapters.json")["chapters"]
                if c["chapter"] != "preface"]
    return next((c for c in chapters if want in (c["label"], c["id"])), None) or \
        next((c for c in chapters if w in (plain(c["headword"]), plain(c["headword_latin"]))), None) or \
        next((c for c in chapters if any(plain(n["name"]) == w for n in c["text_names"] + c["rv_names"])), None)


# --- plain-language labels ----------------------------------------------------------------
def geo_words(g):
    if not g:
        return None
    label, regions = g["geography"], ", ".join(g["native_regions"][:3])
    if label.startswith("not checked"):
        return None
    if label.startswith("no distribution"):
        return f"Grows in {WORLD[BOOK]}?  unknown (no distribution data)"
    if BOOK == "culpeper":
        if label.startswith("local"):
            how = "native" if "native" in label else "introduced"
            return f"Grows in Britain?  yes ({how})"
        if label == "european":
            return "Grows in Britain?  no, but native elsewhere in Europe"
        return f"Grows in Britain?  no; native in {regions}"
    if label == "local":
        return "Grows in his world?  yes (Mediterranean / Near East)"
    if label == "trade":
        return f"Grows in his world?  in his trade world ({regions})"
    if label.startswith("introduced"):
        return "Grows in his world?  only as an introduction (possibly after his time)"
    if label.startswith("impossible"):
        return f"Grows in his world?  no; native only in {regions} (unknown in his time)"
    return f"Grows in his world?  no; native in {regions}"


def check_words(g):
    a = g["agreements"]
    if "agree" in a and "disagree" not in a:
        both = "WFO and WCVP agree"
    elif "disagree" in a:
        both = "WFO and WCVP differ: " + "; ".join(o for o in g["wcvp_opinions"] if o != g["accepted_name"])[:60]
    elif "only WFO" in a:
        both = "only in WFO"
    elif "only WCVP" in a:
        both = "only in WCVP"
    else:
        both = "only Global Names"
    pub = next((p for p in g.get("ipni_publication") or [] if p["author_matches_accepted_name"]), None)
    year = f" · first published {pub['year']}" if pub and pub.get("year") else ""
    return f"Name check:  accepted name, {both}{year}"


# --- sections ------------------------------------------------------------------------------
def answer(top, fit):
    title("Answer")
    if not top:
        say("No plant found with strong or medium evidence.")
        return
    srcs = len(top["source_families"])
    say(f"Most likely:  {top['accepted_name']}  ({top['family'] or '?'})")
    say(f"because:      {', '.join(top['culpeper_names'])} → {srcs} independent source{'s' * (srcs != 1)}"
        f"{' · named for this very chapter' if BOOK == 'dioscorides' and top['strong_rows'] else ''}", hang=14)
    if fit and fit != top["accepted_name"]:
        say(f"but:          it does not grow in {WORLD[BOOK]}; the best candidate that does is {fit}", hang=14)
    elif fit:
        say(f"fits:         grows in {WORLD[BOOK]}")


def book(item):
    title("1. The book")
    if BOOK == "culpeper":
        say(f"{item['name']}  ·  page {item.get('page')}")
        say(f"Also called:  {', '.join(item['other_names']) or '—'}", hang=14)
        for q in item.get("name_evidence") or []:
            say(f"Quote:        “{q['quote'][:200]}{'…' if len(q['quote']) > 200 else ''}”", hang=14)
        return
    c = item
    say(f"Chapter {c['label']}:  {c['headword']}  ({c['headword_latin']})  ·  Wellmann vol. {c['volume']}, p. {c['page']}")
    say(f"Opens:        {c['opening']}", hang=14)
    lex = load(ROOT / "historical_texts" / "dioscorides" / "lexicon_lsj.json")
    latin = {}
    if lex:
        ch = next((x for x in lex["chapters"] if x["label"] == c["label"]), None)
        latin = {n["name"]: n["latin_form"] for n in (ch or {}).get("names", [])}
    for head, names in (("His own names", c["text_names"]), ("Name lists", c["rv_names"])):
        if not names:
            continue
        by = defaultdict(list)
        for n in names:
            by[n["attributed_to"] or "—"].append(f"{n['name']} ({latin.get(n['name'], '')})")
        shown = list(by.items()) if ALL else list(by.items())[:6]
        say(f"{head}:")
        for who, ns in shown:
            say(f"{who:<12} {', '.join(ns[: (99 if ALL else 4)])}{' …' if len(ns) > 4 and not ALL else ''}", 6, 13)
        if len(by) > len(shown):
            say(f"… and {len(by) - len(shown)} more groups (--all)", 6)


def sources(rows):
    title("2. Which sources point to which plant")
    if rows is None:
        say(f"(not available: run python3 matching/{BOOK}/aggregate.py)")
        return
    cols = SOURCES[BOOK]
    key = "source" if BOOK == "culpeper" else "bridge"
    labels = list(dict.fromkeys(cols.values()))
    grid = defaultdict(set)
    weak = no_name = 0
    for r in rows:
        if not r["node"]:
            no_name += 1
        elif r["grade"] == "weak" and not ALL:
            weak += 1
        else:
            grid[r["node"]].add(cols.get(r[key], r[key]))
    used = [l for l in labels if any(l in s for s in grid.values())]
    if not grid:
        say("No source gave a plant with strong or medium evidence.")
    else:
        names = sorted(grid, key=lambda n: (-len(grid[n]), n))[: (60 if ALL else 8)]
        w = max(len(n) for n in names) + 2
        print("  " + " " * w + "  ".join(f"{l:^9}" for l in used))
        for n in names:
            print("  " + f"{n:<{w}}" + "  ".join(f"{'✓' if l in grid[n] else '·':^9}" for l in used))
        if len(grid) > len(names):
            say(f"… and {len(grid) - len(names)} more plants (--all)")
    notes = []
    if weak:
        notes.append(f"{weak} weak matches")
    if no_name:
        notes.append(f"{no_name} hits without a scientific name")
    if notes:
        say(f"Not shown: {', '.join(notes)}" + ("" if ALL else " (--all)"))
    if BOOK == "dioscorides":
        say("LSJ here = the Greek dictionary names this plant for this very chapter (strongest); "
            "L&S = Latin dictionary; WD = Wikidata label in Ancient Greek / Latin / modern Greek")


def plants(hc, geo):
    title("3. Candidate plants (after WFO, WCVP, Global Names, IPNI)")
    if hc is None:
        say(f"(not available: run python3 matching/resolve_scientific.py --book {BOOK})")
        return []
    geo_by = {g["accepted_name"]: g for g in (geo or {}).get("candidates", [])}
    res = [g for g in hc["candidates"] if g["resolved"] and (ALL or g["culpeper_names"] or g["strong_rows"])]
    species = [g for g in res if g["rank"] not in ("genus", "family")]
    higher = [g for g in res if g["rank"] in ("genus", "family")]
    shown = species if ALL else species[:5]
    for i, g in enumerate(shown, 1):
        grade = "strong" if g["strong_rows"] else "medium" if g["culpeper_names"] else "weak"
        srcs = len(g["source_families"])
        print()
        say(f"{i}. {g['accepted_name']}  ·  {g['family'] or '?'}")
        say(f"Evidence:    {grade}; from {', '.join(g['culpeper_names']) or '—'} "
            f"({srcs} independent source{'s' * (srcs != 1)})", 5, 13)
        olds = [s["name"] for s in g["scientific_names"] if plain(s["name"]) != plain(g["accepted_name_without_authors"])]
        if olds:
            say(f"Old names:   {', '.join(olds[:5])} (merged into this name)", 5, 13)
        say(check_words(g), 5, 13)
        gw = geo_words(geo_by.get(g["accepted_name"]))
        if gw:
            say(gw, 5, 13)
        if ALL:
            say(f"IDs:         WFO {g['wfo_id'] or '—'} · WCVP {g['wcvp_id'] or '—'} · decided by {g['decided_by']}", 5, 13)
    print()
    if higher:
        say("Also matched at genus / family level only: " + ", ".join(g["accepted_name"] for g in higher[:6]))
    more = len(species) - len(shown)
    unres = sum(1 for g in hc["candidates"] if not g["resolved"])
    weaker = sum(1 for g in hc["candidates"] if g["resolved"]) - len(res)
    extra = [f"{more} more species" if more > 0 else "", f"{weaker} weaker candidates" if weaker else "",
             f"{unres} name{'s' * (unres != 1)} that {'are' if unres != 1 else 'is'} not a plant or not found" if unres else ""]
    extra = [e for e in extra if e]
    if extra:
        say("Not shown: " + ", ".join(extra) + ("" if ALL else " (--all)"))
    return shown


def main() -> None:
    if not ARGS:
        sys.exit(__doc__)
    want = " ".join(ARGS)
    item = find(want)
    if not item:
        sys.exit(f"No {'herb' if BOOK == 'culpeper' else 'chapter'} called '{want}' in {BOOK}.")
    hid = item["id"]
    name = item.get("name") or f"{item['label']} {item['headword']}"
    print(f"\n{'═' * WIDTH}\n  {BOOK.capitalize()}  ·  {name}\n{'═' * WIDTH}")
    hc = (load(M / "herb_candidates_resolved.json") or {}).get("herbs", {}).get(hid)
    geo = (load(M / "geography.json") or {}).get("herbs", {}).get(hid)
    ev = load(M / "evidence.jsonl")
    rows = None if ev is None else [r for r in ev if (r.get("herb") or r.get("chapter")) == hid]

    res = [g for g in (hc or {}).get("candidates", []) if g["resolved"] and g["culpeper_names"]
           and g["rank"] not in ("genus", "family")]
    answer(res[0] if res else None, (geo or {}).get("first_candidate_that_fits"))
    book(item)
    sources(rows)
    plants(hc, geo)
    print()


if __name__ == "__main__":
    main()
