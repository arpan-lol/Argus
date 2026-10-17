import hashlib
import os
from urllib.parse import urlsplit, urlunsplit


def azure_base_url(value):
    parsed = urlsplit((value or "").strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Azure endpoint must be an HTTPS resource or v1 operation URL without credentials, query parameters, or fragments")
    path = parsed.path.rstrip("/")
    marker = "/openai/v1"
    if marker in path:
        prefix, suffix = path.split(marker, 1)
        if prefix or suffix not in {"", "/responses", "/chat/completions", "/embeddings"}:
            raise ValueError("Unsupported Azure OpenAI v1 endpoint path")
        path = marker
    elif path in {"", "/openai"}:
        path = marker
    else:
        raise ValueError("Azure endpoint must name the resource root or an OpenAI v1 operation")
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), path + "/", "", ""))


def resource_identity(variable):
    value = os.getenv(variable, "")
    if not value:
        return None
    return hashlib.sha256(azure_base_url(value).encode()).hexdigest()


def deployment_settings(kind):
    names = ("LLM2_DEPLOYMENT_NAME", "LLM2_DEPLOYMENT_URL", "LLM2_DEPLOYMENT_KEY") if kind == "llm" else ("EMBEDDING_MODEL_NAME", "EMBEDDING_MODEL_ENDPOINT", "EMBEDDING_MODEL_KEY")
    values = [os.getenv(name, "").strip() for name in names]
    if not all(values):
        raise ValueError("Configure all required Azure " + kind + " settings: " + ", ".join(names))
    if kind == "llm" and values[0].lower().startswith("gpt-5"):
        raise ValueError("GPT-5 is reserved for the agent; ingestion requires the LLM2 GPT-4.1-mini deployment")
    return values[0], azure_base_url(values[1]), values[2]
