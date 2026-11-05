"""Test: can an AI model score descriptions the way the experts of Lardos et al. (2024) did?

Usage:
  python3 description_sources/paper_test/test_models.py --dry-run   # show the sample and prompts, no calls
  python3 description_sources/paper_test/test_models.py             # run all three tests (31 calls)
  python3 description_sources/paper_test/test_models.py --runs gemma_en   # only one test

Ground truth: Data file 9 of the paper (put in description_sources/paper_test/data/,
download: https://figshare.com/s/2e0f64b5794892ed4679). For each Dioscorides plant and
each candidate, the experts scored every detail: good / partial / no match / absent.
"absent" means the modern flora says nothing about that detail; code sets it, no AI.
The model only judges details where both texts say something.

Three runs on the same sample (15 candidates, 5 per expert verdict strong/moderate/weak):
  gemma_en   Gemma 4 31B, Dioscorides' details in English (Beck 2005, as in the paper),
             one candidate per call                                   15 calls
  gemma_gr   Gemma 4 31B, Dioscorides' Greek chapter (Wellmann, our chapters.json); the
             model must find and quote the detail itself, one candidate per call   15 calls
  flash_en   Gemini Flash (GEMINI_MODEL in .env), English details, all 15 candidates
             in ONE call, to see whether batching mixes plants up      1 call

Code then computes, identically for the experts and the model: the detail scores
(good +2, partial +1, no -2, absent 0), the mean per feature group, congruence =
groups with a positive mean - groups with a negative mean, and the verdict
(strong >= 5, moderate 3-4, weak <= 2).
Writes RESULTS.md (tracked, for transparency) and results.json; raw replies are cached
in cache/ so a rerun makes no new calls. The API key is read from .env, never written.
"""
import argparse
import datetime as dt
import json
import random
import re
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = HERE / "data" / "Data file 9 - Botanical comparative analysis.xlsx"
CHAPTERS = ROOT / "historical_texts" / "dioscorides" / "chapters.json"
CACHE = HERE / "cache"
OUT_MD = HERE / "RESULTS.md"
OUT_JSON = HERE / "results.json"
PROMPTS = HERE / "prompts"              # prompts exported for web chats, and the pasted replies
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMMA = "gemma-4-31b-it"
GEMMA_PAUSE = 90                        # observed: right after a success the next Gemma call fails; after 1-2 min it works
GEMMA_WAITS = [90, 120, 180, 240]       # on 500/503 from Gemma: wait this long, then retry
SEED = 42
PER_VERDICT = 5
MIN_JUDGED = 4                          # a candidate needs at least 4 details both texts describe
LABELS = ["good", "partial", "no"]
POINTS = {"good": 2, "partial": 1, "no": -2, "absent": 0, "not_described": 0}
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}
GROUPS = {"Life": "habit", "Habitus": "habit", "Height": "habit", "Stem": "stem", "Leaf": "leaf",
          "Flower": "flower", "Fruit": "fruit", "Seed": "seed", "Root": "root", "Smell": "smell",
          "Taste": "taste", "Ethnobotany": "ethnobotany", "Habitat": "habitat", "Distribution": "distribution"}

RULES = """Scoring rules (from Lardos et al. 2024, J Ethnopharmacol 322:117622):
- good: the two descriptions agree on this detail.
- partial: they partly agree, or one is more general or vaguer than the other but compatible.
- no: they contradict each other.
Judge botanical sense, not wording: ancient descriptions are vague, use comparisons and old
units (a cubit is about 46 cm). Do not use your own knowledge of which plant this is."""

PROMPT_EN = """You compare an ancient plant description (Dioscorides, De materia medica, English
translation) with a modern flora description of one candidate plant, detail by detail.
{rules}

Candidate plant: {candidate}
Details (id | feature | Dioscorides | modern flora):
{details}

Answer with JSON only, no other text:
{{"scores": [{{"id": "<id>", "label": "good|partial|no", "reason": "<max 15 words>"}}]}}
Give exactly one entry per id."""

PROMPT_GR = """You compare an ancient plant description (Dioscorides, De materia medica, in Ancient
Greek, Wellmann's edition) with a modern flora description of one candidate plant, detail by detail.
{rules}
For each detail, first find what Dioscorides says about that feature in the Greek text and copy
it exactly (a few words, in Greek, as written). Ignore statements that only compare the plant
with another plant. If he says nothing about the feature, use label "not_described" and an empty quote.

Dioscorides' chapter {chapter}:
{greek}

Candidate plant: {candidate}
Details (id | feature | modern flora):
{details}

Answer with JSON only, no other text:
{{"scores": [{{"id": "<id>", "quote": "<exact Greek words or empty>", "label": "good|partial|no|not_described", "reason": "<max 15 words>"}}]}}
Give exactly one entry per id."""

PROMPT_BATCH = """You compare ancient plant descriptions (Dioscorides, De materia medica, English
translation) with modern flora descriptions of candidate plants, detail by detail.
{rules}
There are {n} separate candidates below. Score each candidate only against its own details.

{blocks}

Answer with JSON only, no other text:
{{"candidates": [{{"cid": "<cid>", "scores": [{{"id": "<id>", "label": "good|partial|no", "reason": "<max 15 words>"}}]}}]}}
Give exactly one entry per id, under the candidate it belongs to."""

PROMPT_BATCH_GR = """You compare ancient plant descriptions (Dioscorides, De materia medica, in Ancient
Greek, Wellmann's edition) with modern flora descriptions of candidate plants, detail by detail.
{rules}
For each detail, first find what Dioscorides says about that feature in the Greek text of the
candidate's chapter and copy it exactly (a few words, in Greek, as written). Ignore statements that
only compare the plant with another plant. If he says nothing about the feature, use label
"not_described" and an empty quote.
There are {n} separate candidates below, grouped under the chapter they belong to. Score each
candidate only against its own chapter and its own details.

{blocks}

Answer with JSON only, no other text:
{{"candidates": [{{"cid": "<cid>", "scores": [{{"id": "<id>", "quote": "<exact Greek words or empty>", "label": "good|partial|no|not_described", "reason": "<max 15 words>"}}]}}]}}
Give exactly one entry per id, under the candidate it belongs to."""


# ---------- data ----------
def cell(v) -> str:
    s = re.sub(r"\s+", " ", str(v or "")).strip()
    return "" if s.lower() in ("x", "none", "--") else s


def label_of(v) -> str:
    s = cell(v).lower()
    return {"good": "good", "partial": "partial", "no": "no", "absent": "absent"}.get(s, "")


def chapter_label(ref: str):
    m = re.match(r"DMM\s*,?\s*([IV]+)\s*,\s*(\d+)", ref.replace("Ι", "I"))
    return f"{ROMAN[m.group(1)]}.{m.group(2)}" if m else None


def load() -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(DATA, read_only=True, data_only=True)
    rows = list(wb["Comparison DMM vs. FT_FC"].iter_rows(values_only=True))
    head = [cell(h) for h in rows[0]]
    feats = [(i, head[i]) for i in range(4, len(head) - 1, 2) if head[i]]
    chapters = {c["label"]: c for c in json.load(open(CHAPTERS, encoding="utf-8"))["chapters"]}
    out, dmm = [], None
    for r in rows[1:]:
        if not cell(r[0]):
            continue
        if not cell(r[3]):                                    # Dioscorides' own row
            ref = cell(r[1])
            dmm = {"name": cell(r[0]), "ref": ref, "chapter": chapter_label(ref),
                   "desc": {f: cell(r[i]) for i, f in feats if cell(r[i])}}
            continue
        if not dmm or cell(r[0]) != dmm["name"]:
            continue
        details = []
        for i, f in feats:
            exp = label_of(r[i + 1])
            if f in dmm["desc"] and exp:
                details.append({"feature": f, "historical": dmm["desc"][f], "modern": cell(r[i]), "expert": exp})
        if not details:
            continue
        ch = chapters.get(dmm["chapter"] or "")
        greek_ok = bool(ch) and plain(ch["headword_latin"] or "")[:3] == plain(dmm["name"])[:3]
        out.append({"plant": dmm["name"], "ref": dmm["ref"], "chapter": dmm["chapter"],
                    "candidate": re.sub(r"\s*\(.*", "", cell(r[3])), "flora": cell(r[1]),
                    "details": details, "greek": ch["text"] if greek_ok else None})
    return out


def plain(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c)).lower()
    return re.sub(r"[^\w]+", " ", s).strip()


# ---------- the paper's scoring, done in code ----------
def congruence(labels: dict) -> tuple[int, str]:
    """labels: feature -> label. Returns (congruence, verdict)."""
    groups = defaultdict(list)
    for f, lab in labels.items():
        groups[GROUPS.get(f.split()[0], f)].append(POINTS[lab])
    means = [sum(v) / len(v) for v in groups.values()]
    c = sum(m > 0 for m in means) - sum(m < 0 for m in means)
    return c, "strong" if c >= 5 else "moderate" if c >= 3 else "weak"


def sample(cands: list[dict]) -> list[dict]:
    pool = defaultdict(list)
    for c in cands:
        judged = [d for d in c["details"] if d["expert"] in LABELS and d["modern"]]
        if len(judged) >= MIN_JUDGED and c["greek"] and c["flora"] and "not found" not in c["flora"]:
            c["expert_congruence"], c["expert_verdict"] = congruence({d["feature"]: d["expert"] for d in c["details"]})
            pool[c["expert_verdict"]].append(c)
    rnd = random.Random(SEED)
    picked = []
    for v in ("strong", "moderate", "weak"):
        picked += rnd.sample(pool[v], min(PER_VERDICT, len(pool[v])))
    for n, c in enumerate(picked, 1):
        c["cid"] = f"c{n:02d}"
        for k, d in enumerate(c["details"], 1):
            d["id"] = f"{c['cid']}.d{k:02d}"
    return picked


def to_ask(c: dict) -> list[dict]:
    """Details both texts describe; the rest are 'absent' (set by code, as the experts did)."""
    return [d for d in c["details"] if d["modern"]]


# ---------- prompts ----------
def prompt_en(c: dict) -> str:
    lines = "\n".join(f"{d['id']} | {d['feature']} | {d['historical']} | {d['modern']}" for d in to_ask(c))
    return PROMPT_EN.format(rules=RULES, candidate=c["candidate"], details=lines)


def prompt_gr(c: dict) -> str:
    lines = "\n".join(f"{d['id']} | {d['feature']} | {d['modern']}" for d in to_ask(c))
    return PROMPT_GR.format(rules=RULES, chapter=c["chapter"], greek=c["greek"], candidate=c["candidate"], details=lines)


def prompt_batch(cs: list[dict]) -> str:
    blocks = []
    for c in cs:
        lines = "\n".join(f"{d['id']} | {d['feature']} | {d['historical']} | {d['modern']}" for d in to_ask(c))
        blocks.append(f"### cid {c['cid']}: candidate plant {c['candidate']}\nDetails (id | feature | Dioscorides | modern flora):\n{lines}")
    return PROMPT_BATCH.format(rules=RULES, n=len(cs), blocks="\n\n".join(blocks))


def prompt_batch_gr(cs: list[dict]) -> str:
    """All candidates in one prompt, each chapter's Greek text given once, its candidates under it."""
    blocks = []
    for ch in dict.fromkeys(c["chapter"] for c in cs):
        group = [c for c in cs if c["chapter"] == ch]
        parts = [f"## Chapter {ch} (Greek):\n{group[0]['greek']}"]
        for c in group:
            lines = "\n".join(f"{d['id']} | {d['feature']} | {d['modern']}" for d in to_ask(c))
            parts.append(f"### cid {c['cid']}: candidate plant {c['candidate']} (chapter {ch})\n"
                         f"Details (id | feature | modern flora):\n{lines}")
        blocks.append("\n\n".join(parts))
    return PROMPT_BATCH_GR.format(rules=RULES, n=len(cs), blocks="\n\n".join(blocks))


# ---------- API ----------
def env(name: str) -> str:
    for line in open(ROOT / ".env", encoding="utf-8"):
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit(f"{name} not found in .env")


def ctx():
    import ssl
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CALLS = Counter()
OFFLINE = False                         # --import-web: build the report from saved replies only, no API calls


class CallFailed(Exception):
    pass



def post(url: str, body: dict, headers: dict, waits: list) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    for attempt in range(len(waits) + 1):
        try:
            with urllib.request.urlopen(req, timeout=300, context=ctx()) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < len(waits):
                print(f"    {e.code}, waiting {waits[attempt]}s, retry {attempt + 1}/{len(waits)}")
                time.sleep(waits[attempt])
                continue
            raise CallFailed(f"HTTP {e.code}: {msg[:160]}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < len(waits):
                time.sleep(waits[attempt])
                continue
            raise CallFailed(str(e))


def generate(run: str, key: str, model: str, prompt: str) -> dict:
    path = CACHE / run / f"{key}.json"
    if path.exists():
        return json.load(open(path, encoding="utf-8"))
    t0 = time.time()
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}}
    if model.startswith("gemini"):
        body["generationConfig"]["responseMimeType"] = "application/json"
    raw = post(API.format(model=model), body, {"x-goog-api-key": env("GEMINI_API_KEY")},
               GEMMA_WAITS if model.startswith("gemma") else [30, 60])
    parts = (raw.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    rec = {"model": model, "model_version": raw.get("modelVersion"), "usage": raw.get("usageMetadata"),
           "text": "".join(p.get("text", "") for p in parts if not p.get("thought")),
           "time": dt.datetime.now().isoformat(timespec="seconds"), "seconds": round(time.time() - t0, 1), "prompt": prompt}
    CALLS[run] += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    if model.startswith("gemma"):
        time.sleep(GEMMA_PAUSE)
    return rec


def parse(text: str):
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(t[t.index("{"): t.rindex("}") + 1])
    except ValueError:
        return None


# ---------- runs ----------
def run_single(run: str, model: str, cs: list[dict], make, greek: bool) -> dict:
    res = {"model": model, "calls": 0, "versions": set(), "answers": {}, "quotes_bad": [], "parse_fail": [], "missing": []}
    for c in cs:
        print(f"  {run} {c['cid']} {c['plant']} → {c['candidate']}")
        if OFFLINE and not (CACHE / run / f"{c['cid']}.json").exists():
            res["parse_fail"].append(c["cid"])
            continue
        try:
            rec = generate(run, c["cid"], model, make(c))
        except CallFailed as e:
            print(f"    gave up on {c['cid']} for now ({e}); rerun later to fill it in")
            res["parse_fail"].append(c["cid"])
            continue
        res["versions"].add(rec.get("model_version"))
        js = parse(rec["text"])
        if not js:
            res["parse_fail"].append(c["cid"])
            continue
        got = {s.get("id"): s for s in js.get("scores", []) if isinstance(s, dict)}
        for d in to_ask(c):
            s = got.get(d["id"])
            if not s:
                res["missing"].append(d["id"])
                continue
            lab = str(s.get("label", "")).lower().strip()
            if greek and lab != "not_described" and s.get("quote"):
                if plain(s["quote"]) not in plain(c["greek"]):
                    res["quotes_bad"].append({"id": d["id"], "quote": s["quote"]})
            res["answers"][d["id"]] = {"label": lab, "reason": s.get("reason", ""), "quote": s.get("quote", "")}
    return res


def run_batch(run: str, model: str, cs: list[dict], make=None, greek: bool = False) -> dict:
    make = make or prompt_batch
    res = {"model": model, "versions": set(), "answers": {}, "quotes_bad": [], "parse_fail": [], "missing": [], "mixups": []}
    print(f"  {run}: {len(cs)} candidates in one call")
    if OFFLINE and not (CACHE / run / "batch.json").exists():
        res["parse_fail"].append("batch")
        return res
    try:
        rec = generate(run, "batch", model, make(cs))
    except CallFailed as e:
        print(f"    gave up for now ({e}); rerun later")
        res["parse_fail"].append("batch")
        return res
    res["versions"].add(rec.get("model_version"))
    js = parse(rec["text"])
    if not js:
        res["parse_fail"].append("batch")
        return res
    greek_of = {c["cid"]: c["greek"] for c in cs}
    for block in js.get("candidates", []):
        for s in block.get("scores", []):
            sid = str(s.get("id", ""))
            if not sid.startswith(str(block.get("cid", "")) + "."):
                res["mixups"].append({"id": sid, "under": block.get("cid")})
            lab = str(s.get("label", "")).lower().strip()
            if greek and lab != "not_described" and s.get("quote"):
                if plain(s["quote"]) not in plain(greek_of.get(sid.split(".")[0], "")):
                    res["quotes_bad"].append({"id": sid, "quote": s["quote"]})
            res["answers"][sid] = {"label": lab, "reason": s.get("reason", ""), "quote": s.get("quote", "")}
    res["missing"] = [d["id"] for c in cs for d in to_ask(c) if d["id"] not in res["answers"]]
    return res


# ---------- evaluation ----------
def kappa(pairs: list[tuple[str, str]]) -> float:
    if not pairs:
        return float("nan")
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n / n
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def evaluate(cs: list[dict], res: dict) -> dict:
    pairs, rows, disagree = [], [], []
    for c in cs:
        model_labels = {}
        for d in c["details"]:
            if not d["modern"]:
                model_labels[d["feature"]] = "absent"
                continue
            a = res["answers"].get(d["id"])
            lab = a["label"] if a and a["label"] in POINTS else "absent"
            model_labels[d["feature"]] = lab
            if d["expert"] in LABELS:
                pairs.append((d["expert"], lab))
                if lab != d["expert"]:
                    disagree.append({"cid": c["cid"], "feature": d["feature"], "historical": d["historical"],
                                     "modern": d["modern"], "expert": d["expert"], "model": lab,
                                     "reason": (a or {}).get("reason", ""), "quote": (a or {}).get("quote", "")})
        mc, mv = congruence(model_labels)
        rows.append({"cid": c["cid"], "plant": c["plant"], "candidate": c["candidate"], "expert": (c["expert_congruence"], c["expert_verdict"]),
                     "model": (mc, mv)})
    exact = sum(a == b for a, b in pairs)
    sign = sum((a == "no") == (b == "no") and b in LABELS for a, b in pairs)
    return {"pairs": pairs, "n": len(pairs), "exact": exact, "sign": sign, "kappa": kappa([(a, b) for a, b in pairs]),
            "confusion": Counter(pairs), "rows": rows, "disagree": disagree,
            "verdict_ok": sum(r["expert"][1] == r["model"][1] for r in rows),
            "cong_diff": sum(abs(r["expert"][0] - r["model"][0]) for r in rows) / max(1, len(rows))}


# ---------- report ----------
def pct(a, b):
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "–"


def short(s, n=70):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def report(cs, runs: dict, evals: dict, flash_model: str) -> str:
    L = ["# Description check: AI models vs the experts of Lardos et al. (2024)", "",
         f"_Generated by `description_sources/paper_test/test_models.py` on {dt.date.today()}. "
         "Regenerated from the cached replies on every run, so it always matches `cache/`._", "",
         "## What was tested",
         "The paper's experts compared Dioscorides' description of each plant with modern flora descriptions "
         "(Flora of Turkey, Flora of Cyprus) of each candidate plant, detail by detail, and scored each detail "
         "good / partial / no match / absent (data file 9, 1,213 scored details). We gave the same details to AI "
         "models and compared their scores with the experts'. \"Absent\" (the flora says nothing) is set by code, "
         "not by the model, exactly as the experts did; the model judges only the details both texts describe.", "",
         f"Sample: {len(cs)} candidates, {PER_VERDICT} for each expert verdict (strong, moderate, weak), drawn at "
         f"random (seed {SEED}) from candidates with at least {MIN_JUDGED} judged details and a Greek chapter that "
         "matches the paper's reference.", "",
         "| Run | Model | Input | Plants per call | Calls |", "|---|---|---|---|---|"]
    desc = {"gemma_en": ("English details (Beck 2005, as in the paper)", "1"),
            "gemma_gr": ("Greek chapter (Wellmann); the model finds and quotes each detail", "1"),
            "flash_en": ("English details (Beck 2005)", str(len(cs))),
            "flash_lite_en": ("English details (Beck 2005), pasted from the AI Studio playground", str(len(cs))),
            "flash38_en": ("English details (Beck 2005), Gemini 3.8 Flash web chat, temp 0", str(len(cs))),
            "flash38_gr": ("Greek chapters (Wellmann), Gemini 3.8 Flash web chat, temp 0", str(len(cs)))}
    for run, r in runs.items():
        calls = len(list((CACHE / run).glob("*.json"))) if (CACHE / run).exists() else 0
        vers = ", ".join(sorted(v for v in r["versions"] if v)) or "?"
        L.append(f"| {run} | `{r['model']}` (served: {vers}) | {desc[run][0]} | {desc[run][1]} | {calls} |")
    L += ["", "## Results side by side", "",
          "| | " + " | ".join(runs) + " |", "|---|" + "---|" * len(runs)]
    def row(name, f):
        L.append(f"| {name} | " + " | ".join(f(runs[r], evals[r]) for r in runs) + " |")
    row("Details judged by the experts", lambda r, e: str(e["n"]))
    row("**Detail score = expert's (good/partial/no)**", lambda r, e: pct(e["exact"], e["n"]))
    row("Same direction (match vs no match)", lambda r, e: pct(e["sign"], e["n"]))
    row("Cohen's kappa (agreement beyond chance)", lambda r, e: f"{e['kappa']:.2f}")
    row("**Final verdict = expert's (strong/moderate/weak)**", lambda r, e: pct(e["verdict_ok"], len(e["rows"])))
    row("Mean congruence difference", lambda r, e: f"{e['cong_diff']:.1f}")
    row("Details not answered", lambda r, e: str(len(r["missing"])))
    row("Calls failed or replies not valid JSON", lambda r, e: str(len(r["parse_fail"])))
    row("Greek quotes not found in the chapter", lambda r, e: str(len(r["quotes_bad"])) if r["model"] and runs and "quotes_bad" in r else "–")
    row("Mix-ups between plants (batched call)", lambda r, e: str(len(r["mixups"])) if "mixups" in r else "n/a")
    L += ["", "Detail agreement counts only the details the experts judged good, partial or no. "
          "Cohen's kappa: 0 = chance, 1 = perfect; above 0.6 is usually called substantial.", ""]
    for run in runs:
        e, r = evals[run], runs[run]
        L += [f"## {run}", "", "**Confusion (rows: experts, columns: model)**", "",
              "| expert \\ model | good | partial | no | not described / absent |", "|---|---|---|---|---|"]
        for a in LABELS:
            L.append(f"| {a} | " + " | ".join(str(e["confusion"][(a, b)]) for b in LABELS) +
                     f" | {e['confusion'][(a, 'not_described')] + e['confusion'][(a, 'absent')]} |")
        L += ["", "**Per candidate**", "", "| cid | Dioscorides plant | Candidate | Experts | Model |", "|---|---|---|---|---|"]
        for x in e["rows"]:
            ok = "" if x["expert"][1] == x["model"][1] else " ✗"
            L.append(f"| {x['cid']} | {x['plant']} | *{x['candidate']}* | {x['expert'][0]} {x['expert'][1]} | {x['model'][0]} {x['model'][1]}{ok} |")
        if r["quotes_bad"]:
            L += ["", "**Greek quotes not found in the chapter**", ""] + [f"- {q['id']}: «{short(q['quote'])}»" for q in r["quotes_bad"]]
        if r.get("mixups"):
            L += ["", "**Mix-ups**", ""] + [f"- {m['id']} answered under {m['under']}" for m in r["mixups"]]
        if e["disagree"]:
            L += ["", f"**Disagreements (first 8 of {len(e['disagree'])})**", "",
                  "| id | Feature | Dioscorides (Beck) | Modern flora | Experts | Model | Model's reason |", "|---|---|---|---|---|---|---|"]
            for d in e["disagree"][:8]:
                L.append(f"| {d['cid']} | {d['feature']} | {short(d['historical'], 45)} | {short(d['modern'], 45)} | {d['expert']} | {d['model']} | {short(d['reason'], 60)} |")
        L.append("")
    L += ["## Prompts", "", "The exact templates sent (the details are filled in per candidate).", "",
          "<details><summary>English, one candidate per call (gemma_en)</summary>", "", "```", PROMPT_EN.format(rules=RULES, candidate="{candidate}", details="{details}"), "```", "</details>", "",
          "<details><summary>Greek chapter, one candidate per call (gemma_gr)</summary>", "", "```", PROMPT_GR.format(rules=RULES, chapter="{chapter}", greek="{greek}", candidate="{candidate}", details="{details}"), "```", "</details>", "",
          "<details><summary>English, all candidates in one call (flash_en)</summary>", "", "```", PROMPT_BATCH.format(rules=RULES, n="{n}", blocks="{blocks}"), "```", "</details>", "",
          "## Decision", "", "_To be written after review: which model, and why, based on the numbers above._", "",
          "## Notes and limits",
          "- The English runs use the paper's own extraction of Dioscorides' details (Beck's translation), so they "
          "measure comparison only. The Greek run also tests finding the detail in Wellmann's Greek, which is what "
          "our pipeline must do.",
          "- The verdict uses our reading of the paper's method (group means, congruence = positive − negative groups); "
          "the same code scores experts and models, so the comparison is like for like.",
          "- Temperature 0. Each reply is stored in `cache/<run>/` with the model version Google reports.",
          "- Source: Lardos A, Patmore K, Allkin R, Lazarou R, Nesbitt M, Scott AC, Zipser B (2024). J Ethnopharmacol 322:117622. "
          "https://doi.org/10.1016/j.jep.2023.117622 (CC BY 4.0). Data: https://figshare.com/s/2e0f64b5794892ed4679", ""]
    return "\n".join(L)


def main() -> None:
    global OFFLINE
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="gemma_en,gemma_gr,flash_en,flash_lite_en,flash38_en,flash38_gr")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--export-prompts", action="store_true",
                    help="write the prompts still missing a reply to prompts/<run>/<cid>.txt, for pasting into a web chat")
    ap.add_argument("--import-web", metavar="MODEL",
                    help="read pasted web-chat replies from prompts/<run>/<cid>.answer.txt into the cache, "
                         "labelled with this model name (e.g. 'Gemma 4 31B, AI Studio chat')")
    a = ap.parse_args()
    cs = sample(load())
    flash = env("GEMINI_MODEL")
    print(f"Sample: {len(cs)} candidates · " + ", ".join(f"{v} {sum(c['expert_verdict'] == v for c in cs)}" for v in ("strong", "moderate", "weak")))
    for c in cs:
        print(f"  {c['cid']} {c['plant']:15} ch {c['chapter']:6} → {c['candidate']:35} experts {c['expert_congruence']:>2} {c['expert_verdict']:8} · {len(to_ask(c))} details to judge")
    runs = [r.strip() for r in a.runs.split(",")]
    makers = {"gemma_en": lambda: [(c["cid"], prompt_en(c)) for c in cs],
              "gemma_gr": lambda: [(c["cid"], prompt_gr(c)) for c in cs],
              "flash_en": lambda: [("batch", prompt_batch(cs))],
              "flash_lite_en": lambda: [("batch", prompt_batch(cs))],
              "flash38_en": lambda: [("batch", prompt_batch(cs))],
              "flash38_gr": lambda: [("batch", prompt_batch_gr(cs))]}
    if a.export_prompts:
        n = 0
        for run in runs:
            for key, text in makers[run]():
                if (CACHE / run / f"{key}.json").exists():
                    continue
                f = PROMPTS / run / f"{key}.txt"
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(text, encoding="utf-8")
                n += 1
                print(f"  {f.relative_to(ROOT)}")
        print(f"\n{n} prompts written. Paste each into a NEW chat, copy the whole reply into the file with the same "
              f"name ending .answer.txt, then run: --import-web \"<model name>\"")
        return
    if a.import_web:
        n = 0
        for run in runs:
            for key, text in makers[run]():
                ans = PROMPTS / run / f"{key}.answer.txt"
                if not ans.exists() or not ans.read_text(encoding="utf-8").strip() \
                        or (CACHE / run / f"{key}.json").exists():
                    continue                    # no reply pasted yet (or already imported)
                rec = {"model": f"web: {a.import_web}", "model_version": "web chat (temperature not set)",
                       "time": dt.datetime.now().isoformat(timespec="seconds"), "prompt": text,
                       "text": ans.read_text(encoding="utf-8")}
                (CACHE / run).mkdir(parents=True, exist_ok=True)
                (CACHE / run / f"{key}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
                n += 1
        print(f"{n} pasted replies imported. Writing the report ...")
        OFFLINE = True
    if a.dry_run:
        print("\n--- gemma_en prompt (c01) ---\n" + prompt_en(cs[0]))
        print("\n--- gemma_gr prompt (c01), Greek shortened ---\n" + prompt_gr({**cs[0], "greek": cs[0]["greek"][:300] + " …"}))
        print(f"\n--- flash_en: one prompt, {len(prompt_batch(cs))} characters ---")
        return
    results = {}
    if "gemma_en" in runs:
        results["gemma_en"] = run_single("gemma_en", GEMMA, cs, prompt_en, False)
    if "gemma_gr" in runs:
        results["gemma_gr"] = run_single("gemma_gr", GEMMA, cs, prompt_gr, True)
    if "flash_en" in runs:
        results["flash_en"] = run_batch("flash_en", flash, cs)
    if "flash_lite_en" in runs:                 # web chat only: never called through the API
        OFFLINE = True
        results["flash_lite_en"] = run_batch("flash_lite_en", "gemini-3.5-flash-lite (playground)", cs)
    if "flash38_en" in runs:                    # web chat only: never called through the API
        OFFLINE = True
        results["flash38_en"] = run_batch("flash38_en", "gemini-3.8-flash (web chat)", cs)
    if "flash38_gr" in runs:
        OFFLINE = True
        results["flash38_gr"] = run_batch("flash38_gr", "gemini-3.8-flash (web chat)", cs, prompt_batch_gr, True)
    for r in [r for r, v in results.items() if not v["answers"]]:   # no reply at all: leave it out, not "0%"
        print(f"  {r}: no answers yet, left out of the report")
        del results[r]
    if not results:
        print("Nothing to report yet; RESULTS.md unchanged.")
        return
    evals = {r: evaluate(cs, v) for r, v in results.items()}
    OUT_MD.write_text(report(cs, results, evals, flash), encoding="utf-8")
    OUT_JSON.write_text(json.dumps({r: {**{k: v for k, v in results[r].items() if k != "versions"},
                                        "versions": sorted(x for x in results[r]["versions"] if x)} for r in results},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{sum(CALLS.values())} new calls ({dict(CALLS)}). Report: description_sources/paper_test/RESULTS.md")
    for r, e in evals.items():
        print(f"  {r:9} details {pct(e['exact'], e['n'])} · verdicts {pct(e['verdict_ok'], len(e['rows']))} · kappa {e['kappa']:.2f}")


if __name__ == "__main__":
    main()
