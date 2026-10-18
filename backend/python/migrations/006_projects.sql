CREATE TABLE IF NOT EXISTS projects (
 id text PRIMARY KEY, name text NOT NULL, description text NOT NULL DEFAULT '',
 profile_id text, entity_types jsonb NOT NULL DEFAULT '[]', relationship_types jsonb NOT NULL DEFAULT '[]',
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE ingestion_sources ADD COLUMN IF NOT EXISTS project_id text REFERENCES projects(id);
ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS project_id text REFERENCES projects(id);
CREATE INDEX IF NOT EXISTS ingestion_jobs_project ON ingestion_jobs(project_id,created_at);
CREATE INDEX IF NOT EXISTS ingestion_sources_project ON ingestion_sources(project_id);
CREATE TABLE IF NOT EXISTS project_events (
 sequence bigserial PRIMARY KEY, project_id text NOT NULL REFERENCES projects(id),
 job_id text, kind text NOT NULL, payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS project_events_stream ON project_events(project_id,sequence);
CREATE TABLE IF NOT EXISTS project_layouts (
 project_id text NOT NULL REFERENCES projects(id), mode text NOT NULL, node_id text NOT NULL,
 x double precision NOT NULL, y double precision NOT NULL, payload jsonb NOT NULL DEFAULT '{}',
 PRIMARY KEY(project_id,mode,node_id)
);
INSERT INTO projects(id,name) SELECT gen_random_uuid()::text,'Materials research' WHERE NOT EXISTS(SELECT 1 FROM projects);
