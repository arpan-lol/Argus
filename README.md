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

The parser supports JATS/XML and gzip, text/Markdown, HTML, text-bearing PDF, DOCX, CSV/TSV, XLSX, and JSON. It retains source blocks and logical/page/cell locations. Scanned PDFs require OCR, which is not enabled. Legacy Office binaries and presentations are not parsed. Binary formats outside the supported parsers fail explicitly.

Chunking adapts the published FalkorDB SDK v1.4.0 sentence/token algorithm: 512 tokens with two-sentence overlap. Source whitespace and offsets are retained. Oversized individual sentences remain whole and are labeled. The upstream Apache-2.0 license and modification notice are included under backend/python/licenses/.

GLiNER supplies windowed candidate mentions. The configured LLM verifies entities and relationships against exact source quotes. An explicitly configured type vocabulary is optional; otherwise a recorded LLM step infers types from the document. Entity resolution uses FalkorDB vector candidates, exact-name candidates, two order-reversed batched judgments, and constraints against contradictory merges. Similarity alone never merges entities. Invalid model output retries with recorded validation feedback; there is no entity-only fallback.

Assertions preserve their source quotes, offsets, polarity, and conditions. Chunk, entity, and assertion vectors are indexed in FalkorDB. Semantic graphs use an embedding-space namespace such as `argus_sources_v2_<hash>`; model spaces are not mixed. Source replacements retire older graph records logically. Postgres and FalkorDB are separate transaction domains; interrupted publication requires an idempotent retry.

## Azure LLM configuration

Extraction and identity judgments can use Azure while embeddings keep their existing provider/model/dimensions. Set `ARGUS_LLM_PROVIDER` to `azure_openai` or `azure_inference`; `ARGUS_RESOLUTION_PROVIDER` optionally selects a separate judge provider. `ARGUS_EXTRACTION_MODEL` and `ARGUS_RESOLUTION_MODEL` identify the deployed models. Without an explicit LLM provider, existing Google/OpenAI profiles retain their original routing.

For Azure OpenAI v1, configure `AZURE_OPENAI_BASE_URL=https://YOUR-RESOURCE.openai.azure.com/openai/v1` and `AZURE_OPENAI_API_KEY`. Model names must match your deployment names; catalog listings do not establish that a model is deployed.

For the Azure AI model inference API, configure `AZURE_INFERENCE_ENDPOINT=https://YOUR-RESOURCE.services.ai.azure.com/models`, `AZURE_INFERENCE_API_VERSION=2024-05-01-preview`, and `AZURE_INFERENCE_API_KEY`. GPT-OSS-120B was exercised with strict structured output through this interface. Keep `/chat/completions` and the version query out of the base URL.

Optional `ARGUS_LLM_BASE_URL`/`ARGUS_RESOLUTION_BASE_URL` and corresponding `ARGUS_LLM_API_VERSION`/`ARGUS_RESOLUTION_API_VERSION` override the endpoints per role. Endpoints and models are recorded in the processing version; keys remain in the environment. Azure calls use schema-validated structured output, the configured timeout, and no SDK retries. The pipeline's bounded retry policy still applies. Provider changes never silently retry a different model or rewrite an existing job's configuration. `ARGUS_MODEL_PROVIDER` continues to identify the embedding provider when LLM routing is overridden, preserving embedding caches and graph namespaces.

## Legacy corpus and current boundaries

The existing catalog contains 6,000 documents, 133,562 sections, and 252,654 chunks imported into Postgres. Existing SQLite databases are read only by the one-time migration utility:

```powershell
npm run migrate:legacy
```

The dashboard labels the earlier dictionary-based map and catalog **Legacy graph** and **Legacy corpus**. Newly processed sources appear separately in Files with their real stage status and readers. Parsing is not semantic readiness, and imported dictionary links are not newly extracted assertions. Current dashboard chat retrieval still searches the legacy Postgres BM25 index. Slice 4 exposes published-source retrieval separately; the investigation agent and new semantic-map integration remain later work.

## Published retrieval tools

`GET /api/retrieval/tools` lists six typed tools: `search_sources`, `find_entities`, `read_chunks`, `inspect_assertions`, `expand_connections`, and `find_paths`. Invoke one with `POST /api/retrieval/tools/{name}` and body `{"arguments": {...}}`. The agent receives these contracts rather than schema access or arbitrary Cypher. `app.retrieval.bindings.get_tools()` returns LangChain StructuredTools for a later LangGraph ToolNode; no agent loop or MCP transport is enabled yet.

`POST /api/retrieval/search` accepts `{"query":"your question","mode":"hybrid","limit":10}`. Modes are lexical, vector and hybrid. Search combines published Postgres BM25 with native FalkorDB chunk ANN using reciprocal-rank fusion, constant 60. Query embeddings use explicit retrieval-query semantics, matching the publication's provider/model/dimensions, with a persistent profile-keyed cache. Hybrid channel failure is explicitly reported as partial, never silently disguised as hybrid success.

Tools search only active semantic publications in the configured embedding space. They validate source revision and processing version, preserve exact quotation offsets, then recheck publication state before returning. Results retain assertion polarity, conditions, citations, timings, budget receipts and truncation reasons. Shared mentions are navigation rather than scientific assertions; composed paths do not establish a new scientific conclusion.

Traversal uses bounded BFS over source-supported assertion adjacency: up to three hops, 20 assertions per expanded entity, 40 discovered entities and 100 returned assertions. The execution session admits up to 64 database operations with 1.5-second query timeouts and a soft 30-second elapsed budget; in-flight calls and final consistency/persistence can extend beyond it. Responses are capped at 64,000 characters. Snapshot scope is capped at 10,000 publications. ANN examines at most 240 indexed candidates before publication/document filtering and can underfill. Empty bounded results do not prove absence.

For the pinned FalkorDB runtime, native cosine vector scores are distances (lower is nearer), confirmed by an identical-vector read returning approximately zero. Current upstream examples conflict with this runtime behavior; the API labels the signal `cosine_distance` explicitly. Neither BM25, distance nor fusion scores are confidence probabilities.

Slice 4 was exercised on the one currently published semantic source, not the complete registered corpus. Its operation does not establish cross-document quality or corpus-scale performance. Tool runs are persisted in the existing runs API, independently of ingestion jobs.

The source map retains both Network and Trees layouts, stable positions, progressive viewport loading, citation navigation, and expanded modal viewing. The native FalkorDB Browser can inspect the new semantic graph immediately.

Downloaded corpus files, provider credentials, databases, model artifacts, and detailed local progress remain outside Git. The root docs/ folder is intentionally ignored. Read agents.md for working agreements.
