"""Read Bretschneider's identification of each matched Shennong drug (web chat, then code checks).

Usage:
  python3 historical_texts/shennong/bretschneider_ids.py --export-web       write the prompts to web/bretschneider/
  ... paste each batch_NN.txt into a NEW chat (Gemini 3.8 Flash, temp 0), the whole reply into batch_NN.answer.txt ...
  python3 historical_texts/shennong/bretschneider_ids.py --import-web "Gemini 3.8 Flash, web chat, temp 0"

Reads  historical_texts/shennong/bretschneider.json   (entries and unambiguous matches, bretschneider.py)
       historical_texts/shennong/entries.json
Writes historical_texts/shennong/bretschneider_ids.json

The model only reports what the text says, each with an exact quote: which plant is named for this drug,
and WHO names it (Bretschneider himself, or an author he quotes: Loureiro, Siebold, Henry, Smith ...),
and how firmly ("is", "probably", "doubtful"). Code then checks every quote against the OCR text
(whitespace and case ignored) and that the plant name is in its quote; a failed check drops the row.
Grades (used by Stage 2), set by code from the quote:
  strong  Bretschneider's own verdict on the drug, stated as fact or "probably": passage-specific scholarly
          evidence, like LSJ for Dioscorides. Code finds candidate verdicts, Claude proposes yes/no with a reason,
          and a person checks each row in review/bretschneider_strong.csv (your_check: ok, or yes/no to
          overrule); strong only when the answer is yes and the row was checked; until then medium
  medium  his reading of a Chinese illustration ("Good drawing representing Leonurus sibiricus": it identifies
          the picture, which can be wrong, as for 麻黃); how the name is used in 19th-century China ("at Peking the name pan hia is applied to ..."), or an
          author or list he quotes (Loureiro, Tatarinov, the Customs drug lists ...); a quote that opens with a
          source reference ("Tatar., Cat., 44:—") is credited to that source even if the model said Bretschneider
  weak    Japanese usage and Japanese works (Phon zo, So moku, Kwa wi, Siebold): the same characters can name
          another plant in Japanese; and anything "doubtful" Scholars' opinions (1895), not
the classic's words. Ambiguous matches (a tie between two entries) are left out until a person checks them.
"""
import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BRET = HERE / "bretschneider.json"
ENTRIES = HERE / "entries.json"
WEB = HERE / "web" / "bretschneider"
OUT = HERE / "bretschneider_ids.json"
BATCH = 10
TEXT_CAP = 20000                               # no entry is cut (the longest, 牡桂, is 16,600)
FIRM = ("identified", "probably", "doubtful")

PROMPT = """You are reading pages of E. Bretschneider, Botanicon Sinicum, Part III (1895), a study of the plants of the
ancient Chinese materia medica (the Shen nung pen ts'ao king, quoted as "Pen king", and the Pie lu). The text is
OCR of the printed book: the Chinese characters came out as garbage and there are OCR errors. Do not correct them.

For each DRUG below you get its Chinese name, its romanised name as Bretschneider spells it, and the part of his
book about it. Report which plant(s) the text identifies this drug as. Report only what the text says. For each
plant named as the identity of THIS drug (not plants only mentioned for comparison, e.g. "resembling the ..."):
  - "scientific_name": the Latin name as in the text (genus, or genus and species; keep the author if given)
  - "by": "Bretschneider" when he states it himself (e.g. "X is the common name of Plantago major at Peking",
     "represent Plantago", "is Glycyrrhiza"), else the author he quotes (e.g. "Loureiro", "Siebold", "Henry",
     "Smith", "Hanbury", "Tatarinov", "Phon zo zu set", "So moku") as named in the text
  - "certainty": "identified" (stated as fact), "probably" (probably, seems, perhaps, I think), or "doubtful"
     (doubts it, cannot be, unknown to me)
  - "quote": an exact piece of the text, copied character for character (OCR errors included), that contains the
     Latin name and shows who says it; 5 to 40 words
If the text identifies no plant for this drug, give an empty list. Do not use your own knowledge.

Reply with JSON only, no other text, in this form:
{"drugs": [{"id": "<drug id>", "plants": [{"scientific_name": "...", "by": "...", "certainty": "...", "quote": "..."}]}]}

"""


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()


REF = re.compile(r"\bP[.,]\s?,?\s?[XIVLxl1][XIVLxl1Uu]{0,4}\s?[a-e]?\s?[,.]\s?\d{1,3}")


def section(b: dict, slot: int) -> str:
    """The part of a Bretschneider entry about one drug: from its own heading line (or, when the OCR lost
    that heading, from just before its own "Pen king" quotation) to the next drug's "Pen king" quotation.
    Never from another drug's heading: entry 191 holds 忍冬 (jen tung, its heading kept) and 澤瀉 (tse sie,
    heading lost), and 澤瀉's prompt must not start with the honeysuckle."""
    text = b["text"]
    marks = [m.start() for m in re.finditer(r"Pen\s*king\s*[:;]?\s*[—–-]", text)]
    if not marks:
        return text[:TEXT_CAP]
    mark = marks[min(slot, len(marks) - 1)]
    start = 0 if mark < 400 else mark - 400
    if start:
        window = text[start:mark]
        refs = list(REF.finditer(window))
        if refs:                                   # its own heading ("lung tan. P., XIII, 50."): start there
            line_start = window.rfind("\n", 0, refs[-1].start()) + 1
            start += line_start
        else:
            start = mark
    end = marks[slot + 1] if slot + 1 < len(marks) else len(text)
    return text[start:end][:TEXT_CAP]


def items():
    B = json.load(open(BRET, encoding="utf-8"))
    by_num = {b["number"]: b for b in B["entries"]}
    E = {e["label"]: e for e in json.load(open(ENTRIES, encoding="utf-8"))["entries"]}
    out = []
    for lab, m in sorted(B["matches"].items(), key=lambda x: [int(p) for p in x[0].split(".")]):
        e = E[lab]
        if m["ambiguous"] or e["kind"] in ("animal", "mineral"):
            continue
        out.append({"id": f"shennong:{lab}", "label": lab, "name": e["name"], "romanised": m["pen_king_name"] or m["heading"],
                    "number": m["number"], "slot": m["slot"], "text": section(by_num[m["number"]], m["slot"])})
    return out


def export_web() -> None:
    WEB.mkdir(parents=True, exist_ok=True)
    its = items()
    n_batches = (len(its) + BATCH - 1) // BATCH
    for old in WEB.glob("batch_*.txt"):              # batches left from a larger earlier export
        num = int(re.search(r"batch_(\d+)", old.name).group(1))
        if num > n_batches and not (old.name.endswith(".answer.txt") and old.read_text(encoding="utf-8").strip()):
            old.unlink()
    for n in range(0, len(its), BATCH):
        name = f"batch_{n // BATCH + 1:02d}"
        body = PROMPT + "\n\n".join(
            f"=== DRUG {it['id']} · {it['name']} · Bretschneider's spelling: {it['romanised']} · his entry {it['number']}\n"
            f"{it['text']}" for it in its[n:n + BATCH])
        (WEB / f"{name}.txt").write_text(body, encoding="utf-8")
        ans = WEB / f"{name}.answer.txt"
        if not ans.exists():
            ans.write_text("", encoding="utf-8")
    print(f"{len(its)} drugs in {(len(its) + BATCH - 1) // BATCH} batches → {WEB.relative_to(ROOT)}/")


# A quote that opens with a source reference ("Cust. Med., No. 791 :—", "Tatar., Cat., 44:—") is that source's
# statement, quoted by Bretschneider, not his own; "Ch." and "Kiu huang" are Chinese illustrated works whose
# drawings he identifies (his own reading of an illustration)
SOURCES = [("Cust", "Chinese Customs drug lists"), ("Tatar", "Tatarinov"), ("Lour", "Loureiro"), ("Henry", "Henry"),
           ("Smith", "Smith"), ("P. Smith", "Smith"), ("Hanb", "Hanbury"), ("Sieb", "Siebold"), ("So moku", "So moku"),
           ("Phon zo", "Phon zo"), ("Kwa wi", "Kwa wi"), ("Franch", "Franchet"), ("Thunb", "Thunberg"),
           ("Williams", "Williams"), ("Parker", "Parker"), ("Hoffm", "Hoffmann & Schultes"), ("Debeaux", "Debeaux"),
           ("Forbes", "Forbes & Hemsley"), ("Maxim", "Maximowicz"), ("Bunge", "Bunge"), ("Przev", "Przewalski")]
JAPANESE = {"So moku", "Phon zo", "Kwa wi", "Siebold", "Thunberg", "Kaempfer", "Amen. exot", "Geerts",
            "Matsumura"}                                                 # works on Japanese usage
ILLUSTRATED = re.compile(r"^\W*(Ch[.,]|Chi[.,]|Kiu huang|Kin huang)", re.I)


def basis_of(quote: str) -> str:
    q = re.sub(r"\s+", " ", quote.lower())             # "In the  Peking mountains": OCR spacing
    if re.search(r"apothecar|drug-shop|drug shop|i (received|obtained|bought|got)|which i |specimens? (of|from)|"
                 r"the drug .{0,40}(received|obtained|from)|sold (in|at|under)", q):
        return "drug sample, 19th c."
    if re.search(r"\bjapan", q):
        return "name usage, Japan"
    if re.search(r"name .{0,40}(is|are) (applied|given)|common name|the people|is called|at peking|in the peking|"
                 r"vulgo|sinice|now (generally|commonly)|drug-shops|under the name", q):
        return "name usage, China (19th c.)"
    if ILLUSTRATED.search(quote) or re.search(r"drawing|figure|figured|represent|recognizable", q):
        return "illustration"
    return "verdict"


def source_of(quote: str):
    head = quote.strip()[:60]
    if not re.search(r"[:;]\s?[—–-]", head):
        return None
    for key, name in SOURCES:
        if head.lstrip(" ([").startswith(key):
            return name
    return None


def genus_in(genus: str, quote: str) -> bool:
    """The genus is in the quote, allowing for OCR ("(rentiana" for Gentiana): a word at least 80% alike."""
    from difflib import SequenceMatcher
    g = genus.lower().strip(".,")
    if genus.endswith(".") or len(g) < 4:              # abbreviated ("Gl. glabra", "O. spicatus"): the quote must
        return bool(re.search(r"\b" + re.escape(g) + r"\.", quote.lower()))   # have the abbreviation too
    return any(SequenceMatcher(None, g, w).ratio() >= 0.8 for w in re.findall(r"[a-z(]{4,}", quote.lower()))


def parse(raw: str):
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group()) if m else None


def import_web(model: str) -> None:
    its = {it["id"]: it for it in items()}
    rows, dropped, missing, stats = [], Counter(), [], Counter()
    for ans in sorted(WEB.glob("batch_*.answer.txt")):
        raw = ans.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        data = parse(raw)
        if not data:
            print(f"  {ans.name}: not JSON, skipped")
            continue
        for d in data.get("drugs", []):
            it = its.get(d.get("id"))
            if not it:
                continue
            stats["drugs answered"] += 1
            for p in d.get("plants", []):
                q, sci = str(p.get("quote", "")), str(p.get("scientific_name", "")).strip()
                why = None
                if norm(q) not in norm(it["text"]):
                    why = "quote not in the text"
                elif not sci or not genus_in(sci.split()[0], q):
                    why = "plant name not in its quote"
                elif sci.split()[0].endswith(".") and len(sci.split()) > 1 and norm(sci.split()[1]) not in norm(q):
                    why = "plant name not in its quote"
                elif p.get("certainty") not in FIRM:
                    why = "certainty not one of identified/probably/doubtful"
                if why:
                    dropped[why] += 1
                    continue
                by = str(p.get("by", "")).strip() or "unknown"
                if ILLUSTRATED.search(by):                  # "Ch.", "Kiu huang": Chinese illustrated works,
                    by = "Bretschneider"                    # read by Bretschneider (his reading of a drawing)
                src = source_of(q)
                if src and by.lower().startswith("bretschneider"):
                    by = src                                   # he quotes a source here: credited to it
                own = by.lower().startswith("bretschneider")
                japanese = any(by.lower().startswith(j.lower()) for j in JAPANESE)   # "Phon zo zu set" too
                basis = basis_of(q) if own else ("Japanese work" if japanese else "quoted author")
                firm = p["certainty"] != "doubtful"
                # strong: his own verdict, or his reading of a Chinese illustration, stated firmly; medium: how the
                # name is used in 19th-c. China, or an author he quotes; weak: Japanese usage or Japanese works,
                # and anything doubtful (Japanese can name other plants with the same characters)
                # an illustration identifies the picture, not the Han drug (for 麻黃 he reads a drawing as
                # Equisetum): medium, like the name's 19th-century usage
                # "strong" only after a person confirms it (review/bretschneider_strong.csv): code finds verdicts
                # with about 75% precision (2026-11-06 sample), too low for strong on its own
                grade = ("strong, to confirm" if own and firm and basis == "verdict" else
                         "medium" if firm and basis in ("illustration", "name usage, China (19th c.)", "quoted author",
                                                        "drug sample, 19th c.")
                         else "weak")
                rows.append({"entry": it["label"], "name": it["name"], "bretschneider_entry": it["number"],
                             "scientific_name": sci, "by": "Bretschneider" if own else by, "basis": basis,
                             "certainty": p["certainty"], "grade": grade, "quote": q, "model": model})
    # Review (option 3, 2026-11-06): Claude proposes yes/no with a reason for every proposed verdict; a person
    # checks each row (your_check: "ok" = agree, or "yes" / "no" to overrule). Strong only when the final answer
    # is yes AND a person checked the row; unchecked rows count as medium. Recorded as "AI-proposed, checked by
    # a person" in each row's review field.
    import csv
    review = HERE / "review" / "bretschneider_strong.csv"
    key = lambda e, plant, sent: (e, re.sub(r"\s+", " ", plant).strip(), re.sub(r"\s+", " ", sent).strip()[:60])
    old = {}
    if review.exists():
        for r in csv.DictReader(open(review, encoding="utf-8")):
            if "claude_says" in r:
                old[key(r["entry"], r["plant"], r["his_sentence"])] = r
    out_rows = []
    for r in rows:
        if r["grade"] != "strong, to confirm":
            continue
        k = key(r["entry"], r["scientific_name"], r["quote"])
        prev = old.get(k, {})
        says, why, check = prev.get("claude_says", ""), prev.get("why", ""), prev.get("your_check", "").strip().lower()
        final = says if check == "ok" else check if check in ("yes", "no") else ""
        r["grade"] = "strong" if final == "yes" else "medium"
        r["review"] = {"claude_says": says or "not proposed yet", "why": why, "person": check or "not checked",
                       "basis": "AI-proposed, checked by a person" if check else "AI-proposed, not yet checked"}
        out_rows.append([r["entry"], r["name"], re.sub(r"\s+", " ", r["scientific_name"]), re.sub(r"\s+", " ", r["quote"]),
                         says, why, prev.get("your_check", "")])
    review.parent.mkdir(exist_ok=True)
    with open(review, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["entry", "drug", "plant", "his_sentence", "claude_says", "why", "your_check"])
        w.writerows(out_rows)
    done = {r["entry"] for r in rows}
    missing = [i["label"] for i in its.values() if i["label"] not in done]
    OUT.write_text(json.dumps({
        "source": "E. Bretschneider, Botanicon Sinicum, Part III (1895), BHL item 23159 (OCR); public domain",
        "method": "web chat extraction, every quote checked against the OCR text (bretschneider_ids.py)",
        "imported": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rows": rows,
        "dropped": dict(dropped)}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{stats['drugs answered']} of {len(its)} drugs answered · {len(rows)} identifications kept "
          f"({dict(Counter(r['grade'] for r in rows))}) · dropped: {dict(dropped) or 'none'}")
    print(f"drugs with a kept identification: {len(done)} · without: {len(missing)}")
    print(f"Saved to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--export-web", action="store_true")
    ap.add_argument("--import-web", metavar="MODEL")
    a = ap.parse_args()
    if a.export_web:
        export_web()
    elif a.import_web:
        import_web(a.import_web)
    else:
        ap.print_help()
