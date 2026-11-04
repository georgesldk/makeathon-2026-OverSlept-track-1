"""Aggregate the common-name sources into plant candidates for every Culpeper herb.

Usage:  python3 matching/culpeper/aggregate.py
        python3 matching/culpeper/aggregate.py --show "Amara Dulcis"   # print one herb

Reads (no network):
  historical_texts/culpeper/herbs.json
  common_name_sources/gbif/culpeper/gbif.json            common_name_sources/wikidata/culpeper/wikidata.json
  common_name_sources/inaturalist/culpeper/inaturalist.json   common_name_sources/checklistbank/culpeper/checklistbank.json
  common_name_sources/drduke/culpeper/drduke.json        common_name_sources/taxtree/culpeper/taxtree.json
Writes to matching/culpeper/:
  evidence.jsonl                  one row per (herb, Culpeper name, source record)
  scientific_name_candidates.json scientific-name groups: identical names, with every
                                  original form, source ID and kingdom
  scientific_name_queries.jsonl   each distinct scientific name once, with its original
                                  forms: the lookup list for WFO and WCVP
  candidates.json                 per herb: its scientific-name groups with an evidence summary
  checklist_families.json         how each ChecklistBank checklist was grouped (for review)

No decisions are made here. Rows are graded:
  strong  exact name, or an exact part of a listed name ("Bittersweet, Woody Nightshade")
  weak    the spelling only occurs inside a longer name (Duke, ChecklistBank), or a
          TaxTree similar-name hit. Weak rows are kept but not counted in summaries.
Plain search results that are neither (GBIF/Wikidata/iNaturalist look-alikes) stay in
the source files only.

Scientific-name groups: each candidate keeps its full name as the source gave it
(with author where available). For grouping, the name is normalised (author dropped,
hybrid sign kept, varieties folded into the species and kept as "variety"); identical
normalised names form one group. A group is a name, not a confirmed plant: synonyms
are NOT merged, and identity is settled later (WFO and WCVP, then historical checks).
When a Wikidata item lists another source's ID (GBIF P846, iNaturalist P3151, NCBI
P685) for a differently named group, that is recorded as a cross-reference, not merged.
Every row carries the kingdom where the source gives it, because the same scientific
name can belong to a plant and an animal; groups are flagged plant / non-plant /
mixed / unknown. Species, genus and family groups stay separate.

Independence: rows are grouped into source families, so one database copied into
another counts once (see checklist_families.json).

"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "common_name_sources" / "gbif" / "culpeper"))
from source_gbif import key  # noqa: E402  (same name normalisation as the sources)

SOURCES = {
    "gbif": "common_name_sources/gbif/culpeper/gbif.json", "wikidata": "common_name_sources/wikidata/culpeper/wikidata.json",
    "inaturalist": "common_name_sources/inaturalist/culpeper/inaturalist.json",
    "checklistbank": "common_name_sources/checklistbank/culpeper/checklistbank.json",
    "drduke": "common_name_sources/drduke/culpeper/drduke.json", "taxtree": "common_name_sources/taxtree/culpeper/taxtree.json",
}
INFRA = {"var.", "subsp.", "ssp.", "f.", "forma", "subvar.", "cv."}


def load(rel: str) -> dict:
    return json.load(open(ROOT / rel, encoding="utf-8"))


def canonical(name: str | None) -> tuple[str | None, str | None, str | None]:
    """Scientific name -> (group name, level, variety). Author dropped, hybrid sign kept."""
    if not name:
        return None, None, None
    tokens = [x for x in re.sub(r"\s+", " ", name.replace("×", " × ")).strip().split(" ") if x]
    hybrid = any(x in ("×", "x") for x in tokens[1:3])
    w = [x for x in tokens if x not in ("×", "x")]
    if not w or not w[0][:1].isalpha():
        return None, None, None
    genus = w[0][:1].upper() + w[0][1:].lower()
    if len(w) >= 2 and w[1][:1].islower() and w[1] not in INFRA \
            and w[1].rstrip(".") not in ("sp", "spp", "cf", "aff"):   # "Abies sp" = some Abies: genus level
        rest = [x for x in w[2:] if x[:1].islower() and x not in INFRA]
        variety = " ".join(rest) if rest and rest[-1] != w[1] else None
        return f"{genus} {'× ' if hybrid else ''}{w[1]}", "species", variety
    level = "family" if genus.endswith("aceae") else "genus"
    return genus, level, None


# Sources spell kingdoms differently (NCBI: Viridiplantae, Metazoa, Bacillati, ...).
# Anything not recognised (e.g. the placeholder "Regnum") counts as no answer.
KINGDOMS = {"plantae": "Plantae", "viridiplantae": "Plantae", "metazoa": "Animalia",
            "animalia": "Animalia", "fungi": "Fungi", "chromista": "Chromista", "protozoa": "Protozoa",
            "bacteria": "Bacteria", "bacillati": "Bacteria", "pseudomonadati": "Bacteria",
            "fusobacteriati": "Bacteria", "thermotogati": "Bacteria",
            "archaea": "Archaea", "thermoproteati": "Archaea", "methanobacteriati": "Archaea",
            "nanobdellati": "Archaea", "promethearchaeati": "Archaea", "viruses": "Viruses"}


def kingdom(k: str | None) -> str | None:
    if not k:
        return None
    k = k.strip().lower()
    return "Viruses" if k.endswith("virae") else KINGDOMS.get(k)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("×", "x")).strip("-")


# --- source families (independence) -----------------------------------------
OWN = {"53147": "gbif", "139831": "inaturalist", "314569": "wikidata"}


def checklist_family(k: str, c: dict) -> tuple[str, str]:
    alias, title = c.get("alias") or "", c.get("title") or ""
    if not c or c.get("inaccessible") or not (alias or title):
        return f"private:{k}", "private checklist, metadata not accessible"
    if k in OWN:
        return OWN[k], f"copy of {OWN[k]}"
    if re.match(r"COL\d", alias) or "Catalogue of Life" in title:
        return "col", "Catalogue of Life release"
    if c.get("sourceKey"):
        return f"checklist:{c['sourceKey']}", "release of a checklist project"
    return f"checklist:{k}", "independent checklist"


def main() -> None:
    herbs = load("historical_texts/culpeper/herbs.json")["herbs"]
    S = {s: load(p) for s, p in SOURCES.items()}
    ck = S["checklistbank"]["checklists"]
    families = {k: checklist_family(k, c) for k, c in ck.items()}

    rows = []

    def add(hid, cul, src, family, matched, mtype, grade, cand, src_rank, rec, lang="", prov=None,
            full=None, king=None):
        node, level, variety = canonical(cand)
        rows.append({"herb": hid, "culpeper_name": cul, "source": src, "family": family,
                     "matched_text": matched, "match_type": mtype, "grade": grade,
                     "candidate": cand, "candidate_full": (full or cand or "").strip() or None,
                     "node": node, "level": level, "variety": variety, "kingdom": kingdom(king),
                     "source_rank": (src_rank or "").lower() or None, "record": rec,
                     "language": lang or None, "provenance": prov or {}})

    for h in herbs:
        hid = h["id"]
        # GBIF
        g = S["gbif"]
        for nm in g["herbs"][hid]["names"]:
            for s in nm["searches"]:
                for r in s["results"]:
                    if not r["exact_name_match"]:
                        continue
                    t = g["taxa"][str(r["key"])]
                    add(hid, nm["name"], "gbif", "gbif", s["spelling"], "exact", "strong",
                        t.get("canonicalName") or t["scientificName"], t.get("rank"), f"gbif:{t['key']}",
                        ",".join(r["match_languages"]),
                        {"status": t.get("taxonomicStatus"), "accepted": t.get("accepted")},
                        full=t.get("scientificName"), king=t.get("kingdom") or "Plantae")
        # Wikidata
        w = S["wikidata"]
        for nm in w["herbs"][hid]["names"]:
            for s in nm["searches"]:
                for r in s["results"]:
                    if not (r["exact_name_match"] and r["is_taxon"]):
                        continue
                    it = w["items"][r["qid"]]
                    add(hid, nm["name"], "wikidata", "wikidata", r["matched_text"], f"exact {r['matched_in']}",
                        "strong", it.get("taxon_name"), it.get("taxon_rank"), f"wikidata:{r['qid']}",
                        r.get("matched_language", ""), king=it.get("kingdom"))
        # iNaturalist
        n = S["inaturalist"]
        for nm in n["herbs"][hid]["names"]:
            for s in nm["searches"]:
                for r in s["results"]:
                    if not (r["exact_name_match"] or r["exact_name_locales"]):
                        continue
                    t = n["taxa"][str(r["id"])]
                    mtype = "exact" if r["exact_name_match"] else "exact other name"
                    add(hid, nm["name"], "inaturalist", "inaturalist", r["matched_term"] or s["spelling"],
                        mtype, "strong", t["name"], t.get("rank"), f"inat:{t['id']}",
                        ",".join(r["exact_name_locales"]), {"is_active": t.get("is_active")},
                        king=t.get("iconic_taxon_name") or "Plantae")   # searched within plants
        # ChecklistBank
        c = S["checklistbank"]
        for nm in c["herbs"][hid]["names"]:
            for s in nm["searches"]:
                for x in s["hits"]:
                    strong = x["exact_name_match"] or x["exact_part_match"]
                    tx = x.get("taxon") or {}
                    if not strong and not tx:
                        continue            # loose substring hit with no plant: source file only
                    k = str(x["datasetKey"])
                    fam, why = families.get(k, (f"private:{k}", "unknown checklist"))
                    meta = ck.get(k, {})
                    add(hid, nm["name"], "checklistbank", fam, x["name"],
                        ("exact" if x["exact_name_match"] else "exact part") if strong else "contains",
                        "strong" if strong else "weak", tx.get("scientificName"), tx.get("rank"),
                        f"clb:{k}:{x.get('taxonID')}", x.get("language", ""),
                        {"checklist": meta.get("alias") or meta.get("title"), "licence": meta.get("license"),
                         "resolved": bool(tx)},
                        full=" ".join(x for x in (tx.get("scientificName"), tx.get("authorship")) if x),
                        king=tx.get("kingdom"))
        # Dr. Duke's
        d = S["drduke"]
        for nm in d["herbs"][hid]["names"]:
            for s in nm["searches"]:
                for r in s["results"]:
                    p = d["plants"][r["plant"]]
                    strong = r["exact_name_match"] or r["exact_part_match"]
                    add(hid, nm["name"], "drduke", "drduke", r["matched_name"],
                        ("exact" if r["exact_name_match"] else "exact part") if strong else "contains",
                        "strong" if strong else "weak", p.get("taxon"), None, f"duke:{r['plant']}", "",
                        {"tables": r["tables"], "countries": r["countries"], "references": r["references"][:10]},
                        full=" ".join(x for x in (p.get("taxon"), p.get("taxauthor")) if x), king="Plantae")
        # TaxTree (NCBI)
        tt = S["taxtree"]
        for nm in tt["herbs"][hid]["names"]:
            for s in nm["searches"]:
                for r in s["results"]:
                    tid = r.get("tax_id")
                    if r.get("fuzzy"):
                        grade, mtype = "weak", "similar"
                    elif r.get("exact_name_match"):
                        grade, mtype = "strong", f"exact {r.get('name_class', '')}".strip()
                    else:
                        continue
                    info = tt["taxa"].get(str(tid), {})
                    sci = next((x["name_txt"] for x in (info.get("names") or []) if x.get("name_class") == "scientific name"),
                               None) or (info.get("lineage") or {}).get("tax_name")
                    if not sci and r.get("name_class") == "scientific name":
                        sci = r.get("name_txt")
                    rank = r.get("rank") or ("species" if sci and len(sci.split()) > 1 else None)
                    lineage = info.get("lineage") or {}
                    add(hid, nm["name"], "taxtree", "ncbi", r.get("name_txt"), mtype, grade, sci, rank,
                        f"ncbi:{tid}", "", {"family": lineage.get("family"),
                                            "similar_searched": s.get("similar_searched")},
                        king=lineage.get("kingdom") or lineage.get("domain"))

    # de-duplicate: the same record reached through several spellings
    seen, ev = set(), []
    for r in rows:
        k = (r["herb"], r["culpeper_name"], r["record"], r["grade"])
        if k not in seen:
            seen.add(k)
            ev.append(r)

    # Wikidata ID links: a record whose ID a Wikidata item lists under another name
    link = {}
    for qid, it in S["wikidata"]["items"].items():
        if not it.get("is_taxon"):
            continue
        node, _, _ = canonical(it.get("taxon_name"))
        for prop, pref in (("P846", "gbif:"), ("P3151", "inat:"), ("P685", "ncbi:")):
            for v in it.get("external_ids", {}).get(prop, []):
                link[pref + str(v)] = (node, qid, prop)
    for r in ev:
        hit = link.get(r["record"])
        if hit and r["node"] and hit[0] != r["node"]:
            r["cross_reference"] = {"source": "wikidata", "relation": "shared_external_identifier",
                                    "other_name": hit[0], "wikidata_item": hit[1], "property": hit[2]}

    # scientific-name groups (identical normalised names)
    groups = {}
    for r in ev:
        if not r["node"]:
            continue
        g = groups.setdefault(r["node"], {"name": r["node"], "level": r["level"], "ids": defaultdict(set),
                                          "original_forms": set(), "varieties": set(), "kingdoms": set(),
                                          "sources": set(), "herbs": set(), "cross_references": set()})
        g["ids"][r["record"].split(":")[0]].add(r["record"])
        if r["candidate_full"]:
            g["original_forms"].add(r["candidate_full"])
        if r["variety"]:
            g["varieties"].add(r["variety"])
        if r["kingdom"]:
            g["kingdoms"].add(r["kingdom"])
        g["sources"].add(r["source"])
        g["herbs"].add(r["herb"])
        if r.get("cross_reference"):
            g["cross_references"].add(r["cross_reference"]["other_name"])

    def kingdom_flag(ks):
        if not ks:
            return "unknown"
        if ks == {"Plantae"}:
            return "plant"
        return "mixed" if "Plantae" in ks else "non-plant"

    for g in groups.values():
        g["kingdom_flag"] = kingdom_flag(g["kingdoms"])
        if g["level"] == "species":
            genus = g["name"].split()[0]
            g["genus_group"] = genus if genus in groups else None

    # per herb x scientific-name group summary (strong rows only)
    by_herb = defaultdict(lambda: defaultdict(list))
    for r in ev:
        if r["node"]:
            by_herb[r["herb"]][r["node"]].append(r)
    cands = {}
    for h in herbs:
        out = []
        for node, rs in by_herb[h["id"]].items():
            strong = [r for r in rs if r["grade"] == "strong"]
            weak = [r for r in rs if r["grade"] == "weak"]
            out.append({
                "scientific_name": node, "level": groups[node]["level"],
                "kingdom_flag": groups[node]["kingdom_flag"],
                "culpeper_names": sorted({r["culpeper_name"] for r in strong}),
                "sources": sorted({r["source"] for r in strong}),
                "families": sorted({r["family"] for r in strong}),
                "match_types": dict(Counter(r["match_type"] for r in strong)),
                "strong_rows": len(strong), "weak_rows": len(weak),
                "weak_culpeper_names": sorted({r["culpeper_name"] for r in weak} - {r["culpeper_name"] for r in strong}),
                "cross_references": sorted(groups[node]["cross_references"]),
            })
        out.sort(key=lambda c: (-len(c["culpeper_names"]), -len(c["families"]), c["level"] != "species",
                                c["kingdom_flag"] == "non-plant", -c["weak_rows"], c["scientific_name"]))
        cands[h["id"]] = {"name": h["name"], "candidates": out}

    # outputs
    old = HERE / "plants.json"
    if old.exists():
        old.unlink()                       # renamed to scientific_name_candidates.json
    with open(HERE / "evidence.jsonl", "w", encoding="utf-8") as f:
        for r in ev:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    as_json = lambda g: {**g, "ids": {k: sorted(v) for k, v in g["ids"].items()},
                         **{k: sorted(g[k]) for k in ("original_forms", "varieties", "kingdoms",
                                                       "sources", "cross_references")},
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
    (HERE / "checklist_families.json").write_text(json.dumps(
        {k: {"family": f, "reason": why, "alias": ck[k].get("alias"), "title": ck[k].get("title")}
         for k, (f, why) in sorted(families.items(), key=lambda kv: kv[1][0])}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    # report
    strong = [r for r in ev if r["grade"] == "strong"]
    sp = lambda c: [x for x in c["candidates"] if x["level"] == "species" and x["culpeper_names"]
                    and x["kingdom_flag"] != "non-plant"]
    with_sp = [c for c in cands.values() if sp(c)]
    multi = [c for c in with_sp if len(sp(c)[0]["culpeper_names"]) >= 2]
    flags = Counter(g["kingdom_flag"] for g in groups.values())
    xref = sum(1 for r in ev if r.get("cross_reference"))
    print(f"\nAggregated {len(herbs)} herbs from {len(SOURCES)} sources\n")
    print(f"  {len(ev):>7} evidence rows ({len(strong)} strong, {len(ev) - len(strong)} weak)")
    print(f"  {len(groups):>7} scientific-name groups ({sum(g['level'] == 'species' for g in groups.values())} species): "
          f"{flags.get('plant', 0)} plant, {flags.get('non-plant', 0)} non-plant, "
          f"{flags.get('mixed', 0)} mixed, {flags.get('unknown', 0)} kingdom unknown")
    print(f"  {xref:>7} rows with a Wikidata cross-reference to a differently named group\n")
    print(f"  {len(with_sp):>4} herbs have at least one species candidate that is not a known non-plant")
    print(f"  {len(multi):>4} of them have a top species backed by 2+ of Culpeper's names")
    print(f"  {len(herbs) - len(with_sp):>4} herbs have no such candidate\n")
    fams = Counter(f for f, _ in families.values())
    print(f"  ChecklistBank: {len(families)} checklists in {len(fams)} families "
          f"(Catalogue of Life releases: {fams.get('col', 0)}, private: "
          f"{sum(v for k, v in fams.items() if k.startswith('private'))})")
    print("\nSaved to matching/culpeper/: evidence.jsonl, scientific_name_candidates.json,\n"
          "  scientific_name_queries.jsonl, candidates.json, checklist_families.json\n")

    if "--show" in sys.argv:
        want = sys.argv[sys.argv.index("--show") + 1].lower()
        for hid, c in cands.items():
            if want in (hid, c["name"].lower()):
                print(f"{c['name']}:")
                for x in c["candidates"][:12]:
                    print(f"  {x['scientific_name'][:28]:28} {x['level']:7} {x['kingdom_flag']:9} names={len(x['culpeper_names'])} "
                          f"families={len(x['families']):<2} sources={','.join(x['sources'])[:40]:40} "
                          f"weak={x['weak_rows']}  {', '.join(x['culpeper_names'])[:50]}")


if __name__ == "__main__":
    main()
