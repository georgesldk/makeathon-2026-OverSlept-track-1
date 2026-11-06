"""Stage 3, step 3 (retrieval v2): find and store modern evidence for a set of units.
Retrieval only: nothing here judges whether a study supports a claim.

Usage:  python3 stage3/retrieve.py --set shared --dry-run     show the searches, no network
        python3 stage3/retrieve.py --set shared                run on your own computer
        options: --sources pubmed,plant,epmc,ctgov,ema,fulltext  (default: all)

Sets (stage3/sets.py): pilot2 = the 44 pilot units again, shared = the 670 groups both books share.
Needs: pip install openpyxl pypdf   (EMA table and monograph PDFs)

Sources, per plant (accepted name + WCVP synonyms + common names, see below):
  pubmed    plant × each claim concept, two searches (human/review studies; any study), 10 each
  plant     plant × clinical studies only (trial, RCT, meta-analysis, systematic review), 200, no
            concept: what Lardos et al. 2024 did. Code links a study to a claim when the study's
            MeSH headings fall in one of the claim's use groups (not the residual XY), or the
            claim's concept (name or MeSH synonym) is named in the title or abstract
  epmc      Europe PMC, plant × concept, 10: also searches open-access full text
  ctgov     ClinicalTrials.gov API v2, plant as intervention × concept, 10: registered trials
  ema       EMA herbal monographs: the HMPC table, matched by botanical name; for each match the
            final monograph PDF, sections 4.1 (indications) to 4.3, as the stored text
  fulltext  for kept open-access HUMAN studies (trials, systematic reviews, meta-analyses, observational;
            has a PMCID): the Results section from PubMed Central (NCBI efetch, db=pmc), first 1,500
            characters, added after the abstract. Lab and animal studies keep the abstract only.
Concept terms: the MeSH heading ([MeSH Terms] and [tiab]) plus its MeSH synonyms (entry terms of up to
  4 words without commas, at most 8), e.g. Menstruation-Inducing Agents + "Emmenagogues".
Common names: Dr. Duke's common names and Culpeper's entry names (tier A only), used only when unique to one species
  in Dr. Duke's table and at least 5 letters ("Plantain" is shared with bananas, so it is not used).
Screening (code): kept when the plant is named (scientific name, synonym, "G. species" or a common name)
  in the title, abstract, MeSH headings or trial interventions. A common-name-only match is kept but
  marked, and the extraction still has to confirm the species.
Writes  <set studies>/queries.jsonl, studies.jsonl · stage3/texts/<id>.txt · caches in stage3/cache/
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from sets import paths, SETS
from build_units import use_groups

CACHE = HERE / "cache"
TEXTS = HERE / "texts"
DUKE = ROOT / "common_name_sources" / "drduke" / "data"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/"
CTGOV = "https://clinicaltrials.gov/api/v2/studies"
EMA_TABLE = "https://www.ema.europa.eu/en/documents/report/medicines-output-herbal_medicines-report_en.xlsx"
EMA_SITE = "https://www.ema.europa.eu"
PAUSE = {"ncbi": 0.4, "epmc": 0.2, "ctgov": 0.3, "ema": 1.0}
PER_SEARCH, PER_PLANT_CLINICAL, RESULTS_CHARS, EMA_CHARS = 10, 200, 1500, 5000   # 200: paper test, recall 36/44 vs 11/44 at 40
TEXT_CAP = 6000                # a stored text longer than this (proceedings, long reviews) is cut, with a note
HUMAN_TYPES = {"Randomized Controlled Trial", "Clinical Trial", "Controlled Clinical Trial", "Clinical Trial, Phase I",
               "Clinical Trial, Phase II", "Clinical Trial, Phase III", "Clinical Trial, Phase IV", "Meta-Analysis",
               "Systematic Review", "Observational Study", "Pragmatic Clinical Trial", "Multicenter Study"}
MAX_SYNONYM_TERMS, MAX_PLANT_SYNONYMS = 8, 6
HUMAN_FILTER = ('("Clinical Trial"[pt] OR "Randomized Controlled Trial"[pt] OR "Meta-Analysis"[pt] '
                'OR "Systematic Review"[pt] OR "Review"[pt])')
CLINICAL_FILTER = ('("Clinical Trial"[pt] OR "Randomized Controlled Trial"[pt] OR "Meta-Analysis"[pt] '
                   'OR "Systematic Review"[pt])')
ALL_SOURCES = ("pubmed", "plant", "epmc", "ctgov", "ema", "fulltext")
CALLS = defaultdict(int)
T0 = time.time()


def step(msg: str) -> None:
    print(f"\n[{(time.time() - T0) / 60:5.1f} min] {msg}", flush=True)
SKIPPED = []
FAILS_IN_A_ROW = defaultdict(int)       # optional calls per service; after 3 the service is skipped for this run
GIVE_UP_AFTER = 20                      # some articles always fail; only a long run of failures means the service is down
# Every call: 3 tries (waits 5 s, 10 s); then that call is skipped and the run moves on.
# Skipped calls are not cached, so running the same command again asks only for them.
TRIES = 3


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def get(service: str, url: str, binary=False, missing_ok=False, optional=False):
    """Cached GET with retries. Error replies are never cached. 404 -> None when missing_ok.
    optional=True (extras such as full text): after 2 failed tries, skip it (None) instead of stopping."""
    d = CACHE / service
    d.mkdir(parents=True, exist_ok=True)
    path = d / hashlib.sha256(url.encode()).hexdigest()[:32]
    if path.exists():
        data = path.read_bytes()
        return None if data == b"<<404>>" else data
    if optional and FAILS_IN_A_ROW[service] >= GIVE_UP_AFTER:
        SKIPPED.append(url)
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "EthnoHack-OverSlept/0.2 (research; non-commercial)"})
    tries = 1 if optional else TRIES
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=10 if optional else 90, context=ctx()) as r:
                data = r.read()
            if service == "ncbi" and (b'"ERROR"' in data[:400] or b"<ERROR>" in data[:400]):
                raise RuntimeError(data[:200].decode(errors="replace"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 404 and missing_ok:
                path.write_bytes(b"<<404>>")
                return None
            err = f"HTTP {e.code}"
        except Exception as e:
            err = str(e)[:80]
        print(f"    {service} failed ({err}), try {attempt + 1}/{tries}", flush=True)
        if attempt + 1 < tries:
            time.sleep(3 if optional else 5 * (attempt + 1))
    else:
        SKIPPED.append(url)
        if optional:
            FAILS_IN_A_ROW[service] += 1
        print(f"    skipped this call, moving on (not cached; run the same command again later to fill it in)"
              + (f"; {service} full text failed {GIVE_UP_AFTER} times in a row, so full text is skipped for the rest of this run"
                 if optional and FAILS_IN_A_ROW[service] >= GIVE_UP_AFTER else ""), flush=True)
        return None
    path.write_bytes(data)
    FAILS_IN_A_ROW[service] = 0
    CALLS[service] += 1
    time.sleep(PAUSE.get(service, 0.3))
    return data


def ncbi(tool: str, params: dict) -> bytes:
    return get("ncbi", f"{EUTILS}{tool}.fcgi?" + urllib.parse.urlencode({**params, "tool": "ethnohack-overslept"}))


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def bare(name: str) -> str:
    parts = name.split()
    return " ".join(parts[:3] if len(parts) > 2 and parts[1] in ("×", "x") else parts[:2])


def wcvp_synonyms(names: list) -> dict:
    sys.path[:0] = [str(ROOT / "description_sources" / "bhl"), str(ROOT / "description_sources")]
    import source_bhl                              # one pass over WCVP, oldest synonyms first
    return source_bhl.synonyms(names)


def common_names(species: list, units: list) -> dict:
    """Unique common names per species: Dr. Duke's + Culpeper entry names, unique in Dr. Duke's table."""
    taxon = {r["FNFNUM"]: bare(r["TAXON"]) for r in csv.DictReader(open(DUKE / "FNFTAX.csv", encoding="latin-1"))}
    owners, spelled = defaultdict(set), {}
    for r in csv.DictReader(open(DUKE / "COMMON_NAMES.csv", encoding="latin-1")):
        if r["FNFNUM"] in taxon:
            owners[norm(r["CNNAM"])].add(taxon[r["FNFNUM"]])
            spelled.setdefault(norm(r["CNNAM"]), r["CNNAM"].strip().lower())
    out = {sp: set() for sp in species}
    for name, sps in owners.items():
        if len(sps) == 1 and len(name.replace(" ", "")) >= 5 and next(iter(sps)) in out:
            out[next(iter(sps))].add(spelled[name])
    for u in units:
        sp = bare(u["taxon"]["accepted_name"])
        if u["book"] == "culpeper" and sp in out and u["identification"]["tier"] == "A":
            n = norm(u["entry_label"])
            if len(n.replace(" ", "")) >= 5 and (not owners.get(n) or owners[n] == {sp}):
                out[sp].add(u["entry_label"].strip().lower())
    return {sp: sorted(v) for sp, v in out.items()}


def concept_terms(ui: str, D: dict) -> list:
    syn = [t for t in D[ui]["terms"] if "," not in t and len(t.split()) <= 4 and t.isascii()]
    return [D[ui]["name"]] + [t for t in dict.fromkeys(syn) if norm(t) != norm(D[ui]["name"])][:MAX_SYNONYM_TERMS]


def q(term: str) -> str:
    return '"' + term.replace('"', "") + '"'


def plant_terms(sp: str, syns: list, commons: list) -> list:
    return [sp] + syns[:MAX_PLANT_SYNONYMS] + commons


def pubmed_plant(sp, syns, commons, LK, D) -> str:
    terms = [f"{q(t)}[tiab]" for t in plant_terms(sp, syns, commons)]
    ui = next((u for u in LK.get(norm(sp), []) if any(t.startswith("B") for t in D[u]["trees"])
               and D[u]["name"].lower() == sp.lower()), None)       # only a heading for this very species
    if ui:
        terms.insert(0, f'{q(D[ui]["name"])}[MeSH Terms]')
    return "(" + " OR ".join(terms) + ")"


def pubmed_concepts(uis: tuple, D: dict) -> str:
    parts = []
    for ui in uis:
        parts.append(f'{q(D[ui]["name"])}[MeSH Terms]')
        parts += [f"{q(t)}[tiab]" for t in concept_terms(ui, D)]
    return "(" + " OR ".join(parts) + ")"


def or_terms(terms: list) -> str:
    return "(" + " OR ".join(q(t) for t in terms) + ")"


def parse_pubmed(xml: bytes) -> dict:
    out = {}
    for art in ET.fromstring(xml).iter("PubmedArticle"):
        pmid = art.findtext(".//MedlineCitation/PMID")
        a = art.find(".//Article")
        if a is None:
            continue
        abstract = " ".join(((t.get("Label") + ": ") if t.get("Label") else "") + "".join(t.itertext())
                            for t in a.findall(".//Abstract/AbstractText"))
        ids = {i.get("IdType"): i.text for i in art.findall(".//PubmedData/ArticleIdList/ArticleId")}
        date = a.find(".//Journal/JournalIssue/PubDate")
        out[pmid] = {
            "title": "".join(a.find("ArticleTitle").itertext()) if a.find("ArticleTitle") is not None else "",
            "abstract": abstract.strip(), "journal": a.findtext(".//Journal/Title"),
            "publication_date": ("-".join(x for x in (date.findtext("Year"), date.findtext("Month"), date.findtext("Day")) if x)
                                 if date is not None and date.findtext("Year") else (date.findtext("MedlineDate") if date is not None else None)),
            "publication_types": [p.text for p in art.findall(".//PublicationTypeList/PublicationType")],
            "mesh_headings": [m.text for m in art.findall(".//MeshHeadingList/MeshHeading/DescriptorName")],
            "doi": ids.get("doi"), "pmcid": ids.get("pmc")}
    return out


def mentions(text_fields: dict, names: list, commons: list) -> list:
    where = []
    for field, text in text_fields.items():
        t = (text or "").lower()
        hit = None
        for n in names:
            g, *rest = n.lower().split()
            if n.lower() in t or (rest and f"{g[0]}. {' '.join(rest)}" in t):
                hit = {"name": n, "where": field, "kind": "scientific"}
                break
        if not hit:
            tn = " " + norm(t) + " "
            c = next((c for c in commons if f" {norm(c)} " in tn), None)
            if c:
                hit = {"name": c, "where": field, "kind": "common"}
        if hit:
            where.append(hit)
    return where


def results_section(pmcid: str) -> str:
    """The Results section of an open-access article, from PubMed Central (NCBI efetch, db=pmc, JATS XML).
    Articles outside the open-access subset come back without a body: then nothing is added."""
    xml = get("ncbi", f"{EUTILS}efetch.fcgi?" + urllib.parse.urlencode(
        {"db": "pmc", "id": pmcid.replace("PMC", ""), "retmode": "xml", "tool": "ethnohack-overslept"}), optional=True)
    if not xml:
        return ""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return ""
    for sec in root.iter("sec"):
        title = (sec.findtext("title") or "").strip().lower()
        if sec.get("sec-type", "").lower().startswith("result") or title.startswith("result"):
            text = re.sub(r"\s+", " ", " ".join(p for p in sec.itertext())).strip()
            return text[:RESULTS_CHARS]
    return ""


def ctgov_text(s: dict) -> tuple:
    p = s.get("protocolSection", {})
    ident, desc = p.get("identificationModule", {}), p.get("descriptionModule", {})
    design, status = p.get("designModule", {}), p.get("statusModule", {})
    interventions = p.get("armsInterventionsModule", {}).get("interventions", [])
    conds = p.get("conditionsModule", {}).get("conditions", [])
    lines = [ident.get("officialTitle") or ident.get("briefTitle", ""), "",
             f"Registered trial {ident.get('nctId')}. Status: {status.get('overallStatus')}. "
             f"Study type: {design.get('studyType')}. Phases: {', '.join(design.get('phases', []) or ['n/a'])}. "
             f"Allocation: {design.get('designInfo', {}).get('allocation', 'n/a')}. "
             f"Results posted: {'yes' if s.get('hasResults') else 'no'}.",
             "Conditions: " + "; ".join(conds),
             "Interventions: " + "; ".join(f"{i.get('name')} ({i.get('type')}): {i.get('description', '')[:300]}" for i in interventions),
             "Summary: " + desc.get("briefSummary", ""),
             "Description: " + desc.get("detailedDescription", "")[:1500]]
    for o in (s.get("resultsSection", {}).get("outcomeMeasuresModule", {}).get("outcomeMeasures", []) or [])[:4]:
        stats = "; ".join(f"p={a.get('pValue')} ({a.get('statisticalMethod', '')})" for a in o.get("analyses", [])[:2] if a.get("pValue"))
        lines.append(f"Result, {o.get('type', '').lower()} outcome: {o.get('title')}" + (f": {stats}" if stats else ""))
    inter = " ".join(f"{i.get('name')} {i.get('description', '')}" for i in interventions)
    pmids = [r.get("pmid") for r in p.get("referencesModule", {}).get("references", []) if r.get("type") == "RESULT" and r.get("pmid")]
    return "\n".join(lines).strip(), inter, conds, pmids


def ema_table() -> list:
    import openpyxl
    data = get("ema", EMA_TABLE, binary=True)
    if not data:
        return []
    ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    h = next(i for i, r in enumerate(rows) if any("botanical" in str(c or "").lower() for c in r))
    head = [str(c or "").strip().lower() for c in rows[h]]

    def col(*keys):
        return next((i for i, c in enumerate(head) if all(k in c for k in keys)), None)
    cols = {"latin": col("latin"), "botanical": col("botanical"), "common": col("common"),
            "area": col("therapeutic"), "status": col("status"), "outcome": col("outcome"), "url": col("url")}
    if cols["botanical"] is None or cols["latin"] is None:
        raise SystemExit(f"EMA table: columns not recognised: {head}")
    out = []
    for r in rows[h + 1:]:
        get_ = lambda k: (str(r[cols[k]]).strip() if cols[k] is not None and r[cols[k]] is not None else "")
        if get_("latin"):
            out.append({k: get_(k) for k in cols})
    return out


def ema_monograph_text(entry: dict) -> tuple:
    """The final monograph PDF linked from the substance page -> sections 4.1 to 4.3 as text."""
    from pypdf import PdfReader
    slug = re.sub(r"[^a-z0-9]+", "-", entry["latin"].lower()).strip("-")
    page_url = entry["url"] if entry["url"].startswith("http") else f"{EMA_SITE}/en/medicines/herbal/{slug}"
    html = (get("ema", page_url, missing_ok=True) or b"").decode("utf-8", errors="replace")
    links = re.findall(r'href="([^"]+?herbal-monograph/[^"]+?\.pdf)"', html)
    final = [l for l in links if "/final-" in l and "superseded" not in l and "draft" not in l]
    if not final:
        return page_url, None, ""
    pdf_url = final[0] if final[0].startswith("http") else EMA_SITE + final[0]
    pdf = get("ema", pdf_url, binary=True, missing_ok=True)
    if not pdf:
        return page_url, pdf_url, ""
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages[:8])
    text = re.sub(r"[ \t]+", " ", text)
    m = re.search(r"4\.1\.?\s*Therapeutic indications(.*?)(4\.4\.?\s*Special warnings|$)", text, flags=re.S | re.I)
    return page_url, pdf_url, (m.group(1).strip()[:EMA_CHARS] if m else "")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True, choices=[s for s in SETS if s != "pilot"])
    ap.add_argument("--sources", default=",".join(ALL_SOURCES))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    src = set(a.sources.split(","))
    P = paths(a.set)
    units = [json.loads(l) for l in open(P["units"], encoding="utf-8")]
    mesh = json.load(gzip.open(ROOT / "reference_sources/mesh/mesh_index.json.gz", "rt", encoding="utf-8"))
    D, LK = mesh["descriptors"], mesh["lookup"]
    tree_name = {t: d["name"] for d in D.values() for t in d["trees"]}
    groups = defaultdict(list)                       # (species, concept uis) -> units
    by_species = defaultdict(list)
    for u in units:
        sp = bare(u["taxon"]["accepted_name"])
        by_species[sp].append(u)
        uis = tuple(sorted(c["ui"] for c in u["condition_concepts"] + u["action_concepts"] + u["other_concepts"]))
        if uis:
            groups[(sp, uis)].append(u)
    species = sorted(by_species)
    commons = common_names(species, units)
    syn = {s: [] for s in species} if a.dry_run else wcvp_synonyms(species)
    print(f"Set {a.set}: {len(units)} units · {len(species)} plants · {len(groups)} plant × concept groups · "
          f"common names for {sum(1 for v in commons.values() if v)} plants · sources: {', '.join(sorted(src))}")

    searches = []
    for (sp, uis), us in sorted(groups.items()):
        ids = [u["unit_id"] for u in us]
        cterms = [t for ui in uis for t in concept_terms(ui, D)]
        pterms = plant_terms(sp, syn.get(sp, []), commons.get(sp, []))
        base = f"{pubmed_plant(sp, syn.get(sp, []), commons.get(sp, []), LK, D)} AND {pubmed_concepts(uis, D)}"
        info = {"species": sp, "concepts": [D[ui]["name"] for ui in uis], "unit_ids": ids}
        if "pubmed" in src:
            searches += [{**info, "source": "pubmed", "kind": "human_or_review", "query": f"{base} AND {HUMAN_FILTER}", "n": PER_SEARCH},
                         {**info, "source": "pubmed", "kind": "any", "query": base, "n": PER_SEARCH}]
        if "epmc" in src:
            searches.append({**info, "source": "epmc", "kind": "full_text_search",
                             "query": f"{or_terms(pterms)} AND {or_terms(cterms)}", "n": PER_SEARCH})
        if "ctgov" in src:
            searches.append({**info, "source": "ctgov", "kind": "registered_trials", "query":
                             {"query.intr": " OR ".join(q(t) for t in pterms), "query.term": " OR ".join(q(t) for t in cterms)},
                             "n": PER_SEARCH})
    if "plant" in src:
        for sp in species:
            searches.append({"species": sp, "concepts": [], "unit_ids": [], "source": "pubmed", "kind": "plant_clinical",
                             "query": f"{pubmed_plant(sp, syn.get(sp, []), commons.get(sp, []), LK, D)} AND {CLINICAL_FILTER}",
                             "n": PER_PLANT_CLINICAL})
    if a.dry_run:
        for s in [x for x in searches if x["species"] == searches[0]["species"]][:6]:
            print(f"\n{s['species']} · {', '.join(s['concepts']) or '(all clinical)'} · {s['source']} {s['kind']}\n  {s['query']}")
        k = defaultdict(int)
        for s in searches:
            k[f"{s['source']} {s['kind']}"] += 1
        print("\nSearches: " + ", ".join(f"{v} {n}" for n, v in sorted(k.items())) + (" · plus the EMA table" if "ema" in src else ""))
        print("Common names found, e.g.: " + "; ".join(f"{sp}: {', '.join(v)}" for sp, v in list(commons.items()) if v)[:400])
        print("Run without --dry-run on your computer.")
        return

    step(f"Step 1/5: {len(searches)} searches")
    out_dir = P["studies"]
    out_dir.mkdir(parents=True, exist_ok=True)
    TEXTS.mkdir(exist_ok=True)
    found = defaultdict(lambda: {"units": set(), "queries": [], "species": None})
    other = {}                                       # non-PubMed records: id -> record
    with open(out_dir / "queries.jsonl", "w", encoding="utf-8") as f:
        for i, s in enumerate(searches, 1):
            ids = []
            if s["source"] == "pubmed":
                raw = ncbi("esearch", {"db": "pubmed", "term": s["query"], "retmax": s["n"],
                                       "sort": "relevance", "retmode": "json"})
                r = json.loads(raw)["esearchresult"] if raw else {"skipped": True}
                count, ids = int(r.get("count", 0)), [f"pmid:{x}" for x in r.get("idlist", [])]
            elif s["source"] == "epmc":
                raw = get("epmc", f"{EPMC}search?" + urllib.parse.urlencode(
                    {"query": s["query"], "format": "json", "resultType": "core", "pageSize": s["n"]}))
                r = json.loads(raw) if raw else {"skipped": True}
                count = int(r.get("hitCount", 0))
                for x in r.get("resultList", {}).get("result", []):
                    if x.get("pmid"):
                        ids.append(f"pmid:{x['pmid']}")
                    else:
                        sid = f"epmc:{x.get('source')}:{x.get('id')}"
                        ids.append(sid)
                        other[sid] = {"source": "Europe PMC", "title": x.get("title", ""), "abstract": x.get("abstractText", ""),
                                      "journal": (x.get("journalInfo") or {}).get("journal", {}).get("title") or x.get("bookOrReportDetails", {}).get("publisher"),
                                      "publication_date": x.get("firstPublicationDate") or x.get("pubYear"),
                                      "publication_types": (x.get("pubTypeList") or {}).get("pubType", []),
                                      "mesh_headings": [m.get("descriptorName") for m in (x.get("meshHeadingList") or {}).get("meshHeading", [])],
                                      "doi": x.get("doi"), "pmcid": x.get("pmcid"), "extra_text": {}}
            else:
                raw = get("ctgov", f"{CTGOV}?" + urllib.parse.urlencode({**s["query"], "pageSize": s["n"], "format": "json"}))
                r = json.loads(raw) if raw else {"skipped": True}
                count = r.get("totalCount") or len(r.get("studies", []))
                for st in r.get("studies", []):
                    nct = st["protocolSection"]["identificationModule"]["nctId"]
                    text, inter, conds, pmids = ctgov_text(st)
                    ids.append(f"nct:{nct}")
                    other[f"nct:{nct}"] = {"source": "ClinicalTrials.gov", "title": st["protocolSection"]["identificationModule"].get("briefTitle", ""),
                                           "abstract": text, "journal": None,
                                           "publication_date": st["protocolSection"].get("statusModule", {}).get("startDateStruct", {}).get("date"),
                                           "publication_types": ["Registered trial"], "mesh_headings": conds, "doi": None,
                                           "pmcid": None, "extra_text": {"interventions": inter}, "result_pmids": pmids,
                                           "full_text_ready": True}
            s.update(run_at=now(), result_count=count, ids=ids, skipped=bool(r.get("skipped")) if isinstance(r, dict) else False)
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
            for rank, sid in enumerate(ids, 1):
                found[sid]["units"] |= set(s["unit_ids"])
                found[sid]["species"] = s["species"]
                found[sid]["queries"].append({"source": s["source"], "query_kind": s["kind"], "species": s["species"],
                                              "concepts": s["concepts"], "rank": rank, "result_count": count})
            print(f"  [{i}/{len(searches)}] {s['species']} · {', '.join(s['concepts'])[:40] or 'clinical'} · "
                  f"{s['source']} {s['kind']}: {count} found, {len(ids)} kept for reading")

    # fetch PubMed records
    pmids = sorted(x.split(":")[1] for x in found if x.startswith("pmid:"))
    step(f"Step 2/5: fetching {len(pmids)} PubMed records in {(len(pmids) + 99) // 100} batches of 100")
    recs = {}
    for b in range(0, len(pmids), 100):
        print(f"  records {b + 1}-{min(b + 100, len(pmids))} of {len(pmids)}", flush=True)
        raw = ncbi("efetch", {"db": "pubmed", "id": ",".join(pmids[b:b + 100]), "rettype": "abstract", "retmode": "xml"})
        if raw:
            recs.update({f"pmid:{k}": {**v, "source": "PubMed", "extra_text": {}} for k, v in parse_pubmed(raw).items()})
    recs.update(other)

    step("Step 3/5: linking plant-level clinical studies to claims")
    # plant-level clinical studies -> units, by use group or concept named in the text
    for sid, fo in found.items():
        if not any(qq["query_kind"] == "plant_clinical" for qq in fo["queries"]) or sid not in recs:
            continue
        rec = recs[sid]
        text = norm(rec["title"] + " " + rec["abstract"])
        study_groups = set()
        for m in rec["mesh_headings"]:
            for ui in LK.get(norm(m), []):
                study_groups |= set(use_groups(ui, D, tree_name)[0])
        study_groups.discard("XY")
        for u in by_species[fo["species"]]:
            uis = [c["ui"] for c in u["condition_concepts"] + u["action_concepts"] + u["other_concepts"]]
            named = any(f" {norm(t)} " in f" {text} " for ui in uis for t in concept_terms(ui, D))
            if named or (set(u["use_groups"]) - {"XY"}) & study_groups:
                fo["units"].add(u["unit_id"])
                fo.setdefault("link_reason", {})[u["unit_id"]] = "concept named in the study" if named else "shared use group (MeSH)"

    step("Step 4/5: EMA monographs" if "ema" in src else "Step 4/5: EMA skipped")
    # EMA monographs
    ema_n = 0
    if "ema" in src:
        sp_syn = {sp: {sp.lower()} | {bare(x).lower() for x in syn.get(sp, [])} for sp in species}
        for e in ema_table():
            names = {bare(x.strip()).lower() for x in re.split(r"[;,\n]| and/or | or ", e["botanical"]) if x.strip()}
            hits = [sp for sp, ss in sp_syn.items() if ss & names]
            if not hits:
                continue
            page, pdf, text = ema_monograph_text(e)
            sid = "ema:" + re.sub(r"[^a-z0-9]+", "-", e["latin"].lower()).strip("-")
            ema_n += 1
            recs[sid] = {"source": "EMA", "title": f"EU herbal monograph: {e['latin']} ({e['botanical']})",
                         "abstract": text or "", "journal": "European Medicines Agency, HMPC", "publication_date": None,
                         "publication_types": ["Regulatory monograph"], "mesh_headings": [e.get("area", "")],
                         "doi": None, "pmcid": None, "extra_text": {}, "full_text_ready": True,
                         "ema": {"latin": e["latin"], "botanical": e["botanical"], "common": e["common"], "area": e["area"],
                                 "status": e["status"], "outcome": e["outcome"], "page": page, "pdf": pdf}}
            for sp in hits:
                found[sid]["units"] |= {u["unit_id"] for u in by_species[sp]}
                found[sid]["species"] = sp
                found[sid]["queries"].append({"source": "ema", "query_kind": "monograph_by_botanical_name", "species": sp,
                                              "concepts": [], "rank": 1, "result_count": 1})
            print(f"  EMA: {e['latin']} → {', '.join(hits)} ({'sections 4.1-4.3 read' if text else 'no final monograph text found'})")

    kept = rejected = 0
    todo = sorted(found)
    step(f"Step 5/5: screening {len(todo)} records, adding Results sections of open-access human studies")
    with open(out_dir / "studies.jsonl", "w", encoding="utf-8") as f:
        for n_done, sid in enumerate(todo, 1):
            if n_done % 250 == 0 or n_done == len(todo):
                print(f"  {n_done}/{len(todo)} records · kept so far {kept}", flush=True)
            rec = recs.get(sid)
            if not rec:
                continue
            fo = found[sid]
            sp = fo["species"]
            names = [sp] + [bare(x) for x in syn.get(sp, [])]
            fields = {"title": rec["title"], "abstract": rec["abstract"], **rec.get("extra_text", {}),
                      "mesh": " ; ".join(m for m in rec["mesh_headings"] if m)}
            where = [{"name": sp, "where": "ema botanical name", "kind": "scientific"}] if rec["source"] == "EMA" else mentions(fields, names, commons.get(sp, []))
            if not rec["abstract"]:
                decision, reason = "rejected", "no abstract or text"
            elif not where:
                decision, reason = "rejected", "the plant is not named in the title, abstract, MeSH headings or interventions"
            elif not fo["units"]:
                decision, reason = "rejected", "a clinical study of the plant, but no claim in this set shares its use group or concept"
            else:
                weak = all(w["kind"] == "common" for w in where)
                decision = "kept"
                reason = ("plant named only by a common name, in " if weak else "plant named in ") + ", ".join(sorted({w["where"] for w in where}))
            text = f"{rec['title']}\n\n{rec['abstract']}".strip()
            if (decision == "kept" and "fulltext" in src and rec.get("pmcid") and not rec.get("full_text_ready")
                    and set(rec["publication_types"]) & HUMAN_TYPES):
                res = results_section(rec["pmcid"])
                if res:
                    text += f"\n\nRESULTS (open-access full text, PubMed Central, first {RESULTS_CHARS} characters): {res}"
            if len(text) > TEXT_CAP:
                text = text[:TEXT_CAP].rstrip() + f" [text cut at {TEXT_CAP} characters]"
            tpath = TEXTS / (re.sub(r"[^A-Za-z0-9]+", "_", sid) + ".txt")
            tpath.write_text(text, encoding="utf-8")
            kept += decision == "kept"
            rejected += decision == "rejected"
            f.write(json.dumps({
                "schema_version": "0.2", "study_id": sid, "source": rec["source"],
                "other_ids": {"pmid": sid[5:] if sid.startswith("pmid:") else None, "pmcid": rec.get("pmcid"),
                              "doi": rec.get("doi"), "nct": sid[4:] if sid.startswith("nct:") else None,
                              "result_pmids": rec.get("result_pmids")},
                "title": rec["title"], "journal": rec["journal"], "publication_date": rec["publication_date"],
                "publication_types": rec["publication_types"], "taxa_mentioned": where,
                "mesh_headings": rec["mesh_headings"], "ema": rec.get("ema"),
                "text": {"kind": "monograph sections 4.1-4.3" if rec["source"] == "EMA" else "trial registration" if sid.startswith("nct:")
                         else "abstract + results" if "RESULTS (open-access" in text else "abstract",
                         "locator": str(tpath.relative_to(ROOT)), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                         "licence_note": "publisher or registry copyright; kept outside git"},
                "query": fo["queries"], "found_for_units": sorted(fo["units"]), "link_reason": fo.get("link_reason", {}),
                "screening": {"decision": decision, "reason": reason, "by": "code", "at": now()},
                "retrieved_at": now()}, ensure_ascii=False) + "\n")
    by_src = defaultdict(int)
    for l in open(out_dir / "studies.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if r["screening"]["decision"] == "kept":
            by_src[r["source"]] += 1
    step("Done")
    print(f"{kept + rejected} distinct records · {kept} kept ({', '.join(f'{k} {v}' for k, v in sorted(by_src.items()))}) · "
          f"{rejected} rejected · EMA monographs matched: {ema_n} · new calls: {dict(CALLS)}"
          + (f" · calls skipped after errors: {len(SKIPPED)}" if SKIPPED else ""))
    if SKIPPED:
        print(f"{len(SKIPPED)} calls were skipped after errors. Run the same command again later: "
              "finished calls come from the cache, and only the skipped ones are asked again.")
    print(f"Saved: {out_dir.relative_to(ROOT)}/queries.jsonl, studies.jsonl, stage3/texts/")


if __name__ == "__main__":
    main()
