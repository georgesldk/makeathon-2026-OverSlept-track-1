"""Map the MeSH headings the model proposed but MeSH does not have (often old medical words:
strangury, quartan ague, induration) to real MeSH descriptors, from two open sources.

Usage:  python3 claims/map_historical_terms.py              (Disease Ontology + Wikidata; Wikidata needs internet)
        python3 claims/map_historical_terms.py --offline    (Disease Ontology only)
Then rerun the claims import, which uses the table only when the normal MeSH lookup fails.

Sources, both named in the hackathon's dataset list:
  1. Disease Ontology (DOID, CC0): a term equal to a disease's name or EXACT synonym, and that
     disease's cross-reference to MeSH  (reference_sources/doid/doid.obo, release in the file)
  2. Wikidata (CC0): an item whose English label or alias equals the term, and its MeSH
     descriptor ID (property P486). Only exact label/alias matches count.
A term is mapped only when the sources that answer give ONE MeSH descriptor that exists in our
MeSH file. If they disagree, it is left unmapped and marked "conflict" for a person to decide.
Output: claims/historical_terms.csv. Rows a person marked approved=y or edited by hand are kept.
"""
import argparse
import csv
import gzip
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "historical_terms.csv"
DOID = ROOT / "reference_sources/doid/doid.obo"
MESH = ROOT / "reference_sources/mesh/mesh_index.json.gz"
CACHE = HERE / "cache" / "wikidata"
API = "https://www.wikidata.org/w/api.php"
FIELDS = ["old_term", "count", "books", "example_claim", "mesh_ui", "mesh_name", "match", "source",
          "status", "approved", "note"]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def variants(term: str) -> list:
    """The term as written, and MeSH-style inverted names turned round ("Malaria, Quartan" -> "Quartan Malaria")."""
    out = [term]
    if term.count(",") == 1:
        a, b = [x.strip() for x in term.split(",")]
        out.append(f"{b} {a}")
    return out


def rejected_terms() -> dict:
    out = {}
    for book in ("culpeper", "dioscorides"):
        p = HERE / book / "claims.json"
        if not p.exists():
            continue
        for e in json.load(open(p, encoding="utf-8"))["entries"].values():
            for c in e["claims"]:
                for h in c.get("mesh_not_found", []):
                    r = out.setdefault(norm(h), {"old_term": h, "count": 0, "books": set(), "example_claim": c["claim"]})
                    r["count"] += 1
                    r["books"].add(book)
    return out


def doid_index() -> tuple:
    """norm(name or EXACT synonym) -> {MeSH D-codes}; and the release."""
    idx, release = defaultdict(set), ""
    term = None
    for line in open(DOID, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("data-version:"):
            release = line.split(":", 1)[1].strip()
        if line == "[Term]":
            term = {"names": [], "mesh": set(), "id": None, "obsolete": False}
            continue
        if term is None:
            continue
        if not line:
            if term["mesh"] and not term["obsolete"]:
                for n in term["names"]:
                    idx[norm(n)] |= {(m, term["id"]) for m in term["mesh"]}
            term = None
        elif line.startswith("id: "):
            term["id"] = line[4:]
        elif line.startswith("name: "):
            term["names"].append(line[6:])
        elif line.startswith("synonym: ") and " EXACT" in line:
            m = re.match(r'synonym: "(.*?)" EXACT', line)
            if m:
                term["names"].append(m.group(1))
        elif line.startswith("xref: MESH:D"):
            term["mesh"].add(line.split("MESH:")[1].split()[0])
        elif line.startswith("is_obsolete: true"):
            term["obsolete"] = True
    return idx, release


def ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def wd_get(params: dict) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"\W+", "_", json.dumps(params, sort_keys=True))[:150]
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.load(open(path, encoding="utf-8"))
    q = urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "EthnoHack-OverSlept/0.1 (hackathon research)"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx()) as r:
                data = json.load(r)
            break
        except Exception:
            time.sleep(5 * (attempt + 1))
    else:
        return {}
    path.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(0.5)
    return data


def wikidata(term: str) -> set:
    """{(MeSH UI, QID)} for items whose English label or alias equals the term."""
    hits = wd_get({"action": "wbsearchentities", "search": term, "language": "en", "type": "item", "limit": 10})
    ids = [h["id"] for h in hits.get("search", []) if norm((h.get("match") or {}).get("text", "")) == norm(term)]
    if not ids:
        return set()
    ents = wd_get({"action": "wbgetentities", "ids": "|".join(ids), "props": "claims"}).get("entities", {})
    out = set()
    for qid, e in ents.items():
        for cl in (e.get("claims") or {}).get("P486", []):
            v = ((cl.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if v:
                out.add((v, qid))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="Disease Ontology only, no Wikidata")
    a = ap.parse_args()
    D = json.load(gzip.open(MESH, "rt", encoding="utf-8"))["descriptors"]
    terms = rejected_terms()
    doid, release = doid_index()
    kept = {}
    if OUT.exists():                           # keep what a person approved or edited
        for r in csv.DictReader(open(OUT, encoding="utf-8")):
            if r.get("approved", "").strip().lower().startswith("y") or r.get("status") == "manual":
                kept[norm(r["old_term"])] = r
    rows, stats = [], defaultdict(int)
    order = sorted(terms.items(), key=lambda x: -x[1]["count"])
    print(f"{len(order)} terms to look up" + (" (Disease Ontology only)" if a.offline else " in Disease Ontology and Wikidata"))
    for n, (k, t) in enumerate(order, 1):
        print(f"  [{n}/{len(order)}] {t['old_term']} ({t['count']} uses) ...", end=" ", flush=True)
        row = {"old_term": t["old_term"], "count": t["count"], "books": ", ".join(sorted(t["books"])),
               "example_claim": t["example_claim"]}
        if k in kept:
            rows.append({**kept[k], **{x: row[x] for x in ("count", "books", "example_claim")}})
            stats["kept (approved)"] += 1
            print(f"kept: {kept[k].get('mesh_name') or 'unmapped'} (approved earlier)")
            continue
        found = {}                             # MeSH UI -> sources
        for v in variants(t["old_term"]):
            for ui, did in doid.get(norm(v), ()):
                if ui in D:
                    found.setdefault(ui, []).append(f"Disease Ontology {did} ({release})")
            if not a.offline:
                for ui, qid in wikidata(v):
                    if ui in D:
                        found.setdefault(ui, []).append(f"Wikidata {qid}")
        found = {ui: sorted(set(s)) for ui, s in found.items()}
        if len(found) == 1:
            ui, src = next(iter(found.items()))
            row.update(mesh_ui=ui, mesh_name=D[ui]["name"], match="close", source="; ".join(src),
                       status="auto", approved="", note="")
            stats["mapped"] += 1
            print(f"→ {ui} {D[ui]['name']}  [{'; '.join(src)}]")
        elif len(found) > 1:
            row.update(mesh_ui="", mesh_name="", match="", status="conflict", approved="",
                       source="; ".join(f"{ui} {D[ui]['name']}: {', '.join(s)}" for ui, s in found.items()),
                       note="sources disagree: a person decides")
            stats["conflict"] += 1
            print("conflict: " + ", ".join(D[ui]["name"] for ui in found))
        else:
            row.update(mesh_ui="", mesh_name="", match="", source="", status="not found", approved="", note="")
            stats["not found"] += 1
            print("not found")
        rows.append(row)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    total = sum(t["count"] for t in terms.values())
    mapped_uses = sum(int(r["count"]) for r in rows if r.get("mesh_ui"))
    print(f"\n{len(terms)} distinct rejected terms ({total} uses) · " + " · ".join(f"{k} {v}" for k, v in stats.items()))
    print(f"Uses recovered: {mapped_uses} of {total}" + ("  (Disease Ontology only: run without --offline for Wikidata)" if a.offline else ""))
    print(f"Saved to claims/historical_terms.csv. Then rerun the import for each book.")


if __name__ == "__main__":
    main()
