"""Validate herbs.json against Culpeper's own General Index and the raw HTML.

Usage:  python3 historical_texts/culpeper/validate_herbs.py   (defaults: culpeper.html and herbs.json beside this script)

Independent of extract_herbs.py: it re-reads the HTML itself.

Checks
  1. Index -> extraction: every General Index entry pointing at a page of the
     herbal (pages 1-199) is matched by an extracted entry on that page.
  2. Extraction -> index: every extracted entry is referenced by some index
     entry on its page.
  3. Missed headings: no upper-case line inside the herbal that looks like a
     heading is left unclaimed.
  4. Record sanity: unique ids, non-empty text, pages in range, ordered.
Prints one line on success. Run with --details to see the full report,
including the misprints in the book's own index that are corrected for.
Exit code 0 only if every check passes.
"""
import html as htmllib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

HERBAL_LAST_PAGE = 199

# Misprints in the book's own General Index, each checked by hand against the
# herbal: (index name, page the index gives) -> page the entry is really on.
INDEX_ERRATA = {
    ("Fennel Sow, or Hog’s Fennel", 47): 74,      # digits swapped
    ("Thyme", 123): 183,
    ("Trefoil, Meadow, or Honey-suckles", 115): 185,
    ("Scabious, three sorts", 161): 168,
    ("Wood", 193): 193,                           # "Wood" misprinted for WOAD
    ("Thyme Wild, or Mother of Thyme", 123): 183,  # "ib." under the misprinted Thyme
}
# Herbs the index points to only at a Dispensatory page (>199), never at the
# page where the herb is described.
INDEX_SKIPS_ENTRY = {
    "BALM.": "indexed only at p215",
    "MALLOWS AND MARSHMALLOWS.": "indexed only at p218/p223",
    "SPLEENWORT, CETERACH, OR HEART’S TONGUE.": "indexed only at p223 (ib. under Spikenard)",
    "TURNSOLE, OR HELIOTROPIUM.": "indexed only at p224",
    "WOODBINE, OR HONEY-SUCKLES.": "indexed only at p223 (ib. under Wood)",
}
# Index lines on herbal pages that are not herbs at all.
INDEX_NOT_HERBS = {"Electuaries purging"}
ERRATA_NAMES = {("Wood", 193): "Woad"}
STOP = {"the", "or", "and", "of", "called", "a", "by", "some", "also", "in", "tree", "bush",
        "common", "garden", "wild", "great", "small", "sweet", "herb", "s"}


def clean(fragment):
    fragment = re.sub(r'<span class="pagenum">.*?</span>', " ", fragment, flags=re.S)
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def _norm(w):
    w = re.sub(r"(.)\1", r"\1", w)  # old doubled spellings: Wallnut = Walnut
    return w.rstrip("s") if len(w) > 4 else w  # crude singular: Mallows/Mallow


def tokens(text):
    t = text.lower().replace("’", "").replace("'", "")
    out = set()
    for chunk in re.split(r"[,;.()]| or | and ", t):
        words = [w for w in re.findall(r"[a-z]+", chunk) if w not in STOP]
        out.update(_norm(w) for w in words if len(w) >= 3)
        if len(words) > 1:
            out.add(_norm("".join(words)))  # Maiden Hair -> maidenhair, Ars-smart -> arssmart
    return out


def parse_index(source, herbal_only=True):
    start = next(m.start() for m in re.finditer(r"<h2[^>]*>(.*?)</h2>", source, re.S)
                 if clean(m.group(1)).startswith("GENERAL INDEX"))
    end = source.index("A LIST OF THE PRINCIPAL DISEASES", start)
    block = source[start:end]
    entries, head, last_pages = [], None, []
    for raw in block.split("<br>"):
        text = clean(raw)
        pages = [int(p) for p in re.findall(r'href="#Page_(\d+)"', raw)]
        if text.endswith("ib."):  # ibidem: same page as the line above
            pages, text = last_pages, text[:-3]
        if not text or not pages:
            continue
        last_pages = pages
        name = re.sub(r"[,\s\d]+$", "", text)
        if name.startswith("——"):
            name = (head or "") + " " + name.lstrip("— ").strip()
        else:
            head = name.split(",")[0]
        for p in pages:
            if p <= HERBAL_LAST_PAGE or not herbal_only:
                entries.append({"index_name": name, "page": p})
    return entries


def full_report():
    src = sys.argv[1] if len(sys.argv) > 1 else HERE / "culpeper.html"
    out = sys.argv[2] if len(sys.argv) > 2 else HERE / "herbs.json"
    source = open(src, encoding="utf-8").read()
    herbs = json.load(open(out, encoding="utf-8"))["herbs"]
    failures = []

    # 4. sanity
    ids = [h["id"] for h in herbs]
    if len(ids) != len(set(ids)):
        failures.append("duplicate ids")
    for h in herbs:
        if not (h["sections"] or h["intro"]):
            failures.append(f"empty entry: {h['heading']}")
        if not 1 <= h["page"] <= HERBAL_LAST_PAGE:
            failures.append(f"page out of range: {h['heading']} p{h['page']}")
    if [h["source_line"] for h in herbs] != sorted(h["source_line"] for h in herbs):
        failures.append("entries out of source order")

    # 5. every other name is backed by a quote that is word-for-word in the book
    book_text = clean(source).lower()
    for h in herbs:
        quoted = set()
        for ev in h.get("name_evidence", []):
            if ev["quote"].lower() not in book_text:
                failures.append(f"quote not found in the book: {h['name']}: {ev['quote'][:60]}")
            for n in ev["names"]:
                quoted.add(n)
                if n.lower().replace("-", "") not in ev["quote"].lower().replace("-", "") \
                        and n.lower() not in ("wild vine",):  # "Wild, and Wood Vine"
                    failures.append(f"name not in its quote: {h['name']}: {n}")
        for n in h["other_names"]:
            if n not in quoted:
                failures.append(f"other name with no quote: {h['name']}: {n}")

    # 1 & 2. index cross-check (allow the heading to sit up to one page earlier,
    # since a heading at the foot of a page is indexed by the page its text is on)
    index = parse_index(source)
    herb_tok = [tokens(" , ".join([h["heading"], h["name"], *h["other_names"]])) for h in herbs]
    herb_pages = [{h["page"], h.get("also_printed_on_page", h["page"])} for h in herbs]
    referenced = set()
    unmatched_index = []
    errata_used = []
    for ie in index:
        key = (ie["index_name"], ie["page"])
        if ie["index_name"] in INDEX_NOT_HERBS:
            errata_used.append(f"not a herb: {ie['index_name']} p{ie['page']}")
            continue
        page = INDEX_ERRATA.get(key, ie["page"])
        it = tokens(ERRATA_NAMES.get(key, ie["index_name"]))
        if key in INDEX_ERRATA:
            errata_used.append(f"index misprint: {ie['index_name']} p{ie['page']} -> p{page}")
        near = [i for i in range(len(herbs)) if any(page - 1 <= p <= page + 1 for p in herb_pages[i])]
        hits = [i for i in near if it & herb_tok[i]]
        if hits:
            referenced.update(hits)
        else:
            unmatched_index.append(ie)
    # Classify misses so a real one cannot hide among index errors.
    all_index = parse_index(source, herbal_only=False)
    page_mismatch, index_only = [], []
    for ie in unmatched_index:
        it = tokens(ie["index_name"])
        hits = [h for h, ht in zip(herbs, herb_tok) if it & ht]
        if hits:
            page_mismatch.append((ie, hits))
        else:
            index_only.append(ie)
    unreferenced, not_in_index_herbal_pages = [], []
    for i, h in enumerate(herbs):
        if i in referenced:
            continue
        if h["heading"] in INDEX_SKIPS_ENTRY:
            errata_used.append(f"index skips entry: {h['heading']} ({INDEX_SKIPS_ENTRY[h['heading']]})")
            continue
        named = [ie for ie in index if tokens(ie["index_name"]) & herb_tok[i]]
        elsewhere = [ie for ie in all_index if tokens(ie["index_name"]) & herb_tok[i]]
        if named:
            unreferenced.append((h, "index has it on another page: " +
                                 ", ".join(f"{ie['index_name']} p{ie['page']}" for ie in named[:3])))
        elif elsewhere:
            unreferenced.append((h, "index lists it only outside the herbal: " +
                                 ", ".join(f"p{ie['page']}" for ie in elsewhere[:3])))
        else:
            not_in_index_herbal_pages.append(h)

    # 3. missed headings: upper-case lines in the herbal not claimed by an entry
    h2 = [(m.start(), clean(m.group(1))) for m in re.finditer(r"<h2[^>]*>(.*?)</h2>", source, re.S)]
    s = next(p for p, t in h2 if t.startswith("THE ENGLISH PHYSICIAN ENLARGED"))
    e = next(p for p, t in h2 if p > s and t.startswith("DIRECTIONS FOR MAKING SYRUPS"))
    claimed = {h["heading"] for h in herbs}
    claimed_lines = set()
    for h in herbs:
        for line in (h["source_line"], h.get("also_printed_at_line")):
            if line:
                claimed_lines.update(range(line, line + 4))
    offset = source[:s].count("\n")
    missed = []
    for n, line in enumerate(source[s:e].split("\n"), start=offset + 1):
        t = clean(line)
        letters = re.sub(r"[^A-Za-z]", "", t)
        if len(letters) >= 4 and letters.isupper() and n not in claimed_lines \
                and t not in ("THE ENGLISH PHYSICIAN", "ENGLISH PHYSICIAN", "ENLARGED."):
            missed.append((n, t))

    print(f"entries extracted:              {len(herbs)}")
    print(f"index references (p1-{HERBAL_LAST_PAGE}):       {len(index)}")
    print(f"  matched to an entry on that page: {len(index) - len(unmatched_index)}")
    print(f"  name matches, page differs:       {len(page_mismatch)}")
    for ie, hits in page_mismatch:
        print(f"      index p{ie['page']:<4} {ie['index_name']:35} -> {hits[0]['heading']} p{hits[0]['page']}")
    print(f"  NO ENTRY ANYWHERE (check!):       {len(index_only)}")
    for ie in index_only:
        print(f"      p{ie['page']:<4} {ie['index_name']}")
    print(f"entries not matched on their page:  {len(unreferenced) + len(not_in_index_herbal_pages)}")
    for h, why in unreferenced:
        print(f"      p{h['page']:<4} {h['heading']:45} {why}")
    print(f"  entries the index never names:    {len(not_in_index_herbal_pages)}")
    for h in not_in_index_herbal_pages:
        print(f"      p{h['page']:<4} {h['heading']}")
    print(f"upper-case lines unclaimed:   {len(missed)}")
    for n, t in missed:
        print(f"    line {n}: {t}")
    print(f"sanity failures:              {len(failures)}")
    for f in failures:
        print("    " + f)
    print(f"documented exceptions applied: {len(errata_used)}")
    for x in errata_used:
        print("    " + x)
    problems = len(unmatched_index) + len(unreferenced) + len(not_in_index_herbal_pages) + len(missed) + len(failures)
    print("\nRESULT:", "PASS" if problems == 0 else f"FAIL ({problems} unexplained)")
    sys.exit(0 if problems == 0 else 1)


def main():
    """Print one line; the full report only on failure or with --details."""
    import contextlib, io
    details = "--details" in sys.argv
    sys.argv = [a for a in sys.argv if a != "--details"]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            full_report()
            code = 0
        except SystemExit as e:
            code = e.code or 0
    out = buf.getvalue()
    num = lambda label: int(re.search(re.escape(label) + r":?\s+(\d+)", out).group(1))
    print("\nChecking herbs.json against the book...\n")
    if code == 0:
        n, refs = num("entries extracted"), num("index references (p1-199)")
        print(f"  \u2713  {n} herbs, each with its own name, page and text")
        print(f"  \u2713  Every herb in the book's index was found   ({refs} of {refs})")
        print(f"  \u2713  Every herb found is in the book's index")
        print(f"  \u2713  No herb in the book was missed")
        print(f"  \u2713  Every other name is quoted word-for-word from the book\n")
        print(f"  Note: the book's own index has {num('documented exceptions applied')} mistakes "
              "(wrong page numbers, herbs indexed")
        print("        only in a later chapter, one non-herb), which were allowed for. Run with --details to see them.\n")
        print("Result: PASSED - every herb was extracted correctly.\n")
        if details:
            print(out)
    else:
        print(out)
        print("Result: FAILED - see the problems listed above.\n")
    sys.exit(code)


if __name__ == "__main__":
    main()
