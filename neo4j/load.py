#!/usr/bin/env python3
"""Load a prepared snapshot into Neo4j. Requires the official neo4j Python driver."""
import argparse
from collections import defaultdict
import getpass
import json
import os
from pathlib import Path
import sys

QUERIES = {
"snapshot": """UNWIND $rows AS r MERGE (n:PipelineSnapshot {id:r.id}) SET n += r RETURN count(n) AS n""",
"books": """UNWIND $rows AS r MERGE (n:Book {id:r.id}) SET n += r RETURN count(n) AS n""",
"sources": """UNWIND $rows AS r MERGE (n:EvidenceSource {id:r.id}) SET n += r RETURN count(n) AS n""",
"taxa": """UNWIND $rows AS r MERGE (n:Taxon {id:r.id}) SET n += r RETURN count(n) AS n""",
"entries": """UNWIND $rows AS r MATCH (s:PipelineSnapshot {id:r.snapshot_id}), (b:Book {id:r.book_id})
MERGE (n:HistoricalEntry {id:r.id}) SET n += r MERGE (s)-[:INCLUDES]->(n) MERGE (n)-[:IN_BOOK]->(b) RETURN count(n) AS n""",
"names": """UNWIND $rows AS r MATCH (e:HistoricalEntry {id:r.entry_id})
MERGE (n:HistoricalName {id:r.id}) SET n += r MERGE (e)-[:HAS_HISTORICAL_NAME]->(n) RETURN count(n) AS n""",
"taxonomy": """UNWIND $rows AS r MATCH (s:PipelineSnapshot {id:r.snapshot_id})
MERGE (n:TaxonomicResolution {id:r.id}) SET n += r MERGE (s)-[:HAS_TAXONOMIC_RESOLUTION]->(n) RETURN count(n) AS n""",
"taxonomy_taxa": """UNWIND $rows AS r MATCH (n:TaxonomicResolution {id:r.resolution_id, snapshot_id:r.snapshot_id}), (t:Taxon {id:r.taxon_id})
MERGE (n)-[rel:RESOLVES_TO]->(t) SET rel.authority = r.authority, rel.accepted_name = r.accepted_name, rel.rule = r.rule RETURN count(rel) AS n""",
"hypotheses": """UNWIND $rows AS r MATCH (e:HistoricalEntry {id:r.entry_id})
MERGE (n:IdentificationHypothesis {id:r.id}) SET n += r MERGE (e)-[:HAS_HYPOTHESIS]->(n) RETURN count(n) AS n""",
"hypothesis_taxonomy": """UNWIND $rows AS r MATCH (h:IdentificationHypothesis {id:r.hypothesis_id}), (t:TaxonomicResolution {id:r.taxonomy_id})
MERGE (h)-[:HAS_NAME_RESOLUTION]->(t) RETURN count(h) AS n""",
"decisions": """UNWIND $rows AS r MATCH (e:HistoricalEntry {id:r.entry_id})
MERGE (n:EligibilityDecision {id:r.id}) SET n += r MERGE (e)-[:HAS_DECISION]->(n)
WITH n, r OPTIONAL MATCH (h:IdentificationHypothesis {id:r.hypothesis_id})
FOREACH (_ IN CASE WHEN h IS NULL THEN [] ELSE [1] END | MERGE (h)-[:HAS_DECISION]->(n)) RETURN count(n) AS n""",
"evidence": """UNWIND $rows AS r MATCH (e:HistoricalEntry {id:r.entry_id}), (s:EvidenceSource {id:r.source_id})
MERGE (n:EvidenceRecord {id:r.id}) SET n += r MERGE (e)-[:HAS_EVIDENCE]->(n) MERGE (n)-[:FROM_SOURCE]->(s)
WITH n, r OPTIONAL MATCH (h:IdentificationHypothesis {id:r.hypothesis_id})
FOREACH (_ IN CASE WHEN h IS NULL THEN [] ELSE [1] END | MERGE (n)-[:RELATES_TO_HYPOTHESIS]->(h)) RETURN count(n) AS n""",
"comparisons": """UNWIND $rows AS r MATCH (e:HistoricalEntry {id:r.entry_id})
MERGE (n:DescriptionComparison {id:r.id}) SET n += r MERGE (e)-[:HAS_DESCRIPTION_COMPARISON]->(n) RETURN count(n) AS n""",
"candidate_descriptions": """UNWIND $rows AS r MATCH (c:DescriptionComparison {id:r.comparison_id})
MERGE (n:CandidateDescription {id:r.id}) SET n += r MERGE (c)-[:HAS_CANDIDATE_COMPARISON]->(n)
WITH n, r OPTIONAL MATCH (h:IdentificationHypothesis {id:r.hypothesis_id})
FOREACH (_ IN CASE WHEN h IS NULL THEN [] ELSE [1] END | MERGE (n)-[:COMPARES_HYPOTHESIS]->(h)) RETURN count(n) AS n""",
"description_scores": """UNWIND $rows AS r MATCH (c:CandidateDescription {id:r.candidate_description_id})
MERGE (n:DescriptionScore {id:r.id}) SET n += r MERGE (c)-[:HAS_SCORE]->(n) RETURN count(n) AS n""",
}
ORDER = ("snapshot", "books", "sources", "taxa", "entries", "names", "taxonomy", "taxonomy_taxa", "hypotheses", "hypothesis_taxonomy", "decisions", "evidence", "comparisons", "candidate_descriptions", "description_scores")
DERIVED = {"hypothesis_taxonomy", "taxonomy_taxa"}


def validate(rows):
    """Reject missing IDs or cross-snapshot links before connecting or writing."""
    if len(rows["snapshot"]) != 1 or not rows["snapshot"][0].get("id"):
        raise ValueError("Prepared file must contain exactly one snapshot with an ID")
    if rows["snapshot"][0].get("schema_version") != "2":
        raise ValueError("Unsupported graph snapshot version; prepare a fresh version 2 snapshot")
    snapshot = rows["snapshot"][0]["id"]
    indexed = {}
    for kind in ORDER:
        if kind in DERIVED:
            continue
        indexed[kind] = {}
        for row in rows[kind]:
            identifier = row.get("id")
            if not isinstance(identifier, str) or not identifier.strip() or identifier in indexed[kind]:
                raise ValueError(f"{kind}: missing or duplicate ID: {identifier!r}")
            if kind not in ("snapshot", "sources", "taxa") and row.get("snapshot_id") != snapshot:
                raise ValueError(f"{kind}: snapshot mismatch: {identifier}")
            indexed[kind][identifier] = row
    def require(kind, identifier):
        if identifier not in indexed[kind]:
            raise ValueError(f"missing {kind} endpoint: {identifier}")
        return indexed[kind][identifier]
    for e in rows["entries"]:
        b = require("books", e.get("book_id"))
        if e.get("book") != b.get("book"):
            raise ValueError("entry/book mismatch")
    for kind in ("names", "hypotheses", "decisions", "evidence", "comparisons", "candidate_descriptions"):
        for row in rows[kind]:
            entry = require("entries", row.get("entry_id"))
            if kind in ("decisions", "evidence", "candidate_descriptions") and row.get("hypothesis_id"):
                h = require("hypotheses", row["hypothesis_id"])
                if h["entry_id"] != entry["id"]:
                    raise ValueError(f"{kind}: hypothesis belongs to a different entry")
            if kind == "evidence":
                require("sources", row.get("source_id"))
            if kind == "candidate_descriptions":
                comparison = require("comparisons", row.get("comparison_id"))
                if comparison["entry_id"] != entry["id"]:
                    raise ValueError("candidate comparison belongs to a different entry")
            if kind == "hypotheses":
                for identifier in row.get("taxonomy_ids", []):
                    t = require("taxonomy", identifier)
                    if t.get("book") != entry.get("book"):
                        raise ValueError("hypothesis/resolution book mismatch")
    for t in rows["taxonomy"]:
        for link in json.loads(t.get("authority_links_json", "[]")):
            taxon = require("taxa", link.get("taxon_id"))
            if taxon.get("authority") != link.get("authority"):
                raise ValueError("taxon authority mismatch")
    for score in rows["description_scores"]:
        require("candidate_descriptions", score.get("candidate_description_id"))
    return snapshot


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("file", type=Path, help="JSONL created by prepare.py")
    p.add_argument("--uri", default=os.environ.get("NEO4J_URI"), required=not bool(os.environ.get("NEO4J_URI")))
    p.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    p.add_argument("--database", default=os.environ.get("NEO4J_DATABASE", "neo4j"))
    p.add_argument("--batch-size", type=int, default=500)
    a = p.parse_args()
    if a.batch_size < 1: p.error("--batch-size must be positive")
    rows = defaultdict(list)
    with a.file.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            record = json.loads(line)
            if record.get("type") not in ORDER or record["type"] in DERIVED:
                raise ValueError(f"Unknown prepared row type at line {number}: {record.get('type')}")
            rows[record["type"]].append(record["data"])
    snapshot = validate(rows)
    for h in rows["hypotheses"]:
        rows["hypothesis_taxonomy"].extend({"hypothesis_id": h["id"], "taxonomy_id": t} for t in sorted(set(h.get("taxonomy_ids", []))))
    for resolution in rows["taxonomy"]:
        for link in json.loads(resolution.get("authority_links_json", "[]")):
            rows["taxonomy_taxa"].append({**link, "resolution_id": resolution["id"], "snapshot_id": snapshot})
    try:
        from neo4j import GraphDatabase
    except ImportError:
        sys.exit("Install the official neo4j Python driver first: python3.10 -m pip install neo4j")
    password = os.environ.get("NEO4J_PASSWORD") or getpass.getpass("Neo4j password: ")
    with GraphDatabase.driver(a.uri, auth=(a.user, password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=a.database) as session:
            for kind in ORDER:
                values = rows[kind]
                for start in range(0, len(values), a.batch_size):
                    batch = values[start:start+a.batch_size]
                    record = session.run(QUERIES[kind], rows=batch).single(strict=True)
                    if record["n"] != len(batch):
                        raise RuntimeError(f"{kind}: imported {record['n']} of {len(batch)} rows; check missing endpoints")
                print(f"{kind}: {len(values)}")
    print("Loaded snapshot", rows["snapshot"][0]["id"])


if __name__ == "__main__":
    main()
