"""Collect every common-name hit ChecklistBank has for every name of every Culpeper herb.

Usage:  python3 common_name_sources/checklistbank/culpeper/source_checklistbank.py            # all herbs
        python3 common_name_sources/checklistbank/culpeper/source_checklistbank.py --limit 3  # first 3 herbs

Reads historical_texts/culpeper/herbs.json, writes common_name_sources/checklistbank/culpeper/checklistbank.json.
Raw replies are cached in common_name_sources/checklistbank/culpeper/cache/.

ChecklistBank (api.checklistbank.org) holds hundreds of checklists: the
Catalogue of Life, ITIS, national checklists (e.g. Australia's APNI), but
also copies of the GBIF backbone and iNaturalist. Its vernacular search
(/vernacular?q=) looks through the common names of all of them at once and
says, for each hit, which checklist (datasetKey) and which taxon (taxonID)
it belongs to.

No ranking and no picking:
  * every hit is kept (all pages, up to MAX_HITS per spelling), flagged
      exact_name_match   the common name equals the spelling searched
      exact_part_match   one comma/slash-separated part of it does
                         ("Bittersweet, Woody Nightshade")
    The search is a substring search, so most hits are neither.
  * the scientific name is looked up for every exact or exact-part hit, in
    the newest release of each checklist only (ChecklistBank keeps many
    releases of e.g. the Catalogue of Life); other hits keep their taxonID
    and can be resolved later. Private checklists are marked inaccessible;
  * the kingdom of every looked-up taxon, from that checklist's own
    classification of it;
  * every checklist that appears is described once: title, alias, origin
    and licence, so copies of GBIF or iNaturalist can be told apart from
    independent checklists.
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
ROOT = HERE.parent.parent.parent
HERBS = ROOT / "historical_texts" / "culpeper" / "herbs.json"
OUT = HERE / "checklistbank.json"
CACHE_DIR = HERE / "cache"
SEARCH_CACHE = CACHE_DIR / "vernacular_search.json"
TAXON_CACHE = CACHE_DIR / "taxa.json"
DATASET_CACHE = CACHE_DIR / "datasets.json"
KINGDOM_CACHE = CACHE_DIR / "kingdoms.json"     # "datasetKey|taxonID" -> kingdom (or null)

API = "https://api.checklistbank.org"
PAGE = 1000
MAX_HITS = 5000          # per spelling; very short names match thousands of substrings
PAUSE = 0.3
RETRY_WAITS = [5, 15, 30, 60]
GIVE_UP_AFTER = 10
USER_AGENT = ("EthnoHack-OverSlept/0.1 "
              "(https://github.com/georgesldk/makeathon-2026-OverSlept-track-1)")
HIT_FIELDS = ["datasetKey", "taxonID", "name", "latin", "language", "country", "area", "sex", "remarks"]

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


def with_retries(fn, arg):
    for wait in [*RETRY_WAITS, None]:
        try:
            return fn(arg)
        except Exception as e:
            code = getattr(e, "code", 500)
            if code == 404:
                return None
            if code in (401, 403):
                return {"inaccessible": True, "http_status": code}
            if wait is None or not (code >= 500 or code == 429 or "timed out" in str(e)):
                raise
            time.sleep(wait)


def parts(name: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,/;]| or ", name) if p.strip()]


def search(q: str) -> dict:
    hits, offset = [], 0
    while True:
        params = {"q": q, "limit": PAGE, "offset": offset}
        data = get_json(f"{API}/vernacular?" + urllib.parse.urlencode(params))
        page = data.get("result", []) or []
        hits += [{f: r[f] for f in HIT_FIELDS if r.get(f) is not None} for r in page]
        offset += PAGE
        if len(page) < PAGE or data.get("last") or offset >= MAX_HITS:
            return {"hits": hits, "truncated": len(page) == PAGE and offset >= MAX_HITS}
        time.sleep(PAUSE)


def taxon(ref: str) -> dict | None:
    ds, tid = ref.split("|", 1)
    data = get_json(f"{API}/dataset/{ds}/taxon/{urllib.parse.quote(tid, safe='')}")
    n = data.get("name", {})
    return {"scientificName": n.get("scientificName"), "authorship": n.get("authorship"),
            "rank": n.get("rank"), "status": data.get("status"), "parentId": data.get("parentId"),
            "genus": n.get("genus"), "specificEpithet": n.get("specificEpithet")}


def kingdom(ref: str) -> str | None:
    """The kingdom in the checklist's own classification of the taxon, as it writes it."""
    ds, tid = ref.split("|", 1)
    for t in get_json(f"{API}/dataset/{ds}/taxon/{urllib.parse.quote(tid, safe='')}/classification") or []:
        if (t.get("rank") or "").lower() == "kingdom":
            return t.get("name") or t.get("label")
    return None


def dataset(k: str) -> dict:
    d = get_json(f"{API}/dataset/{k}")
    return {f: d.get(f) for f in ("key", "title", "alias", "origin", "type", "license", "url",
                                  "issued", "created", "sourceKey", "private")
            if d.get(f) is not None}


def newest_releases(datasets: dict) -> set[str]:
    """One checklist per family: the newest release of each project.

    ChecklistBank keeps many releases of the same checklist (e.g. every
    Catalogue of Life release); a release records its project as sourceKey.
    Taxa are resolved only in the newest release of each family.
    """
    best = {}
    for k, d in datasets.items():
        if not d or d.get("inaccessible"):
            continue
        fam = str(d.get("sourceKey") or k)
        rank = (str(d.get("issued") or d.get("created") or ""), int(k))
        if fam not in best or rank > best[fam][0]:
            best[fam] = (rank, k)
    return {k for _, k in best.values()}


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
                sys.exit("\nChecklistBank seems to be down. Progress is saved; run again later.")
            continue
        if i % 25 == 0 or i == len(todo):
            save(path, store)
            print(f"  {label}: {i} of {len(todo)}")
        time.sleep(PAUSE)
    save(path, store)


def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    herbs = json.load(open(HERBS, encoding="utf-8"))["herbs"][:limit]
    CACHE_DIR.mkdir(exist_ok=True)
    searches, taxa, datasets = load(SEARCH_CACHE), load(TAXON_CACHE), load(DATASET_CACHE)
    kcache = load(KINGDOM_CACHE)
    wanted = sorted({q for h in herbs for n in [h["name"], *h["other_names"]] for q in spellings(n)})

    todo = [q for q in wanted if q not in searches]
    print(f"\nSearching ChecklistBank for {len(herbs)} herbs ({len(wanted)} spellings)\n")
    if todo:
        try:
            get_json(f"{API}/vernacular?q=bittersweet&limit=1")
        except Exception as e:
            sys.exit(f"Cannot reach ChecklistBank ({e}).\nIf this is a certificate error, run:  pip install truststore")
    print(f"Step 1: common-name search ({len(todo)} spellings to ask, {len(searches)} cached)")
    fetch_all("spellings asked", todo, search, searches, SEARCH_CACHE)

    def flags(hit, q):
        nm = hit.get("name", "")
        return key(nm) == key(q), any(key(p) == key(q) for p in parts(nm))

    keys = {str(h["datasetKey"]) for q in wanted for h in (searches.get(q) or {}).get("hits", [])}
    todo = sorted(keys - datasets.keys())
    print(f"\nStep 2: checklist descriptions ({len(todo)} checklists to ask, {len(datasets)} cached)")
    fetch_all("checklists asked", todo, dataset, datasets, DATASET_CACHE)

    keep = newest_releases(datasets)
    refs = {f"{h['datasetKey']}|{h['taxonID']}" for q in wanted for h in (searches.get(q) or {}).get("hits", [])
            if "taxonID" in h and any(flags(h, q)) and str(h["datasetKey"]) in keep}
    todo = sorted(refs - taxa.keys())
    print(f"\nStep 3: scientific names of exact hits, newest release of each checklist ({len(todo)} taxa to ask, {len(taxa)} cached)")
    fetch_all("taxa asked", todo, taxon, taxa, TAXON_CACHE)

    todo = sorted(r for r in refs if (taxa.get(r) or {}).get("scientificName") and r not in kcache)
    print(f"\nStep 4: kingdom of each of those taxa ({len(todo)} to ask, {len(kcache)} cached)")
    fetch_all("taxa asked", todo, kingdom, kcache, KINGDOM_CACHE)

    def resolved(ref):
        t = taxa.get(ref)
        if not t:
            return None
        k = kcache.get(ref)
        return {**t, "kingdom": k if isinstance(k, str) else None} if t.get("scientificName") else t

    out, used = {}, set()
    for h in herbs:
        names = []
        for n in dict.fromkeys([h["name"], *h["other_names"]]):
            ss = []
            for q in spellings(n):
                s = searches.get(q) or {"hits": [], "truncated": False}
                hits = []
                for hit in s["hits"]:
                    exact, part = flags(hit, q)
                    ref = f"{hit.get('datasetKey')}|{hit.get('taxonID')}"
                    used.add(str(hit.get("datasetKey")))
                    hits.append({**hit, "exact_name_match": exact, "exact_part_match": part,
                                 "taxon": resolved(ref) if (exact or part) else None})
                ss.append({"spelling": q, "searched": q in searches, "truncated": s["truncated"], "hits": hits})
            names.append({"name": n, "searches": ss})
        out[h["id"]] = {"name": h["name"], "names": names}

    OUT.write_text(json.dumps({
        "source": "ChecklistBank vernacular search (api.checklistbank.org/vernacular), all checklists",
        "retrieved": date.today().isoformat(),
        "checklists": {k: datasets[k] for k in sorted(used) if k in datasets},
        "herbs": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    all_hits = [x for o in out.values() for nm in o["names"] for s in nm["searches"] for x in s["hits"]]
    exact = [x for x in all_hits if x["exact_name_match"] or x["exact_part_match"]]
    hit = lambda nm: any(x["exact_name_match"] or x["exact_part_match"] for s in nm["searches"] for x in s["hits"])
    print(f"\n{len(herbs)} herbs: {len(all_hits)} hits kept from {len(used)} checklists, "
          f"{len(exact)} of them exact\n")
    print(f"  {sum(hit(nm) for o in out.values() for nm in o['names']):>4} names have an exact hit")
    print(f"  {sum(any(hit(nm) for nm in o['names']) for o in out.values()):>4} herbs have at least one such name")
    print(f"\nSaved to common_name_sources/checklistbank/culpeper/{OUT.name} ({OUT.stat().st_size / 1e6:.1f} MB)\n")


if __name__ == "__main__":
    main()
