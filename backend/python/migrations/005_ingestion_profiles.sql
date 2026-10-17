CREATE TABLE ingestion_profiles (
 id text PRIMARY KEY,
 prompt text NOT NULL,
 source_manifest jsonb NOT NULL,
 model_configuration jsonb NOT NULL,
 settings jsonb,
 sampling jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 completed_at timestamptz
);
