CREATE TABLE published_documents(id text PRIMARY KEY, title text NOT NULL, metadata jsonb NOT NULL, payload bytea NOT NULL, published_at timestamptz DEFAULT now());
CREATE TABLE published_sections(id text PRIMARY KEY, document_id text NOT NULL REFERENCES published_documents(id), title text NOT NULL, start_offset integer, end_offset integer, payload jsonb NOT NULL);
CREATE INDEX published_sections_document ON published_sections(document_id,start_offset);
CREATE TABLE published_chunks(id text PRIMARY KEY, document_id text NOT NULL REFERENCES published_documents(id), section_id text, start_offset integer, text text NOT NULL, document_title text NOT NULL, section_title text NOT NULL, payload jsonb NOT NULL);
CREATE INDEX published_chunks_document ON published_chunks(document_id,start_offset);
CREATE INDEX published_chunks_bm25 ON published_chunks USING bm25(id,text,document_title,section_title) WITH(key_field='id');
