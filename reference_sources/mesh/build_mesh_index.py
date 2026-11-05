"""Build a small MeSH index for matching claims to MeSH descriptors.

Usage:  python3 reference_sources/mesh/build_mesh_index.py

Input:  reference_sources/mesh/desc2026.gz (or desc20xx.gz / .xml), from
        https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/  (not in git; MISSING_FILES.md)
Output: reference_sources/mesh/mesh_index.json.gz (in git), per descriptor:
        ui, name, tree numbers, entry terms (synonyms), pharmacological actions;
        and a lookup from every normalised name or entry term to its descriptor(s).
MeSH is produced by the U.S. National Library of Medicine (public domain, NLM terms of use).
"""
import gzip
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "mesh_index.json.gz"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def main() -> None:
    src = sorted(list(HERE.glob("desc20*.gz")) + list(HERE.glob("desc20*.xml")))
    if not src:
        raise SystemExit("No desc20xx.gz or .xml in reference_sources/mesh/ (see MISSING_FILES.md)")
    path = src[-1]
    fh = gzip.open(path, "rb") if path.suffix == ".gz" else open(path, "rb")
    desc, lookup = {}, {}
    for _, el in ET.iterparse(fh, events=("end",)):
        if el.tag != "DescriptorRecord":
            continue
        ui = el.findtext("DescriptorUI")
        name = el.findtext("DescriptorName/String")
        terms = sorted({t.findtext("String") for t in el.iter("Term") if t.findtext("String")})
        trees = [t.text for t in el.iter("TreeNumber")]
        pas = [p.findtext("DescriptorReferredTo/DescriptorName/String") for p in el.iter("PharmacologicalAction")]
        desc[ui] = {"name": name, "trees": trees, "terms": [t for t in terms if t and t != name],
                    "actions": [p for p in pas if p]}
        for t in [name] + terms:
            if t:
                lookup.setdefault(norm(t), [])
                if ui not in lookup[norm(t)]:
                    lookup[norm(t)].append(ui)
        el.clear()
    with gzip.open(OUT, "wt", encoding="utf-8") as f:
        json.dump({"source": path.name, "descriptors": desc, "lookup": lookup}, f, ensure_ascii=False)
    print(f"{path.name}: {len(desc):,} descriptors, {len(lookup):,} names and synonyms. Saved to {OUT.relative_to(HERE.parent.parent)}")


if __name__ == "__main__":
    main()
