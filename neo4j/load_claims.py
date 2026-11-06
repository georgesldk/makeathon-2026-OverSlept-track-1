#!/usr/bin/env python3
"""Import existing historical claims and shared Stage 3 outputs, without AI or network retrieval."""
import argparse
from collections import Counter, defaultdict
import getpass
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def key(*parts):
    return hashlib.sha256(packed(parts).encode('utf-8')).hexdigest()


def jsonl(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def prepare(snapshot_file):
    botanical = defaultdict(list)
    for obj in jsonl(snapshot_file):
        botanical[obj['type']].append(obj['data'])
    if len(botanical['snapshot']) != 1 or botanical['snapshot'][0].get('schema_version') != '2':
        raise ValueError('Expected one version 2 botanical snapshot; prepare a new one first')
    snapshot = botanical['snapshot'][0]['id']
    files = [ROOT / 'claims/culpeper/claims.json', ROOT / 'claims/dioscorides/claims.json', ROOT / 'claims/links.json',
             ROOT / 'stage3/units/shared.jsonl', ROOT / 'stage3/studies/shared/studies.jsonl',
             ROOT / 'stage3/assessments/shared/assessments.jsonl', Path(__file__).resolve()]
    hashes = {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    run_id = key('claim-study-import-v1', snapshot, hashes)
    rows = defaultdict(list)
    rows['dataset'].append({'id': run_id, 'snapshot_id': snapshot, 'kind': 'claims_and_stage3_shared',
                            'input_hashes_json': packed(hashes), 'note': 'Imported source assertions; not verified efficacy'})
    entries = {(x['book'], x['label'] if x['book'] == 'dioscorides' else x['entry_key']): x['id']
               for x in botanical['entries']}
    hypotheses = defaultdict(list)
    for h in botanical['hypotheses']:
        original = json.loads(h['raw_json'])
        if original.get('wfo_id'):
            hypotheses[(h['entry_id'], original['wfo_id'])].append(h['id'])
    claims = {}
    concepts = {}
    for book in ('culpeper', 'dioscorides'):
        data = json.loads((ROOT / f'claims/{book}/claims.json').read_text(encoding='utf-8'))
        mesh_version = data.get('mesh')
        if not mesh_version:
            raise ValueError(f'{book}: missing MeSH version')
        for entry_key, entry in data['entries'].items():
            entry_id = entries.get((book, entry_key))
            if not entry_id:
                raise ValueError(f'{book}: historical entry not found: {entry_key}')
            for claim in entry['claims']:
                source_id = claim.get('claim_id')
                if not source_id or source_id in claims:
                    raise ValueError(f'missing or duplicate claim ID: {source_id}')
                cid = key(run_id, 'claim', source_id)
                claims[source_id] = {'id': cid, 'entry_id': entry_id, 'book': book, 'entry_key': entry_key}
                rows['claims'].append({'id': cid, 'dataset_id': run_id, 'snapshot_id': snapshot, 'entry_id': entry_id,
                    'source_claim_id': source_id, 'book': book, 'entry_key': entry_key, 'quote': claim.get('quote'),
                    'translation': claim.get('translation'), 'claim_text': claim.get('claim'), 'relation': claim.get('relation'),
                    'kind': claim.get('kind'), 'plant_part': claim.get('part'), 'preparation': claim.get('preparation'),
                    'route': claim.get('route'), 'batch': entry.get('batch'), 'model_label': data.get('model'),
                    'method': data.get('method'), 'raw_json': packed(claim)})
                for i, concept in enumerate(claim.get('mesh') or []):
                    ui = concept.get('ui')
                    if not ui:
                        raise ValueError(f'{source_id}: MeSH mapping has no ID')
                    mid = key('mesh', mesh_version, ui)
                    previous = concepts.get(mid)
                    if previous and previous['name'] != concept.get('name'):
                        raise ValueError(f'conflicting MeSH labels for {ui}')
                    concepts[mid] = {'id': mid, 'namespace': 'MeSH', 'version': mesh_version,
                                     'source_id': ui, 'name': concept.get('name')}
                    rows['mappings'].append({'id': key(cid, 'mapping', i), 'dataset_id': run_id, 'snapshot_id': snapshot,
                        'claim_id': cid, 'concept_id': mid, 'match': concept.get('match'), 'proposed': concept.get('proposed'),
                        'via': concept.get('via'), 'raw_json': packed(concept)})
    rows['concepts'] = list(concepts.values())
    groups = json.loads((ROOT / 'claims/links.json').read_text(encoding='utf-8'))['shared_claims']
    for i, group in enumerate(groups):
        ids = [claims[x['claim_id']]['id'] for x in group['claims'] if x.get('claim_id') in claims]
        if len(ids) != len(group['claims']):
            raise ValueError(f'shared group {i} references a missing claim')
        # This is the stored source grouping, not a pairwise historical equivalence.
        rows['claim_groups'].append({'id': key(run_id, 'claim_group', i), 'dataset_id': run_id,
            'snapshot_id': snapshot, 'species': group.get('species'), 'mesh_ui': group.get('mesh_ui'),
            'mesh_name': group.get('mesh'), 'both_A': group.get('both_A'), 'claim_ids': sorted(set(ids)),
            'raw_json': packed(group)})
    units = {}
    for u in jsonl(ROOT / 'stage3/units/shared.jsonl'):
        source_id = u.get('unit_id')
        if not source_id or source_id in units or u.get('claim_id') not in claims:
            raise ValueError(f'missing/duplicate unit or claim: {source_id}')
        claim = claims[u['claim_id']]
        if u.get('book') != claim['book'] or str(u.get('entry')) != claim['entry_key']:
            raise ValueError(f'unit does not belong to its claim entry: {source_id}')
        wfo = (u.get('taxon') or {}).get('wfo_id')
        hits = hypotheses.get((claim['entry_id'], wfo), []) if wfo else []
        # Missing or ambiguous matches remain unlinked; no name-only guesses.
        hid = hits[0] if len(hits) == 1 else None
        uid = key(run_id, 'unit', source_id)
        units[source_id] = uid
        rows['units'].append({'id': uid, 'dataset_id': run_id, 'snapshot_id': snapshot, 'source_unit_id': source_id,
            'claim_id': claim['id'], 'hypothesis_id': hid, 'hypothesis_link_status': 'unique' if hid else 'ambiguous' if hits else 'unmatched',
            'taxon_name': (u.get('taxon') or {}).get('accepted_name'), 'wfo_id': wfo,
            'tier': (u.get('identification') or {}).get('tier'), 'raw_json': packed(u)})
    studies = {}
    for s in jsonl(ROOT / 'stage3/studies/shared/studies.jsonl'):
        sid = s.get('study_id')
        if not sid or sid in studies:
            raise ValueError(f'missing/duplicate study ID: {sid}')
        studies[sid] = key(run_id, 'study', sid)
        rows['studies'].append({'id': studies[sid], 'dataset_id': run_id, 'source_study_id': sid,
            'source': s.get('source'), 'title': s.get('title'), 'journal': s.get('journal'),
            'publication_date': s.get('publication_date'), 'raw_json': packed(s)})
    seen = set()
    for a in jsonl(ROOT / 'stage3/assessments/shared/assessments.jsonl'):
        aid = a.get('assessment_id')
        if not aid or aid in seen or a.get('unit_id') not in units or a.get('study_id') not in studies:
            raise ValueError(f'missing/duplicate assessment or endpoint: {aid}')
        seen.add(aid)
        unit = next(x for x in rows['units'] if x['id'] == units[a['unit_id']])
        if claims.get(a.get('claim_id'), {}).get('id') != unit['claim_id']:
            raise ValueError(f'assessment claim does not match its unit: {aid}')
        gid = key(run_id, 'assessment', aid)
        rows['assessments'].append({'id': gid, 'dataset_id': run_id, 'snapshot_id': snapshot, 'source_assessment_id': aid,
            'unit_id': unit['id'], 'study_id': studies[a['study_id']], 'relevance': a.get('relevance'),
            'evidence_type': a.get('evidence_type'), 'finding': a.get('finding'), 'applicability': a.get('applicability'),
            'badge': a.get('badge'), 'review_status': (a.get('review') or {}).get('status'), 'raw_json': packed(a)})
        for i, excerpt in enumerate(a.get('excerpts') or []):
            if not isinstance(excerpt, dict):
                raise ValueError(f'invalid excerpt in assessment: {aid}')
            rows['excerpts'].append({'id': key(gid, 'excerpt', i), 'dataset_id': run_id, 'snapshot_id': snapshot,
                                     'assessment_id': gid, 'field': excerpt.get('field'), 'text': excerpt.get('text'),
                                     'raw_json': packed(excerpt)})
    return snapshot, rows


QUERIES = {
'dataset': '''UNWIND $rows AS r MATCH (s:PipelineSnapshot {id:r.snapshot_id}) MERGE (n:DatasetImport {id:r.id}) SET n += r MERGE (s)-[:HAS_DATASET]->(n) RETURN count(n) AS n''',
'concepts': '''UNWIND $rows AS r MERGE (n:MedicalConcept {id:r.id}) SET n += r RETURN count(n) AS n''',
'claims': '''UNWIND $rows AS r MATCH (d:DatasetImport {id:r.dataset_id}), (e:HistoricalEntry {id:r.entry_id, snapshot_id:r.snapshot_id}) MERGE (n:HistoricalClaim {id:r.id}) SET n += r MERGE (e)-[:HAS_CLAIM]->(n) MERGE (d)-[:INCLUDES_CLAIM]->(n) RETURN count(n) AS n''',
'mappings': '''UNWIND $rows AS r MATCH (c:HistoricalClaim {id:r.claim_id, dataset_id:r.dataset_id}), (m:MedicalConcept {id:r.concept_id}) MERGE (n:ConceptMapping {id:r.id}) SET n += r MERGE (c)-[:HAS_MAPPING]->(n) MERGE (n)-[:MAPS_TO]->(m) RETURN count(n) AS n''',
'claim_groups': '''UNWIND $rows AS r MATCH (d:DatasetImport {id:r.dataset_id}) MERGE (n:ClaimLink {id:r.id}) SET n += r MERGE (d)-[:INCLUDES_CLAIM_GROUP]->(n) RETURN count(n) AS n''',
'group_claims': '''UNWIND $rows AS r MATCH (g:ClaimLink {id:r.group_id, dataset_id:r.dataset_id}), (c:HistoricalClaim {id:r.claim_id, dataset_id:r.dataset_id}) MERGE (g)-[:GROUPS_CLAIM]->(c) RETURN count(c) AS n''',
'units': '''UNWIND $rows AS r MATCH (d:DatasetImport {id:r.dataset_id}), (c:HistoricalClaim {id:r.claim_id, dataset_id:r.dataset_id}) MERGE (n:ClaimPlantUnit {id:r.id}) SET n += r MERGE (d)-[:INCLUDES_UNIT]->(n) MERGE (n)-[:ABOUT_CLAIM]->(c) WITH n,r OPTIONAL MATCH (h:IdentificationHypothesis {id:r.hypothesis_id, snapshot_id:r.snapshot_id}) FOREACH (_ IN CASE WHEN h IS NULL THEN [] ELSE [1] END | MERGE (n)-[:USES_HYPOTHESIS]->(h)) RETURN count(n) AS n''',
'studies': '''UNWIND $rows AS r MATCH (d:DatasetImport {id:r.dataset_id}) MERGE (n:Study {id:r.id}) SET n += r MERGE (d)-[:INCLUDES_STUDY]->(n) RETURN count(n) AS n''',
'assessments': '''UNWIND $rows AS r MATCH (u:ClaimPlantUnit {id:r.unit_id, dataset_id:r.dataset_id}), (s:Study {id:r.study_id, dataset_id:r.dataset_id}) MERGE (n:EvidenceAssessment {id:r.id}) SET n += r MERGE (n)-[:ASSESSES_UNIT]->(u) MERGE (n)-[:ASSESSES_STUDY]->(s) RETURN count(n) AS n''',
'excerpts': '''UNWIND $rows AS r MATCH (a:EvidenceAssessment {id:r.assessment_id, dataset_id:r.dataset_id}) MERGE (n:EvidenceExcerpt {id:r.id}) SET n += r MERGE (a)-[:HAS_EXCERPT]->(n) RETURN count(n) AS n''',
}
ORDER = ('dataset', 'concepts', 'claims', 'mappings', 'claim_groups', 'group_claims', 'units', 'studies', 'assessments', 'excerpts')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path, help='Version 2 botanical snapshot prepared by prepare.py')
    parser.add_argument('--dry-run', action='store_true', help='Validate sources and print counts without connecting')
    parser.add_argument('--uri', default=os.environ.get('NEO4J_URI'))
    parser.add_argument('--user', default=os.environ.get('NEO4J_USER', 'neo4j'))
    parser.add_argument('--database', default=os.environ.get('NEO4J_DATABASE', 'neo4j'))
    parser.add_argument('--batch-size', type=int, default=500)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error('--batch-size must be positive')
    snapshot, rows = prepare(args.snapshot)
    for group in rows['claim_groups']:
        rows['group_claims'].extend({'group_id': group['id'], 'claim_id': cid, 'dataset_id': group['dataset_id']} for cid in group['claim_ids'])
    print('Botanical snapshot:', snapshot, flush=True)
    print('Dataset ID:', rows['dataset'][0]['id'], flush=True)
    print('Rows:', ', '.join(f'{k}={len(rows[k])}' for k in ORDER), flush=True)
    print('Unit-to-hypothesis links:', dict(Counter(x['hypothesis_link_status'] for x in rows['units'])), flush=True)
    if args.dry_run:
        return
    if not args.uri:
        parser.error('--uri or NEO4J_URI is required to load data')
    from neo4j import GraphDatabase
    password = os.environ.get('NEO4J_PASSWORD') or getpass.getpass('Neo4j password: ')
    with GraphDatabase.driver(args.uri, auth=(args.user, password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=args.database) as session:
            if session.run('MATCH (s:PipelineSnapshot {id:$id}) RETURN count(s) AS n', id=snapshot).single()['n'] != 1:
                raise ValueError('The specified botanical snapshot is not loaded')
            # Ensure every referenced botanical entry and hypothesis exists before writing.
            for kind, values in [('entry', sorted({x['entry_id'] for x in rows['claims']})),
                                 ('hypothesis', sorted({x['hypothesis_id'] for x in rows['units'] if x['hypothesis_id']}))]:
                label = 'HistoricalEntry' if kind == 'entry' else 'IdentificationHypothesis'
                for i in range(0, len(values), args.batch_size):
                    batch = values[i:i+args.batch_size]
                    found = session.run(f'UNWIND $ids AS id MATCH (n:{label} {{id:id, snapshot_id:$snapshot}}) RETURN count(n) AS n', ids=batch, snapshot=snapshot).single()['n']
                    if found != len(batch):
                        raise ValueError(f'Missing or wrong-snapshot {kind} endpoints')
            for kind in ORDER:
                for i in range(0, len(rows[kind]), args.batch_size):
                    batch = rows[kind][i:i+args.batch_size]
                    record = session.run(QUERIES[kind], rows=batch).single(strict=True)
                    if record['n'] != len(batch):
                        raise RuntimeError(f'{kind}: loaded {record["n"]} of {len(batch)}; missing endpoints')
                print(f'Loaded {kind}: {len(rows[kind])}', flush=True)
    print('Loaded dataset:', rows['dataset'][0]['id'])


if __name__ == '__main__':
    main()
