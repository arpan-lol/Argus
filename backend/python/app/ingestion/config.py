import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .deployments import base_url, deployment

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def processing_config():
    configured = os.getenv("ARGUS_MODEL_PROVIDER", "")
    azure = configured in {"azure", "azure_openai"} or any(os.getenv(name) for name in ("LLM2_DEPLOYMENT_NAME", "LLM2_DEPLOYMENT_URL", "LLM2_DEPLOYMENT_KEY", "EMBEDDING_MODEL_NAME"))
    provider = "azure_openai" if azure else configured or ("google" if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") else "openai")
    extraction_model = os.getenv("LLM2_DEPLOYMENT_NAME", "") if azure else os.getenv("ARGUS_EXTRACTION_MODEL", "gemini-2.5-flash" if provider == "google" else "gpt-4o-mini")
    embedding_model = os.getenv("EMBEDDING_MODEL_NAME", "") if azure else os.getenv("ARGUS_EMBEDDING_MODEL", "models/gemini-embedding-001" if provider == "google" else "text-embedding-3-small")
    secondary = deployment("LLM2")
    if secondary and secondary["model"].lower().startswith("gpt-5"):
        raise ValueError("GPT-5 is reserved for the agent; configure LLM2 with GPT-4.1-mini for ingestion")
    llm_endpoint = secondary["baseUrl"] if secondary else None
    embedding_endpoint = base_url(os.getenv("EMBEDDING_MODEL_ENDPOINT")) if azure and os.getenv("EMBEDDING_MODEL_ENDPOINT") else None
    resource_hash = lambda value: hashlib.sha256((value.rstrip("/") + "/").encode()).hexdigest() if value else None
    config = {
        "contract": "argus-ingestion-3-parallel",
        "semanticGraph": os.getenv("ARGUS_SEMANTIC_GRAPH", "argus_sources_v2"),
        "parser": "source-blocks-3",
        "structureVersion": "heading-intersection-1",
        "chunker": "falkordb-sdk-v1.4.0-sentence-token-cap-offsets-1",
        "chunkTokens": int(os.getenv("ARGUS_CHUNK_TOKENS", "512")),
        "overlapSentences": int(os.getenv("ARGUS_CHUNK_OVERLAP_SENTENCES", "2")),
        "tokenEncoding": "cl100k_base",
        "provider": provider,
        "extractionModel": extraction_model,
        "resolutionModel": extraction_model if azure else os.getenv("ARGUS_RESOLUTION_MODEL", extraction_model),
        "embeddingModel": embedding_model,
        "embeddingProvider": provider,
        "embeddingDimensions": 3072 if azure else int(os.getenv("ARGUS_EMBEDDING_DIMENSIONS", "768" if provider == "google" else "1536")),
        "llmResourceIdentity": resource_hash(llm_endpoint),
        "embeddingResourceIdentity": resource_hash(embedding_endpoint),
        "providerProfile": "azure-v1-llm2-4.1-mini-embedding3large-native-1" if azure else "legacy-provider-1",
        "glinerModel": os.getenv("ARGUS_GLINER_MODEL", "urchade/gliner_small-v2.1"),
        "glinerThreshold": float(os.getenv("ARGUS_GLINER_THRESHOLD", "0.5")),
        "glinerWindowing": "model-word-cap-offsets-1",
        "glinerOverlapWords": int(os.getenv("ARGUS_GLINER_OVERLAP_WORDS", "32")),
        "entityTypes": json.loads(os.getenv("ARGUS_ENTITY_TYPES", "[]")),
        "retries": int(os.getenv("ARGUS_INGESTION_RETRIES", "3")),
        "retryBaseSeconds": float(os.getenv("ARGUS_RETRY_BASE_SECONDS", "2")),
        "resolutionCandidates": int(os.getenv("ARGUS_RESOLUTION_CANDIDATES", "5")),
        "resolutionSearchCandidates": int(os.getenv("ARGUS_RESOLUTION_SEARCH_CANDIDATES", "25")),
        "resolutionVersion": "batched-pairs-deferred-2",
        "resolutionBatchPairs": int(os.getenv("ARGUS_RESOLUTION_BATCH_PAIRS", "32")),
        "entityEmbeddingBatchSize": int(os.getenv("ARGUS_ENTITY_EMBED_BATCH_SIZE", "32")),
        "resolutionCosineThreshold": float(os.getenv("ARGUS_RESOLUTION_COSINE_THRESHOLD", "0.82")),
        "maxLlmCallsPerJob": int(os.getenv("ARGUS_MAX_LLM_CALLS_PER_JOB", "0")),
        "promptVersion": "argus-source-grounded-1",
        "extractionVersion": "two-attempt-gliner-fallback-1",
        "maxOutputTokens": int(os.getenv("ARGUS_MAX_OUTPUT_TOKENS", "8192")),
        "modelTimeoutSeconds": float(os.getenv("ARGUS_MODEL_TIMEOUT_SECONDS", "120")),
        "extractionThinkingBudget": int(os.getenv("ARGUS_EXTRACTION_THINKING_BUDGET", "0")),
        "resolutionThinkingBudget": int(os.getenv("ARGUS_RESOLUTION_THINKING_BUDGET", "0")),
        "ontologyPolicy": "automatic-corpus-extraction-settings-1",
        "corpusProfileId": None,
        "profileSampleDocuments": int(os.getenv("ARGUS_PROFILE_SAMPLE_DOCUMENTS", "8")),
        "profileSampleCharacters": int(os.getenv("ARGUS_PROFILE_SAMPLE_CHARACTERS", "32000")),
        "maxUploadBytes": int(os.getenv("ARGUS_MAX_UPLOAD_BYTES", "104857600")),
        "maxDecompressedBytes": int(os.getenv("ARGUS_MAX_DECOMPRESSED_BYTES", "209715200")),
        "maxExtractedTextCharacters": int(os.getenv("ARGUS_MAX_EXTRACTED_TEXT_CHARACTERS", "20971520")),
        "maxArchiveMembers": int(os.getenv("ARGUS_MAX_ARCHIVE_MEMBERS", "10000")),
    }
    if azure:
        config.update({
            "ingestionLlmRole": "LLM2",
            "llmProvider": "azure_openai",
            "resolutionProvider": "azure_openai",
            "llmBaseUrl": llm_endpoint,
            "resolutionBaseUrl": llm_endpoint,
            "llmApiVersion": None,
            "resolutionApiVersion": None,
            "llmApi": secondary["api"] if secondary else "responses",
            "resolutionApi": secondary["api"] if secondary else "responses",
            "llmCredentialEnv": "LLM2_DEPLOYMENT_KEY",
            "resolutionCredentialEnv": "LLM2_DEPLOYMENT_KEY",
            "embeddingBaseUrl": embedding_endpoint,
            "embeddingApiVersion": "2024-05-01-preview" if embedding_endpoint and embedding_endpoint.endswith("/models") else None,
            "embeddingCredentialEnv": "EMBEDDING_MODEL_KEY",
        })
    else:
        llm_provider = os.getenv("ARGUS_LLM_PROVIDER")
        if llm_provider:
            resolution_provider = os.getenv("ARGUS_RESOLUTION_PROVIDER") or llm_provider
            endpoints = {"azure_openai": os.getenv("AZURE_OPENAI_BASE_URL"), "azure_inference": os.getenv("AZURE_INFERENCE_ENDPOINT")}
            versions = {"azure_inference": os.getenv("AZURE_INFERENCE_API_VERSION", "2024-05-01-preview")}
            config.update({
                "llmProvider": llm_provider,
                "resolutionProvider": resolution_provider,
                "llmBaseUrl": os.getenv("ARGUS_LLM_BASE_URL") or endpoints.get(llm_provider),
                "resolutionBaseUrl": os.getenv("ARGUS_RESOLUTION_BASE_URL") or endpoints.get(resolution_provider),
                "llmApiVersion": os.getenv("ARGUS_LLM_API_VERSION") or versions.get(llm_provider),
                "resolutionApiVersion": os.getenv("ARGUS_RESOLUTION_API_VERSION") or versions.get(resolution_provider),
            })
    return config



def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
