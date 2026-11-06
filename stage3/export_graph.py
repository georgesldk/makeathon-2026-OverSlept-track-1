"""Stage 3, step 6: graph export. Adds the modern evidence to the Stage 1 graph without changing it.

  python3 stage3/export_graph.py --set shared      (default: pilot)

Writes the set's graph folder (stage3/graph/ for the pilot, stage3/graph/<set>/ otherwise); load it
together with claims/graph/ (the Claim and Species IDs are the same):
  nodes.csv           Study nodes (PubMed / Europe PMC article, registered trial, EMA monograph)
  edges.csv           Claim -ASSESSED_AGAINST-> Study  (badge, applicability, finding, lane, rule IDs,
                        mismatches, unknowns, tier, the model's own verdict, review status)
                      Species -SAFETY_SIGNAL-> Study   (harm reported in the abstract, with the excerpt)
  claim_evidence.csv  one row per claim: results per lane, kept apart (regulatory, human, preclinical,
                      traditional), Dr. Duke's folk use and compound activity, safety flags
"""
import argparse
from collections import defaultdict
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from rules import lane

from sets import paths, SETS

LANES = ("regulatory", "human", "preclinical", "traditional")


def url(sid: str, s: dict) -> str:
    kind, _, rest = sid.partition(":")
    if kind == "pmid":
        return f"https://pubmed.ncbi.nlm.nih.gov/{rest}/"
    if kind == "nct":
        return f"https://clinicaltrials.gov/study/{rest}"
    if kind == "ema":
        return (s.get("ema") or {}).get("page") or ""
    if kind == "epmc":
        src, _, i = rest.partition(":")
        return f"https://europepmc.org/article/{src}/{i}"
    return ""


def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="pilot", choices=SETS)
    name = ap.parse_args().set
    P = paths(name)
    A_DIR, OUT = P["assessments"], P["graph"]
    A = load(A_DIR / "assessments.jsonl")
    S = {s["study_id"]: s for s in load(P["studies"] / "studies.jsonl")}
    U = {u["unit_id"]: u for u in load(P["units"])}
    duke = defaultdict(list)
    if (A_DIR / "duke.jsonl").exists():
        for d in load(A_DIR / "duke.jsonl"):
            duke[d["claim_id"]].append(d)
    review_status, reviewed = "unreviewed", {}
    rf = HERE / "review" / "review_results.json"
    if name == "pilot" and rf.exists():
        r = json.load(open(rf, encoding="utf-8"))
        review_status = "provisional review" if r.get("status", "").startswith("PROVISIONAL") else "reviewed"
        reviewed = {p["assessment_id"]: p["human"] for p in r["pairs"]}

    used = sorted({a["study_id"] for a in A})
    nodes = [{"id": sid, "type": "Study", "source": S[sid].get("source", "PubMed"), "label": S[sid]["title"],
              "year": (S[sid]["publication_date"] or "")[:4],
              "publication_types": "; ".join(S[sid]["publication_types"]), "url": url(sid, S[sid])} for sid in used]

    edges = []
    for a in A:
        u = U[a["unit_id"]]
        h = reviewed.get(a["assessment_id"])
        edges.append({
            "from": a["claim_id"], "to": a["study_id"], "type": "ASSESSED_AGAINST",
            "species": f"taxon:{a['species']}", "tier": u["identification"]["tier"],
            "badge": a["badge"], "applicability": a["applicability"], "finding": a["finding"] or "",
            "lane": lane(a["evidence_type"]) if a["applicability"] not in ("not_relevant", "unassessable") else "", "evidence_type": a["evidence_type"],
            "rules": " ".join(a["rules_applied"]), "modifiers": "; ".join(a.get("modifiers", [])),
            "mismatches": "; ".join(a.get("mismatches", [])), "unknowns": "; ".join(a.get("unknowns", [])),
            "model_overall": a["model_view"]["value"], "flag_for_review": a["comparison"]["flag_for_review"],
            "review_status": review_status if h else "unreviewed",
            "review_applicability": h["applicability"] if h else "", "assessment_id": a["assessment_id"],
            "harm": "", "harm_excerpt": ""})
    seen = set()
    for a in A:
        key = (a["species"], a["study_id"])
        if a["safety"]["flag"] and key not in seen:
            seen.add(key)
            edges.append({k: "" for k in edges[0]} | {
                "from": f"taxon:{a['species']}", "to": a["study_id"], "type": "SAFETY_SIGNAL",
                "species": f"taxon:{a['species']}", "evidence_type": a["evidence_type"],
                "harm": f"{a['safety'].get('category') or 'harm'}: {a['safety']['what']}", "harm_excerpt": a["safety"]["excerpt"]})

    claims = []
    summaries = {c["claim_id"]: c for c in load(A_DIR / "claim_summaries.jsonl")}
    for cid in sorted({u["claim_id"] for u in U.values()}):
        sp = next(u["taxon"]["accepted_name"] for u in U.values() if u["claim_id"] == cid)
        c = summaries.get(cid) or {"claim_id": cid, "species": sp, "studies": 0, "lanes": {},
                                   "search": "no source found by our searches (not the same as not studied)"}
        lanes = c.get("lanes", {})
        dk = duke.get(c["claim_id"], [])
        folk = sorted({f"{r['activity']} ({r['country'] or 'n/a'}; {r['reference']})" for d in dk if d["ethnobotany"]
                       for r in d["ethnobotany"]["records"]})
        mech = sorted({f"{k} ({len(v)} compounds)" for d in dk if d["mechanism"] for k, v in d["mechanism"]["activities"].items()})
        claims.append({
            "claim_id": c["claim_id"], "species": f"taxon:{c['species']}", "studies_assessed": c["studies"],
            **{f"{l}_summary": lanes.get(l, {}).get("summary", "") for l in LANES},
            **{f"{l}_badges": " | ".join(r["badge"] for r in lanes.get(l, {}).get("results", [])) for l in LANES},
            "folk_use_duke": " | ".join(folk[:8]) + (" …" if len(folk) > 8 else ""),
            "compound_activity_duke": " | ".join(mech[:8]) + (" …" if len(mech) > 8 else ""),
            "nothing_assessable": c.get("search", ""),
            "safety_flags": " | ".join(f"{f.get('category') or 'harm'} ({f['study_id']}): {f['what']}" for f in c.get("safety_flags", [])),
            "note": ("Historical claim compared with modern sources found by our searches; folk use and compound "
                     "activity are not evidence of efficacy; not medical advice.")})

    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / "nodes.csv", nodes)
    write(OUT / "edges.csv", edges)
    write(OUT / "claim_evidence.csv", claims)
    n_safety = sum(e["type"] == "SAFETY_SIGNAL" for e in edges)
    print(f"{len(nodes)} Study nodes · {len(edges) - n_safety} ASSESSED_AGAINST + {n_safety} SAFETY_SIGNAL edges · "
          f"{len(claims)} claims summarised · review: {review_status}")
    print(f"Saved: {OUT.relative_to(ROOT)}/nodes.csv, edges.csv, claim_evidence.csv (load with claims/graph/)")


if __name__ == "__main__":
    main()
