"""Stage 1: extract the medicinal claims of each herb and map them to MeSH.

Usage (web-chat route, like the description check):
  python3 claims/extract_claims.py --book culpeper --export-web
  ... paste each claims/web/<book>/batch_NN.txt into a NEW chat (Gemini 3.8 Flash, temp 0),
      paste the whole reply into batch_NN.answer.txt ...
  python3 claims/extract_claims.py --book culpeper --import-web "Gemini 3.8 Flash, web chat, temp 0"

One claim format for every book (so a new book only adds its own claims):
  claim_id, book, entry, quote (verbatim, checked by code), translation (non-English books),
  part, preparation, route, claim (modern plain English), relation, kind,
  mesh: [{ui, name, match exact|broad|close}]   ← the shared concept that links books
Texts: Culpeper's "Government and Virtues" section; Dioscorides' whole chapter (Greek), only for
chapters with a plant shown or possible in matching/dioscorides/eligibility.json.
The model proposes MeSH headings by name; code looks each one up in the official MeSH file
(reference_sources/mesh/mesh_index.json.gz, names and entry terms), so no ID can be invented.
Checks on every reply (all recorded, see claims/CLAIMS_METHOD.md):
  1. the quote must be in the author's text, otherwise the claim is dropped
  2. a claim under the wrong entry is reported as a mix-up
  3. every MeSH heading must exist in the official MeSH file; the ID comes from that file
  4. category check: the MeSH branch must suit the claim (a "treats" claim mapped only to an
     anatomy or organism heading, or a magical/astrological claim with a MeSH concept, is flagged)
  5. a fixed random sample of claims is written to claims/<book>/review_sample.csv for a person
     to mark right or wrong (never overwritten once it exists)
Output: claims/<book>/claims.json (+ a summary on screen).
"""
import argparse
import csv
import gzip
import random
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WEB = HERE / "web"
BATCH_SIZE = 10
MESH = ROOT / "reference_sources/mesh/mesh_index.json.gz"
HISTORICAL = HERE / "historical_terms.csv"   # old term -> MeSH, built by map_historical_terms.py
RELATIONS = ["treats", "relieves", "prevents", "promotes", "causes", "other"]
REVIEW_SIZE = 20
REVIEW_SEED = 42
# MeSH tree branches (first letter, or D27 for drug actions), used by the category check
BRANCHES = {"A": "anatomy", "B": "organisms", "C": "diseases", "D": "chemicals and drugs",
            "D27": "drug actions", "E": "techniques", "F": "behaviour and mental disorders",
            "G": "body processes", "H": "disciplines", "I": "society", "J": "technology",
            "K": "humanities", "L": "information", "M": "people", "N": "health care", "V": "publication",
            "Z": "places"}
KINDS = ["medical", "humoral", "astrological", "magical", "cosmetic", "veterinary", "household", "other"]

PROMPT = """You extract the medicinal claims from historical herbal texts, for a knowledge graph.
There are {n} separate entries below. Treat each entry on its own.

{blocks}

For EACH entry, list every claim the author makes about what the plant (or a part or preparation
of it) does or treats. One claim = one effect or one condition, from one statement; split
"it helps the cough and the jaundice" into two claims. For each claim give:
- id: entry id + k + number (e01k01, e01k02 ...)
- quote: a short VERBATIM quote from that entry's text that states the claim{quote_note}
{translation_field}- part: plant part if stated (root, leaf, seed, flower, juice, bark, fruit, whole herb ...), else ""
- preparation: if stated (decoction, in wine, powder, ointment, poultice, syrup ...), else ""
- route: internal | external | inhaled | other | unknown
- claim: the claim in plain modern English (e.g. "expels intestinal worms", "promotes urine")
- relation: one of {relations}
- kind: one of {kinds} (astrological = planets and signs; humoral = hot/cold/dry/moist, choler,
  phlegm, melancholy as qualities; magical = amulets, charms)
- mesh: 0 to 3 MeSH descriptors, each {{"heading": "<exact MeSH descriptor name>", "match": "exact|broad|close"}}.
  Use real MeSH descriptor names, for example: Anthelmintics, Diuretics, Cathartics, Emetics,
  Expectorants, Menstruation-Inducing Agents, Analgesics, Edema, Jaundice, Cough, Gout, Fever,
  Wounds and Injuries, Snake Bites, Dysentery, Toothache, Depressive Disorder, Lactation.
  Map old terms to modern concepts (dropsy -> Edema, the stone -> Urinary Calculi,
  the falling sickness -> Epilepsy, the king's evil -> Tuberculosis, Lymph Node; ague -> Fever).
  exact = same concept; broad = the MeSH heading is broader; close = similar but not the same.
  Leave mesh empty for astrological, humoral-only or magical claims, or when nothing fits.

Answer with JSON only:
{{"entries": [{{"eid": "e01", "claims": [{{"id": "e01k01", "quote": "...",{translation_json} "part": "", "preparation": "",
  "route": "internal", "claim": "...", "relation": "treats", "kind": "medical",
  "mesh": [{{"heading": "...", "match": "exact"}}]}}]}}]}}"""


def load_json(p):
    return json.load(open(p, encoding="utf-8"))


def plain(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s or "") if not unicodedata.combining(c)).lower()
    return re.sub(r"[^\w]+", " ", s).strip()


def quote_ok(q: str, text: str) -> bool:
    """Every fragment (split at "...") must be in the text. Words in [square brackets] are words the
    model supplied to make a fragment readable (a verb shared by several clauses); they are not
    required to be in the text, as in scholarly quotation."""
    def ok(quote):
        frags = [f for f in re.split(r"\.\.\.|…", quote or "") if plain(f)]
        return bool(frags) and all(plain(f) in plain(text) for f in frags)
    return ok(q) or ok(re.sub(r"\[[^\]]*\]", " ... ", q or ""))


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def parse(text: str):
    t = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        t = t[t.index("{"): t.rindex("}") + 1]
    except ValueError:
        return None
    for attempt in (t, re.sub(r",(\s*[\]}])", r"\1", t)):   # strict=False: copied replies can wrap lines inside strings
        try:
            return json.loads(attempt, strict=False)
        except ValueError:
            continue
    return None


def entries(book: str, every: bool = False) -> list:
    """[(key, display name, text)] in a fixed order. every=True: all Dioscorides chapters with text,
    used on import, so a chapter that later loses its plant keeps its claims (unlinked)."""
    if book == "culpeper":
        out = []
        for h in load_json(ROOT / "historical_texts/culpeper/herbs.json")["herbs"]:
            v = (h.get("sections") or {}).get("government_and_virtues")
            if v:
                out.append((h["id"], h["name"], v))
        return out
    elig = load_json(ROOT / "matching/dioscorides/eligibility.json")["herbs"]
    keep = {v["label"] for v in elig.values() if v["shown"] or v["possible"]}
    return [(c["label"], c["headword"] or c["label"], c["text"])
            for c in load_json(ROOT / "historical_texts/dioscorides/chapters.json")["chapters"]
            if (every or c["label"] in keep) and c.get("text")]


def prompt(book: str, group: list) -> str:
    greek = book == "dioscorides"
    author = "Culpeper, The Complete Herbal (1653), section 'Government and Virtues'" if not greek else \
        "Dioscorides, De materia medica (1st century), Greek, Wellmann's edition"
    blocks = [f"=== ENTRY {eid}: {name} ({author}) ===\n{text}" for eid, (key, name, text) in group]
    return PROMPT.format(
        n=len(group), blocks="\n\n".join(blocks), relations=", ".join(RELATIONS), kinds=", ".join(KINDS),
        quote_note=" (in Greek, exactly as written)" if greek else "",
        translation_field="- translation: an English translation of the quote\n" if greek else "",
        translation_json=' "translation": "...",' if greek else "")


def branches(trees: list) -> list:
    out = []
    for t in trees:
        b = "D27" if t.startswith("D27") else t[:1]
        if b not in out:
            out.append(b)
    return out


def category_flags(c: dict, concepts: list) -> list:
    """Check 4: does the MeSH branch suit the claim? Returns reasons; empty = no doubt."""
    flags = []
    if c.get("kind") in ("astrological", "magical") and concepts:
        flags.append(f"{c.get('kind')} claim mapped to a medical concept")
    if not concepts:
        return flags
    found = {b for m in concepts for b in m["branches"]}
    useful = {"C", "F", "G", "D27", "D"}
    if c.get("relation") in ("treats", "relieves", "prevents") and not (found & useful):
        flags.append("treats/relieves/prevents, but every concept is " +
                     " / ".join(BRANCHES.get(b, b) for b in sorted(found)))
    if c.get("relation") == "promotes" and found <= {"C"}:
        flags.append("promotes, but every concept is a disease")
    return flags


def write_review_sample(book: str, out: dict) -> Path:
    """Check 5: a fixed sample for a person to mark. Never overwritten once it exists."""
    path = HERE / book / "review_sample.csv"
    if path.exists():
        return path
    allc = [(e["name"], c) for e in out.values() for c in e["claims"] if c["mesh"]]
    sample = random.Random(REVIEW_SEED).sample(allc, min(REVIEW_SIZE, len(allc)))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["claim_id", "entry", "quote", "translation", "claim", "mesh", "match",
                    "claim_correct (y/n)", "mesh_correct (y/n)", "note"])
        for name, c in sample:
            w.writerow([c["claim_id"], name, c["quote"], c.get("translation") or "", c["claim"],
                        "; ".join(f"{m['ui']} {m['name']}" for m in c["mesh"]),
                        "; ".join(m["match"] or "" for m in c["mesh"]), "", "", ""])
    return path


def export_web(book: str) -> None:
    es = entries(book)
    folder = WEB / book
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for b in range(0, len(es), BATCH_SIZE):
        name = f"batch_{b // BATCH_SIZE + 1:02d}"
        group = [(f"e{i:02d}", e) for i, e in enumerate(es[b:b + BATCH_SIZE], 1)]
        manifest[name] = {eid: e[0] for eid, e in group}
        (folder / f"{name}.txt").write_text(prompt(book, group), encoding="utf-8")
        ans = folder / f"{name}.answer.txt"
        if not ans.exists():
            ans.write_text("", encoding="utf-8")
    (folder / "batches.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    sizes = [len((folder / f"{n}.txt").read_text(encoding="utf-8")) for n in manifest]
    print(f"{book}: {len(es)} entries in {len(manifest)} prompts of up to {BATCH_SIZE} "
          f"(largest {max(sizes):,} characters). Folder: claims/web/{book}/")


def export_new(book: str) -> None:
    """Only entries with no claims yet (e.g. a chapter that newly has a plant after a Stage 2 fix):
    new batches after the existing ones; batches already pasted are left untouched."""
    folder = WEB / book
    manifest = load_json(folder / "batches.json")
    done = set(load_json(ROOT / "claims" / book / "claims.json")["entries"]) | {k for e in manifest.values() for k in e.values()}
    es = [e for e in entries(book) if e[0] not in done]
    if not es:
        print(f"{book}: every entry already has a batch; nothing to export.")
        return
    n = len(manifest)
    for b in range(0, len(es), BATCH_SIZE):
        n += 1
        name = f"batch_{n:02d}"
        group = [(f"e{i:02d}", e) for i, e in enumerate(es[b:b + BATCH_SIZE], 1)]
        manifest[name] = {eid: e[0] for eid, e in group}
        (folder / f"{name}.txt").write_text(prompt(book, group), encoding="utf-8")
        (folder / f"{name}.answer.txt").write_text("", encoding="utf-8")
        print(f"{name}: {len(group)} new entries ({', '.join(e[0] for _, e in group)})")
    (folder / "batches.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")


def import_web(book: str, label: str) -> None:
    mesh = json.load(gzip.open(MESH, "rt", encoding="utf-8"))
    D, L = mesh["descriptors"], mesh["lookup"]
    hist = {}
    if HISTORICAL.exists():                    # used only when the normal MeSH lookup fails
        for r in csv.DictReader(open(HISTORICAL, encoding="utf-8")):
            if r.get("mesh_ui") and r["mesh_ui"] in D:
                hist[norm(r["old_term"])] = r
    texts = {k: (n, t) for k, n, t in entries(book, every=True)}
    folder = WEB / book
    manifest = load_json(folder / "batches.json")
    out, mixups, missing, bad_quotes, unresolved = {}, [], [], [], Counter()
    for bname, eids in manifest.items():
        ans = folder / f"{bname}.answer.txt"
        raw = ans.read_text(encoding="utf-8") if ans.exists() else ""
        if not raw.strip():
            continue
        js = parse(raw)
        if not js:
            print(f"  {bname}: reply is not valid JSON")
            continue
        got = {str(e.get("eid")): e for e in js.get("entries", []) if isinstance(e, dict)}
        for eid, key in eids.items():
            name, text = texts[key]
            e = got.get(eid)
            if not e:
                missing.append(f"{bname}/{eid} {name}")
                continue
            claims = []
            for n, c in enumerate(e.get("claims", []), 1):
                if not isinstance(c, dict):
                    continue
                c = {k: re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else v for k, v in c.items()}
                cid = str(c.get("id", ""))
                if cid and not cid.startswith(eid):
                    mixups.append(f"{bname}/{eid}: {cid}")
                if not quote_ok(c.get("quote", ""), text):
                    bad_quotes.append(f"{name}: {str(c.get('quote'))[:60]}")
                    continue                          # a claim the author never wrote is not kept
                concepts, not_found = [], []
                for m in c.get("mesh") or []:
                    h = (m or {}).get("heading", "")
                    uis = L.get(norm(h), [])
                    ui = next((u for u in uis if norm(D[u]["name"]) == norm(h)), uis[0] if uis else None)
                    if ui:
                        concepts.append({"ui": ui, "name": D[ui]["name"], "match": m.get("match"), "proposed": h,
                                         "branches": branches(D[ui]["trees"])})
                    elif h and norm(h) in hist:
                        r = hist[norm(h)]
                        concepts.append({"ui": r["mesh_ui"], "name": D[r["mesh_ui"]]["name"],
                                         "match": r.get("match") or m.get("match"), "proposed": h,
                                         "via": f"claims/historical_terms.csv ({r['source']})",
                                         "branches": branches(D[r["mesh_ui"]]["trees"])})
                    elif h:
                        unresolved[h] += 1
                        not_found.append(h)
                claims.append({"claim_id": f"{book}:{key}:c{n:02d}", "quote": c.get("quote"),
                               "translation": c.get("translation"), "part": c.get("part"),
                               "preparation": c.get("preparation"), "route": c.get("route"),
                               "claim": c.get("claim"), "relation": c.get("relation"), "kind": c.get("kind"),
                               "mesh": concepts, "mesh_not_found": not_found,
                               "flags": category_flags(c, concepts)})
            out[key] = {"name": name, "batch": bname, "claims": claims}
    path = HERE / book / "claims.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"book": book, "model": f"web: {label}", "mesh": mesh["source"],
                                "method": "claims/CLAIMS_METHOD.md", "entries": out},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    allc = [c for e in out.values() for c in e["claims"]]
    with_mesh = [c for c in allc if c["mesh"]]
    via_hist = sum(1 for c in allc for m in c["mesh"] if m.get("via"))
    print(f"{book}: {len(out)} entries imported · {len(allc)} claims · {len(with_mesh)} with a MeSH concept"
          + (f" ({via_hist} concepts through the historical-terms table)" if via_hist else ""))
    print(f"Entries missing from a reply: {len(missing)} · mix-ups: {len(mixups)} · "
          f"claims dropped (quote not in the text): {len(bad_quotes)}")
    print("Kinds: " + ", ".join(f"{k} {v}" for k, v in Counter(c["kind"] for c in allc).most_common()))
    print("Top MeSH concepts: " + ", ".join(f"{k} {v}" for k, v in
                                           Counter(m["name"] for c in allc for m in c["mesh"]).most_common(15)))
    if unresolved:
        print(f"MeSH headings proposed but not in MeSH ({sum(unresolved.values())}): " +
              ", ".join(f"{k} {v}" for k, v in unresolved.most_common(15)))
    flagged = [c for c in allc if c["flags"]]
    print(f"Category check: {len(flagged)} claims flagged" +
          "".join(f"\n  {c['claim_id']}: {c['claim']} → {', '.join(m['name'] for m in c['mesh'])} ({c['flags'][0]})"
                  for c in flagged[:10]))
    complete = len(out) == sum(len(v) for v in manifest.values())
    if with_mesh and complete:                 # the sample is drawn once, from the whole book
        rs = write_review_sample(book, out)
        print(f"Review sample for a person to mark: {rs.relative_to(ROOT)}")
    elif with_mesh:
        print(f"Review sample: written once every batch is imported ({len(out)} of "
              f"{sum(len(v) for v in manifest.values())} entries so far)")
    print(f"Saved to claims/{book}/claims.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="culpeper", choices=["culpeper", "dioscorides"])
    ap.add_argument("--export-web", action="store_true")
    ap.add_argument("--export-new", action="store_true", help="batches only for entries with no claims yet")
    ap.add_argument("--import-web", metavar="MODEL")
    a = ap.parse_args()
    if a.export_new:
        return export_new(a.book)
    if a.export_web:
        export_web(a.book)
    elif a.import_web:
        import_web(a.book, a.import_web)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
