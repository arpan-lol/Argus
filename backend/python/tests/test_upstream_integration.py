import tempfile
from pathlib import Path
from unittest import TestCase

from app.ingestion.extraction import source_span
from app.ingestion.parsers import parse, normalize
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.profiles import source_quality
from app.ingestion.publication import supported_spans


class SourceIntegrityTest(TestCase):
    def test_explicit_repeated_occurrence_keeps_its_location(self):
        chunk = {"text": "gelatin then gelatin", "startOffset": 100}
        second = source_span(chunk, 13, 20)
        record = {"quote": "gelatin", "sourceSpan": second, "sourceSpans": [second]}
        self.assertEqual(supported_spans(chunk, record)[1]["startOffset"], 113)
        record["sourceSpan"]["startOffset"] = 999
        with self.assertRaises(ValueError):
            supported_spans(chunk, record)

    def test_unlocated_repeated_quote_preserves_all_occurrences(self):
        chunk = {"text": "gelatin then gelatin", "startOffset": 100}
        spans, _, status = supported_spans(chunk, {"quote": "gelatin"})
        self.assertEqual([item["startOffset"] for item in spans], [100, 113])
        self.assertEqual(status, "multiple_occurrences")

    def test_relation_endpoints_must_exist(self):
        chunk = {"text": "Zeolite adsorbs lead."}
        output = {"entities": [{"key": "a", "name": "Zeolite", "quote": "Zeolite"}], "relationships": [{"subject": "a", "object": "missing", "predicate": "adsorbs", "quote": chunk["text"]}]}
        with self.assertRaises(ValueError):
            IngestionPipeline().validate_extraction(chunk, output)

    def test_abstract_only_source_is_labeled(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'abstract.nxml'
            file.write_text('<article><front><article-meta><abstract><p>Abstract content.</p></abstract></article-meta></front></article>')
            document = source_quality(normalize(parse(file)))
        self.assertEqual(document['metadata']['sourceCoverage']['coverageLabel'], 'abstract_only')

    def test_jats_body_text_is_retained_including_nested_text_and_tails(self):
        text = '<article><front><article-meta><title-group><article-title>Title</article-title></title-group><abstract><p>Abstract</p></abstract></article-meta></front><body>Lead<sec><title>Methods</title>Intro<p>Para <italic>inline</italic> tail</p><list><list-item><p>Item</p></list-item></list><fig><caption><p>Caption</p></caption></fig><table-wrap><table><tr><td>Cell</td></tr></table><table-wrap-foot><p>Foot</p></table-wrap-foot></table-wrap>End</sec>Body tail</body><back><ref-list><ref><mixed-citation>Reference</mixed-citation></ref></ref-list></back></article>'
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'sample.xml'
            file.write_text(text)
            parsed = parse(file)
        coverage = parsed["metadata"]["sourceCoverage"]
        self.assertTrue(coverage["bodyCoverageComplete"])
        self.assertEqual(coverage["bodyMissingNonWhitespaceCharacters"], 0)
        self.assertEqual(coverage["bodyAvailableTextSha256"], coverage["bodyRetainedTextSha256"])
        retained = ''.join(block['text'] for block in parsed['blocks'])
        for expected in ['Lead', 'inline', 'tail', 'Item', 'Caption', 'Foot', 'Body tail', 'Abstract', 'Reference']:
            self.assertIn(expected, retained)
