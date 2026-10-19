import json
from unittest import TestCase

from app.ingestion.chunking import chunk_document
from app.ingestion.native_records import parse_native_stix
from app.ingestion.parsers import normalize


class StixProjectionTest(TestCase):
    def test_projected_source_is_labeled(self):
        bundle = {
            'type': 'bundle',
            'id': 'bundle--00000000-0000-4000-8000-000000000001',
            'x_argus_projection': {'sourceUrl': 'https://example.org/source.json', 'selection': 'Selected records', 'sourceSha256': 'abc'},
            'objects': [{'type': 'attack-pattern', 'id': 'attack-pattern--00000000-0000-4000-8000-000000000002', 'name': 'Technique'}],
        }
        parsed = parse_native_stix(json.dumps(bundle).encode(), 10000)
        self.assertEqual(parsed['metadata']['sourceCoverage']['coverageLabel'], 'field_projected_subset')
        self.assertTrue(parsed['metadata']['sourceCoverage']['limitedSource'])
        self.assertEqual(parsed['metadata']['sourceUrl'], 'https://example.org/source.json')

    def test_native_records_do_not_overlap_across_chunks(self):
        parsed = {
            'blocks': [{'ordinal': index, 'kind': 'record', 'role': 'stix_object', 'text': f'item {index}', 'location': {}, 'structured': None} for index in range(6)],
            'metadata': {'parser': 'stix_native_json'},
        }
        document = normalize(parsed)
        chunks = chunk_document(document, 'native-test', {'tokenEncoding': 'cl100k_base', 'chunkTokens': 5, 'overlapSentences': 2})['chunks']
        occurrences = [ordinal for chunk in chunks for ordinal in chunk['blockOrdinals']]
        self.assertEqual(sorted(occurrences), list(range(6)))
