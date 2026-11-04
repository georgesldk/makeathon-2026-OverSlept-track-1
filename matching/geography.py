"""Historical check 1, geography: does each candidate plant grow where the author lived?

Usage:  python3 matching/geography.py                      # Culpeper
        python3 matching/geography.py --book dioscorides   # Dioscorides
        python3 matching/geography.py --show "Amara Dulcis"   (or --show 4.75)

Reads  matching/<book>/herb_candidates_resolved.json   (resolve_scientific.py)
       scientific_name_sources/wcvp/<book>/wcvp.json    (source_wcvp.py: WCVP distributions)
Writes matching/<book>/geography.json

For every resolved species candidate, WCVP's distribution (TDWG botanical areas, native or
introduced) is compared with the author's world:
  Culpeper (England, 1650s)
    local      native or introduced in Great Britain or Ireland
    european   native elsewhere in Europe (garden plant or imported drug)
    far        native only outside Europe (an import, or the wrong plant)
  Dioscorides (eastern Mediterranean, 1st century)
    local      native in the Mediterranean and Near East (southern Europe, northern
               Africa, western Asia)
    trade      native in the lands his spices and drugs came from (Arabia, NE Africa,
               India, Caucasus, Central Asia, China, Indo-China, Malesia)
    introduced only introduced in those lands: possibly after his time
    impossible native only in the Americas, Australia or the Pacific: unknown to anyone
               in the Old World before 1492
  Both: "no distribution data" (WCVP has none) and "not checked" (genus or family level).

Nothing is removed or re-ordered: each candidate gets a geography label, and each herb or
chapter says which of its candidates is the first one that fits the author's world.
WCVP records where plants grow today; "introduced" carries no date.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOK = sys.argv[sys.argv.index("--book") + 1] if "--book" in sys.argv else "culpeper"
HERE = ROOT / "matching" / BOOK
WCVP = ROOT / "scientific_name_sources" / "wcvp" / BOOK / "wcvp.json"
OUT = HERE / "geography.json"

MED = {"Southeastern Europe", "Southwestern Europe", "Northern Africa", "Western Asia"}
TRADE = {"Arabian Peninsula", "Northeast Tropical Africa", "Indian Subcontinent", "Caucasus", "Central Asia",
         "China", "Indo-China", "Malesia"}
NEW_WORLD = {"NORTHERN AMERICA", "SOUTHERN AMERICA", "AUSTRALASIA", "PACIFIC", "ANTARCTIC"}
FITS = {"culpeper": ("local", "european"), "dioscorides": ("local", "trade")}


def squash(s: str | None) -> str:
    return re.sub(r"[\s\-×.]|(?<=\s)x(?=\s)", "", (s or "").lower())


def label(dist: list[dict]) -> tuple[str, list[str]]:
    native = [d for d in dist if not d["introduced"] and not d["doubtful"]]
    intro = [d for d in dist if d["introduced"]]
    where = sorted({d["region"] for d in native})
    if BOOK == "culpeper":
        if any(d["area_code"] in ("GRB", "IRE") for d in dist):
            how = "native" if any(d["area_code"] in ("GRB", "IRE") for d in native) else "introduced"
            return f"local ({how} in Britain/Ireland)", where
        if any(d["continent"] == "EUROPE" for d in native):
            return "european", where
        return "far", where
    if any(d["region"] in MED for d in native):
        return "local", where
    if any(d["region"] in TRADE for d in native):
        return "trade", where
    if any(d["region"] in MED | TRADE for d in intro):
        return "introduced only", where
    if native and all(d["continent"] in NEW_WORLD for d in native):
        return "impossible (native only in the Americas/Australasia/Pacific)", where
    return "far", where


def main() -> None:
    herbs = json.load(open(HERE / "herb_candidates_resolved.json", encoding="utf-8"))["herbs"]
    wcvp = json.load(open(WCVP, encoding="utf-8"))
    acc = wcvp["accepted"]
    by_name = {}
    for pid, a in acc.items():
        by_name.setdefault(squash(a["taxon_name"]), pid)
    fits = FITS[BOOK]

    out, top_labels, rescued, stats = {}, Counter(), 0, Counter()
    for hid, h in herbs.items():
        cands = []
        for g in h["candidates"]:
            if not g["resolved"] or not g.get("culpeper_names") and not g["strong_rows"]:
                continue                           # unresolved, or weak evidence only
            rec = {"accepted_name": g["accepted_name"], "rank": g["rank"], "strong_rows": g["strong_rows"],
                   "book_names": g["culpeper_names"], "sources": g["source_families"]}
            pid = g.get("wcvp_id") if g.get("wcvp_id") in acc else by_name.get(squash(g["accepted_name_without_authors"]))
            if g["rank"] not in ("species", "subspecies", "variety", "form") and not (g["rank"] or "").startswith("sp"):
                rec["geography"], rec["native_regions"] = "not checked (genus or family level)", []
            elif not pid or not acc[pid].get("distribution"):
                rec["geography"], rec["native_regions"] = "no distribution data", []
            else:
                rec["geography"], rec["native_regions"] = label(acc[pid]["distribution"])
                rec["wcvp_range"] = acc[pid].get("geographic_area")
            cands.append(rec)
        fit = lambda r: r["geography"].startswith(fits)
        checked = [r for r in cands if not r["geography"].startswith(("not checked", "no distribution"))]
        first_fit = next((r["accepted_name"] for r in checked if fit(r)), None)
        out[hid] = {"name": h["name"], "label": h.get("label"), "first_candidate_that_fits": first_fit,
                    "candidates": cands}
        if checked:
            t = checked[0]
            top_labels[t["geography"].split(" (")[0]] += 1
            if not fit(t) and first_fit:
                rescued += 1
        for r in cands:
            stats[r["geography"].split(" (")[0]] += 1

    OUT.write_text(json.dumps({"book": BOOK, "wcvp_version": wcvp.get("wcvp_version"),
                               "note": "WCVP distributions describe where plants grow today",
                               "herbs": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    unit = "herbs" if BOOK == "culpeper" else "chapters"
    world = "England (Britain/Ireland)" if BOOK == "culpeper" else "the Mediterranean and his trade world"
    print(f"\nGeography check for {BOOK.capitalize()}: {world}\n")
    print("  all candidates (strong or medium evidence): " + ", ".join(f"{k} {n}" for k, n in stats.most_common()))
    print(f"\n  top checked candidate of each of {sum(top_labels.values())} {unit}: "
          + ", ".join(f"{k} {n}" for k, n in top_labels.most_common()))
    print(f"  {rescued} {unit}: the top candidate does not fit, but a lower one does")
    print(f"\nSaved to matching/{BOOK}/geography.json\n")

    if "--show" in sys.argv:
        want = sys.argv[sys.argv.index("--show") + 1].lower()
        for hid, h in out.items():
            if want in (hid, (h["name"] or "").lower(), (h["label"] or "").lower()):
                print(f"{h['label'] or h['name']} {h['name']}:  first that fits: {h['first_candidate_that_fits']}")
                for r in h["candidates"][:10]:
                    print(f"  {r['accepted_name'][:45]:45} {r['geography'][:40]:40} {', '.join(r['native_regions'][:3])}")


if __name__ == "__main__":
    main()
