"""Tie every scientific-name candidate to an accepted name in WFO and in WCVP, compare the
two, and regroup each herb's candidates by accepted name.

Usage:  python3 matching/resolve_scientific.py                      # Culpeper
        python3 matching/resolve_scientific.py --book dioscorides   # Dioscorides
        python3 matching/resolve_scientific.py --show "Amara Dulcis"   # one herb

Reads  matching/<book>/candidates.json                       (aggregate.py)
       scientific_name_sources/wfo/<book>/wfo.json            (source_wfo.py)
       scientific_name_sources/wcvp/<book>/wcvp.json          (source_wcvp.py)
       scientific_name_sources/globalnames/<book>/globalnames.json  (optional)
       scientific_name_sources/ipni/<book>/ipni.json                (optional)
Writes matching/<book>/scientific_names_resolved.json  per scientific name: the accepted
                                                         name in WFO and in WCVP, the rule
                                                         that decided each, and whether they agree
       matching/<book>/herb_candidates_resolved.json   per herb: candidates grouped by
                                                         accepted name, evidence added together

Each backbone is resolved on its own, with the same rules (only its own statuses and plain
text; the first that applies decides):
  accepted         the name is accepted (WFO: WFO's single match; WCVP: one Accepted record)
  synonym          the name is a synonym / spelling variant of the accepted name it points to
  only accepted    several entries spelled the same, exactly one accepted (the others are
                   deprecated, unplaced, misapplied, illegitimate ...)
  author           several accepted entries spelled the same (homonyms): the one whose author
                   appears in the original form the sources gave
  synonyms agree   no accepted entry, but every same-spelled synonym points to one name
  close spelling   WFO only, species only: one accepted name 1-2 letters away; flagged
  family           a family name WCVP lists in its family column
Anything else stays unresolved with the reason. Nothing is dropped.

Global Names Verifier (third opinion, lower trust, only used when WFO and WCVP both fail):
  global names     every curated database that answers (Catalogue of Life, ITIS, GRIN,
                   Tropicos, ...) gives the same current name, and at least two do;
                   for a misspelt name (match type Fuzzy) this is the corrected name
Its view is recorded for every name (match type, current names by database).

IPNI (publication details only, decides nothing): for every accepted name, the IPNI
records spelled the same whose author matches the accepted name's author (all of them if
none does): IPNI ID, author, year, publication, nomenclatural status, type specimens.

Agreement (names compared without authors, ignoring case, spaces, hyphens, hybrid sign):
  agree / disagree / only WFO / only WCVP / only Global Names / neither.
Herb candidates are grouped by the WFO accepted name, or WCVP's when WFO has none (WFO is
the project's primary identifier); WCVP's opinion is kept on every group.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOK = sys.argv[sys.argv.index("--book") + 1] if "--book" in sys.argv else "culpeper"
HERE = ROOT / "matching" / BOOK
WFO = ROOT / "scientific_name_sources" / "wfo" / BOOK / "wfo.json"
WCVP = ROOT / "scientific_name_sources" / "wcvp" / BOOK / "wcvp.json"
GNV = ROOT / "scientific_name_sources" / "globalnames" / BOOK / "globalnames.json"
IPNI = ROOT / "scientific_name_sources" / "ipni" / BOOK / "ipni.json"


def squash(s: str | None) -> str:
    return re.sub(r"[\s\-×.]|(?<=\s)x(?=\s)", "", (s or "").lower())


def author_squash(s: str | None) -> str:
    return re.sub(r"[\s.]", "", (s or "").lower())


def author_in_forms(authors: str | None, forms: list[str]) -> bool:
    a = author_squash(authors)
    return bool(a) and any(a in author_squash(f) for f in forms)


def blank(name: str) -> dict:
    return {"accepted_id": None, "accepted_name": None, "accepted_name_without_authors": None,
            "family": None, "rank": None, "rule": None, "reason": None, "via": None}


# --- WFO --------------------------------------------------------------------------
def wfo_family(placement: str | None) -> str | None:
    return next((p for p in (placement or "").split("$")[0].split("/") if p.endswith("aceae")), None)


def wfo_target(x: dict):
    if x["role"] == "accepted":
        return x["wfo_id"], x["full_name"], x["name_without_authors"]
    if x["role"] == "synonym" and x.get("accepted_wfo_id"):
        return x["accepted_wfo_id"], x["accepted_name"], x.get("accepted_name_without_authors")
    return None


def resolve_wfo(name: str, v: dict | None) -> dict:
    out = blank(name)

    def done(x, rule):
        wid, full, bare = wfo_target(x)
        out.update(accepted_id=wid, accepted_name=full, accepted_name_without_authors=bare,
                   family=wfo_family(x["placement"]), rank=x["rank"], rule=rule,
                   via={"id": x["wfo_id"], "name": x["full_name"], "role": x["role"]})
        return out

    if v is None:
        out["reason"] = "not sent (flagged non-plant)"
        return out
    m = v["match"]
    if m:
        if wfo_target(m):
            return done(m, "accepted" if m["role"] == "accepted" else "synonym")
        out.update(reason=f"WFO's match is {m['role']}", via={"id": m["wfo_id"], "name": m["full_name"],
                                                                "role": m["role"]})
        return out
    same = [x for x in v["candidates"] if x["spelling"] == "same"]
    if same:
        acc = [x for x in same if x["role"] == "accepted"]
        if len(acc) == 1:
            return done(acc[0], "only accepted")
        if len(acc) > 1:
            hit = [x for x in acc if author_in_forms(x["authors"], v["original_forms"])]
            if len({x["wfo_id"] for x in hit}) == 1:
                return done(hit[0], "author")
            out["reason"] = "homonyms: " + "; ".join(x["full_name"] for x in acc)
            return out
        targets = {wfo_target(x)[0] for x in same if wfo_target(x)}
        if len(targets) == 1:
            return done(next(x for x in same if wfo_target(x)), "synonyms agree")
        out["reason"] = ("same-spelled synonyms point to different names" if targets
                         else "same-spelled entries are all unplaced or deprecated")
        return out
    close = [x for x in v["candidates"] if x["spelling"] == "close" and wfo_target(x)]
    if close and v["level"] == "species":
        if len({wfo_target(x)[0] for x in close}) == 1:
            return done(close[0], "close spelling")
        out["reason"] = "close spellings point to several names"
        return out
    out["reason"] = ("close spelling only, genus level or above (not used)"
                     if any(x["spelling"] == "close" for x in v["candidates"])
                     else "not in WFO")
    return out


# --- WCVP -------------------------------------------------------------------------
ACCEPTED = {"Accepted", "Artificial Hybrid"}
POINTS = {"Synonym", "Orthographic", "Illegitimate", "Invalid"}     # not Misapplied: a wrong use


def resolve_wcvp(name: str, v: dict | None, accepted: dict) -> dict:
    out = blank(name)

    def done(r, rule):
        a = accepted.get(r["accepted_plant_name_id"]) or r
        out.update(accepted_id=a["plant_name_id"],
                   accepted_name=" ".join(x for x in (a["taxon_name"], a["taxon_authors"]) if x),
                   accepted_name_without_authors=a["taxon_name"], family=a["family"],
                   rank=(a["taxon_rank"] or "").lower() or None, rule=rule,
                   via={"id": r["plant_name_id"], "name": " ".join(x for x in (r["taxon_name"], r["taxon_authors"]) if x),
                        "status": r["taxon_status"]})
        return out

    if v is None:
        out["reason"] = "not sent (flagged non-plant)"
        return out
    recs = v["records"]
    if not recs:
        if v.get("family_in_wcvp"):
            out.update(accepted_name=name, accepted_name_without_authors=name, family=name, rank="family",
                       rule="family")
            return out
        out["reason"] = "not in WCVP"
        return out
    acc = [r for r in recs if r["taxon_status"] in ACCEPTED and r["accepted_plant_name_id"] == r["plant_name_id"]]
    if len(acc) == 1:
        return done(acc[0], "accepted" if len(recs) == 1 else "only accepted")
    if len(acc) > 1:
        hit = [r for r in acc if author_in_forms(r["taxon_authors"], v["original_forms"])]
        if len(hit) == 1:
            return done(hit[0], "author")
        out["reason"] = "homonyms: " + "; ".join(f"{r['taxon_name']} {r['taxon_authors'] or ''}".strip() for r in acc)
        return out
    pts = [r for r in recs if r["taxon_status"] in POINTS and r["accepted_plant_name_id"]]
    targets = {r["accepted_plant_name_id"] for r in pts}
    if len(targets) == 1:
        return done(pts[0], "synonym" if len(recs) == 1 else "synonyms agree")
    statuses = sorted({r["taxon_status"] for r in recs})
    out["reason"] = ("same-spelled synonyms point to different names" if targets
                     else f"WCVP records are {', '.join(statuses)}")
    return out


# --- Global Names Verifier --------------------------------------------------------------
def resolve_gnv(name: str, v: dict | None) -> tuple[dict, dict | None]:
    out = blank(name)
    if v is None:
        out["reason"] = "not checked"
        return out, None
    cur = [r for r in v["results"] if r["curation"] == "Curated" and r["currentCanonicalSimple"]]
    by_db = {}
    for r in cur:
        by_db.setdefault(r["dataSourceTitleShort"], r["currentCanonicalSimple"])
    view = {"match_type": v["match_type"], "databases": len({r["dataSourceTitleShort"] for r in v["results"]}),
            "curated_current_names": by_db,
            "spelling_suggestion": sorted({r["matchedCanonicalSimple"] for r in v["results"]
                                           if r["matchType"] == "Fuzzy"}) or None}
    names = {squash(x) for x in by_db.values()}
    if v["match_type"] in ("Exact", "Fuzzy") and len(by_db) >= 2 and len(names) == 1:
        current = next(iter(by_db.values()))
        out.update(accepted_name=current, accepted_name_without_authors=current,
                   rank="species" if len(current.split()) == 2 else None,
                   rule="global names" + (" (corrected spelling)" if v["match_type"] == "Fuzzy" else ""))
        return out, view
    out["reason"] = (f"match type {v['match_type']}" if v["match_type"] not in ("Exact", "Fuzzy")
                     else "curated databases disagree" if len(names) > 1 else "fewer than two curated databases")
    return out, view


# --- IPNI -------------------------------------------------------------------------
def ipni_publication(accepted_full: str | None, bare: str | None, ipni: dict) -> list[dict]:
    """IPNI records of the accepted name; those whose author is in the accepted name first."""
    recs = [r for r in (ipni.get(bare or "") or {}).get("records", []) if r.get("exact_name_match")]
    if not recs:
        return []
    full = author_squash(accepted_full)
    by_author = [r for r in recs if author_squash(r.get("authorship")) and author_squash(r.get("authorship")) in full]
    keep = by_author or recs
    return [{"ipni_id": r.get("id"), "name": " ".join(x for x in (r.get("scientific_name"), r.get("authorship")) if x),
             "year": r.get("published_in_year"), "page": r.get("published_in_page"), "status": r.get("status"),
             "rank": r.get("rank"), "family": r.get("family_name"),
             "publication_issued": (r.get("reference") or {}).get("issued"),
             "publication_remarks": (r.get("reference") or {}).get("remarks"),
             "type_specimens": [{k: t.get(k) for k in ("status", "institution_code", "catalog_number", "collector")}
                                for t in r.get("type_materials") or []],
             "author_matches_accepted_name": bool(by_author)} for r in keep]


# --- run --------------------------------------------------------------------------
def main() -> None:
    cands = json.load(open(HERE / "candidates.json", encoding="utf-8"))
    wfo = json.load(open(WFO, encoding="utf-8"))
    wcvp = json.load(open(WCVP, encoding="utf-8"))
    gnv = json.load(open(GNV, encoding="utf-8"))["names"] if GNV.exists() else {}
    ipni = json.load(open(IPNI, encoding="utf-8"))["names"] if IPNI.exists() else {}
    all_names = sorted({c["scientific_name"] for h in cands.values() for c in h["candidates"]})

    resolved = {}
    for n in all_names:
        a = resolve_wfo(n, wfo["names"].get(n))
        b = resolve_wcvp(n, wcvp["names"].get(n), wcvp["accepted"])
        c, view = resolve_gnv(n, gnv.get(n))
        if a["rule"] and b["rule"]:
            same = squash(a["accepted_name_without_authors"]) == squash(b["accepted_name_without_authors"])
            agreement = "agree" if same else "disagree"
        else:
            agreement = ("only WFO" if a["rule"] else "only WCVP" if b["rule"]
                         else "only Global Names" if c["rule"] else "neither")
        main_ = a if a["rule"] else b if b["rule"] else c if c["rule"] else None
        resolved[n] = {"scientific_name": n, "wfo": a, "wcvp": b, "global_names": c,
                       "global_names_view": view, "agreement": agreement,
                       "ipni_publication": ipni_publication(main_["accepted_name"], main_["accepted_name_without_authors"],
                                                            ipni) if main_ else []}

    herbs = {}
    for hid, h in cands.items():
        groups = {}
        for c in h["candidates"]:
            c["culpeper_names"] = c.get("culpeper_names", c.get("book_names", []))
            r = resolved[c["scientific_name"]]
            main_ = (r["wfo"] if r["wfo"]["rule"] else r["wcvp"] if r["wcvp"]["rule"]
                     else r["global_names"] if r["global_names"]["rule"] else None)
            key = squash(main_["accepted_name_without_authors"]) if main_ else f"unresolved:{c['scientific_name']}"
            g = groups.setdefault(key, {
                "accepted_name": main_["accepted_name"] if main_ else None,
                "accepted_name_without_authors": main_["accepted_name_without_authors"] if main_ else None,
                "decided_by": ({id(r["wfo"]): "WFO", id(r["wcvp"]): "WCVP",
                                id(r["global_names"]): "Global Names"}[id(main_)]) if main_ else None,
                "wfo_id": r["wfo"]["accepted_id"], "wcvp_id": r["wcvp"]["accepted_id"],
                "family": (main_ or {}).get("family"), "rank": (main_ or {}).get("rank"),
                "resolved": bool(main_), "ipni_publication": r["ipni_publication"],
                "agreements": Counter(), "wcvp_opinions": set(),
                "unresolved_reason": None if main_ else (f"WFO: {r['wfo']['reason']}; WCVP: {r['wcvp']['reason']}; "
                                                         f"Global Names: {r['global_names']['reason']}"),
                "scientific_names": [], "culpeper_names": set(), "sources": set(), "source_families": set(),
                "strong_rows": 0, "weak_rows": 0, "kingdom_flags": set()})
            g["wfo_id"] = g["wfo_id"] or r["wfo"]["accepted_id"]
            g["wcvp_id"] = g["wcvp_id"] or r["wcvp"]["accepted_id"]
            g["agreements"][r["agreement"]] += 1
            if r["wcvp"]["accepted_name"]:
                g["wcvp_opinions"].add(r["wcvp"]["accepted_name"])
            g["scientific_names"].append({"name": c["scientific_name"], "level": c["level"],
                                          "wfo_rule": r["wfo"]["rule"], "wcvp_rule": r["wcvp"]["rule"],
                                          "agreement": r["agreement"], "culpeper_names": c["culpeper_names"],
                                          "strong_rows": c["strong_rows"]})
            g["culpeper_names"] |= set(c["culpeper_names"])
            g["sources"] |= set(c["sources"])
            g["source_families"] |= set(c["families"])
            g["strong_rows"] += c["strong_rows"]
            g["weak_rows"] += c["weak_rows"]
            g["kingdom_flags"].add(c["kingdom_flag"])
        out = []
        for g in groups.values():
            for k in ("culpeper_names", "sources", "source_families", "kingdom_flags", "wcvp_opinions"):
                g[k] = sorted(g[k])
            g["agreements"] = dict(g["agreements"])
            out.append(g)
        # strong evidence first (for Dioscorides: a lexicon naming this very chapter), then
        # how many of the book's names and how many independent sources back the candidate
        out.sort(key=lambda g: (not g["resolved"], g["strong_rows"] == 0, -len(g["culpeper_names"]), -len(g["source_families"]),
                                -g["strong_rows"], g["accepted_name"] or g["scientific_names"][0]["name"]))
        herbs[hid] = {"name": h["name"], "label": h.get("label"), "candidates": out}

    meta = {"wfo_release": wfo.get("wfo_release"), "wcvp_version": wcvp.get("wcvp_version")}
    (HERE / "scientific_names_resolved.json").write_text(json.dumps({**meta, "names": resolved},
                                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "herb_candidates_resolved.json").write_text(json.dumps({**meta, "herbs": herbs},
                                                                   ensure_ascii=False, indent=1), encoding="utf-8")

    # report
    sent = [r for r in resolved.values() if r["wfo"]["reason"] != "not sent (flagged non-plant)"]
    print(f"\n{len(all_names)} scientific names; {len(sent)} looked up "
          f"(WFO {meta['wfo_release']}, WCVP {meta['wcvp_version']})\n")
    for label in ("wfo", "wcvp"):
        rules = Counter(r[label]["rule"] for r in sent if r[label]["rule"])
        why = Counter(re.sub(r":.*", "", r[label]["reason"]) for r in sent if not r[label]["rule"])
        print(f"  {label.upper()}: {sum(rules.values())} tied to an accepted name  ("
              + ", ".join(f"{k} {n}" for k, n in rules.most_common()) + ")")
        print("        not: " + ", ".join(f"{k} {n}" for k, n in why.most_common()))
    agree = Counter(r["agreement"] for r in sent)
    print("\n  WFO vs WCVP: " + ", ".join(f"{k} {agree.get(k, 0)}" for k in
                                         ("agree", "disagree", "only WFO", "only WCVP",
                                          "only Global Names", "neither")))
    gn = Counter(r["global_names"]["rule"] for r in sent if r["agreement"] == "only Global Names")
    if gn:
        print("        settled by Global Names only: " + ", ".join(f"{k} {n}" for k, n in gn.items()))

    sp = lambda g: g["resolved"] and g["rank"] == "species" and g["culpeper_names"]
    with_sp = [h for h in herbs.values() if any(sp(g) for g in h["candidates"])]
    multi = [h for h in with_sp if len(next(g for g in h["candidates"] if sp(g))["culpeper_names"]) >= 2]
    top_agree = [h for h in with_sp if next(g for g in h["candidates"] if sp(g))["agreements"].get("agree")]
    unit = "herbs" if BOOK == "culpeper" else "chapters"
    backed = "strong evidence" if BOOK == "culpeper" else "strong or medium evidence"
    print(f"\n  {len(with_sp)} of {len(herbs)} {unit} have an accepted species backed by {backed}")
    if BOOK != "culpeper":
        top_strong = [h for h in with_sp if next(g for g in h["candidates"] if sp(g))["strong_rows"]]
        print(f"  {len(top_strong)} of them: the top one is identified for this very chapter (strong)")
    print(f"  {len(multi)} of them: the top one is backed by 2+ of the book's names")
    print(f"  {len(top_agree)} of them: WFO and WCVP agree on the top one")
    top_ipni = [next(g for g in h["candidates"] if sp(g)) for h in with_sp]
    top_ipni = [g for g in top_ipni if any(x["author_matches_accepted_name"] for x in g["ipni_publication"])]
    years = [next(x["year"] for x in g["ipni_publication"] if x["author_matches_accepted_name"]) for g in top_ipni]
    years = [y for y in years if isinstance(y, int)]
    if ipni:
        print(f"  {len(top_ipni)} of them: IPNI has the top one's original publication"
              + (f" ({sum(y <= 1753 for y in years)} published by 1753, the start of botanical names)" if years else ""))
    print()
    print(f"Saved to matching/{BOOK}/: scientific_names_resolved.json, herb_candidates_resolved.json\n")

    if "--show" in sys.argv:
        want = sys.argv[sys.argv.index("--show") + 1].lower()
        for hid, h in herbs.items():
            if want in (hid, (h["name"] or "").lower(), (h.get("label") or "").lower()):
                print(f"{h['name']}:")
                for g in h["candidates"][:12]:
                    label = g["accepted_name"] or f"[unresolved] {g['scientific_names'][0]['name']}"
                    pub = next((x for x in g["ipni_publication"] if x["author_matches_accepted_name"]), None)
                    print(f"  {label[:52]:52} {(g['family'] or ''):15} names={len(g['culpeper_names'])} "
                          f"sources={len(g['source_families']):<2} {','.join(f'{k} {n}' for k, n in g['agreements'].items()):14}"
                          + (f" IPNI {pub['year']}" if pub else ""))


if __name__ == "__main__":
    main()
