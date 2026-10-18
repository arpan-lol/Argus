from psycopg.types.json import Jsonb

from app.database import connection


def emit(project_id, kind, payload, job_id=None):
    if not project_id:
        return
    with connection() as conn:
        conn.execute('INSERT INTO project_events(project_id,job_id,kind,payload) VALUES(%s,%s,%s,%s)', (project_id, job_id, kind, Jsonb(payload)))


def job_event(job, kind, payload):
    emit(job['configuration'].get('projectId'), kind, payload, job['id'])
