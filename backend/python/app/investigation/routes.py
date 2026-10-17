from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .contracts import ChatRequest
from . import service


router = APIRouter(tags=["investigations"])


@router.get("/chat-config")
def chat_configuration():
    config = service.configuration()
    return {"model": config["chatModel"], "coverage": config["coverage"], "limits": config["chatLimits"]}


@router.post("/chat")
def chat(body: ChatRequest):
    run_id, updates = service.start(body)
    return StreamingResponse(service.events(updates, run_id), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.get("/chat/{run_id}")
def investigation(run_id: UUID):
    return service.detail(str(run_id))


@router.post("/chat/{run_id}/resume")
def resume(run_id: UUID):
    identifier, updates = service.start(run_id=str(run_id))
    return StreamingResponse(service.events(updates, identifier), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
