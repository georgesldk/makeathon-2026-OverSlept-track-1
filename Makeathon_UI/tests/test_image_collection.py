"""Offline tests for conservative image-to-taxon and licence matching."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('candidate_images', Path(__file__).resolve().parents[1] / 'collect_candidate_images.py')
images = importlib.util.module_from_spec(spec)
spec.loader.exec_module(images)

MATCH = {'matchType': 'EXACT', 'status': 'ACCEPTED', 'confidence': 100, 'usageKey': 1, 'scientificName': 'Example plant L.'}
MEDIA = {'type': 'StillImage', 'identifier': 'https://images.example/photo.jpg', 'license': 'http://creativecommons.org/licenses/by/4.0/', 'creator': 'A. Botanist'}


class ImageCollectionTests(unittest.TestCase):
    def test_requires_matching_author_and_accepted_taxon(self):
        with patch.object(images, 'get', return_value={**MATCH, 'scientificName': 'Example plant Mill.'}):
            self.assertEqual(images.find_image('Example plant L.')['status'], 'unmatched')
        with patch.object(images, 'get', return_value={**MATCH, 'status': 'SYNONYM'}):
            self.assertEqual(images.find_image('Example plant L.')['status'], 'unmatched')

    def test_never_uses_other_taxon_or_missing_image_licence(self):
        occurrences = {'results': [{'taxonKey': 2, 'key': 10, 'media': [MEDIA]}, {'taxonKey': 1, 'key': 11, 'media': [{**MEDIA, 'license': None}]}]}
        with patch.object(images, 'get', side_effect=[MATCH, occurrences]):
            self.assertEqual(images.find_image('Example plant L.')['status'], 'no_eligible_image')

    def test_preserves_individual_image_attribution_and_source(self):
        occurrences = {'results': [{'taxonKey': 1, 'key': 10, 'media': [MEDIA]}]}
        with patch.object(images, 'get', side_effect=[MATCH, occurrences]):
            result = images.find_image('Example plant L.')
        self.assertEqual(result['status'], 'available')
        self.assertEqual(result['creator'], 'A. Botanist')
        self.assertEqual(result['license_url'], 'https://creativecommons.org/licenses/by/4.0/')
        self.assertEqual(result['occurrence_url'], 'https://www.gbif.org/occurrence/10')


if __name__ == '__main__':
    unittest.main()
