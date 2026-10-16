# Cosmic Source Workspace

A source workspace extended from [Cosmic Engine](https://github.com/arpan-lol/cosmic-engine), with central chat and a resizable Source Explorer. Follow citations through a stable, progressively loaded graph, or switch the right panel to file and chunk readers.

## Run locally

Requirements: Node.js 22.13+, npm, Python 3.11+, and Docker for FalkorDB.

```powershell
docker compose up -d
npm run setup
npm run ingest -- --limit 150 --batch-size 25
npm run dev
```

- Workspace: http://localhost:3001
- Express API: http://localhost:4000/api
- FalkorDB browser: http://localhost:3000

The first ingestion command discovers the available scientific collections, downloads a bounded batch of actual PMC full text, parses it, and writes a searchable local catalog. To continue acquisition toward a larger collection, rerun with a higher total target:

```powershell
npm run ingest -- --limit 6000 --batch-size 100
```

Acquisition is resumable. A discovery count is not a downloaded or indexed count. Network availability and source response times determine acquisition duration. Downloaded article text and local databases stay in ignored data/; reproduce them with the ingestion command after cloning.

npm run build builds both application packages. Backend configuration is described in [backend/.env.example](backend/.env.example). Keep the unauthenticated workspace bound to localhost.

## Source Explorer

The graph provides a collection overview, files, headings and chunks at increasing zoom levels. Positions remain stable when selecting nodes. Drag to pan, scroll to zoom, select a node for its details, and double-click a file to explore it. Citation navigation zooms out, moves to the source, and zooms in. Only the current viewport and nearby records are loaded; the browser does not render the complete graph at once.

Shared-name connections can link files across the collection. Overview groups summarize connections for navigation; grouping and distance do not imply semantic similarity or scientific validation. The inactive graph or file view is unmounted when switching modes.

Cosmic-derived readers support local previews for PDF, DOCX, images, spreadsheets and text. Local file previews are labeled **Preview only** and are not uploaded or indexed. Server upload ingestion is pending agreement on its standardized processing pipeline. Presentations and legacy binary Word files have explicit fallback states.

## Source and graph semantics

Use Case A is materials source review, initially adsorption and water remediation, with a broader catalysis discovery collection. Source articles are acquired through official PMC services and retain their source links and license metadata.

JATS/XML article sections are logical navigation locations, not physical PDF pages. Chunks preserve exact source spans into normalized article text. The graph connects documents, sections, chunks, and explicitly labeled dictionary term mentions. A co-mention is not a validated experimental claim, a causal relationship, or a scientific endorsement.

The first slice supports source-backed lexical retrieval and graph exploration without a model API key. Dense embeddings, model synthesis, and other unavailable strategies must remain visibly unavailable rather than return simulated results. Search scores are ranking values, not probabilities. Corpus search coverage and graph synchronization coverage are displayed separately.

## Organization

```text
frontend/       Next.js dashboard, source viewer, graph and run inspector
backend/        Express routes, controllers, services, errors and logging
ingestion/      Resumable PMC discovery, acquisition, parsing and indexing
scripts/        Local workspace launcher
compose.yaml    Pinned FalkorDB service
research/       Reproducible discovery audit
engine/         Earlier independent Python integration spike
fixtures/       Explicitly synthetic fixtures for the Python spike only
```

The application reuses Cosmic Engine's UI primitives, theme, strategy-control pattern, and Express utility conventions. It does not require Cosmic's authentication, Milvus, or PostgreSQL services. The original project remains unmodified.

## Development agreement

Read [agents.md](agents.md). Future architectural decisions require discussing the options with Arpan. Commit messages are lowercase. Local progress, goals, and detailed implementation notes live under the gitignored root docs/ directory.
