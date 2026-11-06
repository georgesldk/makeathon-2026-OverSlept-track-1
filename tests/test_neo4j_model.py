"""Offline graph preparation and snapshot-integrity checks; no database required."""
import importlib.util
import json
from collections import defaultdict
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


prepare = module('graph_prepare', 'neo4j/prepare.py')
loader = module('graph_load', 'neo4j/load.py')


def write(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def make_fixture(root, book, *, release='2026-06', authority_rule='accepted'):
    entry_id = 'example' if book == 'culpeper' else 'dioscorides-2-1'
    name = 'Example' if book == 'culpeper' else 'βρύον'
    if book == 'culpeper':
        hist = {'source': 'edition', 'herbs': [{'id': entry_id, 'name': name, 'heading': name,
                                                 'other_names': [], 'name_evidence': []}]}
        sourcefile = 'herbs.json'
    else:
        hist = {'source': 'edition', 'chapters': [{'id': entry_id, 'chapter': '1', 'label': '2.1',
               'headword': name, 'opening': name, 'text_names': [], 'rv_names': []}]}
        sourcefile = 'chapters.json'
    write(root, f'historical_texts/{book}/{sourcefile}', hist)
    candidate = {'accepted_name': 'Testus plantus L.', 'resolved': True, 'rank': 'species',
                 'scientific_names': [{'name': 'Testus plantus'}]}
    write(root, f'matching/{book}/herb_candidates_resolved.json',
          {'herbs': {entry_id: {'name': name, 'label': '2.1' if book == 'dioscorides' else None,
                                'candidates': [candidate]}}})
    decision = {'accepted_name': candidate['accepted_name'], 'tier': 'A', 'rules': ['A1'], 'caveats': [], 'reasons': []}
    write(root, f'matching/{book}/eligibility.json', {'herbs': {entry_id: {'shown': [decision], 'possible': [], 'hidden': []}}})
    write(root, f'matching/{book}/geography.json', {'herbs': {entry_id: {'candidates': []}}})
    item = {'wfo': {'accepted_id': 'wfo-123', 'accepted_name': 'Testus plantus L.', 'rule': authority_rule},
            'wcvp': {'accepted_id': '55', 'accepted_name': 'Testus plantus L.', 'rule': 'accepted'},
            'global_names': {}, 'agreement': 'agree'}
    write(root, f'matching/{book}/scientific_names_resolved.json',
          {'wfo_release': release, 'wcvp_version': '16', 'names': {'Testus plantus': item}})
    path = root / f'matching/{book}/evidence.jsonl'
    # Preserve both a uniquely matched row and an unmatched row.
    rows = [{('herb' if book == 'culpeper' else 'chapter'): entry_id, 'source': 'fixture',
             'candidate': 'Testus plantus', 'node': node, 'grade': 'strong'}
            for node in ('Testus plantus', None)]
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')


def complete_rows(root, snapshot='snapshot-1'):
    rows = defaultdict(list, {'snapshot': [{'id': snapshot, 'schema_version': '2'}]})
    for book in ('culpeper', 'dioscorides'):
        for kind, values in prepare.prepare(book, snapshot, root).items():
            rows[kind].extend(values)
    for kind in ('taxa', 'sources'):
        rows[kind] = list({row['id']: row for row in rows[kind]}.values())
    return rows


class GraphPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_fixture(self.root, 'culpeper')
        make_fixture(self.root, 'dioscorides')

    def test_same_authority_id_and_release_can_be_shared_across_books(self):
        rows = complete_rows(self.root)
        wfo = [t for t in rows['taxa'] if t['authority'] == 'WFO']
        self.assertEqual(len(wfo), 1)
        for resolution in rows['taxonomy']:
            links = json.loads(resolution['authority_links_json'])
            self.assertIn(wfo[0]['id'], [link['taxon_id'] for link in links])
        self.assertEqual(loader.validate(rows), 'snapshot-1')

    def test_same_name_does_not_merge_different_authorities(self):
        rows = complete_rows(self.root)
        self.assertEqual({t['authority'] for t in rows['taxa']}, {'WFO', 'WCVP'})
        self.assertEqual(len({t['id'] for t in rows['taxa']}), 2)

    def test_different_releases_do_not_share_taxon_identity(self):
        make_fixture(self.root, 'dioscorides', release='later')
        rows = complete_rows(self.root)
        self.assertEqual(len([t for t in rows['taxa'] if t['authority'] == 'WFO']), 2)

    def test_no_accepted_resolution_does_not_create_wfo_taxon(self):
        make_fixture(self.root, 'culpeper', authority_rule=None)
        data = prepare.prepare('culpeper', 'snapshot-1', self.root)
        self.assertFalse(any(t['authority'] == 'WFO' for t in data['taxa']))
        self.assertEqual([x['authority'] for x in json.loads(data['taxonomy'][0]['authority_links_json'])], ['WCVP'])

    def test_unmatched_evidence_and_hidden_candidate_are_preserved(self):
        p = self.root / 'matching/culpeper/eligibility.json'
        d = json.loads(p.read_text())
        entry = d['herbs']['example']
        row = entry['shown'].pop()
        row['tier'], row['rules'] = 'X', ['X1']
        entry['hidden'].append(row)
        p.write_text(json.dumps(d))
        data = prepare.prepare('culpeper', 'snapshot-1', self.root)
        self.assertEqual(data['decisions'][0]['tier'], 'X')
        self.assertEqual(len(data['evidence']), 2)
        self.assertEqual(data['evidence'][1]['hypothesis_link_status'], 'unmatched')
        self.assertIsNone(data['evidence'][1]['hypothesis_id'])

    def test_snapshot_scopes_entries_and_hypotheses_but_not_same_taxon(self):
        a = prepare.prepare('culpeper', 'one', self.root)
        b = prepare.prepare('culpeper', 'two', self.root)
        self.assertNotEqual(a['entries'][0]['id'], b['entries'][0]['id'])
        self.assertNotEqual(a['hypotheses'][0]['id'], b['hypotheses'][0]['id'])
        self.assertEqual({x['id'] for x in a['taxa']}, {x['id'] for x in b['taxa']})
        self.assertNotEqual(a['books'][0]['id'], b['books'][0]['id'])

    def test_validator_rejects_cross_snapshot_and_missing_endpoint(self):
        rows = complete_rows(self.root)
        rows['evidence'][0]['snapshot_id'] = 'another-snapshot'
        with self.assertRaisesRegex(ValueError, 'snapshot mismatch'):
            loader.validate(rows)
        rows = complete_rows(self.root)
        rows['evidence'][0]['hypothesis_id'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'missing hypotheses'):
            loader.validate(rows)

    def test_validator_rejects_cross_entry_hypothesis_link(self):
        rows = complete_rows(self.root)
        rows['decisions'][0]['hypothesis_id'] = rows['hypotheses'][1]['id']
        with self.assertRaisesRegex(ValueError, 'different entry'):
            loader.validate(rows)

    def test_description_scores_keep_original_quote_and_do_not_create_missing_scores(self):
        check = {'herbs': {'Example': {'name': 'Example', 'model_version': 'web: reviewed label',
                'details': {'d1': {'feature': 'root', 'quote': 'white root'}},
                'candidates': [{'accepted_name': 'Testus plantus L.', 'verdict': 'weak',
                                'congruence': 0, 'scores': [{'id': 'd1', 'label': 'partial',
                                'source': 'bhl', 'reason': 'source text'}]},
                               {'accepted_name': 'Other candidate', 'scores': []}]}}}
        write(self.root, 'description_sources/check/culpeper/description_check.json', check)
        data = prepare.prepare('culpeper', 'snapshot-1', self.root)
        self.assertEqual(len(data['candidate_descriptions']), 2)
        self.assertEqual(len(data['description_scores']), 1)
        self.assertEqual(data['description_scores'][0]['historical_quote'], 'white root')
        self.assertEqual(data['description_scores'][0]['label'], 'partial')
        self.assertEqual(data['candidate_descriptions'][0]['link_status'], 'unique')
        self.assertEqual(data['candidate_descriptions'][1]['link_status'], 'unmatched_or_ambiguous')
        self.assertIsNone(data['candidate_descriptions'][1]['hypothesis_id'])
        loader.validate(complete_rows(self.root))

    def test_validator_rejects_a_score_attached_to_a_missing_comparison(self):
        rows = complete_rows(self.root)
        rows['description_scores'].append({'id': 'score', 'snapshot_id': 'snapshot-1',
                                           'candidate_description_id': 'missing'})
        with self.assertRaisesRegex(ValueError, 'missing candidate_descriptions'):
            loader.validate(rows)


if __name__ == '__main__':
    unittest.main()
