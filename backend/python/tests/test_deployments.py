import json
import os
from unittest import TestCase, mock

import httpx
from openai import OpenAI
from pydantic import BaseModel

from app.ingestion.config import processing_config
from app.ingestion.deployments import base_url, deployment
from app.ingestion.providers import Providers
from app.ingestion.publication import semantic_graph_name


class Check(BaseModel):
    ok: bool


class DeploymentNamesTest(TestCase):
    def setUp(self):
        environment = mock.patch.dict(os.environ, {
            "LLM1_DEPLOYMENT_NAME": "gpt-5", "LLM1_DEPLOYMENT_URL": "https://primary.example/openai/v1/responses", "LLM1_DEPLOYMENT_KEY": "primary-test-key",
            "LLM2_DEPLOYMENT_NAME": "gpt-4.1-mini", "LLM2_DEPLOYMENT_URL": "https://secondary.example/openai/v1/responses", "LLM2_DEPLOYMENT_KEY": "secondary-test-key",
            "AZURE_API_KEY": "shared-test-key", "AZURE_OPENAI_ENDPOINT": "https://fallback.example/openai/v1",
            "EMBEDDING_MODEL_NAME": "text-embedding-3-large", "EMBEDDING_MODEL_ENDPOINT": "https://embeddings.example", "EMBEDDING_MODEL_KEY": "embedding-test-key",
        }, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.requests = []
        self.receipts = []
        self.config = processing_config()
        self.embedding_rows = [{"object": "embedding", "index": 0, "embedding": [1., 2., 3.]}]

    def transport(self, request):
        self.requests.append(request)
        if request.url.path.endswith('/embeddings'):
            return httpx.Response(200, json={"object": "list", "model": "text-embedding-3-large", "data": self.embedding_rows, "usage": {"prompt_tokens": 3, "total_tokens": 3}})
        return httpx.Response(200, json={"id": "resp-test", "object": "response", "created_at": 1, "model": json.loads(request.content)["model"], "status": "completed", "output": [{"id": "msg-test", "type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": '{"ok":true}', "annotations": []}]}], "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}})

    def client(self, **kwargs):
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(self.transport)))

    def test_new_names_override_legacy_llm_routes_without_storing_keys(self):
        with mock.patch.dict(os.environ, {"ARGUS_LLM_PROVIDER": "azure_inference", "ARGUS_EXTRACTION_MODEL": "old-model"}):
            config = processing_config()
        self.assertEqual(config["extractionModel"], "gpt-4.1-mini")
        self.assertEqual(config["resolutionModel"], "gpt-4.1-mini")
        self.assertEqual(config["llmBaseUrl"], "https://secondary.example/openai/v1")
        self.assertEqual(config["llmApi"], "responses")
        self.assertEqual(config["embeddingDimensions"], 3072)
        self.assertEqual(config["embeddingBaseUrl"], "https://embeddings.example/openai/v1")
        self.assertNotIn("test-key", json.dumps(config))

    def test_primary_and_secondary_use_their_own_keys_and_protocol(self):
        provider = Providers(self.config, self.receipts.append)
        with mock.patch("openai.OpenAI", side_effect=self.client), mock.patch.object(provider, "wait_for_capacity", return_value=0):
            self.assertEqual(provider.structured(Check, "Return JSON", {}), {"ok": True})
            self.assertEqual(provider.structured(Check, "Return JSON", {}, judge=True), {"ok": True})
        self.assertEqual(self.requests[0].headers["api-key"], "secondary-test-key")
        self.assertEqual(self.requests[1].headers["api-key"], "secondary-test-key")
        for request in self.requests:
            self.assertEqual(request.url.path, "/openai/v1/responses")
            body = json.loads(request.content)
            self.assertFalse(body["store"])
            self.assertTrue(body["text"]["format"]["strict"])
        self.assertNotIn("reasoning", json.loads(self.requests[0].content))
        self.assertNotIn("reasoning", json.loads(self.requests[1].content))
        self.assertNotIn("test-key", json.dumps(self.receipts))

    def test_embedding_ingestion_and_queries_use_same_endpoint_and_key(self):
        provider = Providers({**self.config, "embeddingDimensions": 3}, self.receipts.append)
        with mock.patch("openai.OpenAI", side_effect=self.client):
            self.assertEqual(provider.embed(["source"]), [[1., 2., 3.]])
            self.assertEqual(provider.embed_query("question"), [1., 2., 3.])
        for request in self.requests:
            self.assertEqual(str(request.url), "https://embeddings.example/openai/v1/embeddings")
            self.assertEqual(request.headers["api-key"], "embedding-test-key")
            self.assertEqual(json.loads(request.content)["dimensions"], 3)
        self.assertNotIn("test-key", json.dumps(self.receipts))

    def test_embedding_rejects_malformed_dimensions_and_indexes(self):
        provider = Providers({**self.config, "embeddingDimensions": 3})
        with mock.patch("openai.OpenAI", side_effect=self.client):
            self.embedding_rows[0]["embedding"] = [1.]
            with self.assertRaisesRegex(ValueError, "dimensions"):
                provider.embed(["source"])
            self.embedding_rows[0]["index"] = 5
            with self.assertRaisesRegex(ValueError, "indexes"):
                provider.embed(["source"])

    def test_vector_namespace_is_endpoint_specific(self):
        other = {**self.config, "embeddingBaseUrl": "https://other.example/openai/v1"}
        self.assertNotEqual(semantic_graph_name(self.config), semantic_graph_name(other))
        self.assertNotEqual(semantic_graph_name(self.config), semantic_graph_name({**self.config, "provider": "google"}))

    def test_url_normalization_rejects_embedded_secrets(self):
        self.assertEqual(base_url("https://example.com/openai/v1/responses/"), "https://example.com/openai/v1")
        for url in ("http://example.com", "https://user:secret@example.com", "https://example.com?key=secret", "https://example.com/#secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                base_url(url)
        with mock.patch.dict(os.environ, {"LLM1_DEPLOYMENT_URL": ""}), self.assertRaises(ValueError):
            deployment("LLM1")

    def test_shared_azure_key_is_a_fallback(self):
        with mock.patch.dict(os.environ, {"LLM1_DEPLOYMENT_KEY": ""}):
            self.assertEqual(Providers(self.config).credentials("azure_openai", "LLM1_DEPLOYMENT_KEY"), "shared-test-key")
