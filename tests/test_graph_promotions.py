"""Promoted graph fields preserve the source values and uncertainty."""
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('promote_properties', Path(__file__).resolve().parents[1] / 'neo4j/promote_properties.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GraphPromotionsTests(unittest.TestCase):
    def test_assessment_keeps_compatibility_review_and_missing_distinct(self):
        raw = {'compatibility': {'species': {'value': 'same'}, 'route': {'value': 'unknown'}},
               'comparison': {'agree': False, 'flag_for_review': True},
               'validation': {'schema_ok': True, 'excerpts_failed': []},
               'mismatches': [], 'unknowns': ['route']}
        row = module.promote('assessments', {'raw_json': json.dumps(raw)})
        self.assertEqual(row['species_match'], 'same')
        self.assertEqual(row['route_match'], 'unknown')
        self.assertIsNone(row['condition_match'])
        self.assertIs(row['code_model_agree'], False)
        self.assertIs(row['review_flag'], True)
        self.assertEqual(row['excerpts_failed'], [])

    def test_source_lineage_is_not_botanical_family(self):
        raw = {'family': 'gbif', 'match_type': 'exact', 'matched_text': 'Bitter-sweet'}
        row = module.promote('evidence', {'raw_json': json.dumps(raw)})
        self.assertEqual(row['source_lineage'], 'gbif')
        self.assertNotIn('family', row)


if __name__ == '__main__':
    unittest.main()
