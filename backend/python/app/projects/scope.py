from contextvars import ContextVar

from fastapi import HTTPException, Request

from app.database import connection


current_project = ContextVar('argus_project', default=None)


def get_project(project_id):
    with connection() as conn:
        row = conn.execute('SELECT * FROM projects WHERE id=%s', (project_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Project not found')
    return row


async def project_scope(request: Request):
    project_id = request.path_params['project_id']
    get_project(project_id)
    token = current_project.set(project_id)
    try:
        yield project_id
    finally:
        current_project.reset(token)


def apply_project(config, project_id=None):
    project_id = project_id or current_project.get()
    if not project_id:
        return config
    project = get_project(project_id)
    return {**config, 'projectId': project_id, 'workspaceDescription': project['description'], 'categories': project.get('categories') or ['general_documents'], 'semanticGraph': 'argus_project_' + project_id.replace('-', '')}
