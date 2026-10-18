from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import connection
from app.projects.scope import current_project, project_scope
from ..config import processing_config
from .storage import ensure


router = APIRouter(prefix='/projects/{project_id}/codebase', tags=['codebase ingestion'], dependencies=[Depends(project_scope)])


@router.get('')
def overview(limit: int = Query(20, ge=1, le=100)):
    ensure()
    project = current_project.get()
    config = processing_config(project)
    with connection() as conn:
        rows = conn.execute("SELECT id,status,created_at,updated_at,jsonb_array_length(manifest) AS files,payload->>'quality' AS quality,payload->>'stopReason' AS stop_reason,payload->'coverage' AS coverage FROM ingestion_codebase_runs WHERE project_id=%s ORDER BY updated_at DESC LIMIT %s", (project, limit)).fetchall()
        usage = conn.execute('SELECT coalesce(sum(reserved_tokens),0) AS reserved_tokens,count(*) AS attempted_calls FROM ingestion_codebase_calls WHERE project_id=%s', (project,)).fetchone()
    return {'runs': rows, 'budget': {**usage, 'limitTokens': config['codeAgentTokenBudget'], 'scope': 'Persistent workspace code-builder reservations across snapshots and failures; separate from document label discovery', 'meaning': 'Conservative token reservations, not billed tokens or USD'}, 'modelRole': 'LLM2', 'tools': ['list_files', 'read_sources', 'search_sources', 'find_entities', 'write_graph', 'finish'], 'source': 'https://github.com/arpan-lol/falkor/tree/ingestion-main/backend/python/app/ingestion/codebase', 'upstream': 'https://github.com/samyakkkk/flow', 'license': 'AGPL-3.0-only for the Flow-adapted codebase builder'}


@router.get('/runs/{run_id}')
def details(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    ensure()
    with connection() as conn:
        run = conn.execute('SELECT * FROM ingestion_codebase_runs WHERE project_id=%s AND id=%s', (current_project.get(), run_id)).fetchone()
        if not run:
            raise HTTPException(404, 'Codebase ingestion run not found')
        calls = conn.execute('SELECT id,status,reserved_tokens,payload,created_at FROM ingestion_codebase_calls WHERE project_id=%s AND run_id=%s ORDER BY id', (current_project.get(), run_id)).fetchall()
    payload = run.pop('payload')
    claims = payload.get('claims', [])
    page = claims[offset:offset + limit]
    keys = {claim['entity']['key'] for claim in page if claim['kind'] == 'entity'}
    keys.update(key for claim in page if claim['kind'] == 'relationship' for key in (claim['relationship']['subject'], claim['relationship']['object']))
    return {**run, 'summary': {key: value for key, value in payload.items() if key not in {'entities', 'claims', 'seen'}}, 'claims': page, 'entities': {key: value for key, value in payload.get('entities', {}).items() if key in keys}, 'totalClaims': len(claims), 'offset': offset, 'limit': limit, 'calls': calls}
