# Argus

An inspectable source workspace powered by FalkorDB. Python and LangGraph run ingestion, Postgres stores processing state and BM25 indexes, and FalkorDB stores the semantic graph and vectors. The Next.js dashboard retains central chat and a resizable Source Explorer.

## Run locally

Requirements: Python 3.12 (the tested local extraction runtime), Node.js 22.13+, npm, and Docker.

```powershell
docker compose up -d
npm run setup
Copy-Item backend/python/.env.example backend/python/.env
npm run dev
```

Configure Azure LLM2 and the separate embedding deployment in ignored backend/.env or backend/python/.env before model processing. LLM2 is GPT-4.1 mini for all ingestion LLM work; LLM1/GPT-5 is reserved for the separately developed agent and is never selected by ingestion. `npm run setup` creates the local Python virtual environment when missing. The first local GLiNER run downloads model weights. All services bind to localhost; authentication remains outside this implementation pass.

- Dashboard: http://localhost:3001/dashboard
- Python API and OpenAPI: http://localhost:4000/docs
- FalkorDB Browser: http://localhost:3000
- Postgres with pg_search: localhost:5434, database/user `argus`, development password `argus_local`.
- FalkorDB Browser connection: localhost:6379, user `default`, empty password, TLS off.

`npm run build` compiles Python and builds the frontend. `backend/src/` is retained as an inactive TypeScript migration reference; standard startup uses Python. `dev:legacy` is explicitly historical.

## Ingestion

Create a workspace on the home screen, select one or more document categories, describe the dataset, and choose files, a folder or a repository ZIP. Files selected in the creation modal follow the regular workspace upload path. A blank description is requested before uploading. New workspaces use the current local extraction contract; historical jobs retain their saved configuration and are not automatically reprocessed.

Categories seed entity and relationship types. Direct LLM2 requests receive random source chunks grouped into batches of up to 3,000 source tokens. There are no tools or fixed model call counts. A persisted 30-second admission window starts when workspace discovery begins: no further call starts afterward, and an active response may finish subject to its normal 120-second request timeout. Later files reuse the saved workspace settings.

The shared workspace budget defaults to 24,000 reserved tokens across calls and resumes. Reservations include the complete sampled request, schema, a conservative input allowance and up to 1,536 output tokens. Actual reported usage is shown separately. Reservations are not refunded after failures or crashes. Initial sampling is streamed; it does not pre-tokenize the whole corpus before the first batch. Entity types are capped at 24 and relationship types at 32 to bound local inference cost and overlapping labels.

The Python/LangGraph flow is register → parse → normalize → chunk, then chunk embeddings, initial entity extraction and workspace label discovery run in parallel. GLiNER-relex starts after the labels are ready. Entity resolution, entity embeddings, source validation and graph publication follow. Each file has immutable originals, revision/configuration identities, attempts, item artifacts, timings and checkpoints. Local model or provider failures remain explicit and retryable.

Plain GLiNER extracts entity spans. Those spans are retained alongside GLiNER-relex results, deduplicated by source location. GLiNER-relex jointly extracts entities and relationships locally; there is no per-chunk LLM extraction or LLM duplicate judging. It uses entity threshold 0.4, adjacency threshold 0.65 and relation threshold 0.8, within the model authors' documented ranges. Its scores are uncalibrated and can be confidently wrong. Exact source offsets and valid relationship endpoints are checked; this does not independently validate the relation's meaning or classify negation. Model relations retain `unclassified` polarity and extraction provenance.

Python source uses the built-in AST parser for imports, symbol definitions, inheritance and named call references. Qualified symbols preserve case and link matching references across files. These are syntax links; unresolved names are explicitly marked and do not establish runtime dispatch. GLiNER-relex processes Python comments and docstrings. Other supported languages retain source text and use local extraction; full semantic analysis for those languages is not implemented. Code syntax and model predictions expose their distinct provenance to retrieval tools.

Readers support JATS/XML/NXML and gzip, text/Markdown/MDX, source code, HTML, text-bearing PDF, DOCX, CSV/TSV, XLSX, JSON and JSONL. They preserve page/section/cell/record locations where the format supports them. JATS body accounting stops ingestion on actual text loss; abstract-only input is allowed with a coverage label. The optional `backend/python/requirements-layout.txt` installs Docling for category-routed PDF layout and table extraction. Otherwise PDFs use the text reader with an explicit warning. OCR, legacy Office binaries and arbitrary binary formats are not enabled.

Repository ZIPs retain paths and originals, reject unsafe paths, links, encrypted entries and oversized archives, and report skipped generated or unsupported files. Folder uploads apply the same file selection policy. New publications and later uploads update the workspace graph through the existing live processing stream. Both graph layouts, source readers and citation navigation use published records.

Chunking adapts the FalkorDB SDK v1.4.0 sentence/token algorithm with a 512-token cap and two-sentence overlap. Python and other source code use line boundaries. Oversized units split at exact source character boundaries. Normalized whitespace and citation offsets are retained; the modification notice and Apache-2.0 license remain under backend/python/licenses/.

Exact normalized entity names and types use SDK-style grouping without model judgment. Identical canonical entities reuse embeddings across files in the same project and vector space. Chunk and entity vectors use the separate Azure text-embedding-3-large deployment at native 3,072 dimensions. Relationship vectors are not generated; traversal uses stored relationships. Embedding batches contain up to 64 inputs. Requests are checked against Azure array, per-input and aggregate token bounds. A Postgres admission ledger shares the ingestion allowance across workers, defaulting to 135,000 estimated tokens per rolling minute for the supplied 150,000 TPM deployment, leaving headroom for query traffic. Retry-After headers are honored. Provider latency and quota wait are recorded separately.

Run `npm run setup` to install the pinned runtime into `backend/python/.venv`, which standard startup now prefers. The first local model use may download weights; cached loading avoids remote revalidation when possible. Use `backend/python/requirements-dev.txt` for pytest. `ARGUS_RUN_STORAGE_TESTS=1` enables an isolated Postgres/FalkorDB check with synthetic files and mocked model outputs; it does not ingest the real corpus or call Azure.

Originals, local model weights, credentials, backups and detailed progress remain outside Git. Do not ingest from `data/backups/` by default. Real ingestion is triggered by your file uploads in the UI.

## Published retrieval tools

`GET /api/retrieval/tools` lists six typed tools: `search_sources`, `find_entities`, `read_chunks`, `inspect_assertions`, `expand_connections`, and `find_paths`. Invoke one with `POST /api/retrieval/tools/{name}` and body `{"arguments": {...}}`. The agent receives these contracts rather than schema access or arbitrary Cypher. `app.retrieval.bindings.get_tools()` returns LangChain StructuredTools for the merged LangGraph investigation agent. MCP transport is not enabled.

`POST /api/retrieval/search` accepts `{"query":"your question","mode":"hybrid","limit":10}`. Modes are lexical, vector and hybrid. Search combines published Postgres BM25 with native FalkorDB chunk ANN using reciprocal-rank fusion, constant 60. Query embeddings use explicit retrieval-query semantics, matching the publication's provider/model/dimensions, with a persistent profile-keyed cache. Hybrid channel failure is explicitly reported as partial, never silently disguised as hybrid success.

Tools search only active semantic publications in the configured embedding space. They validate source revision and processing version, preserve exact quotation offsets, then recheck publication state before returning. Results retain assertion polarity, conditions, citations, timings, budget receipts and truncation reasons. Shared mentions are navigation rather than scientific assertions; composed paths do not establish a new scientific conclusion.

Traversal uses bounded BFS over source-supported assertion adjacency: up to three hops, 20 assertions per expanded entity, 40 discovered entities and 100 returned assertions. The execution session admits up to 64 database operations with 1.5-second query timeouts and a soft 30-second elapsed budget; in-flight calls and final consistency/persistence can extend beyond it. Responses are capped at 64,000 characters. Snapshot scope is capped at 10,000 publications. ANN examines at most 240 indexed candidates before publication/document filtering and can underfill. Empty bounded results do not prove absence.

For the pinned FalkorDB runtime, native cosine vector scores are distances (lower is nearer), confirmed by an identical-vector read returning approximately zero. Current upstream examples conflict with this runtime behavior; the API labels the signal `cosine_distance` explicitly. Neither BM25, distance nor fusion scores are confidence probabilities.

Slice 4 was previously exercised on one semantic source before the reset. That source had incomplete body coverage under the old parser and is no longer published. Those observations do not establish cross-document quality or corpus-scale performance; the revised Azure pipeline has not been run on the corpus. Tool runs are persisted in the existing runs API, independently of ingestion jobs.

The source map retains both Network and Trees layouts, stable positions, progressive viewport loading, citation navigation, and expanded modal viewing. The native FalkorDB Browser can inspect semantic graphs once fresh ingestion creates them.

Downloaded corpus files, provider credentials, databases, model artifacts, and detailed local progress remain outside Git. The root docs/ folder is intentionally ignored. Read agents.md for working agreements.

## Model deployment configuration


Use the deployment variables in `backend/python/.env.example`:

| Variables | Role |
| --- | --- |
| `LLM1_DEPLOYMENT_NAME`, `LLM1_DEPLOYMENT_URL`, `LLM1_DEPLOYMENT_KEY` | Chat; default deployment `gpt-5` |
| `LLM2_DEPLOYMENT_NAME`, `LLM2_DEPLOYMENT_URL`, `LLM2_DEPLOYMENT_KEY` | Workspace label discovery only; default deployment `gpt-4.1-mini` |
| `AZURE_API_KEY` | Legacy agent fallback only; ingestion requires explicit role keys |
| `AZURE_OPENAI_ENDPOINT` | Legacy provider setting; ingestion uses explicit embedding settings |
| `EMBEDDING_MODEL_NAME`, `EMBEDDING_MODEL_ENDPOINT`, `EMBEDDING_MODEL_KEY` | Document and query embeddings; default model `text-embedding-3-large`, 3,072 dimensions |

LLM URLs can be the complete Responses endpoint, such as `https://YOUR-RESOURCE.services.ai.azure.com/openai/v1/responses`. The application splits the API protocol from the base URL. A bare embedding resource endpoint gains `/openai/v1`; `/openai/v1/embeddings` is also accepted and normalized. An explicit `/models` embedding base uses the Azure inference API version. URLs must use HTTPS without credentials or query strings. Role-specific keys are used for their corresponding requests and never stored in processing profiles, graphs, or receipts. Responses requests use `store=false` and schema-validated output.

`LLM1_*` takes precedence over legacy chat settings; `LLM2_*` takes precedence over legacy extraction and resolution settings. GPT-5 cannot be selected as LLM2 in new profiles. Ingestion requires LLM2 and never substitutes LLM1. Generic provider adapters remain available for the agent and historical profiles. Newly registered ingestion jobs always use the explicit LLM2 and embedding deployment settings; stale Google or legacy model variables cannot select an ingestion provider. The approved ingestion deployment uses native 3,072 dimensions.

Embedding model, dimensions, provider, and normalized Azure embedding endpoint define the new vector namespace and query cache. Existing vectors are retained; switching to a new namespace requires reprocessing sources before they become searchable there. Model and endpoint changes produce new processing versions rather than rewriting saved jobs. Provider errors do not silently select another model. Ingestion uses configured timeouts, rate limits and bounded retries.

## Conversational research

`POST /api/chat` returns NDJSON events for acceptance, model activity, real tool calls, usage, and the final cited report. Greetings receive a conversational answer without keyword searches. Research answers use the six published-source tools, validate citation revisions and quotations, and open the cited processing job in Files. The legacy map retains its own identifiers and scope.

Configure the `LLM1_*` deployment variables above to select the chat model. Legacy independent `ARGUS_CHAT_*` settings remain available when LLM1 is absent. Responses requests use `store=false`.

Postgres stores run events, tool receipts, budgets, and LangGraph checkpoints. `GET /api/chat/{runId}` reconnects to saved results; `POST /api/chat/{runId}/resume` retries an unfinished step. The browser retains at most 12 run IDs in session storage for reload recovery, and sends only two preceding turns as conversational context. New chat clears those browser references. There is no cross-conversation semantic memory.

Each run admits at most eight model calls and eight retrieval calls, with 10,000 estimated context tokens, 2,048 maximum output tokens per call, and 64,000 reserved tokens overall. Two concurrent workers are allowed. A 180-second admission deadline and individual model request timeouts bound execution; in-flight work can exceed the admission deadline. Token reservations are estimates; reported usage is displayed separately. The optional $0.25 reservation limit applies only when both `ARGUS_CHAT_INPUT_USD_PER_MILLION` and `ARGUS_CHAT_OUTPUT_USD_PER_MILLION` are configured with deployment prices. No dollar cost is invented when prices are absent. Budget environment overrides in `.env.example` may lower these limits.

Run recovery preserves previous budget reservations. Completed tool results replay from their receipts; a crash after a paid model call but before its checkpoint can cause that call to repeat on resume. Citation validation checks source identity and quotation offsets; it does not prove every generated interpretation. Available publication counts are shown in the chat and engine configuration.
