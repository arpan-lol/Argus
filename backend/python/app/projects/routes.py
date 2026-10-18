import asyncio
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.datastructures import UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.database import connection
from app.ingestion.config import processing_config
from app.ingestion.pipeline import IngestionPipeline, STAGES, serialize
from app.ingestion.profiles import create_profile
from .events import emit
from .scope import get_project, project_scope


router = APIRouter(prefix='/projects', tags=['projects'])
scoped = APIRouter(prefix='/{project_id}', dependencies=[Depends(project_scope)])
pipeline = IngestionPipeline()


class NewProject(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=12000)

    @field_validator('name')
    @classmethod
    def name_present(cls, value):
        if not value.strip():
            raise ValueError('Enter a project name')
        return value.strip()

    @field_validator('description')
    @classmethod
    def description_text(cls, value):
        return value.strip()


class Description(BaseModel):
    model_config = ConfigDict(extra='forbid')
    description: str = Field(min_length=1, max_length=12000)


def summary(row):
    return serialize({key: row[key] for key in ('id', 'name', 'description', 'created_at', 'updated_at', 'entity_types', 'relationship_types')})


@router.get('')
def projects():
    with connection() as conn:
        rows = conn.execute("SELECT p.*,(SELECT count(*) FROM ingestion_sources s WHERE s.project_id=p.id) AS files,(SELECT count(*) FROM ingestion_jobs j JOIN ingestion_publications pub ON pub.job_id=j.id WHERE j.project_id=p.id AND pub.active) AS published FROM projects p ORDER BY p.created_at,p.id").fetchall()
    return {'projects': [{**summary(row), 'files': row['files'], 'published': row['published']} for row in rows]}


@router.post('', status_code=201)
def new_project(body: NewProject):
    project_id = str(uuid.uuid4())
    with connection() as conn:
        row = conn.execute('INSERT INTO projects(id,name,description) VALUES(%s,%s,%s) RETURNING *', (project_id, body.name, body.description)).fetchone()
    return summary(row)


@scoped.get('')
def project(project_id: str):
    with connection() as conn:
        latest = conn.execute('SELECT coalesce(max(sequence),0) AS sequence FROM project_events WHERE project_id=%s', (project_id,)).fetchone()['sequence']
    return {**summary(get_project(project_id)), 'lastEventSequence': latest}


@scoped.get('/metrics')
def metrics(project_id: str):
    with connection() as conn:
        receipts = conn.execute("SELECT i.payload FROM ingestion_items i JOIN ingestion_jobs j ON j.id=i.job_id WHERE j.project_id=%s AND i.stage='provider_call'", (project_id,)).fetchall()
    totals = {'inputTokens': 0, 'outputTokens': 0, 'embeddingTokens': 0, 'llmCalls': 0, 'embeddingCalls': 0, 'failedCalls': 0, 'durationMs': 0, 'usageMissingCalls': 0}
    for row in receipts:
        value = row['payload']
        usage = value.get('usage') or {}
        embedding = value.get('kind') in ('embedding', 'query_embedding')
        totals['embeddingCalls' if embedding else 'llmCalls'] += 1
        totals['failedCalls'] += int(value.get('status') == 'failed')
        totals['usageMissingCalls'] += int(not usage)
        totals['durationMs'] += value.get('durationMs') or 0
        tokens = usage.get('input_tokens', usage.get('prompt_tokens', 0)) or 0
        totals['embeddingTokens' if embedding else 'inputTokens'] += tokens
        if not embedding:
            totals['outputTokens'] += usage.get('output_tokens', usage.get('completion_tokens', 0)) or 0
    return {'actualReportedUsage': totals, 'costUsd': None, 'duplicateMode': 'custom' if processing_config()['customDuplicateChecking'] else 'sdk_basic', 'execution': {'queue': 'one job per file', 'workers': int(os.getenv('ARGUS_INGESTION_WORKERS', '1')), 'parallelStages': ['embed', 'extract'], 'chunkEmbeddingBatchSize': 1}, 'estimate': {'basicDuplicateLlmCalls': 0, 'customDuplicateLlmCalls': '2 × ceil(candidate pairs / batch size), plus retries', 'extractionLlmCalls': 'One per uncached chunk normally; at most two extraction attempts per chunk'}}


@scoped.put('/description')
def describe(project_id: str, body: Description):
    description = body.description.strip()
    if not description:
        raise HTTPException(400, 'Describe the data in this workspace')
    with connection() as conn:
        row = conn.execute('SELECT * FROM projects WHERE id=%s FOR UPDATE', (project_id,)).fetchone()
        if row['description'] and row['description'] != description:
            raise HTTPException(409, 'This workspace already has a saved description')
        row = conn.execute('UPDATE projects SET description=%s,updated_at=now() WHERE id=%s RETURNING *', (description, project_id)).fetchone()
    return summary(row)


@scoped.post('/uploads', status_code=202)
async def upload_sources(project_id: str, request: Request):
    config = processing_config()
    form = await request.form(max_files=config['maxUploadFiles'])
    files = form.getlist('files')
    through = str(form.get('through', 'publish'))
    if through not in STAGES:
        await form.close()
        raise HTTPException(400, 'Unknown ingestion stage')
    if not files or any(not isinstance(file, UploadFile) for file in files):
        await form.close()
        raise HTTPException(400, 'Choose at least one source file')
    try:
        return await upload_project_files(project_id, files, through, config)
    finally:
        await form.close()


async def upload_project_files(project_id, files, through, config=None):
    config = config or processing_config()
    project = get_project(project_id)
    if not project['description']:
        raise HTTPException(409, 'Describe this workspace before uploading files')
    staged = []
    temporary = []
    try:
        for file in files:
            filename = Path(file.filename or 'source.txt').name
            with tempfile.NamedTemporaryFile(delete=False, suffix='-' + filename) as target:
                path = Path(target.name)
                temporary.append(path)
                size = 0
                digest = hashlib.sha256()
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > config['maxUploadBytes']:
                        raise HTTPException(413, filename + ' exceeds the configured upload limit')
                    digest.update(chunk)
                    target.write(chunk)
            source_id = 'source:' + hashlib.sha256((project_id + ':' + digest.hexdigest()).encode()).hexdigest()
            staged.append((path, filename, source_id, pipeline.describe_source(path, source_id=source_id, filename=filename)))
        if not staged:
            raise HTTPException(400, 'Choose at least one source file')
        with connection() as lease:
            lease.execute('SELECT pg_advisory_lock(hashtextextended(%s,0))', ('project-profile:' + project_id,))
            lease.commit()
            try:
                project = get_project(project_id)
                profile_id = project['profile_id']
                if not profile_id:
                    profile_id = create_profile(project['description'], [source for _, _, _, source in staged], config)['id']
                    with connection() as conn:
                        conn.execute('UPDATE projects SET profile_id=%s,updated_at=now() WHERE id=%s', (profile_id, project_id))
                jobs = [pipeline.register_file(path, source_id=source_id, filename=filename, profile_id=profile_id) for path, filename, source_id, _ in staged]
            finally:
                lease.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))', ('project-profile:' + project_id,))
        for job in jobs:
            if job['status'] not in ('complete', 'running', 'queued'):
                pipeline.enqueue(job['id'], through)
            emit(project_id, 'file_registered', {'filename': job['filename']}, job['id'])
        return {'jobs': [pipeline.get_job(job['id']) for job in jobs]}
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)


@scoped.get('/events')
async def events(project_id: str, request: Request, after: int = Query(0, ge=0)):
    last = request.headers.get('last-event-id', '')
    cursor = max(after, int(last) if last.isdigit() else 0)
    async def stream():
        nonlocal cursor
        ticks = 0
        while not await request.is_disconnected():
            with connection() as conn:
                rows = conn.execute('SELECT sequence,job_id,kind,payload,created_at FROM project_events WHERE project_id=%s AND sequence>%s ORDER BY sequence LIMIT 200', (project_id, cursor)).fetchall()
            for row in rows:
                cursor = row['sequence']
                payload = serialize({'sequence': cursor, 'jobId': row['job_id'], 'type': row['kind'], 'at': row['created_at'], **row['payload']})
                yield 'id: ' + str(cursor) + '\ndata: ' + json.dumps(payload, ensure_ascii=False) + '\n\n'
            if not rows:
                ticks += 1
                if ticks % 15 == 0:
                    yield ': heartbeat\n\n'
                await asyncio.sleep(1)
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


router.include_router(scoped)
