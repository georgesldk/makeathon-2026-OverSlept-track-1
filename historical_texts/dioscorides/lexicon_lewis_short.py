"""Look up the Latin names in Dioscorides (the names the Romans use, written in Greek letters
in the RV/N lists) in Lewis & Short's Latin Dictionary, and collect the plant identifications
it gives (a labelled evidence layer, like lexicon_lsj.py).

Usage:  python3 historical_texts/dioscorides/lexicon_lewis_short.py

Reads  historical_texts/dioscorides/lexicon_lsj.json     (for each name's Latin spelling)
       reference_sources/lewis_short/lewis_short_index.json.gz
       scientific_name_sources/wcvp/data/wcvp_names.csv  (optional: to check genera)
Writes historical_texts/dioscorides/lexicon_lewis_short.json

For each Roman / Latin name: its words are reduced to dictionary form (veneriam -> veneria,
gladiolum -> gladiolus; a form only counts if Lewis & Short has it), and every Latin
binomial in the entry is kept (genus checked against WCVP), with the English gloss.
Lewis & Short's identifications (1879) are the lexicographers' opinions.
"""
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

from lexicon_lsj import read_entry, load_genera   # same reading of entries as for LSJ

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LSJ_OUT = HERE / "lexicon_lsj.json"
LS = ROOT / "reference_sources" / "lewis_short" / "lewis_short_index.json.gz"
OUT = HERE / "lexicon_lewis_short.json"
ROMAN = {"Romans", "Latins", "Italians"}
# inflected Latin ending -> dictionary endings
ENDINGS = [("icem", ["ix"]), ("inem", ["o"]), ("onem", ["o"]), ("tem", ["s"]), ("rem", ["r", "ris"]),
           ("am", ["a"]), ("um", ["us", "um"]), ("em", ["is", "es"]), ("im", ["is"]), ("ae", ["a"]),
           ("as", ["a"]), ("os", ["us"]), ("i", ["us", "um"]), ("is", ["is", "us"]), ("a", ["a", "um"])]


def plain(w: str) -> str:
    return re.sub(r"[^a-z]", "", w.lower().replace("j", "i").replace("v", "u"))


def candidates(word: str) -> list[str]:
    w = plain(word)
    out = [w]
    for suf, reps in ENDINGS:
        if w.endswith(suf) and len(w) > len(suf) + 2:
            out += [w[: -len(suf)] + r for r in reps]
    return list(dict.fromkeys(out))


def main() -> None:
    chapters = json.load(open(LSJ_OUT, encoding="utf-8"))["chapters"]
    with gzip.open(LS, "rt", encoding="utf-8") as g:
        entries = json.load(g)["entries"]
    by_lemma = defaultdict(list)
    for e in entries:
        by_lemma[e["lemma"]].append(e)
    genera = load_genera()
    out, n_names, n_found, n_bin = [], 0, 0, 0
    for c in chapters:
        recs = []
        for n in c["names"]:
            if n["attributed_to"] not in ROMAN:
                continue
            n_names += 1
            hit = None
            for i, word in enumerate(n["latin_form"].split()[:2]):
                for cand in candidates(word):
                    if cand in by_lemma:
                        hit = {"dictionary_form": cand, "matched_word": word, "word_position": i + 1,
                               "entries": [{"ls_key": e["key"], **read_entry(e["text"], genera)}
                                           for e in by_lemma[cand]]}
                        break
                if hit:
                    break
            hit = hit or {"dictionary_form": None, "entries": []}
            n_found += bool(hit["entries"])
            n_bin += any(x["identifications"] for x in hit["entries"])
            recs.append({"name": n["name"], "latin_form": n["latin_form"], "layer": n["layer"],
                         "attributed_to": n["attributed_to"], **hit})
        out.append({"label": c["label"], "headword": c["headword"], "names": recs,
                    "note": "Lewis & Short (1879) identifications: lexicographers' opinions, not Dioscorides' text"})
    OUT.write_text(json.dumps({"source": "Lewis & Short, A Latin Dictionary (1879), Perseus Digital Library, CC BY-SA",
                               "chapters": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{n_names} Roman / Latin names looked up in Lewis & Short")
    print(f"  {n_found} found, {n_bin} of them with a Latin binomial")
    print(f"\nSaved to historical_texts/dioscorides/{OUT.name}\n")


if __name__ == "__main__":
    main()
