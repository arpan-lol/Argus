import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import TestCase, mock

from app.ingestion.extraction import extract_document, gliner_fallback
from app.ingestion.parsers import parse
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.providers import ConfigurationRequired
from app.ingestion.publication import quote_offset
from app.ingestion.resolution import resolve


class Pipeline:
    retry_call = IngestionPipeline.retry_call
    validate_extraction = IngestionPipeline.validate_extraction
    stage_extract = IngestionPipeline.stage_extract

    def __init__(self):
        self.saved = {}
        self.budget = mock.Mock()
        self.call_recorder = mock.Mock(return_value=lambda value: None)
        self.chunk = {"id": "chunk-1", "text": "gelatin in water", "startOffset": 10, "endOffset": 26}

    def item(self, job, stage, key):
        return self.saved.get((stage, key))

    def save_item(self, job, stage, key, value):
        self.saved[stage, key] = value

    def artifact(self, job, stage):
        return {"normalize": {"metadata": {"title": "Test source"}}, "chunk": {"chunks": [self.chunk]}}.get(stage)


class Database:
    def execute(self, *args):
        return self

    def fetchone(self):
        return None

    @contextmanager
    def connection(self):
        yield self


class UpstreamIntegrationTest(TestCase):
    def setUp(self):
        self.pipeline = Pipeline()
        self.job = {"id": "job-1", "filename": "test.txt", "configuration": {"entityTypes": ["protein"], "retries": 3, "retryBaseSeconds": 0, "promptVersion": "test", "extractionVersion": "two-attempt-gliner-fallback-1", "embeddingDimensions": 3, "embeddingModel": "test"}}
        self.provider = mock.Mock()
        self.provider.gliner.return_value = {"mentions": [{"start": 0, "end": 7, "label": "protein", "score": .9}]}
        self.provider.safe_error.side_effect = str
        self.provider.structured.side_effect = ValueError("invalid extraction")
        self.database = Database()

    def extract(self):
        with mock.patch("app.ingestion.extraction.Providers", return_value=self.provider), mock.patch("app.ingestion.extraction.connection", self.database.connection):
            return self.pipeline.stage_extract(self.job)

    def test_pipeline_wires_two_attempt_fallback_without_assertions(self):
        result = self.extract()
        item = self.pipeline.item("job-1", "extract", "chunk-1")
        self.assertEqual(self.provider.structured.call_count, 2)
        self.assertEqual(result["fallbackChunks"], 1)
        self.assertEqual(result["quality"], "partial_connections")
        self.assertEqual(item["relationships"], [])
        self.assertFalse(item["entities"][0]["llmVerified"])
        self.assertEqual(item["entities"][0]["sourceSpan"]["startOffset"], 10)
        self.assertEqual(item["entities"][0]["quote"], "gelatin")
        self.extract()
        self.assertEqual(self.provider.structured.call_count, 2)

    def test_access_errors_do_not_become_fallback(self):
        error = RuntimeError("deployment missing")
        error.status_code = 404
        self.provider.structured.side_effect = error
        with self.assertRaises(ConfigurationRequired):
            self.extract()
        self.assertEqual(self.provider.structured.call_count, 1)
        self.assertIsNone(self.pipeline.item("job-1", "extract", "chunk-1"))

    def test_valid_extraction_keeps_verification_and_exact_span(self):
        self.provider.structured.side_effect = None
        self.provider.structured.return_value = {"entities": [{"key": "e1", "name": "gelatin", "quote": "gelatin", "description": "", "entity_type": "protein"}], "relationships": []}
        result = self.extract()
        item = self.pipeline.item("job-1", "extract", "chunk-1")
        self.assertEqual(result["fallbackChunks"], 0)
        self.assertTrue(item["entities"][0]["llmVerified"])
        self.assertEqual(item["entities"][0]["sourceSpan"]["endOffset"], 17)

    def test_fallback_defers_resolution_without_llm_or_neighbor_queries(self):
        self.extract()
        self.provider.structured.reset_mock()
        self.provider.embed.return_value = [[1., 2., 3.]]
        graph = mock.Mock()
        with mock.patch("app.ingestion.resolution.Providers", return_value=self.provider), mock.patch("app.ingestion.resolution.connection", self.database.connection), mock.patch("app.ingestion.resolution.graph_connection", return_value=graph), mock.patch("app.ingestion.resolution.index"):
            result = resolve(self.pipeline, self.job)
        self.assertEqual(result["deferredMentions"], 1)
        self.assertEqual(result["candidatePairs"], 0)
        self.provider.structured.assert_not_called()
        self.assertTrue(all('queryNodes' not in args.args[0] for args in graph.query.call_args_list))
        resolutions = [value for (stage, key), value in self.pipeline.saved.items() if stage == "resolve"]
        self.assertEqual(resolutions[0]["decision"], "deferred")

    def test_fallback_rejects_invalid_span(self):
        candidates = {"mentions": [{"start": 100, "end": 200, "label": "protein", "score": .9}]}
        with self.assertRaises(ValueError):
            gliner_fallback(self.pipeline.chunk, candidates, ["protein"], "failed", 2)

    def test_publication_preserves_repeated_fallback_mention_location(self):
        chunk = {"text": "gelatin then gelatin", "startOffset": 100}
        candidates = {"mentions": [{"start": 13, "end": 20, "label": "protein", "score": .9}]}
        result = gliner_fallback(chunk, candidates, ["protein"], "failed", 2)
        self.assertEqual(quote_offset(chunk, result["entities"][0]), 13)
        result["entities"][0]["sourceSpan"]["startOffset"] = 999
        with self.assertRaises(ValueError):
            quote_offset(chunk, result["entities"][0])

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
