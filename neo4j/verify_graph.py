#!/usr/bin/env python3
"""Read-only coverage and integrity checks for the structured EthnoTrace graph."""
import argparse
from collections import Counter
import csv
import getpass
import hashlib
import os
from pathlib import Path

from neo4j import GraphDatabase
from archive_scientific_sources import ROOT, outputs


def file_count(path):
    if path.suffix == '.json':
        return 1
    if path.suffix == '.jsonl':
        with path.open(encoding='utf-8') as f:
            return sum(bool(line.strip()) for line in f)
    with path.open(encoding='utf-8-sig', newline='') as f:
        return max(0, sum(1 for _ in csv.reader(f)) - 1)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', default=os.environ.get('NEO4J_DATABASE', 'ethnotrace-clean'))
    p.add_argument('--uri', default=os.environ.get('NEO4J_URI', 'neo4j://127.0.0.1:7687'))
    p.add_argument('--user', default=os.environ.get('NEO4J_USER', 'neo4j'))
    a = p.parse_args()
    password = os.environ.get('NEO4J_PASSWORD') or getpass.getpass('Neo4j password: ')
    expected = {str(path.relative_to(ROOT)): (sha256(path), file_count(path)) for path in outputs()}
    problems = []
    with GraphDatabase.driver(a.uri, auth=(a.user, password)) as driver:
        with driver.session(database=a.database, default_access_mode='READ') as session:
            actual = {}
            q = '''MATCH (d:SourceDocument) OPTIONAL MATCH (d)-[r:HAS_RECORD]->()
                   RETURN d.path AS path, d.sha256 AS sha, d.status AS status, count(r) AS records'''
            for row in session.run(q):
                actual.setdefault(row['path'], []).append((row['sha'], row['records'], row['status']))
            for path, (digest, count) in expected.items():
                matching = [v for v in actual.get(path, []) if v == (digest, count, 'complete')]
                if len(matching) != 1:
                    problems.append(f'{path}: expected SHA {digest}, {count} records, status complete; found {actual.get(path, [])}')
            extra_paths = set(actual) - set(expected)
            print(f'Source files: {len(expected)} local; {len(actual)} graph paths; {len(problems)} missing or mismatched')
            if extra_paths:
                print(f'Graph also contains {len(extra_paths)} source paths not found locally (may be older imports).')
            checks = {
                'Hypotheses without historical entry': 'MATCH (h:IdentificationHypothesis) WHERE NOT EXISTS { MATCH (:HistoricalEntry)-[:HAS_HYPOTHESIS]->(h) } RETURN count(h) AS n',
                'Claims without historical entry': 'MATCH (c:HistoricalClaim) WHERE NOT EXISTS { MATCH (:HistoricalEntry)-[:HAS_CLAIM]->(c) } RETURN count(c) AS n',
                'Full unit records without claim': 'MATCH (u:FullUnitRecord) WHERE NOT EXISTS { MATCH (u)-[:ABOUT_CLAIM]->(:HistoricalClaim) } RETURN count(u) AS n',
                'Assessments without unit': 'MATCH (a:EvidenceAssessment) WHERE NOT EXISTS { MATCH (a)-[:ASSESSES_UNIT]->(:ClaimPlantUnit) } RETURN count(a) AS n',
                'Assessments without study': 'MATCH (a:EvidenceAssessment) WHERE NOT EXISTS { MATCH (a)-[:ASSESSES_STUDY]->(:Study) } RETURN count(a) AS n',
                'Full units linked across snapshots': 'MATCH (u:FullUnitRecord)-[:USES_HYPOTHESIS]->(h:IdentificationHypothesis) WHERE u.snapshot_id <> h.snapshot_id RETURN count(u) AS n',
            }
            for description, query in checks.items():
                count = session.run(query).single(strict=True)['n']
                print(f'{description}: {count}')
                if count:
                    problems.append(f'{description}: {count}')
            for label in ('HistoricalEntry', 'IdentificationHypothesis', 'Taxon', 'EvidenceRecord', 'HistoricalClaim', 'Study', 'EvidenceAssessment', 'FullUnitRecord'):
                count = session.run(f'MATCH (n:{label}) RETURN count(n) AS n').single(strict=True)['n']
                print(f'{label}: {count}')
    for problem in problems:
        print('PROBLEM:', problem)
    print('These checks compare file hashes and record counts and find selected broken links. They do not prove every graph property or scientific assertion is correct.')
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
