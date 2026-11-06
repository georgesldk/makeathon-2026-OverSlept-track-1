"""Stage 3, step 4: claim × study extraction through the web chat, then code checks and rules.
The model only fills fields (STAGE3_DATA_CONTRACT.md §4.1); stage3/rules.py derives the result.

Usage:
  python3 stage3/extract_assessments.py --set shared --export-web      write the prompts to stage3/web/shared/
  ... paste each batch_NNN.txt into a NEW chat (Gemini 3.8 Flash, temp 0), reply into batch_NNN.answer.txt ...
  python3 stage3/extract_assessments.py --set shared --import-web "Gemini 3.8 Flash, web chat, temp 0"
  (--set pilot is the frozen, reviewed pilot: import only)

Pairs: every unit × every study kept by screening that was found for that unit. Batches of 32 pairs
(the pilot used 8; 32 was not tested against 8, see EVIDENCE_RULES.md), at most 3,200 pairs. When there
are more pairs, they are chosen in rounds so that as many claims as possible get evidence:
round 1 = each unit's best study, round 2 = its second best, and so on (at most 6 per unit). Within
a round, units go in the set's order (shared: groups with an A plant in both books first). Best study:
EMA monograph, then systematic review / meta-analysis, RCT / clinical trial, registered trial with
results, review, any other; then search rank. Pairs left out are listed in not_exported.jsonl.
Import, per pair: schema check · every excerpt must be in the stored text (whitespace and case
ignored; pieces joined by "..." in order), otherwise the field it supports is voided (-> unknown) ·
rules.assess() · then rules.summarise() per claim.
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from rules import assess, summarise
from sets import paths, SETS

BATCH = {"pilot": 8}                    # the pilot's batches; every other set uses DEFAULT_BATCH
DEFAULT_BATCH, MAX_PAIRS, MAX_PER_UNIT = 32, 3200, 6     # 32 pairs ≈ 24k output tokens; 64 got cut off in the web chat
PROMPT_VERSION = {"pilot": "s3-extract-0.3"}       # the pilot's replies were made with 0.3
DEFAULT_PROMPT_VERSION = "s3-extract-0.5"           # 0.4 = 0.3 + registered trials and EMA monographs;
                                                    # 0.5 = every filled field must carry its own excerpt
FIELDS = ("species", "condition", "therapeutic_action", "plant_part", "preparation", "route")

PROMPT = """You extract facts from modern sources for a research database. You do NOT judge whether a
source supports a historical remedy: you only report what each source text says, field by field.
There are {n} separate pairs below. Each pair = one historical claim (from an old herbal) and one
modern source: a scientific abstract (sometimes with its Results section), a registered clinical
trial, or an EU herbal monograph (EMA). Treat every pair on its own.

{blocks}

For EACH pair, fill these fields from the SOURCE TEXT only (never from your own knowledge):
1. relevance: does the study investigate the claim or a meaningfully related question?
   direct | related | different_question | not_about_the_plant | unclear
2. evidence_type: systematic_review | human_rct | human_other | animal | in_vitro |
   traditional_use_document | registered_trial | regulatory_monograph | other | unknown
   (a survey of traditional uses = traditional_use_document; a ClinicalTrials.gov record = registered_trial;
   an EMA monograph = regulatory_monograph)
3. compatibility, for species, condition, therapeutic_action, plant_part, preparation, route:
   same | related | different | unknown, plus what the study says ("study_says").
   species: same = the claim's species; related = another species of the same genus; different = another genus.
   A homeopathic dilution, an isolated compound or a mixed product is a "different" preparation.
   If the abstract does not say, write unknown. Never guess a match.
4. outcome: positive | negative | mixed | inconclusive | not_reported | unclear,
   with the endpoint measured and the comparator, if stated. Take the outcome from reported RESULTS,
   not from background sentences. Harm or toxicity of the plant is not a positive outcome for the claim.
   A registered trial: positive/negative only if results are given in the text, otherwise not_reported.
   An EMA monograph: positive = it lists an indication matching the claim (quote the indication),
   otherwise not_reported. Its route and preparation are in its posology section.
5. excerpts: EVERY field you fill (anything not unknown/unclear), including relevance and evidence_type,
   needs its OWN entry in "excerpts": an EXACT phrase copied from the source text or its MODERN SOURCE
   header line (a short phrase is enough). Code checks each one; a field without a verified excerpt is
   discarded, so do not skip relevance.
6. harm: does the abstract report harm, toxicity, poisoning or adverse effects caused by the plant
   or its products? yes | no | not_reported, with what harm and an EXACT excerpt. Report this even when
   the study is about a different question. Harm is a safety finding, not evidence for or against the claim.
7. overall (answer LAST, after all the fields above): taking everything into account, does this study
   support the historical claim? supports | contradicts | mixed | unrelated | insufficient,
   with a one-line reason and an EXACT excerpt from the abstract. Sharing the plant and the condition
   is not enough to support: the study must test the plant for this use and report a result.

Answer with JSON only:
{{"pairs": [{{"pid": "p01", "relevance": "...", "evidence_type": "...",
  "compatibility": {{"species": {{"value": "...", "study_says": "..."}}, "condition": {{...}},
     "therapeutic_action": {{...}}, "plant_part": {{...}}, "preparation": {{...}}, "route": {{...}}}},
  "outcome": {{"value": "...", "endpoint": "...", "comparator": "..."}},
  "excerpts": [{{"field": "relevance|evidence_type|outcome|species|condition|therapeutic_action|plant_part|preparation|route",
                 "text": "<exact words from the source text>"}}],
  "harm": {{"value": "yes|no|not_reported", "what": "...", "excerpt": "<exact words from the source text>"}},
  "overall": {{"value": "...", "reason": "...", "excerpt": "<exact words from the source text>"}}}}]}}"""


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def found(excerpt: str, text: str) -> bool:
    """The excerpt is in the abstract. Pieces joined by "..." must each be there, in order (as in Stage 1)."""
    pos, t = 0, norm(text)
    pieces = [norm(x) for x in re.split(r"\.\.\.|…", excerpt or "") if norm(x)]
    for piece in pieces:
        i = t.find(piece, pos)
        if i < 0:
            return False
        pos = i + len(piece)
    return bool(pieces)


def parse(text: str):
    t = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        t = t[t.index("{"): t.rindex("}") + 1]
    except ValueError:
        return None
    for attempt in (t, re.sub(r",(\s*[\]}])", r"\1", t)):
        try:
            return json.loads(attempt, strict=False)
        except ValueError:
            continue
    return salvage(t)


def salvage(t: str):
    """A reply cut off before its end: keep every complete pair object, drop the unfinished one."""
    i = t.find("[")
    if i < 0:
        return None
    dec, pos, pairs = json.JSONDecoder(strict=False), i + 1, []
    while True:
        m = re.compile(r"\s*,?\s*").match(t, pos)
        pos = m.end()
        try:
            obj, pos = dec.raw_decode(t, pos)
        except ValueError:
            break
        if isinstance(obj, dict):
            pairs.append(obj)
    return {"pairs": pairs, "salvaged": True} if pairs else None


def pairs(P: dict) -> list:
    units = {json.loads(l)["unit_id"]: json.loads(l) for l in open(P["units"], encoding="utf-8")}
    out = []
    lines = open(P["studies"] / "studies.jsonl", encoding="utf-8").readlines()
    print(f"Reading {len(lines)} source records ...", flush=True)
    for line in lines:
        s = json.loads(line)
        if s["screening"]["decision"] != "kept":
            continue
        text = (ROOT / s["text"]["locator"]).read_text(encoding="utf-8")
        for uid in s["found_for_units"]:
            if uid in units:
                out.append((units[uid], s, text))
    return sorted(out, key=lambda x: (x[0]["unit_id"], x[1]["study_id"]))


def study_priority(s: dict, text: str) -> tuple:
    pts = set(s.get("publication_types") or [])
    if s.get("source") == "EMA":
        level = 0
    elif pts & {"Systematic Review", "Meta-Analysis"}:
        level = 1
    elif pts & {"Randomized Controlled Trial", "Clinical Trial", "Controlled Clinical Trial"} or any(p.startswith("Clinical Trial") for p in pts):
        level = 2
    elif s.get("source") == "ClinicalTrials.gov" and "Results posted: yes" in text:
        level = 3
    elif "Review" in pts:
        level = 4
    else:
        level = 5
    return (level, min((q["rank"] for q in s.get("query", [])), default=99), s["study_id"])


def choose(ps: list, units_order: list, limit: int) -> tuple:
    """Round-robin over units (each unit's best study first) until the limit; returns (chosen, left out)."""
    per_unit = defaultdict(list)
    for p in ps:
        per_unit[p[0]["unit_id"]].append(p)
    for uid in per_unit:
        per_unit[uid].sort(key=lambda p: study_priority(p[1], p[2]))
    chosen, left = [], []
    for r in range(max((len(v) for v in per_unit.values()), default=0)):
        for uid in units_order:
            if r < len(per_unit.get(uid, [])):
                p = per_unit[uid][r]
                if r >= MAX_PER_UNIT:
                    left.append((p, f"more than {MAX_PER_UNIT} studies for this claim"))
                elif len(chosen) < limit:
                    chosen.append(p)
                else:
                    left.append((p, f"over the cap of {MAX_PAIRS} pairs"))
    return chosen, left


def header(s: dict) -> str:
    """The source's header line in the prompt; excerpts may quote it (e.g. publication types)."""
    return (f"MODERN SOURCE ({s.get('source', 'PubMed')}, {s['study_id']}, {s['publication_date']}, "
            f"{', '.join(s['publication_types'])}):")


def block(pid: str, u: dict, s: dict, text: str) -> str:
    claim = (f"{u['quote']}" + (f" (translation: {u['translation']})" if u.get("translation") else ""))
    return (f"=== PAIR {pid} ===\n"
            f"HISTORICAL CLAIM ({u['book']}, {u['entry_label']}): \"{claim}\"\n"
            f"  meaning: {u['claim_text']} · plant: {u['taxon']['accepted_name']} · part: {u['plant_part']} · "
            f"preparation: {', '.join(u['preparation'])} · route: {', '.join(u['route'])}\n"
            f"{header(s)}\n{text}")


def export_web(name_: str) -> None:
    if name_ == "pilot":
        raise SystemExit("The pilot is frozen (its replies and review use prompt 0.3); import only.")
    P = paths(name_)
    batch = BATCH.get(name_, DEFAULT_BATCH)
    ps = pairs(P)
    order = [json.loads(l)["unit_id"] for l in open(P["units"], encoding="utf-8")]
    print(f"{len(ps)} candidate pairs; choosing up to {MAX_PAIRS} (round by round) ...", flush=True)
    ps, left = choose(ps, order, MAX_PAIRS)
    ps.sort(key=lambda p: (order.index(p[0]["unit_id"]), study_priority(p[1], p[2])))
    folder = P["web"]
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for b in range(0, len(ps), batch):
        name = f"batch_{b // batch + 1:03d}"
        group = ps[b:b + batch]
        manifest[name] = {f"p{i:02d}": [u["unit_id"], s["study_id"]] for i, (u, s, _) in enumerate(group, 1)}
        prompt = PROMPT.format(n=len(group), blocks="\n\n".join(
            block(f"p{i:02d}", u, s, t) for i, (u, s, t) in enumerate(group, 1)))
        (folder / f"{name}.txt").write_text(prompt, encoding="utf-8")
        if (b // batch + 1) % 10 == 0:
            print(f"  {b // batch + 1} prompts written", flush=True)
        ans = folder / f"{name}.answer.txt"
        if not ans.exists():
            ans.write_text("", encoding="utf-8")
    (folder / "batches.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    with open(folder / "not_exported.jsonl", "w", encoding="utf-8") as fh:
        for (u, s, _), why in left:
            fh.write(json.dumps({"unit_id": u["unit_id"], "study_id": s["study_id"], "reason": why}) + "\n")
    units_with = len({u["unit_id"] for u, _, _ in ps})
    sizes = [len(t) for _, _, t in ps]
    print(f"{len(ps)} claim × source pairs in {len(manifest)} prompts of up to {batch} "
          f"({units_with} of {len(order)} claims get at least one source) · left out: {len(left)} "
          f"(listed in not_exported.jsonl) · average source text {sum(sizes) // max(len(sizes), 1)} characters")
    print(f"Sources: " + ", ".join(f"{k} {v}" for k, v in Counter(s.get("source", "PubMed") for _, s, _ in ps).most_common()))
    print(f"Folder: {folder.relative_to(ROOT)}/")


def check_excerpts(fields: dict, text: str) -> tuple:
    """Every non-unknown field needs an excerpt found in the abstract; otherwise it is voided."""
    good = {e.get("field") for e in fields.get("excerpts", []) if isinstance(e, dict) and found(e.get("text"), text)}
    bad = sorted({e.get("field") for e in fields.get("excerpts", []) if isinstance(e, dict)} - good)
    needed = []
    if fields.get("relevance") not in (None, "unclear"):
        needed.append("relevance")
    if fields.get("evidence_type") not in (None, "unknown"):
        needed.append("evidence_type")
    if (fields.get("outcome") or {}).get("value") not in (None, "unclear", "not_reported"):
        needed.append("outcome")
    needed += [k for k in FIELDS if ((fields.get("compatibility") or {}).get(k) or {}).get("value") not in (None, "unknown")]
    voided = [f for f in needed if f not in good]
    return voided, bad, len(good)


def code_view(r: dict) -> str:
    """The rules' result on the same scale as the model's overall view.
    An indirect study (another species, an isolated compound, a mixed product, another condition)
    cannot support or contradict this claim, so it counts as insufficient here. Its badge is unchanged."""
    if r["applicability"] == "not_relevant":
        return "unrelated"
    if r["applicability"] in ("unassessable", "indirect"):
        return "insufficient"
    return {"positive": "supports", "negative": "contradicts", "mixed": "mixed"}.get(r["finding"], "insufficient")


def model_view(f: dict, text: str) -> dict:
    o = f.get("overall") if isinstance(f.get("overall"), dict) else {}
    ex = o.get("excerpt") or ""
    return {"value": o.get("value", "missing"), "reason": o.get("reason"), "excerpt": ex,
            "excerpt_ok": found(ex, text),
            "note": "the model's own overall view: stored for comparison, never used for the result"}


REASSURING = re.compile(r"\b(low|no|non|not|without|minimal|negligible)[- ]?(acute |significant |apparent )?"
                        r"(toxic|toxicity|genotoxic|genotoxicity|cytotoxic|cytotoxicity|adverse|side effect)|non-?toxic|"
                        r"well[- ]tolerated|no serious|safe\b")
ALLERGY = re.compile(r"allerg|hypersensitiv|anaphyla|atopic|urticari|sensiti[sz]|coeliac|celiac|gluten|immunotherapy|contact dermatitis")
TOXIC = re.compile(r"poison|toxic|intoxicat|death|fatal|lethal|hepato|nephro|liver (damage|injury|failure)|renal failure|"
                   r"carcino|genotox|mutagen|teratogen|abortifacient|phototox|alkaloid")


def safety_category(what: str, excerpt: str, study_id: str) -> str:
    """Code's sorting of a reported harm (keywords, in this order). "reassuring" = the text says low or no harm:
    kept on record, never shown as a signal."""
    t, w = f"{what or ''} {excerpt or ''}".lower(), (what or "").lower()
    if REASSURING.search(w) and not re.search(r"\b(death|fatal|poison)", t):     # judged on the harm named
        return "reassuring"
    if study_id.startswith("ema:"):
        return "contraindication (EMA)"
    if re.search(r"phototox|photodermat|photosensiti", t):                        # light-triggered: toxicity
        return "toxicity"
    if ALLERGY.search(t):
        return "allergy"
    if TOXIC.search(t):
        return "toxicity"
    return "adverse effect"


def safety(f: dict, text: str, study_id: str = "") -> dict:
    """Harm reported in the source: a safety signal, kept apart from the evidence and never used by the rules."""
    h = f.get("harm") if isinstance(f.get("harm"), dict) else {}
    ok = found(h.get("excerpt"), text)
    yes = h.get("value") == "yes" and ok
    cat = safety_category(h.get("what"), h.get("excerpt"), study_id) if yes else None
    return {"harm": h.get("value", "missing"), "what": h.get("what"), "excerpt": h.get("excerpt"),
            "excerpt_ok": ok, "category": cat, "flag": yes and cat != "reassuring"}


def ema_use(f: dict) -> str:
    """Traditional-use indications in EMA monographs start "Traditional herbal medicinal product"."""
    if f.get("evidence_type") != "regulatory_monograph":
        return None
    t = norm(" ".join(e.get("text", "") for e in f.get("excerpts", []) if isinstance(e, dict) and e.get("field") == "outcome"))
    if "traditional herbal medicinal product" in t:
        return "traditional_use"
    return "well_established_use" if t else "use_type_unstated"


def export_new(name_: str) -> None:
    """After the units change (e.g. a Stage 2 fix): batches only for pairs that have no batch yet,
    appended after the existing ones. Each claim keeps at most MAX_PER_UNIT sources in all."""
    P = paths(name_)
    WEB = P["web"]
    manifest = json.load(open(WEB / "batches.json", encoding="utf-8"))
    have = {tuple(v) for pids in manifest.values() for v in pids.values()}
    per_unit = Counter(uid for uid, _ in have)
    ps = [p for p in pairs(P) if (p[0]["unit_id"], p[1]["study_id"]) not in have]
    order = [json.loads(l)["unit_id"] for l in open(P["units"], encoding="utf-8")]
    by_unit = defaultdict(list)
    for p in ps:
        by_unit[p[0]["unit_id"]].append(p)
    chosen = []
    for uid in order:
        room = MAX_PER_UNIT - per_unit[uid]
        chosen += sorted(by_unit.get(uid, []), key=lambda p: study_priority(p[1], p[2]))[:max(room, 0)]
    if not chosen:
        print("No new pairs: every unit already has its sources in a batch.")
        return
    batch, n = BATCH.get(name_, DEFAULT_BATCH), len(manifest)
    for b in range(0, len(chosen), batch):
        n += 1
        name = f"batch_{n:03d}"
        group = chosen[b:b + batch]
        manifest[name] = {f"p{i:02d}": [u["unit_id"], s["study_id"]] for i, (u, s, _) in enumerate(group, 1)}
        (WEB / f"{name}.txt").write_text(PROMPT.format(n=len(group), blocks="\n\n".join(
            block(f"p{i:02d}", u, s, t) for i, (u, s, t) in enumerate(group, 1))), encoding="utf-8")
        (WEB / f"{name}.answer.txt").write_text("", encoding="utf-8")
        print(f"{name}: {len(group)} new pairs → paste it like the others")
    (WEB / "batches.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"{len(chosen)} new pairs for {len({p[0]['unit_id'] for p in chosen})} units")


def export_missing(name_: str) -> None:
    """Pairs left out by cut-off replies (in batches that HAVE a reply) go into new batches at the end."""
    P = paths(name_)
    WEB = P["web"]
    manifest = json.load(open(WEB / "batches.json", encoding="utf-8"))
    ps = {(u["unit_id"], s["study_id"]): (u, s, t) for u, s, t in pairs(P)}
    answered, todo = set(), []
    for name, pids in manifest.items():
        ans = WEB / f"{name}.answer.txt"
        raw = ans.read_text(encoding="utf-8") if ans.exists() else ""
        js = parse(raw) if raw.strip() else None
        if js:
            got = {str(p.get("pid")) for p in js.get("pairs", []) if isinstance(p, dict)}
            answered |= {tuple(v) for k, v in pids.items() if k in got}
    for name, pids in manifest.items():
        ans = WEB / f"{name}.answer.txt"
        if ans.exists() and ans.read_text(encoding="utf-8").strip():
            todo += [tuple(v) for v in pids.values() if tuple(v) not in answered and tuple(v) not in todo]
    if not todo:
        print("No missing pairs in the batches answered so far.")
        return
    batch, n = BATCH.get(name_, DEFAULT_BATCH), len(manifest)
    for b in range(0, len(todo), batch):
        n += 1
        name = f"batch_{n:03d}"
        group = [ps[k] for k in todo[b:b + batch]]
        manifest[name] = {f"p{i:02d}": [u["unit_id"], s["study_id"]] for i, (u, s, _) in enumerate(group, 1)}
        (WEB / f"{name}.txt").write_text(PROMPT.format(n=len(group), blocks="\n\n".join(
            block(f"p{i:02d}", u, s, t) for i, (u, s, t) in enumerate(group, 1))), encoding="utf-8")
        (WEB / f"{name}.answer.txt").write_text("", encoding="utf-8")
        print(f"{name}: {len(group)} missing pairs → paste it like the others")
    (WEB / "batches.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


CORRECTIONS = HERE / "review" / "corrections.csv"
FLAGGED = HERE / "review" / "flagged_pairs.csv"


def load_corrections() -> dict:
    """stage3/review/corrections.csv: a person corrects a fact the model filled in (never the verdict); the
    rules then recompute the result. Only rows with confirmed = yes are applied."""
    out = defaultdict(list)
    if CORRECTIONS.exists():
        import csv
        for r in csv.DictReader(open(CORRECTIONS, encoding="utf-8")):
            if r.get("confirmed", "").strip().lower() == "yes":
                out[(r["unit_id"], r["study_id"])].append(r)
    if FLAGGED.exists():    # flagged pairs: Claude proposes a fact correction, a person marks your_check = ok
        import csv
        for r in csv.DictReader(open(FLAGGED, encoding="utf-8")):
            chk = r.get("your_check", "").strip().lower()
            if r["claude_says"] == "correct a fact" and chk in ("ok", "yes", "claude only"):
                by = ("Claude only (not checked by a person)" if chk == "claude only"
                      else "Claude (proposed), George (checked)")
                out[(r["unit_id"], r["study_id"])].append({**r, "by": by})
    return out


def apply_corrections(f: dict, uid: str, sid: str, corrections: dict) -> list:
    done = []
    for r in corrections.get((uid, sid), []):
        field = r["field"]
        if field in ("species", "condition", "therapeutic_action", "plant_part", "preparation", "route"):
            slot = f.setdefault("compatibility", {}).setdefault(field, {})
            old = slot.get("value")
            slot["value"] = r["corrected"]
        elif field in ("relevance", "evidence_type"):
            old = f.get(field)
            f[field] = r["corrected"]
            voided = (f.get("validation") or {}).get("fields_voided", [])
            if field in voided:                      # a person's correction replaces a voided answer
                voided.remove(field)
        else:
            continue
        done.append({"field": field, "model": old, "corrected": r["corrected"], "why": r["why"], "by": r["by"]})
    return done


def import_web(name_: str, label: str) -> None:
    P = paths(name_)
    corrections = load_corrections()
    WEB, OUT = P["web"], P["assessments"]
    version = PROMPT_VERSION.get(name_, DEFAULT_PROMPT_VERSION)
    ps = {(u["unit_id"], s["study_id"]): (u, s, t) for u, s, t in pairs(P)}
    manifest = json.load(open(WEB / "batches.json", encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    out, missing, stats = [], [], Counter()
    for name, pids in manifest.items():
        ans = WEB / f"{name}.answer.txt"
        raw = ans.read_text(encoding="utf-8") if ans.exists() else ""
        if not raw.strip():
            continue
        js = parse(raw)
        if not js:
            print(f"  {name}: reply is not valid JSON")
            continue
        if js.get("salvaged"):
            print(f"  {name}: reply was cut off; kept its {len(js['pairs'])} complete pairs of {len(pids)}")
        got = {str(p.get("pid")): p for p in js.get("pairs", []) if isinstance(p, dict)}
        for pid, (uid, sid) in pids.items():
            if (uid, sid) not in ps:                 # the unit or source is gone (a Stage 2 fix dropped the plant)
                stats["pairs whose unit no longer exists"] += 1
                continue
            u, s, text = ps[(uid, sid)]
            f = got.get(pid)
            if not f:
                missing.append((f"{name}/{pid}", uid, sid))
                continue
            voided, bad, nok = check_excerpts(f, header(s) + "\n" + text)
            f["validation"] = {"schema_ok": all(k in f for k in ("relevance", "evidence_type", "compatibility", "outcome")),
                               "excerpts_checked": nok + len(bad), "excerpts_failed": bad, "fields_voided": voided}
            f["ema_use"] = ema_use(f)
            fixes = apply_corrections(f, uid, sid, corrections)    # a person's corrections of facts, if any
            r = assess(f, u["identification"]["tier"])
            mv = model_view(f, text)
            cv = code_view(r)
            comparison = {"code_view": cv, "model_view": mv["value"], "agree": cv == mv["value"],
                          "flag_for_review": cv != mv["value"]}
            stats["voided fields"] += len(voided)
            out.append({"schema_version": "0.1", "assessment_id": f"{uid}|{sid}|v1", "unit_id": uid, "study_id": sid,
                        "claim_id": u["claim_id"], "species": u["taxon"]["accepted_name"],
                        "relevance": f.get("relevance"), "evidence_type": f.get("evidence_type"),
                        "compatibility": f.get("compatibility"), "outcome": f.get("outcome"),
                        "excerpts": f.get("excerpts"), "validation": f["validation"], **r,
                        "model_view": mv, "comparison": comparison, "safety": safety(f, header(s) + "\n" + text, sid),
                        "provenance": {"model": f"web: {label}", "prompt_version": version, "set": name_,
                                       "settings": {"temperature": 0},
                                       "input_hashes": {"study_text": hashlib.sha256(text.encode()).hexdigest()},
                                       "raw_response_file": str(ans.relative_to(ROOT)),
                                       "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                        "review": ({"status": "facts corrected by a person", "corrections": fixes}
                                   if fixes else {"status": "unreviewed"})})
    done = {(a["unit_id"], a["study_id"]) for a in out}
    missing = [m for m in missing if (m[1], m[2]) not in done]
    latest = {(a["unit_id"], a["study_id"]): a for a in out}   # a pair answered twice: the later reply wins
    out = list(latest.values())
    with open(OUT / "assessments.jsonl", "w", encoding="utf-8") as fh:
        for a in out:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")
    by_claim = defaultdict(list)
    for a in out:
        by_claim[a["claim_id"]].append(a)
    with open(OUT / "claim_summaries.jsonl", "w", encoding="utf-8") as fh:
        for cid, aa in sorted(by_claim.items()):
            flags = [{"study_id": a["study_id"], "category": a["safety"]["category"], "what": a["safety"]["what"]}
                     for a in aa if a["safety"]["flag"]]
            fh.write(json.dumps({"claim_id": cid, "species": aa[0]["species"], "studies": len(aa),
                                 **summarise(aa), "safety_flags": flags}, ensure_ascii=False) + "\n")
    by_species = defaultdict(dict)
    for a in out:
        if a["safety"]["flag"]:
            by_species[a["species"]][a["study_id"]] = {"study_id": a["study_id"], "category": a["safety"]["category"],
                                                       "what": a["safety"]["what"], "excerpt": a["safety"]["excerpt"]}
    with open(OUT / "safety_flags.jsonl", "w", encoding="utf-8") as fh:
        for sp, d in sorted(by_species.items()):
            fh.write(json.dumps({"species": sp, "flags": list(d.values())}, ensure_ascii=False) + "\n")
    if stats["pairs whose unit no longer exists"]:
        print(f"Set aside: {stats['pairs whose unit no longer exists']} answered pairs whose claim × plant unit no longer exists")
    print(f"{len(out)} of {len(ps)} pairs assessed · missing from replies: {len(missing)} · "
          f"fields voided by the excerpt check: {stats['voided fields']}")
    print("Applicability: " + ", ".join(f"{k} {v}" for k, v in Counter(a["applicability"] for a in out).most_common()))
    print("Badges: " + "; ".join(f"{k} ({v})" for k, v in Counter(a["badge"] for a in out).most_common(12)))
    if out:
        agree = sum(a["comparison"]["agree"] for a in out)
        print(f"Rules vs the model's own overall view: agree {agree}/{len(out)} ({agree / len(out):.0%}); "
              f"{len(out) - agree} flagged for review")
        for k, v in Counter((a["comparison"]["code_view"], a["comparison"]["model_view"]) for a in out
                            if not a["comparison"]["agree"]).most_common():
            print(f"  rules {k[0]} · model {k[1]}: {v}")
    harm = Counter(a["safety"]["harm"] for a in out)
    print("Safety, by category (code): " + ", ".join(f"{k} {v}" for k, v in Counter(
        a["safety"]["category"] for a in out if a["safety"]["category"]).most_common()) + " · 'reassuring' is not shown as a signal")
    print(f"Harm reported: {harm['yes']} pairs, {sum(a['safety']['flag'] for a in out)} with a checked excerpt · "
          f"species with a safety flag: {len(by_species)}" + (f" ({', '.join(sorted(by_species))})" if by_species else ""))
    print(f"Saved to {OUT.relative_to(ROOT)}/ (assessments.jsonl, claim_summaries.jsonl, safety_flags.jsonl)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export-web", action="store_true")
    ap.add_argument("--import-web", metavar="MODEL")
    ap.add_argument("--export-missing", action="store_true", help="pairs lost to cut-off replies, as new batches")
    ap.add_argument("--export-new", action="store_true", help="after the units change: batches for new pairs only")
    ap.add_argument("--set", default="pilot", choices=SETS)
    a = ap.parse_args()
    if a.export_new:
        export_new(a.set)
    elif a.export_missing:
        export_missing(a.set)
    elif a.export_web:
        export_web(a.set)
    elif a.import_web:
        import_web(a.set, a.import_web)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
