"""Eligibility: which candidates the end user sees (matching/ELIGIBILITY_RULES.md, in code).

Usage:  python3 matching/eligibility.py --book culpeper
        python3 matching/eligibility.py --book dioscorides
        python3 matching/eligibility.py --book culpeper --show "Devil's-Bit"

Reads what the pipeline already made (nothing is recomputed, nothing upstream changes):
  matching/<book>/herb_candidates_resolved.json   accepted names, WFO/WCVP agreement, kingdom, rank
  matching/<book>/evidence.jsonl                  every name match, its grade and its source
  matching/<book>/geography.json                  does it grow in the author's world
  description_sources/check/<book>/description_check.json   the description check (D), if present
Every candidate gets a tier and the rule IDs that put it there:
  A  shown as the identification      B  shown with caveats (rule IDs)      X  never shown (reason)
Output: matching/<book>/eligibility.json
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MIN_LINEAGES = 2                                   # A4a, the one setting (ELIGIBILITY_RULES.md)
EUROPE = {"Northern Europe", "Middle Europe", "Southwestern Europe", "Southeastern Europe", "Eastern Europe"}
POINTS = {"good": 2, "partial": 1, "no": -2, "absent": 0}


# ---------- L1: lineages ----------
def lineage(book: str, e: dict):
    """The lineage a piece of evidence belongs to (sources that copy each other count once)."""
    if book == "culpeper":
        f = e.get("family") or e.get("source")
        if f in ("gbif", "col"):
            return "GBIF + Catalogue of Life"
        if f.startswith("private"):
            return "private checklists"
        return {"wikidata": "Wikidata", "inaturalist": "iNaturalist", "ncbi": "NCBI", "drduke": "Dr. Duke's"}.get(
            f, f.replace("checklist:", "ChecklistBank project "))
    b = e.get("bridge", "")
    if b.startswith("lexicon"):
        return (e.get("detail") or {}).get("lexicon") or "LSJ"
    if b.startswith("wikidata"):
        return "Wikidata"
    return None                                    # same-word genus: a spelling coincidence, no lineage


def evidence(book: str) -> dict:
    """(entry, candidate name) -> rows with grade, lineage, passage-specific flag, layer."""
    out = defaultdict(list)
    for line in open(HERE / book / "evidence.jsonl", encoding="utf-8"):
        e = json.loads(line)
        entry = e.get("herb") or e.get("chapter")
        # keyed by the grouped name ("node"), the name candidates are grouped and looked up by; the raw
        # "candidate" ("Equisetum ramosissimum ramosissimum") would never be found (bug 3, Marselo's audit)
        out[(entry, e.get("node") or e.get("candidate"))].append({
            "grade": e.get("grade"), "lineage": lineage(book, e),
            "passage": e.get("bridge") == "lexicon_this_chapter",
            "layer": e.get("layer"), "book_name": e.get("culpeper_name") or e.get("book_name")})
    return out


# ---------- G: geography ----------
def geography(book: str, g: dict):
    """'fits', 'introduced' (B3), 'unknown' (B3), 'far' / 'impossible' (X2), or None."""
    if not g:
        return None
    lab = g["geography"]
    if lab.startswith("not checked"):
        return None
    if lab.startswith("impossible"):
        return "impossible"
    if lab.startswith("far"):
        return "far"
    if lab.startswith("no distribution"):
        return "unknown"
    if book == "culpeper":
        if lab.startswith("local (native") or lab == "european":
            return "fits"
        if lab.startswith("local (introduced"):           # fits if native somewhere in Europe (G1 wider world)
            return "fits" if EUROPE & set(g.get("native_regions") or []) else "introduced"
    else:
        if lab in ("local", "trade"):
            return "fits"
        if lab.startswith("introduced"):
            return "introduced"
    return "unknown"


# ---------- D: description check ----------
def description(entry: dict, accepted: str):
    """'fits', 'fits, Wikipedia only', 'poor' (explicit mismatch), 'weak', 'not assessable', None (not checked)."""
    if not entry:
        return None, None
    c = next((c for c in entry["candidates"] if c["accepted_name"] == accepted), None)
    if not c:
        return None, None
    details = entry["details"]
    if len({d["feature"] for d in details.values()}) < 3:
        return "not assessable", c["congruence"]          # D4: too few details, missing data is not weak
    if c["congruence"] >= 3:
        return ("fits, Wikipedia only" if c["wikipedia_only"] else "fits"), c["congruence"]
    groups = defaultdict(list)
    for s in c["scores"]:
        if s.get("id") in details and str(s.get("label")).lower() in POINTS:
            groups[details[s["id"]]["feature"]].append(POINTS[str(s["label"]).lower()])
    if not any(groups.values()):                          # no usable scores: never compared, not "poor" (bug 6)
        return None, None
    negative = any(sum(v) / len(v) < 0 for v in groups.values() if v)
    return ("poor" if negative else "weak"), c["congruence"]


# ---------- the rules ----------
def judge(book: str, cand: dict, ev: list, geo, desc, described: bool) -> dict:
    strong = {r["lineage"] for r in ev if r["grade"] == "strong" and r["lineage"]}
    medium = {r["lineage"] for r in ev if r["grade"] in ("strong", "medium") and r["lineage"]}
    passage = any(r["passage"] for r in ev)
    flags = set(cand.get("kingdom_flags") or [])
    rank = cand.get("rank")
    x = []
    if not cand.get("resolved") or not cand.get("decided_by"):
        x.append("X3")
    # X4 (bug 4): an explicit "non-plant", or a kingdom not confirmed as plant ("unknown", "mixed") with no
    # plant list (WFO, WCVP) behind the name. Global Names alone also covers animals (the shrew, Sorex araneus)
    plant_list = cand.get("decided_by") in ("WFO", "WCVP")
    if ("non-plant" in flags and "plant" not in flags) or ("plant" not in flags and not plant_list):
        x.append("X4")
    if not rank:                                           # rank unknown: a one-word name is a genus or family
        bare = (cand.get("accepted_name_without_authors") or "").split()          # (bug 5)
        rank = ("family" if bare and bare[0].endswith("aceae") else "genus") if len(bare) == 1 else rank
    if rank in ("genus", "family", "order", "class", "phylum", "tribe"):
        x.append("X6")
    if geo in ("far", "impossible"):
        x.append("X2")
    if ev and all(r["layer"] == "text" for r in ev):
        x.append("X5")
    if not medium:
        x.append("X1")
    if x:
        return {"tier": "X", "rules": x}
    caveats = []
    a4a = len(strong) >= MIN_LINEAGES
    second = len(medium - {r["lineage"] for r in ev if r["passage"]}) >= 1
    a4b = passage and (second or desc[0] == "fits")       # Wikipedia alone cannot confirm (D7)
    if cand.get("decided_by") == "Global Names":
        caveats.append("B4")
    if "disagree" in (cand.get("agreements") or {}):
        caveats.append("B2")
    if geo in ("introduced", "unknown"):
        caveats.append("B3")
    if not (a4a or a4b):
        caveats.append("B5" if passage or medium <= {"LSJ", "Lewis & Short"} else "B1")
    if desc[0] in ("poor", "weak"):
        caveats.append("B6")                               # A6: where described, the description decides
    elif described and desc[0] is None:
        caveats.append("B7")                               # A6: described, but this candidate was never compared
    rules = ["A1", "A2", "A3", "A4a" if a4a else "A4b", "A5", "A6"] if not caveats else caveats
    return {"tier": "A" if not caveats else "B", "rules": rules}


CAVEATS = {"B1": "one source", "B2": "botanists disagree on the name", "B3": "may not have grown there in the author's time",
           "B4": "name not in the main plant lists", "B5": "identified by a dictionary only",
           "B6": "the book's description fits poorly",
           "B7": "not compared with the book's description"}
REASONS = {"X1": "weak evidence only", "X2": "grows far from the author's world", "X3": "no accepted name",
           "X4": "not a plant", "X5": "only a word in the text, not a name of this entry", "X6": "genus or family only"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="culpeper", choices=["culpeper", "dioscorides"])
    ap.add_argument("--show", help="print one herb or chapter")
    a = ap.parse_args()
    book = a.book
    resolved = json.load(open(HERE / book / "herb_candidates_resolved.json", encoding="utf-8"))["herbs"]
    geo = json.load(open(HERE / book / "geography.json", encoding="utf-8"))["herbs"]
    dpath = ROOT / "description_sources/check" / book / "description_check.json"
    dcheck = json.load(open(dpath, encoding="utf-8"))["herbs"] if dpath.exists() else {}
    ev = evidence(book)
    out = {}
    for key, h in resolved.items():
        geo_by_name = {c["accepted_name"]: c for c in (geo.get(key) or {}).get("candidates", [])}
        dentry = dcheck.get(h.get("label") or h["name"])
        described = bool(dentry) and len({d["feature"] for d in dentry["details"].values()}) >= 3
        rows = []
        for c in h["candidates"]:
            names = {s["name"] for s in c.get("scientific_names", [])} or {c.get("accepted_name_without_authors")}
            e = [r for n in names for r in ev.get((key, n), [])]
            g = geography(book, geo_by_name.get(c.get("accepted_name")))
            d = description(dentry, c.get("accepted_name"))
            j = judge(book, c, e, g, d, described)
            rows.append({"accepted_name": c.get("accepted_name") or "(unresolved: " + ", ".join(sorted(names)) + ")",
                         "family": c.get("family"), "rank": c.get("rank"), **j,
                         # WFO and WCVP disagree (B2): show WCVP's name too, not only one (bug 7)
                         "other_accepted_names": sorted({o for o in (c.get("wcvp_opinions") or [])
                                                         if o and o != c.get("accepted_name")}),
                         "caveats": [CAVEATS[r] for r in j["rules"] if r in CAVEATS],
                         "reasons": [REASONS[r] for r in j["rules"] if r in REASONS],
                         "lineages_strong": sorted({r["lineage"] for r in e if r["grade"] == "strong" and r["lineage"]}),
                         "lineages_medium": sorted({r["lineage"] for r in e if r["grade"] == "medium" and r["lineage"]}),
                         "passage_specific": any(r["passage"] for r in e),
                         "geography": (geo_by_name.get(c.get("accepted_name")) or {}).get("geography"),
                         "description": d[0], "description_congruence": d[1]})
        order = lambda r: (-len(r["lineages_strong"]), -(r["description_congruence"] or -99))
        shown = sorted([r for r in rows if r["tier"] == "A"], key=order)
        genera = defaultdict(list)                          # P1: several A candidates of one genus = a plant complex
        for r in shown:
            genera[r["accepted_name"].split()[0]].append(r)
        for r in shown:
            if len(genera[r["accepted_name"].split()[0]]) > 1:
                r["plant_complex"] = r["accepted_name"].split()[0]
        out[key] = {"name": h["name"], "label": h.get("label"),
                    "shown": shown, "possible": sorted([r for r in rows if r["tier"] == "B"], key=order),
                    "hidden": [r for r in rows if r["tier"] == "X"]}
    (HERE / book / "eligibility.json").write_text(json.dumps(
        {"book": book, "rules": "matching/ELIGIBILITY_RULES.md", "min_lineages": MIN_LINEAGES,
         "description_check": str(dpath.relative_to(ROOT)) if dcheck else None, "herbs": out},
        ensure_ascii=False, indent=1), encoding="utf-8")
    if a.show:
        want = a.show.lower().replace("’", "'")
        for k, v in out.items():
            if want in (v["name"].lower().replace("’", "'"), (v["label"] or "").lower(), k):
                print(f"\n{v['name']} {v['label'] or ''}")
                for part, title in (("shown", "SHOWN"), ("possible", "POSSIBLE (with caveat)")):
                    print(f"  {title}:" + ("" if v[part] else " none"))
                    for r in v[part]:
                        print(f"    {r['accepted_name']}  [{', '.join(r['rules'])}]  "
                              f"{'; '.join(r['caveats'])}  · lineages: {', '.join(r['lineages_strong'] + r['lineages_medium']) or '-'}"
                              f" · description: {r['description'] or 'not checked'}")
                print(f"  HIDDEN: {len(v['hidden'])} ({', '.join(sorted({x for r in v['hidden'] for x in r['rules']}))})")
        return
    n = len(out)
    with_a = sum(bool(v["shown"]) for v in out.values())
    only_b = sum(not v["shown"] and bool(v["possible"]) for v in out.values())
    none = n - with_a - only_b
    tiers = defaultdict(int)
    for v in out.values():
        for part in ("shown", "possible", "hidden"):
            for r in v[part]:
                for rule in (r["rules"] if part != "shown" else []):
                    tiers[rule] += 1
    print(f"{book}: {n} entries · {with_a} with an identification (A) · {only_b} with possible ones only (B) · "
          f"{none} with nothing shown")
    print("Caveats (B): " + ", ".join(f"{k} {tiers[k]} ({CAVEATS[k]})" for k in sorted(CAVEATS) if tiers[k]))
    print("Hidden (X):  " + ", ".join(f"{k} {tiers[k]}" for k in sorted(REASONS) if tiers[k]))
    print(f"Saved to matching/{book}/eligibility.json")


if __name__ == "__main__":
    main()
