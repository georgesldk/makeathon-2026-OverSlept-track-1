"""BHL descriptions (historical floras) for the main candidate species of a book (rule D7).

Usage:  python3 description_sources/bhl/source_bhl.py --book culpeper
        python3 description_sources/bhl/source_bhl.py --book dioscorides

Which species: description_sources/targets.py (per herb, the top species candidate and the
first that fits the geography check). For each, the same tested steps as test_bhl.py:
the accepted name plus up to 6 WCVP synonyms (old floras use old names), BHL pages in
botany books (regional floras first: British for Culpeper, Mediterranean for Dioscorides),
only pages where the name heads an entry, OCR misreadings undone, at most one page per
book, the best 2 kept, 8 more pages read if nothing is usable.
Needs BHL_API_KEY in .env and the WCVP download. Slow (10-25 calls per species) but
resumable: every reply is cached, so stop it any time and rerun.
Output: description_sources/bhl/<book>/bhl.json. Cache: bhl/cache/ (shared with the test).
"""
import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import test_bhl as T                  # the tested scoring: score_page(), pick(), ocr(), clean()
from targets import targets

REGION = {"culpeper": "britain", "dioscorides": "mediterranean"}
NAMES_CACHE = T.CACHE / "names"       # slimmed name lookups: BHL's full replies run to megabytes


def synonyms(names: list) -> dict:
    """Accepted name -> species-rank synonyms in WCVP, oldest first (one pass over WCVP)."""
    want = set(names)
    acc, syn = {}, {}
    with open(T.WCVP, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="|", quoting=csv.QUOTE_NONE))
    for r in rows:
        if r["taxon_status"] == "Accepted" and r["taxon_name"] in want:
            acc[r["plant_name_id"]] = r["taxon_name"]
    for r in rows:
        n = acc.get(r["accepted_plant_name_id"])
        if n and r["taxon_name"] != n and r["taxon_rank"] == "Species":
            y = re.search(r"\d{4}", r["first_published"] or "")
            syn.setdefault(n, set()).add((int(y.group()) if y else 9999, r["taxon_name"]))
    return {n: [s for _, s in sorted(syn.get(n, ()))][:T.MAX_SYNONYMS] for n in names}


def pages_for(name: str) -> list:
    """BHL pages naming `name`, in botany books only; cached slim."""
    NAMES_CACHE.mkdir(parents=True, exist_ok=True)
    path = NAMES_CACHE / (re.sub(r"\W+", "_", name) + ".json")
    if path.exists():
        return json.load(open(path, encoding="utf-8"))
    q = urllib.parse.urlencode({"op": "GetNameMetadata", "name": name, "format": "json", "apikey": T.key()})
    req = urllib.request.Request(f"{T.API}?{q}", headers={"User-Agent": "EthnoHack-OverSlept/0.1"})
    with urllib.request.urlopen(req, timeout=120, context=T.CTX) as r:
        data = json.load(r)
    T.CALLS[0] += 1
    time.sleep(0.5)
    words = T.BOTANY + T.REGIONAL["britain"] + T.REGIONAL["mediterranean"]
    out = []
    res = data.get("Result") if isinstance(data, dict) else None
    for n in (res if isinstance(res, list) else [res]):      # BHL sends null for names it does not know
        for t in (n or {}).get("Titles") or []:
            title = (t or {}).get("FullTitle") or (t or {}).get("ShortTitle") or ""
            if not any(w in title.lower() for w in words):
                continue
            for it in t.get("Items") or []:
                for p in (it or {}).get("Pages") or []:
                    if not p:
                        continue
                    out.append({"title": title, "year": it.get("Year") or t.get("PublicationDate"),
                                "page_id": p.get("PageID"), "url": p.get("PageUrl"), "name": name, "item_id": it.get("ItemID")})
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def describe(name: str, names: list, region: str) -> dict:
    pages = []
    for n in names:
        try:
            pages += pages_for(n)
        except Exception as e:
            print(f"    ! {n}: {str(e)[:100]}")
    pages.sort(key=lambda p: (not any(w in p["title"].lower() for w in T.REGIONAL[region]),
                              not any(w in p["title"].lower() for w in T.REGIONAL["britain"] + T.REGIONAL["mediterranean"]),
                              str(p["year"] or "")))
    seen, short = set(), []
    for p in pages:                                   # at most 2 pages per book
        if sum(1 for q in short if q["title"] == p["title"]) < 2 and p["page_id"] not in seen:
            short.append(p)
            seen.add(p["page_id"])
        if len(short) >= 2 * T.SHORTLIST:
            break
    scored = [x for p in short[:T.SHORTLIST] if (x := T.score_page(p, names))]
    keep = T.pick(scored)
    if not keep and len(short) > T.SHORTLIST:
        scored += [x for p in short[T.SHORTLIST:] if (x := T.score_page(p, names))]
        keep = T.pick(scored)
    return {"names_searched": names, "pages_found": len(pages), "pages_read": len(scored),
            "found": bool(keep), "kept": [{k: v for k, v in x.items() if k != "item_id"} for x in keep]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="culpeper", choices=["culpeper", "dioscorides"])
    book = ap.parse_args().book
    todo = {n: t for n, t in targets(book).items() if t["bhl"]}
    out_path = HERE / book / "bhl.json"
    out_path.parent.mkdir(exist_ok=True)
    print(f"{book}: {len(todo)} species. Reading WCVP synonyms (about 30 s) ...")
    syn = synonyms(list(todo))
    species, t0 = {}, time.time()

    def save():
        found = sum(v["found"] for v in species.values())
        out_path.write_text(json.dumps({"book": book, "source": "Biodiversity Heritage Library, API v3",
                                        "region_first": REGION[book], "found": found, "species": species},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
        return found

    for n, (name, t) in enumerate(sorted(todo.items()), 1):
        names = [x.replace("× ", "") for x in [name] + syn.get(name, [])]   # floras write "Iris germanica"
        species[name] = {**describe(name, names, REGION[book]), "herbs": t["herbs"]}
        if n % 10 == 0:
            found = save()
            print(f"  {n}/{len(todo)} · description found for {found} · {T.CALLS[0]} new calls · {time.time() - t0:.0f}s")
    found = save()
    print(f"\n{book}: description found for {found} of {len(todo)} species. {T.CALLS[0]} new BHL calls. "
          f"Saved to description_sources/bhl/{book}/bhl.json")


if __name__ == "__main__":
    main()
