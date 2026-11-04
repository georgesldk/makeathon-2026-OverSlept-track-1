"""Extract every chapter of Dioscorides' De materia medica from Wellmann's Greek edition.

Usage:  python3 historical_texts/dioscorides/extract_wellmann.py

Reads  historical_texts/dioscorides/source/tlg0656.tlg001.1st1K-grc1.xml
       (Wellmann, Pedanii Dioscuridis Anazarbei De materia medica libri quinque, 3 vols,
       Berlin 1906-1914; TEI encoding by the First1KGreek project, Harvard / Leipzig;
       CC BY-SA 4.0; read on Scaife: urn:cts:greekLit:tlg0656.tlg001.1st1K-grc1)
Writes historical_texts/dioscorides/chapters.json

Each chapter's names come in two layers, kept apart:
  text_names   Dioscorides' own: the chapter opens with the headword and often its other
               names ("ἀσπάλαθος, οἱ δὲ ἐρυσίσκηπτρον, Σύροι δὲ διάξυλον καλοῦσι")
  rv_names     the attributed name lists (Romans, Egyptians, Gauls, Dacians, Magi ...)
               that Wellmann judged later additions and printed in his footnotes, marked
               "RV:" (and "N:" for codex N), e.g. "RV: ἶρίς· οἱ δὲ ἶρις Ἰλλυρική, ...,
               Ῥωμαῖοι ῥάδιξ ..., Αἰγύπτιοι ναρί"
Every name keeps who uses it ("others", "some", Romans, Egyptians, ...), the Greek quote
it comes from, and a Latin-letter transliteration (for searching modern sources later).

Also kept per chapter: Greek text (footnotes and Wellmann's deletions removed, his
additions kept), volume and page of Wellmann's edition, the parallel passages he cites
(SIM: Theophrastus, Pliny ...), and every footnote raw.

Fixes for the digital edition (each listed in the output):
  * in three places the encoders merged many chapters into one (book 1 from ch. 66,
    book 2 from ch. 105, book 4 from ch. 134); their paragraphs still start with the
    chapter number, so they are split back at those numbers
  * a footnote that runs over a page break continues in a note with no line number;
    it is joined to the RV / N note it continues
"""
import json
import re
from difflib import SequenceMatcher
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "source" / "tlg0656.tlg001.1st1K-grc1.xml"
OUT = HERE / "chapters.json"
T = "{http://www.tei-c.org/ns/1.0}"
VOLUME = {"1": 1, "2": 1, "3": 2, "4": 2, "5": 3}

# who uses a name: accent-free stems -> label
PEOPLE = {"ρωμαι": "Romans", "αιγυπτι": "Egyptians", "γαλλ": "Gauls", "δακ": "Dacians",
          "αφρ": "Africans", "συρ": "Syrians", "προφητ": "Prophets", "μαγ": "Magi",
          "πυθαγορ": "Pythagoras", "ζωροαστρ": "Zoroaster", "οσθαν": "Osthanes",
          "αρμενι": "Armenians", "καππαδοκ": "Cappadocians", "σικελ": "Sicilians",
          "θουσκ": "Etruscans", "τουσκ": "Etruscans", "σπαν": "Spaniards", "ισπαν": "Spaniards",
          "βησσ": "Bessi", "αθηναι": "Athenians", "βοιωτ": "Boeotians", "ιων": "Ionians",
          "κυπρι": "Cyprians", "αιθιοπ": "Ethiopians", "λιβυ": "Libyans", "ινδ": "Indians",
          "δημοκριτ": "Democritus", "κρατευ": "Crateuas", "ανδρε": "Andreas", "αραβ": "Arabs",
          "περσ": "Persians", "καρχηδον": "Carthaginians", "ποντικ": "Pontians", "κρητ": "Cretans",
          "θρακ": "Thracians", "μακεδον": "Macedonians", "ιταλ": "Italians", "λατιν": "Latins",
          "βαβυλων": "Babylonians", "ηπειρωτ": "Epirotes", "δαρδαν": "Dardanians", "μαρσ": "Marsi",
          "γαλατ": "Galatians", "ιλλυρι": "Illyrians", "αιολ": "Aeolians", "κιλικ": "Cilicians",
          "ιπποκρατ": "Hippocrates", "θεοφραστ": "Theophrastus", "νικανδρ": "Nicander"}
OTHERS = {"οιδε": "others", "ενιοι": "some", "τινες": "some", "υποτινων": "some", "υποτινωνδε": "some",
          "αλλοι": "others", "αλλοιδε": "others"}
VERBS = r"(?:καλεῖ|καλοῦσι|καλοῦσιν|καλεῖται|καλοῦνται|ὀνομάζουσι|ὀνομάζουσιν|ὀνομάζεται|λέγουσι|λέγουσιν|λέγεται|προσαγορεύουσι|προσαγορεύεται|ὠνόμασται|ἐκάλεσαν)"


def plain(s: str) -> str:
    """Greek without accents, breathings, case or punctuation (for comparing)."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("ς", "σ")
    return re.sub(r"[^\w]", "", s)


TRANSLIT = {"α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "e", "θ": "th", "ι": "i",
            "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x", "ο": "o", "π": "p", "ρ": "r", "σ": "s",
            "ς": "s", "τ": "t", "υ": "y", "φ": "ph", "χ": "ch", "ψ": "ps", "ω": "o"}


def translit(s: str) -> str:
    """Simple classical transliteration: ἶρις -> iris, ἄκορον -> akoron, ῥάδιξ -> rhadix."""
    out = []
    for word in (s or "").split():
        d = unicodedata.normalize("NFD", word)
        rough = "̔" in d
        base = "".join(c for c in d if not unicodedata.combining(c)).lower()
        w = []
        for i, ch in enumerate(base):
            if ch == "υ" and i and base[i - 1] in "αεηο":
                w.append("u")                          # αυ ευ ου -> au eu ou
            elif ch == "ρ" and i and base[i - 1] == "ρ":
                w.append("rh")                         # ρρ -> rrh
                continue
            elif ch == "γ" and i + 1 < len(base) and base[i + 1] in "γκξχ":
                w.append("n")                          # γγ -> ng
            else:
                w.append(TRANSLIT.get(ch, ch))
        t = "".join(w)
        if rough:
            t = "rh" + t[1:] if base[:1] == "ρ" else "h" + t
        out.append(t)
    return " ".join(out)


def first_number(text: str):
    m = re.match(r"^\s*(\d+)\s", text or "")
    return int(m.group(1)) if m else None


def clean(text: str) -> str:
    text = re.sub(r"(?<![\w])\d+(?![\w])", " ", text)       # margin line and section numbers
    return re.sub(r"\s+", " ", text).strip()


def walk(el, page, out, notes):
    """Text of an element without footnotes or deletions; footnotes and page breaks recorded."""
    tag = el.tag.replace(T, "")
    if tag == "pb":
        page[0] = el.get("n")
    elif tag == "note":
        notes.append({"text": re.sub(r"\s+", " ", "".join(el.itertext())).strip(), "page": page[0]})
    elif tag != "del":
        out.append(el.text or "")
        for ch in el:
            walk(ch, page, out, notes)
            out.append(ch.tail or "")
        return
    # pb / note / del: only the tail counts, added by the caller


def paragraphs(chapter_div, page):
    """(paragraph text, footnotes, page at its start) for every <p> in a chapter, in order.
    Footnotes and page breaks that sit outside a <p> go with the paragraph before them."""
    out = []

    def visit(el):
        tag = el.tag.replace(T, "")
        if tag == "p":
            start = page[0]
            parts, notes = [], []
            walk(el, page, parts, notes)
            out.append({"raw": "".join(parts), "notes": notes, "page": start})
        elif tag == "pb":
            page[0] = el.get("n")
        elif tag == "note":
            nt = {"text": re.sub(r"\s+", " ", "".join(el.itertext())).strip(), "page": page[0]}
            if out:
                out[-1]["notes"].append(nt)
            else:
                out.append({"raw": "", "notes": [nt], "page": page[0]})
        else:
            for kid in el:
                visit(kid)

    for kid in chapter_div:
        visit(kid)
    return out


def note_kind(t: str) -> str:
    if re.match(r"^\d*\s*RV\s*:", t):
        return "RV"
    if re.match(r"^\d*\s*[ΝN]\s*:", t):
        return "N"
    if re.match(r"^\d+\s*SIM\b", t):
        return "SIM"
    if re.match(r"^\d+\s*EXC\b", t):
        return "EXC"
    return "apparatus" if re.match(r"^\d", t) else "continuation"


# --- names ---------------------------------------------------------------------
def who_of(token: str):
    """('others' | people label | None, rest of the token)."""
    words = token.split()
    for n in (2, 1):
        key = plain("".join(words[:n]))
        if key in OTHERS:
            return OTHERS[key], " ".join(words[n:])
    if words:
        key = plain(words[0])
        for stem, label in PEOPLE.items():
            if key.startswith(stem) and words[0][:1].isupper():
                rest = words[1:]
                if rest and plain(rest[0]) in ("δε", "και"):
                    rest = rest[1:]
                return label, " ".join(rest)
    return None, token


def tidy(name: str):
    name = re.sub(r"\[[^\]]*\]|\([^)]*\)|[<>⟨⟩†*]", "", name)
    name = re.sub(VERBS + r".*$", "", name)
    name = re.sub(r"^(?:δὲ|δέ|καὶ|καί|ἣν|ἢν|ὃν|ὅν|ὃ|ἣ|ἥν|ἃ|ὁμοίως)\s+", "", name.strip())
    name = re.sub(r"\s+(?:δὲ|δέ|καὶ|καί)$", "", name.strip(" ,.;·:᾿’'"))
    name = name.strip(" ,.;·:᾿’'—-")
    if not name or len(name.split()) > 4 or re.search(r"\d", name):
        return None
    return name


def parse_list(segment: str, start_who=None) -> list[dict]:
    """'οἱ δὲ X, οἱ δὲ Y, Ῥωμαῖοι Z, Αἰγύπτιοι W' -> names with who uses them."""
    found, who = [], start_who
    for token in re.split(r"[,·;\u0387]|\s(?=οἱ\s+δ[ὲέ]\s)", segment):
        token = re.sub(r"^(?:ἣν|ἥν|ὃν|ὅν|ὃ|ἃ|ἣ|ὃς)\s+", "", token.strip())   # "ἣν ἔνιοι κάλυκα"
        if not token:
            continue
        w, rest = who_of(token)
        if w:
            who = w
        name = tidy(rest)
        if name:
            found.append({"name": name, "attributed_to": who})
    return found


def text_names(text: str, headword_plain: str) -> list[dict]:
    """Names in the opening sentence of the chapter, before the naming verb."""
    first = re.split(r"(?<=[.;])\s", text, maxsplit=1)[0]
    m = re.search(VERBS, first)
    head = first[:m.start()] if m else first
    if not re.search(r"οἱ δ|ἔνιοι|τιν[ὲεῶω]ς|τινων|ὑπό τινων|ὑπ᾿ ἐνίων", head) and not any(
            plain(w).startswith(tuple(PEOPLE)) and w[:1].isupper() for w in head.split()[1:]):
        return []
    # drop the headword itself (first item)
    parts = re.split(r"[,·\u0387]|\s(?=οἱ\s+δ[ὲέ]\s)", head, maxsplit=1)
    rest = parts[1] if len(parts) > 1 else ""
    if len(parts) == 1:   # "βρύον ὑπό τινων δὲ σπλάγχνον": no comma after the headword
        words = head.split()
        rest = " ".join(words[1:])
    # in the text a name is always introduced ("οἱ δὲ", "ἔνιοι", a people): words before
    # any such marker are description, not names
    return [{**n, "layer": "text"} for n in parse_list(rest)
            if n["attributed_to"] and plain(n["name"]) != headword_plain]


def rv_names(note: str) -> tuple[str | None, list[dict]]:
    """'RV: ἶρίς· οἱ δὲ ἶρις Ἰλλυρική, ... Αἰγύπτιοι ναρί. <description>' -> headword, names."""
    body = re.sub(r"^\d*\s*(?:RV|[ΝN])\s*:\s*", "", note)
    first = re.split(r"(?<=\.)\s", body, maxsplit=1)[0]
    first = first.replace("\u0387", "·")
    if "·" in first:
        head, rest = first.split("·", 1)
    else:
        head, rest = (first.split(",", 1) + [""])[:2]
    head = head.strip(" .")
    return head, parse_list(rest)


# --- chapters ------------------------------------------------------------------
def main() -> None:
    root = ET.parse(SOURCE).getroot()
    edition = root.find(f".//{T}div[@type='edition']")
    page = [None]
    chapters, fixes = [], []
    for book in edition.findall(f"{T}div[@subtype='book']"):
        b = book.get("n")
        if b in ("3", "5"):
            page[0] = None                # a new volume starts; its first page has no marker
        for div in book.findall(f"{T}div[@subtype='chapter']"):
            n = div.get("n")
            paras = paragraphs(div, page)
            if n == "preface":
                chapters.append({"book": int(b), "label": f"{b}.preface", "chapter": "preface", "paras": paras})
                continue
            cur = int(re.match(r"\d+", n).group())
            unit = {"book": int(b), "label": f"{b}.{n}", "chapter": n, "paras": []}
            merged = len("".join(p["raw"] for p in paras)) > 20000
            split_here = []
            for p in paras:
                k = first_number(p["raw"])
                if merged and k and cur < k <= cur + 3 and unit["paras"]:
                    chapters.append(unit)
                    cur = k
                    unit = {"book": int(b), "label": f"{b}.{k}", "chapter": str(k), "paras": [],
                            "fix": f"split out of {b}.{n} (chapters merged in the digital edition)"}
                    split_here.append(k)
                unit["paras"].append(p)
            chapters.append(unit)
            if split_here:
                fixes.append(f"book {b}: chapters {split_here[0]}-{split_here[-1]} split out of chapter {n}")

    # footnotes in order; continuations joined to the RV/N note they continue
    last_rv = None
    for c in chapters:
        c["notes"] = []
        for p in c["paras"]:
            for nt in p["notes"]:
                kind = note_kind(nt["text"])
                if kind == "continuation" and last_rv is not None:
                    last_rv["text"] += " " + nt["text"]
                    last_rv["continued_on_page"] = nt["page"]
                    continue
                rec = {"kind": kind, **nt}
                c["notes"].append(rec)
                if kind in ("RV", "N"):
                    last_rv = rec

    for v in (1, 2, 3):                   # chapters before the first page marker of a volume
        vol = [c for c in chapters if VOLUME[str(c["book"])] == v]
        first = next((int(p["page"]) for c in vol for p in c["paras"] if p["page"]), None)
        for c in vol:
            for p in c["paras"]:
                if p["page"] is None and first:
                    p["page"] = str(first - 1)
    out = []
    for c in chapters:
        raw = " ".join(p["raw"] for p in c["paras"])
        text = clean(raw)
        words = [w for w in re.findall(r"[^\s,.;·\u0387]+", text)]
        skip = {"ο", "η", "το", "οι", "αι", "τα", "δε", "και", "περι", "εστι", "εστιν", "του", "τησ"}
        head = next((w for w in words if plain(w) not in skip), None)
        out.append({
            "id": f"dioscorides-{c['book']}-{c['chapter']}",
            "book": c["book"], "chapter": c["chapter"], "label": c["label"],
            "volume": VOLUME[str(c["book"])], "page": c["paras"][0]["page"] if c["paras"] else None,
            "headword": head, "headword_latin": translit(head) if head else None,
            "opening": " ".join(words[:12]),
            "text": text, "notes": c["notes"], "fix": c.get("fix")})

    # RV / N notes -> the chapter whose headword they name (the note sits on the page where
    # the chapter starts, which may be in the previous chapter's paragraphs)
    by_pos = {id(c): i for i, c in enumerate(out)}
    for c in out:
        c.update(text_names=[], rv_names=[], rv_headwords=[], rv_quotes=[])
    for i, c in enumerate(out):
        for nt in c["notes"]:
            if nt["kind"] not in ("RV", "N"):
                continue
            head, names = rv_names(nt["text"])
            target, best = c, 0.0
            for j in sorted(range(max(0, i - 3), min(i + 4, len(out))), key=lambda j: abs(j - i)):
                hw = out[j]["headword"]
                if not (hw and head) or out[j]["book"] != c["book"]:
                    continue
                score = max(SequenceMatcher(None, plain(hw), plain(w)).ratio() for w in head.split())
                if score > best and score >= 0.6:
                    target, best = out[j], score
            nt["match_score"] = round(best, 2)
            nt["assigned_to"] = target["label"]
            target["rv_headwords"].append({"headword": head, "source": nt["kind"]})
            target["rv_names"] += [{**x, "layer": nt["kind"]} for x in names]
            target["rv_quotes"].append({"quote": nt["text"], "source": nt["kind"], "page": nt["page"]})

    for c in out:
        if c["chapter"] != "preface" and c["headword"]:
            c["text_names"] = text_names(c["text"], plain(c["headword"]))
        names = c["text_names"] + c["rv_names"]
        for x in names:
            x["latin"] = translit(x["name"])
        c["other_names"] = list(dict.fromkeys(x["name"] for x in names))
        c["parallels"] = [n["text"] for n in c["notes"] if n["kind"] == "SIM"]

    OUT.write_text(json.dumps({
        "source": "Dioscorides, De materia medica, ed. M. Wellmann (Berlin 1906-1914), TEI by First1KGreek "
                  "(Harvard College Library / University of Leipzig), urn:cts:greekLit:tlg0656.tlg001.1st1K-grc1",
        "licence": "CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/)",
        "fixes": fixes, "chapters": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    real = [c for c in out if c["chapter"] != "preface"]
    print(f"\n{len(real)} chapters (+{len(out) - len(real)} prefaces) -> historical_texts/dioscorides/{OUT.name}")
    for f in fixes:
        print(f"  fixed: {f}")
    print(f"  per book: " + ", ".join(f"{b}: {sum(1 for c in real if c['book'] == b)}" for b in range(1, 6)))
    print(f"  names in Dioscorides' text: {sum(len(c['text_names']) for c in real)} "
          f"in {sum(1 for c in real if c['text_names'])} chapters")
    print(f"  names in the RV/N lists:    {sum(len(c['rv_names']) for c in real)} "
          f"in {sum(1 for c in real if c['rv_names'])} chapters\n")


if __name__ == "__main__":
    main()
