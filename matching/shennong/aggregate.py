"""Collect every scientific-name candidate for every Shennong Bencao Jing entry, with graded evidence.

Usage:  python3 matching/shennong/aggregate.py
        python3 matching/shennong/aggregate.py --show 1.33     # one entry

Reads  historical_texts/shennong/entries.json                    the entries (extract_sun.py)
       historical_texts/shennong/bretschneider_ids.json          Bretschneider (1895), checked identifications
       common_name_sources/wikidata/shennong/wikidata.json       Wikidata, Chinese labels (source_wikidata.py)
       scientific_name_sources/wcvp/data/wcvp_names.csv           genera: plant check and OCR repair
Writes to matching/shennong/ the same files as matching/dioscorides/aggregate.py, so the scientific phase
(WFO, WCVP, Global Names, IPNI, resolve_scientific.py, geography.py, eligibility.py) runs with --book shennong:
  evidence.jsonl, candidates.json, scientific_name_candidates.json, scientific_name_queries.jsonl

Bridges, and how strong each is (the role LSJ plays for Dioscorides is played by Bretschneider):
  strong  bretschneider_verdict    his own verdict on what the drug is, proposed by Claude and checked by a
                                   person (review/bretschneider_strong.csv); passage-specific
  medium  bretschneider_reading    his reading of a Chinese illustration, the name's 19th-century usage in
                                   China, or a drug sample he examined
          bretschneider_quoted     an author or list he quotes (Loureiro, Tatarinov, Henry, Customs lists ...);
                                   each author is a lineage of its own
          wikidata_crude_drug      a Wikidata crude-drug item with this name names its source taxon (P1582)
          wikidata_label           a taxon whose Chinese label or alias is the headword
  weak    bretschneider_weak       anything he calls doubtful
  (left out: Japanese usage of the same characters and the Japanese works he quotes, Phon zo zu set, So moku,
  Kwa wi, Siebold, Kaempfer ...: the same characters can name another plant in Japan, as 人参 is carrot)
          wikidata_other_name      a taxon labelled with one of the entry's other names (一名, Wu Pu, Famous
                                   Physicians): the same name can belong to another drug
Bretschneider's Latin names are OCR: an author's name is cut off, an abbreviated genus ("D. japonica") is
expanded from the same entry's rows, and a genus not in WCVP is repaired to the nearest WCVP genus (at least
80% alike), preferring a genus the entry's other sources already name ("Gnanthe" -> Oenanthe, "Pwonia" ->
Paeonia: the nearest WCVP genera would be Gymnanthes and Pontia); words split by a line-break hyphen are
rejoined ("Adeno- phora"); and a species name not in WCVP for its genus is corrected to the nearest one listed (at
least 80% alike, "monnierit" -> monnieri); every repair is recorded in the row.
Animals and minerals (kind from the plain Wikisource version) are skipped.
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from difflib import get_close_matches
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TEXT = ROOT / "historical_texts" / "shennong"
WIKIDATA = ROOT / "common_name_sources" / "wikidata" / "shennong" / "wikidata.json"
WCVP = ROOT / "scientific_name_sources" / "wcvp" / "data" / "wcvp_names.csv"
sys.path.insert(0, str(ROOT / "matching" / "culpeper"))
from aggregate import canonical, slug  # noqa: E402  (same scientific-name normalisation)

GRADE = {"bretschneider_verdict": "strong", "bretschneider_reading": "medium", "bretschneider_quoted": "medium",
         "wikidata_crude_drug": "medium", "wikidata_label": "medium", "bretschneider_weak": "weak",
         "wikidata_other_name": "weak"}
EXTRA_GENERA = {"Lemna", "Usnea", "Ganoderma", "Poria", "Wolfiporia", "Polyporus", "Auricularia"}


def load(p: Path):
    return json.load(open(p, encoding="utf-8")) if p.exists() else None


def clean_name(raw: str, genera: set, siblings: list, species: dict) -> tuple:
    """OCR'd Latin name -> (clean name or None, repairs). Every repair is checked against WCVP and recorded."""
    fixes = []
    t = re.sub(r"\s+", " ", raw).strip()
    t = re.sub(r"\(([A-Z][a-z]+)\)", "", t).strip()               # "Boymia (Evodia) rutecarpa", "Pulsatilla (Anemone)"
    t = re.split(r",|\s(?:L|DC|Pall|Sims|Benth|Maxim|Max|Thunb|Juss|Laxm|Lam|Roxbg|Ker|Bge|Fischer|Schott|Ten|"
                 r"Turcz|Nees|Al\.\s?Br|Hance|Franch|Oliv|Mig|Miq|Sieb|Zucc|S\.\s?&\s?Z)\b", t)[0].strip(" .")
    t = re.sub(r"\bvar[-.]?\s.*$", "", t).strip()                   # varieties: kept at species level here
    t = re.sub(r"(\w)-\s+(\w)", r"\1\2", t)                        # a line-break hyphen: "Adeno- phora"
    words = t.split()
    if not words:
        return None, fixes
    g = re.sub(r"^[^A-Za-z]+", "", words[0])                        # "(rentiana", "@leditechia", "T'richosan-"
    g = g.replace("’", "").replace("'", "").replace("‘", "")
    sib_genera = [re.sub(r"[^A-Za-z]", "", s.split()[0]) for s in siblings if s.split()]
    if re.fullmatch(r"[A-Z][a-z]{0,2}\.?", g) and len(words) > 1:  # "D. japonica", "Gl. glabra", "O. spicatus"
        full = next((x for x in sib_genera if x.startswith(g.rstrip(".")) and len(x) > 3), None)
        if not full:
            return None, fixes + ["abbreviated genus not found in the same entry"]
        fixes.append(f"genus {g} -> {full}")
        g = full
    g = g[:1].upper() + g[1:].lower()
    if g not in genera:                                              # the ligatures Œ and Æ, read as G, C or E:
        lig = next((x for x in ("Oe" + g[1:], "Ae" + g[1:]) if x in genera), None)   # "Gnanthe" = Œnanthe
        if lig:
            fixes.append(f"OCR {g} -> {lig} (ligature)")
            g = lig
    if re.search(r"(aceae|eae|iadea)$", g) and g not in genera:      # a family or tribe ("Aselepiadea")
        return None, fixes + [f"{g}: a family or tribe, not a genus"]
    if g not in genera:
        # first the genera this entry's other sources name (Wikidata gives Paeonia for 芍藥, Oenanthe for 水靳):
        # "Pwonia" -> Paeonia, not the nearest WCVP genus Pontia; then any WCVP genus, at least 80% alike
        sib = [x for x in dict.fromkeys(sib_genera) if x in genera and x != g]
        near = get_close_matches(g, sib, n=1, cutoff=0.6) or get_close_matches(g, genera, n=1, cutoff=0.8)
        if not near:
            return None, fixes + [f"genus {g} not in WCVP"]
        fixes.append(f"OCR {g} -> {near[0]}" + (" (a genus this entry's other sources name)" if near[0] in sib else ""))
        g = near[0]
    sp = [w.lower() for w in words[1:2] if re.fullmatch(r"[A-Za-z\-]{3,}", w)]
    if sp and species.get(g) and sp[0] not in species[g]:
        near = get_close_matches(sp[0], species[g], n=1, cutoff=0.8)
        if near:
            fixes.append(f"OCR {sp[0]} -> {near[0]}")
            sp = [near[0]]
        else:
            fixes.append(f"species {sp[0]} not in WCVP for {g} (kept as printed)")
    return " ".join([g] + sp), fixes


def main() -> None:
    entries = [e for e in load(TEXT / "entries.json")["entries"] if e["kind"] not in ("animal", "mineral")]
    bret = (load(TEXT / "bretschneider_ids.json") or {"rows": []})["rows"]
    wd = (load(WIKIDATA) or {"rows": []})["rows"]
    genera, species = set(), defaultdict(set)
    if WCVP.exists():
        with open(WCVP, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter="|", quoting=csv.QUOTE_NONE):
                if r["genus"]:
                    genera.add(r["genus"])
                    if r["species"]:
                        species[r["genus"]].add(r["species"])
    genera |= EXTRA_GENERA
    species = {g: sorted(v) for g, v in species.items()}
    by_label = {e["label"]: e for e in entries}
    rows, unusable, skipped_japanese = [], Counter(), [0]

    def add(e, name, layer, bridge, sci, detail, lineage):
        node, level, variety = canonical(sci)
        if not node:
            return
        rows.append({"chapter": e["id"], "label": e["label"], "book_name": name, "layer": layer,
                     "attributed_to": None, "bridge": bridge, "grade": GRADE[bridge], "lineage": lineage,
                     "source": bridge.split("_")[0], "candidate": sci, "node": node, "level": level,
                     "variety": variety, "kingdom": "Plantae" if node.split()[0] in genera else None,
                     "detail": detail})

    for r in bret:
        e = by_label.get(r["entry"])
        if not e:
            continue
        if r["basis"] in ("Japanese work", "name usage, Japan"):
            skipped_japanese[0] += 1               # Chinese text: Japanese usage of the same characters is left out
            continue
        siblings = [x["scientific_name"] for x in bret if x["entry"] == r["entry"]]
        sib = siblings + [w["scientific_name"] for w in wd if w["entry"] == r["entry"]]
        sci, fixes = clean_name(r["scientific_name"], genera, sib, species)
        if not sci:
            unusable[fixes[-1] if fixes else "empty"] += 1
            continue
        if r["grade"] == "strong":
            bridge, lineage = "bretschneider_verdict", "Bretschneider"
        elif r["grade"] == "weak":
            bridge, lineage = "bretschneider_weak", "Japanese works" if r["basis"] == "Japanese work" else "Bretschneider"
        elif r["by"] == "Bretschneider":
            bridge, lineage = "bretschneider_reading", "Bretschneider"
        else:
            bridge, lineage = "bretschneider_quoted", r["by"]
        add(e, e["name"], "headword", bridge, sci,
            {"as_printed": r["scientific_name"], "repairs": fixes, "by": r["by"], "basis": r["basis"],
             "certainty": r["certainty"], "quote": r["quote"], "bretschneider_entry": r["bretschneider_entry"],
             "review": r.get("review")}, lineage)

    for r in wd:
        e = by_label.get(r["entry"])
        if not e or (r.get("rank") or "species") not in ("species", "subspecies", "variety", "form", "genus"):
            continue
        head = r["layer"].startswith("headword")
        bridge = ("wikidata_crude_drug" if r["route"] == "crude drug" and head else
                  "wikidata_label" if head else "wikidata_other_name")
        add(e, r["name"], r["layer"], bridge, r["scientific_name"],
            {"qid": r["qid"], "matched": r["matched_form"], "language": r["language"], "route": r["route"]},
            "Wikidata")

    seen, ev = set(), []
    for r in rows:                                    # one row per (entry, name, bridge, lineage, candidate)
        k = (r["chapter"], r["book_name"], r["bridge"], r["lineage"], r["node"])
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

    cands, by = {}, defaultdict(lambda: defaultdict(list))
    for r in ev:
        by[r["chapter"]][r["node"]].append(r)
    for e in entries:
        out = []
        for node, rs in by[e["id"]].items():
            grade_of = lambda gr: [x for x in rs if x["grade"] == gr]
            strong, medium, weak = grade_of("strong"), grade_of("medium"), grade_of("weak")
            out.append({"scientific_name": node, "level": groups[node]["level"],
                        "kingdom_flag": groups[node]["kingdom_flag"],
                        "book_names": sorted({x["book_name"] for x in strong + medium}),
                        "sources": sorted({x["source"] for x in strong + medium}),
                        "families": sorted({x["bridge"] for x in strong + medium}),
                        "lineages": sorted({x["lineage"] for x in strong + medium}),
                        "bridges": dict(Counter(x["bridge"] for x in rs)),
                        "strong_rows": len(strong), "medium_rows": len(medium), "weak_rows": len(weak),
                        "weak_book_names": sorted({x["book_name"] for x in weak})})
        out.sort(key=lambda x: (-x["strong_rows"], -len(x["lineages"]), -x["medium_rows"],
                                x["level"] != "species", -x["weak_rows"], x["scientific_name"]))
        cands[e["id"]] = {"name": e["name"], "label": e["label"], "candidates": out}

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

    grades, bridges = Counter(r["grade"] for r in ev), Counter(r["bridge"] for r in ev)
    top = lambda c, gr: [x for x in c["candidates"] if x["level"] == "species" and x[f"{gr}_rows"]]
    print(f"\nAggregated {len(entries)} Shennong plant entries\n")
    print(f"  {len(ev):>6} evidence rows: " + ", ".join(f"{k} {grades[k]}" for k in ("strong", "medium", "weak")))
    print("         by bridge: " + ", ".join(f"{k} {n}" for k, n in bridges.most_common()))
    print(f"         Bretschneider names not usable: {dict(unusable) or 'none'} · Japanese usage left out: "
          f"{skipped_japanese[0]}")
    print(f"  {len(groups):>6} scientific-name groups ({sum(g['level'] == 'species' for g in groups.values())} species)")
    print(f"  {sum(1 for c in cands.values() if top(c, 'strong')):>6} entries with a species candidate on strong evidence")
    print(f"  {sum(1 for c in cands.values() if not top(c, 'strong') and top(c, 'medium')):>6} more with medium evidence only")
    print(f"  {sum(1 for c in cands.values() if not c['candidates']):>6} entries with no candidate\n")
    print("Saved to matching/shennong/")
    if "--show" in sys.argv:
        want = sys.argv[sys.argv.index("--show") + 1]
        c = next((v for v in cands.values() if v["label"] == want), None)
        if c:
            print(f"\n{c['label']} {c['name']}:")
            for x in c["candidates"][:12]:
                print(f"  {x['scientific_name'][:32]:32} {x['level']:8} strong={x['strong_rows']} medium={x['medium_rows']} "
                      f"weak={x['weak_rows']} · {', '.join(x['lineages'])}")


if __name__ == "__main__":
    main()
