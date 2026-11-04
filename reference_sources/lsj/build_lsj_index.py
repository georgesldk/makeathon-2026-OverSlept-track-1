"""Build a compact, searchable index of the LSJ Greek-English Lexicon.

Usage:  git clone --depth 1 --filter=blob:none --sparse https://github.com/PerseusDL/lexica /tmp/lexica
        (cd /tmp/lexica && git sparse-checkout set CTS_XML_TEI/perseus/pdllex/grc/lsj)
        python3 reference_sources/lsj/build_lsj_index.py /tmp/lexica/CTS_XML_TEI/perseus/pdllex/grc/lsj

Writes reference_sources/lsj/lsj_index.json.gz: one record per LSJ entry
  {"key": Beta Code headword, "lemma": accent-free Greek, "text": the entry as plain text}

LSJ: H. G. Liddell, R. Scott, H. S. Jones, A Greek-English Lexicon (9th ed., 1940),
machine-readable edition by the Perseus Digital Library, Tufts University (CC BY-SA).
Greek inside entries is in Beta Code (a)/koron = ἄκορον); headwords are converted.
"""
import gzip
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "lsj_index.json.gz"
BETA = dict(zip("abgdezhqiklmncoprstufxyw", "αβγδεζηθικλμνξοπρστυφχψω"))


def beta_plain(key: str) -> str:
    """Beta Code headword -> Greek letters without accents ('a)/koron1' -> 'ακορον')."""
    return "".join(BETA.get(ch, "") for ch in re.sub(r"\d", "", key.lower()))


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not src or not src.is_dir():
        sys.exit(__doc__)
    out = []
    for f in sorted(src.glob("grc.lsj.perseus-eng*.xml")):
        t = f.read_text(encoding="utf-8")
        for m in re.finditer(r'<entryFree[^>]*?key="([^"]+)"[^>]*>(.*?)</entryFree>', t, re.S):
            text = html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))
            out.append({"key": m.group(1), "lemma": beta_plain(m.group(1)),
                        "text": re.sub(r"\s+", " ", text).strip()})
    with gzip.open(OUT, "wt", encoding="utf-8") as g:
        json.dump({"source": "LSJ, A Greek-English Lexicon (1940), Perseus Digital Library, CC BY-SA. "
                             "https://github.com/PerseusDL/lexica", "entries": out}, g, ensure_ascii=False)
    print(f"{len(out)} LSJ entries -> {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
