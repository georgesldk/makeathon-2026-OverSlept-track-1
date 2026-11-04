"""Look up every scientific name from the Culpeper aggregate in IPNI (International Plant
Names Index), through the hackathon-hosted copy.

Usage:  python3 scientific_name_sources/ipni/source_ipni.py            # plant, mixed, unknown names
        add --book dioscorides to run it for Dioscorides (default: culpeper)
        python3 scientific_name_sources/ipni/source_ipni.py --all      # also names flagged non-plant
        python3 scientific_name_sources/ipni/source_ipni.py --limit 20 # first 20 names, for a test

Reads matching/<book>/scientific_name_queries.jsonl (aggregate.py) and, if present,
matching/<book>/scientific_names_resolved.json (resolve_scientific.py), so the accepted
names WFO and WCVP point to are looked up too. Writes scientific_name_sources/ipni/<book>/ipni.json.
Raw replies are cached in scientific_name_sources/ipni/cache/ (shared by both books).

IPNI records plant names as published: who published each name, when (year), where
(reference, page) and its nomenclatural status. It gives no opinion on which name is
accepted. For us it answers: did this name exist in Culpeper's time?
Kew's own IPNI API refuses scripted requests, so the hackathon copy is used
(ipni.ethcstwin.di.uoa.gr:65000, University of Athens; not an official IPNI service).

  /names/search/?scientific_name=...   every record returned is kept (IPNI often holds
  several records for one name), with its publication (reference) and type material,
  flagged exact_name_match (same spelling, ignoring case, spaces, hyphens, hybrid sign).

Note: botanical names officially start with Linnaeus, Species Plantarum (1 May 1753), so
almost every name dates from 1753 or later, a century after Culpeper. IPNI's dates say
when a name was formally published, not when the plant was known.

No ranking and no picking.
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
ROOT = HERE.parent.parent
BOOK = sys.argv[sys.argv.index("--book") + 1] if "--book" in sys.argv else "culpeper"
QUERIES = ROOT / "matching" / BOOK / "scientific_name_queries.jsonl"
RESOLVED = ROOT / "matching" / BOOK / "scientific_names_resolved.json"
OUT = HERE / BOOK / "ipni.json"
CACHE_DIR = HERE / "cache"
NAME_CACHE = CACHE_DIR / "names.json"        # name -> search results

API = "https://ipni.ethcstwin.di.uoa.gr:65000"
LIMIT = 100
PAUSE = 0.2
RETRY_WAITS = [5, 15, 30]
GIVE_UP_AFTER = 10
USER_AGENT = ("EthnoHack-OverSlept/0.1 "
              "(https://github.com/georgesldk/makeathon-2026-OverSlept-track-1)")


def ssl_context():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CTX = ssl_context()


def get_json(path: str, **params):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=90, context=CTX) as r:
        return json.load(r)


def results(data) -> list:
    """The API may answer with a list, a dict holding a list, a single record or nothing."""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    for k in ("results", "items", "data", "names"):
        if isinstance(data.get(k), list):
            return data[k]
    return [data]


def with_retries(fn, arg):
    for wait in [*RETRY_WAITS, None]:
        try:
            return fn(arg)
        except Exception as e:
            code = getattr(e, "code", 500)
            if code == 404:
                return None
            if wait is None or not (code >= 500 or code == 429 or "timed out" in str(e)):
                raise
            time.sleep(wait)


def search(name: str) -> list:
    """Every record IPNI has under this name (paged)."""
    out, offset = [], 0
    while True:
        data = get_json("/names/search/", scientific_name=name, limit=LIMIT, offset=offset)
        page = results(data)
        out += page
        offset += LIMIT
        total = data.get("count", 0) if isinstance(data, dict) else 0
        if len(page) < LIMIT or offset >= total:
            return out


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
                sys.exit("\nIPNI seems to be down. Progress is saved; run again later.")
            continue
        if i % 100 == 0 or i == len(todo):
            save(path, store)
            print(f"  {label}: {i} of {len(todo)}")
        time.sleep(PAUSE)
    save(path, store)


def squash(s) -> str:
    return re.sub(r"[\s\-×.]|(?<=\s)x(?=\s)", "", str(s or "").lower())


def name_of(r: dict) -> str | None:
    for k in ("scientific_name", "scientificName", "name", "taxon_name"):
        if isinstance(r, dict) and r.get(k):
            return r[k]
    return None


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    keep_all = "--all" in sys.argv
    queries = [json.loads(l) for l in open(QUERIES, encoding="utf-8")]
    queries = [q for q in queries if keep_all or q["kingdom_flag"] != "non-plant"]
    asked_for = {q["name"]: {"query_id": q["query_id"], "why": "candidate name"} for q in queries}
    if RESOLVED.exists():               # accepted names WFO/WCVP point to, when spelled differently
        for r in json.load(open(RESOLVED, encoding="utf-8"))["names"].values():
            for side in ("wfo", "wcvp"):
                n = r[side].get("accepted_name_without_authors")
                if n and n not in asked_for and r[side].get("rank") not in ("family",):
                    asked_for[n] = {"query_id": None, "why": f"accepted name ({side.upper()}) of {r['scientific_name']}"}
    names_wanted = list(asked_for)[:limit]
    CACHE_DIR.mkdir(exist_ok=True)
    found = load(NAME_CACHE)

    todo = [n for n in names_wanted if n not in found]
    print(f"\nLooking up {len(names_wanted)} names in IPNI (hackathon copy)\n")
    if todo:
        try:   # one real search first, so a network, certificate or server problem is obvious
            search("Solanum dulcamara")
        except Exception as e:
            sys.exit(f"IPNI's name search failed ({e}).\n"
                     "HTTP 500 means the hackathon IPNI server itself has a problem; try again later.\n"
                     "If this is a certificate error, run:  pip install truststore")
    print(f"Step 1: name search ({len(todo)} to ask, {len(found)} cached)")
    fetch_all("names asked", todo, search, found, NAME_CACHE)

    out = {}
    for n in names_wanted:
        recs = []
        for r in found.get(n) or []:
            exact = squash(name_of(r)) == squash(n)
            recs.append({**r, "exact_name_match": exact})
        out[n] = {**asked_for[n], "searched": n in found, "records": recs}

    OUT.write_text(json.dumps({
        "source": "IPNI (International Plant Names Index) via the hackathon-hosted API "
                  "(ipni.ethcstwin.di.uoa.gr:65000, not an official IPNI service)",
        "retrieved": date.today().isoformat(), "names": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    vals = list(out.values())
    exact = [v for v in vals if any(r["exact_name_match"] for r in v["records"])]
    years = [r.get("published_in_year") for v in vals for r in v["records"] if r["exact_name_match"]]
    years = [int(y) for y in years if str(y or "").isdigit()]
    print(f"\n{len(vals)} names looked up in IPNI\n")
    print(f"  {len(exact):>5} have an IPNI record spelled the same")
    print(f"  {len(vals) - len(exact):>5} have none")
    if years:
        print(f"  publication years of those records: {min(years)}-{max(years)} "
              f"({sum(y == 1753 for y in years)} from 1753, Linnaeus' Species Plantarum)")
    print(f"\nSaved to scientific_name_sources/ipni/{BOOK}/{OUT.name} ({OUT.stat().st_size / 1e6:.1f} MB)\n")


if __name__ == "__main__":
    main()
