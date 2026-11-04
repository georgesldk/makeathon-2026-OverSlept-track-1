"""Collect every scientific-name candidate for every Dioscorides chapter, with graded evidence.

Usage:  python3 matching/dioscorides/aggregate.py
        python3 matching/dioscorides/aggregate.py --show 4.75     # one chapter

Reads (each optional except the first two):
  historical_texts/dioscorides/chapters.json               the chapters and their names
  historical_texts/dioscorides/lexicon_lsj.json            Greek lexicon identifications
  historical_texts/dioscorides/lexicon_lewis_short.json    Latin lexicon identifications
  common_name_sources/wikidata/dioscorides/wikidata.json   Wikidata labels in grc, el, la
  scientific_name_sources/wcvp/data/wcvp_names.csv          genera (plant check, genus bridge)
Writes to matching/dioscorides/ the same files as matching/culpeper/aggregate.py, so the
scientific phase (WFO, WCVP, Global Names, IPNI, resolve_scientific.py) runs unchanged:
  evidence.jsonl, candidates.json (per chapter), scientific_name_candidates.json,
  scientific_name_queries.jsonl

Bridges from a Greek or Latin name to a scientific name, and how strong each is:
  strong  lexicon_this_chapter   LSJ gives this binomial for this very chapter
  medium  lexicon_headword       LSJ gives it for the chapter's headword, in another passage
          lexicon_latin          Lewis & Short gives it for a name the Romans use
          wikidata_grc / _la     a taxon whose Ancient Greek / Latin label or alias is the name
  weak    lexicon_synonym        LSJ gives it for one of the chapter's other names, elsewhere
          wikidata_el            a taxon whose modern Greek label or alias is the name
          wikidata_la_same_word  a Latin label that is simply the scientific name itself
                                 (Wikidata's Latin label of Iris is "Iris"): same as above
          same_word_genus        the name's Latin spelling is itself a genus (ἶρις -> Iris);
                                 only a hint: Linnaeus sometimes reused a name for another plant
The lexicons' identifications are scholars' opinions; every row says which bridge it used.
No ranking and no picking: everything is kept, graded, and grouped by scientific name.
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TEXT = ROOT / "historical_texts" / "dioscorides"
WIKIDATA = ROOT / "common_name_sources" / "wikidata" / "dioscorides" / "wikidata.json"
WCVP = ROOT / "scientific_name_sources" / "wcvp" / "data" / "wcvp_names.csv"
sys.path.insert(0, str(ROOT / "matching" / "culpeper"))
from aggregate import canonical, slug  # noqa: E402  (same scientific-name normalisation)

GRADE = {"lexicon_this_chapter": "strong", "lexicon_headword": "medium", "lexicon_latin": "medium",
         "wikidata_grc": "medium", "wikidata_la": "medium", "lexicon_synonym": "weak",
         "wikidata_el": "weak", "same_word_genus": "weak", "wikidata_la_same_word": "weak"}
EXTRA_GENERA = {"Ulva", "Usnea", "Marchantia", "Fucus", "Lichen", "Agaricus", "Boletus", "Polyporus",
                "Fomes", "Cetraria", "Lecanora", "Roccella", "Corallina", "Chondrus", "Sphaerococcus"}


def load(p: Path):
    return json.load(open(p, encoding="utf-8")) if p.exists() else None


def main() -> None:
    chapters = [c for c in load(TEXT / "chapters.json")["chapters"] if c["chapter"] != "preface"]
    lsj = {c["label"]: c for c in (load(TEXT / "lexicon_lsj.json") or {"chapters": []})["chapters"]}
    ls = {c["label"]: c for c in (load(TEXT / "lexicon_lewis_short.json") or {"chapters": []})["chapters"]}
    wd = load(WIKIDATA) or {"names": {}}
    genera = set()
    if WCVP.exists():
        with open(WCVP, encoding="utf-8", newline="") as f:
            genera = {r["genus"] for r in csv.DictReader(f, delimiter="|", quoting=csv.QUOTE_NONE) if r["genus"]}
    genera |= EXTRA_GENERA
    used = {"lsj": bool(lsj), "lewis_short": bool(ls), "wikidata": bool(wd["names"]), "wcvp_genera": WCVP.exists()}

    rows = []

    def add(c, name, layer, who, bridge, sci, detail):
        node, level, variety = canonical(sci)
        if not node:
            return
        rows.append({"chapter": c["id"], "label": c["label"], "book_name": name, "layer": layer,
                     "attributed_to": who, "bridge": bridge, "grade": GRADE[bridge],
                     "source": bridge.split("_")[0] if not bridge.startswith("same") else "wcvp",
                     "candidate": sci, "node": node, "level": level, "variety": variety,
                     "kingdom": "Plantae" if node.split()[0] in genera else None, "detail": detail})

    for c in chapters:
        L = lsj.get(c["label"], {"names": []})
        for n in L["names"]:
            for e in n["entries"]:
                for x in e["identifications"]:
                    bridge = ("lexicon_this_chapter" if x["cites_this_chapter"]
                              else "lexicon_headword" if n["layer"] == "headword" else "lexicon_synonym")
                    add(c, n["name"], n["layer"], n["attributed_to"], bridge, x["binomial"],
                        {"lexicon": "LSJ", "entry": e["lsj_key"], "gloss": x["gloss"],
                         "cites": x["dsc"] + [f"Ps.-Dsc. {p}" for p in x["pseudo_dsc"]]})
            # the Latin spelling is itself a genus name
            latin = (n.get("latin_form") or "").split()
            if latin and len(latin[0]) > 3:
                w = latin[0].capitalize()
                # Latin genus endings differ from the Greek: acorum -> Acorus, mandragoras -> Mandragora
                forms = [w, w[:-2] + "us" if w.endswith("um") else None, w[:-1] if w.endswith("as") else None,
                         w[:-2] + "um" if w.endswith("us") else None, w[:-1] if w.endswith("es") else None]
                hit = next((f for f in forms if f and f in genera), None)
                if hit:
                    add(c, n["name"], n["layer"], n["attributed_to"], "same_word_genus", hit,
                        {"latin_form": n["latin_form"]})
            for h in (wd["names"].get(n["name"]) or {}).get("hits", []):
                if h["exact_name_match"] and h.get("taxon_name"):
                    bridge = f"wikidata_{h['searched_language']}"
                    if bridge == "wikidata_la" and h["taxon_name"].split()[0].lower() == h["searched"].split()[0].lower():
                        bridge = "wikidata_la_same_word"
                    add(c, n["name"], n["layer"], n["attributed_to"], bridge,
                        h["taxon_name"], {"qid": h["qid"], "matched": h["matched_text"],
                                          "language": h["searched_language"]})
        for n in ls.get(c["label"], {"names": []})["names"]:
            for e in n["entries"]:
                for x in e["identifications"]:
                    add(c, n["name"], n["layer"], n["attributed_to"], "lexicon_latin", x["binomial"],
                        {"lexicon": "Lewis & Short", "entry": e["ls_key"], "gloss": x["gloss"]})

    # one row per (chapter, name, bridge, candidate)
    seen, ev = set(), []
    for r in rows:
        k = (r["chapter"], r["book_name"], r["bridge"], r["node"])
        if k not in seen:
            seen.add(k)
            ev.append(r)

    groups = {}
    for r in ev:
        g = groups.setdefault(r["node"], {"name": r["node"], "level": r["level"], "original_forms": set(),
                                          "varieties": set(), "kingdoms": set(), "sources": set(), "herbs": set()})
        g["original_forms"].add(r["candidate"])
        if r["variety"]:
            g["varieties"].add(r["variety"])
        if r["kingdom"]:
            g["kingdoms"].add(r["kingdom"])
        g["sources"].add(r["source"])
        g["herbs"].add(r["chapter"])
    for g in groups.values():
        g["kingdom_flag"] = "plant" if g["kingdoms"] == {"Plantae"} else "unknown"

    cands = {}
    by = defaultdict(lambda: defaultdict(list))
    for r in ev:
        by[r["chapter"]][r["node"]].append(r)
    for c in chapters:
        out = []
        for node, rs in by[c["id"]].items():
            grade_of = lambda rr: [x for x in rs if x["grade"] == rr]
            strong, medium, weak = grade_of("strong"), grade_of("medium"), grade_of("weak")
            out.append({"scientific_name": node, "level": groups[node]["level"],
                        "kingdom_flag": groups[node]["kingdom_flag"],
                        "book_names": sorted({x["book_name"] for x in strong + medium}),
                        "sources": sorted({x["source"] for x in strong + medium}),
                        "families": sorted({x["bridge"] for x in strong + medium}),
                        "bridges": dict(Counter(x["bridge"] for x in rs)),
                        "strong_rows": len(strong), "medium_rows": len(medium), "weak_rows": len(weak),
                        "weak_book_names": sorted({x["book_name"] for x in weak})})
        out.sort(key=lambda x: (-x["strong_rows"], -len(x["book_names"]), -x["medium_rows"],
                                x["level"] != "species", -x["weak_rows"], x["scientific_name"]))
        cands[c["id"]] = {"name": c["headword"], "label": c["label"], "candidates": out}

    with open(HERE / "evidence.jsonl", "w", encoding="utf-8") as f:
        for r in ev:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    as_json = lambda g: {**g, **{k: sorted(g[k]) for k in ("original_forms", "varieties", "kingdoms", "sources")},
                         "herbs": len(g["herbs"])}
    (HERE / "scientific_name_candidates.json").write_text(json.dumps(
        {k: as_json(v) for k, v in sorted(groups.items())}, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(HERE / "scientific_name_queries.jsonl", "w", encoding="utf-8") as f:
        for k, g in sorted(groups.items()):
            f.write(json.dumps({"query_id": f"scientific-name:{slug(k)}", "name": k, "level": g["level"],
                                "original_forms": sorted(g["original_forms"]), "varieties": sorted(g["varieties"]),
                                "kingdom_flag": g["kingdom_flag"], "sources": sorted(g["sources"]),
                                "herbs": len(g["herbs"]), "status": "pending"}, ensure_ascii=False) + "\n")
    (HERE / "candidates.json").write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")

    grades = Counter(r["grade"] for r in ev)
    bridges = Counter(r["bridge"] for r in ev)
    top = lambda c, g: [x for x in c["candidates"] if x["level"] == "species" and x[f"{g}_rows"]]
    print(f"\nAggregated {len(chapters)} Dioscorides chapters "
          f"(inputs: {', '.join(k for k, v in used.items() if v)}; missing: "
          f"{', '.join(k for k, v in used.items() if not v) or 'none'})\n")
    print(f"  {len(ev):>6} evidence rows: " + ", ".join(f"{k} {grades[k]}" for k in ("strong", "medium", "weak")))
    print("         by bridge: " + ", ".join(f"{k} {n}" for k, n in bridges.most_common()))
    print(f"  {len(groups):>6} scientific-name groups ({sum(g['level'] == 'species' for g in groups.values())} species)\n")
    print(f"  {sum(1 for c in cands.values() if top(c, 'strong')):>4} chapters with a species candidate on strong evidence")
    print(f"  {sum(1 for c in cands.values() if not top(c, 'strong') and top(c, 'medium')):>4} more with medium evidence only")
    print(f"  {sum(1 for c in cands.values() if not c['candidates']):>4} chapters with no candidate at all "
          f"(many are animals, minerals, wines and preparations)\n")
    print("Saved to matching/dioscorides/: evidence.jsonl, candidates.json, scientific_name_candidates.json,\n"
          "  scientific_name_queries.jsonl\n")

    if "--show" in sys.argv:
        want = sys.argv[sys.argv.index("--show") + 1]
        c = next((v for v in cands.values() if v["label"] == want), None)
        if c:
            print(f"{c['label']} {c['name']}:")
            for x in c["candidates"][:12]:
                print(f"  {x['scientific_name'][:30]:30} {x['level']:7} strong={x['strong_rows']} medium={x['medium_rows']} "
                      f"weak={x['weak_rows']}  " + ", ".join(f"{k} {n}" for k, n in x["bridges"].items()))


if __name__ == "__main__":
    main()
