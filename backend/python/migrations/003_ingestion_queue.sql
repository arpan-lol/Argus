ALTER TABLE IF EXISTS ingestion_jobs ADD COLUMN IF NOT EXISTS queued_through text;
