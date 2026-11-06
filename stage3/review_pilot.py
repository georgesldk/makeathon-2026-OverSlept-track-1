"""Stage 3, step 5: human review of the claim × study pilot.

  python3 stage3/review_pilot.py --make     writes stage3/review/pilot_review.csv
  ... fill the four human_* columns (Numbers or Excel, save as CSV, same name) ...
  python3 stage3/review_pilot.py --score    compares the rules and the model with you

Sheet: every pair where the rules and the model's own overall view disagree, then 10 random pairs
where they agree (seed 42), so both kinds are checked. The reviewer decides from the claim and the
abstract; the machine results are in the sheet for reference but should be judged, not copied.
"""
import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from extract_assessments import code_view

SHEET = HERE / "review" / "pilot_review.csv"
RESULTS = HERE / "review" / "review_results.json"
STATUS = ("PROVISIONAL: done in haste on 5 Nov 2026; how the sheet was filled is not recorded. "
          "To be redone by a person reading each abstract before any result is reported. See stage3/review/README.md.")
AGREEING_SAMPLE, SEED = 10, 42
APPLICABILITY = ("direct", "partial", "indirect", "not_relevant", "unassessable")
FINDINGS = ("positive", "negative", "mixed", "inconclusive", "not_reported", "unclear")
HUMAN = ["human_applicability", "human_finding", "human_harm", "human_notes"]


def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def make() -> None:
    A = load(HERE / "assessments" / "v1" / "assessments.jsonl")
    S = {s["study_id"]: s for s in load(HERE / "studies" / "studies.jsonl")}
    U = {u["unit_id"]: u for u in load(HERE / "units" / "pilot.jsonl")}
    flagged = [a for a in A if a["comparison"]["flag_for_review"]]
    agreeing = [a for a in A if not a["comparison"]["flag_for_review"]]
    random.Random(SEED).shuffle(agreeing)
    rows = []
    for why, group in (("disagreement", flagged), ("random agreeing", agreeing[:AGREEING_SAMPLE])):
        for a in group:
            u, s, c = U[a["unit_id"]], S[a["study_id"]], a["compatibility"]
            rows.append({
                "n": len(rows) + 1, "why_in_sheet": why, "assessment_id": a["assessment_id"],
                "book": u["book"], "plant": a["species"], "tier": u["identification"]["tier"],
                "claim_quote": u["quote"], "claim_meaning": u["claim_text"],
                "claim_part_prep_route": f"{u['plant_part']} · {', '.join(u['preparation'])} · {', '.join(u['route'])}",
                "study": f"{s['title']} ({s['publication_date'][:4]})",
                "pubmed": f"https://pubmed.ncbi.nlm.nih.gov/{s['study_id'].split(':')[1]}/",
                "rules_badge": a["badge"], "rules_rules": " ".join(a["rules_applied"]),
                "model_fields": " · ".join(f"{k} {c[k]['value']}" for k in c) + f" · relevance {a['relevance']}",
                "model_overall": f"{a['model_view']['value']}: {a['model_view']['reason']}",
                "model_harm": f"{a['safety']['harm']}: {a['safety']['what'] or ''}",
                **{h: "" for h in HUMAN},
                "abstract": (ROOT / s["text"]["locator"]).read_text(encoding="utf-8"),
            })
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    if SHEET.exists() and any(r.get("human_applicability") for r in csv.DictReader(open(SHEET, encoding="utf-8"))):
        sys.exit(f"{SHEET.relative_to(ROOT)} already has reviews; not overwritten.")
    with open(SHEET, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} pairs ({len(flagged)} disagreements + {min(AGREEING_SAMPLE, len(agreeing))} random agreeing) "
          f"→ {SHEET.relative_to(ROOT)}")
    print("Fill: human_applicability (" + " / ".join(APPLICABILITY) + ")")
    print("      human_finding (" + " / ".join(FINDINGS) + ")")
    print("      human_harm (yes / no / not_reported) · human_notes (why, especially when you disagree)")


def score() -> None:
    A = {a["assessment_id"]: a for a in load(HERE / "assessments" / "v1" / "assessments.jsonl")}
    rows = [r for r in csv.DictReader(open(SHEET, encoding="utf-8-sig")) if r["human_applicability"].strip()]
    bad = [r["n"] for r in rows if r["human_applicability"].strip() not in APPLICABILITY
           or (r["human_finding"].strip() and r["human_finding"].strip() not in FINDINGS)]
    if bad:
        sys.exit(f"Rows with a value outside the lists: {bad}")
    res, tally = [], Counter()
    for r in rows:
        a = A[r["assessment_id"]]
        h_app, h_fin = r["human_applicability"].strip(), r["human_finding"].strip() or None
        if h_app in ("not_relevant", "unassessable"):
            h_fin = None
        human_view = code_view({"applicability": h_app, "finding": h_fin})
        rec = {"n": r["n"], "assessment_id": a["assessment_id"], "why_in_sheet": r["why_in_sheet"],
               "human": {"applicability": h_app, "finding": h_fin, "harm": r["human_harm"].strip(), "notes": r["human_notes"]},
               "rules": {"applicability": a["applicability"], "finding": a["finding"]},
               "agree": {"applicability": a["applicability"] == h_app,
                         "finding": a["finding"] == h_fin,
                         "rules_view": a["comparison"]["code_view"] == human_view,
                         "model_view": a["model_view"]["value"] == human_view,
                         "harm": (a["safety"]["harm"] == r["human_harm"].strip()) if r["human_harm"].strip() else None}}
        res.append(rec)
        for k, v in rec["agree"].items():
            if v is not None:
                tally[k, "n"] += 1
                tally[k, "ok"] += v
    n = len(res)
    print(f"{n} pairs reviewed · {STATUS}")
    labels = {"applicability": "Rules' applicability = yours", "finding": "Finding = yours",
              "rules_view": "Rules' verdict (supports/contradicts/...) = yours",
              "model_view": "Model's own verdict = yours", "harm": "Harm = yours"}
    for k, lab in labels.items():
        if tally[k, "n"]:
            print(f"  {lab}: {tally[k, 'ok']}/{tally[k, 'n']} ({tally[k, 'ok'] / tally[k, 'n']:.0%})")
    for why in ("disagreement", "random agreeing"):
        sub = [x for x in res if x["why_in_sheet"] == why]
        if sub:
            print(f"  {why}: rules right {sum(x['agree']['rules_view'] for x in sub)}/{len(sub)}, "
                  f"model right {sum(x['agree']['model_view'] for x in sub)}/{len(sub)}")
    wrong = Counter((x["rules"]["applicability"], x["human"]["applicability"]) for x in res if not x["agree"]["applicability"])
    if wrong:
        print("  Where the rules' applicability differs (rules → you): " +
              "; ".join(f"{a} → {b} ({v})" for (a, b), v in wrong.most_common()))
    RESULTS.write_text(json.dumps({"status": STATUS, "reviewed": n, "pairs": res}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {RESULTS.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--make", action="store_true")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    make() if a.make else score() if a.score else ap.print_help()


if __name__ == "__main__":
    main()
