Architecture verification - how the verifier decides what Argus actually is

Status published: 'architecture unverified' until internal-state evidence exists.
Protocol: (1) ingest benchmark-corpus.md unchanged; (2) run evaluation-questions.md conversation by conversation; (3) score with scoring-guide.md;
(4) only then classify behavior using the implementation evidence below. Data suppression or consistent 0 hits on traversal categories is itself data.

Implementation anchors in this build (verify these, do not assume):
- Graph store: FalkorDB per project (labels Document/Section/Chunk/Mention/Assertion/Entity; entity map gated on ingestion_resolution_decisions of the active publication). Typed edges: HAS_SECTION, HAS_CHUNK, NEXT_CHUNK, MENTS, RELATES.
- Lexical: Postgres ParadeDB BM25 over documents/sections/chunks; matches power keyword questions.
- Vector channel: disabled in this build (no embedding spend); anything implying vector recall is unsupported by implementation.
- Retrievability surface: scripts/app/retrieval tools: tool search_sources / find_entities (lexical seed), expand_connections (typed-edge expansion over FalkorDB), inspect_assertions (assertion provenance).
- Ingestion convention for this corpus: committed to facts via a deterministic fact-line parser, so extraction quality is NOT a variable in the verdict; recorded in the write-up with exact tool named.

Classification matrix (verifier decides; do not lean on self-report):
- Traditional vector RAG: lexical/vector hits; no typed-edge traversal observed in traces; multi-hop categories fail or answer from prose coincidence only.
- Graph RAG: retrieval issues typed EDGE expansion/Mentions/RELATES, citation resolves Claim/provenance, and hops appear in retrieval traces for Q03/Q04/Q11/Q13.
- Agentic/iterative traditional RAG: convo loop running tools (search - check underlying - search again / comparing records where large Coconut extents exist and simple template replies), with hop answers emerging only from multi-shot retrieval.

Deliverables (the five artifacts in this folder):
- A benchmark-corpus.md (ingested unchanged; the fact-line convention documents the graph).
- B evaluation-questions.md
- C answer-key.md (computed; never ingested)
- D scoring-guide.md
- E architecture-verification.md (this file)

Run commands:
- Regenerate artifacts: python backend/python/scripts/generate_benchmark.py
- Ingest corpus (workspace or project scope): python backend/python/scripts/publish_benchmark.py --project argus-benchmark
  - Deterministic fact-line parser; publishes one document with one section per record (161 sections/chunks), 103 entities, 323 assertions into the project's FalkorDB graph; quality/processing labels say benchmark_corpus and record that no model extracted anything.
- Smoke probes (Session + tools in backend/python/app/retrieval): BM25 search_sources, find_entities (citation-verified mention spans), find_paths (typed-edge traversal up to 3 hops per call; the 6-hop flagship chain composes from chained calls), inspect_assertions (polarity preserved).
  - All probes and all scoring conversations run with search mode lexical only. Hybrid or vector mode issues a live embedding-provider call and is excluded; discovery transcripts that show provider calls are logged as cost leaks (see scoring-guide controls).

Publication history: the corpus was authored 2026-10-18 and regenerated solely from backend/python/scripts/benchmark_model.py. Answer files are never ingested; the benchmark project owns its own FalkorDB graph.
