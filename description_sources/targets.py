"""Which candidate species need a modern description, per book (shared by the description sources).

For every herb (Culpeper) or chapter (Dioscorides) that has species-level candidates:
  - Wikipedia: the top 3 species candidates, plus the first candidate that fits the
    geography check if it is lower down (cheap: one call per species)
  - BHL: only the top candidate and the first that fits (expensive: 10-25 calls per species)
Culpeper herbs without a description section are skipped: there is nothing to compare
("It is so generally known ... I shall not trouble you with the description").
Candidates the geography check calls impossible (New World plants for Dioscorides) are skipped.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI_TOP = 3


def targets(book: str) -> dict:
    """species name (no authors) -> {"herbs": [herb or chapter], "bhl": bool}"""
    geo = json.load(open(ROOT / "matching" / book / "geography.json", encoding="utf-8"))["herbs"]
    described = None
    if book == "culpeper":
        herbs = json.load(open(ROOT / "historical_texts" / "culpeper" / "herbs.json", encoding="utf-8"))["herbs"]
        described = {h["name"] for h in herbs if (h.get("sections") or {}).get("description")}
    out = {}
    for h in geo.values():
        if described is not None and h["name"] not in described:
            continue
        cands = [c for c in h["candidates"] if c["rank"] == "species" and not c["geography"].startswith("impossible")]
        if not cands:
            continue
        fits = h.get("first_candidate_that_fits")
        herb = h.get("label") or h["name"]
        for i, c in enumerate(cands):
            first_fit = c["accepted_name"] == fits
            if i >= WIKI_TOP and not first_fit:
                continue
            name = strip_authors(c["accepted_name"])
            t = out.setdefault(name, {"herbs": [], "bhl": False})
            if herb not in t["herbs"]:
                t["herbs"].append(herb)
            t["bhl"] = t["bhl"] or i == 0 or first_fit
    return out


def strip_authors(name: str) -> str:
    """'Solanum dulcamara L.' -> 'Solanum dulcamara'; keeps hybrids ('Iris × germanica')."""
    parts = name.split()
    keep = parts[:3] if len(parts) > 2 and parts[1] in ("×", "x") else parts[:2]
    return " ".join(keep)


if __name__ == "__main__":
    for b in ("culpeper", "dioscorides"):
        t = targets(b)
        print(f"{b}: {len(t)} species for Wikipedia, {sum(v['bhl'] for v in t.values())} for BHL")
    both = set(targets("culpeper")) | set(targets("dioscorides"))
    print(f"both books: {len(both)} unique species")
