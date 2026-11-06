"""Split Sun Xingyan's Shennong Bencao Jing (神農本草經, 1799) into one record per drug.

Usage:  python3 historical_texts/shennong/extract_sun.py
        python3 historical_texts/shennong/extract_sun.py --show 車前子     # one entry

Reads  historical_texts/shennong/source/wikisource/神農本草經 (孫星衍).json   the main text
       historical_texts/shennong/source/wikisource/神農本草經.json           cross-check only
       (both from Chinese Wikisource via fetch_wikisource.py; CC BY-SA, underlying texts public domain)
Writes historical_texts/shennong/entries.json

Sun Xingyan and Sun Fengyi rebuilt the lost Han classic (1st-2nd c. AD) from later quotations. Each
entry keeps its layers apart, and so does every record here:
  classic     the classic's own text: taste and nature (味甘，微寒), uses (主 ...), effects of long use
              (久服 ...), other names (一名 ...), habitat (生山谷); Sun's source notes in brackets
              （《御覽》引 ...） are taken out of it and kept in "sun_notes"
  wu_pu       《吳普》曰: Wu Pu's materia medica (3rd c.), as quoted later
  mingyi      《名醫》曰: Records of Famous Physicians (Mingyi bielu, c. 3rd-5th c.): names, places, harvest
  commentary  案 / 按: Sun's own notes (Shuowen, Erya, Guo Pu ...): often a description of the plant
Only "classic" is the Shennong text; the other layers are later and are labelled as such.
The grade is Sun's. Reconstructions differ on grades: the plain version puts 55 entries in another
grade, recorded in plain_version_match.grade, not corrected.

Repairs, each recorded in the record's "repairs":
  * headings missing in the Wikisource text (two drugs under one heading, e.g. 石膽 inside 滑石): a
    second classic paragraph ("味 ...") after the first one's notes starts a new entry; its name comes
    from its Wu Pu or Famous Physicians note, or from the matching entry of the plain version
  * characters missing in Unicode are blanks (　) or "KT" in the source: counted, never guessed
  * the appendix (附：諸藥制使, drug compatibilities) and the Wu Pu appendix are not drugs: skipped
The plain one-page version (神農本草經, no edition named, not proofread) is used only to cross-check
each entry and to take its kind (玉石 minerals, 草 herbs, 木 trees, 果菜 fruit and vegetables, 米穀
grains, 蟲獸 animals); the match and its score are recorded.
"""
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "source" / "wikisource"
SUN = SRC / "神農本草經 (孫星衍).json"
PLAIN = SRC / "神農本草經.json"
OUT = HERE / "entries.json"
GRADES = {"卷一·上經": ("upper", 1), "卷二·中經": ("middle", 2), "卷三·下經": ("lower", 3)}
KINDS = {"玉石": "mineral", "草": "herb", "木": "tree", "果菜": "fruit or vegetable", "米穀": "grain",
         "蟲獸": "animal"}
MISSING = re.compile(r"　|KT")
TASTES = "甘苦辛酸鹹咸澀"
NOTE = re.compile(r"（[^（）]*）")
LAYER = re.compile(r"^(《吳普(?:本草)?》|《名醫》|案|按)")


def plain_entries():
    """The plain version: name, grade, kind and text of each entry, for cross-checking."""
    w = json.load(open(PLAIN, encoding="utf-8"))["wikitext"]
    out, kind = [], None
    for line in w.split("\n"):
        h = re.match(r"^===\s*(\S+?)部(上|中|下)品\s*===", line)
        if h:
            kind = (KINDS.get(h.group(1)), {"上": "upper", "中": "middle", "下": "lower"}[h.group(2)])
            continue
        m = re.match(r"^'{2,3}(.+?)'{3}\s*(.*)$", line.strip())   # one line in the source has '' not '''
        if m and kind:
            out.append({"name": m.group(1), "kind": kind[0], "grade": kind[1], "text": m.group(2)})
    return out


def norm(t: str) -> str:
    t = NOTE.sub("", t)
    t = t.replace("主治", "主").replace("砂", "沙").replace("消", "硝")
    return re.sub(r"[，。、；：\s　]", "", t)


def match_plain(classic: str, name: str | None, grade: str, plain: list) -> dict | None:
    """Best plain-version entry for this classic text: same name first, else the most similar text."""
    best = None
    for p in plain:
        s = SequenceMatcher(None, norm(classic)[:60], norm(p["text"])[:60]).ratio()
        if name and norm(p["name"]) == norm(name):
            s += 0.3
        if p["grade"] == grade:
            s += 0.05
        if best is None or s > best[0]:
            best = (s, p)
    if best and best[0] >= 0.55:
        # below 0.7 the pairing is often wrong (徐長卿 -> 赤箭): kept as "unconfirmed", its kind not used
        return {"name": best[1]["name"], "kind": best[1]["kind"], "grade": best[1]["grade"],
                "score": round(min(best[0], 1.0), 2), "confirmed": best[0] >= 0.7}
    return None


def fields(classic_raw: str) -> dict:
    notes = NOTE.findall(classic_raw)
    t = NOTE.sub("", classic_raw).strip()
    # "味甘，微寒。" "味苦寒。" "味辛，溫，主 ..." "味苦澀。" "味平。": tastes, then the nature, up to 主 or 。
    seg = re.match(r"^味([^主。]*)", t)
    seg = seg.group(1) if seg else ""
    tastes = "".join(c for c in seg if c in TASTES) or None
    nature = re.sub(r"[，、,\s]|無毒|有毒", "", "".join(c for c in seg if c not in TASTES)) or None
    uses = re.search(r"主(.+?)(?=久服|一名|生[^。]{0,8}。?$|$)", t)
    long_use = re.search(r"久服[，,]?(.+?)(?=一名|生[^。]{0,8}。?$|$)", t)
    # the habitat is the last 生 clause naming a place ("生子" bears offspring, "生齒" grows teeth: not places)
    habitat = [re.split(r"（", h)[0] for h in re.findall(r"生([^，。；生]{1,10}?)(?:。|$)", t)
               if re.search(r"[山谷澤野土田池川海陵阪道石邱]", h)]
    return {
        "text": t,
        "taste": tastes,
        "nature": nature,
        "toxicity": "有毒" if "有毒" in t else ("無毒" if "無毒" in t else None),
        "uses": uses.group(1).strip(" ，。") if uses else None,
        "long_use": long_use.group(1).strip(" ，。") if long_use else None,
        "other_names": names_in(t),
        "habitat": habitat[-1] if habitat else None,
        "sun_notes": [n.strip("（）") for n in notes],
        "missing_characters": len(MISSING.findall(t)),
    }


def names_in(t: str) -> list:
    """一名 X; a name made only of missing characters (blanks in the source) is left out."""
    return [n for n in re.findall(r"一名([^，。；（]+)", t) if MISSING.sub("", n).strip()]


def layer_names(paras: list, prefix: str) -> list:
    return [n for p in paras if p.startswith(prefix) for n in names_in(NOTE.sub("", p))]


def cut_runon(classic_raw: str):
    """A later layer that runs into the classic text in the source ("增志《名醫》曰：生巴郡"): the classic has
    no 《 or 案： outside Sun's bracketed notes, so the first one starts the later layer."""
    masked = NOTE.sub(lambda m: "＿" * len(m.group()), classic_raw)
    m = re.search(r"《|案：|按：", masked)
    if not m:
        return classic_raw, None
    return classic_raw[:m.start()], classic_raw[m.start():]


def main() -> None:
    w = json.load(open(SUN, encoding="utf-8"))
    plain = plain_entries()
    parts = re.split(r"^(=+)\s*([^=\n]+?)\s*=+\s*$", w["wikitext"], flags=re.M)
    raw, grade = [], None
    for i in range(1, len(parts), 3):
        level, title, body = parts[i], parts[i + 1], parts[i + 2]
        if level == "=":
            grade = GRADES.get(title.strip())
            continue
        if not grade:                                     # prefaces and the two appendices
            continue
        paras = [p.strip() for p in body.split("\n") if p.strip()]
        # split where a second classic paragraph ("味 ...") follows notes: a heading missing in the source
        groups, cur = [], []
        for p in paras:
            if p.startswith("味") and any(LAYER.match(x) for x in cur):
                groups.append(cur)
                cur = []
            cur.append(p)
        groups.append(cur)
        for n, g in enumerate(groups):
            raw.append({"heading": title.strip() if n == 0 else None, "grade": grade, "paras": g,
                        "split_from": None if n == 0 else title.strip()})

    entries, per_grade = [], Counter()
    for r in raw:
        g = r["paras"]
        lead = [p for p in g if p.startswith("（") and not p.startswith("（《") and g.index(p) == 0]
        body = [p for p in g if p not in lead]
        classic_paras = []
        for p in body:                                    # the classic: up to the first later layer
            if LAYER.match(p):
                break
            classic_paras.append(p)
        later = body[len(classic_paras):]
        classic_raw = "".join(classic_paras)
        repairs = []
        classic_raw, runon = cut_runon(classic_raw)
        if runon:
            later = [runon] + later
            repairs.append("a later layer ran into the classic text in the source: cut at " + runon[:6])
        name, name_from = r["heading"], "heading"
        if not name:
            wu = next((p for p in later if p.startswith("《吳普")), None)
            m = re.match(r"《吳普(?:本草)?》曰[:：]\s*([^，。,]{1,6})[，,]", wu or "")
            if m:
                name, name_from = m.group(1), "Wu Pu note"
            repairs.append(f"heading missing in the source: split from {r['split_from']}")
        if classic_raw and not classic_raw.startswith("味"):
            repairs.append("classic text does not start with 味 (taste): damaged or partial in the source")
        f = fields(classic_raw)
        pm = match_plain(classic_raw, name, r["grade"][0], plain)
        if not name and pm and pm["confirmed"]:
            name, name_from = pm["name"], "plain version (text match)"
        if f["missing_characters"]:
            repairs.append(f"{f['missing_characters']} character(s) missing in Unicode (blank or KT in the source)")
        per_grade[r["grade"][1]] += 1
        num = per_grade[r["grade"][1]]
        entries.append({
            "id": f"shennong-{r['grade'][1]}-{num}", "label": f"{r['grade'][1]}.{num}",
            "name": name, "name_from": name_from, "grade": r["grade"][0],
            "kind": pm["kind"] if pm and pm["confirmed"] else None, "plain_version_match": pm,
            "classic": f,
            "wu_pu": [p for p in later if p.startswith("《吳普")],
            "mingyi": [p for p in later if p.startswith("《名醫》")],
            "commentary": [p for p in later if not (p.startswith("《吳普") or p.startswith("《名醫》"))],
            "heading_note": [p.strip("（）") for p in lead],
            "other_names_by_layer": {"classic": f["other_names"], "wu_pu": layer_names(later, "《吳普"),
                                     "mingyi": layer_names(later, "《名醫》")},
            "repairs": repairs})

    meta = {"title": "神農本草經 (Shennong Bencao Jing)", "edition": "Sun Xingyan and Sun Fengyi (1799)",
            "source": "Chinese Wikisource, " + w["url"], "revision": w["revid"], "revision_time": w["timestamp"],
            "licence": w["licence"],
            "note": ("The Han classic is lost: this is a Qing reconstruction. Only 'classic' is the Shennong "
                     "text; wu_pu, mingyi and commentary are later layers. 'kind' comes from the plain "
                     "Wikisource version (no edition named), matched by text.")}
    OUT.write_text(json.dumps({**meta, "entries": entries}, ensure_ascii=False, indent=1), encoding="utf-8")

    kinds = Counter(e["kind"] or "unmatched" for e in entries)
    print(f"{len(entries)} entries · by grade {dict(Counter(e['grade'] for e in entries))}")
    print(f"  kind (from the plain version): {dict(kinds)}")
    print(f"  split where a heading was missing: {sum(1 for e in entries if e['name_from'] != 'heading')} "
          f"(names from Wu Pu {sum(e['name_from'] == 'Wu Pu note' for e in entries)}, plain version "
          f"{sum(e['name_from'].startswith('plain') for e in entries)}, none {sum(not e['name'] for e in entries)})")
    print(f"  with uses (主 ...): {sum(bool(e['classic']['uses']) for e in entries)} · other names: "
          f"{sum(bool(e['classic']['other_names']) for e in entries)} · habitat: "
          f"{sum(bool(e['classic']['habitat']) for e in entries)} · damaged start: "
          f"{sum(any('does not start' in x for x in e['repairs']) for e in entries)} · missing characters: "
          f"{sum(bool(e['classic']['missing_characters']) for e in entries)} entries")
    pmc = [e["plain_version_match"] for e in entries if e["plain_version_match"]]
    print(f"  plain-version cross-check: confirmed {sum(m['confirmed'] for m in pmc)}, unconfirmed "
          f"{sum(not m['confirmed'] for m in pmc)}, none {len(entries) - len(pmc)} · other grade there: "
          f"{sum(1 for e in entries if e['plain_version_match'] and e['plain_version_match']['confirmed'] and e['plain_version_match']['grade'] != e['grade'])}")
    print(f"Saved to {OUT.relative_to(HERE.parent.parent)}")
    if "--show" in sys.argv:
        want = sys.argv[sys.argv.index("--show") + 1]
        for e in entries:
            if e["name"] == want or e["label"] == want:
                print(json.dumps(e, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
