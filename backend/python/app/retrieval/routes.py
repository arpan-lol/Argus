import logging

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from . import tools
from .contracts import Invocation, SearchSources, TOOLS, ARTICLE_TOOLS, catalog
from .session import BudgetReached, Session


logger = logging.getLogger("argus.retrieval")
router = APIRouter()


def execute(name, arguments, project_id=None):
    if name == "recall":
        return {"tool": "recall", "outcome": "capability_disabled", "items": [], "reason": "Long-term findings memory is disabled by user choice", "generation": False}
    if name not in TOOLS:
        raise HTTPException(404, "Unknown retrieval tool")
    try:
        validated = TOOLS[name][0].model_validate(arguments)
    except ValidationError as error:
        raise HTTPException(400, [{"field": ".".join(map(str, item["loc"])), "message": item["msg"]} for item in error.errors()]) from error
    session = Session(name, validated.model_dump(), project_id)
    if not session.jobs:
        session.warnings.append("No active semantic publications for the configured embedding profile. Legacy corpus is not searched by these tools.")
        return session.finish({"items": []}, "no_published_sources")
    try:
        payload = getattr(tools, name)(session, validated)
        unknown = next((kind for field, kind in (("unknownChunkIds", "chunk"), ("unknownEntityIds", "entity"), ("unknownDocumentIds", "document")) if payload.get(field)), None)
        outcome = ("partial" if payload.get("items") else "unknown_" + unknown) if unknown else "partial" if payload.get("partial") else None
        if unknown:
            payload.update(inputError=True, recovery="Unknown lookup IDs do not establish missing source facts. Use search_sources or resolve_entities to discover the correct IDs before retrying.")
    except BudgetReached:
        payload, outcome = {"items": []}, "budget_exceeded"
    except Exception:
        logger.exception("Retrieval tool failed: %s run=%s", name, session.id)
        session.warnings.append("Requested retrieval failed; no results inferred. Inspect this run's trace and server logs.")
        payload, outcome = {"items": []}, "unavailable"
    return session.finish(payload, outcome)


@router.get("/retrieval/tools")
def tool_catalog():
    return {"tools": catalog(), "scope": "Published semantic sources only", "rawCypher": False, "schemaAccess": False, "agentLoop": True, "chatEndpoint": "/api/chat", "langgraphBinding": "app.retrieval.bindings.get_tools", "articleTools": ARTICLE_TOOLS, "longTermMemory": False, "mcp": {"transport": "stdio", "module": "app.retrieval.mcp_server"}}


@router.post("/retrieval/tools/{name}")
def invoke(name: str, body: Invocation):
    return execute(name, body.arguments)


@router.post("/retrieval/search")
def search(body: SearchSources):
    return execute("search_sources", body.model_dump())
