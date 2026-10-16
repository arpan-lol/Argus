import { performance } from 'node:perf_hooks';
import { randomUUID } from 'node:crypto';
import { corpusService } from './corpus.service.js';
import { graphService } from './graph.service.js';
import { runService } from './run.service.js';
import { AppError } from '../types/errors.js';
import type { EvidenceHit, SearchOptions, Trace } from '../types/evidence.types.js';

export const retrievalService = {
  async search(query: string, options: SearchOptions = {}) {
    if (typeof query !== 'string' || !query.trim() || query.length > 2000) throw new AppError('Query must contain 1–2000 characters', 400, true);
    const started = performance.now();
    const runId = randomUUID();
    const trace: Trace[] = [];
    const limit = Math.max(1, Math.min(30, Number(options.limit) || 12));
    const warnings: string[] = [];
    const effective = { graphExpansion: options.graphExpansion !== false, limit, documentId: options.documentId };
    let stage = performance.now();
    const candidates = corpusService.lexical(query, effective.graphExpansion ? Math.max(1, Math.ceil(limit * 0.7)) : limit, effective.documentId);
    const results: EvidenceHit[] = candidates.map(({ chunk, document, score }, index) => ({ ...chunk, chunkId: chunk.id, documentTitle: document.title, score, scoreType: 'bm25', rank: index + 1, reasons: ['Matched query terms using SQLite FTS5 BM25 over source text, document title, and section title'], pathIds: [`${document.id}|HAS_SECTION|${chunk.sectionId}`, `${chunk.sectionId}|HAS_CHUNK|${chunk.id}`], retrieval: 'lexical' }));
    trace.push({ id: `${runId}:lexical`, stage: 'lexical retrieval', status: 'complete', durationMs: performance.now() - stage, inputCount: corpusService.counts().chunks, outputCount: results.length, details: { engine: 'SQLite FTS5', ranking: 'BM25', scoreInterpretation: 'Negated SQLite BM25; higher ranks first. Not confidence or probability.', queryOperator: 'OR', fields: ['chunk text', 'document title', 'section title'] } });
    let graphAvailable = false;
    if (effective.graphExpansion && results.length) {
      stage = performance.now();
      graphAvailable = await graphService.ensure();
      if (graphAvailable) graphAvailable = await graphService.warmDocuments(results.map(hit => hit.documentId));
      trace.push({ id: `${runId}:sync`, stage: 'graph readiness', status: graphAvailable ? 'complete' : 'unavailable', durationMs: performance.now() - stage, details: { indexedDocuments: graphService.indexedDocuments, indexedChunks: graphService.indexedChunks, totalDocuments: corpusService.counts().documents } });
      if (graphAvailable) {
        stage = performance.now();
        const expanded = await graphService.expand(results.slice(0, 4).map(hit => hit.id), Math.max(0, limit - results.length), query);
        const seen = new Set(results.map(hit => hit.id));
        for (const match of expanded.matches) {
          const source = corpusService.chunk(match.chunkId);
          if (!source || seen.has(match.chunkId) || (effective.documentId && source.document.id !== effective.documentId)) continue;
          const entity = source.document.entities.find(e => e.id === match.entityId);
          const chunk = source.chunk;
          const reasons = match.entityId ? [`Shares the explicitly queried term “${entity?.label || match.entityId}” with retrieved chunk ${match.seedId}`, 'Term co-mention is a retrieval connection, not a scientific relationship or validated claim'] : [`Adjacent source context for retrieved chunk ${match.seedId}`, 'One NEXT_CHUNK edge in the same source section; no inferred scientific relationship'];
          const pathIds = match.entityId ? [`${match.seedId}|MENTIONS|${match.entityId}`, `${chunk.id}|MENTIONS|${match.entityId}`] : [`${match.edgeSource}|NEXT_CHUNK|${match.edgeTarget}`];
          results.push({ ...chunk, chunkId: chunk.id, documentTitle: source.document.title, score: 0, scoreType: 'graph_path', rank: results.length + 1, reasons, pathIds, retrieval: 'graph' });
          seen.add(chunk.id);
        }
        trace.push({ id: `${runId}:expansion`, stage: 'graph expansion', status: 'complete', durationMs: performance.now() - stage, inputCount: Math.min(4, candidates.length), outputCount: results.length - candidates.length, details: { ...expanded.execution, entityExtraction: 'deterministic dictionary mentions, no inferred scientific claims', scoreInterpretation: 'Graph-path hits carry score=0 solely as a compatibility placeholder. They have no numeric relevance or confidence score; inspect their recorded path.' } });
      } else warnings.push('FalkorDB is unavailable. Results contain lexical evidence only.');
    } else trace.push({ id: `${runId}:expansion`, stage: 'graph expansion', status: 'disabled', durationMs: 0 });
    stage = performance.now();
    const graph = await graphService.inspect({}, results.map(hit => hit.id));
    trace.push({ id: `${runId}:projection`, stage: 'evidence graph projection', status: 'complete', durationMs: performance.now() - stage, outputCount: graph.nodes.length });
    if (graphService.indexedDocuments < corpusService.counts().documents) warnings.push(`FalkorDB currently contains ${graphService.indexedDocuments} documents; lexical search covers all ${corpusService.counts().documents} parsed documents. Selected evidence documents are synchronized on demand. Expansion can only discover neighbors already in the graph; run a full backfill for broader coverage.`);
    const unsupported = Object.keys(options).filter(key => !['graphExpansion', 'limit', 'documentId'].includes(key));
    if (unsupported.length) warnings.push(`Unsupported options were not applied: ${unsupported.join(', ')}`);
    const response = { runId, query: query.trim(), corpusVersion: corpusService.read().updatedAt, results, trace, timings: { totalMs: performance.now() - started }, options: effective, capabilities: { lexical: true, graph: graphAvailable || graphService.status === 'ready', vector: false, generation: false, reranking: false }, warnings, graph, offsetUnit: 'unicode_codepoint' };
    runService.save(response);
    return response;
  },
};
