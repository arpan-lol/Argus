import type { Request, Response } from 'express';
import { corpusService } from '../services/corpus.service.js';
import { graphService } from '../services/graph.service.js';
import { retrievalService } from '../services/retrieval.service.js';
import { runService } from '../services/run.service.js';
import { config } from '../config/env.js';
import { AppError } from '../types/errors.js';

const compactDiscovery = (value: unknown): unknown => {
  if (Array.isArray(value)) return value.map(compactDiscovery);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).filter(([key]) => !['pmcids', 'ids', 'discoveryIds'].includes(key)).map(([key, item]) => [key, compactDiscovery(item)]));
  return value;
};

export const evidenceController = {
  health(_req: Request, res: Response) { res.json({ status: 'ok', service: 'falkor-evidence', corpus: corpusService.counts(), graph: { status: graphService.status, name: config.graphName }, capabilities: { lexical: true, vector: false, generation: false } }); },
  corpus(_req: Request, res: Response) {
    const catalog = corpusService.read();
    res.json({ schemaVersion: catalog.schemaVersion, collection: catalog.collection, updatedAt: catalog.updatedAt, counts: corpusService.counts(), discovery: compactDiscovery(catalog.discovery), ingestion: compactDiscovery(catalog.ingestion), capabilities: { lexical: true, graph: graphService.status === 'ready', vector: false, generation: false, reranking: false }, graph: { status: graphService.status, name: config.graphName, indexedDocuments: graphService.indexedDocuments, indexedChunks: graphService.indexedChunks, initialProjectionDocuments: 300, backfill: graphService.backfill, lastError: graphService.lastError }, offsetUnit: 'unicode_codepoint' });
  },
  documents(req: Request, res: Response) {
    const requestedLimit = Number(req.query.limit);
    const requestedOffset = Number(req.query.offset);
    const limit = Number.isFinite(requestedLimit) ? Math.max(1, Math.min(100, Math.floor(requestedLimit || 24))) : 24;
    const offset = Number.isFinite(requestedOffset) ? Math.max(0, Math.floor(requestedOffset)) : 0;
    const documents = corpusService.summaries(limit, offset);
    res.json({ documents, total: corpusService.counts().documents, limit, offset });
  },
  document(req: Request, res: Response) { res.json(corpusService.document(String(req.params.id))); },
  async graph(req: Request, res: Response) {
    res.json(await graphService.inspect({ documentId: typeof req.query.documentId === 'string' ? req.query.documentId : undefined, sectionId: typeof req.query.sectionId === 'string' ? req.query.sectionId : undefined, chunkId: typeof req.query.chunkId === 'string' ? req.query.chunkId : undefined }));
  },
  async diagnostics(_req: Request, res: Response) { res.json(await graphService.diagnostics()); },
  backfill(req: Request, res: Response) {
    const limit = Number(req.body?.limit || 6000);
    if (!Number.isFinite(limit) || limit < 1) throw new AppError('A finite positive document limit is required', 400, true);
    res.status(202).json(graphService.startBackfill(limit));
  },
  async search(req: Request, res: Response) {
    if (!req.body || typeof req.body.query !== 'string') throw new AppError('A query string is required', 400, true);
    if (req.body.options && (typeof req.body.options !== 'object' || Array.isArray(req.body.options))) throw new AppError('Options must be an object', 400, true);
    if (req.body.options?.documentId && typeof req.body.options.documentId !== 'string') throw new AppError('documentId must be a string', 400, true);
    res.json(await retrievalService.search(req.body.query, req.body.options));
  },
  run(req: Request, res: Response) { const run = runService.get(String(req.params.id)); if (!run) throw new AppError('Run not found', 404, true); res.json(run); },
  runs(_req: Request, res: Response) { res.json({ runs: runService.list() }); },
};
