#!/usr/bin/env python3
"""Load a versioned EthnoTrace snapshot without serialized JSON properties."""
import argparse
from collections import defaultdict
import getpass
import hashlib
import json
import os
from pathlib import Path

import load as botanical
import load_claims as claims
import load_full_units as full
from promote_properties import promote
from structured_values import encode

LABELS = {'snapshot': 'PipelineSnapshot', 'books': 'Book', 'sources': 'EvidenceSource', 'taxa': 'Taxon',
          'entries': 'HistoricalEntry', 'names': 'HistoricalName', 'taxonomy': 'TaxonomicResolution',
          'hypotheses': 'IdentificationHypothesis', 'decisions': 'EligibilityDecision', 'evidence': 'EvidenceRecord',
          'comparisons': 'DescriptionComparison', 'candidate_descriptions': 'CandidateDescription',
          'description_scores': 'DescriptionScore', 'dataset': 'DatasetImport', 'concepts': 'MedicalConcept',
          'claims': 'HistoricalClaim', 'mappings': 'ConceptMapping', 'claim_groups': 'ClaimLink',
          'units': 'ClaimPlantUnit', 'studies': 'Study', 'assessments': 'EvidenceAssessment', 'excerpts': 'EvidenceExcerpt'}

NODE_QUERY = 'UNWIND $rows AS r MERGE (n:SourceValue {id:r.id}) SET n += r RETURN count(n) AS n'
EDGE_QUERY = '''UNWIND $rows AS r MATCH (a:SourceValue {id:r.parent}), (b:SourceValue {id:r.child})
MERGE (a)-[e:HAS_VALUE]->(b) SET e.field=r.field, e.position=r.index RETURN count(e) AS n'''


def load_batch(session, kind, original, query):
    domain, nodes, edges, roots = [], [], [], []
    for row in original:
        promoted = promote(kind, row)
        clean = {}
        for field, value in promoted.items():
            if field.endswith('_json'):
                if value is not None:
                    root, child_nodes, child_edges = encode(json.loads(value), row['id'], field)
                    nodes.extend(child_nodes)
                    edges.extend(child_edges)
                    roots.append({'owner': row['id'], 'root': root, 'field': field.removesuffix('_json')})
            else:
                clean[field] = value
        domain.append(clean)
    actual = session.run(query, rows=domain).single(strict=True)['n']
    if actual != len(domain):
        raise RuntimeError(f'{kind}: {actual}/{len(domain)} domain rows matched')
    for start in range(0, len(nodes), 1000):
        batch = nodes[start:start+1000]
        if session.run(NODE_QUERY, rows=batch).single(strict=True)['n'] != len(batch):
            raise RuntimeError(f'{kind}: source value node count mismatch')
    for start in range(0, len(edges), 1000):
        batch = edges[start:start+1000]
        if session.run(EDGE_QUERY, rows=batch).single(strict=True)['n'] != len(batch):
            raise RuntimeError(f'{kind}: source value edge count mismatch')
    label = LABELS[kind]
    root_query = f'''UNWIND $rows AS r MATCH (a:`{label}` {{id:r.owner}}), (b:SourceValue {{id:r.root}})
       MERGE (a)-[e:HAS_SOURCE_VALUE {{field:r.field}}]->(b) RETURN count(e) AS n'''
    if roots and session.run(root_query, rows=roots).single(strict=True)['n'] != len(roots):
        raise RuntimeError(f'{kind}: missing source value owner')


def load_rows(session, kind, rows, query, batch_size):
    for pos in range(0, len(rows), batch_size):
        load_batch(session, kind, rows[pos:pos+batch_size], query)
    print(kind, len(rows), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('snapshot', type=Path)
    p.add_argument('--database', required=True)
    p.add_argument('--batch-size', type=int, default=100)
    args = p.parse_args()
    if args.batch_size < 1:
        p.error('batch size must be positive')
    rows = defaultdict(list)
    for obj in claims.jsonl(args.snapshot):
        rows[obj['type']].append(obj['data'])
    snapshot = botanical.validate(rows)
    for h in rows['hypotheses']:
        rows['hypothesis_taxonomy'].extend({'hypothesis_id': h['id'], 'taxonomy_id': t} for t in sorted(set(h.get('taxonomy_ids', []))))
    for resolution in rows['taxonomy']:
        for link in json.loads(resolution.get('authority_links_json', '[]')):
            rows['taxonomy_taxa'].append({**link, 'resolution_id': resolution['id'], 'snapshot_id': snapshot})
    _, extra = claims.prepare(args.snapshot)
    for group in extra['claim_groups']:
        extra['group_claims'].extend({'group_id': group['id'], 'claim_id': cid, 'dataset_id': group['dataset_id']} for cid in group['claim_ids'])
    fsnapshot, shared, dataset, hashes, records = full.prepare(args.snapshot)
    if snapshot != fsnapshot:
        raise ValueError('Snapshot mismatch')
    code_files = [Path(__file__), Path(__file__).parent / 'structured_values.py', Path(__file__).parent / 'promote_properties.py']
    build_id = claims.key('structured-build-v1', snapshot, shared, dataset,
                          {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in code_files})
    from neo4j import GraphDatabase
    password = os.environ.get('NEO4J_PASSWORD') or getpass.getpass('Neo4j password: ')
    with GraphDatabase.driver(os.environ['NEO4J_URI'], auth=(os.environ.get('NEO4J_USER', 'neo4j'), password)) as driver:
        with driver.session(database=args.database) as s:
            count = s.run('MATCH (n) RETURN count(n) AS n').single()['n']
            if count:
                marker = s.run('MATCH (b:StructuredBuild) RETURN b.id AS id, b.status AS status').data()
                if len(marker) != 1 or marker[0]['id'] != build_id or marker[0]['status'] != 'loading':
                    raise ValueError('Target database is not empty or belongs to a different/completed build')
            schema = (Path(__file__).parent / '01_schema.cypher').read_text()
            for statement in '\n'.join(line for line in schema.splitlines() if not line.lstrip().startswith('//')).split(';'):
                if statement.strip():
                    s.run(statement).consume()
            s.run('CREATE CONSTRAINT structured_value_id IF NOT EXISTS FOR (n:SourceValue) REQUIRE n.id IS UNIQUE').consume()
            s.run('CREATE CONSTRAINT full_unit_record_id IF NOT EXISTS FOR (n:FullUnitRecord) REQUIRE n.id IS UNIQUE').consume()
            s.run('MERGE (b:StructuredBuild {id:$id}) SET b.status="loading", b.snapshot_id=$snapshot', id=build_id, snapshot=snapshot).consume()
            for kind in botanical.ORDER:
                if kind in botanical.DERIVED:
                    for i in range(0, len(rows[kind]), args.batch_size):
                        batch = rows[kind][i:i+args.batch_size]
                        if s.run(botanical.QUERIES[kind], rows=batch).single()['n'] != len(batch):
                            raise RuntimeError(f'{kind}: missing endpoints')
                    print(kind, len(rows[kind]), flush=True)
                else:
                    load_rows(s, kind, rows[kind], botanical.QUERIES[kind], args.batch_size)
            for kind in claims.ORDER:
                if kind == 'group_claims':
                    for i in range(0, len(extra[kind]), args.batch_size):
                        batch = extra[kind][i:i+args.batch_size]
                        if s.run(claims.QUERIES[kind], rows=batch).single()['n'] != len(batch):
                            raise RuntimeError('Missing claim-group endpoint')
                    print(kind, len(extra[kind]), flush=True)
                else:
                    load_rows(s, kind, extra[kind], claims.QUERIES[kind], args.batch_size)
            # Full source rows refer to the already-loaded shared claims dataset.
            metadata = {'id': dataset, 'snapshot_id': snapshot, 'kind': 'full_unit_source_records',
                        'input_hashes_json': claims.packed(hashes)}
            load_batch(s, 'dataset', [metadata], claims.QUERIES['dataset'])
            s.run('MATCH (a:DatasetImport {id:$a}), (b:DatasetImport {id:$b}) MERGE (a)-[:USES_CLAIMS_FROM]->(b)', a=dataset, b=shared).consume()
            LABELS['full_units'] = 'FullUnitRecord'
            q = '''UNWIND $rows AS r MATCH (d:DatasetImport {id:r.dataset_id}), (c:HistoricalClaim {id:r.claim_id, dataset_id:r.shared_dataset_id}) MERGE (n:FullUnitRecord {id:r.id}) SET n += r MERGE (d)-[:INCLUDES_UNIT_RECORD]->(n) MERGE (n)-[:ABOUT_CLAIM]->(c) WITH n,r OPTIONAL MATCH (h:IdentificationHypothesis {id:r.hypothesis_id, snapshot_id:r.snapshot_id}) FOREACH (_ IN CASE WHEN h IS NULL THEN [] ELSE [1] END | MERGE (n)-[:USES_HYPOTHESIS]->(h)) WITH n,r OPTIONAL MATCH (u:ClaimPlantUnit {id:r.shared_unit_id, dataset_id:r.shared_dataset_id}) FOREACH (_ IN CASE WHEN u IS NULL THEN [] ELSE [1] END | MERGE (n)-[:CORRESPONDS_TO_SHARED_UNIT]->(u)) RETURN count(n) AS n'''
            load_rows(s, 'full_units', records, q, args.batch_size)
            s.run('MATCH (b:StructuredBuild {id:$id}) SET b.status="complete"', id=build_id).consume()
    print('Structured graph loaded:', args.database, snapshot, flush=True)


if __name__ == '__main__':
    main()
