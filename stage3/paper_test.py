"""Stage 3 paper test: our retrieval and our claim × study extraction, measured against the experts of
Lardos et al. 2024 (data file 7: the PubMed clinical studies they judged relevant, with indication,
medicinal use group and preparation, for the candidate plants of the Greek text).

  python3 stage3/paper_test.py --prepare      read data file 7 (offline)
  python3 stage3/paper_test.py --fetch        on your computer: PubMed IDs, abstracts, recall, use groups
  python3 stage3/paper_test.py --export-web   prompts to stage3/paper_test/web/ (same prompt as Stage 3)
  ... paste each batch into a NEW chat (Gemini 3.8 Flash, temp 0), reply into batch_NNN.answer.txt ...
  python3 stage3/paper_test.py --import-web "Gemini 3.8 Flash, web chat, temp 0"

Three measurements:
 1. Retrieval recall: for each plant, our plant-level clinical search (scientific name + WCVP synonyms +
    Dr. Duke's unique common names, clinical publication types). How many of the experts' studies does it
    find within our cap (200) and within 500? The experts also searched other species of the genus, so
    recall is reported separately for studies that name the plant itself.
 2. Use groups by code: the use groups our code gives a study from its MeSH headings, against the experts'.
 3. The extraction: each expert study is paired with (a) a claim for each use group the experts gave it
    (should be relevant) and (b) one use group they did not give it, chosen at random (should be "not
    relevant"). The prompt, the excerpt check and the rules are exactly those of Stage 3.
Data file 7 is not redistributed (description_sources/paper_test/data/, outside git).
Normalised: "NS" (not one of the 21 groups) is read as NC, neurological; "MN/ CV" as MN and CV.
"""
import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
OUT = HERE / "paper_test"
DATA7 = ROOT / "description_sources" / "paper_test" / "data" / "Data file 7 - Clinical trial data PubMed .xlsx"
SEED, BATCH, OUR_CAP, DEEP = 42, 32, 200, 500
DETAILS = {"AN": "male genital organ", "BS": "spleen, blood", "CV": "dropsy/oedema, internal haemorrhoids, heart and vessels",
           "DE": "skin disorders, injuries, wounds, bleeding wounds, animal bites, hair", "FV": "fever, intermittent fevers",
           "GI": "oesophagus, stomach, intestine", "GY": "female genital organ, menstruation", "ID": "infectious diseases, consumption",
           "LG": "liver, gall bladder", "MA": "pregnancy, birth, lactation", "MC": "mental conditions",
           "MN": "metabolic and nutritional disorders, appetite, diabetes", "MS": "gout, rheumatism, sciatica, spasm, fractures, strains, paralysis",
           "NC": "headache, migraine, neurological conditions", "OP": "eyes", "OC": "teeth, gums, mouth ulcers",
           "OT": "ears", "RE": "lungs, bronchi, cough", "RL": "head, nose, throat, tonsillitis", "UR": "kidney, bladder, urethra"}
FIX = {"NS": "NC"}


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def prepare() -> None:
    import openpyxl
    wb = openpyxl.load_workbook(DATA7)
    rows = []
    for name in wb.sheetnames:
        if not name.startswith("Batch") or "Hits" in name:
            continue
        for r in wb[name].iter_rows(min_row=2):
            v = [c.value for c in r]
            if len(v) < 8 or not v[1] or not v[4] or str(v[4]).strip() in ("N/A", "n/a"):
                continue
            groups = sorted({FIX.get(g, g) for g in re.split(r"[,;/]\s*", str(v[5] or "")) if g.strip()} - {"N/A", ""})
            link = next((c.hyperlink.target for c in r if c.hyperlink), None)
            pmid = re.search(r"/(\d{5,9})/?", link or "")
            rows.append({"row": f"{name}:{r[0].row}", "jc_name": v[1], "plant": v[2], "species": str(v[3]).strip(),
                         "indication": str(v[4]).strip(), "use_groups": [g.strip() for g in groups],
                         "preparation": v[6], "title": str(v[7] or "").strip(), "pmid": pmid.group(1) if pmid else None,
                         "pmid_from": "data file 7 link" if pmid else None})
    OUT.mkdir(exist_ok=True)
    with open(OUT / "expert_studies.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} expert-relevant study rows · {sum(1 for r in rows if r['pmid'])} with a PubMed link · "
          f"{len({r['species'] for r in rows})} plants → stage3/paper_test/expert_studies.jsonl")


def fetch() -> None:
    import gzip
    from retrieve import ncbi, parse_pubmed, mentions, pubmed_plant, CLINICAL_FILTER, wcvp_synonyms, bare, common_names, TEXTS
    from build_units import use_groups
    rows = load(OUT / "expert_studies.jsonl")
    for r in rows:                                      # PubMed ID by title when the sheet has no link
        if not r["pmid"] and len(r["title"]) > 20:
            # every word of the title as a [ti] term (a long title rarely matches as one quoted phrase);
            # accepted only when exactly one record matches
            words = [w for w in re.findall(r"[A-Za-z0-9]+", r["title"]) if len(w) > 2][:20]
            raw = ncbi("esearch", {"db": "pubmed", "term": " AND ".join(f"{w}[ti]" for w in words), "retmax": 2, "retmode": "json"})
            res = json.loads(raw)["esearchresult"] if raw else {}
            if len(res.get("idlist", [])) == 1:
                r["pmid"], r["pmid_from"] = res["idlist"][0], "title search"
    pmids = sorted({r["pmid"] for r in rows if r["pmid"]})
    recs = {}
    for b in range(0, len(pmids), 100):
        recs.update(parse_pubmed(ncbi("efetch", {"db": "pubmed", "id": ",".join(pmids[b:b + 100]), "rettype": "abstract", "retmode": "xml"})))
    mesh = json.load(gzip.open(ROOT / "reference_sources/mesh/mesh_index.json.gz", "rt", encoding="utf-8"))
    D, LK = mesh["descriptors"], mesh["lookup"]
    tree_name = {t: d["name"] for d in D.values() for t in d["trees"]}
    species = sorted({bare(r["species"]) for r in rows})
    syn = wcvp_synonyms(species)
    commons = common_names(species, [])
    TEXTS.mkdir(exist_ok=True)
    found = {}
    for sp in species:
        res = json.loads(ncbi("esearch", {"db": "pubmed", "term": f"{pubmed_plant(sp, syn.get(sp, []), commons.get(sp, []), LK, D)} AND {CLINICAL_FILTER}",
                                          "retmax": DEEP, "sort": "relevance", "retmode": "json"}))["esearchresult"]
        found[sp] = res.get("idlist", [])
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
    stats = Counter()
    for r in rows:
        sp = bare(r["species"])
        rec = recs.get(r["pmid"]) if r["pmid"] else None
        r["has_abstract"] = bool(rec and rec["abstract"])
        if rec:
            (TEXTS / f"pmid_{r['pmid']}.txt").write_text(f"{rec['title']}\n\n{rec['abstract']}".strip(), encoding="utf-8")
            r["names_the_plant"] = bool(mentions({"title": rec["title"], "abstract": rec["abstract"],
                                                   "mesh": " ; ".join(rec["mesh_headings"])}, [sp] + [bare(x) for x in syn.get(sp, [])], commons.get(sp, [])))
            ids = found.get(sp, [])
            r["rank_in_our_search"] = ids.index(r["pmid"]) + 1 if r["pmid"] in ids else None
            g = set()
            for m in rec["mesh_headings"]:
                for ui in LK.get(norm(m), []):
                    g |= set(use_groups(ui, D, tree_name)[0])
            r["code_use_groups"] = sorted(g)
            r["publication_types"] = rec["publication_types"]
    with open(OUT / "expert_studies.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # one study can be listed for several rows (plants); recall counts each plant × study once
    seen, res = set(), defaultdict(Counter)
    for r in rows:
        if not r.get("pmid") or (r["species"], r["pmid"]) in seen or "names_the_plant" not in r:
            continue
        seen.add((r["species"], r["pmid"]))
        k = "names the plant" if r["names_the_plant"] else "another species / plant not named"
        rk = r["rank_in_our_search"]
        res[k]["n"] += 1
        res[k]["cap"] += bool(rk and rk <= OUR_CAP)
        res[k]["deep"] += bool(rk)
    use = [r for r in rows if r.get("code_use_groups") is not None]
    ex = lambda gs: set(gs) - {"XY"}
    both = [r for r in use if ex(r["use_groups"]) and ex(r["code_use_groups"])]
    summary = {"rows": len(rows), "with_pmid": sum(1 for r in rows if r["pmid"]),
               "pmid_from_title_search": sum(1 for r in rows if r.get("pmid_from") == "title search"),
               "with_abstract": sum(1 for r in rows if r.get("has_abstract")),
               "recall": {k: dict(v) for k, v in res.items()},
               "use_groups_by_code": {"studies": len(use), "experts_gave_only_XY": sum(1 for r in use if not ex(r["use_groups"])),
                                      "code_found_none": sum(1 for r in use if not ex(r["code_use_groups"])),
                                      "comparable": len(both), "overlap": sum(1 for r in both if ex(r["use_groups"]) & ex(r["code_use_groups"]))}}
    (OUT / "fetch_results.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"{summary['rows']} rows · PubMed ID for {summary['with_pmid']} ({summary['pmid_from_title_search']} by title search) · "
          f"abstract for {summary['with_abstract']}")
    for k, v in res.items():
        print(f"Recall, studies that {k}: {v['cap']}/{v['n']} within our cap of {OUR_CAP} · {v['deep']}/{v['n']} within {DEEP}")
    u = summary["use_groups_by_code"]
    print(f"Use groups by code (MeSH): {u['comparable']} comparable studies, at least one group shared with the experts in "
          f"{u['overlap']} · experts gave only XY: {u['experts_gave_only_XY']} · code found no group: {u['code_found_none']}")
    print("Saved: stage3/paper_test/fetch_results.json, expert_studies.jsonl")


def test_pairs() -> list:
    from build_units import GROUPS
    rows = [r for r in load(OUT / "expert_studies.jsonl") if r.get("has_abstract") and r.get("pmid")]
    rnd, out, seen = random.Random(SEED), [], set()
    for r in rows:
        key = (r["species"], r["pmid"])
        if key in seen:
            continue
        seen.add(key)
        given = [g for g in r["use_groups"] if g in DETAILS]
        others = sorted(set(DETAILS) - set(r["use_groups"]))
        for g, expect in [(g, "relevant") for g in given] + [(rnd.choice(others), "not_relevant")]:
            claim = f"used for {GROUPS[g].lower()} ({DETAILS[g]})"
            unit = {"unit_id": f"paper:{r['pmid']}:{r['species']}:{g}", "book": "test", "entry_label": r["plant"],
                    "quote": f"[{r['plant']}] is {claim}", "translation": None, "claim_text": claim,
                    "taxon": {"accepted_name": r["species"]}, "plant_part": "unknown", "preparation": ["unknown"],
                    "route": ["unknown"], "identification": {"tier": "A"}}
            out.append((unit, {"study_id": f"pmid:{r['pmid']}", "source": "PubMed", "publication_date": "",
                               "publication_types": r.get("publication_types", [])},
                        (ROOT / "stage3" / "texts" / f"pmid_{r['pmid']}.txt").read_text(encoding="utf-8"), g, expect))
    return out


def export_web() -> None:
    from extract_assessments import PROMPT, block
    ps = test_pairs()
    folder = OUT / "web"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for b in range(0, len(ps), BATCH):
        name = f"batch_{b // BATCH + 1:03d}"
        grp = ps[b:b + BATCH]
        manifest[name] = {f"p{i:02d}": [u["unit_id"], s["study_id"], g, e] for i, (u, s, _, g, e) in enumerate(grp, 1)}
        (folder / f"{name}.txt").write_text(PROMPT.format(n=len(grp), blocks="\n\n".join(
            block(f"p{i:02d}", u, s, t) for i, (u, s, t, _, _) in enumerate(grp, 1))), encoding="utf-8")
        ans = folder / f"{name}.answer.txt"
        if not ans.exists():
            ans.write_text("", encoding="utf-8")
    (folder / "batches.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"{len(ps)} test pairs ({sum(1 for p in ps if p[4] == 'relevant')} expert use groups + "
          f"{sum(1 for p in ps if p[4] == 'not_relevant')} random controls) in {len(manifest)} prompts → stage3/paper_test/web/")


def import_web(label: str) -> None:
    from extract_assessments import parse, check_excerpts, ema_use, header
    from rules import assess
    ps = {(u["unit_id"], s["study_id"]): (u, header(s) + "\n" + t) for u, s, t, _, _ in test_pairs()}
    manifest = json.load(open(OUT / "web" / "batches.json", encoding="utf-8"))
    res = []
    for name, pids in manifest.items():
        raw = (OUT / "web" / f"{name}.answer.txt").read_text(encoding="utf-8")
        js = parse(raw) if raw.strip() else None
        if not js:
            continue
        got = {str(p.get("pid")): p for p in js.get("pairs", []) if isinstance(p, dict)}
        for pid, (uid, sid, g, expect) in pids.items():
            f = got.get(pid)
            if not f:
                continue
            u, text = ps[(uid, sid)]
            voided, bad, _ = check_excerpts(f, text)
            f["validation"] = {"fields_voided": voided}
            f["ema_use"] = ema_use(f)
            r = assess(f, "A")
            res.append({"unit_id": uid, "study_id": sid, "group": g, "expected": expect, "applicability": r["applicability"],
                        "badge": r["badge"], "relevance": f.get("relevance"), "voided": voided, "model_overall": (f.get("overall") or {}).get("value")})
    pos = [x for x in res if x["expected"] == "relevant"]
    neg = [x for x in res if x["expected"] == "not_relevant"]
    sens = sum(1 for x in pos if x["applicability"] not in ("not_relevant", "unassessable"))
    spec = sum(1 for x in neg if x["applicability"] == "not_relevant")
    out = {"model": label, "pairs": len(res),
           "expert_groups_kept_relevant": [sens, len(pos)], "random_controls_marked_not_relevant": [spec, len(neg)],
           "applicability_on_expert_groups": dict(Counter(x["applicability"] for x in pos)),
           "applicability_on_controls": dict(Counter(x["applicability"] for x in neg)), "results": res}
    (OUT / "test_results.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(res)} test pairs scored")
    if pos:
        print(f"Expert use groups judged relevant (not 'not relevant'/'unassessable'): {sens}/{len(pos)} ({sens / len(pos):.0%})")
    if neg:
        print(f"Random other use groups judged not relevant: {spec}/{len(neg)} ({spec / len(neg):.0%})")
    print("On expert groups: " + ", ".join(f"{k} {v}" for k, v in Counter(x["applicability"] for x in pos).most_common()))
    print("On controls: " + ", ".join(f"{k} {v}" for k, v in Counter(x["applicability"] for x in neg).most_common()))
    print("Saved: stage3/paper_test/test_results.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--export-web", action="store_true")
    ap.add_argument("--import-web", metavar="MODEL")
    a = ap.parse_args()
    if a.prepare:
        prepare()
    elif a.fetch:
        fetch()
    elif a.export_web:
        export_web()
    elif a.import_web:
        import_web(a.import_web)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
