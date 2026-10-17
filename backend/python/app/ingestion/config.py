import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def processing_config():
    provider = os.getenv("ARGUS_MODEL_PROVIDER", "google" if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") else "openai")
    return {
        "contract": "argus-ingestion-2",
        "semanticGraph": os.getenv("ARGUS_SEMANTIC_GRAPH", "argus_sources_v2"),
        "parser": "source-blocks-2",
        "structureVersion": "heading-intersection-1",
        "chunker": "falkordb-sdk-v1.4.0-sentence-token-cap-offsets-1",
        "chunkTokens": int(os.getenv("ARGUS_CHUNK_TOKENS", "512")),
        "overlapSentences": int(os.getenv("ARGUS_CHUNK_OVERLAP_SENTENCES", "2")),
        "tokenEncoding": "cl100k_base",
        "provider": provider,
        "extractionModel": os.getenv("ARGUS_EXTRACTION_MODEL", "gemini-2.5-flash" if provider == "google" else "gpt-4o-mini"),
        "resolutionModel": os.getenv("ARGUS_RESOLUTION_MODEL", os.getenv("ARGUS_EXTRACTION_MODEL", "gemini-2.5-flash" if provider == "google" else "gpt-4.1-mini")),
        "embeddingModel": os.getenv("ARGUS_EMBEDDING_MODEL", "models/gemini-embedding-001" if provider == "google" else "text-embedding-3-small"),
        "embeddingDimensions": int(os.getenv("ARGUS_EMBEDDING_DIMENSIONS", "768" if provider == "google" else "1536")),
        "glinerModel": os.getenv("ARGUS_GLINER_MODEL", "urchade/gliner_small-v2.1"),
        "glinerThreshold": float(os.getenv("ARGUS_GLINER_THRESHOLD", "0.5")),
        "glinerWindowing": "model-word-cap-offsets-1",
        "glinerOverlapWords": int(os.getenv("ARGUS_GLINER_OVERLAP_WORDS", "32")),
        "entityTypes": json.loads(os.getenv("ARGUS_ENTITY_TYPES", "[]")),
        "retries": int(os.getenv("ARGUS_INGESTION_RETRIES", "3")),
        "retryBaseSeconds": float(os.getenv("ARGUS_RETRY_BASE_SECONDS", "2")),
        "resolutionCandidates": int(os.getenv("ARGUS_RESOLUTION_CANDIDATES", "5")),
        "resolutionSearchCandidates": int(os.getenv("ARGUS_RESOLUTION_SEARCH_CANDIDATES", "25")),
        "resolutionVersion": "batched-pairs-1",
        "resolutionBatchPairs": int(os.getenv("ARGUS_RESOLUTION_BATCH_PAIRS", "32")),
        "entityEmbeddingBatchSize": int(os.getenv("ARGUS_ENTITY_EMBED_BATCH_SIZE", "32")),
        "resolutionCosineThreshold": float(os.getenv("ARGUS_RESOLUTION_COSINE_THRESHOLD", "0.82")),
        "maxLlmCallsPerJob": int(os.getenv("ARGUS_MAX_LLM_CALLS_PER_JOB", "0")),
        "promptVersion": "argus-source-grounded-1",
        "extractionVersion": "typed-grounding-repair-2",
        "maxOutputTokens": int(os.getenv("ARGUS_MAX_OUTPUT_TOKENS", "8192")),
        "modelTimeoutSeconds": float(os.getenv("ARGUS_MODEL_TIMEOUT_SECONDS", "120")),
        "extractionThinkingBudget": int(os.getenv("ARGUS_EXTRACTION_THINKING_BUDGET", "0")),
        "resolutionThinkingBudget": int(os.getenv("ARGUS_RESOLUTION_THINKING_BUDGET", "0")),
        "ontologyPolicy": "configured-types-or-document-inferred-v1",
        "maxUploadBytes": int(os.getenv("ARGUS_MAX_UPLOAD_BYTES", "104857600")),
        "maxDecompressedBytes": int(os.getenv("ARGUS_MAX_DECOMPRESSED_BYTES", "209715200")),
        "maxExtractedTextCharacters": int(os.getenv("ARGUS_MAX_EXTRACTED_TEXT_CHARACTERS", "20971520")),
        "maxArchiveMembers": int(os.getenv("ARGUS_MAX_ARCHIVE_MEMBERS", "10000")),
    }


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
