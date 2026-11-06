#!/usr/bin/env python3
"""Import full claim–plant source rows without conflating duplicate source IDs."""
import argparse
from collections import Counter, defaultdict
import getpass
import hashlib
import json
import os
from pathlib import Path

import load_claims as base


def prepare(snapshot_file):
    snapshot, existing = base.prepare(snapshot_file)
    source_dataset = existing['dataset'][0]['id']
    files = [base.ROOT / 'stage3/units/culpeper.jsonl', base.ROOT / 'stage3/units/dioscorides.jsonl']
    hashes = {str(p.relative_to(base.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    hashes['loader_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    dataset = base.key('full-unit-source-records-v1', snapshot, source_dataset, hashes)
    claims = {c['source_claim_id']: c for c in existing['claims']}
    shared = {u['source_unit_id']: u for u in existing['units']}
    hypotheses = defaultdict(list)
    for obj in base.jsonl(snapshot_file):
        if obj['type'] == 'hypotheses':
            h = obj['data']
            wfo = json.loads(h['raw_json']).get('wfo_id')
            if wfo:
                hypotheses[(h['entry_id'], wfo)].append(h['id'])
    records = []
    for path in files:
        source_path = str(path.relative_to(base.ROOT))
        for line_no, line in enumerate(path.open(encoding='utf-8'), 1):
            if not line.strip():
                continue
            u = json.loads(line)
            claim = claims.get(u.get('claim_id'))
            if not u.get('unit_id') or not claim or claim['book'] != u.get('book') or claim['entry_key'] != str(u.get('entry')):
                raise ValueError(f'{source_path}:{line_no}: missing or inconsistent claim/unit')
            wfo = (u.get('taxon') or {}).get('wfo_id')
            candidates = hypotheses.get((claim['entry_id'], wfo), []) if wfo else []
            link = shared.get(u['unit_id'])
            if not wfo or not link or link.get('wfo_id') != wfo or link['claim_id'] != claim['id']:
                link = None
            records.append({'id': base.key(dataset, source_path, line_no), 'dataset_id': dataset,
                'snapshot_id': snapshot, 'shared_dataset_id': source_dataset, 'source_path': source_path,
                'source_line': line_no, 'source_unit_id': u['unit_id'], 'claim_id': claim['id'],
                'hypothesis_id': candidates[0] if len(candidates) == 1 else None,
                'hypothesis_link_status': 'unique' if len(candidates) == 1 else 'ambiguous' if candidates else 'unmatched',
                'shared_unit_id': link['id'] if link else None, 'wfo_id': wfo,
                'taxon_name': (u.get('taxon') or {}).get('accepted_name'),
                'tier': (u.get('identification') or {}).get('tier'), 'raw_json': base.packed(u)})
    counts = Counter(r['source_unit_id'] for r in records)
    for r in records:
        r['source_id_count'] = counts[r['source_unit_id']]
        if r['source_id_count'] > 1:
            r['shared_unit_id'] = None
    return snapshot, source_dataset, dataset, hashes, records


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('snapshot', type=Path)
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    snapshot, shared_dataset, dataset, hashes, records = prepare(args.snapshot)
    print('Dataset:', dataset, 'records:', len(records), 'duplicate-ID rows:', sum(r['source_id_count'] > 1 for r in records), flush=True)
    print('Hypothesis links:', dict(Counter(r['hypothesis_link_status'] for r in records)), 'shared matches:', sum(bool(r['shared_unit_id']) for r in records), flush=True)
    if args.dry_run:
        return
    from neo4j import GraphDatabase
    with GraphDatabase.driver(os.environ['NEO4J_URI'], auth=(os.environ.get('NEO4J_USER', 'neo4j'), os.environ.get('NEO4J_PASSWORD') or getpass.getpass())) as driver:
        with driver.session(database=os.environ.get('NEO4J_DATABASE', 'neo4j')) as s:
            s.run('CREATE CONSTRAINT full_unit_record_id IF NOT EXISTS FOR (n:FullUnitRecord) REQUIRE n.id IS UNIQUE').consume()
            count = s.run('MATCH (s:PipelineSnapshot {id:$snapshot})-[:HAS_DATASET]->(d:DatasetImport {id:$shared}) RETURN count(d) AS n', snapshot=snapshot, shared=shared_dataset).single()['n']
            if count != 1:
                raise ValueError('Shared dataset and snapshot must already exist')
            s.run('MATCH (s:PipelineSnapshot {id:$snapshot}), (d:DatasetImport {id:$shared}) MERGE (n:DatasetImport {id:$id}) SET n.kind=$kind, n.snapshot_id=$snapshot, n.input_hashes_json=$hashes MERGE (s)-[:HAS_DATASET]->(n) MERGE (n)-[:USES_CLAIMS_FROM]->(d)', snapshot=snapshot, shared=shared_dataset, id=dataset, kind='full_unit_source_records', hashes=base.packed(hashes)).consume()
            q = '''UNWIND $rows AS r MATCH (d:DatasetImport {id:r.dataset_id}), (c:HistoricalClaim {id:r.claim_id, dataset_id:r.shared_dataset_id}) MERGE (n:FullUnitRecord {id:r.id}) SET n += r MERGE (d)-[:INCLUDES_UNIT_RECORD]->(n) MERGE (n)-[:ABOUT_CLAIM]->(c) WITH n,r OPTIONAL MATCH (h:IdentificationHypothesis {id:r.hypothesis_id, snapshot_id:r.snapshot_id}) FOREACH (_ IN CASE WHEN h IS NULL THEN [] ELSE [1] END | MERGE (n)-[:USES_HYPOTHESIS]->(h)) WITH n,r OPTIONAL MATCH (u:ClaimPlantUnit {id:r.shared_unit_id, dataset_id:r.shared_dataset_id}) FOREACH (_ IN CASE WHEN u IS NULL THEN [] ELSE [1] END | MERGE (n)-[:CORRESPONDS_TO_SHARED_UNIT]->(u)) RETURN count(n) AS n'''
            for i in range(0, len(records), 500):
                batch = records[i:i+500]
                if s.run(q, rows=batch).single()['n'] != len(batch):
                    raise RuntimeError('Missing claim endpoint; rerun after resolving the source data')
            print('Loaded full unit source records:', len(records), flush=True)


if __name__ == '__main__':
    main()
