"""Extract every herb entry from Culpeper's Complete Herbal (Gutenberg #49513, HTML edition).

Usage:  python3 historical_texts/culpeper/extract_herbs.py   (defaults: culpeper.html and herbs.json beside this script)

Only the Python standard library is used. The herbal proper runs from the
"THE ENGLISH PHYSICIAN ENLARGED." chapter up to "DIRECTIONS FOR MAKING SYRUPS";
everything after that (Dispensatory, Galen's Key, Last Legacies, Index) is not
herb entries and is ignored.

An entry starts at any of:
  * an <h3> inside the herbal (326 of them),
  * an <h4> whose text is entirely upper case (THE LESSER CELANDINE ...),
  * a <p> whose text is entirely upper case (CINQUEFOIL ..., wrapped in a div).
A mixed-case <h4> ("The BROOM RAPE also is not without its virtues") is a
subsection of the entry it sits in, not a new entry.
"""
import html as htmllib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

START_MARK = "THE ENGLISH PHYSICIAN ENLARGED."
END_MARK = "DIRECTIONS FOR MAKING SYRUPS"

SECTION_KEYS = {
    "descript.": "description",
    "description of the mild.": "description",
    "place.": "place",
    "time.": "time",
    "place and time.": "place_and_time",
    "time and place.": "place_and_time",
    "government and virtues.": "government_and_virtues",
    "government and virtues": "government_and_virtues",
}

BLOCK_RE = re.compile(r"<(h3|h4|p)\b[^>]*>(.*?)</\1>", re.S)
PAGE_RE = re.compile(r'id="Page_(\d+)"')
LABEL_RE = re.compile(r"^\s*<i>([^<]{1,40})</i>\s*\]\s*", re.S)


def text_of(fragment: str) -> str:
    fragment = re.sub(r'<span class="pagenum">.*?</span>', " ", fragment, flags=re.S)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", htmllib.unescape(fragment)).strip()


def is_all_caps(text: str) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", text)
    return len(letters) >= 3 and letters.isupper()


def split_names(heading: str) -> list[str]:
    """Best-effort split of a heading into the names Culpeper gives the plant.

    The heading itself is always kept verbatim in the output; this list is a
    convenience and is checked by eye, not trusted blindly.
    """
    h = heading.rstrip(".,").strip()
    has_alt = re.search(r"\bOR\b|\bCALLED\b|KNOWN BY THE NAME OF", h)
    if not has_alt:
        return [h]
    h = re.sub(r",?\s*\bOR MORE PROPERLY\b\s*", " OR ", h)
    parts = re.split(
        r";|,?\s*\b(?:VULGARLY |USUALLY )?(?:CALLED|KNOWN BY THE NAME OF)\b(?:\s+(?:ALSO|BY SOME|IN SOME COUNTIES))?\s*,?|,?\s*\bOR\b,?|,|\s+\bAND\b\s+",
        h,
    )
    names = [p.strip(" ,") for p in parts if p and p.strip(" ,")]
    return names


# Headings whose automatic split loses the noun ("THE WOOLLEN, OR, COTTON THISTLE").
NAME_OVERRIDES = {
    "THE WOOLLEN, OR, COTTON THISTLE.": ["WOOLLEN THISTLE", "COTTON THISTLE"],
}

SMALL_WORDS = {"of", "the", "and", "by", "in", "a"}


def display(name: str) -> str:
    name = re.sub(r"^THE\s+", "", name)
    words = re.findall(r"[A-Za-z’']+|[^A-Za-z’']+", name.lower())
    out = []
    for i, w in enumerate(words):
        out.append(w if (i > 0 and w in SMALL_WORDS) else w.capitalize())
    return "".join(out)


# --- Other names stated in the text -------------------------------------------
# Culpeper usually opens an entry with a sentence such as "It is called
# Snakeweed, English Serpentary, Dragon-wort, Osterick, and Passions."  The
# capitalised names after the naming verb are collected from those sentences.
NAMING_RE = re.compile(
    r"\b(?:is|are)\s+(?:also\s+|likewise\s+|by\s+(?:some|many)\s+)*called\b"
    r"|\bcall\s+(?:it|them)\b|\bcalled\s+(?:also|likewise)\b|\bnamed\b")
# Explanations inside a naming sentence ("because it strengthens the liver").
EXPLANATION_RE = re.compile(
    r"\bbecause\b[^,;:]*|\bfrom the (?:Greek|Latin)[^,;:]*|\bthough\b[^;]*"
    r"|\bI suppose\b[^;]*|\bby apothecaries\b|\bin Sussex\b")
CAPITALISED_RE = re.compile(r"(?:St\. )?[A-Z][\w’'-]*(?:\s+(?:of\s+|de\s+)?[A-Z][\w’'-]*)*")
LEADING_WORDS = {"It", "They", "This", "Besides", "The", "Some", "Others", "And", "Or", "But", "By", "In", "For"}
NOT_NAMES = {"English", "Latin", "Greek", "French", "Sussex", "Kent", "Hercules", "I", "Apothecaries"}

# Corrections from reading every naming sentence by hand. Each carries a note
# that is written into the herb's name_evidence.
TEXT_NAME_FIXES = {
    "Briony": {"replace": {"Wild": "Wild Vine"},
               "note": "'Wild, and Wood Vine' read as Wild Vine and Wood Vine"},
    "Heart’s-Ease": {"set": ["Herb of the Trinity", "Three Faces in a Hood",
                             "Live in Idleness", "Cull Me to You", "Pancies"],
                     "also_quote": "herb of the Trinity",
                     "note": "names contain lower-case words, so they were copied by hand from these sentences"},
    "Horehound": {"drop": ["Hen-bit"],
                  "note": "Hen-bit dropped: the book gives it as the name of the black sort, a different plant"},
    "Dog Mercury": {"drop": ["French Mercury"],
                    "note": "French Mercury dropped: it is the previous entry, not this herb"},
    "Elder Tree": {"move": (["Dead-wort", "Wall-wort"], "Dwarf-Elder"),
                   "note": "Dead-wort and Wall-wort moved to Dwarf-Elder: the sentence names the Dwarf-Elder"},
}


def names_in_text(text: str | None, known: set[str]) -> list[tuple[str, list[str]]]:
    """Return (sentence, names) for every naming sentence in the text."""
    found: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    protected = re.sub(r"\bSt\.\s", "St\u00b7 ", text or "")
    for sentence in re.split(r"(?<=\.)\s+", protected):
        sentence = sentence.replace("St\u00b7", "St.")
        verb = NAMING_RE.search(sentence)
        if not verb:
            continue
        rest = EXPLANATION_RE.sub(",", sentence[verb.end():])
        names = []
        for m in CAPITALISED_RE.finditer(rest):
            words = m.group(0).split()
            while words and words[0] in LEADING_WORDS:
                words = words[1:]
            name = " ".join(words)
            if name and name not in NOT_NAMES and name.lower() not in known and name not in seen:
                names.append(name)
                seen.add(name)
        if names:
            found.append((sentence.strip(), names))
    return found


def apply_name_fixes(name: str, evidence: list[tuple[str, list[str]]], moved_in: dict,
                     text: str) -> list[dict]:
    """Apply the hand corrections; return name_evidence records."""
    fix = TEXT_NAME_FIXES.get(name, {})
    records = []
    for quote, names in evidence:
        if fix.get("also_quote"):  # a name sits in the sentence before
            before = next(x for x in re.split(r"(?<=\.)\s+", text) if fix["also_quote"] in x)
            quote = before.strip() + " " + quote
        if "set" in fix:
            names = list(fix["set"])
        names = [fix.get("replace", {}).get(n, n) for n in names if n not in fix.get("drop", [])]
        if "move" in fix:
            moving, target = fix["move"]
            moved_in.setdefault(target, []).append(
                {"quote": quote, "names": [n for n in names if n in moving],
                 "note": f"from the {name} entry: {fix['note']}"})
            names = [n for n in names if n not in moving]
        rec = {"quote": quote, "names": names}
        if fix.get("note"):
            rec["note"] = fix["note"]
        records.append(rec)
        if "set" in fix:
            fix = {**fix, "set": []}  # set the names once, on the first sentence
    return records


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("’", "")).strip("-")


def extract(source: str) -> list[dict]:
    h2s = [(m.start(), text_of(m.group(1))) for m in re.finditer(r"<h2[^>]*>(.*?)</h2>", source, re.S)]
    start = next(pos for pos, t in h2s if t.startswith(START_MARK))
    end = next(pos for pos, t in h2s if pos > start and t.startswith(END_MARK))
    body = source[start:end]
    line_offset = source[:start].count("\n")

    # Track the printed page: a pagenum anchor marks where page N begins.
    page_marks = [(m.start(), int(m.group(1))) for m in PAGE_RE.finditer(body)]
    first_page = page_marks[0][1] - 1 if page_marks else 1

    def page_at(pos: int) -> int:
        page = first_page
        for p, n in page_marks:
            if p > pos:
                break
            page = n
        return page

    entries: list[dict] = []
    current = None
    for m in BLOCK_RE.finditer(body):
        tag, inner = m.group(1), m.group(2)
        text = text_of(inner)
        starts_entry = tag == "h3" or (tag in ("h4", "p") and is_all_caps(text))
        if starts_entry:
            current = {
                "heading": text,
                "page": page_at(m.start()),
                "source_line": line_offset + body[: m.start()].count("\n") + 1,
                "sections": {},
                "subsections": [],
                "_other": [],
            }
            entries.append(current)
            continue
        if current is None:
            continue  # chapter title / preamble before the first herb
        if tag == "h4":  # mixed-case subheading inside an entry
            current["subsections"].append(text)
            continue
        label = LABEL_RE.match(inner)
        key = SECTION_KEYS.get(text_of(label.group(1)).lower()) if label else None
        if key:
            content = text_of(inner[label.end():])
            current["sections"][key] = (current["sections"].get(key, "") + " " + content).strip()
            current["_last"] = key
        elif text:
            # Paragraph without a label: continuation of the previous section,
            # or (before any section) an introductory note.
            last = current.get("_last")
            if last:
                current["sections"][last] += " " + text
            else:
                current["_other"].append(text)

    # Finalise records.
    out: list[dict] = []
    moved_in: dict[str, list[dict]] = {}  # names a correction moves to a later entry
    by_text: dict[str, dict] = {}  # id -> record, to catch a herb printed twice
    for e in entries:
        names = [display(n) for n in NAME_OVERRIDES.get(e["heading"]) or split_names(e["heading"])]
        known = {n.lower() for n in names}
        intro = " ".join(e["_other"])
        evidence = apply_name_fixes(names[0], names_in_text(intro, known), moved_in, intro)
        evidence = [ev for ev in evidence if ev["names"] or ev.get("note")] + moved_in.pop(names[0], [])
        if len(names) > 1:
            evidence.insert(0, {"quote": e["heading"], "names": names[1:], "note": "from the heading"})
        text_names = [n for ev in evidence for n in ev["names"]]
        twin = by_text.get(slug(names[0]))
        if twin:  # the same herb printed a second time (ONE-BLADE p26, ONE BLADE p129)
            twin["also_printed_on_page"] = e["page"]
            twin["also_printed_at_line"] = e["source_line"]
            continue
        rec = {
            "id": slug(names[0]),
            "name": names[0],
            "other_names": list(dict.fromkeys(n for n in text_names if n not in names[:1])),
            "name_evidence": evidence,
            "heading": e["heading"],
            "page": e["page"],
            "source_line": e["source_line"],
            "intro": " ".join(e["_other"]) or None,
            "sections": e["sections"],
            "subsections": e["subsections"],
            "has_virtues_section": "government_and_virtues" in e["sections"],
        }
        by_text[rec["id"]] = rec
        out.append(rec)
    return out


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else HERE / "culpeper.html"
    dst = sys.argv[2] if len(sys.argv) > 2 else HERE / "herbs.json"
    source = open(src, encoding="utf-8").read()
    herbs = extract(source)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"source": "Culpeper, The Complete Herbal (Project Gutenberg #49513, HTML)",
                   "count": len(herbs), "herbs": herbs}, f, ensure_ascii=False, indent=2)
    virtues = sum(h["has_virtues_section"] for h in herbs)
    with_names = sum(bool(h["other_names"]) for h in herbs)
    no_virtues = [h["name"] for h in herbs if h["sections"] and not h["has_virtues_section"]]
    prose = [h["name"] for h in herbs if not h["sections"]]
    twice = [h["name"] for h in herbs if "also_printed_on_page" in h]
    print(f"\nFound {len(herbs)} herbs in Culpeper's Complete Herbal")
    print(f"(pages {herbs[0]['page']} to {herbs[-1]['page']}, from {herbs[0]['name']} to {herbs[-1]['name']})\n")
    print(f"  {virtues:>3}  describe the herb and its medicinal uses")
    print(f"  {len(no_virtues):>3}  describe the herb but give no medicinal uses   (e.g. {', '.join(no_virtues[:2])})")
    print(f"  {len(prose):>3}  are written as plain paragraphs               (e.g. {', '.join(prose[:2])})\n")
    print(f"  {with_names} herbs have other names recorded (e.g. Amara Dulcis is also Bitter-sweet)")
    if twice:
        print(f"  {', '.join(twice)} is printed twice in the book; kept as one herb\n")
    print(f"Saved to {Path(dst).parent.name}/{Path(dst).name}\n")


if __name__ == "__main__":
    main()
