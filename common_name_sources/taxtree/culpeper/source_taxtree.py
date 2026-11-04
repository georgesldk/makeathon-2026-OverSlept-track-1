"""Collect everything TaxTree (NCBI Taxonomy) returns for every name of every Culpeper herb.

Usage:  python3 common_name_sources/taxtree/culpeper/source_taxtree.py                  # all herbs
        python3 common_name_sources/taxtree/culpeper/source_taxtree.py --limit 3        # first 3 herbs
        python3 common_name_sources/taxtree/culpeper/source_taxtree.py --no-similar     # skip the slow similar-name search
        python3 common_name_sources/taxtree/culpeper/source_taxtree.py --fuzzy-lineage  # also details of similar-name hits (hours)

Reads historical_texts/culpeper/herbs.json, writes common_name_sources/taxtree/culpeper/taxtree.json.
Raw replies are cached in common_name_sources/taxtree/culpeper/cache/.

TaxTree is the hackathon-hosted wrapper around NCBI Taxonomy
(taxtree.ethcstwin.di.uoa.gr:65000). NCBI keeps every name of a taxon with a
"name class": scientific name, synonym, common name, genbank common name,
authority, ... Its name search appears to be exact, so each spelling is sent
as written, in lower case and in Latin form (first word capitalised only).

No ranking and no picking:
  * /names/search   exact search, every result kept      (exact_name_match)
  * /names/similar  fuzzy search, every result kept      (fuzzy: true)
  * for every NCBI taxon found by exact search: all its names (every class)
    and its ranked lineage (genus, family, order, ... kingdom). Similar-name
    hits keep their NCBI ID, name and name class plus their ranked lineage
    (so their kingdom is known); --fuzzy-lineage also fetches all their names.
"""
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
HERBS = ROOT / "historical_texts" / "culpeper" / "herbs.json"
OUT = HERE / "taxtree.json"
CACHE_DIR = HERE / "cache"
SEARCH_CACHE = CACHE_DIR / "name_search.json"
SIMILAR_CACHE = CACHE_DIR / "name_similar.json"
TAXON_CACHE = CACHE_DIR / "taxa.json"
LINEAGE_CACHE = CACHE_DIR / "lineage.json"      # tax_id -> ranked lineage, for similar-name hits

API = "https://taxtree.ethcstwin.di.uoa.gr:65000"
LIMIT = 50
PAUSE = 0.2
RETRY_WAITS = [5, 15, 30]
GIVE_UP_AFTER = 10
USER_AGENT = ("EthnoHack-OverSlept/0.1 "
              "(https://github.com/georgesldk/makeathon-2026-OverSlept-track-1)")

sys.path.insert(0, str(ROOT / "common_name_sources" / "gbif" / "culpeper"))
from source_gbif import spellings, key  # noqa: E402  (same spellings as every source)


def ssl_context():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CTX = ssl_context()


def get_json(path: str, **params) -> dict:
    url = f"{API}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return json.load(r)


def with_retries(fn, arg):
    for wait in [*RETRY_WAITS, None]:
        try:
            return fn(arg)
        except Exception as e:
            code = getattr(e, "code", 500)
            if wait is None or not (code >= 500 or code == 429 or "timed out" in str(e)):
                raise
            time.sleep(wait)


def forms(q: str) -> list[str]:
    words = q.split(" ")
    latin = " ".join([words[0][:1].upper() + words[0][1:].lower()] + [w.lower() for w in words[1:]])
    return list(dict.fromkeys([q, q.lower(), latin]))


def results(data) -> list[dict]:
    """The endpoints answer in different shapes: {"results": [...]}, a bare list, or null."""
    if isinstance(data, list):
        return data
    return (data or {}).get("results", []) or []


def search(q: str) -> list[dict]:
    return results(get_json("/names/search/", name_txt=q, limit=LIMIT))


def similar(q: str) -> list[dict]:
    return results(get_json("/names/similar/", name_txt=q, limit=LIMIT))


def taxon(tax_id: str) -> dict:
    try:
        names = results(get_json("/names/search/", tax_id=tax_id, limit=LIMIT))
    except urllib.error.HTTPError as e:
        if e.code != 422:   # 422 = TaxTree rejected the parameters; try without a limit
            raise
        names = results(get_json("/names/search/", tax_id=tax_id))
    lineage = results(get_json("/ranked_lineage/search/", tax_id=tax_id))
    return {"names": names, "lineage": lineage[0] if lineage else None}


def lineage(tax_id: str) -> dict | None:
    res = results(get_json("/ranked_lineage/search/", tax_id=tax_id))
    return res[0] if res else None


def load(p: Path) -> dict:
    return json.load(open(p, encoding="utf-8")) if p.exists() else {}


def save(p: Path, d: dict) -> None:
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def fetch_all(label, todo, fn, store, path):
    failed = 0
    for i, item in enumerate(todo, 1):
        try:
            store[item] = with_retries(fn, item)
            failed = 0
        except Exception as e:
            failed += 1
            print(f"  ! {item}: {e} (will retry on the next run)")
            if failed >= GIVE_UP_AFTER:
                save(path, store)
                sys.exit("\nTaxTree seems to be down. Progress is saved; run again later.")
            continue
        if i % 50 == 0 or i == len(todo):
            save(path, store)
            print(f"  {label}: {i} of {len(todo)}")
        time.sleep(PAUSE)
    save(path, store)


def tax_id(r):
    return r.get("tax_id") if isinstance(r, dict) else None


def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    herbs = json.load(open(HERBS, encoding="utf-8"))["herbs"][:limit]
    CACHE_DIR.mkdir(exist_ok=True)
    found, sim, taxa = load(SEARCH_CACHE), load(SIMILAR_CACHE), load(TAXON_CACHE)
    lin = load(LINEAGE_CACHE)
    queries = sorted({f for h in herbs for n in [h["name"], *h["other_names"]]
                      for q in spellings(n) for f in forms(q)})

    print(f"\nSearching TaxTree (NCBI Taxonomy) for {len(herbs)} herbs ({len(queries)} query strings)\n")
    if any(q not in found or q not in sim for q in queries):
        try:
            get_json("/names/classes/")
        except Exception as e:
            sys.exit(f"Cannot reach TaxTree ({e}).\nIf this is a certificate error, run:  pip install truststore")
    todo = [q for q in queries if q not in found]
    print(f"Step 1: exact name search ({len(todo)} to ask, {len(found)} cached)")
    fetch_all("asked", todo, search, found, SEARCH_CACHE)
    todo = [q for q in queries if q not in sim]
    if "--no-similar" in sys.argv:
        print(f"\nStep 2: similar-name search skipped (--no-similar); {len(sim)} cached results are kept")
    else:
        print(f"\nStep 2: similar-name search ({len(todo)} to ask, {len(sim)} cached; "
              f"about 7 s each on TaxTree's server)")
        fetch_all("asked", todo, similar, sim, SIMILAR_CACHE)

    # Details for taxa from exact hits only; similar-name hits are mostly look-alikes from
    # all of life (bacteria, worms) and would take hours. --fuzzy-lineage fetches them too.
    hits = [r for q in queries for r in (found.get(q) or [])]
    if "--fuzzy-lineage" in sys.argv:
        hits += [r for q in queries for r in (sim.get(q) or [])]
    ids = {str(tax_id(r)) for r in hits if tax_id(r)}
    todo = sorted(ids - taxa.keys())
    print(f"\nStep 3: all names and lineage of each NCBI taxon found by exact search "
          f"({len(todo)} to ask, {len(taxa)} cached)")
    fetch_all("taxa asked", todo, taxon, taxa, TAXON_CACHE)

    sim_ids = {str(tax_id(r)) for q in queries for r in (sim.get(q) or []) if tax_id(r)}
    todo = sorted(sim_ids - taxa.keys() - lin.keys())
    print(f"\nStep 4: lineage (kingdom) of each similar-name hit ({len(todo)} to ask, {len(lin)} cached)")
    fetch_all("taxa asked", todo, lineage, lin, LINEAGE_CACHE)
    details = lambda k: taxa.get(k) or ({"names": None, "lineage": lin[k]} if k in lin else None)

    out, used = {}, set()
    for h in herbs:
        names = []
        for n in dict.fromkeys([h["name"], *h["other_names"]]):
            ss = []
            for q in spellings(n):
                for f in forms(q):
                    results = []
                    for r, fuzzy in [(r, False) for r in found.get(f) or []] + [(r, True) for r in sim.get(f) or []]:
                        tid = tax_id(r)
                        if tid:
                            used.add(str(tid))
                        r = r if isinstance(r, dict) else {"value": r}
                        results.append({**r, "fuzzy": fuzzy,
                                        "exact_name_match": key(str(r.get("name_txt", ""))) == key(f)})
                    ss.append({"spelling": q, "sent_as": f, "searched": f in found,
                               "similar_searched": f in sim, "results": results})
            names.append({"name": n, "searches": ss})
        out[h["id"]] = {"name": h["name"], "names": names}

    OUT.write_text(json.dumps({
        "source": "TaxTree (NCBI Taxonomy, hackathon-hosted wrapper): /names/search, /names/similar, "
                  "/ranked_lineage/search",
        "retrieved": date.today().isoformat(),
        "taxa": {k: details(k) for k in sorted(used) if details(k)},
        "herbs": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    res = [r for o in out.values() for nm in o["names"] for s in nm["searches"] for r in s["results"]]
    hit = lambda nm: any(r["exact_name_match"] and not r["fuzzy"] for s in nm["searches"] for r in s["results"])
    print(f"\n{len(herbs)} herbs: {len(res)} results kept ({sum(not r['fuzzy'] for r in res)} exact-search, "
          f"{sum(r['fuzzy'] for r in res)} similar-name), {len(used)} NCBI taxa\n")
    print(f"  {sum(hit(nm) for o in out.values() for nm in o['names']):>4} names are exactly an NCBI name")
    print(f"  {sum(any(hit(nm) for nm in o['names']) for o in out.values()):>4} herbs have at least one such name")
    print(f"\nSaved to common_name_sources/taxtree/culpeper/{OUT.name} ({OUT.stat().st_size / 1e6:.1f} MB)\n")


if __name__ == "__main__":
    main()
