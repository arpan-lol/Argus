import json
import time
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.database import connection
from app.projects.scope import current_project
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


@router.post("/chat/start")
def start_chat(body: ChatRequest):
    run_id, _ = service.start(body)
    return {"runId": run_id}


@router.get("/chat/history")
def chat_history(limit: int = 100):
    project_id = current_project.get()
    if not project_id:
        return {"conversations": []}
    maximum = min(max(limit, 1), 300)
    with connection() as conn:
        rows = conn.execute("SELECT id,request,status,created_at,updated_at FROM chat_runs WHERE configuration->>'projectId'=%s ORDER BY created_at DESC,id DESC LIMIT %s", (project_id, maximum)).fetchall()
    groups = {}
    for row in rows:
        conversation_id = row["request"].get("conversation_id") or str(row["id"])
        group = groups.setdefault(conversation_id, {"id": conversation_id, "title": row["request"]["query"], "updatedAt": row["updated_at"].isoformat(), "runs": []})
        group["runs"].append({"id": str(row["id"]), "query": row["request"]["query"], "status": row["status"]})
    for group in groups.values():
        group["runs"].reverse()
        group["title"] = group["runs"][0]["query"]
    return {"conversations": list(groups.values()), "limited": len(rows) == maximum}


@router.get("/chat/{run_id}/events")
def saved_chat_events(run_id: UUID, after: int = 0):
    service.get_run(str(run_id))

    def stream():
        cursor = max(0, after)
        heartbeat = time.monotonic()
        while True:
            with connection() as conn:
                events = conn.execute("SELECT sequence,kind,payload FROM chat_events WHERE run_id=%s AND sequence>%s ORDER BY sequence LIMIT 100", (str(run_id), cursor)).fetchall()
            for event in events:
                cursor = event["sequence"]
                payload = {"type": event["kind"], **event["payload"], "sequence": cursor}
                yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
                if event["kind"] in ("done", "error"):
                    return
            if time.monotonic() - heartbeat >= 8:
                yield ": heartbeat\n\n"
                heartbeat = time.monotonic()
            time.sleep(.3)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.get("/chat/{run_id}")
def investigation(run_id: UUID):
    return service.detail(str(run_id))


@router.post("/chat/{run_id}/resume")
def resume(run_id: UUID, request: Request):
    identifier, updates = service.start(run_id=str(run_id))
    if 'project_id' in request.path_params:
        return StreamingResponse(('data: ' + line.rstrip('\n') + '\n\n' for line in service.events(updates, identifier)), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
    return StreamingResponse(service.events(updates, identifier), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/chat/{run_id}/resume-start")
def resume_chat(run_id: UUID):
    identifier, _ = service.start(run_id=str(run_id))
    return {"runId": identifier}
