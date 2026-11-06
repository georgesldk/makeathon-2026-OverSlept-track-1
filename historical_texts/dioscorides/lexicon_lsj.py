"""Look up every Dioscorides name in the LSJ Greek-English Lexicon and collect the modern
plant identifications it gives (a labelled evidence layer, kept separate from the text).

Usage:  python3 historical_texts/dioscorides/lexicon_lsj.py
        python3 historical_texts/dioscorides/lexicon_lsj.py --show 4.75     # one chapter

Reads  historical_texts/dioscorides/chapters.json        (extract_wellmann.py)
       reference_sources/lsj/lsj_index.json.gz            (build_lsj_index.py)
       scientific_name_sources/wcvp/data/wcvp_names.csv   (optional: to check genera)
Writes historical_texts/dioscorides/lexicon_lsj.json

For each name (headword, Dioscorides' own synonyms, RV/N list names):
  1. dictionary form: names are often inflected ("οἱ δὲ μαχαιρίωνα καλοῦσι" is accusative);
     the usual Greek endings are undone (μαχαιρίωνα -> μαχαιρίων, ξιρίδα -> ξιρίς) and a form
     only counts if LSJ has an entry for it
  2. LSJ entry: its English gloss, every Latin binomial it gives (genus checked against
     WCVP when available, abbreviations like "M. autumnalis" expanded), and the Dioscorides
     passages it cites for each ("Dsc. 4.75"; "Ps.-Dsc." = the RV lists)
  3. cites_this_chapter: the identification is given by LSJ for this very chapter; this is
     the strongest link, because LSJ distinguishes meanings by passage (ἑλένιον: calamint
     in one chapter, elecampane in the next)
  4. latin_form: the name in Latin spelling for searching (ἄκορον -> acorum); names the
     Romans use are Latin written in Greek letters and are spelt back (ῥάδιξ -> radix)

LSJ's identifications are the lexicographers' opinions (1940), not Dioscorides' words:
every record says so, and nothing here is merged into the text layers.
"""
import csv
import gzip
import copy
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CHAPTERS = HERE / "chapters.json"
LSJ = ROOT / "reference_sources" / "lsj" / "lsj_index.json.gz"
WCVP = ROOT / "scientific_name_sources" / "wcvp" / "data" / "wcvp_names.csv"
OUT = HERE / "lexicon_lsj.json"


def plain(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("ς", "σ")
    return re.sub(r"[^\w]", "", s)


# --- 1. dictionary form ------------------------------------------------------------
# inflected ending -> possible dictionary endings (accent-free, final sigma as σ)
ENDINGS = [("ωνα", ["ων"]), ("ονα", ["ων"]), ("ηνα", ["ην"]), ("ιδα", ["ισ"]), ("ιτα", ["ισ"]),
           ("ντα", ["ν", "σ"]), ("ακα", ["αξ"]), ("ικα", ["ιξ"]), ("υκα", ["υξ"]), ("ηκα", ["ηξ"]),
           ("γα", ["ξ"]), ("χα", ["ξ"]), ("πα", ["ψ"]), ("βα", ["ψ"]), ("φα", ["ψ"]), ("δα", ["σ"]),
           ("τα", ["σ"]), ("θα", ["σ"]), ("ια", ["ιον", "ια"]), ("ον", ["οσ", "ον"]), ("ην", ["η", "ησ"]),
           ("αν", ["α", "ασ"]), ("ιν", ["ισ", "ι"]), ("υν", ["υσ"]), ("ου", ["οσ", "ον"]), ("ησ", ["η", "ησ"]),
           ("ασ", ["α", "ασ"]), ("οι", ["οσ"]), ("αι", ["α", "η"]), ("ων", ["ων", "οσ", "ον"]),
           ("α", ["α", "ον", "ασ"]), ("ε", ["η"]), ("ι", ["ι", "ισ"])]


def candidates(word: str) -> list[str]:
    w = plain(word)
    out = [w]
    for suf, reps in ENDINGS:
        if w.endswith(suf) and len(w) > len(suf) + 2:
            out += [w[: -len(suf)] + r for r in reps]
    return list(dict.fromkeys(out))


# --- 2. LSJ entries ------------------------------------------------------------------
BINOMIAL = re.compile(r"\b([A-Z][a-z]{2,}|[A-Z]\.)\s+([A-Za-z][a-z\-]{2,})\b")
DSC = re.compile(r"(Ps\.-\s*)?Dsc\.\s*(?:Eup\.\s*)?(\d)\.\s*(\d+)|\bib\.\s*(?:(\d)\.\s*)?(\d+)\b")
# "ib. 4.109" names its book; "ib. 28" keeps the last one (round 2: "ib. 4.109" was read as "ib. 4")
LOCIS_CITATIS = re.compile(r"\b[Il]l\.\s?cc\.")    # "ll. cc." (OCR: "Il.cc."): "in the passages cited"
SUBSENSE = re.compile(r";\s+(?=[a-z][)(]?\.[\s,])")   # "; b. ἄγριος": the headword abbreviated
ALSO = re.compile(r";\s")     # "; also k. ἑτέρα, honeysuckle, Lonicera ...", "; stone pine, P. pinea": a new sense
AFTER_AUTHOR = re.compile(r"[A-Z][A-Za-z]*\.\s?$")   # "Hp. ll.cc." points to Hippocrates, not to Dioscorides
# other citations that OTHER_AUTHOR cannot see ("IG 2.61", "PCair.Zen. 223", "SIG 1170"): an "ib." after one
# of them may not be Dioscorides, so it is kept apart for review instead of guessed
OTHER_CITATION = re.compile(r"\b(?:[A-Z]{2,}[A-Za-z.]*|P[A-Z][A-Za-z.]+)\s?\d")
BOUNDARY = re.compile(r"\s(?:[IVX]+\.|\d\.)\s|:—|(?<=[a-z]{2})\.\s+(?=[a-z])|(?<=\d)\s\.\s+(?=[a-z])"
                      r"|(?<=\d)\s?[.;]\s+(?==\s)|(?<=[\w)])\s\.\s+(?=[^\d\s=])|(?<=\s)\)\.\s+(?=[^\d\s=])")
# round 2: a citation closed by " . " ends its sense ("Ath. 3.73a . of trees ...", "Ps.- Dsc. 4.112 . Nile water-lily")

# round 2: ". = ἀμβροσία" / "; = βάτος" after a citation starts another equivalence (a new sense)
OTHER_AUTHOR = re.compile(r"\b(?!Dsc\.|Ps\.)[A-Z][a-z]{1,12}\.\s")    # "Nic. ", "Plu. ", "Theoc. " (not "M. ")
ENGLISH = {"The", "This", "Name", "Cf", "Also", "Used", "See", "Prob", "Perh", "Lat", "Ion", "Att", "Dor",
           "Hom", "Hdt", "Ar", "Pl", "Arist", "Thphr", "Gal", "Hp", "Plin", "Nic", "Theoc", "Gr", "Eng",
           "Fr", "Sch", "Phot", "Hsch", "Suid", "Gp", "Orib", "Aret", "Paul", "Aet", "Alex", "Gloss",
           "Ps", "Dsc", "Aesch", "Soph", "Eur", "Plu", "Luc", "Ath", "Ael", "Poll", "Call", "Antig", "Opp"}


def read_entry(text: str, genera: set[str] | None) -> dict:
    """Binomials with the English gloss before them and the Dioscorides passages after them.

    Round 2 (Marselo's second audit):
      * "ll. cc." after a binomial ("Dsc. 2.164 ... :— Cyclamen graecum, etc., ll. cc.") gives it the Dioscorides
        passages cited before it in the same sense that no binomial took (kept also in "via_locis_citatis")
      * ";" followed by a new binomial (before any Dioscorides citation) starts a new sense, so later passages
        are not given to the earlier binomial (κυκλάμινος: "; also ... Lonicera", 2.165 is the honeysuckle's;
        πίτυς: "; stone pine, P. pinea, ... Dsc. 1.69" is not the Aleppo pine's)
      * ". = X" / "; = X" after a citation, "; b. ἄγριος" (the headword abbreviated) and a citation closed by
        " . " also end a sense
      * "ib." keeps the kind of the citation it repeats: after "Ps.-Dsc. 3.113", "ib. 114" is Ps.-Dsc. 3.114
      * an "ib." with an unrecognised citation in between goes to "uncertain_ib" (not evidence), for review
    """
    events = []
    for m in BINOMIAL.finditer(text):
        g, sp = m.group(1), m.group(2)
        if g.rstrip(".") in ENGLISH or (sp[:1].isupper() and (g.endswith(".") or not sp[1:].islower())):
            continue                                  # citations like "X. Smp", "Thphr. HP"
        events.append((m.start(), "bin", (g, sp.lower())))
    for m in DSC.finditer(text):
        events.append((m.start(), "dsc", m))
    for m in BOUNDARY.finditer(text):
        major = bool(re.match(r"\s(?:[IVX]+\.|\d\.)\s", m.group()))      # a numbered sense, not ":—"
        events.append((m.start(), "cut", major))
    for m in LOCIS_CITATIS.finditer(text):
        if not AFTER_AUTHOR.search(text[max(0, m.start() - 10):m.start()]):
            events.append((m.start(), "llcc", None))
    bins = [e[0] for e in events if e[1] == "bin"]
    for m in ALSO.finditer(text):
        nxt = next((p for p in bins if p > m.start()), None)
        dsc_first = re.search(r"Dsc\.", text[m.end():nxt]) if nxt else None
        if nxt is not None and nxt - m.end() <= 100 and not dsc_first:
            events.append((m.start(), "cut", False))
    for m in SUBSENSE.finditer(text):
        # "; b. ἄγριος, = κολχικόν, ib. 4.83": a sub-sense equated with another plant ends the sense; but
        # "; n. Ἰνδική Dsc. 1.7" (a kind of the same plant, spikenard, no gloss of its own) does not
        nxt = DSC.search(text, m.end())
        seg = text[m.end():nxt.start() if nxt else len(text)]
        # ... or a sub-sense with an English gloss of its own ("; m. κυδωνία quince, malus Punica, Dsc. 1.115")
        # (the equals sign stands alone: in Beta Code "=" is also the circumflex, mei=zon = μεῖζον)
        if re.search(r"(?:^|[\s,])=\s", seg) or re.search(r"(?<![\w*)(/\\=|])[a-z]{4,}(?![\w)(/\\=|])", seg):
            events.append((m.start(), "cut", False))
    if genera is not None:                            # a bare genus ("the purple Iris, I. germanica")
        for m in re.finditer(r"\b([A-Z][a-z]{2,})\b", text):
            if m.group(1) in genera:
                events.append((m.start(), "genus", m.group(1)))
    events.sort(key=lambda e: e[0])
    ids, open_, last_full, last_book, last_kind, last_dsc_end = [], [], {}, None, None, None
    orphans = []                                      # passages cited in this sense that no binomial took
    for pos, kind, val in events:
        if kind == "cut":
            open_ = []
            if val:
                orphans = []
        elif kind == "genus":
            last_full[val[0]] = val
        elif kind == "bin":
            g, sp = val
            if g.endswith("."):                       # "M. autumnalis" -> the last genus in M
                g = last_full.get(g[0])
                if not g:
                    continue
            if genera is not None and g not in genera:
                continue
            last_full[g[0]] = g
            before = text[max(0, pos - 80):pos]
            parts = [x.strip(" ,.") for x in re.split(r"[,;:(]|\s—\s|\.\s", before)]
            parts = [x for x in parts if x]
            last = parts[-1] if parts else ""
            gloss = last if last and re.fullmatch(r"[A-Za-z' \-]+", last) and last[:1].islower() else None
            current = next((x for x in ids if x["binomial"] == f"{g} {sp}"), None)
            if current is None:
                current = {"binomial": f"{g} {sp}", "gloss": gloss, "dsc": [], "pseudo_dsc": [],
                           "via_locis_citatis": [], "uncertain_ib": []}
                ids.append(current)
            open_.append(current)
        elif kind == "llcc":
            for cur in open_:
                for key, ref in orphans:
                    if ref not in cur[key]:
                        cur[key].append(ref)
                        cur["via_locis_citatis"].append(ref if key == "dsc" else f"Ps.-Dsc. {ref}")
            orphans = []
        elif kind == "dsc":
            m = val
            if m.group(2):
                last_book, last_dsc_end = m.group(2), m.end()
                last_kind = "pseudo_dsc" if m.group(1) else "dsc"
                ref, key = f"{m.group(2)}.{m.group(3)}", last_kind
            elif last_book and not OTHER_AUTHOR.search(text[last_dsc_end:pos]):
                # "ib. 28" repeats the last Dioscorides citation only when no other author is cited in between
                # ("Dsc. 4.98 ... Nic. Th. 792; also, a marsh-plant, ib. 415" is Nicander: bug 2), and it keeps
                # that citation's kind (Ps.-Dsc. or Dsc.)
                ref, key = f"{m.group(4) or last_book}.{m.group(5)}", last_kind
                last_book = m.group(4) or last_book
                if OTHER_CITATION.search(text[last_dsc_end:pos]):
                    for cur in open_:
                        cur["uncertain_ib"].append({"ref": ref, "kind": key, "context": text[max(0, pos - 60):pos + 12]})
                    last_dsc_end = m.end()
                    continue
                last_dsc_end = m.end()
            else:
                continue
            if not open_:
                orphans.append((key, ref))
            for cur in open_:
                # a citation belongs to every binomial named since the last sense break
                # ("m. arrhen = Mandragora officinalis, m. thelys = M. autumnalis, Dsc. 4.75")
                if ref not in cur[key]:
                    cur[key].append(ref)
    first_gloss = re.split(r"\s(?:Hom|Hdt|Thphr|Dsc|Hp|Arist|Pl|Ar|Gal)\.", text, maxsplit=1)[0]
    return {"start": first_gloss[:160], "identifications": ids}


# --- 4. Latin spelling ----------------------------------------------------------------
LAT = {"α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "e", "θ": "th", "ι": "i", "κ": "c",
       "λ": "l", "μ": "m", "ν": "n", "ξ": "x", "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t",
       "υ": "y", "φ": "ph", "χ": "ch", "ψ": "ps", "ω": "o"}


def latin_form(name: str, roman: bool = False, rough_first: bool = False) -> str:
    """Classical Latin spelling of a Greek name (ἄκορον -> acorum); for Latin words written
    in Greek letters (roman=True): ου -> u, β -> v (ῥάδιξ μουρικάτα -> radix muricata)."""
    words = []
    for word in name.split():
        d = unicodedata.normalize("NFD", word)
        rough = "\u0314" in d or (rough_first and not words)
        b = "".join(c for c in d if not unicodedata.combining(c)).lower()
        b = re.sub(r"[^\w]", "", b)
        if roman:
            b = b.replace("ου", "u").replace("β", "v")
            t = "".join(LAT.get(c, c) for c in b).replace("y", "u")
        else:
            b = b.replace("ου", "u").replace("αυ", "au").replace("ευ", "eu").replace("αι", "ae")
            b = b.replace("οι", "oe").replace("ει", "i")
            b = b.replace("γγ", "ng").replace("γκ", "nc").replace("ρρ", "rrh")
            t = "".join(LAT.get(c, c) for c in b)
            if b.endswith("οσ") or b.endswith("ος"):
                t = t[:-2] + "us"                   # -ος -> -us
            elif b.endswith("ον") and len(t) > 4:
                t = t[:-2] + "um"                   # -ον -> -um
        if rough:
            t = "rh" + t[1:] if b[:1] == "ρ" else "h" + t
        words.append(t)
    return " ".join(words)


def load_genera() -> set[str] | None:
    """Every genus in WCVP (vascular plants), plus the algae, mosses, lichens and fungi
    lexicons name for Dioscorides; None when the WCVP download is not there."""
    if not WCVP.exists():
        return None
    with open(WCVP, encoding="utf-8", newline="") as f:
        genera = {r["genus"] for r in csv.DictReader(f, delimiter="|", quoting=csv.QUOTE_NONE) if r["genus"]}
    return genera | {"Ulva", "Usnea", "Marchantia", "Fucus", "Lichen", "Agaricus", "Boletus", "Polyporus",
                     "Fomes", "Cetraria", "Lecanora", "Roccella", "Corallina", "Chondrus", "Sphaerococcus"}


def main() -> None:
    chapters = [c for c in json.load(open(CHAPTERS, encoding="utf-8"))["chapters"] if c["chapter"] != "preface"]
    with gzip.open(LSJ, "rt", encoding="utf-8") as g:
        lsj = json.load(g)["entries"]
    by_lemma = defaultdict(list)
    for e in lsj:
        by_lemma[e["lemma"]].append(e)
    genera = load_genera()
    parsed = {}

    def lookup(name: str) -> dict:
        for i, word in enumerate(name.split()[:2]):
            for cand in candidates(word):
                if cand in by_lemma:
                    entries = []
                    for e in by_lemma[cand]:
                        if e["key"] not in parsed:
                            parsed[e["key"]] = read_entry(e["text"], genera)
                        # a copy per chapter: "cites this chapter" is set per chapter below, and a shared
                        # parsed entry would carry one chapter's answer into another (bug 1, Marselo's audit)
                        entries.append({"lsj_key": e["key"], **copy.deepcopy(parsed[e["key"]])})
                    return {"dictionary_form": cand, "matched_word": word, "word_position": i + 1,
                            "entries": entries}
        return {"dictionary_form": None, "entries": []}

    out, stats = [], defaultdict(int)
    for c in chapters:
        num = re.match(r"\d+", c["chapter"]).group()
        here = f"{c['book']}.{num}"
        names = [{"name": c["headword"], "layer": "headword", "attributed_to": None}] if c["headword"] else []
        names += [{k: n[k] for k in ("name", "layer", "attributed_to")} for n in c["text_names"] + c["rv_names"]]
        recs = []
        for n in names:
            roman = n["attributed_to"] in ("Romans", "Latins", "Italians")
            hit = lookup(n["name"])
            for e in hit["entries"]:
                for x in e["identifications"]:
                    x["cites_this_chapter"] = here in x["dsc"] or here in x["pseudo_dsc"]
            # Latin spelling of the dictionary form when LSJ confirmed one (κιρκαίαν -> circaea)
            if hit["dictionary_form"] and not roman and len(n["name"].split()) == 1:
                rough = "\u0314" in unicodedata.normalize("NFD", n["name"])
                latin = latin_form(hit["dictionary_form"], rough_first=rough)
            else:
                latin = latin_form(n["name"], roman)
            recs.append({**n, "latin_form": latin, **hit})
        chapter_ids = {}
        for r in recs:
            for e in r["entries"]:
                for x in e["identifications"]:
                    if x["cites_this_chapter"]:
                        chapter_ids.setdefault(x["binomial"], {"binomial": x["binomial"], "gloss": x["gloss"],
                                                               "via_names": []})["via_names"].append(r["name"])
        out.append({"label": c["label"], "headword": c["headword"], "names": recs,
                    "identifications_for_this_chapter": list(chapter_ids.values()),
                    "note": "LSJ (1940) identifications: lexicographers' opinions, not Dioscorides' text"})
        stats["chapters"] += 1
        stats["headword in LSJ"] += bool(recs and recs[0]["layer"] == "headword" and recs[0]["entries"])
        stats["chapter has an LSJ identification citing it"] += bool(chapter_ids)
        stats["names"] += len(recs)
        stats["names found in LSJ"] += sum(bool(r["entries"]) for r in recs)
        stats["names with a Latin binomial"] += sum(any(e["identifications"] for e in r["entries"]) for r in recs)

    OUT.write_text(json.dumps({
        "source": "LSJ, A Greek-English Lexicon (Liddell, Scott, Jones, 9th ed. 1940), Perseus Digital Library, CC BY-SA",
        "genera_checked_against": "WCVP v16" if genera else None, "chapters": out},
        ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{stats['chapters']} chapters, {stats['names']} names looked up in LSJ\n")
    print(f"  {stats['headword in LSJ']:>5} chapter headwords found in LSJ")
    print(f"  {stats['chapter has an LSJ identification citing it']:>5} chapters with a Latin binomial that LSJ gives "
          f"for this very chapter")
    print(f"  {stats['names found in LSJ']:>5} of {stats['names']} names found in LSJ, "
          f"{stats['names with a Latin binomial']} of them with a Latin binomial")
    print(f"  genera checked against WCVP: {'yes' if genera else 'no (WCVP download not found)'}")
    print(f"\nSaved to historical_texts/dioscorides/{OUT.name} ({OUT.stat().st_size / 1e6:.1f} MB)\n")

    if "--show" in sys.argv:
        want = sys.argv[sys.argv.index("--show") + 1]
        for ch in out:
            if ch["label"] == want:
                print(f"{ch['label']} {ch['headword']}:")
                for x in ch["identifications_for_this_chapter"]:
                    print(f"  * {x['binomial']} ({x['gloss']})  via {', '.join(x['via_names'])}")
                for r in ch["names"][:12]:
                    print(f"    {r['layer']:8} {r['name'][:22]:22} -> {r['latin_form'][:22]:22} "
                          f"LSJ: {r['dictionary_form'] or '-'}")


if __name__ == "__main__":
    main()
