"""Search Dr. Duke's Phytochemical and Ethnobotanical Databases for every name of every Culpeper herb.

Usage:  python3 common_name_sources/drduke/culpeper/source_drduke.py

Reads historical_texts/culpeper/herbs.json and the USDA tables in common_name_sources/drduke/data/, writes
common_name_sources/drduke/culpeper/drduke.json. No network: the data is a local download.

Source: Dr. Duke's Phytochemical and Ethnobotanical Databases, USDA
Agricultural Research Service, Ag Data Commons, doi:10.15482/USDA.ADC/1239279
(CC0). Two tables carry common names:
  COMMON_NAMES  common name -> plant (FNFNUM), the plant's scientific name in FNFTAX
  ETHNOBOT      ethnobotanical use records with a common name (CNAME), the
                plant's scientific name, the country and the literature reference

No ranking and no picking. Each spelling (same variants as every source) is
compared with every common name in both tables; every name that equals the
spelling, or one of whose comma/slash-separated parts does, or that contains
it, is kept and flagged:
  exact_name_match   the common name equals the spelling (ignoring case,
                     spaces, hyphens, apostrophes)
  exact_part_match   one part of a listed name does ("Bittersweet, Felonwort")
  contains_match     the spelling only occurs inside a longer name
"""
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
HERBS = ROOT / "historical_texts" / "culpeper" / "herbs.json"
DATA = HERE.parent / "data"
OUT = HERE / "drduke.json"
MIN_CONTAINS = 4   # a spelling shorter than this is matched exactly only ("Ash" would hit hundreds)

sys.path.insert(0, str(ROOT / "common_name_sources" / "gbif" / "culpeper"))
from source_gbif import spellings, key  # noqa: E402  (same spellings as every source)


def read(table: str) -> list[dict]:
    path = DATA / f"{table}.csv"
    if not path.exists():
        sys.exit(f"Missing {path}. Copy the Duke CSV tables into common_name_sources/drduke/data/ first.")
    with open(path, encoding="latin-1", newline="") as f:
        return list(csv.DictReader(f))


def parts(name: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,/;]| or ", name) if p.strip()]


def plant_record(t: dict) -> dict:
    keep = ["TAXON", "TAXAUTHOR", "GENUS", "SPECIES", "SUBSPECIES", "VARIETY", "FAMILY", "SPCMT"]
    return {k.lower(): t[k].strip() for k in keep if t.get(k, "").strip()}


def main() -> None:
    herbs = json.load(open(HERBS, encoding="utf-8"))["herbs"]
    fnftax = {r["FNFNUM"]: r for r in read("FNFTAX")}
    by_taxon = {r["TAXON"].strip().lower(): n for n, r in fnftax.items() if r.get("TAXON")}

    # Every common name in Duke, once, with the plant(s) it points to.
    names: dict[str, dict] = {}
    plants: dict[str, dict] = {}

    def plant_id(fnfnum: str | None, taxon: str) -> str:
        if fnfnum and fnfnum in fnftax:
            pid = f"fnf:{fnfnum}"
            plants.setdefault(pid, {"id": pid, **plant_record(fnftax[fnfnum])})
        else:
            pid = f"taxon:{taxon}"
            plants.setdefault(pid, {"id": pid, "taxon": taxon})
        return pid

    for r in read("COMMON_NAMES"):
        nm = r["CNNAM"].strip()
        if not nm:
            continue
        pid = plant_id(r["FNFNUM"], "")
        e = names.setdefault(nm, {"name": nm, "links": {}})
        e["links"].setdefault(pid, {"plant": pid, "tables": set(), "countries": set(), "references": set(), "records": 0})
        e["links"][pid]["tables"].add("COMMON_NAMES")

    for r in read("ETHNOBOT"):
        nm, taxon = r.get("CNAME", "").strip(), r.get("TAXON", "").strip()
        if not nm or not taxon:
            continue
        pid = plant_id(by_taxon.get(taxon.lower()), taxon)
        e = names.setdefault(nm, {"name": nm, "links": {}})
        link = e["links"].setdefault(pid, {"plant": pid, "tables": set(), "countries": set(), "references": set(), "records": 0})
        link["tables"].add("ETHNOBOT")
        link["records"] += 1
        if r.get("COUNTRY", "").strip():
            link["countries"].add(r["COUNTRY"].strip())
        if r.get("REFERENCE", "").strip():
            link["references"].add(r["REFERENCE"].strip())

    index = [(nm, key(nm), [key(p) for p in parts(nm)]) for nm in names]

    out, used_plants = {}, set()
    for h in herbs:
        hn = []
        for n in dict.fromkeys([h["name"], *h["other_names"]]):
            ss = []
            for q in spellings(n):
                kq, hits = key(q), []
                for nm, kn, kparts in index:
                    exact, part = kn == kq, kq in kparts
                    contains = not (exact or part) and len(kq) >= MIN_CONTAINS and kq in kn
                    if not (exact or part or contains):
                        continue
                    for link in names[nm]["links"].values():
                        used_plants.add(link["plant"])
                        hits.append({"plant": link["plant"], "matched_name": nm,
                                     "tables": sorted(link["tables"]), "records": link["records"],
                                     "countries": sorted(link["countries"]), "references": sorted(link["references"]),
                                     "exact_name_match": exact, "exact_part_match": part,
                                     "contains_match": contains})
                ss.append({"spelling": q, "results": hits})
            hn.append({"name": n, "searches": ss})
        out[h["id"]] = {"name": h["name"], "names": hn}

    OUT.write_text(json.dumps({
        "source": "Dr. Duke's Phytochemical and Ethnobotanical Databases (USDA ARS), "
                  "Ag Data Commons doi:10.15482/USDA.ADC/1239279, CC0; tables COMMON_NAMES, FNFTAX, ETHNOBOT",
        "retrieved": date.today().isoformat(),
        "plants": {p: plants[p] for p in sorted(used_plants)},
        "herbs": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    res = [r for o in out.values() for nm in o["names"] for s in nm["searches"] for r in s["results"]]
    good = lambda nm: any(r["exact_name_match"] or r["exact_part_match"] for s in nm["searches"] for r in s["results"])
    print(f"\nDr. Duke's: {len(names)} distinct common names in the tables, linked to {len(plants)} plants\n")
    print(f"{len(herbs)} herbs: {len(res)} hits kept "
          f"({sum(r['exact_name_match'] or r['exact_part_match'] for r in res)} exact, "
          f"{sum(r['contains_match'] for r in res)} contains-only)\n")
    print(f"  {sum(good(nm) for o in out.values() for nm in o['names']):>4} names have an exact hit")
    print(f"  {sum(any(good(nm) for nm in o['names']) for o in out.values()):>4} herbs have at least one such name")
    print(f"\nSaved to common_name_sources/drduke/culpeper/{OUT.name} ({OUT.stat().st_size / 1e6:.1f} MB)\n")


if __name__ == "__main__":
    main()
