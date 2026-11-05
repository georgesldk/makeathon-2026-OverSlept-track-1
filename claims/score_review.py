"""Check 5: count the marks a person put in claims/<book>/review_sample.csv.

Usage:  python3 claims/score_review.py
Prints, per book, how many claims and MeSH terms the reviewer marked right (y) or wrong (n),
and writes the totals to claims/review_results.json (cited in claims/CLAIMS_METHOD.md).
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    out = {}
    for book in ("culpeper", "dioscorides"):
        p = HERE / book / "review_sample.csv"
        if not p.exists():
            continue
        rows = list(csv.DictReader(open(p, encoding="utf-8")))
        res = {}
        for col, label in (("claim_correct (y/n)", "claim"), ("mesh_correct (y/n)", "mesh")):
            marks = [r[col].strip().lower()[:1] for r in rows if r[col].strip()]
            y, n = marks.count("y"), marks.count("n")
            res[label] = {"right": y, "wrong": n, "unmarked": len(rows) - y - n}
        out[book] = res
        c, m = res["claim"], res["mesh"]
        rate = lambda d: f"{d['right']}/{d['right'] + d['wrong']}" if d["right"] + d["wrong"] else "-"
        print(f"{book}: claim right {rate(c)} · MeSH right {rate(m)} · unmarked {c['unmarked']}")
        for r in rows:
            if r["claim_correct (y/n)"].strip().lower().startswith("n") or r["mesh_correct (y/n)"].strip().lower().startswith("n"):
                print(f"  wrong: {r['claim_id']} {r['claim']} → {r['mesh']}  {r['note']}")
    (HERE / "review_results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("Saved to claims/review_results.json")


if __name__ == "__main__":
    main()
