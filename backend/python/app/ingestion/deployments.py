import os
from urllib.parse import urlsplit

from .azure import azure_base_url


def base_url(value, default_path="/openai/v1"):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Deployment URLs must use HTTPS without credentials, query strings or fragments")
    path = parsed.path.rstrip("/")
    for suffix in ("/responses", "/chat/completions", "/embeddings"):
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    if path == "/models":
        return parsed._replace(netloc=parsed.netloc.lower(), path=path).geturl()
    return azure_base_url(value).rstrip("/")


def deployment(prefix):
    name = os.getenv(prefix + "_DEPLOYMENT_NAME", "").strip()
    url = os.getenv(prefix + "_DEPLOYMENT_URL", "").strip()
    if not name and not url:
        return None
    if not name or not url:
        raise ValueError(f"Configure both {prefix}_DEPLOYMENT_NAME and {prefix}_DEPLOYMENT_URL")
    api = "responses" if url.rstrip("/").endswith("/responses") else "chat_completions"
    return {"model": name, "baseUrl": base_url(url), "api": api, "credentialEnv": prefix + "_DEPLOYMENT_KEY"}
