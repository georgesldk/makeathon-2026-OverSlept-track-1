#!/usr/bin/env python3
"""Prepare a versioned graph snapshot from existing pipeline JSON; never connect to Neo4j."""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ("culpeper", "dioscorides", "shennong")


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def key(*parts):
    return digest(packed(parts))


def read(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def prepare(book, snapshot, root):
    hist_key = {'culpeper': 'herbs', 'dioscorides': 'chapters', 'shennong': 'entries'}[book]
    hist = read(root / f"historical_texts/{book}/{hist_key}.json")
    original = hist[hist_key]
    source = {h["id"]: h for h in original if book == "culpeper" or h.get("chapter") != "preface"}
    resolved = read(root / f"matching/{book}/herb_candidates_resolved.json")["herbs"]
    decisions = read(root / f"matching/{book}/eligibility.json")["herbs"]
    geography = read(root / f"matching/{book}/geography.json")["herbs"]
    taxfile = read(root / f"matching/{book}/scientific_names_resolved.json")
    taxonomy = taxfile["names"]
    releases = {"wfo": taxfile.get("wfo_release"), "wcvp": taxfile.get("wcvp_version")}
    descfile = root / f"description_sources/check/{book}/description_check.json"
    desc = read(descfile).get("herbs", {}) if descfile.exists() else {}
    if book == 'shennong':
        if set(resolved) != set(decisions) or not set(resolved).issubset(source):
            raise ValueError('shennong: inconsistent historical, resolved and eligibility IDs')
        # The source also contains animal and mineral records, which have no botanical decisions.
        for entry_key in set(source) - set(resolved):
            resolved[entry_key] = {'candidates': []}
            decisions[entry_key] = {'shown': [], 'possible': [], 'hidden': []}
    if set(source) != set(resolved) or set(source) != set(decisions):
        raise ValueError(f"{book}: entry IDs differ across historical, resolved and eligibility files")
    result = {k: [] for k in ("books", "entries", "names", "hypotheses", "decisions", "evidence", "sources", "taxonomy", "taxa", "comparisons", "candidate_descriptions", "description_scores")}
    # The edition metadata must not be overwritten when a different snapshot is loaded.
    book_id = key(snapshot, "book", book)
    result["books"].append({"id": book_id, "snapshot_id": snapshot, "book": book,
                            "name": {"culpeper": "Culpeper", "dioscorides": "Dioscorides", "shennong": "Shennong Bencao Jing"}[book], "source": hist.get("source")})
    link_by_entry = {}
    for entry_key, h in source.items():
        eid = key(snapshot, book, "entry", entry_key)
        rh = resolved[entry_key]
        entry_name = h.get("headword") if book == "dioscorides" else h.get("name")
        result["entries"].append({"id": eid, "snapshot_id": snapshot, "book_id": book_id, "book": book,
                                  "entry_key": entry_key, "name": entry_name, "label": h.get("label"),
                                  "raw_json": packed(h), "geography_json": packed(geography.get(entry_key))})
        names = ([{"name": h.get("name"), "layer": "heading", "quote": h.get("heading")}]
                 + [{"name": name, "layer": "other", "quote": ev.get("quote"), "note": ev.get("note")}
                    for ev in h.get("name_evidence", []) for name in ev.get("names", [])] if book == "culpeper" else
                 [{"name": h.get("headword"), "layer": "headword", "quote": h.get("opening")}]
                 + [{**n, "quote": None} for n in h.get("text_names", []) + h.get("rv_names", [])]) if book != 'shennong' else (
                 [{"name": h.get("name"), "layer": "heading", "quote": None}] +
                 [{"name": name, "layer": layer, "quote": None} for layer, values in (h.get('other_names_by_layer') or {}).items() for name in values])
        for i, name in enumerate(names):
            result["names"].append({"id": key(eid, "name", i), "snapshot_id": snapshot, "entry_id": eid, "name": name.get("name"),
                                    "layer": name.get("layer"), "quote": name.get("quote"), "raw_json": packed(name)})
        by_node = defaultdict(set)
        hyp_names = defaultdict(list)
        for i, hyp in enumerate(rh["candidates"]):
            hid = key(eid, "hypothesis", i)
            result["hypotheses"].append({"id": hid, "snapshot_id": snapshot, "entry_id": eid, "book": book,
                "accepted_name": hyp.get("accepted_name"), "resolved": bool(hyp.get("resolved")),
                "rank": hyp.get("rank"), "taxonomy_ids": [key(snapshot, book, "taxonomy", n["name"]) for n in hyp.get("scientific_names", []) if n.get("name") in taxonomy], "raw_json": packed(hyp)})
            for n in hyp.get("scientific_names", []):
                if n.get("name"):
                    by_node[n["name"]].add(hid)
            if hyp.get("accepted_name"):
                hyp_names[hyp["accepted_name"]].append(hid)
            else:
                original_names = sorted({n["name"] for n in hyp.get("scientific_names", []) if n.get("name")})
                if original_names:
                    hyp_names["(unresolved: " + ", ".join(original_names) + ")"].append(hid)
        link_by_entry[entry_key] = (eid, by_node)
        decs = decisions[entry_key]
        for section in ("shown", "possible", "hidden"):
            for i, dec in enumerate(decs[section]):
                hits = hyp_names.get(dec.get("accepted_name"), [])
                result["decisions"].append({"id": key(eid, "decision", section, i), "snapshot_id": snapshot, "entry_id": eid,
                    "hypothesis_id": hits[0] if len(hits) == 1 else None, "link_status": "unique" if len(hits) == 1 else "unmatched_or_ambiguous",
                    "tier": dec.get("tier"), "rules": dec.get("rules", []), "caveats": dec.get("caveats", []),
                    "reasons": dec.get("reasons", []), "accepted_name": dec.get("accepted_name"), "raw_json": packed(dec)})
        desc_key = rh.get("label") or rh.get("name")
        if desc_key in desc:
            comparison = desc[desc_key]
            comparison_id = key(eid, "description")
            result["comparisons"].append({"id": comparison_id, "snapshot_id": snapshot, "entry_id": eid,
                                          "model_version": comparison.get("model_version"), "raw_json": packed(comparison)})
            for i, candidate_result in enumerate(comparison.get("candidates", [])):
                candidate_id = key(comparison_id, "candidate", i)
                hits = hyp_names.get(candidate_result.get("accepted_name"), [])
                result["candidate_descriptions"].append({
                    "id": candidate_id, "snapshot_id": snapshot, "entry_id": eid, "comparison_id": comparison_id,
                    "hypothesis_id": hits[0] if len(hits) == 1 else None,
                    "link_status": "unique" if len(hits) == 1 else "unmatched_or_ambiguous",
                    "accepted_name": candidate_result.get("accepted_name"), "verdict": candidate_result.get("verdict"),
                    "congruence": candidate_result.get("congruence"), "wikipedia_only": candidate_result.get("wikipedia_only"),
                    "raw_json": packed(candidate_result)})
                for j, score in enumerate(candidate_result.get("scores", [])):
                    detail = comparison.get("details", {}).get(score.get("id")) or {}
                    result["description_scores"].append({
                        "id": key(candidate_id, "score", j), "snapshot_id": snapshot, "candidate_description_id": candidate_id,
                        "feature": detail.get("feature"), "historical_quote": detail.get("quote"),
                        "label": score.get("label"), "source": score.get("source"), "reason": score.get("reason"),
                        "detail_id": score.get("id"), "raw_json": packed(score)})
    sources = {}
    with (root / f"matching/{book}/evidence.jsonl").open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            e = json.loads(line)
            entry_key = e.get("herb") or e.get("chapter")
            if entry_key not in link_by_entry:
                raise ValueError(f"{book}: evidence line {number} references missing entry {entry_key}")
            eid, by_node = link_by_entry[entry_key]
            hits = by_node.get(e.get("node"), set())
            src = e.get("source") or "unspecified"
            source_id = key("source", src)
            sources[source_id] = {"id": source_id, "name": src}
            result["evidence"].append({"id": key(snapshot, book, "evidence", number), "snapshot_id": snapshot, "entry_id": eid,
                "source_id": source_id, "line_number": number, "node": e.get("node"),
                "original_candidate": e.get("candidate"), "source": src, "grade": e.get("grade"),
                "hypothesis_id": next(iter(hits)) if len(hits) == 1 else None,
                "hypothesis_link_status": "unique" if len(hits) == 1 else "ambiguous" if hits else "unmatched",
                "raw_json": packed(e)})
    result["sources"] = list(sources.values())
    taxa = {}
    for name, item in taxonomy.items():
        authority_links = []
        for authority, release in releases.items():
            assertion = item.get(authority) or {}
            identifier = assertion.get("accepted_id")
            # A bare identifier without an accepted resolution or release is not
            # enough to create a cross-book taxon identity.
            if not (assertion.get("rule") and identifier and release):
                continue
            tid = key("taxon", authority, str(release), str(identifier))
            taxa[tid] = {"id": tid, "authority": authority.upper(), "release": str(release),
                         "source_id": str(identifier)}
            authority_links.append({"taxon_id": tid, "authority": authority.upper(),
                                    "accepted_name": assertion.get("accepted_name"),
                                    "rule": assertion.get("rule")})
        result["taxonomy"].append({"id": key(snapshot, book, "taxonomy", name), "snapshot_id": snapshot,
            "book": book, "original_name": name, "agreement": item.get("agreement"),
            "wfo_json": packed(item.get("wfo")), "wcvp_json": packed(item.get("wcvp")),
            "global_names_json": packed(item.get("global_names")), "authority_links_json": packed(authority_links),
            "raw_json": packed(item)})
    result["taxa"] = list(taxa.values())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New JSONL file for later import; must not already exist")
    args = parser.parse_args()
    paths = []
    for book in BOOKS:
        hist_key = {'culpeper': 'herbs', 'dioscorides': 'chapters', 'shennong': 'entries'}[book]
        paths += [ROOT / f"historical_texts/{book}/{hist_key}.json"]
        paths += [ROOT / f"matching/{book}/{name}" for name in ("herb_candidates_resolved.json", "eligibility.json", "geography.json", "scientific_names_resolved.json", "evidence.jsonl")]
        p = ROOT / f"description_sources/check/{book}/description_check.json"
        if p.exists(): paths.append(p)
    paths.append(Path(__file__).resolve())
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    snapshot = digest(packed(hashes))
    rows = {"snapshot": [{"id": snapshot, "schema_version": "2", "input_hashes_json": packed(hashes),
                          "note": "Unreviewed pipeline outputs; identifications are hypotheses"}]}
    for book in BOOKS:
        for kind, values in prepare(book, snapshot, ROOT).items():
            rows.setdefault(kind, []).extend(values)
    # Source labels are intentionally shared between books and snapshots.
    rows["sources"] = list({row["id"]: row for row in rows["sources"]}.values())
    rows["taxa"] = list({row["id"]: row for row in rows["taxa"]}.values())
    for kind, values in rows.items():
        ids = [row["id"] for row in values]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate {kind} identifiers in prepared snapshot")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        for kind, values in rows.items():
            for value in values:
                stream.write(packed({"type": kind, "data": value}) + "\n")
    print("snapshot:", snapshot)
    print("rows:", ", ".join(f"{k}={len(v)}" for k, v in rows.items()))
    print("evidence links:", dict(Counter(e["hypothesis_link_status"] for e in rows["evidence"])))
    print("decision links:", dict(Counter(e["link_status"] for e in rows["decisions"])))
    print("wrote:", args.output)


if __name__ == "__main__":
    main()
