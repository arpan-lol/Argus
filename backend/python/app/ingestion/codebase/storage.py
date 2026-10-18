import json

from psycopg.types.json import Jsonb

from app.database import connection


DDL = '''
CREATE TABLE IF NOT EXISTS ingestion_codebase_runs (
 id text PRIMARY KEY, project_id text NOT NULL, manifest jsonb NOT NULL,
 status text NOT NULL DEFAULT 'running', payload jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ingestion_codebase_calls (
 id bigserial PRIMARY KEY, project_id text NOT NULL, run_id text NOT NULL,
 reserved_tokens integer NOT NULL, status text NOT NULL DEFAULT 'reserved',
 payload jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ingestion_codebase_calls_project ON ingestion_codebase_calls(project_id);
CREATE TABLE IF NOT EXISTS ingestion_codebase_entities (
 project_id text NOT NULL, entity_key text NOT NULL, name text NOT NULL, entity_type text NOT NULL,
 payload jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(project_id,entity_key)
);
'''


def ensure():
    with connection() as conn:
        conn.execute(DDL)


def reserve(project, run, tokens, maximum):
    with connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('codebase-budget:' + project,))
        used = conn.execute('SELECT coalesce(sum(reserved_tokens),0) AS total FROM ingestion_codebase_calls WHERE project_id=%s', (project,)).fetchone()['total']
        if used + tokens > maximum:
            return None
        return conn.execute('INSERT INTO ingestion_codebase_calls(project_id,run_id,reserved_tokens) VALUES(%s,%s,%s) RETURNING id', (project, run, tokens)).fetchone()['id']


def finish_call(identifier, status, payload):
    with connection() as conn:
        conn.execute('UPDATE ingestion_codebase_calls SET status=%s,payload=%s WHERE id=%s', (status, Jsonb(payload), identifier))


def find_entities(project, query, limit=20):
    with connection() as conn:
        rows = conn.execute('SELECT payload FROM ingestion_codebase_entities WHERE project_id=%s AND (strpos(lower(name),lower(%s))>0 OR strpos(lower(entity_key),lower(%s))>0) ORDER BY entity_key LIMIT %s', (project, query, query, limit)).fetchall()
    return [row['payload'] for row in rows]


def save_entity(project, entity, conn):
    prior = conn.execute('SELECT payload FROM ingestion_codebase_entities WHERE project_id=%s AND entity_key=%s FOR UPDATE', (project, entity['key'])).fetchone()
    if prior:
        entity['name'] = prior['payload']['name']
        entity['entity_type'] = prior['payload']['entity_type']
    duplicate = conn.execute('SELECT entity_key FROM ingestion_codebase_entities WHERE project_id=%s AND name=%s AND entity_type=%s AND entity_key<>%s LIMIT 1', (project, entity['name'], entity['entity_type'], entity['key'])).fetchone()
    if duplicate:
        raise ValueError('Reuse existing matching entity key: ' + duplicate['entity_key'])
    conn.execute('INSERT INTO ingestion_codebase_entities(project_id,entity_key,name,entity_type,payload) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(project_id,entity_key) DO UPDATE SET payload=excluded.payload,updated_at=now()', (project, entity['key'], entity['name'], entity['entity_type'], Jsonb(entity)))


def save_run(run, payload, status='running'):
    with connection() as conn:
        conn.execute('UPDATE ingestion_codebase_runs SET payload=%s,status=%s,updated_at=now() WHERE id=%s', (Jsonb(json.loads(json.dumps(payload, default=str))), status, run))
