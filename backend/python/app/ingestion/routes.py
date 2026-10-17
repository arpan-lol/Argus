import os
import hashlib
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb

from app.database import connection

from .config import fingerprint, processing_config
from .pipeline import IngestionPipeline, STAGES, serialize
from .structure import sections_for, chunk_sections


router = APIRouter(prefix="/ingestion", tags=["ingestion"])
pipeline = IngestionPipeline()


@router.get("/jobs")
def jobs(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return pipeline.list_jobs(limit, offset)


@router.get("/jobs/{job_id}")
def job(job_id: str):
    try:
        return pipeline.get_job(job_id)
    except KeyError:
        raise HTTPException(404, "Ingestion job not found")


@router.post("/jobs", status_code=202)
async def upload(file: UploadFile = File(...), source_id: str | None = Form(None), through: str = Form("publish")):
    if through not in STAGES:
        raise HTTPException(400, "Unknown ingestion stage")
    filename = Path(file.filename or "uploaded-source.txt").name
    maximum = processing_config()["maxUploadBytes"]
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix="-" + filename) as target:
            temporary = Path(target.name)
            received = 0
            digest = hashlib.sha256()
            while data := await file.read(1024 * 1024):
                received += len(data)
                if received > maximum:
                    raise HTTPException(413, f"File exceeds configured {maximum} byte upload limit")
                target.write(data)
                digest.update(data)
        if source_id:
            with connection() as conn:
                existing = conn.execute("SELECT id FROM ingestion_sources WHERE id=%s", (source_id,)).fetchone()
            if not existing:
                raise HTTPException(404, "Explicit replacement source was not found")
        result = pipeline.register_file(temporary, source_id=source_id or "upload:" + digest.hexdigest(), filename=filename)
        try:
            return pipeline.enqueue(result["id"], through)
        except RuntimeError:
            raise HTTPException(409, "This file already has an active ingestion worker")
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
        await file.close()


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry(job_id: str, through: str = "publish"):
    result = job(job_id)
    if through not in {"register", "parse", "normalize", "chunk", "embed", "extract", "resolve", "validate", "publish"}:
        raise HTTPException(400, "Unknown ingestion stage")
    try:
        return pipeline.enqueue(job_id, through)
    except RuntimeError:
        raise HTTPException(409, "This job already has an active ingestion worker")


@router.get("/jobs/{job_id}/events")
def events(job_id: str, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    job(job_id)
    with connection() as conn:
        rows = conn.execute("SELECT stage,item_id,payload,created_at FROM ingestion_items WHERE job_id=%s AND stage IN ('provider_call','retry_history','profile') ORDER BY created_at LIMIT %s OFFSET %s", (job_id, limit, offset)).fetchall()
    return {"events": serialize(rows), "limit": limit, "offset": offset}


@router.get("/jobs/{job_id}/artifacts/{stage}")
def artifact(job_id: str, stage: str):
    job(job_id)
    result = pipeline.artifact(job_id, stage)
    if result is None:
        raise HTTPException(404, "Stage has no completed artifact")
    return result


@router.get("/jobs/{job_id}/resolutions")
def resolutions(job_id: str, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    job(job_id)
    with connection() as conn:
        rows = conn.execute("SELECT * FROM ingestion_resolution_decisions WHERE job_id=%s ORDER BY created_at LIMIT %s OFFSET %s", (job_id, limit, offset)).fetchall()
    return {"resolutions": serialize(rows), "limit": limit, "offset": offset}


@router.post("/resolutions/{decision_id}/revert", status_code=202)
def revert_resolution(decision_id: str):
    from .publication import publication_lease_key
    with connection() as conn:
        decision = conn.execute("SELECT * FROM ingestion_resolution_decisions WHERE id=%s", (decision_id,)).fetchone()
    if not decision:
        raise HTTPException(404, "Resolution decision not found")
    record = pipeline.job_row(decision["job_id"])
    source_key = publication_lease_key(record["source_id"])
    with connection() as lease:
        acquired = lease.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired", (record["id"],)).fetchone()["acquired"]
        if not acquired:
            raise HTTPException(409, "This job has an active worker. Retry the reversal after it finishes.")
        source_acquired = False
        try:
            source_acquired = lease.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired", (source_key,)).fetchone()["acquired"]
            if not source_acquired:
                raise HTTPException(409, "Another revision of this source is publishing. Retry the reversal after it finishes.")
            decision = lease.execute("SELECT * FROM ingestion_resolution_decisions WHERE id=%s FOR UPDATE", (decision_id,)).fetchone()
            if decision["decision"] != "same" or decision["reverted"]:
                raise HTTPException(409, "Only an accepted identity merge that has not already been reversed can be reversed")
            if not lease.execute("SELECT 1 FROM ingestion_publications WHERE job_id=%s AND active", (record["id"],)).fetchone():
                raise HTTPException(409, "Only the currently published source revision can have a merge reversed")
            mention_id = decision["mention_id"]
            entity = None
            chunks = pipeline.artifact(record["id"], "chunk")
            if not chunks:
                raise HTTPException(409, "Original chunk artifacts are unavailable")
            for chunk in chunks["chunks"]:
                extraction = pipeline.item(record["id"], "extract", chunk["id"])
                if not extraction:
                    continue
                for extracted in extraction["entities"]:
                    if "mention:" + fingerprint([chunk["id"], extracted["key"]]) == mention_id:
                        entity = extracted
                        break
                if entity is not None:
                    break
            embedded = pipeline.item(record["id"], "entity_embed", mention_id)
            if entity is None or not embedded:
                raise HTTPException(409, "Original extraction or embedding artifact is unavailable")
            canonical_id = "entity:" + fingerprint([record["id"], mention_id])
            lease.execute("INSERT INTO ingestion_entities(id,label,entity_type,description,aliases,embedding,embedding_model,created_by_job,source_quote) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (canonical_id, entity["name"], entity["entity_type"], entity["description"], Jsonb([entity["name"]]), Jsonb(embedded["vector"]), record["configuration"]["embeddingModel"], record["id"], entity["quote"]))
            lease.execute("UPDATE ingestion_resolution_decisions SET reverted=true,canonical_id=%s WHERE id=%s", (canonical_id, decision_id))
            lease.execute("DELETE FROM ingestion_artifacts WHERE job_id=%s AND stage='publish'", (record["id"],))
            lease.execute("UPDATE ingestion_jobs SET status='queued',queued_through='publish',error=NULL,updated_at=now() WHERE id=%s", (record["id"],))
            lease.commit()
        finally:
            lease.rollback()
            if source_acquired:
                lease.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (source_key,))
            lease.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (record["id"],))
    return {"decisionId": decision_id, "reverted": True, "jobId": record["id"], "status": "queued"}


@router.get("/documents")
def documents(limit: int = Query(24, ge=1, le=100), offset: int = Query(0, ge=0)):
    with connection() as conn:
        rows = conn.execute("SELECT * FROM (SELECT DISTINCT ON (j.source_id) j.source_id AS id,s.filename,j.status,j.id AS job_id,j.updated_at,COALESCE(a.payload->'metadata'->>'title',s.filename) AS title,s.source_url AS \"sourceUrl\",COALESCE(jsonb_array_length(c.payload->'chunks'),0) AS \"chunkCount\" FROM ingestion_jobs j JOIN ingestion_sources s ON s.id=j.source_id JOIN ingestion_artifacts a ON a.job_id=j.id AND a.stage='normalize' LEFT JOIN ingestion_artifacts c ON c.job_id=j.id AND c.stage='chunk' ORDER BY j.source_id,j.created_at DESC) d ORDER BY updated_at DESC LIMIT %s OFFSET %s", (limit, offset)).fetchall()
        total = conn.execute("SELECT count(DISTINCT source_id) AS count FROM ingestion_jobs j WHERE EXISTS(SELECT 1 FROM ingestion_artifacts a WHERE a.job_id=j.id AND a.stage='normalize')").fetchone()["count"]
    return {"documents": serialize(rows), "total": total, "limit": limit, "offset": offset}


def latest_document_job(source_id):
    with connection() as conn:
        row = conn.execute("SELECT j.id FROM ingestion_jobs j WHERE j.source_id=%s AND EXISTS(SELECT 1 FROM ingestion_artifacts a WHERE a.job_id=j.id AND a.stage='normalize') ORDER BY j.created_at DESC LIMIT 1", (source_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Source not found")
    return pipeline.job_row(row["id"])


@router.get("/documents/{source_id}")
def document(source_id: str):
    record = latest_document_job(source_id)
    return document_for_job(record)


@router.get("/jobs/{job_id}/document")
def job_document(job_id: str):
    try:
        return document_for_job(pipeline.job_row(job_id))
    except KeyError:
        raise HTTPException(404, "Source job not found")


@router.get("/jobs/{job_id}/original")
def job_original(job_id: str):
    try:
        record = pipeline.job_row(job_id)
    except KeyError:
        raise HTTPException(404, "Source job not found")
    return FileResponse(record["original_path"], filename=record["filename"])


def document_for_job(record):
    source_id = record["source_id"]
    normalized = pipeline.artifact(record["id"], "normalize")
    if not normalized:
        raise HTTPException(409, "Source text is not parsed yet")
    chunks = pipeline.artifact(record["id"], "chunk") or {"chunks": []}
    extraction = pipeline.artifact(record["id"], "extract") or {}
    processing_warnings = [*normalized["metadata"].get("warnings", []), *[warning["message"] for warning in extraction.get("warnings", [])]]
    title = normalized["metadata"].get("title", record["filename"])
    source_url = normalized["metadata"].get("sourceUrl") or record["source_url"]
    sections = sections_for(normalized, record)
    enriched_chunks = []
    for chunk in chunks["chunks"]:
        primary, related = chunk_sections(chunk, sections)
        enriched_chunks.append({**chunk, "documentId": source_id, "sectionId": primary["id"], "sectionIds": [section["id"] for section in related], "sectionTitle": primary["title"], "sourceUrl": source_url, "locationKind": "source"})
    return {**normalized["metadata"], "id": source_id, "title": title, "processingWarnings": processing_warnings, "extractionQuality": extraction.get("quality"), "filename": record["filename"], "text": normalized["text"], "textLength": len(normalized["text"]), "chunks": enriched_chunks, "sections": sections, "entities": [], "offsetUnit": "unicode_codepoint", "textNormalization": normalized["normalization"], "extractionBoundary": "Inspect the ingestion job for extraction/validation readiness; parsed text does not imply indexed semantic assertions.", "blocks": normalized["blocks"], "metadata": normalized["metadata"], "status": record["status"], "jobId": record["id"], "revision": record["revision"], "processingVersion": record["processing_version"], "sourceUrl": source_url, "capabilities": {"original": True, "parsedText": True, "chunks": bool(chunks["chunks"]), "indexed": record["status"] == "complete"}}


@router.get("/documents/{source_id}/download")
def download(source_id: str):
    record = latest_document_job(source_id)
    return FileResponse(record["original_path"], filename=record["filename"])
