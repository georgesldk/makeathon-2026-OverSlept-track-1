"""Split Bretschneider's study of the Shennong materia medica into entries and match them to ours.

Usage:  python3 historical_texts/shennong/bretschneider.py            (needs: pip install pypinyin)
        python3 historical_texts/shennong/bretschneider.py --show 1.33

Reads  reference_sources/bretschneider/GetItemMetadata_23159_t_t.json   BHL OCR of
         E. Bretschneider, Botanicon Sinicum, Part III: Botanical investigations into the materia medica
         of the ancient Chinese. J. North China Branch Roy. Asiat. Soc., n.s. 29 (1895). Public domain.
         BHL item 23159 (fetched by check_sources.py)
       historical_texts/shennong/entries.json                            our Shennong entries
Writes historical_texts/shennong/bretschneider.json

Bretschneider numbers each drug of the Shen nung pen ts'ao king and the Pie lu (Mingyi bielu) and quotes
the classic as "Pen king". The OCR lost the Chinese characters, so entries are matched by romanisation:
each of our names is converted to Bretschneider's spelling (older Wade-Giles: 甘草 kan ts'ao, 薑 kiang,
玄 hüan) and compared with his heading and with the name he quotes from the Pen king. Only entries that
quote the Pen king can match a Shennong drug. Matches are one to one; each keeps its score and the
runner-up, so weak or close matches can be checked. His identification itself is prose (e.g. "Ch'e tsien
is the common name of Plantago major, L., at Peking") and is read in a later, checked step.
"""
import json
import re
import sys
from difflib import SequenceMatcher
from itertools import product
from pathlib import Path

from pypinyin import Style, pinyin

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OCR = ROOT / "reference_sources" / "bretschneider" / "GetItemMetadata_23159_t_t.json"
ENTRIES = HERE / "entries.json"
OUT = HERE / "bretschneider.json"
FIRST_PAGE, APPENDIX_PAGE = 18, 552           # page indexes: the plant list runs from 18 up to the appendix
HEAD = re.compile(r"(?m)^\W{0,3}(\d{1,3})\s?[.,]\s?[—–-]+\s?(.*)$")
PARTS = "子實仁根花葉皮莖汁核"

# pinyin initial -> Bretschneider (older Wade-Giles, k/h before i and ü as in his text)
INITIAL = [("zh", "ch"), ("ch", "ch'"), ("sh", "sh"), ("b", "p"), ("p", "p'"), ("d", "t"), ("t", "t'"),
           ("g", "k"), ("k", "k'"), ("z", "ts"), ("c", "ts'"), ("j", "k"), ("q", "k'"), ("x", "h"), ("r", "j")]


def syllable(py: str) -> str:
    """One pinyin syllable (no tones) -> Bretschneider's spelling."""
    py = py.replace("v", "ü").replace("u:", "ü")
    if py in ("zi", "ci", "si"):
        return {"zi": "tsz'", "ci": "ts'z'", "si": "sz'"}[py]
    if py in ("zhi", "chi", "shi", "ri"):
        return {"zhi": "chi", "chi": "ch'i", "shi": "shi", "ri": "ji"}[py]
    if py == "er":
        return "rh"
    ini, fin = "", py
    for a, b in INITIAL:
        if py.startswith(a):
            ini, fin = b, py[len(a):]
            break
    else:
        for a in "mfnlhwy":
            if py.startswith(a):
                ini, fin = a, py[1:]
                break
    if ini in ("k", "k'", "h") and py[0] in "jqx" and fin.startswith("u"):
        fin = "ü" + fin[1:]                       # ju, qu, xu are jü, qü, xü
    if ini == "y" and fin.startswith("u"):
        fin = "ü" + fin[1:]                       # yu(an) = yü(an)
    fin = re.sub(r"ian$", "ien", fin)              # -ian is -ien, but -iang stays (香 hiang, not hieng)
    fin = fin.replace("iong", "iung").replace("ong", "ung")
    if fin == "e" and ini in ("k", "k'", "h"):
        fin = "o"
    if fin == "uo" and ini not in ("k", "k'", "h", "sh", "ch", "ch'"):
        fin = "o"
    if ini == "y" and fin == "ou":
        fin = "u"
    return ini + fin


def variants(py: str) -> list:
    """Pinyin j/q/x merged two older series: 前 ts'ien but 乾 k'ien, 薑 kiang but 椒 tsiao. Both are tried."""
    out = [syllable(py)]
    if py[:1] in "jqx" and not py.startswith(("ju", "qu", "xu")):
        alt = {"j": "ts", "q": "ts'", "x": "s"}[py[0]] + syllable(py)[len({"j": "k", "q": "k'", "x": "h"}[py[0]]):]
        out.append(alt)
    return out


def romanisations(name: str, limit: int = 16) -> list:
    """Every reading (polyphones and j/q/x series included, at most `limit`) in Bretschneider's spelling."""
    readings = pinyin(name, style=Style.NORMAL, heteronym=True, errors="ignore")
    options = [[v for r in rs[:3] for v in variants(r)] for rs in readings]
    forms = []
    for combo in product(*options):
        forms.append(" ".join(combo))
        if len(forms) >= limit:
            break
    return forms


def norm(t: str) -> str:
    t = t.lower()
    t = re.sub(r"[‘’'`´°*]", "", t)
    t = t.replace("ü", "u").replace("ii", "u").replace("ti", "u") if False else t.replace("ü", "u").replace("ii", "u")
    return re.sub(r"[^a-z]", "", t)


REF = re.compile(r"\bP[.,]\s?,?\s?[XIVLxl1][XIVLxl1Uu]{0,4}\s?[a-e]?\s?[,.]\s?\d{1,3}")   # "P., XIIa, 1."


def split_entries(pages: list) -> list:
    """Headings: a line opening with a (possibly garbled) number and a dash, carrying the Pen ts'ao kang mu
    reference ("P., XIIa, 1."), or a clean "N.—" line. Numbers the OCR garbled ("90." for 50) are inferred
    from their neighbours and marked."""
    cands = []
    for i in range(FIRST_PAGE, APPENDIX_PAGE):
        t = pages[i].get("OcrText") or ""
        seen = set()
        for m in re.finditer(r"(?m)^(.{0,8}?)[—–]\s?-?(.*)$", t):
            lead, rest = m.group(1), m.group(2)
            if not re.search(r"\d|[oOlI]\d|^\W*$", lead):
                continue
            ref = REF.search(rest) or REF.search(t[m.end():m.end() + 80])
            num = re.search(r"(\d{1,3})", lead)
            if ref or (num and re.fullmatch(r"\W{0,3}\d{1,3}\s?[.,:]?\s?", lead)):
                cands.append({"page": i, "pos": m.start(), "read": int(num.group(1)) if num else None,
                              "line": rest, "has_ref": bool(ref)})
                seen.add(m.start())
        # the OCR sometimes turns the dash into digits ("32.95 7H tu huo. P., XII, 25."): a short line that
        # opens with a number and carries the reference is a heading too
        for m in re.finditer(r"(?m)^\W{0,3}(\d{1,3})[.,]\S*\s(.{0,70})$", t):
            if m.start() not in seen and REF.search(m.group(2)):
                cands.append({"page": i, "pos": m.start(), "read": int(m.group(1)), "line": m.group(2), "has_ref": True})
    cands.sort(key=lambda c: (c["page"], c["pos"]))
    seq, prev = [], 0
    for c in cands:
        r = c["read"]
        if r is not None and prev < r <= prev + 15:
            c["number"], c["number_inferred"] = r, False
        elif c["has_ref"]:
            c["number"], c["number_inferred"] = prev + 1, True
        else:
            continue                                   # a stray "12.—" inside the text
        seq.append(c)
        prev = c["number"]
    out = []
    for n, c in enumerate(seq):
        end = seq[n + 1] if n + 1 < len(seq) else {"page": APPENDIX_PAGE, "pos": 0}
        chunks = []
        for p in range(c["page"], min(end["page"], APPENDIX_PAGE - 1) + 1):
            t = pages[p].get("OcrText") or ""
            a = c["pos"] if p == c["page"] else 0
            b = end["pos"] if p == end["page"] else len(t)
            chunks.append(t[a:b])
        text = "\n".join(chunks)
        line = c["line"]
        heading = re.split(r"\bP[.,]\s?,?\s?[XIVLxl1]", line)[0][:60].strip()   # tokens() reads it
        pks = []
        for pk in re.finditer(r"Pen\s*king\s*[:;]?\s*[—–-]+\s*([A-Za-z][A-Za-z‘’'` ]{1,30}?)[.,(]", text):
            pkn = pk.group(1).strip()
            if len(pkn) > 1 and pkn[0].isupper() and pkn[1].isupper():
                pkn = pkn[1:]                          # "NKan ts'ao": a stray OCR capital
            pks.append(pkn)
        pkn = pks[0] if pks else None                  # more than one: a heading the OCR lost (two drugs)
        out.append({"number": c["number"], "number_inferred": c["number_inferred"], "heading": heading,
                    "pen_king_name": pkn, "pen_king_names": pks, "quotes_pen_king": bool(re.search(r"Pen\s*king", text)),
                    "pages": [pages[p]["PageID"] for p in range(c["page"], min(end["page"], APPENDIX_PAGE - 1) + 1)],
                    "text": text})
    return out


def tokens(t: str, heading: bool = False) -> list:
    """Romanised syllables in a heading: lower-case words with a vowel (the OCR'd Chinese leaves 'ff', 'BB')."""
    words = re.findall(r"[A-Za-z‘’'`]+", t or "")
    if heading:                                    # headings are lower case ("shi nan"); the OCR'd Chinese
        words = [w for w in words if not w[:1].isupper()]   # before them comes out capitalised ("Hi", "BB")
    # "rh" (耳, 兒) is a syllable without a vowel: 木耳 mu rh must not look like a one-syllable 木
    return [norm(w) for w in words if (re.search(r"[aeiouy]", w.lower()) or norm(w) == "rh")
            and len(norm(w)) <= 6 and norm(w)]


def score(ours: list, theirs: list) -> float:
    """Syllable by syllable: our N syllables against every run of N words in his heading or Pen king name;
    each syllable must be similar (>= 0.5), the score is their mean."""
    best = 0.0
    for form in ours:
        a = [norm(x) for x in form.split()]
        for k, t in enumerate(theirs):
            w = tokens(t, heading=(k == 0))
            if len(a) == 1 and not (k == 1 and len(w) == 1):
                continue                               # one syllable: only a one-word Pen king name counts
            for i in range(len(w) - len(a) + 1):
                r = [SequenceMatcher(None, x, y).ratio() for x, y in zip(a, w[i:i + len(a)])]
                if r and min(r) >= 0.8:                # every syllable close (OCR), not just similar:
                    best = max(best, sum(r) / len(r))    # chi / hi, lien / kien are other drugs
    return best


def main() -> None:
    pages = json.load(open(OCR, encoding="utf-8"))["Result"][0]["Pages"]
    bret = split_entries(pages)
    ours = json.load(open(ENTRIES, encoding="utf-8"))["entries"]
    pen = [b for b in bret if b["quotes_pen_king"]]
    pairs = []
    for e in ours:
        # the main name only: an other name (一名) can be another drug's main name (卮子 is also 木丹, close
        # to 牡丹 mou tan), and Bretschneider files each drug under its main name
        names = [n for n in [e["name"]] if n and not re.search(r"　|KT", n)]
        pm = e.get("plain_version_match") or {}
        if pm.get("confirmed") and len(pm["name"]) > len(e["name"]) and e["name"] in pm["name"]:
            # a heading that lost a character in the source (「黃」 for 黃耆, 「木」 for 蘗木): use the plain
            # version's full name, never the truncated one-character form
            names = [pm["name"]] + [n for n in names if n != e["name"]]
        names += [n[:-1] for n in names if len(n) > 2 and n[-1] in PARTS]   # not down to one syllable
        forms = [f for n in names for f in romanisations(n)]
        for b in pen:
            # each drug the entry quotes from the Pen king is a slot of its own (entries merged by a lost
            # heading hold two: "Pen king:— Pei mu ... Pen king:— Lung tan"); the heading is slot 0
            slots = [(0, [b["heading"], (b["pen_king_names"] or [None])[0]])]
            slots += [(k, [None, n]) for k, n in enumerate(b["pen_king_names"][1:], 1)]
            for k, names_ in slots:
                # the Pen king name is clean text: 0.8 is enough; a heading carries OCR'd Chinese and may hold
                # other drugs' syllables ("ta tou huang kiian"), so a match on the heading alone needs 0.9
                s_pk = score(forms, [None, names_[1]])
                s_head = score(forms, [names_[0], None])
                sc = max(s_pk if s_pk >= 0.9 else 0, s_head if s_head >= 0.9 else 0)
                if sc:
                    pairs.append((sc, e["label"], (b["number"], k), forms[0]))
    pairs.sort(reverse=True)
    taken_e, taken_b, match = set(), set(), {}
    for s, lab, slot, form in pairs:                         # one to one per slot, best first
        if lab in taken_e or slot in taken_b:
            continue
        taken_e.add(lab)
        taken_b.add(slot)
        num = slot[0]
        runner = max((p for p in pairs if p[1] == lab and p[2][0] != num), default=None)
        match[lab] = {"number": num, "slot": slot[1], "score": round(s, 2), "our_romanisation": form,
                      "runner_up": {"number": runner[2][0], "score": round(runner[0], 2)} if runner else None,
                      # a tie, either way: another entry of his fits this drug as well, or another drug of ours
                      # fits this entry as well (homophones: 秦椒 and 秦艽 are both qin jiao); not used until checked
                      "ambiguous": bool(runner and runner[0] >= s - 0.02) or any(
                          p[2] == slot and p[1] != lab and p[0] >= s - 0.02
                          and len(p[3].split()) >= len(form.split()) for p in pairs)}   # a shorter name inside
                          # his ("ku ts'ao" in "hia ku ts'ao") is no rival
    # ties a person resolved (review/bretschneider_ties.csv): "match" fixes the entry and slot, "none" removes it
    ties = HERE / "review" / "bretschneider_ties.csv"
    if ties.exists():
        import csv
        for r in csv.DictReader(open(ties, encoding="utf-8")):
            lab = r["entry"]
            if r["decision"] == "none":
                match.pop(lab, None)
            elif r["decision"] == "match":
                slot = (int(r["bretschneider_entry"]), int(r["slot"]))
                for other in [k for k, m in match.items() if (m["number"], m.get("slot")) == slot and k != lab]:
                    match.pop(other)                    # the slot belongs to the drug the person chose
                match[lab] = {"number": slot[0], "slot": slot[1], "score": None, "our_romanisation": None,
                              "runner_up": None, "ambiguous": False,
                              "resolved_by": f"tie resolved by a person ({r['by']}): {r['why']}"}
    by_num = {b["number"]: b for b in bret}
    for e in ours:
        m = match.get(e["label"])
        if m:
            m["heading"] = by_num[m["number"]]["heading"]
            pk = by_num[m["number"]]["pen_king_names"]
            m["pen_king_name"] = pk[m["slot"]] if m["slot"] < len(pk) else None
    OUT.write_text(json.dumps({
        "source": ("E. Bretschneider, Botanicon Sinicum, Part III (1895), J. North China Branch Roy. Asiat. Soc. "
                   "n.s. 29; Biodiversity Heritage Library item 23159, OCR; public domain"),
        "note": "Matched by romanisation (the OCR lost the Chinese characters); scores 0-1, with the runner-up.",
        "entries": bret, "matches": match}, ensure_ascii=False, indent=1), encoding="utf-8")

    plants = [e for e in ours if e["kind"] not in ("animal", "mineral")]
    good = [m for m in match.values() if (m["score"] or 1) >= 0.85]
    close = [m for m in match.values() if m["ambiguous"]]
    print(f"Bretschneider: {len(bret)} entries (numbers {bret[0]['number']}-{bret[-1]['number']}), "
          f"{len(pen)} quote the Pen king")
    print(f"Matched: {len(match)} of our {len(ours)} entries ({sum(1 for e in plants if e['label'] in match)} of "
          f"{len(plants)} plant entries) · score >= 0.85: {len(good)} · ambiguous (a tie): {len(close)}")
    print(f"Saved to {OUT.relative_to(ROOT)}")
    if "--show" in sys.argv:
        lab = sys.argv[sys.argv.index("--show") + 1]
        e = next(x for x in ours if x["label"] == lab)
        m = match.get(lab)
        print(f"\n{lab} {e['name']} -> {m}")
        if m:
            print(by_num[m["number"]]["text"][:1500])


if __name__ == "__main__":
    main()
