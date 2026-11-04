"""Collect everything iNaturalist returns for every name of every Culpeper herb.

Usage:  python3 common_name_sources/inaturalist/culpeper/source_inaturalist.py            # all herbs
        python3 common_name_sources/inaturalist/culpeper/source_inaturalist.py --limit 3  # first 3 herbs

Reads historical_texts/culpeper/herbs.json, writes common_name_sources/inaturalist/culpeper/inaturalist.json.
Raw replies are cached in common_name_sources/inaturalist/culpeper/cache/, so a rerun only asks
about spellings it has not seen yet.

No ranking and no picking. Each name of each herb is searched, in the same
spelling variants as the GBIF script, with iNaturalist's taxa search
(/v1/taxa, restricted to plants, taxon 47126), which matches scientific and
common names in every language. Every taxon returned is kept with all its
names (each with language) and its place in the classification.

Each result carries, as information only:
  matched_term       the name iNaturalist says matched the search
  exact_name_match   matched_term equals the spelling searched (ignoring case,
                     spaces, hyphens, apostrophes)
  exact_name_locales languages of the taxon's names that equal the spelling

iNaturalist asks API users to stay around one request per second; this
script waits 1.1 s between calls, so a full run takes about 20 minutes.
"""
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
HERBS = ROOT / "historical_texts" / "culpeper" / "herbs.json"
OUT = HERE / "inaturalist.json"
CACHE = HERE / "cache" / "taxa_search.json"

API = "https://api.inaturalist.org/v1/taxa"
PLANTAE = 47126
PER_PAGE = 30
PAUSE = 1.1
RETRY_WAITS = [5, 15, 30, 60]
GIVE_UP_AFTER = 10
USER_AGENT = ("EthnoHack-OverSlept/0.1 "
              "(https://github.com/georgesldk/makeathon-2026-OverSlept-track-1)")
FIELDS = ["id", "name", "rank", "rank_level", "is_active", "parent_id", "ancestor_ids",
          "iconic_taxon_name", "preferred_common_name", "wikipedia_url", "observations_count"]

sys.path.insert(0, str(ROOT / "common_name_sources" / "gbif" / "culpeper"))
from source_gbif import spellings, key  # noqa: E402  (same spellings as every source)


def ssl_context():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CTX = ssl_context()


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return json.load(r)


def search(q: str) -> list[dict]:
    params = {"q": q, "taxon_id": PLANTAE, "all_names": "true", "per_page": PER_PAGE, "locale": "en"}
    data = get_json(API + "?" + urllib.parse.urlencode(params))
    out = []
    for r in data.get("results", []):
        rec = {f: r.get(f) for f in FIELDS if r.get(f) is not None}
        rec["matched_term"] = r.get("matched_term")
        rec["names"] = [{"name": n.get("name"), "locale": n.get("locale"), "lexicon": n.get("lexicon"),
                         "is_valid": n.get("is_valid")} for n in r.get("names", [])]
        out.append(rec)
    return out


def with_retries(q):
    for wait in [*RETRY_WAITS, None]:
        try:
            return search(q)
        except Exception as e:
            code = getattr(e, "code", 500)
            if wait is None or not (code >= 500 or code == 429 or "timed out" in str(e)):
                raise
            time.sleep(wait)


def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    herbs = json.load(open(HERBS, encoding="utf-8"))["herbs"][:limit]
    CACHE.parent.mkdir(exist_ok=True)
    cache = json.load(open(CACHE, encoding="utf-8")) if CACHE.exists() else {}
    wanted = sorted({q for h in herbs for n in [h["name"], *h["other_names"]] for q in spellings(n)})
    todo = [q for q in wanted if q not in cache]

    print(f"\nSearching iNaturalist for {len(herbs)} herbs "
          f"({len(todo)} spellings to ask, {len(cache)} cached; about {len(todo) * PAUSE / 60:.0f} min)\n")
    if todo:
        try:
            search("bittersweet")
        except Exception as e:
            sys.exit(f"Cannot reach iNaturalist ({e}).\nIf this is a certificate error, run:  pip install truststore")
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
                sys.exit("\niNaturalist seems to be down. Progress is saved; run again later.")
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
                    taxa.setdefault(str(r["id"]), r)
                    locales = sorted({x["locale"] or "?" for x in r["names"] if key(x["name"] or "") == key(q)})
                    results.append({"id": r["id"], "matched_term": r.get("matched_term"),
                                    "exact_name_match": key(r.get("matched_term") or "") == key(q),
                                    "exact_name_locales": locales})
                searches.append({"spelling": q, "searched": q in cache, "results": results})
            names.append({"name": n, "searches": searches})
        out[h["id"]] = {"name": h["name"], "names": names}

    OUT.write_text(json.dumps({
        "source": "iNaturalist API v1 taxa search (plants, taxon 47126), all names, up to 30 per spelling",
        "retrieved": date.today().isoformat(),
        "taxa": taxa,
        "herbs": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    hit = lambda nm: any(r["exact_name_match"] for s in nm["searches"] for r in s["results"])
    print(f"\n{len(herbs)} herbs, {sum(len(o['names']) for o in out.values())} names, "
          f"{len(taxa)} distinct iNaturalist taxa\n")
    print(f"  {sum(hit(nm) for o in out.values() for nm in o['names']):>4} names exactly match a taxon name")
    print(f"  {sum(any(hit(nm) for nm in o['names']) for o in out.values()):>4} herbs have at least one such name")
    print(f"\nSaved to common_name_sources/inaturalist/culpeper/{OUT.name} ({OUT.stat().st_size / 1e6:.1f} MB)\n")


if __name__ == "__main__":
    main()
