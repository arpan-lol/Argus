CREATE TABLE chat_runs (
 id uuid PRIMARY KEY,
 request jsonb NOT NULL,
 configuration jsonb NOT NULL,
 status text NOT NULL DEFAULT 'queued',
 budget jsonb NOT NULL DEFAULT '{}',
 result jsonb,
 error text,
 runtime_ms double precision NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE chat_events (
 sequence bigserial PRIMARY KEY,
 run_id uuid NOT NULL REFERENCES chat_runs(id),
 kind text NOT NULL,
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX chat_events_run ON chat_events(run_id,sequence);
CREATE TABLE chat_tool_results (
 run_id uuid NOT NULL REFERENCES chat_runs(id),
 call_id text NOT NULL,
 payload jsonb NOT NULL,
 PRIMARY KEY(run_id,call_id)
);
