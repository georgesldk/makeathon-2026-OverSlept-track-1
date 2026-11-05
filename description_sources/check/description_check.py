"""AI 2, botanical validation: does each candidate match what the author describes? (rule D)

Usage:
  python3 description_sources/check/description_check.py --book culpeper --limit 50 --dry-run   # show one prompt, no calls
  python3 description_sources/check/description_check.py --book culpeper --limit 50              # 50 herbs, 50 calls
  options: --model gemini-3.5-flash (default: gemma-4-31b-it, the model closest to the experts
           in description_sources/paper_test/RESULTS.md)

A new step on top of the pipeline; it changes no existing file. It reads:
  the author's text   Culpeper: description + place + time sections; Dioscorides: the chapter (Greek)
  the candidates      matching/<book>/geography.json: top 3 species + the first that fits geography
                      (the same choice as description_sources/targets.py)
  modern descriptions description_sources/bhl/<book>/bhl.json (historical floras) and
                      description_sources/wikipedia/<book>/wikipedia.json (WEAK)
One call per herb, all its candidates in it. The model:
  1. lists the author's details, each with a verbatim quote (code checks the quote is in the text),
  2. scores each detail per candidate: good / partial / no / absent, naming the source it used,
  3. says whether each BHL passage really describes that candidate (catches wrong pages).
Code then computes, as in Lardos et al. 2024 and the paper test: points (good +2, partial +1,
no -2, absent 0), mean per feature group, congruence = positive groups - negative groups,
verdict strong >= 5, moderate 3-4, weak <= 2. Details scored only from Wikipedia are counted
separately: a candidate supported by Wikipedia alone cannot be called strong (rule D7).
Herbs the author does not describe are skipped (no call). Every reply is cached.

Web-chat route (no API): prompts of 15 herbs each, pasted into a chat by hand.
  python3 description_sources/check/description_check.py --book culpeper --export-web      # write the prompts
  ... paste each web/<book>/batch_NN.txt into a NEW chat, paste the reply into batch_NN.answer.txt ...
  python3 description_sources/check/description_check.py --book culpeper --import-web "Gemini 3.8 Flash, web chat, temp 0"
The batches are fixed in web/<book>/batches.json, so importing always matches the prompts.
Code checks that every answer sits under its own herb and candidate (mix-ups are counted).
Output: description_sources/check/<book>/description_check.json (+ a short summary on screen).
"""
import argparse
import datetime as dt
import json
import random
import re
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
from targets import strip_authors, WIKI_TOP

CACHE = HERE / "cache"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemma-4-31b-it"
SEED = 42
BHL_CHARS, WIKI_CHARS = 1500, 1800
WAITS = [10, 30, 60, 120]
POINTS = {"good": 2, "partial": 1, "no": -2, "absent": 0}
FEATURES = ["habit", "height", "stem", "leaf", "flower", "fruit", "seed", "root", "smell", "taste",
            "habitat", "flowering time"]

PROMPT = """You check which candidate plant matches a historical plant description, detail by detail,
using the method of Lardos et al. 2024 (J Ethnopharmacol 322:117622).

AUTHOR'S TEXT ({author}, {herb}):
{text}

CANDIDATES AND THEIR MODERN DESCRIPTIONS:
{candidates}

Steps:
1. List the author's botanical details (only what he says about this plant itself: habit, height,
   stem, leaf, flower, fruit, seed, root, smell, taste, habitat, flowering time). For each, copy a
   short verbatim quote from the author's text. Skip medicinal uses. Comparisons with everyday
   things ("like a grape seed") count; comparisons with another named plant only if he describes
   the feature, not merely names the plant.
2. For each candidate and each detail, score:
   good = the descriptions agree; partial = partly agree, or one is vaguer but compatible;
   no = they contradict; absent = the candidate's descriptions say nothing about it.
   Name the source you used: "bhl" or "wikipedia" (or "none" when absent).
   Judge botanical sense, not wording; old descriptions are vague. Do not use your own knowledge
   of which plant it is, only the descriptions given.
3. For each BHL passage, say whether it really describes that candidate (a passage may be about a
   neighbouring species): "yes", "partly" or "no".

Answer with JSON only:
{{"details": [{{"id": "d1", "feature": "<one of: {features}>", "quote": "<verbatim>"}}],
  "candidates": [{{"cid": "<cid>", "bhl_passages": [{{"pid": "<pid>", "describes_candidate": "yes|partly|no"}}],
                   "scores": [{{"id": "d1", "label": "good|partial|no|absent", "source": "bhl|wikipedia|none",
                               "reason": "<max 12 words>"}}]}}]}}"""


PROMPT_BATCH = """You check, for several herbs, which candidate plant matches each historical plant description,
detail by detail, using the method of Lardos et al. 2024 (J Ethnopharmacol 322:117622).
There are {n} separate herbs below. Treat each herb on its own: compare it only with its own candidates.

{blocks}

For EACH herb:
1. List the author's botanical details (only what he says about this plant itself: habit, height,
   stem, leaf, flower, fruit, seed, root, smell, taste, habitat, flowering time). For each, copy a
   short verbatim quote from that herb's author's text. Skip medicinal uses. Comparisons with
   everyday things ("like a grape seed") count; comparisons with another named plant only if he
   describes the feature, not merely names the plant.
2. For each of its candidates and each detail, score:
   good = the descriptions agree; partial = partly agree, or one is vaguer but compatible;
   no = they contradict; absent = the candidate's descriptions say nothing about it.
   Name the source you used: "bhl" or "wikipedia" (or "none" when absent).
   Judge botanical sense, not wording; old descriptions are vague. Do not use your own knowledge
   of which plant it is, only the descriptions given.
3. For each BHL passage, say whether it really describes that candidate (a passage may be about a
   neighbouring species): "yes", "partly" or "no".

Answer with JSON only, one entry per herb, using the ids given (herb ids like h01, candidate ids like
h01c1, passage ids like h01c1p1; number details h01d1, h01d2 ...):
{{"herbs": [{{"hid": "h01",
  "details": [{{"id": "h01d1", "feature": "<one of: {features}>", "quote": "<verbatim>"}}],
  "candidates": [{{"cid": "h01c1", "bhl_passages": [{{"pid": "h01c1p1", "describes_candidate": "yes|partly|no"}}],
                  "scores": [{{"id": "h01d1", "label": "good|partial|no|absent", "source": "bhl|wikipedia|none",
                              "reason": "<max 8 words>"}}]}}]}}]}}"""
WEB = HERE / "web"
BATCH_SIZE = 15


# ---------- inputs ----------
def load_json(p):
    return json.load(open(p, encoding="utf-8"))


def author_texts(book: str) -> dict:
    if book == "culpeper":
        out = {}
        for h in load_json(ROOT / "historical_texts/culpeper/herbs.json")["herbs"]:
            s = h.get("sections") or {}
            if not s.get("description"):
                continue                                   # nothing to compare: skipped, no call
            parts = [f"Description: {s['description']}"]
            for k in ("place", "time", "place_and_time"):
                if s.get(k):
                    parts.append(f"{k.replace('_', ' ').capitalize()}: {s[k]}")
            out[h["name"]] = "\n".join(parts)
        return out
    return {c["label"]: c["text"] for c in load_json(ROOT / "historical_texts/dioscorides/chapters.json")["chapters"]
            if c.get("text")}


def candidates(h: dict) -> list:
    cands = [c for c in h["candidates"] if c["rank"] == "species" and not c["geography"].startswith("impossible")]
    fits = h.get("first_candidate_that_fits")
    return [c for i, c in enumerate(cands) if i < WIKI_TOP or c["accepted_name"] == fits]


def build(book: str) -> list:
    geo = load_json(ROOT / "matching" / book / "geography.json")["herbs"]
    bhl = load_json(ROOT / "description_sources/bhl" / book / "bhl.json")["species"]
    wiki = load_json(ROOT / "description_sources/wikipedia" / book / "wikipedia.json")["species"]
    texts = author_texts(book)
    herbs = []
    for h in geo.values():
        key = h.get("label") or h["name"]
        if key not in texts:
            continue
        cs = []
        for i, c in enumerate(candidates(h), 1):
            name = strip_authors(c["accepted_name"])
            b = [k for k in (bhl.get(name) or {}).get("kept", [])]
            w = wiki.get(name) or {}
            cs.append({"cid": f"c{i}", "accepted_name": c["accepted_name"], "name": name, "geography": c["geography"],
                       "bhl": [{"pid": f"c{i}p{j}", "title": x["title"], "year": x["year"], "url": x["url"],
                                "text": x["passage"][:BHL_CHARS]} for j, x in enumerate(b, 1)],
                       "wikipedia": {"url": w.get("url"), "section": w.get("section"),
                                     "text": (w.get("text") or "")[:WIKI_CHARS]} if w.get("found") else None})
        cs = [c for c in cs if c["bhl"] or c["wikipedia"]]
        if cs:
            herbs.append({"herb": key, "name": h["name"], "text": texts[key], "candidates": cs})
    return herbs


def prompt(book: str, h: dict) -> str:
    blocks = []
    for c in h["candidates"]:
        lines = [f"### {c['cid']}: {c['name']}"]
        for p in c["bhl"]:
            lines.append(f"[bhl {p['pid']}] {p['title'][:80]} ({p['year']}), OCR text:\n{p['text']}")
        if c["wikipedia"]:
            lines.append(f"[wikipedia] {c['wikipedia']['text']}")
        blocks.append("\n".join(lines))
    author = "Culpeper, The Complete Herbal, 1653" if book == "culpeper" else \
        "Dioscorides, De materia medica, Greek (Wellmann)"
    return PROMPT.format(author=author, herb=h["name"], text=h["text"], candidates="\n\n".join(blocks),
                         features=", ".join(FEATURES))


def with_ids(h: dict, hid: str) -> dict:
    """The herb with batch-wide ids (h01c1, h01c1p1), so answers can be checked for mix-ups."""
    cs = []
    for c in h["candidates"]:
        cid = hid + c["cid"]
        cs.append({**c, "cid": cid, "bhl": [{**p, "pid": cid + p["pid"][len(c["cid"]):]} for p in c["bhl"]]})
    return {**h, "hid": hid, "candidates": cs}


def candidate_blocks(cands: list) -> str:
    blocks = []
    for c in cands:
        lines = [f"### {c['cid']}: {c['name']}"]
        for p in c["bhl"]:
            lines.append(f"[bhl {p['pid']}] {p['title'][:80]} ({p['year']}), OCR text:\n{p['text']}")
        if c["wikipedia"]:
            lines.append(f"[wikipedia] {c['wikipedia']['text']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def prompt_batch(book: str, herbs: list) -> str:
    author = "Culpeper, The Complete Herbal, 1653" if book == "culpeper" else \
        "Dioscorides, De materia medica, Greek (Wellmann)"
    blocks = [f"=== HERB {h['hid']}: {h['name']} ===\nAUTHOR'S TEXT ({author}):\n{h['text']}\n\n"
              f"CANDIDATES AND THEIR MODERN DESCRIPTIONS:\n{candidate_blocks(h['candidates'])}" for h in herbs]
    return PROMPT_BATCH.format(n=len(herbs), blocks="\n\n".join(blocks), features=", ".join(FEATURES))


def export_web(book: str) -> None:
    herbs = sorted(build(book), key=lambda h: h["herb"])
    folder = WEB / book
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for b in range(0, len(herbs), BATCH_SIZE):
        name = f"batch_{b // BATCH_SIZE + 1:02d}"
        group = [with_ids(h, f"h{i:02d}") for i, h in enumerate(herbs[b:b + BATCH_SIZE], 1)]
        manifest[name] = {g["hid"]: g["herb"] for g in group}
        (folder / f"{name}.txt").write_text(prompt_batch(book, group), encoding="utf-8")
        ans = folder / f"{name}.answer.txt"
        if not ans.exists():
            ans.write_text("", encoding="utf-8")
    (folder / "batches.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    sizes = [len((folder / f"{n}.txt").read_text(encoding="utf-8")) for n in manifest]
    print(f"{book}: {len(herbs)} herbs in {len(manifest)} prompts of up to {BATCH_SIZE} "
          f"(largest {max(sizes):,} characters). Folder: description_sources/check/web/{book}/")


def import_web(book: str, label: str) -> None:
    folder = WEB / book
    manifest = load_json(folder / "batches.json")
    by_key = {h["herb"]: h for h in build(book)}
    out = HERE / book / "description_check.json"
    old = load_json(out) if out.exists() else {"herbs": {}, "failed": []}
    results, mixups, missing, done = old.get("herbs", {}), [], [], 0
    for name, hids in manifest.items():
        ans = folder / f"{name}.answer.txt"
        js = parse(ans.read_text(encoding="utf-8")) if ans.exists() else None
        if not js:
            if ans.exists() and ans.read_text(encoding="utf-8").strip():
                print(f"  {name}: reply is not valid JSON")
            continue
        got = {str(x.get("hid")): x for x in js.get("herbs", []) if isinstance(x, dict)}
        for hid, key in hids.items():
            h = with_ids(by_key[key], hid)
            r = got.get(hid)
            if not r:
                missing.append(f"{name}/{hid} {h['name']}")
                continue
            ids = [str(d.get("id", "")) for d in r.get("details", [])] + \
                  [str(c.get("cid", "")) for c in r.get("candidates", [])] + \
                  [str(s.get("id", "")) for c in r.get("candidates", []) for s in c.get("scores", [])]
            mixups += [f"{name}/{hid}: {i}" for i in ids if i and not i.startswith(hid)]
            results[key] = {"name": h["name"], "model_version": f"web: {label}", "batch": name, **judge(h, r)}
            done += 1
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"book": book, "model": f"web: {label}",
                               "method": "Lardos et al. 2024, congruence per candidate",
                               "herbs": results, "failed": old.get("failed", [])}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"{book}: {done} herbs imported from the pasted replies ({len(results)} in the file).")
    print(f"Herbs missing from a reply: {len(missing)}" + ("".join(f"\n  {m}" for m in missing[:10])))
    print(f"Mix-ups (an id under the wrong herb): {len(mixups)}" + ("".join(f"\n  {m}" for m in mixups[:10])))
    summary(results)
    print(f"Saved to description_sources/check/{book}/description_check.json")


def summary(results: dict) -> None:
    top = Counter(r["candidates"][0]["verdict"] for r in results.values() if r["candidates"])
    best_lower = [(r["name"], max(r["candidates"], key=lambda c: c["congruence"])["accepted_name"])
                  for r in results.values() if r["candidates"] and
                  max(r["candidates"], key=lambda c: c["congruence"])["congruence"] > r["candidates"][0]["congruence"] + 1]
    print(f"Top candidate's verdict: {dict(top)}")
    print(f"Quotes not found in the author's text: {sum(len(r['quotes_not_in_text']) for r in results.values())}")
    print(f"BHL pages the model rejected as another plant: "
          f"{sum(len(c['bhl_pages_rejected']) for r in results.values() for c in r['candidates'])}")
    print(f"Herbs where a lower candidate fits clearly better ({len(best_lower)}):")
    for name, cand in best_lower[:20]:
        print(f"  {name} → {cand}")


# ---------- API ----------
def env(name: str) -> str:
    for line in open(ROOT / ".env", encoding="utf-8"):
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit(f"{name} not found in .env")


def ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CALLS = [0]


def generate(book: str, herb: str, model: str, text: str) -> dict:
    path = CACHE / book / model / (re.sub(r"\W+", "_", herb) + ".json")
    if path.exists():
        return load_json(path)
    body = {"contents": [{"role": "user", "parts": [{"text": text}]}], "generationConfig": {"temperature": 0}}
    if model.startswith("gemini"):
        body["generationConfig"]["responseMimeType"] = "application/json"
    req = urllib.request.Request(API.format(model=model), data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": env("GEMINI_API_KEY")})
    t0 = time.time()
    for attempt in range(len(WAITS) + 1):
        try:
            with urllib.request.urlopen(req, timeout=300, context=ctx()) as r:
                raw = json.load(r)
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:200]
            if e.code in (429, 500, 502, 503, 504) and attempt < len(WAITS):
                print(f"    {e.code}, waiting {WAITS[attempt]}s")
                time.sleep(WAITS[attempt])
                continue
            raise RuntimeError(f"HTTP {e.code}: {msg}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < len(WAITS):
                time.sleep(WAITS[attempt])
                continue
            raise RuntimeError(str(e))
    parts = (raw.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    rec = {"model": model, "model_version": raw.get("modelVersion"), "usage": raw.get("usageMetadata"),
           "time": dt.datetime.now().isoformat(timespec="seconds"), "seconds": round(time.time() - t0, 1),
           "prompt": text, "text": "".join(p.get("text", "") for p in parts if not p.get("thought"))}
    CALLS[0] += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def parse(text: str):
    t = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        t = t[t.index("{"): t.rindex("}") + 1]
    except ValueError:
        return None
    for attempt in (t, re.sub(r",(\s*[\]}])", r"\1", t)):   # strict=False: copied replies can wrap lines inside strings   # web replies sometimes leave a trailing comma
        try:
            return json.loads(attempt, strict=False)
        except ValueError:
            continue
    return None


# ---------- scoring, in code ----------
def plain(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c)).lower()
    return re.sub(r"[^\w]+", " ", s).strip()


def quote_ok(q: str, text: str) -> bool:
    frags = [f for f in re.split(r"\.\.\.|…", q or "") if plain(f)]
    return bool(frags) and all(plain(f) in plain(text) for f in frags)


def congruence(details: dict, scores: list) -> tuple:
    groups = defaultdict(list)
    for s in scores:
        d = details.get(s.get("id"))
        lab = str(s.get("label", "")).lower()
        if d and lab in POINTS:
            groups[d["feature"]].append(POINTS[lab])
    means = [sum(v) / len(v) for v in groups.values() if v]
    c = sum(m > 0 for m in means) - sum(m < 0 for m in means)
    return c, "strong" if c >= 5 else "moderate" if c >= 3 else "weak"


def judge(h: dict, js: dict) -> dict:
    details = {d.get("id"): {"feature": str(d.get("feature", "")).lower(), "quote": d.get("quote", "")}
               for d in js.get("details", []) if isinstance(d, dict)}
    bad = [i for i, d in details.items() if not quote_ok(d["quote"], h["text"])]
    for i in bad:                                          # a detail the author never wrote is not used
        details.pop(i)
    by_cid = {str(c.get("cid")): c for c in js.get("candidates", []) if isinstance(c, dict)}
    out = []
    for c in h["candidates"]:
        r = by_cid.get(c["cid"], {})
        scores = [s for s in r.get("scores", []) if isinstance(s, dict) and s.get("id") in details]
        wrong = {p.get("pid") for p in r.get("bhl_passages", []) if str(p.get("describes_candidate")).lower() == "no"}
        if wrong and len(wrong) == len(c["bhl"]):          # every BHL page is about another plant: drop BHL scores
            scores = [s for s in scores if s.get("source") != "bhl"]
        cong, verdict = congruence(details, scores)
        src = Counter(s.get("source") for s in scores if s.get("label") in ("good", "partial", "no"))
        wiki_only = src.get("wikipedia", 0) > 0 and src.get("bhl", 0) == 0
        if wiki_only and verdict == "strong":
            verdict = "moderate (Wikipedia only, D7)"
        out.append({"cid": c["cid"], "accepted_name": c["accepted_name"], "geography": c["geography"],
                    "congruence": cong, "verdict": verdict, "sources_used": dict(src), "wikipedia_only": wiki_only,
                    "bhl_pages_rejected": sorted(wrong), "scores": scores})
    return {"details": details, "quotes_not_in_text": bad, "candidates": out}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="culpeper", choices=["culpeper", "dioscorides"])
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--export-web", action="store_true", help="write prompts of 15 herbs for a web chat")
    ap.add_argument("--import-web", metavar="MODEL", help="read the pasted replies; MODEL labels them")
    a = ap.parse_args()
    if a.export_web:
        return export_web(a.book)
    if a.import_web:
        return import_web(a.book, a.import_web)
    herbs = build(a.book)
    random.Random(SEED).shuffle(herbs)
    herbs = herbs[: a.limit]
    print(f"{a.book}: {len(herbs)} herbs (random, seed {SEED}), model {a.model}")
    if a.dry_run:
        p = prompt(a.book, herbs[0])
        print(f"\n--- prompt for {herbs[0]['name']} ({len(p)} characters) ---\n{p}")
        return
    results, failed = {}, []
    for n, h in enumerate(herbs, 1):
        print(f"  {n}/{len(herbs)} {h['name']} · {len(h['candidates'])} candidates")
        try:
            rec = generate(a.book, h["herb"], a.model, prompt(a.book, h))
        except RuntimeError as e:
            print(f"    gave up for now ({e}); rerun to fill it in")
            failed.append(h["herb"])
            continue
        js = parse(rec["text"])
        if not js:
            failed.append(h["herb"])
            print("    reply was not valid JSON")
            continue
        results[h["herb"]] = {"name": h["name"], "model_version": rec.get("model_version"), **judge(h, js)}
    out = HERE / a.book / "description_check.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"book": a.book, "model": a.model, "method": "Lardos et al. 2024, congruence per candidate",
                               "herbs": results, "failed": failed}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{CALLS[0]} new calls · {len(results)} herbs checked · {len(failed)} failed")
    summary(results)
    print(f"Saved to description_sources/check/{a.book}/description_check.json")


if __name__ == "__main__":
    main()
