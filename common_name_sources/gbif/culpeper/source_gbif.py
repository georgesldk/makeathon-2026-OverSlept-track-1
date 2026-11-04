"""Collect everything GBIF returns for every name of every Culpeper herb.

Usage:  python3 common_name_sources/gbif/culpeper/source_gbif.py            # all herbs
        python3 common_name_sources/gbif/culpeper/source_gbif.py --limit 3  # first 3 herbs, for a test

Reads historical_texts/culpeper/herbs.json, writes common_name_sources/gbif/culpeper/gbif.json.
Raw GBIF replies are cached in common_name_sources/gbif/culpeper/cache/, so a rerun only asks
GBIF about spellings it has not seen yet.

No ranking and no picking: every result is kept, for later processing.
Each name of each herb (its main name and its other names) is searched in
GBIF's common names, restricted to plants in the GBIF Backbone, as written
and in simple spelling variants:
    hyphens as spaces and joined   "Night-shade" -> "Night shade", "Nightshade"
    singular of the last word      "Daisies" -> "Daisy"
    without a final Tree / Bush    "Ash Tree" -> "Ash"
Each result carries a flag saying whether one of its common names is exactly
the spelling searched (ignoring case, spaces, hyphens, apostrophes), and in
which languages. The flag is information only; nothing is dropped.

Output: "taxa" holds each GBIF taxon once (classification, accepted name,
common names); "herbs" lists, per herb and name, the taxa each spelling
returned, by key.
"""
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
HERBS = HERE.parent.parent.parent / "historical_texts" / "culpeper" / "herbs.json"
OUT = HERE / "gbif.json"
CACHE = HERE / "cache" / "gbif_search_full.json"

API = "https://api.gbif.org/v1/species/search"
BACKBONE = "d7dddbf4-2cf0-4f39-9b2a-bb099caae36c"   # GBIF Backbone Taxonomy
PLANTAE = 6                                          # kingdom key in the Backbone
PAGE = 100                                           # results read per search
PAUSE = 0.25                                         # seconds between calls
RETRY_WAITS = [5, 15, 30]                            # waits before retrying a failed call
GIVE_UP_AFTER = 10                                   # failures in a row before stopping
FIELDS = ["key", "scientificName", "canonicalName", "authorship", "rank",
          "taxonomicStatus", "synonym", "acceptedKey", "accepted",
          "kingdom", "phylum", "class", "order", "family", "genus",
          "species", "speciesKey"]


def ssl_context():
    """Use the Mac's certificate store if 'truststore' is installed."""
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CTX = ssl_context()


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "EthnoHack-OverSlept/0.1"})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return json.load(r)


def key(name: str) -> str:
    """Comparison form of a name: lower case, no spaces/hyphens/apostrophes."""
    return re.sub(r"[\s\-’'.]", "", name.lower())


def singular(word: str) -> str:
    w = word.lower()
    if w.endswith("ies") and len(w) > 4:
        return word[:-3] + "y"
    if w.endswith(("sses", "ches", "shes")):
        return word[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def spellings(name: str) -> list[str]:
    base = name.replace("’", "'")
    forms = [name,
             re.sub(r"\s+", " ", base.replace("-", " ")).strip(),
             re.sub(r"\s+", " ", base.replace("-", "")).strip()]
    extra = []
    for f in forms:
        words = f.split(" ")
        extra.append(" ".join(words[:-1] + [singular(words[-1])]))
        no_tree = re.sub(r"[\s-]*\b(?:Tree|Bush)$", "", f, flags=re.I).strip()
        if no_tree:
            extra.append(no_tree)
    return list(dict.fromkeys(forms + extra))


def search(q: str) -> list[dict]:
    params = {"q": q, "qField": "VERNACULAR", "datasetKey": BACKBONE,
              "highertaxonKey": PLANTAE, "limit": PAGE}
    data = get_json(API + "?" + urllib.parse.urlencode(params))
    out = []
    for r in data.get("results", []):
        rec = {f: r.get(f) for f in FIELDS if r.get(f) is not None}
        rec["vernacularNames"] = [{"name": v.get("vernacularName", ""), "language": v.get("language", "")}
                                  for v in r.get("vernacularNames", [])]
        out.append(rec)
    return out


def with_retries(q):
    for wait in [*RETRY_WAITS, None]:
        try:
            return search(q)
        except Exception as e:
            temporary = getattr(e, "code", 500) >= 500 or "timed out" in str(e)
            if wait is None or not temporary:
                raise
            time.sleep(wait)


def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    herbs = json.load(open(HERBS, encoding="utf-8"))["herbs"][:limit]
    CACHE.parent.mkdir(exist_ok=True)
    cache = json.load(open(CACHE, encoding="utf-8")) if CACHE.exists() else {}

    todo = sorted({q for h in herbs for n in [h["name"], *h["other_names"]] for q in spellings(n)}
                  - cache.keys())
    print(f"\nSearching GBIF for {len(herbs)} herbs "
          f"({len(todo)} spellings to ask about, {len(cache)} cached)\n")
    if todo:
        try:  # one test call first, so a network or certificate problem is obvious
            search("bittersweet")
        except Exception as e:
            sys.exit(f"Cannot reach GBIF ({e}).\nIf this is a certificate error, run:  pip install truststore")
    failed = 0
    for i, q in enumerate(todo, 1):
        try:
            cache[q] = with_retries(q)
            failed = 0
        except Exception as e:
            failed += 1
            print(f"  ! {q}: {e} (will retry on the next run)")
            if failed >= GIVE_UP_AFTER:
                CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                sys.exit("\nGBIF seems to be down. Progress is saved; run again later.")
            continue
        if i % 25 == 0 or i == len(todo):
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"  spellings asked: {i} of {len(todo)}")
        time.sleep(PAUSE)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    taxa, out = {}, {}
    for h in herbs:
        names = []
        for n in dict.fromkeys([h["name"], *h["other_names"]]):
            searches = []
            for q in spellings(n):
                results = []
                for r in cache.get(q, []):
                    taxa.setdefault(str(r["key"]), {f: v for f, v in r.items()})
                    langs = sorted({v["language"] or "?" for v in r["vernacularNames"]
                                    if key(v["name"]) == key(q)})
                    results.append({"key": r["key"], "exact_name_match": bool(langs),
                                    "match_languages": langs})
                searches.append({"spelling": q, "searched": q in cache, "results": results})
            names.append({"name": n, "searches": searches})
        out[h["id"]] = {"name": h["name"], "names": names}

    OUT.write_text(json.dumps({
        "source": "GBIF Species API, common-name search (qField=VERNACULAR), "
                  "GBIF Backbone, plants only, up to 100 results per spelling",
        "retrieved": date.today().isoformat(),
        "taxa": taxa,
        "herbs": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    n_names = sum(len(o["names"]) for o in out.values())
    hit = lambda nm: any(r["exact_name_match"] for s in nm["searches"] for r in s["results"])
    names_exact = sum(hit(nm) for o in out.values() for nm in o["names"])
    herbs_exact = sum(any(hit(nm) for nm in o["names"]) for o in out.values())
    n_res = sum(len(s["results"]) for o in out.values() for nm in o["names"] for s in nm["searches"])
    print(f"\n{len(herbs)} herbs, {n_names} names, {n_res} results kept "
          f"({len(taxa)} distinct GBIF taxa)\n")
    print(f"  {names_exact:>4} names have at least one exact common-name match")
    print(f"  {herbs_exact:>4} herbs have at least one exact common-name match")
    print(f"  {len(herbs) - herbs_exact:>4} herbs have only non-exact results, or none\n")
    size = OUT.stat().st_size / 1e6
    print(f"Saved to common_name_sources/gbif/culpeper/{OUT.name} ({size:.1f} MB)\n")


if __name__ == "__main__":
    main()
