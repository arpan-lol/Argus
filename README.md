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

Configure a Google or OpenAI credential in the ignored Python environment file before model processing. `npm run setup` creates the local Python virtual environment when missing. The first local GLiNER run downloads model weights. All services bind to localhost; authentication remains outside this implementation pass.

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

## Legacy corpus and current boundaries

The existing catalog contains 6,000 documents, 133,562 sections, and 252,654 chunks imported into Postgres. Existing SQLite databases are read only by the one-time migration utility:

```powershell
npm run migrate:legacy
```

The dashboard labels the earlier dictionary-based map and catalog **Legacy graph** and **Legacy corpus**. Newly processed sources appear separately in Files with their real stage status and readers. Parsing is not semantic readiness, and imported dictionary links are not newly extracted assertions. Current chat retrieval searches the legacy Postgres BM25 index; graph-assisted retrieval, the investigation agent, and new semantic-map integration belong to later slices.

The source map retains both Network and Trees layouts, stable positions, progressive viewport loading, citation navigation, and expanded modal viewing. The native FalkorDB Browser can inspect the new semantic graph immediately.

Downloaded corpus files, provider credentials, databases, model artifacts, and detailed local progress remain outside Git. The root docs/ folder is intentionally ignored. Read agents.md for working agreements.
