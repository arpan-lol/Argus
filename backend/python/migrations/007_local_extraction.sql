ALTER TABLE projects ADD COLUMN IF NOT EXISTS categories jsonb NOT NULL DEFAULT '["general_documents"]';
ALTER TABLE ingestion_profiles ADD COLUMN IF NOT EXISTS tokens_reserved bigint NOT NULL DEFAULT 0;
ALTER TABLE ingestion_profiles ADD COLUMN IF NOT EXISTS exploration_started_at timestamptz;
CREATE TABLE IF NOT EXISTS ingestion_profile_calls (
 profile_id text NOT NULL REFERENCES ingestion_profiles(id), sequence integer NOT NULL,
 reserved_tokens integer NOT NULL, status text NOT NULL, payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(profile_id,sequence)
);
