"""Link every extracted claim to its plant (Stage 2) and its MeSH concepts, and find the
claims the books share. No AI; run it after each import.

Usage:  python3 claims/link_claims.py
        python3 claims/link_claims.py --show "Artemisia absinthium"

Reads  claims/<book>/claims.json            (claims, from extract_claims.py)
       matching/<book>/eligibility.json     (the plants of each entry, tiers A / B / X)
Writes claims/links.json, and claims/graph/nodes.csv + edges.csv (ready for a graph database).

Edges:
  claim  -[ABOUT_PLANT {tier, rules, caveats}]->  species   A = the identification, B = possible
                                                            (with caveats); X species are never linked
  claim  -[HAS_CONCEPT {match}]->                 MeSH descriptor
  entry  -[HAS_CLAIM]->                           claim
A claim belongs to its entry, so it is linked to every A/B species of that entry (an entry can be
several plants: "Mallows and Marshmallows", a plant complex). Entries with no A/B species keep
their claims, unlinked to a plant.
Shared claims: the same species and the same MeSH concept in Culpeper and Dioscorides ("shared_claims",
the set Stage 3 was run on, unchanged by a third book); and the Shennong claims another book shares
("shennong_shared_claims").
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BOOKS = ["culpeper", "dioscorides", "shennong"]
PAIR = {"culpeper", "dioscorides"}          # "shared_claims" stays the Culpeper-Dioscorides set Stage 3 was run on


def load(p):
    return json.load(open(p, encoding="utf-8"))


def plants(book: str) -> dict:
    """entry key used by the claims -> [(species, tier, rules, caveats)]"""
    elig = load(ROOT / "matching" / book / "eligibility.json")["herbs"]
    out = {}
    for key, h in elig.items():
        k = h["label"] if book in ("dioscorides", "shennong") else key
        out[k] = [(r["accepted_name"], "A", r["rules"], []) for r in h["shown"]] + \
                 [(r["accepted_name"], "B", r["rules"], r["caveats"]) for r in h["possible"]]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", help="a species: print its claims across books")
    a = ap.parse_args()
    books = [b for b in BOOKS if (HERE / b / "claims.json").exists()]
    if not books:
        raise SystemExit("No claims yet: import some with claims/extract_claims.py first")
    nodes, edges = {}, []
    by_pair = defaultdict(list)            # (species, mesh ui) -> claims
    by_species = defaultdict(list)
    stats = {}
    for book in books:
        cl = load(HERE / book / "claims.json")["entries"]
        pl = plants(book)
        n_claims = n_linked = n_a = 0
        for key, e in cl.items():
            entry_id = f"{book}:{key}"
            nodes[entry_id] = {"type": "Entry", "label": e["name"], "book": book}
            sp = pl.get(key, [])
            for c in e["claims"]:
                n_claims += 1
                cid = c["claim_id"]
                nodes[cid] = {"type": "Claim", "label": c["claim"], "book": book, "quote": c["quote"],
                              "translation": c.get("translation"), "kind": c["kind"], "relation": c["relation"],
                              "part": c.get("part"), "preparation": c.get("preparation"), "route": c.get("route")}
                edges.append({"from": entry_id, "to": cid, "type": "HAS_CLAIM"})
                for m in c["mesh"]:
                    nodes[f"mesh:{m['ui']}"] = {"type": "MeSH", "label": m["name"]}
                    edges.append({"from": cid, "to": f"mesh:{m['ui']}", "type": "HAS_CONCEPT", "match": m["match"]})
                if sp:
                    n_linked += 1
                n_a += any(t == "A" for _, t, _, _ in sp)
                for name, tier, rules, caveats in sp:
                    nodes[f"taxon:{name}"] = {"type": "Species", "label": name}
                    edges.append({"from": cid, "to": f"taxon:{name}", "type": "ABOUT_PLANT", "tier": tier,
                                  "rules": " ".join(rules), "caveats": "; ".join(caveats)})
                    rec = {"claim_id": cid, "book": book, "entry": e["name"], "tier": tier, "claim": c["claim"],
                           "quote": c["quote"], "translation": c.get("translation")}
                    by_species[name].append({**rec, "mesh": [m["name"] for m in c["mesh"]]})
                    for m in c["mesh"]:
                        by_pair[(name, m["ui"], m["name"])].append(rec)
        stats[book] = {"claims": n_claims, "linked_to_a_plant": n_linked, "linked_to_an_A_plant": n_a}
    shared, shennong_shared = [], []
    for (sp, ui, mname), recs in by_pair.items():
        cd = [r for r in recs if r["book"] in PAIR]
        bks = sorted({r["book"] for r in cd})
        if len(bks) > 1:                      # unchanged definition: Culpeper and Dioscorides
            shared.append({"species": sp, "mesh_ui": ui, "mesh": mname, "books": bks,
                           "both_A": all(any(r["tier"] == "A" and r["book"] == b for r in cd) for b in bks),
                           "claims": cd})
        all_b = sorted({r["book"] for r in recs})
        if "shennong" in all_b and len(all_b) > 1:   # the Shennong claims another book shares
            shennong_shared.append({"species": sp, "mesh_ui": ui, "mesh": mname, "books": all_b,
                                    "A_in_every_book": all(any(r["tier"] == "A" and r["book"] == b for r in recs)
                                                           for b in all_b),
                                    "shennong_A": any(r["tier"] == "A" and r["book"] == "shennong" for r in recs),
                                    "claims": recs})
    shared.sort(key=lambda s: (not s["both_A"], s["species"], s["mesh"]))
    shennong_shared.sort(key=lambda s: (not s["shennong_A"], -len(s["books"]), s["species"], s["mesh"]))
    (HERE / "links.json").write_text(json.dumps({"books": books, "stats": stats, "shared_claims": shared,
                                                 "shennong_shared_claims": shennong_shared},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    g = HERE / "graph"
    g.mkdir(exist_ok=True)
    with open(g / "nodes.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["id", "type", "label", "book", "kind", "relation", "part", "preparation", "route", "quote", "translation"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for i, n in nodes.items():
            w.writerow({"id": i, **n})
    with open(g / "edges.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["from", "to", "type", "tier", "rules", "caveats", "match"], extrasaction="ignore")
        w.writeheader()
        w.writerows(edges)
    if a.show:
        want = a.show.lower()
        for sp, recs in by_species.items():
            if sp.lower().startswith(want):
                print(f"\n{sp}")
                for r in sorted(recs, key=lambda r: (r["book"], r["claim_id"])):
                    print(f"  [{r['book']}, {r['tier']}] {r['claim']}  · MeSH: {', '.join(r['mesh']) or '-'}")
                    print(f"      \"{r['quote']}\"" + (f"  ({r['translation']})" if r.get("translation") else ""))
        return
    for b, s in stats.items():
        print(f"{b}: {s['claims']} claims · {s['linked_to_a_plant']} linked to a plant "
              f"({s['linked_to_an_A_plant']} to an identification, tier A)")
    print(f"Shared claims (same species + same MeSH concept in culpeper and dioscorides): {len(shared)} "
          f"({sum(s['both_A'] for s in shared)} with tier A in every book)")
    print(f"Shennong claims shared with another book: {len(shennong_shared)} groups "
          f"({sum(len(s['books']) == 3 for s in shennong_shared)} in all three books, "
          f"{sum(s['shennong_A'] for s in shennong_shared)} with the Shennong plant tier A)")
    for s in shared[:15]:
        print(f"  {s['species']} · {s['mesh']} · {', '.join(s['books'])}{'' if s['both_A'] else ' (B)'}")
    print(f"Graph: {len(nodes):,} nodes, {len(edges):,} edges → claims/graph/nodes.csv, edges.csv · details: claims/links.json")


if __name__ == "__main__":
    main()
