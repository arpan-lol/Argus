# Argus

An inspectable source workspace extended from [Cosmic Engine](https://github.com/arpan-lol/cosmic-engine). Python and LangGraph run ingestion, Postgres stores processing state and BM25 indexes, and FalkorDB stores the semantic graph and vectors. The Next.js dashboard retains central chat and a resizable Source Explorer.

## Run locally

Requirements: Python 3.12+ (this pass ran on 3.13), Node.js 22.13+, npm, and Docker.

```powershell
docker compose up -d
npm run setup
Copy-Item backend/python/.env.example backend/python/.env
npm run dev
```

Configure Google, OpenAI, or Azure credentials in the ignored Python environment file before model processing. `npm run setup` creates the local Python virtual environment when missing. The first local GLiNER run downloads model weights. All services bind to localhost; authentication remains outside this implementation pass.

- Dashboard: http://localhost:3001/dashboard
- Python API and OpenAPI: http://localhost:4000/docs
- FalkorDB Browser: http://localhost:3000
- Postgres with pg_search: localhost:5434, database/user `argus`, development password `argus_local`.
- FalkorDB Browser connection: localhost:6379, user `default`, empty password, TLS off.

`npm run build` compiles Python and builds the frontend. `backend/src/` is retained as an inactive TypeScript migration reference; standard startup uses Python. `dev:legacy` is explicitly historical.

## Ingestion

Upload a file through Source Explorer or process an existing source:

```powershell
npm run ingest -- path/to/source.pdf
npm run ingest -- --glob "data/raw/*.xml.gz" --through chunk
npm run ingest -- --resume job:your-job-identifier
```

Stages: register → parse → normalize → chunk → embed → extract → resolve → validate → publish.

Each file has immutable originals, a content revision, a processing configuration fingerprint, stage attempts, per-item artifacts, timings, model receipts, and Postgres LangGraph checkpoints. A bounded worker queue processes explicitly scheduled uploads and retries. Registered inventory does not automatically trigger model calls. `--through chunk` stops before provider calls; `--register-only` only records the original and job.

JATS parsing retains ordered text from nested body structures, front matter, abstracts, captions, tables and references, with explicit body coverage accounting and warnings when body text is missing. Existing parsed sources require a new processing job to use this parser version.

The parser supports JATS/XML and gzip, text/Markdown, HTML, text-bearing PDF, DOCX, CSV/TSV, XLSX, and JSON. It retains source blocks and logical/page/cell locations. Scanned PDFs require OCR, which is not enabled. Legacy Office binaries and presentations are not parsed. Binary formats outside the supported parsers fail explicitly.

Chunking adapts the published FalkorDB SDK v1.4.0 sentence/token algorithm: 512 tokens with two-sentence overlap. Source whitespace and offsets are retained. Oversized individual sentences remain whole and are labeled. The upstream Apache-2.0 license and modification notice are included under backend/python/licenses/.

GLiNER supplies windowed candidate mentions. The configured LLM verifies entities and relationships against exact source quotes. An explicitly configured type vocabulary is optional; otherwise a recorded LLM step infers types from the document. Entity resolution uses FalkorDB vector candidates, exact-name candidates, two order-reversed batched judgments, and constraints against contradictory merges. Similarity alone never merges entities. New processing profiles allow two extraction attempts with recorded validation feedback. If both fail, exact GLiNER spans remain explicitly labeled as unverified fallback mentions with no relationships; duplicate checks are deferred. Missing deployment or access configuration still stops the job. The processed file reader displays fallback and source-coverage warnings. Older saved jobs retain their previous extraction policy.

Assertions preserve their source quotes, offsets, polarity, and conditions. Chunk, entity, and assertion vectors are indexed in FalkorDB. Semantic graphs use an embedding-space namespace such as `argus_sources_v2_<hash>`; model spaces are not mixed. Source replacements retire older graph records logically. Postgres and FalkorDB are separate transaction domains; interrupted publication requires an idempotent retry.

## Model deployment configuration

Use the deployment variables in `backend/python/.env.example`:

| Variables | Role |
| --- | --- |
| `LLM1_DEPLOYMENT_NAME`, `LLM1_DEPLOYMENT_URL`, `LLM1_DEPLOYMENT_KEY` | Chat; default deployment `gpt-5` |
| `LLM2_DEPLOYMENT_NAME`, `LLM2_DEPLOYMENT_URL`, `LLM2_DEPLOYMENT_KEY` | Source extraction and entity resolution judgments; default deployment `gpt-4.1-mini` |
| `AZURE_API_KEY` | Shared fallback when a role-specific Azure key is absent |
| `AZURE_OPENAI_ENDPOINT` | Fallback embedding base URL when an embedding endpoint is absent |
| `EMBEDDING_MODEL_NAME`, `EMBEDDING_MODEL_ENDPOINT`, `EMBEDDING_MODEL_KEY` | Document and query embeddings; default model `text-embedding-3-large`, 3,072 dimensions |

LLM URLs can be the complete Responses endpoint, such as `https://YOUR-RESOURCE.services.ai.azure.com/openai/v1/responses`. The application splits the API protocol from the base URL. A bare embedding resource endpoint gains `/openai/v1`; `/openai/v1/embeddings` is also accepted and normalized. An explicit `/models` embedding base uses the Azure inference API version. URLs must use HTTPS without credentials or query strings. Role-specific keys are used for their corresponding requests and never stored in processing profiles, graphs, or receipts. Responses requests use `store=false` and schema-validated output.

`LLM1_*` takes precedence over legacy chat settings; `LLM2_*` takes precedence over legacy extraction and resolution settings. GPT-5 cannot be selected as LLM2 in new profiles. When LLM2 is omitted, resolution uses LLM1. Existing Google/OpenAI/Azure profiles and older `ARGUS_*` model settings remain supported. When `EMBEDDING_MODEL_NAME` is present, new profiles default to Azure embeddings unless `ARGUS_MODEL_PROVIDER` explicitly selects another provider. `ARGUS_EMBEDDING_DIMENSIONS` can override the model's default dimensions.

Embedding model, dimensions, provider, and normalized Azure embedding endpoint define the new vector namespace and query cache. Existing vectors are retained; switching to a new namespace requires reprocessing sources before they become searchable there. Model and endpoint changes produce new processing versions rather than rewriting saved jobs. Provider errors do not silently select another model. Ingestion uses configured timeouts, rate limits and bounded retries.

## Legacy corpus and current boundaries

The existing catalog contains 6,000 documents, 133,562 sections, and 252,654 chunks imported into Postgres. Existing SQLite databases are read only by the one-time migration utility:

```powershell
npm run migrate:legacy
```

The dashboard labels the earlier dictionary-based map and catalog **Legacy graph** and **Legacy corpus**. Newly processed sources appear separately in Files with their real stage status and readers. Parsing is not semantic readiness, and imported dictionary links are not newly extracted assertions. Dashboard chat uses a bounded LangGraph investigation over published semantic sources. The legacy catalog stays separate; new semantic-map integration remains later work.

## Published retrieval tools

`GET /api/retrieval/tools` lists six typed tools: `search_sources`, `find_entities`, `read_chunks`, `inspect_assertions`, `expand_connections`, and `find_paths`. Invoke one with `POST /api/retrieval/tools/{name}` and body `{"arguments": {...}}`. The agent receives these contracts rather than schema access or arbitrary Cypher. `app.retrieval.bindings.get_tools()` returns LangChain StructuredTools for typed retrieval integrations. The dashboard investigation uses these same bounded contracts; no MCP transport is enabled.

`POST /api/retrieval/search` accepts `{"query":"your question","mode":"hybrid","limit":10}`. Modes are lexical, vector and hybrid. Search combines published Postgres BM25 with native FalkorDB chunk ANN using reciprocal-rank fusion, constant 60. Query embeddings use explicit retrieval-query semantics, matching the publication's provider/model/dimensions, with a persistent profile-keyed cache. Hybrid channel failure is explicitly reported as partial, never silently disguised as hybrid success.

Tools search only active semantic publications in the configured embedding space. They validate source revision and processing version, preserve exact quotation offsets, then recheck publication state before returning. Results retain assertion polarity, conditions, citations, timings, budget receipts and truncation reasons. Shared mentions are navigation rather than scientific assertions; composed paths do not establish a new scientific conclusion.

Traversal uses bounded BFS over source-supported assertion adjacency: up to three hops, 20 assertions per expanded entity, 40 discovered entities and 100 returned assertions. The execution session admits up to 64 database operations with 1.5-second query timeouts and a soft 30-second elapsed budget; in-flight calls and final consistency/persistence can extend beyond it. Responses are capped at 64,000 characters. Snapshot scope is capped at 10,000 publications. ANN examines at most 240 indexed candidates before publication/document filtering and can underfill. Empty bounded results do not prove absence.

For the pinned FalkorDB runtime, native cosine vector scores are distances (lower is nearer), confirmed by an identical-vector read returning approximately zero. Current upstream examples conflict with this runtime behavior; the API labels the signal `cosine_distance` explicitly. Neither BM25, distance nor fusion scores are confidence probabilities.

Slice 4 was exercised on the one currently published semantic source, not the complete registered corpus. Its operation does not establish cross-document quality or corpus-scale performance. Tool runs are persisted in the existing runs API, independently of ingestion jobs.

The source map retains both Network and Trees layouts, stable positions, progressive viewport loading, citation navigation, and expanded modal viewing. The native FalkorDB Browser can inspect the new semantic graph immediately.

Downloaded corpus files, provider credentials, databases, model artifacts, and detailed local progress remain outside Git. The root docs/ folder is intentionally ignored. Read agents.md for working agreements.

## Conversational research

`POST /api/chat` returns NDJSON events for acceptance, model activity, real tool calls, usage, and the final cited report. Greetings receive a conversational answer without keyword searches. Research answers use the six published-source tools, validate citation revisions and quotations, and open the cited processing job in Files. The legacy map retains its own identifiers and scope.

Configure the `LLM1_*` deployment variables above to select the chat model. Legacy independent `ARGUS_CHAT_*` settings remain available when LLM1 is absent. Responses requests use `store=false`.

Postgres stores run events, tool receipts, budgets, and LangGraph checkpoints. `GET /api/chat/{runId}` reconnects to saved results; `POST /api/chat/{runId}/resume` retries an unfinished step. The browser retains at most 12 run IDs in session storage for reload recovery, and sends only two preceding turns as conversational context. New chat clears those browser references. There is no cross-conversation semantic memory.

Each run admits at most eight model calls and eight retrieval calls, with 10,000 estimated context tokens, 2,048 maximum output tokens per call, and 64,000 reserved tokens overall. Two concurrent workers are allowed. A 180-second admission deadline and individual model request timeouts bound execution; in-flight work can exceed the admission deadline. Token reservations are estimates; reported usage is displayed separately. The optional $0.25 reservation limit applies only when both `ARGUS_CHAT_INPUT_USD_PER_MILLION` and `ARGUS_CHAT_OUTPUT_USD_PER_MILLION` are configured with deployment prices. No dollar cost is invented when prices are absent. Budget environment overrides in `.env.example` may lower these limits.

Run recovery preserves previous budget reservations. Completed tool results replay from their receipts; a crash after a paid model call but before its checkpoint can cause that call to repeat on resume. Citation validation checks source identity and quotation offsets; it does not prove every generated interpretation. Available publication counts are shown in the chat and engine configuration.
