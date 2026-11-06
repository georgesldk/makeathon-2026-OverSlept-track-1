"""Stage 3: Dr. Duke's Phytochemical and Ethnobotanical Databases (USDA, CC0) as two labelled lanes.
Code only, no model, no network.

  python3 stage3/duke.py --set shared

For each unit (claim × plant), by the plant's name (accepted name, bare):
  ethnobotany  Dr. Duke's ETHNOBOT records of this species for an activity matching the claim's concept:
               a recorded modern folk use, with its source and country. Traditional lane: not efficacy.
  mechanism    chemicals Dr. Duke's lists in this species (FARMACY_NEW) that have an activity matching the
               claim's concept (AGGREGAC). Plausibility only: a compound with an activity, at an unknown dose,
               says nothing about the remedy working.
Matching an activity to a concept: the MeSH heading or one of its synonyms, compared word by word after
removing plural and adjective endings, either equal ("Diuretic" = Diuretics) or, for a condition only,
with "anti" in front ("Antiulcer" = Ulcer; never for an action: "Antidiuretic" is not Diuretics).
"Antitussive" is not matched to Cough (different words), so some real matches are missed.
It is approximate and is reported as such.
Writes <set assessments>/duke.jsonl (one line per unit with any match).
"""
import argparse
import csv
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from sets import paths, SETS

DUKE = ROOT / "common_name_sources" / "drduke" / "data"
ENDINGS = ("ities", "ity", "ics", "ic", "ies", "ia", "es", "al", "s")
NOTE = {"ethnobotany": "recorded folk use (Dr. Duke's); not evidence of efficacy",
        "mechanism": "compound activity (Dr. Duke's); plausibility only, not evidence the remedy works"}


def stem(text: str) -> str:
    words = re.sub(r"[^a-z ]+", " ", text.lower().replace("-", "")).split()
    out = []
    for w in words:
        for e in ENDINGS:
            if w.endswith(e) and len(w) - len(e) >= 4:
                w = w[: -len(e)]
                break
        out.append(w)
    return " ".join(out)


def bare(name: str) -> str:
    return " ".join(name.split()[:2])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True, choices=SETS)
    a = ap.parse_args()
    P = paths(a.set)
    units = [json.loads(l) for l in open(P["units"], encoding="utf-8")]
    D = json.load(gzip.open(ROOT / "reference_sources/mesh/mesh_index.json.gz", "rt", encoding="utf-8"))["descriptors"]
    species = {bare(u["taxon"]["accepted_name"]) for u in units}
    enc = {"encoding": "latin-1"}
    fnf = {r["FNFNUM"]: bare(r["TAXON"]) for r in csv.DictReader(open(DUKE / "FNFTAX.csv", **enc))}
    ethno = defaultdict(list)
    for r in csv.DictReader(open(DUKE / "ETHNOBOT.csv", **enc)):
        sp = bare(r["TAXON"] or f"{r['GENUS']} {r['SPECIES']}")
        if sp in species:
            ethno[sp].append(r)
    chems = defaultdict(set)
    for r in csv.DictReader(open(DUKE / "FARMACY_NEW.csv", **enc)):
        if fnf.get(r["FNFNUM"]) in species:
            chems[fnf[r["FNFNUM"]]].add(r["CHEM"])
    acts = defaultdict(list)
    wanted = set().union(*chems.values()) if chems else set()
    for r in csv.DictReader(open(DUKE / "AGGREGAC.csv", **enc)):
        if r["CHEM"] in wanted:
            acts[r["CHEM"]].append(r)
    out_dir = P["assessments"]
    out_dir.mkdir(parents=True, exist_ok=True)
    n_e = n_m = 0
    with open(out_dir / "duke.jsonl", "w", encoding="utf-8") as f:
        for u in units:
            sp = bare(u["taxon"]["accepted_name"])
            uis = [c["ui"] for c in u["condition_concepts"] + u["action_concepts"] + u["other_concepts"]]
            def stems(concepts):
                return {stem(t) for c in concepts for t in [D[c["ui"]]["name"]] + D[c["ui"]]["terms"] if "," not in t}
            terms = stems(u["action_concepts"] + u["other_concepts"]) | stems(u["condition_concepts"])
            # "anti" + a condition: anti-ulcer acts against ulcers. Never for actions: Antidiuretic is the
            # opposite of Diuretic.
            terms |= {"anti" + t for t in stems(u["condition_concepts"])}

            def hit(activity):
                s = stem(activity)
                return s in terms or s.replace("anti ", "anti") in terms
            e_hits = [{"activity": r["ACTIVITY"], "country": r["COUNTRY"], "reference": r["REFERENCE"]}
                      for r in ethno.get(sp, []) if hit(r["ACTIVITY"])]
            m_hits = defaultdict(set)
            for c in chems.get(sp, ()):
                for r in acts.get(c, ()):
                    if hit(r["ACTIVITY"]):
                        m_hits[r["ACTIVITY"]].add(c)
            if not e_hits and not m_hits:
                continue
            n_e += bool(e_hits)
            n_m += bool(m_hits)
            f.write(json.dumps({
                "unit_id": u["unit_id"], "claim_id": u["claim_id"], "species": u["taxon"]["accepted_name"],
                "concepts": [D[ui]["name"] for ui in uis],
                "ethnobotany": {"records": e_hits, "note": NOTE["ethnobotany"]} if e_hits else None,
                "mechanism": {"activities": {k: sorted(v) for k, v in sorted(m_hits.items())},
                              "compounds": len(set().union(*m_hits.values())), "note": NOTE["mechanism"]} if m_hits else None,
                "source": "Dr. Duke's Phytochemical and Ethnobotanical Databases (USDA ARS), CC0"},
                ensure_ascii=False) + "\n")
    print(f"Set {a.set}: {len(units)} units · {len(species)} plants ({sum(1 for s in species if s in ethno)} with folk-use records, "
          f"{sum(1 for s in species if chems.get(s))} with compounds in Dr. Duke's)")
    print(f"Matches: folk use for {n_e} units · compound activity for {n_m} units → {(out_dir / 'duke.jsonl').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
