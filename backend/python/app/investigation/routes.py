from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .contracts import ChatRequest
from . import service


router = APIRouter(tags=["investigations"])


@router.get("/chat-config")
def chat_configuration():
    config = service.configuration()
    return {"model": config["chatModel"], "coverage": config["coverage"], "limits": config["chatLimits"]}


@router.post("/chat")
def chat(body: ChatRequest, request: Request):
    run_id, updates = service.start(body)
    if 'project_id' in request.path_params:
        return StreamingResponse(('data: ' + line.rstrip('\n') + '\n\n' for line in service.events(updates, run_id)), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
    return StreamingResponse(service.events(updates, run_id), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.get("/chat/{run_id}")
def investigation(run_id: UUID):
    return service.detail(str(run_id))


@router.post("/chat/{run_id}/resume")
def resume(run_id: UUID, request: Request):
    identifier, updates = service.start(run_id=str(run_id))
    if 'project_id' in request.path_params:
        return StreamingResponse(('data: ' + line.rstrip('\n') + '\n\n' for line in service.events(updates, identifier)), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
    return StreamingResponse(service.events(updates, identifier), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
