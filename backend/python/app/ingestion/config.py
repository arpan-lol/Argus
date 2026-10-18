import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .deployments import base_url, deployment

SDK_DEFAULT_ENTITY_TYPES = ("Person", "Organization", "Technology", "Product", "Location", "Date", "Event", "Concept", "Law", "Dataset", "Method")

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def processing_config(project_id=None):
    provider = "azure_openai"
    extraction_model = os.getenv("LLM2_DEPLOYMENT_NAME", "").strip()
    embedding_model = os.getenv("EMBEDDING_MODEL_NAME", "").strip()
    secondary = deployment("LLM2")
    if secondary and secondary["model"].lower().startswith("gpt-5"):
        raise ValueError("GPT-5 is reserved for the agent; configure LLM2 with GPT-4.1-mini for ingestion")
    llm_endpoint = secondary["baseUrl"] if secondary else None
    embedding_endpoint = base_url(os.getenv("EMBEDDING_MODEL_ENDPOINT")) if os.getenv("EMBEDDING_MODEL_ENDPOINT") else None
    resource_hash = lambda value: hashlib.sha256((value.rstrip("/") + "/").encode()).hexdigest() if value else None
    config = {
        "contract": "argus-ingestion-7-deferred-entity-vectors",
        "semanticGraph": os.getenv("ARGUS_SEMANTIC_GRAPH", "argus_sources_v2"),
        "parser": "category-routed-source-blocks-5",
        "structureVersion": "heading-intersection-1",
        "chunker": "structure-sentence-clause-token-cap-offsets-2",
        "chunkTokens": int(os.getenv("ARGUS_CHUNK_TOKENS", "512")),
        "overlapSentences": int(os.getenv("ARGUS_CHUNK_OVERLAP_SENTENCES", "2")),
        "tokenEncoding": "cl100k_base",
        "profileTokenEncoding": "o200k_base",
        "provider": provider,
        "extractionModel": extraction_model,
        "embeddingModel": embedding_model,
        "embeddingProvider": provider,
        "embeddingDimensions": 3072,
        "entityEmbeddingPolicy": "explicit-post-ingestion-finalization",
        "entityIdentityPolicy": "exact-normalized-name-type-including-short-names-2",
        "codeAgentVersion": "flow-behavior-builder-4",
        "codeAgentTokenBudget": int(os.getenv("ARGUS_CODE_AGENT_TOKEN_BUDGET", "300000")),
        "codeAgentMaxSteps": int(os.getenv("ARGUS_CODE_AGENT_MAX_STEPS", "96")),
        "codeAgentContextTokens": int(os.getenv("ARGUS_CODE_AGENT_CONTEXT_TOKENS", "18000")),
        "codeAgentOutputTokens": int(os.getenv("ARGUS_CODE_AGENT_OUTPUT_TOKENS", "2048")),
        "embeddingTokensPerMinute": int(os.getenv('ARGUS_EMBEDDING_TOKENS_PER_MINUTE', '135000')),
        "llmResourceIdentity": resource_hash(llm_endpoint),
        "embeddingResourceIdentity": resource_hash(embedding_endpoint),
        "providerProfile": "azure-v1-llm2-4.1-mini-embedding3large-native-2",
        "glinerModel": os.getenv("ARGUS_GLINER_MODEL", "urchade/gliner_small-v2.1"),
        "glinerThreshold": float(os.getenv("ARGUS_GLINER_THRESHOLD", "0.5")),
        "glinerWindowing": "model-word-cap-offsets-1",
        "glinerOverlapWords": int(os.getenv("ARGUS_GLINER_OVERLAP_WORDS", "32")),
        "relexModel": os.getenv("ARGUS_RELEX_MODEL", "knowledgator/gliner-relex-base-v1.0"),
        "relexBatchSize": int(os.getenv('ARGUS_RELEX_BATCH_SIZE', '4')),
        "relexMaxSpans": int(os.getenv('ARGUS_RELEX_MAX_SPANS', '64')),
        "localModelThreads": int(os.getenv('ARGUS_LOCAL_MODEL_THREADS', str(min(8, os.cpu_count() or 1)))),
        "localModelDevice": os.getenv('ARGUS_LOCAL_MODEL_DEVICE', 'auto'),
        "localModelCacheSize": int(os.getenv('ARGUS_LOCAL_MODEL_CACHE_SIZE', '0')),
        "relexEntityThreshold": float(os.getenv("ARGUS_RELEX_ENTITY_THRESHOLD", "0.4")),
        "relexRelationThreshold": float(os.getenv("ARGUS_RELEX_RELATION_THRESHOLD", "0.8")),
        "relexAdjacencyThreshold": float(os.getenv("ARGUS_RELEX_ADJACENCY_THRESHOLD", "0.65")),
        "categories": ["general_documents"],
        "entityTypes": json.loads(os.getenv("ARGUS_ENTITY_TYPES", "[]")),
        "retries": int(os.getenv("ARGUS_INGESTION_RETRIES", "3")),
        "retryBaseSeconds": float(os.getenv("ARGUS_RETRY_BASE_SECONDS", "2")),
        "promptVersion": "batched-category-label-discovery-code-routing-2",
        "extractionVersion": "local-relex-source-context-2",
        "maxOutputTokens": int(os.getenv("ARGUS_MAX_OUTPUT_TOKENS", "8192")),
        "modelTimeoutSeconds": float(os.getenv("ARGUS_MODEL_TIMEOUT_SECONDS", "120")),
        "extractionThinkingBudget": int(os.getenv("ARGUS_EXTRACTION_THINKING_BUDGET", "0")),
        "ontologyPolicy": "workspace-categories-bounded-sampling-1",
        "corpusProfileId": None,
        "profileStartWindowSeconds": 30,
        "profileTokenBudget": int(os.getenv("ARGUS_PROFILE_TOKEN_BUDGET", "300000")),
        "profileBatchTokens": min(10000, int(os.getenv("ARGUS_PROFILE_BATCH_TOKENS", "10000"))),
        "profileConcurrencyLimit": min(4, max(1, int(os.getenv("ARGUS_PROFILE_CONCURRENCY", "4")))),
        "profileOutputTokens": int(os.getenv("ARGUS_PROFILE_OUTPUT_TOKENS", "1536")),
        "profileEntityCap": 24,
        "profileRelationshipCap": 32,
        "layoutParser": os.getenv("ARGUS_LAYOUT_PARSER", "auto"),
        "maxUploadBytes": int(os.getenv("ARGUS_MAX_UPLOAD_BYTES", "104857600")),
        "maxUploadFiles": int(os.getenv("ARGUS_MAX_UPLOAD_FILES", "10000")),
        "maxDecompressedBytes": int(os.getenv("ARGUS_MAX_DECOMPRESSED_BYTES", "209715200")),
        "maxExtractedTextCharacters": int(os.getenv("ARGUS_MAX_EXTRACTED_TEXT_CHARACTERS", "20971520")),
        "maxArchiveMembers": int(os.getenv("ARGUS_MAX_ARCHIVE_MEMBERS", "10000")),
    }
    config.update({
        "ingestionLlmRole": "LLM2",
        "llmProvider": "azure_openai",
        "llmBaseUrl": llm_endpoint,
        "llmApiVersion": None,
        "llmApi": secondary["api"] if secondary else "responses",
        "llmCredentialEnv": "LLM2_DEPLOYMENT_KEY",
        "embeddingBaseUrl": embedding_endpoint,
        "embeddingApiVersion": "2024-05-01-preview" if embedding_endpoint and embedding_endpoint.endswith("/models") else None,
        "embeddingCredentialEnv": "EMBEDDING_MODEL_KEY",
    })
    from app.projects.scope import apply_project
    return apply_project(config, project_id)



def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
