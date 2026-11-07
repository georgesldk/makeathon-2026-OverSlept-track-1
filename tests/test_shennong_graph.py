"""Contracts for the Shennong graph import; no database or network required."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'neo4j'))
import prepare
from load_claims import review_status
from promote_properties import promote


class ShennongGraphTests(unittest.TestCase):
    def test_original_records_and_unlinked_evidence_are_retained(self):
        source = json.loads((ROOT / 'historical_texts/shennong/entries.json').read_text())['entries']
        rows = prepare.prepare('shennong', 'test-snapshot', ROOT)
        self.assertEqual({e['entry_key'] for e in rows['entries']}, {e['id'] for e in source})
        with (ROOT / 'matching/shennong/evidence.jsonl').open() as stream:
            lines = sum(bool(x.strip()) for x in stream)
        self.assertEqual(len(rows['evidence']), lines)
        self.assertTrue(all(e['hypothesis_link_status'] in ('unique', 'unmatched', 'ambiguous') for e in rows['evidence']))

    def test_ai_only_review_is_not_reported_as_human(self):
        record = {'review': {'status': 'facts corrected by a person', 'corrections': [{'by': 'Claude only (not checked by a person)'}]}}
        self.assertEqual(review_status(record), 'AI only; not checked by a person')
        self.assertEqual(review_status({'review': {'status': 'facts corrected by a person', 'corrections': [{'by': 'person'}]}}), 'facts corrected by a person')

    def test_shennong_lineage_is_queryable(self):
        row = {'raw_json': json.dumps({'lineage': 'Loureiro', 'source': 'bretschneider'})}
        self.assertEqual(promote('evidence', row)['source_lineage'], 'Loureiro')


if __name__ == '__main__':
    unittest.main()
