from unittest import TestCase, mock

from app.ingestion.config import processing_config
from app.ingestion.extraction import extract_document
from app.ingestion.pipeline import IngestionPipeline, PauseRequested
from app.ingestion.providers import ConfigurationRequired


class ExtractionRetriesTest(TestCase):
    def setUp(self):
        self.saved = {}
        self.pipeline = mock.Mock()
        self.pipeline.item.side_effect = lambda job, stage, key: self.saved.get((stage, key))
        self.pipeline.save_item.side_effect = lambda job, stage, key, value: self.saved.update({(stage, key): value})
        self.pipeline.job_row.return_value = {"stop_requested": False}
        self.pipeline.retry_call.side_effect = lambda *args, **kwargs: IngestionPipeline.retry_call(self.pipeline, *args, **kwargs)
        self.pipeline.validate_extraction.side_effect = lambda *args: IngestionPipeline.validate_extraction(self.pipeline, *args)
        self.chunk = {"id": "chunk-1", "text": "gelatin in water", "startOffset": 10, "endOffset": 26}
        self.pipeline.artifact.side_effect = lambda job, stage: {"normalize": {"metadata": {"title": "Test source"}}, "chunk": {"chunks": [self.chunk]}, "configure": {}}[stage]
        self.job = {"id": "job-1", "filename": "test.txt", "configuration": {"entityTypes": ["protein"], "retries": 9, "retryBaseSeconds": 0, "promptVersion": "test"}}
        self.provider = mock.Mock()
        self.provider.gliner.return_value = {"mentions": [{"start": 0, "end": 7, "label": "protein", "score": .9}]}
        self.provider.safe_error.side_effect = str
        self.valid = {"entities": [{"key": "e1", "name": "gelatin", "quote": "gelatin", "description": "", "entity_type": "protein"}], "relationships": []}
        self.providers = mock.patch("app.ingestion.extraction.Providers", return_value=self.provider)
        self.events = mock.patch("app.projects.events.job_event")
        self.providers.start()
        self.events.start()
        self.addCleanup(self.providers.stop)
        self.addCleanup(self.events.stop)

    def test_retries_invalid_extraction_once_then_succeeds(self):
        self.provider.structured.side_effect = [ValueError("invalid relationship endpoint"), self.valid]
        result = extract_document(self.pipeline, self.job)
        self.assertEqual(self.provider.structured.call_count, 2)
        self.assertEqual(result["fallbackChunks"], 0)
        item = self.saved["extract", "chunk-1"]
        self.assertEqual(item["metadata"]["llmAttempts"], 2)
        self.assertTrue(item["entities"][0]["llmVerified"])
        self.assertEqual(self.provider.structured.call_args_list[1].args[2]["previous_validation_error"], "invalid relationship endpoint")

    def test_two_failures_keep_mentions_without_connections_and_replay(self):
        self.provider.structured.side_effect = ValueError("invalid relationship endpoint")
        extract_document(self.pipeline, self.job)
        item = self.saved["extract", "chunk-1"]
        self.assertEqual(self.provider.structured.call_count, 2)
        self.assertEqual(item["metadata"]["llmAttempts"], 2)
        self.assertEqual(item["relationships"], [])
        self.assertEqual(item["entities"][0]["quote"], "gelatin")
        self.assertFalse(item["entities"][0]["llmVerified"])
        extract_document(self.pipeline, self.job)
        self.assertEqual(self.provider.structured.call_count, 2)

    def test_configuration_and_budget_errors_remain_explicit(self):
        self.provider.structured.side_effect = ConfigurationRequired("spending limit reached")
        with self.assertRaises(ConfigurationRequired):
            extract_document(self.pipeline, self.job)
        self.assertEqual(self.provider.structured.call_count, 1)
        self.assertNotIn(("extract", "chunk-1"), self.saved)

    def test_new_configuration_records_two_attempt_policy(self):
        self.assertEqual(processing_config()["extractionVersion"], "two-attempt-gliner-fallback-2")

    def test_pause_on_second_attempt_does_not_publish_fallback(self):
        self.provider.structured.side_effect = [ValueError("invalid extraction"), PauseRequested()]
        with self.assertRaises(PauseRequested):
            extract_document(self.pipeline, self.job)
        self.assertNotIn(("extract", "chunk-1"), self.saved)
