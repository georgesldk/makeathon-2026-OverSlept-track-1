"""Look up every scientific name from the Culpeper aggregate in Kew's WCVP (offline).

Usage:  python3 scientific_name_sources/wcvp/source_wcvp.py         # plant, mixed, unknown names
        add --book dioscorides to run it for Dioscorides (default: culpeper)
        python3 scientific_name_sources/wcvp/source_wcvp.py --all   # also names flagged non-plant

Reads matching/<book>/scientific_name_queries.jsonl (written by aggregate.py) and the
WCVP download in scientific_name_sources/wcvp/data/ (wcvp_names.csv, wcvp_distribution.csv;
gitignored, see DATA_SOURCES.md). Writes scientific_name_sources/wcvp/<book>/wcvp.json.

WCVP (World Checklist of Vascular Plants) is Kew's list of every vascular plant name with
Kew's opinion of it. It covers vascular plants only: mosses, algae and fungi are not in it.
For each of our names it keeps every WCVP record spelled the same (ignoring case, spaces,
hyphens and the hybrid sign), with:
  status           Accepted, Synonym, Orthographic (spelling variant), Illegitimate, Invalid,
                   Misapplied, Unplaced, Artificial Hybrid, Local Biotype
  accepted name    the record that status points to (for synonyms and spelling variants)
  authors, year and place of publication, IPNI and POWO identifiers, family
Family-level names are checked against WCVP's family column (WCVP has no family records).
For every accepted name reached, its distribution (TDWG areas, native or introduced),
life form and climate are kept: material for the later historical checks (where could
Culpeper have met this plant?).

No ranking and no picking: all same-spelled records are kept.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BOOK = sys.argv[sys.argv.index("--book") + 1] if "--book" in sys.argv else "culpeper"
QUERIES = ROOT / "matching" / BOOK / "scientific_name_queries.jsonl"
DATA = HERE / "data"
OUT = HERE / BOOK / "wcvp.json"
KEEP = ["plant_name_id", "ipni_id", "powo_id", "taxon_rank", "taxon_status", "family", "taxon_name",
        "taxon_authors", "accepted_plant_name_id", "basionym_plant_name_id", "homotypic_synonym",
        "place_of_publication", "volume_and_page", "first_published", "nomenclatural_remarks",
        "geographic_area", "lifeform_description", "climate_description", "hybrid_formula", "reviewed"]

csv.field_size_limit(10 ** 8)


def squash(s: str | None) -> str:
    """Comparison form: "Atropa bella-donna" = "Atropa belladonna", "Mentha × piperita" = "Mentha piperita"."""
    return re.sub(r"[\s\-×.]|(?<=\s)x(?=\s)", "", (s or "").lower())


def rows(path: Path):
    with open(path, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f, delimiter="|", quoting=csv.QUOTE_NONE)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not (DATA / "wcvp_names.csv").exists():
        sys.exit(f"WCVP download not found in {DATA} (see DATA_SOURCES.md).")
    queries = [json.loads(l) for l in open(QUERIES, encoding="utf-8")]
    keep_all = "--all" in sys.argv
    skipped = [q for q in queries if q["kingdom_flag"] == "non-plant" and not keep_all]
    queries = [q for q in queries if keep_all or q["kingdom_flag"] != "non-plant"]
    wanted = defaultdict(list)
    for q in queries:
        wanted[squash(q["name"])].append(q["name"])
    families_wanted = {q["name"] for q in queries if q["level"] == "family"}
    print(f"\nLooking up {len(queries)} scientific names in WCVP "
          f"({len(skipped)} flagged non-plant skipped; --all to include them)\n")

    # pass 1: records spelled like our names; families seen
    hits, families = defaultdict(list), defaultdict(int)
    print("Step 1: reading wcvp_names.csv for our names ...")
    for r in rows(DATA / "wcvp_names.csv"):
        if r["family"] in families_wanted:
            families[r["family"]] += 1
        k = squash(r["taxon_name"])
        if k in wanted:
            rec = {f: (r.get(f) or None) for f in KEEP}
            for n in wanted[k]:
                hits[n].append(rec)
    acc_ids = {h["accepted_plant_name_id"] for hs in hits.values() for h in hs if h["accepted_plant_name_id"]}

    # pass 2: the accepted records those point to
    print(f"Step 2: reading the {len(acc_ids)} accepted names they point to ...")
    accepted = {}
    for r in rows(DATA / "wcvp_names.csv"):
        if r["plant_name_id"] in acc_ids:
            accepted[r["plant_name_id"]] = {f: (r.get(f) or None) for f in KEEP}

    # pass 3: where the accepted names grow
    print("Step 3: reading wcvp_distribution.csv for those accepted names ...")
    dist = defaultdict(list)
    for r in rows(DATA / "wcvp_distribution.csv"):
        if r["plant_name_id"] in accepted:
            dist[r["plant_name_id"]].append({
                "area_code": r["area_code_l3"], "area": r["area"], "region": r["region"],
                "continent": r["continent"], "introduced": r["introduced"] == "1",
                "extinct": r["extinct"] == "1", "doubtful": r["location_doubtful"] == "1"})
    for pid, a in accepted.items():
        a["distribution"] = dist.get(pid, [])

    out = {}
    for q in queries:
        recs = hits.get(q["name"], [])
        out[q["name"]] = {
            "query_id": q["query_id"], "level": q["level"], "kingdom_flag": q["kingdom_flag"],
            "original_forms": q["original_forms"], "herbs": q["herbs"],
            "records": [{**h, "accepted_name": (accepted.get(h["accepted_plant_name_id"] or "") or {}).get("taxon_name"),
                         "accepted_authors": (accepted.get(h["accepted_plant_name_id"] or "") or {}).get("taxon_authors")}
                        for h in recs],
            "family_in_wcvp": families.get(q["name"], 0) if q["level"] == "family" else None}

    OUT.write_text(json.dumps({
        "source": "WCVP: World Checklist of Vascular Plants (Royal Botanic Gardens, Kew), bulk download",
        "wcvp_version": "16 (extracted 2026-06-04)", "licence": "CC BY 3.0",
        "citation": "Govaerts R (ed.). 2026. WCVP: World Checklist of Vascular Plants. Facilitated by the "
                    "Royal Botanic Gardens, Kew. https://doi.org/10.34885/egs6-cp24",
        "retrieved": date.today().isoformat(), "names": out, "accepted": accepted},
        ensure_ascii=False, indent=1), encoding="utf-8")

    vals = list(out.values())
    found = [v for v in vals if v["records"]]
    fam = [v for v in vals if not v["records"] and v["family_in_wcvp"]]
    status = defaultdict(int)
    for v in found:
        for h in v["records"]:
            status[h["taxon_status"]] += 1
    print(f"\n{len(vals)} names looked up in WCVP (version 16)\n")
    print(f"  {len(found):>5} have at least one WCVP record spelled the same "
          f"({sum(len(v['records']) for v in found)} records)")
    print("        record statuses: " + ", ".join(f"{k} {n}" for k, n in sorted(status.items(), key=lambda kv: -kv[1])))
    print(f"  {len(fam):>5} are family names found in WCVP's family column")
    print(f"  {len(vals) - len(found) - len(fam):>5} not in WCVP (WCVP has vascular plants only)")
    print(f"  {len(accepted):>5} accepted names reached, "
          f"{sum(1 for a in accepted.values() if a['distribution'])} with a distribution")
    print(f"\nSaved to scientific_name_sources/wcvp/{BOOK}/{OUT.name} ({OUT.stat().st_size / 1e6:.1f} MB)\n")


if __name__ == "__main__":
    main()
