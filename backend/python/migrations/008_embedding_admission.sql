CREATE TABLE IF NOT EXISTS ingestion_embedding_reservations (
 id bigserial PRIMARY KEY, rate_key text NOT NULL, tokens integer NOT NULL,
 admitted_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS ingestion_embedding_reservations_window ON ingestion_embedding_reservations(rate_key,admitted_at);
