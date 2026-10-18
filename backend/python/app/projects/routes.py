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
from psycopg.types.json import Jsonb

from app.database import connection
from app.ingestion.config import processing_config
from app.ingestion.pipeline import IngestionPipeline, STAGES, serialize
from .events import emit
from .scope import get_project, project_scope
from app.ingestion.categories import category_catalog, validate_categories


router = APIRouter(prefix='/projects', tags=['projects'])
scoped = APIRouter(prefix='/{project_id}', dependencies=[Depends(project_scope)])
pipeline = IngestionPipeline()


class NewProject(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=12000)
    categories: list[str] = Field(default_factory=lambda: ['general_documents'], max_length=8)

    @field_validator('categories')
    @classmethod
    def selected_categories(cls, value):
        return validate_categories(value)

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
    categories: list[str] | None = Field(default=None, max_length=8)


def summary(row):
    return {**serialize({key: row[key] for key in ('id', 'name', 'description', 'categories', 'created_at', 'updated_at', 'entity_types', 'relationship_types')}), 'configurationLocked': bool(row.get('profile_id'))}


@router.get('/categories')
def categories():
    return {'categories': [{'id': item['id'], 'name': item['name'], 'description': item['description']} for item in category_catalog()]}


@router.get('')
def projects():
    with connection() as conn:
        rows = conn.execute("SELECT p.*,(SELECT count(*) FROM ingestion_sources s WHERE s.project_id=p.id) AS files,(SELECT count(*) FROM ingestion_jobs j JOIN ingestion_publications pub ON pub.job_id=j.id WHERE j.project_id=p.id AND pub.active) AS published FROM projects p ORDER BY p.created_at,p.id").fetchall()
    return {'projects': [{**summary(row), 'files': row['files'], 'published': row['published']} for row in rows]}


@router.post('', status_code=201)
def new_project(body: NewProject):
    project_id = str(uuid.uuid4())
    with connection() as conn:
        row = conn.execute('INSERT INTO projects(id,name,description,categories) VALUES(%s,%s,%s,%s) RETURNING *', (project_id, body.name, body.description, Jsonb(body.categories))).fetchone()
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
    return {'actualReportedUsage': totals, 'costUsd': None, 'duplicateMode': 'sdk_basic', 'execution': {'queue': 'one job per file', 'workers': int(os.getenv('ARGUS_INGESTION_WORKERS', '1')), 'parallelStages': ['embed', 'mentions', 'configure'], 'chunkEmbeddingBatchSize': 64, 'embeddingTokensPerMinute': processing_config()['embeddingTokensPerMinute']}, 'estimate': {'duplicateLlmCalls': 0, 'extractionLlmCalls': 0, 'workspaceDiscovery': 'Batched random samples; no calls start after 30 seconds; each dispatched response may finish; shared workspace token budget'}}


@scoped.put('/description')
def describe(project_id: str, body: Description):
    description = body.description.strip()
    if not description:
        raise HTTPException(400, 'Describe the data in this workspace')
    with connection() as conn:
        row = conn.execute('SELECT * FROM projects WHERE id=%s FOR UPDATE', (project_id,)).fetchone()
        if row['description'] and row['description'] != description:
            raise HTTPException(409, 'This workspace already has a saved description')
        selected = row.get('categories') or ['general_documents']
        if body.categories is not None:
            try:
                selected = validate_categories(body.categories)
            except ValueError as error:
                raise HTTPException(400, str(error))
            if selected != row.get('categories') and conn.execute('SELECT 1 FROM ingestion_jobs WHERE project_id=%s LIMIT 1', (project_id,)).fetchone():
                raise HTTPException(409, 'Categories are saved for this workspace; create another workspace for a different category setup')
        row = conn.execute('UPDATE projects SET description=%s,categories=%s,updated_at=now() WHERE id=%s RETURNING *', (description, Jsonb(selected), project_id)).fetchone()
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
    if project.get('profile_id'):
        from app.ingestion.profiles import get_profile, profile_compatible
        if not profile_compatible(get_profile(project['profile_id']), config):
            raise HTTPException(409, 'This workspace uses earlier extraction settings. Create a new workspace to build a fresh graph with local extraction.')
    staged = []
    temporary = []
    archives = []
    skipped = []
    seen = {}
    try:
        for file in files:
            from app.ingestion.archives import source_name, expand_archive, skip_reason, content_skip_reason
            try:
                filename = source_name(file.filename or 'source.txt')
            except ValueError as error:
                raise HTTPException(400, str(error))
            reason = skip_reason(filename) if not filename.lower().endswith('.zip') else None
            if reason:
                skipped.append({'filename': filename, 'reason': reason})
                continue
            with tempfile.NamedTemporaryFile(delete=False, suffix='-' + Path(filename).name) as target:
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
            members = [(path, filename)]
            if filename.lower().endswith('.zip'):
                pipeline.describe_source(path, source_id='archive:' + digest.hexdigest(), filename=filename)
                try:
                    members, report = expand_archive(path, filename, config, temporary)
                except (ValueError, __import__('zipfile').BadZipFile) as error:
                    raise HTTPException(400, str(error))
                archives.append(report)
                skipped.extend(report['skipped'])
            for member, relative in members:
                reason = content_skip_reason(member, relative)
                if reason:
                    skipped.append({'filename': relative, 'reason': reason})
                    continue
                revision = hashlib.sha256(member.read_bytes()).hexdigest()
                if relative in seen:
                    if seen[relative] != revision:
                        raise HTTPException(400, 'Different files share the path ' + relative + '. Upload their containing folder to retain distinct paths.')
                    skipped.append({'filename': relative, 'reason': 'duplicate source in this upload'})
                    continue
                seen[relative] = revision
                source_id = 'source:' + hashlib.sha256((project_id + ':' + relative).encode()).hexdigest()
                staged.append((member, relative, source_id, pipeline.describe_source(member, source_id=source_id, filename=relative)))
                if len(staged) > config['maxUploadFiles']:
                    raise HTTPException(413, 'Expanded files exceed the configured file count')
        if not staged:
            raise HTTPException(400, 'No supported source files were found. Add source code, Markdown, JATS/XML, PDF, Office documents, JSON or text files.')
        from app.ingestion.profiles import create_profile
        with connection() as conn:
            saved = conn.execute('SELECT * FROM projects WHERE id=%s FOR UPDATE', (project_id,)).fetchone()
            profile_id = saved['profile_id']
            if not profile_id:
                profile_id = create_profile(project['description'], [source for _, _, _, source in staged], config)['id']
                conn.execute('UPDATE projects SET profile_id=%s WHERE id=%s', (profile_id, project_id))
        jobs = [pipeline.register_file(path, source_id=source_id, filename=filename, profile_id=profile_id) for path, filename, source_id, _ in staged]
        for job in jobs:
            if job['status'] not in ('complete', 'running', 'queued'):
                pipeline.enqueue(job['id'], through)
            emit(project_id, 'file_registered', {'filename': job['filename']}, job['id'])
        return {'jobs': [pipeline.get_job(job['id']) for job in jobs], 'archives': archives, 'skippedFiles': skipped}
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
