"""Offline checks for the claim/study graph importer; no Neo4j connection."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('claim_graph_loader', ROOT / 'neo4j/load_claims.py')
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


def write(root, path, value, jsonl=False):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    if jsonl:
        file.write_text(''.join(json.dumps(x) + '\n' for x in value), encoding='utf-8')
    else:
        file.write_text(json.dumps(value), encoding='utf-8')
    return file


class ClaimGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        write(self.root, 'neo4j/load_claims.py', {'revision': 1})
        self.patches = [patch.object(loader, 'ROOT', self.root), patch.object(loader, '__file__', str(self.root / 'neo4j/load_claims.py'))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        snapshot = [{'type': 'snapshot', 'data': {'id': 'snap', 'schema_version': '2'}},
                    {'type': 'entries', 'data': {'id': 'entry', 'book': 'culpeper', 'label': None, 'entry_key': 'herb'}},
                    {'type': 'hypotheses', 'data': {'id': 'hyp', 'entry_id': 'entry', 'raw_json': json.dumps({'wfo_id': 'wfo-1'})}}]
        self.snapshot_file = write(self.root, 'snapshot.jsonl', snapshot, jsonl=True)
        self.claim = {'claim_id': 'culpeper:herb:c01', 'quote': 'the original quote', 'claim': 'historical claim',
                      'kind': 'medical', 'relation': 'treats', 'part': 'root', 'preparation': '', 'route': 'unknown',
                      'mesh': [{'ui': 'D000001', 'name': 'A concept', 'match': 'close', 'proposed': 'old term'}]}
        write(self.root, 'claims/culpeper/claims.json', {'mesh': 'desc2026.gz', 'model': 'web: label',
              'entries': {'herb': {'name': 'Herb', 'batch': 'batch_01', 'claims': [self.claim]}}})
        write(self.root, 'claims/dioscorides/claims.json', {'mesh': 'desc2026.gz', 'entries': {}})
        write(self.root, 'claims/links.json', {'shared_claims': []})
        self.unit = {'unit_id': 'unit-1', 'claim_id': 'culpeper:herb:c01', 'book': 'culpeper', 'entry': 'herb',
                     'taxon': {'wfo_id': 'wfo-1', 'accepted_name': 'Testus plantus'}, 'identification': {'tier': 'B'}}
        write(self.root, 'stage3/units/shared.jsonl', [self.unit], jsonl=True)
        self.study = {'study_id': 'pmid:1', 'source': 'PubMed', 'title': 'Fixture study'}
        write(self.root, 'stage3/studies/shared/studies.jsonl', [self.study], jsonl=True)
        self.assessment = {'assessment_id': 'assess-1', 'unit_id': 'unit-1', 'study_id': 'pmid:1',
                           'claim_id': 'culpeper:herb:c01', 'finding': 'negative', 'applicability': 'partial',
                           'review': {'status': 'unreviewed'}, 'excerpts': [{'field': 'outcome', 'text': 'not effective'}]}
        write(self.root, 'stage3/assessments/shared/assessments.jsonl', [self.assessment], jsonl=True)

    def test_quote_mapping_study_and_review_are_preserved_separately(self):
        _, rows = loader.prepare(self.snapshot_file)
        self.assertEqual(rows['claims'][0]['quote'], 'the original quote')
        self.assertEqual(rows['mappings'][0]['match'], 'close')
        self.assertEqual(rows['units'][0]['hypothesis_id'], 'hyp')
        self.assertEqual(rows['assessments'][0]['finding'], 'negative')
        self.assertEqual(rows['assessments'][0]['applicability'], 'partial')
        self.assertEqual(rows['assessments'][0]['review_status'], 'unreviewed')
        self.assertEqual(rows['excerpts'][0]['text'], 'not effective')

    def test_unmatched_authority_id_does_not_guess_by_name(self):
        self.unit['taxon']['wfo_id'] = 'wfo-other'
        write(self.root, 'stage3/units/shared.jsonl', [self.unit], jsonl=True)
        _, rows = loader.prepare(self.snapshot_file)
        self.assertEqual(rows['units'][0]['hypothesis_link_status'], 'unmatched')
        self.assertIsNone(rows['units'][0]['hypothesis_id'])

    def test_ambiguous_authority_id_is_not_arbitrarily_linked(self):
        with self.snapshot_file.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'type': 'hypotheses', 'data': {'id': 'hyp-2', 'entry_id': 'entry',
                     'raw_json': json.dumps({'wfo_id': 'wfo-1'})}}) + '\n')
        _, rows = loader.prepare(self.snapshot_file)
        self.assertEqual(rows['units'][0]['hypothesis_link_status'], 'ambiguous')
        self.assertIsNone(rows['units'][0]['hypothesis_id'])

    def test_assessment_cannot_be_attached_to_wrong_claim(self):
        self.assessment['claim_id'] = 'culpeper:herb:other'
        write(self.root, 'stage3/assessments/shared/assessments.jsonl', [self.assessment], jsonl=True)
        with self.assertRaisesRegex(ValueError, 'assessment claim'):
            loader.prepare(self.snapshot_file)

    def test_source_changes_produce_separate_dataset_id(self):
        _, before = loader.prepare(self.snapshot_file)
        self.assessment['finding'] = 'mixed'
        write(self.root, 'stage3/assessments/shared/assessments.jsonl', [self.assessment], jsonl=True)
        _, after = loader.prepare(self.snapshot_file)
        self.assertNotEqual(before['dataset'][0]['id'], after['dataset'][0]['id'])
        self.assertNotEqual(before['claims'][0]['id'], after['claims'][0]['id'])


if __name__ == '__main__':
    unittest.main()
