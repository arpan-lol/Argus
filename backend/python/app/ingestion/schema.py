DDL = """
CREATE TABLE IF NOT EXISTS ingestion_sources (
 id text PRIMARY KEY, filename text NOT NULL, original_path text NOT NULL,
 source_url text, media_type text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ingestion_jobs (
 id text PRIMARY KEY, source_id text NOT NULL REFERENCES ingestion_sources(id),
 revision text NOT NULL, processing_version text NOT NULL, configuration jsonb NOT NULL, original_path text NOT NULL,
 status text NOT NULL DEFAULT 'registered', current_stage text, error text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(source_id, revision, processing_version)
);
CREATE TABLE IF NOT EXISTS ingestion_attempts (
 id bigserial PRIMARY KEY, job_id text NOT NULL REFERENCES ingestion_jobs(id),
 stage text NOT NULL, attempt integer NOT NULL, status text NOT NULL,
 started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
 duration_ms double precision, error text, metadata jsonb NOT NULL DEFAULT '{}',
 UNIQUE(job_id, stage, attempt)
);
CREATE TABLE IF NOT EXISTS ingestion_artifacts (
 job_id text NOT NULL REFERENCES ingestion_jobs(id), stage text NOT NULL,
 payload jsonb NOT NULL, digest text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(job_id,stage)
);
CREATE TABLE IF NOT EXISTS ingestion_items (
 job_id text NOT NULL REFERENCES ingestion_jobs(id), stage text NOT NULL,
 item_id text NOT NULL, payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(job_id,stage,item_id)
);
CREATE TABLE IF NOT EXISTS ingestion_entities (
 id text PRIMARY KEY, label text NOT NULL, entity_type text NOT NULL,
 description text NOT NULL DEFAULT '', aliases jsonb NOT NULL DEFAULT '[]',
 embedding jsonb, embedding_model text NOT NULL, created_by_job text NOT NULL REFERENCES ingestion_jobs(id),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ingestion_entity_lookup ON ingestion_entities(lower(label),entity_type);
CREATE TABLE IF NOT EXISTS ingestion_resolution_decisions (
 id text PRIMARY KEY, job_id text NOT NULL REFERENCES ingestion_jobs(id),
 mention_id text NOT NULL, candidate_id text, canonical_id text NOT NULL,
 decision text NOT NULL, rationale text NOT NULL, votes jsonb NOT NULL,
 reverted boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ingestion_publications (
 job_id text PRIMARY KEY REFERENCES ingestion_jobs(id), source_id text NOT NULL,
 published_at timestamptz NOT NULL DEFAULT now(), active boolean NOT NULL DEFAULT true,
 counts jsonb NOT NULL
);
ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS original_path text;
ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS queued_through text;
ALTER TABLE ingestion_jobs ALTER COLUMN status SET DEFAULT 'registered';
UPDATE ingestion_jobs SET status='registered' WHERE status='queued' AND queued_through IS NULL;
CREATE INDEX IF NOT EXISTS ingestion_jobs_queued ON ingestion_jobs(created_at,id) WHERE status='queued' AND queued_through IS NOT NULL;
ALTER TABLE ingestion_entities ADD COLUMN IF NOT EXISTS embedding_model text;
ALTER TABLE ingestion_entities ADD COLUMN IF NOT EXISTS source_quote text;
CREATE TABLE IF NOT EXISTS ingestion_provider_limits (
 rate_key text PRIMARY KEY, next_at timestamptz NOT NULL
);
"""


def ensure_schema(conn):
    conn.execute(DDL)
