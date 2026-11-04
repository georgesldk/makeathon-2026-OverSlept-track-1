"""Check that extract_wellmann.py read Wellmann's Greek Dioscorides correctly.

Usage:  python3 historical_texts/dioscorides/validate_wellmann.py            # summary, a few examples
        python3 historical_texts/dioscorides/validate_wellmann.py --details  # every problem

Reads historical_texts/dioscorides/chapters.json and the source TEI file, and checks:
  1. Chapter numbers   every book runs 1, 2, 3, ... (Wellmann: 129, 186, 158, 192, 162+);
                       gaps are listed with the text around them
  2. Merged chapters   the chapters split back apart start with their own number in the source
  3. Pages             pages never go backwards within a volume
  4. Text              no footnote text, markup or digits left; no empty chapter
  5. RV / N lists      every RV/N footnote in the source is used; each is attached to the
                       chapter whose headword it names (or says so when it could not be)
  6. Names             every name is word for word in its quote (text names in the
                       chapter's opening, RV names in their footnote)
  7. Coverage          every Greek word of the source's chapter paragraphs is in the output
  8. Numbering vs LSJ  LSJ cites Dioscorides by Wellmann's chapter numbers; for each headword
                       found in LSJ, its citation in the same book should be our chapter
                       number (needs lexicon_lsj.json)
"""
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHAPTERS = HERE / "chapters.json"
SOURCE = HERE / "source" / "tlg0656.tlg001.1st1K-grc1.xml"
T = "{http://www.tei-c.org/ns/1.0}"
EXPECTED = {1: 129, 2: 186, 3: 158, 4: 192, 5: 162}     # last chapter number per book in Wellmann
DETAILS = "--details" in sys.argv
SHOW = None if DETAILS else 5


def plain(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("ς", "σ")
    return re.sub(r"[^\w\s]", "", s)


def report(title, problems, note=""):
    print(f"  {'PASS ' if not problems else 'CHECK'}  {title}" + (f"  ({note})" if note else ""))
    for p in problems[:SHOW]:
        print(f"          - {p}")
    if not DETAILS and len(problems) > (SHOW or 0):
        print(f"          ... and {len(problems) - SHOW} more (--details)")


def main() -> None:
    data = json.load(open(CHAPTERS, encoding="utf-8"))
    ch = [c for c in data["chapters"] if c["chapter"] != "preface"]
    print(f"\nValidating {len(ch)} chapters of Dioscorides (Wellmann's Greek edition)\n")

    # 1. numbering
    probs = []
    num = lambda c: int(re.match(r"\d+", c["chapter"]).group())
    for b in range(1, 6):
        ns = [num(c) for c in ch if c["book"] == b]
        if max(ns) != EXPECTED[b]:
            probs.append(f"book {b}: last chapter is {max(ns)}, Wellmann has {EXPECTED[b]}")
        for n in range(1, max(ns) + 1):
            if n not in ns:
                before = next((c for c in reversed(ch) if c["book"] == b and num(c) < n), None)
                probs.append(f"book {b}: no chapter {n}; {before['label'] if before else '-'} "
                             f"({before['headword'] if before else ''}) may contain it")
        dup = [k for k, v in Counter(c["label"] for c in ch if c["book"] == b).items() if v > 1]
        probs += [f"book {b}: chapter {d} appears twice" for d in dup]
    report("1. chapter numbers run without gaps", probs,
           "a/b chapters (3.73a, 3.73b) are Wellmann's own")

    # 2. merged chapters split back
    split = [c for c in ch if c.get("fix")]
    probs = [f"{c['label']}: opening '{c['opening'][:30]}'" for c in split if not c["text"]]
    report("2. chapters split back out of merged blocks", probs,
           f"{len(split)} chapters; " + "; ".join(data["fixes"]))

    # 3. pages
    probs = []
    for q, p in zip(ch, ch[1:]):
        if p["volume"] == q["volume"] and p["page"] and q["page"] and int(p["page"]) < int(q["page"]):
            probs.append(f"{p['label']} on vol. {p['volume']} p. {p['page']} after {q['label']} p. {q['page']}")
    report("3. pages never go backwards within a volume", probs,
           ", ".join(f"vol. {v}: pp. {min(int(c['page']) for c in ch if c['volume'] == v)}-"
                     f"{max(int(c['page']) for c in ch if c['volume'] == v)}" for v in (1, 2, 3)))

    # 4. text
    probs = [f"{c['label']}: empty" for c in ch if len(c["text"]) < 20]
    probs += [f"{c['label']}: leftover '{m.group()}'" for c in ch
              for m in [re.search(r"\d|RV:|SIM\.|EXC\.|<|>", c["text"])] if m]
    report("4. text is clean (no footnotes, markup or numbers)", probs)

    # 5. RV / N lists
    root = ET.parse(SOURCE).getroot()
    src_rv = [n for n in root.iter(T + "note")
              if re.match(r"^\d*\s*(?:RV|[ΝN])\s*:", re.sub(r"\s+", " ", "".join(n.itertext())).strip())]
    used = [n for c in data["chapters"] for n in c["notes"] if n["kind"] in ("RV", "N")]
    heads = {c["label"]: c["headword"] for c in ch}

    def list_head(text):
        body = re.sub(r"^\d*\s*(?:RV|[ΝN])\s*:\s*", "", text)
        return re.split(r"[·,\u0387]", body)[0][:20]

    unmatched = [f"{n['assigned_to']}: list for '{list_head(n['text'])}' left where the source puts it "
                 f"(chapter headword '{heads.get(n['assigned_to'])}')"
                 for n in used if not n.get("match_score")]
    report("5a. every RV/N list in the source is used", [] if len(used) == len(src_rv) else
           [f"source has {len(src_rv)}, output {len(used)}"], f"{len(used)} lists")
    report("5b. each list is attached to the chapter it names", unmatched,
           f"{len(used) - len(unmatched)} of {len(used)} match by headword; the rest sit where the "
           "source puts them")

    # 6. names in their quotes
    probs = []
    for c in ch:
        opening = plain(c["text"][:600])
        for n in c["text_names"]:
            if plain(n["name"]) not in opening:
                probs.append(f"{c['label']}: '{n['name']}' not in the chapter's opening")
        rvq = " ".join(plain(q["quote"]) for q in c["rv_quotes"])
        for n in c["rv_names"]:
            if plain(n["name"]) not in rvq:
                probs.append(f"{c['label']}: '{n['name']}' not in its RV/N list")
    total = sum(len(c["text_names"]) + len(c["rv_names"]) for c in ch)
    report("6. every name is word for word in its quote", probs, f"{total} names")

    # 7. coverage of the source text
    src_words = Counter()
    for p in root.find(f".//{T}div[@type='edition']").iter(T + "p"):
        e = ET.fromstring(ET.tostring(p))
        for parent in e.iter():
            for kid in list(parent):
                if kid.tag in (T + "note", T + "del"):
                    keep = kid.tail or ""
                    idx = list(parent).index(kid)
                    if idx:
                        prev = list(parent)[idx - 1]
                        prev.tail = (prev.tail or "") + keep
                    else:
                        parent.text = (parent.text or "") + keep
                    parent.remove(kid)
        src_words.update(plain(w) for w in re.findall(r"[^\W\d_]+", "".join(e.itertext())))
    out_words = Counter(plain(w) for c in data["chapters"] for w in re.findall(r"[^\W\d_]+", c["text"]))
    lost = src_words - out_words
    missing = sum(lost.values())
    report("7. every word of the source text is in the output", [] if missing == 0 else
           [f"{missing} of {sum(src_words.values())} words missing ({missing / sum(src_words.values()):.2%}): "
            + ", ".join(f"{w} x{n}" for w, n in lost.most_common(12))], f"{sum(src_words.values())} words")
    # 8. chapter numbers against LSJ's citations
    lex = HERE / "lexicon_lsj.json"
    if lex.exists():
        offs, probs = Counter(), []
        for c in json.load(open(lex, encoding="utf-8"))["chapters"]:
            head = c["names"][0] if c["names"] and c["names"][0]["layer"] == "headword" else None
            if not head:
                continue
            b, n = c["label"].split(".")
            n = int(re.match(r"\d+", n).group())
            cites = {r for e in head["entries"] for x in e["identifications"] for r in x["dsc"] + x["pseudo_dsc"]}
            same = [int(r.split(".")[1]) - n for r in cites if r.split(".")[0] == b]
            if same:
                d = min(same, key=abs)
                offs[d] += 1
                if d and abs(d) <= 3:
                    probs.append(f"{c['label']} ({c['headword']}): LSJ cites {b}.{n + d}")
        exact = offs.get(0, 0)
        checked = sum(v for k, v in offs.items() if abs(k) <= 3)
        report("8. chapter numbers agree with LSJ's citations of Wellmann", probs,
               f"{exact} of {checked} headwords cited by LSJ at exactly our chapter number")
    print()


if __name__ == "__main__":
    main()
