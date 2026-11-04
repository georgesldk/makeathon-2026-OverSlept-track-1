"""Build a compact, searchable index of Lewis & Short's Latin Dictionary.

Usage:  git clone --depth 1 --filter=blob:none --sparse https://github.com/PerseusDL/lexica /tmp/lexica
        (cd /tmp/lexica && git sparse-checkout set CTS_XML_TEI/perseus/pdllex/lat/ls)
        python3 reference_sources/lewis_short/build_lewis_short_index.py /tmp/lexica/CTS_XML_TEI/perseus/pdllex/lat/ls

Writes reference_sources/lewis_short/lewis_short_index.json.gz: one record per entry
  {"key": headword as in the source, "lemma": lower-case Latin without digits, "text": plain text}

Lewis & Short, A Latin Dictionary (Oxford 1879), machine-readable edition by the
Perseus Digital Library, Tufts University (CC BY-SA).
"""
import gzip
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "lewis_short_index.json.gz"


def lemma(key: str) -> str:
    k = unicodedata.normalize("NFD", re.sub(r"\d", "", key))
    k = "".join(c for c in k if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z]", "", k.replace("j", "i").replace("v", "u"))


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not src or not src.is_dir():
        sys.exit(__doc__)
    out = []
    for f in sorted(src.glob("lat.ls.perseus-eng*.xml")):
        t = f.read_text(encoding="utf-8")
        for m in re.finditer(r'<entryFree[^>]*?key="([^"]+)"[^>]*>(.*?)</entryFree>', t, re.S):
            text = html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))
            out.append({"key": m.group(1), "lemma": lemma(m.group(1)), "text": re.sub(r"\s+", " ", text).strip()})
    with gzip.open(OUT, "wt", encoding="utf-8") as g:
        json.dump({"source": "Lewis & Short, A Latin Dictionary (1879), Perseus Digital Library, CC BY-SA. "
                             "https://github.com/PerseusDL/lexica", "entries": out}, g, ensure_ascii=False)
    print(f"{len(out)} Lewis & Short entries -> {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
