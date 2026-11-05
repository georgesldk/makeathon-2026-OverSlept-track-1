"""Test: can BHL give us plant descriptions for the description check (D rules)?

Usage:  python3 description_sources/bhl/test_bhl.py

Needs BHL_API_KEY in .env (free key: https://www.biodiversitylibrary.org/getapikey.aspx)
and the WCVP download (for synonyms). For 5 test plants:
  1. names: the accepted name plus its synonyms from WCVP, oldest first, because old
     floras use old names (Boissier may file a plant under a name we no longer use)
  2. pages: every BHL page where one of those names was found, kept only if the book
     looks like a flora or botany book; regional floras first
  3. scoring: each shortlisted page's OCR text is scored: + the name as a heading
     (followed by an author or a number), + description words in English or Latin
     (leaves/folia, stem/caulis, flowers/flores, root/radix ...); - pages that are
     indexes or lists (many names, few description words)
     A name right after "quam", "ut in", "than", "as in" is a comparison and is skipped:
     the page describes another plant. Pages with fewer than 5 description words are dropped.
  4. only hits where the name is an entry heading count (a name in running text, a key or
     a story is skipped; common OCR misreadings like "Zinn." for "Linn." are undone
     first); the description stops where the next plant's entry begins
  5. the best 2 pages are kept, at most one per book; an entry near the bottom of a page
     is read on into the next page; if nothing is usable, 8 more pages are read
Writes description_sources/bhl/test_results.json and prints the best passages.
Every reply is cached in description_sources/bhl/cache/, so nothing is asked twice.
"""
import csv
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CACHE = HERE / "cache"
WCVP = ROOT / "scientific_name_sources" / "wcvp" / "data" / "wcvp_names.csv"
OUT = HERE / "test_results.json"
API = "https://www.biodiversitylibrary.org/api3"
PLANTS = {"Solanum dulcamara": "britain", "Stellaria media": "britain", "Inula helenium": "britain",
          "Mandragora officinarum": "mediterranean", "Iris pseudacorus": "mediterranean"}
REGIONAL = {"britain": ["british flora", "british botany", "british islands", "english botany", "flora of the british",
                        "manual of british", "student's flora", "handbook of the british", "flora medica"],
            "mediterranean": ["flora orientalis", "flora graeca", "florae graecae", "flora of syria", "flora italica",
                              "flora aegyptiaca", "flora of cyprus", "conspectus florae", "flora of palestine",
                              "flore de france", "flora hispanica", "flora europae"]}
BOTANY = ["flora", "flore", "botany", "botanik", "plantarum", "plants", "herbal", "manual", "handbook",
          "prodromus", "species", "materia medica", "pharmacograph"]
DESC_WORDS = r"\b(leaves|leaf|stem|stems|flowers?|petals?|calyx|corolla|root|rootstock|berr(?:y|ies)|fruit|seeds?|" \
             r"hairy|downy|glabrous|ovate|lanceolate|cordate|folia|folium|caulis|caule|flores|flos|radix|" \
             r"bacca|semina|capsula|petala|perennis|annua)\b"
MAX_SYNONYMS = 6
SHORTLIST = 8
KEEP = 2
MIN_DESC = 5                                  # fewer description words: a list of names, not a description
COMPARISON = re.compile(r"(?:\bquam|\but in|\bthan|\bas in|\blike|\bcf\.?|\bsimilis|\baffinis)[\s,.]*$", re.I)


def key() -> str:
    for line in open(ROOT / ".env", encoding="utf-8"):
        if line.startswith("BHL_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("BHL_API_KEY not found in .env")


def ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CTX = ctx()
CALLS = [0]


def call(op: str, **params) -> dict:
    CACHE.mkdir(exist_ok=True)
    name = re.sub(r"[^\w]+", "_", f"{op}_{'_'.join(str(v) for v in params.values())}")[:120] + ".json"
    path = CACHE / name
    if path.exists():
        return json.load(open(path, encoding="utf-8"))
    q = urllib.parse.urlencode({"op": op, **params, "format": "json", "apikey": key()})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "EthnoHack-OverSlept/0.1"})
    with urllib.request.urlopen(req, timeout=90, context=CTX) as r:
        data = json.load(r)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    CALLS[0] += 1
    time.sleep(0.5)
    return data


def synonyms(names: list[str]) -> dict[str, list[str]]:
    """Accepted name -> its species-rank synonyms in WCVP, oldest first."""
    rows = list(csv.DictReader(open(WCVP, encoding="utf-8", newline=""), delimiter="|", quoting=csv.QUOTE_NONE))
    acc = {r["taxon_name"]: r["plant_name_id"] for r in rows if r["taxon_status"] == "Accepted" and r["taxon_name"] in names}
    out = {n: [] for n in names}
    for r in rows:
        for n, pid in acc.items():
            if r["accepted_plant_name_id"] == pid and r["taxon_name"] != n and r["taxon_rank"] == "Species":
                year = re.search(r"\d{4}", r["first_published"] or "")
                out[n].append((int(year.group()) if year else 9999, r["taxon_name"]))
    return {n: [s for _, s in sorted(set(v))][:MAX_SYNONYMS] for n, v in out.items()}


def pages_for(name: str) -> list[dict]:
    data = call("GetNameMetadata", name=name)
    out = []
    for n in data.get("Result") or []:
        for t in n.get("Titles") or []:
            title = t.get("FullTitle") or t.get("ShortTitle") or ""
            for it in t.get("Items") or []:
                pages = it.get("Pages") or []
                for i, p in enumerate(pages):
                    out.append({"title": title, "year": it.get("Year") or t.get("PublicationDate"),
                                "page_id": p.get("PageID"), "url": p.get("PageUrl"), "name": name,
                                "item_id": it.get("ItemID")})
    return out


def ocr(page_id) -> str:
    meta = call("GetPageMetadata", pageid=page_id, ocr="t", names="f")
    res = meta.get("Result")
    res = res[0] if isinstance(res, list) and res else res or {}
    return re.sub(r"\s+", " ", res.get("OcrText") or "")


HEADING = re.compile(r"\s*[,.;]?\s*(?:(?:[A-Z][a-z]*\.?\s*){0,3}(?:\(|L\.|Linn|\d|[A-Z]\.)"
                     r"|[A-Z][a-z]+[,.])")      # "(Wither.)", "Linn.", "L.", "C. B.", or ", Elecampane."
OCR_FIXES = [(r"\b(?:Zinn|Zina|Linu|Liun|Lmn|Iinn|Linri)\.", "Linn."), (r"\bPirate\b", "Plate"),
             (r"\bPuate\b", "Plate"), (r"\bWith,", "With."), (r"\s+([,.;])", r"\1"), (r"(\w)- (\w)", r"\1\2")]


def clean(text: str) -> str:
    """Undo common OCR misreadings that hide an entry heading ("Zinn." for "Linn.")
    and join words split at line ends ("droop- ing")."""
    for a, b in OCR_FIXES:
        text = re.sub(a, b, text)
    return text


NEXT_ENTRY = re.compile(r"SPECIES [IVXL]+|\b[A-Z]{4,} [A-Z]{4,}\b")


def score(text: str, names: list[str], extra: str = "") -> tuple[int, int, str, int]:
    """(score, position of the best name hit, why, description words).
    Only hits where the name is an entry heading count; a name mentioned in running text
    (a key, a story, a comparison) does not. `extra` is the next page, for entries that
    start near the bottom of this one."""
    best, pos, why, best_desc = -99, 0, "", 0
    text, extra = clean(text), clean(extra)
    full = text + " " + extra
    binomials = len(re.findall(r"\b[A-Z][a-z]+ [a-z]{4,}\b", text))
    for n in names:
        g, sp = n.split()[:2]
        for m in re.finditer(rf"{g}\s+{sp}|{g[0]}\.\s*{sp}", text, re.I):
            if COMPARISON.search(text[max(0, m.start() - 15): m.start()]):
                continue                          # "... quam Mandragora officinarum": another plant is described
            after = full[m.end(): m.end() + 900]
            if not HEADING.match(after):
                continue                          # running text or a running page header, not an entry
            nxt = NEXT_ENTRY.search(after, 20)
            if nxt:
                after = after[: nxt.start()]      # stop where the next plant's entry begins
            desc = len(re.findall(DESC_WORDS, after, re.I))
            s = desc + 4 + (3 if m.group().isupper() else 0)
            if binomials > 40 and desc < 8:
                s -= 10                           # an index or a list of names
            if desc < MIN_DESC:
                s -= 10
            if s > best:
                best, pos, best_desc = s, m.start(), desc
                why = f"{desc} description words, heading{', list page' if binomials > 40 else ''}"
    return best, pos, why, best_desc


def score_page(p: dict, names: list[str]) -> dict | None:
    try:
        text = ocr(p["page_id"])
    except Exception as e:
        print(f"  ! page {p['page_id']}: {e}")
        return None
    extra = ""
    late = [m.start() for n in names for m in re.finditer(n.split()[0], text, re.I) if m.start() > len(text) * 0.7]
    if late:                                      # an entry may start near the bottom: read the next page too
        try:
            extra = ocr(int(p["page_id"]) + 1)
        except Exception:
            pass
    s, pos, why, desc = score(text, names, extra)
    full = clean(text) + " " + clean(extra)
    return {**p, "score": s, "why": why, "desc_words": desc, "passage": full[max(0, pos - 50): pos + 1500],
            "next_page_added": bool(extra)}


def pick(scored: list[dict]) -> list[dict]:
    keep, books = [], set()
    for s in sorted(scored, key=lambda x: -x["score"]):   # one page per book (several scans of one book are common)
        book = re.sub(r"\W+", " ", s["title"].lower()).strip()
        if s["score"] > 0 and s["desc_words"] >= MIN_DESC and book not in books:
            keep.append(s)
            books.add(book)
        if len(keep) == KEEP:
            break
    return keep


def main() -> None:
    syn = synonyms(list(PLANTS))
    results = {}
    for name, region in PLANTS.items():
        names = [name] + syn[name]
        print(f"\n{'=' * 90}\n{name}  · synonyms searched: {', '.join(syn[name]) or 'none'}\n{'=' * 90}")
        pages = []
        for n in names:
            try:
                pages += pages_for(n)
            except Exception as e:
                print(f"  ! {n}: {e}")
        botany = [p for p in pages if any(w in p["title"].lower() for w in BOTANY + REGIONAL[region])]
        botany.sort(key=lambda p: (not any(w in p["title"].lower() for w in REGIONAL[region]),
                                   not any(w in p["title"].lower() for w in REGIONAL["britain"] + REGIONAL["mediterranean"]),
                                   str(p["year"] or "")))
        seen, short = set(), []
        for p in botany:                          # at most 2 pages per book
            if sum(1 for q in short if q["title"] == p["title"]) < 2 and p["page_id"] not in seen:
                short.append(p)
                seen.add(p["page_id"])
            if len(short) >= 2 * SHORTLIST:
                break
        scored = [x for p in short[:SHORTLIST] if (x := score_page(p, names))]
        keep = pick(scored)
        rounds = 1
        if not keep and len(short) > SHORTLIST:   # nothing usable: try the next pages, only for this plant
            scored += [x for p in short[SHORTLIST:] if (x := score_page(p, names))]
            keep, rounds = pick(scored), 2
        print(f"  {len(pages)} pages found, {len(botany)} in botany books, {len(scored)} pages read ({rounds} round{'s' * (rounds > 1)})")
        for k in keep:
            print(f"\n  [{k['score']}] {k['title'][:70]} ({k['year']}) as '{k['name']}'  · {k['why']}"
                  f"{', + next page' if k['next_page_added'] else ''}")
            print(f"  {k['url']}")
            print("  " + k["passage"][:700])
        if not keep:
            print("  no page looks like a description")
        results[name] = {"region": region, "names_searched": names, "kept": keep,
                         "shortlist": [{x: s[x] for x in ("title", "year", "url", "score", "why")} for s in scored]}
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{CALLS[0]} new BHL calls (the rest came from the cache). Saved to description_sources/bhl/{OUT.name}\n")


if __name__ == "__main__":
    main()
