CREATE TABLE retrieval_query_embeddings (
 id text PRIMARY KEY,
 profile jsonb NOT NULL,
 vector jsonb NOT NULL,
 receipt jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ingestion_publications_active_sources ON ingestion_publications(source_id,job_id) WHERE active;
