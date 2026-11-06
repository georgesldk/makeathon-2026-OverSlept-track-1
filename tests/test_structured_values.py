"""The source-value representation retains nested data without JSON properties."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('structured_values', Path(__file__).resolve().parents[1] / 'neo4j/structured_values.py')
values = importlib.util.module_from_spec(spec)
spec.loader.exec_module(values)


class StructuredValuesTests(unittest.TestCase):
    def test_nested_null_empty_order_and_types_round_trip(self):
        original = {'title': 'ἶρις', 'none': None, 'empty_object': {}, 'empty_array': [],
                    'mixed': [1, 1.0, True, None, {'a.b': 'x', '': 'empty key'}],
                    'strings': ['first', 'second'], 'boolean': False}
        root, nodes, edges = values.encode(original, 'claim', 'raw_json')
        self.assertEqual(values.decode(root, nodes, edges), original)
        recovered = values.decode(root, nodes, edges)
        self.assertIs(type(recovered['mixed'][0]), int)
        self.assertIs(type(recovered['mixed'][1]), float)
        self.assertIs(type(recovered['mixed'][2]), bool)
        self.assertEqual(list(recovered), list(original))

    def test_different_owner_and_path_produce_different_ids(self):
        a = values.encode({'x': [1]}, 'a', 'raw_json')[0]
        b = values.encode({'x': [1]}, 'b', 'raw_json')[0]
        c = values.encode({'x': [1]}, 'a', 'other')[0]
        self.assertEqual(len({a, b, c}), 3)
        self.assertEqual(a, values.encode({'x': [2]}, 'a', 'raw_json')[0])

    def test_oversize_integer_is_rejected(self):
        with self.assertRaises(ValueError):
            values.encode({'too_large': 2**63}, 'a', 'raw_json')

if __name__ == '__main__':
    unittest.main()
