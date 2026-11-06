"""Feasibility check for identifying the Shennong Bencao Jing plants (Stage 2), before building anything.

Usage:  python3 historical_texts/shennong/check_sources.py
        (pip install opencc-python-reimplemented  first, for simplified-character names; optional)

1. Bretschneider, Botanicon Sinicum (1882-1895, public domain), from the Biodiversity Heritage Library
   (API v3, BHL_API_KEY in .env, never written anywhere): lists its volumes, fetches the OCR of the
   volume that covers the Shen nung pen ts'ao (Part III, "Botanical investigations into the materia medica
   of the ancient Chinese", 1895), and reports how readable it is.
   Saved: reference_sources/bretschneider/  (BHL replies, one file per call)
2. Wikidata (CC0): which taxa have one of our Chinese names as a label or alias (traditional, and
   simplified when OpenCC is installed), and which crude-drug items name a source taxon (P1582).
   One SPARQL query per 60 names. Saved: common_name_sources/wikidata/shennong/check.json
Writes no pipeline outputs; prints a report.
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
ROOT = HERE.parent.parent
ENTRIES = HERE / "entries.json"
BHL_DIR = ROOT / "reference_sources" / "bretschneider"
WD_OUT = ROOT / "common_name_sources" / "wikidata" / "shennong" / "check.json"
BHL = "https://www.biodiversitylibrary.org/api3"
SPARQL = "https://query.wikidata.org/sparql"
UA = "EthnoHack-OverSlept/0.3 (research; non-commercial)"
TITLE_ID = 4313                                  # Botanicon sinicum, BHL bibliography 4313
LANGS = ["zh", "zh-hant", "zh-hans", "zh-tw", "zh-hk", "zh-cn", "ja"]
PARTS = "子實仁根花葉皮莖汁核膠脂骨角甲"            # plant (and animal) part endings: 車前子 -> 車前


def ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CTX = ctx()


def env(name):
    for line in open(ROOT / ".env", encoding="utf-8"):
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit(f"{name} not found in .env")


def get(url, data=None, headers=None, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
                return r.read()
        except Exception as e:
            print(f"    failed ({str(e)[:80]}), try {i + 1}/{tries}", flush=True)
            time.sleep(5 * (i + 1))
    raise SystemExit("gave up; run the same command again later (saved replies are kept)")


def bhl(op, **params):
    BHL_DIR.mkdir(parents=True, exist_ok=True)
    path = BHL_DIR / (re.sub(r"[^\w]+", "_", f"{op}_{'_'.join(map(str, params.values()))}") + ".json")
    if path.exists():
        return json.loads(path.read_text())
    q = urllib.parse.urlencode({"op": op, **params, "format": "json", "apikey": env("BHL_API_KEY")})
    data = json.loads(get(f"{BHL}?{q}"))
    path.write_text(json.dumps(data, ensure_ascii=False))
    time.sleep(1)
    return data


def check_bhl():
    print("== 1. Bretschneider, Botanicon Sinicum (BHL)")
    meta = bhl("GetTitleMetadata", id=TITLE_ID, items="t")
    items = (meta.get("Result") or [{}])[0].get("Items", [])
    for it in items:
        print(f"  item {it.get('ItemID')}: {it.get('Volume') or ''} {it.get('Year') or ''} · {it.get('ItemUrl')}")
    best = None
    for it in items:
        m = bhl("GetItemMetadata", id=it["ItemID"], pages="t", ocr="t")
        pages = (m.get("Result") or [{}])[0].get("Pages", [])
        text = "\n".join(p.get("OcrText") or "" for p in pages)
        hits = len(re.findall(r"Shen[\s-]*nung|pen[\s-]*ts.ao[\s-]*king", text, re.I))
        bins = len(re.findall(r"\b[A-Z][a-z]{3,}\s[a-z]{4,}\b", text))
        print(f"    item {it['ItemID']}: {len(pages)} pages, {len(text):,} characters of OCR, "
              f"'Shen nung' {hits} times, ~{bins:,} Latin-looking binomials")
        if hits and (best is None or hits > best[0]):
            best = (hits, it["ItemID"], pages)
    if not best:
        print("  no volume mentions the Shen nung pen ts'ao in its OCR")
        return
    _, iid, pages = best
    print(f"\n  The Shennong volume looks like item {iid}. Samples of its OCR:")
    shown = 0
    for p in pages:
        t = p.get("OcrText") or ""
        if re.search(r"Ch.e[\s-]*ts.ien|Plantago", t) or (shown < 2 and len(t) > 1500 and re.search(r"\b[A-Z][a-z]+ [a-z]+, L\.", t)):
            i = max(0, (re.search(r"Ch.e[\s-]*ts.ien|Plantago", t) or re.search(r".", t)).start() - 300)
            print(f"\n  --- page {p.get('PageID')} ---\n" + re.sub(r"\n+", "\n", t[i:i + 1200]))
            shown += 1
        if shown >= 3:
            break
    chinese = sum(len(re.findall(r"[一-鿿]", p.get("OcrText") or "")) for p in pages)
    print(f"\n  Chinese characters in the OCR: {chinese:,} (few means they were not recognised; we would "
          f"match on the romanised names)")


def names():
    E = [e for e in json.load(open(ENTRIES, encoding="utf-8"))["entries"] if e["kind"] not in ("animal", "mineral")]
    out = {}
    for e in E:
        for n in [e["name"]] + e["classic"]["other_names"]:
            if not n or re.search(r"[　]|KT", n):
                continue
            out.setdefault(n, set()).add((e["label"], "headword" if n == e["name"] else "other name"))
            if len(n) > 1 and n[-1] in PARTS:
                out.setdefault(n[:-1], set()).add((e["label"], "headword without part" if n == e["name"] else "other name without part"))
    return E, out


def check_wikidata():
    print("\n== 2. Wikidata: taxa with our Chinese names")
    E, nm = names()
    try:
        import opencc
        conv = opencc.OpenCC("t2s")
        simp = {n: conv.convert(n) for n in nm}
    except ImportError:
        simp = {n: n for n in nm}
        print("  (OpenCC not installed: traditional forms only. pip install opencc-python-reimplemented)")
    forms = {}
    for n in nm:
        for f in {n, simp[n]}:
            forms.setdefault(f, set()).add(n)
    keys = sorted(forms)
    rows = []
    for i in range(0, len(keys), 60):
        vals = " ".join(f'"{k}"@{l}' for k in keys[i:i + 60] for l in LANGS)
        q = f"""SELECT ?item ?taxon ?rank ?lab ?via WHERE {{
          VALUES ?lab {{ {vals} }}
          {{ ?item rdfs:label|skos:altLabel ?lab . ?item wdt:P225 ?taxon . BIND("taxon label" AS ?via) }}
          UNION
          {{ ?drug rdfs:label|skos:altLabel ?lab . ?drug wdt:P1582 ?item . ?item wdt:P225 ?taxon . BIND("crude drug -> taxon" AS ?via) }}
          OPTIONAL {{ ?item wdt:P105 ?r . ?r rdfs:label ?rank FILTER(lang(?rank) = "en") }}
        }}"""
        data = json.loads(get(SPARQL, urllib.parse.urlencode({"query": q}).encode(),
                              {"Accept": "application/sparql-results+json",
                               "Content-Type": "application/x-www-form-urlencoded"}))
        for b in data["results"]["bindings"]:
            rows.append({"form": b["lab"]["value"], "lang": b["lab"].get("xml:lang"), "item": b["item"]["value"].rsplit("/", 1)[1],
                         "taxon": b["taxon"]["value"], "rank": b.get("rank", {}).get("value"), "via": b["via"]["value"]})
        print(f"  {min(i + 60, len(keys))}/{len(keys)} name forms queried, {len(rows)} hits so far", flush=True)
        time.sleep(1.5)
    WD_OUT.parent.mkdir(parents=True, exist_ok=True)
    WD_OUT.write_text(json.dumps({"source": "Wikidata SPARQL (CC0)", "rows": rows}, ensure_ascii=False, indent=1))
    hit_names = {n for r in rows for n in forms.get(r["form"], [])}
    entries_hit = {lab for n in hit_names for lab, _ in nm[n]}
    head_hit = {lab for n in hit_names for lab, how in nm[n] if how.startswith("headword")}
    species = {lab for r in rows if r["rank"] in ("species", "subspecies", "variety") for n in forms[r["form"]]
               for lab, how in nm[n] if how.startswith("headword")}
    print(f"\n  plant entries (herb, tree, fruit, grain, or kind unknown): {len(E)}")
    print(f"  entries with any Wikidata taxon: {len(entries_hit)} · through the headword: {len(head_hit)} · "
          f"headword -> a species or below: {len(species)}")
    print(f"  hits by route: {dict(Counter(r['via'] for r in rows))}")
    for e in E[:400]:
        if e["label"] in ("1.33", "1.22", "1.20", "2.21", "1.18"):
            got = sorted({(r["taxon"], r["via"]) for r in rows for n in forms.get(r["form"], []) if (e["label"], "headword") in nm[n] or (e["label"], "headword without part") in nm[n]})
            print(f"    {e['label']} {e['name']}: {got[:6]}")


if __name__ == "__main__":
    check_bhl()
    check_wikidata()
    print(f"\nSaved: {BHL_DIR.relative_to(ROOT)}/, {WD_OUT.relative_to(ROOT)}")
