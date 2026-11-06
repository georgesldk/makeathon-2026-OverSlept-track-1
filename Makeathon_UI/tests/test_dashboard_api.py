"""Read-only dashboard endpoint contract without requiring a running Neo4j."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault('NEO4J_PASSWORD', 'test-only')
spec = importlib.util.spec_from_file_location('dashboard_api', Path(__file__).resolve().parents[1] / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class DashboardAPITests(unittest.TestCase):
    def test_studies_are_scoped_and_truncation_is_visible(self):
        context = {'snapshot': 's', 'dataset': 'd', 'full_dataset': 'f'}
        rows = [{'study': {'title': str(i)}} for i in range(51)]
        with patch.object(server, 'query', return_value=rows) as query:
            result = server.entry_studies(context, 'e')
        self.assertEqual(len(result['items']), 50)
        self.assertTrue(result['has_more'])
        self.assertEqual(query.call_args.kwargs['id'], 'e')
        cypher = query.call_args.args[0]
        self.assertIn('snapshot_id:$snapshot', cypher)
        self.assertIn('dataset_id:$dataset', cypher)
        self.assertIn('ABOUT_CLAIM', cypher)
        self.assertIn('ASSESSES_UNIT', cypher)
        self.assertIn('ASSESSES_STUDY', cypher)

    def test_empty_studies_are_not_invented(self):
        with patch.object(server, 'query', return_value=[]):
            result = server.entry_studies({'snapshot': 's', 'dataset': 'd', 'full_dataset': 'f'}, 'e')
        self.assertEqual(result, {'items': [], 'has_more': False})


if __name__ == '__main__':
    unittest.main()
