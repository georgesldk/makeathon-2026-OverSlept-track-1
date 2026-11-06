"""Stage 3, step 3, first version: PubMed only. Kept because it made the frozen pilot set; every later
set uses stage3/retrieve.py (retrieval v2).
Find and store PubMed studies for the pilot units (StudyRecord, contract §3).
Retrieval only: nothing here judges whether a study supports a claim.

Usage:  python3 stage3/retrieve_pubmed.py --dry-run    show the queries, no network
        python3 stage3/retrieve_pubmed.py              run on your own computer (needs NCBI)

For each plant × medical concept in stage3/units/pilot.jsonl:
  plant    = accepted name [tiab] + its MeSH heading if MeSH has one for this very species (not its
             genus) + up to 6 WCVP synonyms [tiab]
  concept  = each MeSH term of the claim, as [MeSH Terms] and as [tiab]
  two searches, newest-relevance order:
    a. human and review studies: Clinical Trial, RCT, Meta-Analysis, Systematic Review, Review  (up to 10)
    b. any study                                                                               (up to 10)
Every PubMed record found is fetched once (title, abstract, journal, date, publication types,
MeSH headings, DOI, PMCID) and screened by code: kept only if the plant (accepted name, a synonym,
or "G. species") is named in its title, abstract or MeSH headings; otherwise rejected, with the reason.
Writes stage3/studies/queries.jsonl (every query: string, date, count, PMIDs in order),
       stage3/studies/studies.jsonl (StudyRecord), stage3/texts/pmid_<n>.txt (title + abstract).
Replies are cached in stage3/cache/ncbi/; NCBI's limit (3 requests a second without a key) is respected.
"""
import argparse
import gzip
import hashlib
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = HERE / "cache" / "ncbi"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
PAUSE = 0.4
PER_SEARCH = 10
HUMAN_FILTER = ('("Clinical Trial"[pt] OR "Randomized Controlled Trial"[pt] OR "Meta-Analysis"[pt] '
                'OR "Systematic Review"[pt] OR "Review"[pt])')
CALLS = [0]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def ncbi(tool: str, params: dict) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps([tool, params], sort_keys=True).encode()).hexdigest()[:32]
    path = CACHE / f"{tool}_{key}"
    if path.exists():
        return path.read_bytes()
    q = urllib.parse.urlencode({**params, "tool": "ethnohack-overslept"})
    req = urllib.request.Request(f"{EUTILS}{tool}.fcgi?{q}", headers={"User-Agent": "EthnoHack-OverSlept/0.1"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx()) as r:
                data = r.read()
            if b'"ERROR"' in data[:400] or b"<ERROR>" in data[:400]:
                raise RuntimeError(data[:200].decode(errors="replace"))
            break
        except Exception as e:
            print(f"    NCBI {tool} failed ({str(e)[:80]}), retry {attempt + 1}/3")
            time.sleep(5 * (attempt + 1))
    else:
        raise SystemExit("NCBI is not answering; rerun later (finished searches are cached).")
    path.write_bytes(data)
    CALLS[0] += 1
    time.sleep(PAUSE)
    return data


def bare(name: str) -> str:
    """'Daucus carota L.' -> 'Daucus carota'; keeps hybrids."""
    parts = name.split()
    return " ".join(parts[:3] if len(parts) > 2 and parts[1] in ("×", "x") else parts[:2])


def synonyms(names: list) -> dict:
    sys.path[:0] = [str(ROOT / "description_sources" / "bhl"), str(ROOT / "description_sources")]
    import source_bhl                              # one pass over WCVP, oldest synonyms first
    return source_bhl.synonyms(names)


def plant_clause(sp: str, syns: list, mesh_lookup: dict, D: dict) -> str:
    terms = [f'"{sp}"[tiab]']
    # only a MeSH heading for this very species: MeSH often files a species under its genus
    # ("Achillea millefolium" -> Achillea), which would silently bring in other species
    ui = next((u for u in mesh_lookup.get(re.sub(r"[^a-z0-9]+", " ", sp.lower()).strip(), [])
               if any(t.startswith("B") for t in D[u]["trees"]) and D[u]["name"].lower() == sp.lower()), None)
    if ui:
        terms.insert(0, f'"{D[ui]["name"]}"[MeSH Terms]')
    terms += [f'"{s}"[tiab]' for s in syns]
    return "(" + " OR ".join(terms) + ")"


def concept_clause(concepts: list) -> str:
    return "(" + " OR ".join(f'"{c["name"]}"[MeSH Terms] OR "{c["name"]}"[tiab]' for c in concepts) + ")"


def parse_records(xml: bytes) -> dict:
    out = {}
    for art in ET.fromstring(xml).iter("PubmedArticle"):
        pmid = art.findtext(".//MedlineCitation/PMID")
        a = art.find(".//Article")
        abstract = " ".join(((t.get("Label") + ": ") if t.get("Label") else "") + "".join(t.itertext())
                            for t in a.findall(".//Abstract/AbstractText")) if a is not None else ""
        ids = {i.get("IdType"): i.text for i in art.findall(".//PubmedData/ArticleIdList/ArticleId")}
        date = a.find(".//Journal/JournalIssue/PubDate") if a is not None else None
        out[pmid] = {
            "title": "".join(a.find("ArticleTitle").itertext()) if a is not None and a.find("ArticleTitle") is not None else "",
            "abstract": abstract.strip(),
            "journal": a.findtext(".//Journal/Title") if a is not None else None,
            "publication_date": "-".join(x for x in (date.findtext("Year"), date.findtext("Month"), date.findtext("Day")) if x)
                                if date is not None and date.findtext("Year") else (date.findtext("MedlineDate") if date is not None else None),
            "publication_types": [p.text for p in art.findall(".//PublicationTypeList/PublicationType")],
            "mesh_headings": [m.text for m in art.findall(".//MeshHeadingList/MeshHeading/DescriptorName")],
            "doi": ids.get("doi"), "pmcid": ids.get("pmc")}
    return out


def mentions(rec: dict, names: list) -> list:
    """Where the plant is named: title, abstract, mesh. Also 'G. species'."""
    where = []
    for field in ("title", "abstract"):
        text = rec[field].lower()
        for n in names:
            g, *rest = n.lower().split()
            if n.lower() in text or (rest and f"{g[0]}. {' '.join(rest)}" in text):
                where.append({"name": n, "where": field})
                break
    if any(n.lower() == m.lower() for n in names for m in rec["mesh_headings"]):
        where.append({"name": names[0], "where": "mesh"})
    return where


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    units = [json.loads(l) for l in open(HERE / "units" / "pilot.jsonl", encoding="utf-8")]
    mesh = json.load(gzip.open(ROOT / "reference_sources/mesh/mesh_index.json.gz", "rt", encoding="utf-8"))
    D, LK = mesh["descriptors"], mesh["lookup"]
    groups = defaultdict(list)                       # (species, concept uis) -> units
    for u in units:
        concepts = u["condition_concepts"] + u["action_concepts"] + u["other_concepts"]
        if concepts:
            groups[(bare(u["taxon"]["accepted_name"]), tuple(sorted(c["ui"] for c in concepts)))].append(u)
    species = sorted({sp for sp, _ in groups})
    print(f"{len(units)} pilot units → {len(groups)} plant × concept searches for {len(species)} plants")
    syn = {s: [] for s in species} if a.dry_run else synonyms(species)
    queries = []
    for (sp, uis), us in sorted(groups.items()):
        concepts = [{"ui": ui, "name": D[ui]["name"]} for ui in uis]
        base = f"{plant_clause(sp, syn.get(sp, []), LK, D)} AND {concept_clause(concepts)}"
        for kind, q in (("human_or_review", f"{base} AND {HUMAN_FILTER}"), ("any", base)):
            queries.append({"species": sp, "concepts": concepts, "kind": kind, "query": q,
                            "unit_ids": [u["unit_id"] for u in us]})
    if a.dry_run:
        for q in queries[:4]:
            print(f"\n{q['species']} · {', '.join(c['name'] for c in q['concepts'])} · {q['kind']}\n  {q['query']}")
        print(f"\n… {len(queries)} searches in all. Run without --dry-run on your computer.")
        return
    (HERE / "studies").mkdir(exist_ok=True)
    (HERE / "texts").mkdir(exist_ok=True)
    found = defaultdict(lambda: {"units": set(), "queries": []})
    with open(HERE / "studies" / "queries.jsonl", "w", encoding="utf-8") as f:
        for i, q in enumerate(queries, 1):
            r = json.loads(ncbi("esearch", {"db": "pubmed", "term": q["query"], "retmax": PER_SEARCH,
                                            "sort": "relevance", "retmode": "json"}))["esearchresult"]
            q.update(run_at=now(), result_count=int(r.get("count", 0)), pmids=r.get("idlist", []),
                     database="pubmed", translation=r.get("querytranslation"))
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
            for rank, pmid in enumerate(q["pmids"], 1):
                found[pmid]["units"] |= set(q["unit_ids"])
                found[pmid]["queries"].append({"query_kind": q["kind"], "species": q["species"],
                                               "concepts": [c["name"] for c in q["concepts"]], "rank": rank,
                                               "result_count": q["result_count"]})
            print(f"  [{i}/{len(queries)}] {q['species']} · {', '.join(c['name'] for c in q['concepts'])[:50]} "
                  f"· {q['kind']}: {q['result_count']} found, {len(q['pmids'])} kept for reading")
    pmids = sorted(found)
    recs = {}
    for b in range(0, len(pmids), 100):
        recs.update(parse_records(ncbi("efetch", {"db": "pubmed", "id": ",".join(pmids[b:b + 100]),
                                                  "rettype": "abstract", "retmode": "xml"})))
    kept = rejected = 0
    with open(HERE / "studies" / "studies.jsonl", "w", encoding="utf-8") as f:
        for pmid in pmids:
            rec = recs.get(pmid)
            if not rec:
                continue
            names = [found[pmid]["queries"][0]["species"]] + syn.get(found[pmid]["queries"][0]["species"], [])
            where = mentions(rec, names)
            text = f"{rec['title']}\n\n{rec['abstract']}".strip()
            tpath = HERE / "texts" / f"pmid_{pmid}.txt"
            tpath.write_text(text, encoding="utf-8")
            if not rec["abstract"]:
                decision, reason = "rejected", "no abstract in PubMed"
            elif not where:
                decision, reason = "rejected", "the plant is not named in title, abstract or MeSH headings"
            else:
                decision, reason = "kept", "plant named in " + ", ".join(w["where"] for w in where)
            kept += decision == "kept"
            rejected += decision == "rejected"
            f.write(json.dumps({
                "schema_version": "0.1", "study_id": f"pmid:{pmid}",
                "other_ids": {"pmid": pmid, "pmcid": rec["pmcid"], "doi": rec["doi"], "nct": None},
                "source": "PubMed", "title": rec["title"], "journal": rec["journal"],
                "publication_date": rec["publication_date"], "publication_types": rec["publication_types"],
                "taxa_mentioned": where, "mesh_headings": rec["mesh_headings"],
                "text": {"kind": "abstract" if rec["abstract"] else "title_only",
                         "locator": str(tpath.relative_to(ROOT)), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                         "licence_note": "PubMed abstract; publisher copyright, kept outside git"},
                "query": found[pmid]["queries"], "found_for_units": sorted(found[pmid]["units"]),
                "screening": {"decision": decision, "reason": reason, "by": "code", "at": now()},
                "duplicates_merged": [], "retrieved_at": now()}, ensure_ascii=False) + "\n")
    print(f"\n{len(pmids)} distinct PubMed records · {kept} kept · {rejected} rejected by screening · "
          f"{CALLS[0]} new NCBI calls\nSaved: stage3/studies/queries.jsonl, studies.jsonl, stage3/texts/")


if __name__ == "__main__":
    main()
