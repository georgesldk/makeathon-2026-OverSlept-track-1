"""Check every scientific name from the Culpeper aggregate with Global Names Verifier.

Usage:  python3 scientific_name_sources/globalnames/source_globalnames.py         # plant, mixed, unknown
        add --book dioscorides to run it for Dioscorides (default: culpeper)
        python3 scientific_name_sources/globalnames/source_globalnames.py --all   # also non-plant names

Reads matching/<book>/scientific_name_queries.jsonl (aggregate.py),
writes scientific_name_sources/globalnames/<book>/globalnames.json.
Raw replies are cached in scientific_name_sources/globalnames/cache/ (shared by both books).

Global Names Verifier (verifier.globalnames.org, free, no key) checks a name against
100+ databases at once (Catalogue of Life, ITIS, NCBI, GRIN, GBIF, Tropicos, IPNI, ...)
and tolerates misspellings. Names are sent in batches; for each it keeps:
  match_type   Exact, Fuzzy (misspelling), PartialExact / PartialFuzzy (only part of the
               name, e.g. the genus), Virus, NoMatch, ...
  results      every database's record: the name it matched, the name it currently uses,
               its status (accepted / synonym), classification, edit distance, link
For names WFO and WCVP could not settle, a Fuzzy match shows the likely correct spelling.

No ranking and no picking: every database's record is kept.
"""
import json
import ssl
import sys
import time
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BOOK = sys.argv[sys.argv.index("--book") + 1] if "--book" in sys.argv else "culpeper"
QUERIES = ROOT / "matching" / BOOK / "scientific_name_queries.jsonl"
OUT = HERE / BOOK / "globalnames.json"
CACHE_DIR = HERE / "cache"
CACHE = CACHE_DIR / "verifications.json"     # name -> verifier reply for that name

API = "https://verifier.globalnames.org/api/v1/verifications"
BATCH = 200
PAUSE = 1.0
RETRY_WAITS = [5, 15, 30, 60]
USER_AGENT = ("EthnoHack-OverSlept/0.1 "
              "(https://github.com/georgesldk/makeathon-2026-OverSlept-track-1)")
KEEP = ["dataSourceId", "dataSourceTitleShort", "curation", "recordId", "outlink", "matchedName",
        "matchedCanonicalSimple", "currentRecordId", "currentName", "currentCanonicalSimple",
        "taxonomicStatus", "isSynonym", "classificationPath", "classificationRanks",
        "editDistance", "stemEditDistance", "matchType", "entryDate"]


def ssl_context():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CTX = ssl_context()


def verify(names: list[str]) -> dict[str, dict]:
    body = json.dumps({"nameStrings": names, "withAllMatches": True}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"})
    for wait in [*RETRY_WAITS, None]:
        try:
            with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
                data = json.load(r)
            break
        except Exception as e:
            code = getattr(e, "code", 500)
            if wait is None or not (code >= 500 or code == 429 or "timed out" in str(e)):
                raise
            time.sleep(wait)
    out = {}
    for n in data.get("names", []):
        out[n["name"]] = {"match_type": n.get("matchType"), "cardinality": n.get("cardinality"),
                          "curation": n.get("curation"), "error": n.get("error"),
                          "results": [{k: r.get(k) for k in KEEP} for r in n.get("results") or []]}
    return out


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    keep_all = "--all" in sys.argv
    queries = [json.loads(l) for l in open(QUERIES, encoding="utf-8")]
    skipped = [q for q in queries if q["kingdom_flag"] == "non-plant" and not keep_all]
    queries = [q for q in queries if keep_all or q["kingdom_flag"] != "non-plant"]
    CACHE_DIR.mkdir(exist_ok=True)
    cache = json.load(open(CACHE, encoding="utf-8")) if CACHE.exists() else {}
    todo = [q["name"] for q in queries if q["name"] not in cache]
    print(f"\nChecking {len(queries)} scientific names with Global Names Verifier "
          f"({len(skipped)} flagged non-plant skipped; --all to include them)")
    print(f"\n{len(todo)} to ask, {len(cache)} cached, {BATCH} names per request")
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        try:
            got = verify(chunk)
        except Exception as e:
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            sys.exit(f"Cannot use Global Names Verifier ({e}). Progress is saved; run again later.\n"
                     "If this is a certificate error, run:  pip install truststore")
        cache.update(got)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        print(f"  names checked: {min(i + BATCH, len(todo))} of {len(todo)}")
        time.sleep(PAUSE)

    out = {q["name"]: {"query_id": q["query_id"], "level": q["level"], "kingdom_flag": q["kingdom_flag"],
                       **(cache.get(q["name"]) or {"match_type": None, "results": []})} for q in queries}
    OUT.write_text(json.dumps({
        "source": "Global Names Verifier (verifier.globalnames.org/api/v1/verifications), all data sources",
        "retrieved": date.today().isoformat(), "names": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    types = Counter(v["match_type"] for v in out.values())
    srcs = Counter(r["dataSourceTitleShort"] for v in out.values() for r in v["results"])
    print(f"\n{len(out)} names checked\n")
    print("  match types: " + ", ".join(f"{k} {n}" for k, n in types.most_common()))
    print("  databases answering most often: " + ", ".join(f"{k} {n}" for k, n in srcs.most_common(8)))
    print(f"\nSaved to scientific_name_sources/globalnames/{BOOK}/{OUT.name} ({OUT.stat().st_size / 1e6:.1f} MB)\n")


if __name__ == "__main__":
    main()
