"""Search Wikidata for every Dioscorides name, in Ancient Greek, Latin and modern Greek.

Usage:  python3 common_name_sources/wikidata/dioscorides/source_wikidata.py
        python3 common_name_sources/wikidata/dioscorides/source_wikidata.py --limit 20   # a test

Reads historical_texts/dioscorides/lexicon_lsj.json (every name with its dictionary form and
Latin spelling), writes common_name_sources/wikidata/dioscorides/wikidata.json.
Raw replies are cached in common_name_sources/wikidata/dioscorides/cache/.

Wikidata labels and aliases are searched (wbsearchentities) in three languages:
  grc  Ancient Greek    the name as Dioscorides writes it
  el   modern Greek     the same Greek name (modern Greek plant names often continue the
                        ancient ones: μανδραγόρας)
  la   Latin            the name's Latin spelling (acorum, gladiolus, radix ...)
Every item found is fetched: its labels in these languages and English, whether it is a
taxon, and its scientific name (P225). Each hit is flagged exact_name_match (the label or
alias equals the name, ignoring accents and case).

No ranking and no picking: every hit is kept.
"""
import json
import re
import ssl
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
NAMES = ROOT / "historical_texts" / "dioscorides" / "lexicon_lsj.json"
OUT = HERE / "wikidata.json"
CACHE_DIR = HERE / "cache"
SEARCH_CACHE = CACHE_DIR / "search.json"     # "lang|term" -> hits
ITEM_CACHE = CACHE_DIR / "items.json"        # QID -> item

API = "https://www.wikidata.org/w/api.php"
USER_AGENT = ("EthnoHack-OverSlept/0.1 "
              "(https://github.com/georgesldk/makeathon-2026-OverSlept-track-1)")
PAUSE = 0.3
RETRY_WAITS = [5, 15, 30, 60]
GIVE_UP_AFTER = 10
TAXON = "Q16521"
LANGS = ["grc", "el", "la", "en"]


def ssl_context():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CTX = ssl_context()


def get_json(params: dict) -> dict:
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode({**params, "format": "json"}),
                                 headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
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


def plain(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("ς", "σ")
    return re.sub(r"[^\w]", "", s)


def search(key: str) -> list[dict]:
    lang, term = key.split("|", 1)
    data = get_json({"action": "wbsearchentities", "search": term, "language": lang, "uselang": lang,
                     "strictlanguage": 1, "type": "item", "limit": 50})
    return [{"qid": h["id"], "matched_text": (h.get("match") or {}).get("text"),
             "matched_in": (h.get("match") or {}).get("type"),
             "matched_language": (h.get("match") or {}).get("language")} for h in data.get("search", [])]


def fetch_items(qids: list[str]) -> dict[str, dict]:
    data = get_json({"action": "wbgetentities", "ids": "|".join(qids), "props": "labels|aliases|claims",
                     "languages": "|".join(LANGS)})
    out = {}
    for q, e in data.get("entities", {}).items():
        if "missing" in e:
            continue
        claims = e.get("claims", {})
        val = lambda p: [((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") for c in claims.get(p, [])]
        inst = [v.get("id") for v in val("P31") if isinstance(v, dict)]
        out[q] = {"qid": q, "labels": {l: v["value"] for l, v in e.get("labels", {}).items()},
                  "aliases": {l: [a["value"] for a in v] for l, v in e.get("aliases", {}).items()},
                  "is_taxon": TAXON in inst or bool(val("P225")),
                  "taxon_name": next((v for v in val("P225") if isinstance(v, str)), None),
                  "instance_of": inst}
    return out


def load(p: Path) -> dict:
    return json.load(open(p, encoding="utf-8")) if p.exists() else {}


def save(p: Path, d: dict) -> None:
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def run(label, todo, batch, fn, store, path):
    failed = done = 0
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        try:
            store.update(with_retries(fn, chunk) if batch > 1 else {chunk[0]: with_retries(fn, chunk[0])})
            failed = 0
        except Exception as e:
            failed += 1
            print(f"  ! {chunk[0]}: {e} (will retry on the next run)")
            if failed >= GIVE_UP_AFTER:
                save(path, store)
                sys.exit("\nWikidata seems to be down. Progress is saved; run again later.")
            continue
        done += len(chunk)
        if done % 100 < batch or done == len(todo):
            save(path, store)
            print(f"  {label}: {done} of {len(todo)}")
        time.sleep(PAUSE)
    save(path, store)


def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    chapters = json.load(open(NAMES, encoding="utf-8"))["chapters"]
    names = {}
    for c in chapters:
        for n in c["names"]:
            names.setdefault(n["name"], n["latin_form"])
    names = dict(list(names.items())[:limit])
    keys = []
    for greek, latin in names.items():
        keys += [f"grc|{greek}", f"el|{greek}", f"la|{latin}"]
    keys = list(dict.fromkeys(keys))
    CACHE_DIR.mkdir(exist_ok=True)
    found, items = load(SEARCH_CACHE), load(ITEM_CACHE)
    todo = [k for k in keys if k not in found]
    print(f"\nSearching Wikidata for {len(names)} Dioscorides names in Ancient Greek, modern Greek and Latin\n")
    print(f"Step 1: label and alias search ({len(todo)} to ask, {len(found)} cached)")
    run("searches", todo, 1, search, found, SEARCH_CACHE)
    qids = sorted({h["qid"] for k in keys for h in found.get(k) or []} - items.keys())
    print(f"\nStep 2: item details ({len(qids)} to fetch, {len(items)} cached)")
    run("items", qids, 50, fetch_items, items, ITEM_CACHE)

    out, used = {}, {}
    for greek, latin in names.items():
        hits = []
        for lang, term in (("grc", greek), ("el", greek), ("la", latin)):
            for h in found.get(f"{lang}|{term}") or []:
                it = items.get(h["qid"], {})
                used[h["qid"]] = it
                hits.append({**h, "searched_language": lang, "searched": term,
                             "exact_name_match": plain(h["matched_text"]) == plain(term),
                             "is_taxon": it.get("is_taxon"), "taxon_name": it.get("taxon_name")})
        out[greek] = {"latin_form": latin, "hits": hits}
    OUT.write_text(json.dumps({"source": "Wikidata wbsearchentities (grc, el, la) and wbgetentities",
                               "retrieved": date.today().isoformat(), "items": used, "names": out},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    good = [n for n, v in out.items() if any(h["exact_name_match"] and h["taxon_name"] for h in v["hits"])]
    print(f"\n{len(out)} names: {len(good)} exactly match the label or alias of a taxon with a scientific name")
    for lang in ("grc", "el", "la"):
        k = sum(1 for v in out.values() if any(h["exact_name_match"] and h["taxon_name"] and
                                                h["searched_language"] == lang for h in v["hits"]))
        print(f"  {lang}: {k}")
    print(f"\nSaved to common_name_sources/wikidata/dioscorides/{OUT.name}\n")


if __name__ == "__main__":
    main()
