import json
import os
from unittest import TestCase, mock

import httpx
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.ingestion.config import fingerprint, processing_config
from app.ingestion.providers import ConfigurationRequired, Providers
from app.ingestion.publication import semantic_graph_name


class CheckResult(BaseModel):
    ok: bool


class AzureProvidersTest(TestCase):
    def setUp(self):
        self.config = {
            "provider": "google", "semanticGraph": "sources", "embeddingModel": "embedding-model", "embeddingDimensions": 2,
            "llmProvider": "azure_inference", "resolutionProvider": "azure_openai",
            "llmBaseUrl": "https://inference.example/models", "resolutionBaseUrl": "https://openai.example/openai/v1",
            "llmApiVersion": "2024-05-01-preview", "resolutionApiVersion": None,
            "extractionModel": "gpt-oss-120b", "resolutionModel": "identity-judge",
            "maxOutputTokens": 512, "modelTimeoutSeconds": 3, "promptVersion": "test",
        }
        self.receipts = []
        self.requests = []
        self.output = '{"ok":true}'

    def transport(self, request):
        self.requests.append(request)
        return httpx.Response(200, json={
            "id": "test-completion", "object": "chat.completion", "created": 1, "model": "deployed-model",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": self.output}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

    def client(self, **kwargs):
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(self.transport)))

    def invoke(self, judge=False):
        provider = Providers(self.config, self.receipts.append)
        with mock.patch.dict(os.environ, {"AZURE_INFERENCE_API_KEY": "test-inference-key", "AZURE_OPENAI_API_KEY": "test-openai-key"}), mock.patch.object(provider, "wait_for_capacity", return_value=0), mock.patch("openai.OpenAI", side_effect=self.client):
            return provider.structured(CheckResult, "Return JSON", {"source": "untrusted source text"}, judge=judge)

    def test_extraction_uses_inference_endpoint_with_strict_schema(self):
        self.assertEqual(self.invoke(), {"ok": True})
        request = self.requests[0]
        body = json.loads(request.content)
        self.assertEqual(str(request.url), "https://inference.example/models/chat/completions?api-version=2024-05-01-preview")
        self.assertEqual(request.headers["api-key"], "test-inference-key")
        self.assertEqual(body["model"], "gpt-oss-120b")
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertFalse(body["response_format"]["json_schema"]["schema"]["additionalProperties"])
        self.assertEqual(self.receipts[0]["usage"]["total_tokens"], 15)
        self.assertNotIn("test-inference-key", json.dumps(self.receipts))

    def test_resolution_routes_to_its_own_deployment(self):
        self.assertEqual(self.invoke(judge=True), {"ok": True})
        request = self.requests[0]
        body = json.loads(request.content)
        self.assertEqual(str(request.url), "https://openai.example/openai/v1/chat/completions")
        self.assertEqual(request.headers["api-key"], "test-openai-key")
        self.assertEqual(body["model"], "identity-judge")
        self.assertIn("max_completion_tokens", body)
        self.assertNotIn("temperature", body)

    def test_invalid_structured_output_fails_without_provider_fallback(self):
        self.output = '{"ok":"not a boolean"}'
        with self.assertRaises(ValidationError):
            self.invoke()
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.receipts[0]["status"], "failed")

    def test_old_profiles_keep_their_original_provider(self):
        provider = Providers({"provider": "google"})
        self.assertEqual(provider.llm_profile(), ("google", None, None))
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-google-key", "GOOGLE_API_KEY": ""}):
            self.assertEqual(Providers(self.config).credentials(), "test-google-key")

    def test_azure_profile_does_not_change_embedding_namespace(self):
        old = {key: value for key, value in self.config.items() if key in ("provider", "semanticGraph", "embeddingModel", "embeddingDimensions")}
        self.assertEqual(semantic_graph_name(old), semantic_graph_name(self.config))
        self.assertNotEqual(fingerprint(old), fingerprint(self.config))

    def test_endpoint_credentials_are_rejected(self):
        for endpoint in ("https://user:secret@example.com/models", "https://example.com/models?api-key=secret", "http://example.com/models"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ConfigurationRequired):
                Providers({**self.config, "llmBaseUrl": endpoint}).llm_profile()

    def test_configuration_records_routes_without_keys(self):
        with mock.patch.dict(os.environ, {"ARGUS_LLM_PROVIDER": "azure_inference", "ARGUS_RESOLUTION_PROVIDER": "azure_openai", "AZURE_INFERENCE_API_KEY": "private-inference-test-key", "AZURE_OPENAI_API_KEY": "private-openai-test-key", "AZURE_INFERENCE_ENDPOINT": "https://inference.example/models", "AZURE_OPENAI_BASE_URL": "https://openai.example/openai/v1"}):
            config = processing_config()
        self.assertEqual(config["llmProvider"], "azure_inference")
        self.assertEqual(config["resolutionProvider"], "azure_openai")
        self.assertNotIn("private-inference-test-key", json.dumps(config))
        self.assertNotIn("private-openai-test-key", json.dumps(config))
