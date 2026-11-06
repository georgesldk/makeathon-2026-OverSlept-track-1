"""Show one plant's Stage 3 results in the terminal: its claims, the modern evidence per lane, the
sources with their badges, Dr. Duke's records and the safety signals.

Usage:  python3 stage3/show.py "Plantago major"          # scientific name, or part of it
        python3 stage3/show.py plantain                  # or a book's name for it
        python3 stage3/show.py "Plantago major" --all    # also the sources judged not relevant
        python3 stage3/show.py "Ruta" --set pilot        # another set (default: shared)

Read-only: it reads what the pipeline wrote (units, assessments, claim summaries, studies, Dr. Duke's,
safety flags) and changes nothing. Historical claims, not medical advice.
"""
import json
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sets import paths

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SET = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else "shared"
if "--set" in sys.argv:
    ARGS.remove(SET)
ALL = "--all" in sys.argv
LANES = ("regulatory", "human", "preclinical", "traditional")
ORDER = {"direct": 0, "partial": 1, "indirect": 2, "unassessable": 3, "not_relevant": 4}


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []


def wrap(text, indent):
    return textwrap.fill(" ".join(str(text).split()), 100, initial_indent=indent, subsequent_indent=indent)


def main() -> None:
    if not ARGS:
        sys.exit(__doc__)
    q = ARGS[0].lower()
    P = paths(SET)
    units = load(P["units"])
    match = sorted({u["taxon"]["accepted_name"] for u in units
                    if q in u["taxon"]["accepted_name"].lower() or q in u["entry_label"].lower()})
    if not match:
        sys.exit(f"No plant matching {ARGS[0]!r} in set {SET}.")
    if len(match) > 1:
        print(f"{len(match)} plants match {ARGS[0]!r}; showing the first. Others: " + "; ".join(match[1:12]))
    sp = match[0]
    us = [u for u in units if u["taxon"]["accepted_name"] == sp]
    A = [a for a in load(P["assessments"] / "assessments.jsonl") if a["species"] == sp]
    S = {s["study_id"]: s for s in load(P["studies"] / "studies.jsonl")}
    summ = {c["claim_id"]: c for c in load(P["assessments"] / "claim_summaries.jsonl")}
    duke = {d["claim_id"]: d for d in load(P["assessments"] / "duke.jsonl") if d["species"] == sp}
    safety = next((s for s in load(P["assessments"] / "safety_flags.jsonl") if s["species"] == sp), None)

    print(f"\n{sp} · {us[0]['taxon'].get('family') or ''} · set {SET}")
    for book in ("culpeper", "dioscorides", "shennong"):
        names = sorted({(u["entry_label"], u["identification"]["tier"]) for u in us if u["book"] == book})
        if names:
            print(f"  {book.capitalize()}: " + ", ".join(f"{n} (tier {t})" for n, t in names))
    by_claim = defaultdict(list)
    for a in A:
        by_claim[a["claim_id"]].append(a)
    print(f"  {len({u['claim_id'] for u in us})} claims in this set · {len(by_claim)} with sources read · "
          f"{len(A)} claim × source pairs · {sum(a['applicability'] not in ('not_relevant', 'unassessable') for a in A)} usable")
    print("  Historical claims compared with modern sources found by our searches. Not medical advice.\n")

    def rank(cid):
        aa = by_claim.get(cid, [])
        return (min((ORDER.get(a["applicability"], 9) for a in aa), default=9), cid)
    for cid in sorted({u["claim_id"] for u in us}, key=rank):
        u = next(x for x in us if x["claim_id"] == cid)
        aa = sorted(by_claim.get(cid, []), key=lambda a: ORDER.get(a["applicability"], 9))
        shown = [a for a in aa if ALL or a["applicability"] not in ("not_relevant", "unassessable")]
        c = summ.get(cid, {})
        lanes = {l: v["summary"] for l, v in (c.get("lanes") or {}).items()}
        if not aa and not ALL:
            continue
        print(f"■ {cid} · {u['book']}")
        print(wrap(f"“{u['quote']}”" + (f"  ({u['translation']})" if u.get("translation") else ""), "  "))
        print(wrap(f"means: {u['claim_text']} · part: {u['plant_part']} · preparation: {', '.join(u['preparation'])} "
                   f"· route: {', '.join(u['route'])}", "  "))
        if lanes:
            for l in LANES:
                if l in lanes:
                    print(f"  {l:12} {lanes[l]}")
        elif aa:
            print(f"  no usable source: {len(aa)} read, none relevant (not the same as not studied)")
        else:
            print("  no source found by our searches (not the same as not studied)")
        for a in shown:
            s = S.get(a["study_id"], {})
            out = next((e["text"] for e in a.get("excerpts") or [] if e.get("field") == "outcome"), "")
            year = (s.get("publication_date") or "")[:4]
            print(wrap(f"· {a['badge']} — {s.get('title', '')} ({year}, {a['study_id']})", "    "))
            if out:
                print(wrap(f"“{out[:220]}{'…' if len(out) > 220 else ''}”", "        "))
        hidden = len(aa) - len(shown)
        if hidden:
            print(f"    + {hidden} source{'s' if hidden != 1 else ''} judged not relevant (--all to list them)")
        d = duke.get(cid)
        if d and d.get("ethnobotany"):
            recs = sorted({f"{r['activity']} ({r['country'] or 'n/a'})" for r in d["ethnobotany"]["records"]})
            print(wrap("Dr. Duke's folk use (not efficacy): " + ", ".join(recs[:8]), "    "))
        if d and d.get("mechanism"):
            print(wrap("Dr. Duke's compound activity (plausibility only): " + ", ".join(
                f"{k} ({len(v)} compounds)" for k, v in list(d["mechanism"]["activities"].items())[:6]), "    "))
        print()
    if safety:
        print("⚠ Safety signals (reported in the sources; not evidence for or against any claim)")
        for f in safety["flags"]:
            print(wrap(f"· {f.get('category') or 'harm'}: {f['what']} ({f['study_id']})", "  "))
    else:
        print("No harm reported in the sources read (not proof of safety).")


if __name__ == "__main__":
    main()
