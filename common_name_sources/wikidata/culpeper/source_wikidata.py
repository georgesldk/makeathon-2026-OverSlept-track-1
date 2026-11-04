"""Collect everything Wikidata returns for every name of every Culpeper herb.

Usage:  python3 common_name_sources/wikidata/culpeper/source_wikidata.py            # all herbs
        python3 common_name_sources/wikidata/culpeper/source_wikidata.py --limit 3  # first 3 herbs, for a test

Reads historical_texts/culpeper/herbs.json, writes common_name_sources/wikidata/culpeper/wikidata.json.
Raw replies are cached in common_name_sources/wikidata/culpeper/cache/, so a rerun only asks
Wikidata about what it has not seen yet.

No ranking and no picking: every item found is kept, for later processing.
Each name of each herb (main name and other names) is searched in the same
spelling variants as the GBIF script, two ways, because Wikidata's search
covers only labels and aliases:
  1. label/alias search (wbsearchentities, English), up to 50 items;
  2. "taxon common name" statements (P1843) equal to the spelling, in the
     usual capitalisations, language en / en-gb / en-us (SPARQL).
Every item found is then fetched in full: labels, aliases, what it is an
instance of, taxon name, rank and parent, common names with their
references, every external identifier (GBIF, WFO, IPNI, NCBI, POWO, ...)
and its English Wikipedia article. Finally, for every taxon item, the
kingdom it sits under in Wikidata's parent-taxon tree (P171).

Each hit carries, as information only:
  matched_in        label | alias | common_name
  matched_text      the text in Wikidata that matched
  exact_name_match  matched_text equals the spelling searched (ignoring
                    case, spaces, hyphens, apostrophes)
Items that are not taxa (a film called "Mortal") are kept but flagged.
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
OUT = HERE / "wikidata.json"
CACHE_DIR = HERE / "cache"
SEARCH_CACHE = CACHE_DIR / "search.json"        # spelling -> label/alias hits
COMMON_CACHE = CACHE_DIR / "common_names.json"  # spelling -> P1843 hits
ITEM_CACHE = CACHE_DIR / "items.json"           # QID -> item details
KINGDOM_CACHE = CACHE_DIR / "kingdoms.json"     # QID -> kingdom (or null)

API = "https://www.wikidata.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
# Wikimedia asks for a User-Agent with contact information.
USER_AGENT = ("EthnoHack-OverSlept/0.1 "
              "(https://github.com/georgesldk/makeathon-2026-OverSlept-track-1)")
PAUSE = 0.3
RETRY_WAITS = [5, 15, 30, 60]
GIVE_UP_AFTER = 10
SPARQL_BATCH = 20        # spellings per common-name query
ITEM_BATCH = 50          # items per wbgetentities call (the API maximum)
TEXT_LANGS = ["en", "en-gb", "en-us", "la"]   # labels/aliases/descriptions kept
NAME_LANGS = ["en", "en-gb", "en-us"]         # P1843 languages searched
TAXON = "Q16521"
KINGDOM_BATCH = 50       # taxon items per kingdom query
# Items a parent-taxon chain (P171) can end at
WD_KINGDOMS = {"Q756": "Plantae", "Q729": "Animalia", "Q764": "Fungi", "Q10876": "Bacteria",
               "Q10872": "Archaea", "Q808": "Viruses"}
RANKS = {"Q7432": "species", "Q34740": "genus", "Q35409": "family",
         "Q68947": "subspecies", "Q767728": "variety"}

# The spelling variants are the GBIF script's, so all sources search the same strings.
sys.path.insert(0, str(ROOT / "common_name_sources" / "gbif" / "culpeper"))
from source_gbif import spellings, key  # noqa: E402


def ssl_context():
    """Use the Mac's certificate store if 'truststore' is installed."""
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CTX = ssl_context()


def get_json(url: str, accept: str = "application/json") -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        data = json.load(r)
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"Wikidata error: {data['error'].get('code')} {data['error'].get('info', '')[:100]}")
    return data


def with_retries(fn, arg):
    for wait in [*RETRY_WAITS, None]:
        try:
            return fn(arg)
        except Exception as e:
            code = getattr(e, "code", 500)
            temporary = code >= 500 or code == 429 or "timed out" in str(e) or "maxlag" in str(e)
            if wait is None or not temporary:
                raise
            time.sleep(wait)


# --- 1. label / alias search --------------------------------------------------
def search_labels(q: str) -> list[dict]:
    params = {"action": "wbsearchentities", "search": q, "language": "en", "uselang": "en",
              "type": "item", "limit": 50, "format": "json"}
    data = get_json(API + "?" + urllib.parse.urlencode(params))
    return [{"qid": h["id"],
             "matched_in": (h.get("match") or {}).get("type", "label"),
             "matched_text": (h.get("match") or {}).get("text", h.get("label", "")),
             "matched_language": (h.get("match") or {}).get("language", "")}
            for h in data.get("search", [])]


# --- 2. taxon common name (P1843) ---------------------------------------------
def case_forms(q: str) -> list[str]:
    return list(dict.fromkeys([q, q.lower(), q.title(), q[:1].upper() + q[1:].lower()]))


def sparql_literal(text: str, lang: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + f'"@{lang}'


def search_common_names(batch: list[str]) -> dict[str, list[dict]]:
    """One SPARQL query for a batch of spellings; returns spelling -> hits."""
    literals = {sparql_literal(f, lang): q for q in batch for f in case_forms(q) for lang in NAME_LANGS}
    query = ("SELECT ?item ?n WHERE { VALUES ?n { " + " ".join(literals) +
             " } ?item p:P1843/ps:P1843 ?n . }")
    data = get_json(SPARQL + "?" + urllib.parse.urlencode({"query": query, "format": "json"}),
                    accept="application/sparql-results+json")
    out = {q: [] for q in batch}
    for b in data["results"]["bindings"]:
        text, lang = b["n"]["value"], b["n"].get("xml:lang", "")
        q = literals.get(sparql_literal(text, lang))
        if q is None:
            continue
        hit = {"qid": b["item"]["value"].rsplit("/", 1)[-1], "matched_in": "common_name",
               "matched_text": text, "matched_language": lang}
        if hit not in out[q]:
            out[q].append(hit)
    return out


# --- 3. item details ----------------------------------------------------------
def values(claims: dict, prop: str) -> list:
    out = []
    for c in claims.get(prop, []):
        dv = c.get("mainsnak", {}).get("datavalue")
        if dv:
            v = dv["value"]
            out.append(v.get("id", v) if isinstance(v, dict) else v)
    return out


def references(claim: dict) -> list[dict]:
    refs = []
    for r in claim.get("references", []):
        snaks = r.get("snaks", {})
        ref = {}
        for prop, name in (("P248", "stated_in"), ("P854", "reference_url"), ("P143", "imported_from")):
            v = [s["datavalue"]["value"] for s in snaks.get(prop, []) if s.get("datavalue")]
            if v:
                ref[name] = [x.get("id", x) if isinstance(x, dict) else x for x in v]
        if ref:
            refs.append(ref)
    return refs


def item_record(e: dict) -> dict:
    claims = e.get("claims", {})
    pick = lambda field: {l: v["value"] for l, v in e.get(field, {}).items()}
    rec = {
        "qid": e["id"],
        "labels": pick("labels"),
        "descriptions": pick("descriptions"),
        "aliases": {l: [a["value"] for a in v] for l, v in e.get("aliases", {}).items()},
        "instance_of": values(claims, "P31"),
        "is_taxon": TAXON in values(claims, "P31") or bool(values(claims, "P225")),
        "enwiki": e.get("sitelinks", {}).get("enwiki", {}).get("title"),
    }
    if rec["is_taxon"]:
        rank = values(claims, "P105")
        rec.update({
            "taxon_name": (values(claims, "P225") or [None])[0],
            "taxon_rank": RANKS.get(rank[0], rank[0]) if rank else None,
            "parent_taxon": values(claims, "P171"),
            "common_names": [{"name": c["mainsnak"]["datavalue"]["value"]["text"],
                              "language": c["mainsnak"]["datavalue"]["value"]["language"],
                              "references": references(c)}
                             for c in claims.get("P1843", []) if c.get("mainsnak", {}).get("datavalue")],
            "external_ids": {p: values(claims, p) for p, cs in claims.items()
                             if cs and cs[0].get("mainsnak", {}).get("datatype") == "external-id"},
        })
    return rec


def fetch_items(qids: list[str]) -> dict[str, dict]:
    params = {"action": "wbgetentities", "ids": "|".join(qids),
              "props": "labels|descriptions|aliases|claims|sitelinks",
              "languages": "|".join(TEXT_LANGS), "sitefilter": "enwiki",
              "format": "json"}
    data = get_json(API + "?" + urllib.parse.urlencode(params))
    return {q: item_record(e) for q, e in data.get("entities", {}).items() if "missing" not in e}


def kingdoms(qids: list[str]) -> dict[str, str | None]:
    """One SPARQL query: which kingdom each item sits under (P171, any depth)."""
    values = " ".join(f"wd:{q}" for q in qids)
    ks = " ".join(f"wd:{q}" for q in WD_KINGDOMS)
    query = f"SELECT ?item ?k WHERE {{ VALUES ?item {{ {values} }} VALUES ?k {{ {ks} }} ?item wdt:P171+ ?k . }}"
    data = get_json(SPARQL + "?" + urllib.parse.urlencode({"query": query, "format": "json"}),
                    accept="application/sparql-results+json")
    out = {q: None for q in qids}
    for b in data["results"]["bindings"]:
        out[b["item"]["value"].rsplit("/", 1)[-1]] = WD_KINGDOMS[b["k"]["value"].rsplit("/", 1)[-1]]
    return out


# --- run ----------------------------------------------------------------------
def load(path: Path) -> dict:
    return json.load(open(path, encoding="utf-8")) if path.exists() else {}


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def run_step(label, todo, batch, fn, store, path):
    """Fetch in batches, saving the cache as it goes; stop if Wikidata is down."""
    failed = 0
    chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]
    done = 0
    for chunk in chunks:
        try:
            store.update(with_retries(fn, chunk))
            failed = 0
        except Exception as e:
            failed += 1
            print(f"  ! {chunk[0]}{' ...' if len(chunk) > 1 else ''}: {e} (will retry on the next run)")
            if failed >= GIVE_UP_AFTER:
                save(path, store)
                sys.exit("\nWikidata seems to be down. Progress is saved; run again later.")
            continue
        done += len(chunk)
        if done % 50 < batch or done == len(todo):
            save(path, store)
            print(f"  {label}: {done} of {len(todo)}")
        time.sleep(PAUSE)
    save(path, store)


def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    herbs = json.load(open(HERBS, encoding="utf-8"))["herbs"][:limit]
    CACHE_DIR.mkdir(exist_ok=True)
    search, common, items = load(SEARCH_CACHE), load(COMMON_CACHE), load(ITEM_CACHE)
    kcache = load(KINGDOM_CACHE)
    wanted = sorted({q for h in herbs for n in [h["name"], *h["other_names"]] for q in spellings(n)})

    todo_s = [q for q in wanted if q not in search]
    todo_c = [q for q in wanted if q not in common]
    print(f"\nSearching Wikidata for {len(herbs)} herbs ({len(wanted)} spellings)\n")
    if todo_s or todo_c:
        try:  # one test call first, so a network or certificate problem is obvious
            search_labels("bittersweet")
        except Exception as e:
            sys.exit(f"Cannot reach Wikidata ({e}).\nIf this is a certificate error, run:  pip install truststore")

    print(f"Step 1: labels and aliases ({len(todo_s)} spellings to ask, {len(search)} cached)")
    run_step("spellings asked", todo_s, 1, lambda c: {c[0]: search_labels(c[0])}, search, SEARCH_CACHE)
    print(f"\nStep 2: taxon common names ({len(todo_c)} spellings to ask, {len(common)} cached)")
    run_step("spellings asked", todo_c, SPARQL_BATCH, search_common_names, common, COMMON_CACHE)

    qids = sorted({h["qid"] for q in wanted for h in search.get(q, []) + common.get(q, [])} - items.keys())
    print(f"\nStep 3: item details ({len(qids)} items to fetch, {len(items)} cached)")
    run_step("items fetched", qids, ITEM_BATCH, fetch_items, items, ITEM_CACHE)

    found = {h["qid"] for q in wanted for h in search.get(q, []) + common.get(q, [])}
    todo_k = sorted(q for q in found if items.get(q, {}).get("is_taxon") and q not in kcache)
    print(f"\nStep 4: kingdom of each taxon item ({len(todo_k)} to ask, {len(kcache)} cached)")
    run_step("items asked", todo_k, KINGDOM_BATCH, kingdoms, kcache, KINGDOM_CACHE)

    out_items, out = {}, {}
    for h in herbs:
        names = []
        for n in dict.fromkeys([h["name"], *h["other_names"]]):
            searches = []
            for q in spellings(n):
                hits = []
                for hit in search.get(q, []) + common.get(q, []):
                    if hit["qid"] in items:
                        it = items[hit["qid"]]
                        out_items[hit["qid"]] = {**it, "kingdom": kcache.get(hit["qid"])} if it.get("is_taxon") else it
                    hits.append({**hit, "exact_name_match": key(hit["matched_text"]) == key(q),
                                 "is_taxon": items.get(hit["qid"], {}).get("is_taxon")})
                searches.append({"spelling": q, "searched": q in search and q in common, "results": hits})
            names.append({"name": n, "searches": searches})
        out[h["id"]] = {"name": h["name"], "names": names}

    OUT.write_text(json.dumps({
        "source": "Wikidata: wbsearchentities (English labels and aliases) and SPARQL "
                  "(taxon common name P1843, en/en-gb/en-us); items via wbgetentities",
        "retrieved": date.today().isoformat(),
        "items": out_items,
        "herbs": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    all_hits = [r for o in out.values() for nm in o["names"] for s in nm["searches"] for r in s["results"]]
    good = lambda nm: any(r["exact_name_match"] and r["is_taxon"]
                          for s in nm["searches"] for r in s["results"])
    print(f"\n{len(herbs)} herbs, {sum(len(o['names']) for o in out.values())} names, "
          f"{len(all_hits)} hits kept ({len(out_items)} distinct items, "
          f"{sum(1 for i in out_items.values() if i['is_taxon'])} of them taxa)\n")
    print(f"  {sum(good(nm) for o in out.values() for nm in o['names']):>4} names exactly match a taxon's label, alias or common name")
    print(f"  {sum(any(good(nm) for nm in o['names']) for o in out.values()):>4} herbs have at least one such name")
    print(f"\nSaved to common_name_sources/wikidata/culpeper/{OUT.name} ({OUT.stat().st_size / 1e6:.1f} MB)\n")


if __name__ == "__main__":
    main()
