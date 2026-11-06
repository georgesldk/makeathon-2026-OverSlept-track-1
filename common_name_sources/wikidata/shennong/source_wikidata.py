"""Wikidata taxa for the names of the Shennong Bencao Jing (Chinese labels only).

Usage:  python3 common_name_sources/wikidata/shennong/source_wikidata.py
        (pip install opencc-python-reimplemented  first: Wikidata often has simplified labels only)

Reads  historical_texts/shennong/entries.json
Writes common_name_sources/wikidata/shennong/wikidata.json   one row per entry x name x taxon

Names, by layer (the later layers are kept apart, as Dioscorides' RV lists are):
  headword, classic (一名 in the Shennong text), wu_pu, mingyi; plus each without its plant-part ending
  (車前子 -> 車前) when two characters or more remain
Routes:
  taxon label    a taxon (P225) whose Chinese label or alias is the name
  crude drug     an item whose Chinese label or alias is the name and that names its source taxon
                 (P1582, natural product of taxon), e.g. 車前子 -> Plantago asiatica
Only Chinese labels (zh, zh-hant, zh-hans, zh-tw, zh-hk, zh-cn): the same characters in Japanese can
name another plant (人参 is carrot in Japanese). Animals and minerals are skipped. Wikidata is CC0.
"""
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
ENTRIES = ROOT / "historical_texts" / "shennong" / "entries.json"
OUT = HERE / "wikidata.json"
CACHE = HERE / "cache"
SPARQL = "https://query.wikidata.org/sparql"
UA = "EthnoHack-OverSlept/0.3 (research; non-commercial)"
LANGS = ["zh", "zh-hant", "zh-hans", "zh-tw", "zh-hk", "zh-cn"]
PARTS = "子實仁根花葉皮莖汁核"
BATCH = 60


def ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def sparql(q: str, key: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    for i in range(3):
        try:
            req = urllib.request.Request(SPARQL, data=urllib.parse.urlencode({"query": q}).encode(),
                                         headers={"User-Agent": UA, "Accept": "application/sparql-results+json",
                                                  "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=120, context=ctx()) as r:
                data = json.loads(r.read())
            path.write_text(json.dumps(data, ensure_ascii=False))
            time.sleep(1.5)
            return data
        except Exception as e:
            print(f"    failed ({str(e)[:80]}), try {i + 1}/3", flush=True)
            time.sleep(10 * (i + 1))
    raise SystemExit("Wikidata kept failing; run the same command again later (finished batches are cached)")


def main() -> None:
    entries = [e for e in json.load(open(ENTRIES, encoding="utf-8"))["entries"] if e["kind"] not in ("animal", "mineral")]
    try:
        import opencc
        t2s = opencc.OpenCC("t2s").convert
    except ImportError:
        t2s = None
        print("OpenCC not installed: traditional forms only (pip install opencc-python-reimplemented)")
    uses = {}                                         # name form -> [(entry, name, layer)]
    for e in entries:
        layered = [(e["name"], "headword")] + [(n, "classic") for n in e["classic"]["other_names"]]
        layered += [(n, layer) for layer in ("wu_pu", "mingyi") for n in e["other_names_by_layer"][layer]]
        for n, layer in layered:
            if not n or re.search(r"　|KT", n):
                continue
            names = [(n, layer)]
            if len(n) > 2 and n[-1] in PARTS:
                names.append((n[:-1], layer + " (without part)"))
            for nm, ly in names:
                for form in {nm, t2s(nm) if t2s else nm}:
                    uses.setdefault(form, []).append((e["label"], nm, ly))
    forms = sorted(uses)
    rows = []
    for i in range(0, len(forms), BATCH):
        chunk = forms[i:i + BATCH]
        vals = " ".join(f'"{f}"@{l}' for f in chunk for l in LANGS)
        q = f"""SELECT ?item ?taxon ?rank ?lab ?route WHERE {{
          VALUES ?lab {{ {vals} }}
          {{ ?item rdfs:label|skos:altLabel ?lab . ?item wdt:P225 ?taxon . BIND("taxon label" AS ?route) }}
          UNION
          {{ ?drug rdfs:label|skos:altLabel ?lab . ?drug wdt:P1582 ?item . ?item wdt:P225 ?taxon .
             BIND("crude drug" AS ?route) }}
          OPTIONAL {{ ?item wdt:P105 ?r . ?r rdfs:label ?rank FILTER(lang(?rank) = "en") }} }}"""
        data = sparql(q, f"batch_{i // BATCH:03d}_{len(chunk)}_{abs(hash(tuple(chunk))) % 10**8}")
        for b in data["results"]["bindings"]:
            f = b["lab"]["value"]
            for label, name, layer in uses.get(f, []):
                rows.append({"entry": label, "name": name, "layer": layer, "matched_form": f,
                             "language": b["lab"].get("xml:lang"), "route": b["route"]["value"],
                             "qid": b["item"]["value"].rsplit("/", 1)[1], "scientific_name": b["taxon"]["value"],
                             "rank": b.get("rank", {}).get("value")})
        print(f"  {min(i + BATCH, len(forms))}/{len(forms)} name forms, {len(rows)} rows", flush=True)
    rows = [dict(t) for t in {tuple(sorted(r.items())) for r in rows}]
    rows.sort(key=lambda r: (r["entry"], r["layer"], r["scientific_name"]))
    OUT.write_text(json.dumps({"source": "Wikidata SPARQL, Chinese labels and aliases (CC0)",
                               "languages": LANGS, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    hit = {r["entry"] for r in rows}
    head = {r["entry"] for r in rows if r["layer"].startswith("headword")}
    print(f"\n{len(entries)} plant entries · with any taxon {len(hit)} · through the headword {len(head)}")
    print(f"rows by route: {dict(Counter(r['route'] for r in rows))} · by layer: {dict(Counter(r['layer'] for r in rows))}")
    print(f"Saved to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
