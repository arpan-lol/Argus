import hashlib
import os

from .deployments import base_url, deployment


def ingestion_configuration_failure(config, error):
    if config.get("ingestionLlmRole") != "LLM2":
        return False
    if getattr(error, "status_code", None) in (401, 403, 404):
        return True
    body = getattr(error, "body", None)
    detail = str(body if body is not None else error).casefold()
    return any(code in detail for code in ("insufficient_quota", "billing_hard_limit_reached", "billing_not_active", "invalid_api_key", "deploymentnotfound", "deployment_not_found", "invalidapiversionparameter", "unsupportedapiversion"))


def validate_ingestion_llm(config, judge=False):
    if config.get("ingestionLlmRole") != "LLM2":
        return
    current = deployment("LLM2")
    if not current or not os.getenv("LLM2_DEPLOYMENT_KEY", "").strip():
        raise ValueError("Configure the complete LLM2 deployment before starting ingestion")
    if current["model"].lower().startswith("gpt-5"):
        raise ValueError("GPT-5 is reserved for the agent; ingestion must use LLM2 GPT-4.1-mini")
    label = "resolution" if judge else "llm"
    model = config["resolutionModel"] if judge else config["extractionModel"]
    resource = hashlib.sha256((current["baseUrl"].rstrip("/") + "/").encode()).hexdigest()
    if model != current["model"] or config.get(label + "Provider") != "azure_openai" or config.get(label + "BaseUrl") != current["baseUrl"] or config.get(label + "Api") != current["api"] or config.get("llmResourceIdentity") != resource or config.get(label + "CredentialEnv") != "LLM2_DEPLOYMENT_KEY":
        raise ValueError("LLM2 settings changed; create a new processing configuration before continuing ingestion")


def validate_ingestion_embeddings(config):
    if config.get("ingestionLlmRole") != "LLM2":
        return
    name = os.getenv("EMBEDDING_MODEL_NAME", "").strip()
    endpoint = os.getenv("EMBEDDING_MODEL_ENDPOINT", "").strip()
    if not name or not endpoint or not os.getenv("EMBEDDING_MODEL_KEY", "").strip():
        raise ValueError("Configure EMBEDDING_MODEL_NAME, EMBEDDING_MODEL_ENDPOINT and EMBEDDING_MODEL_KEY")
    normalized = base_url(endpoint)
    resource = hashlib.sha256((normalized.rstrip("/") + "/").encode()).hexdigest()
    if config.get("embeddingModel") != name or config.get("embeddingBaseUrl") != normalized or config.get("embeddingResourceIdentity") != resource or config.get("embeddingDimensions") != 3072 or config.get("embeddingCredentialEnv") != "EMBEDDING_MODEL_KEY":
        raise ValueError("Embedding settings changed; create a new native-3072-dimension processing configuration")
