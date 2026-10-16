import { createClient } from 'redis';
import { config } from '../config/env.js';
import { corpusService } from './corpus.service.js';
import type { GraphView, GraphNode, GraphEdge, Document } from '../types/evidence.types.js';
import { logger } from '../utils/logger.util.js';

const value = (input: unknown): string => {
  if (input === null || input === undefined) return 'null';
  if (typeof input === 'string') return JSON.stringify(input).replace(/\\u([0-9a-f]{4})/gi, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
  if (Array.isArray(input)) return `[${input.map(value).join(',')}]`;
  if (typeof input === 'object') return `{${Object.entries(input).map(([key, entry]) => `${key}:${value(entry)}`).join(',')}}`;
  return String(input);
};

class GraphService {
  private client = createClient({ url: config.redisUrl, socket: { connectTimeout: 1500, reconnectStrategy: false } });
  private signature = '';
  private syncing?: Promise<boolean>;
  status = 'not connected';
  lastError?: string;
  indexedDocuments = 0;
  indexedChunks = 0;
  private revisions = new Map<string, string>();
  private chunkCounts = new Map<string, number>();
  backfill = { status: 'idle', processedDocuments: 0, limit: 0 };

  constructor() {
    const invalidate = (message: string) => {
      this.status = 'unavailable';
      this.lastError = message;
      this.signature = '';
      this.revisions.clear();
      this.chunkCounts.clear();
      this.indexedDocuments = 0;
      this.indexedChunks = 0;
    };
    this.client.on('error', error => invalidate(error.message));
    this.client.on('end', () => invalidate('Graph connection closed; synchronization is required.'));
  }

  async query(query: string, readOnly = true): Promise<unknown[][]> {
    if (!this.client.isOpen) await this.client.connect();
    const result = await this.client.sendCommand([readOnly ? 'GRAPH.RO_QUERY' : 'GRAPH.QUERY', config.graphName, query, 'TIMEOUT', '10000']) as unknown as unknown[];
    return Array.isArray(result[1]) ? result[1] as unknown[][] : [];
  }

  async ensure(): Promise<boolean> {
    const catalog = corpusService.read();
    if (!corpusService.counts().documents) { this.status = 'awaiting ingestion'; return false; }
    const signature = `${catalog.updatedAt}:${corpusService.counts().chunks}`;
    if (signature === this.signature && this.status === 'ready') return true;
    if (this.syncing) return this.syncing;
    this.syncing = this.sync(signature).finally(() => { this.syncing = undefined; });
    return this.syncing;
  }

  private async batch(rows: Record<string, unknown>[], query: string) {
    for (let offset = 0; offset < rows.length; offset += 100) await this.query(`UNWIND ${value(rows.slice(offset, offset + 100))} AS row ${query}`, false);
  }

  private async sync(signature: string, suppliedDocuments?: Document[]): Promise<boolean> {
    this.status = 'syncing';
    try {
      const catalog = corpusService.read();
      for (const label of ['Document', 'Section', 'Chunk', 'Entity']) {
        try { await this.query(`CREATE INDEX FOR (n:${label}) ON (n.id)`, false); } catch (error) { if (!String(error).toLowerCase().includes('already')) throw error; }
      }
      const documents = (suppliedDocuments || corpusService.documents(300)).filter(doc => this.revisions.get(doc.id) !== doc.revisionId);
      await this.batch(documents.map(d => ({ id: d.id, title: d.title, revisionId: d.revisionId })), 'MERGE (d:Document {id:row.id}) SET d.title=row.title,d.revisionId=row.revisionId');
      await this.batch(documents.flatMap(d => d.sections.map(s => ({ id: s.id, title: s.title, documentId: d.id }))), 'MATCH (d:Document {id:row.documentId}) MERGE (s:Section {id:row.id}) SET s.title=row.title MERGE (d)-[:HAS_SECTION]->(s)');
      await this.batch(documents.flatMap(d => d.chunks.map(c => ({ id: c.id, documentId: d.id, sectionId: c.sectionId, ordinal: c.ordinal, text: c.text }))), 'MATCH (s:Section {id:row.sectionId}) MERGE (c:Chunk {id:row.id}) SET c.documentId=row.documentId,c.sectionId=row.sectionId,c.ordinal=row.ordinal,c.text=row.text MERGE (s)-[:HAS_CHUNK]->(c)');
      await this.batch(documents.flatMap(d => d.entities.map(e => ({ id: e.id, label: e.label, kind: e.type }))), 'MERGE (e:Entity {id:row.id}) SET e.label=row.label,e.kind=row.kind');
      await this.batch(documents.flatMap(d => d.entities.flatMap(e => [...new Set(e.mentions.map(m => m.chunkId))].map(chunkId => ({ entityId: e.id, chunkId })))), 'MATCH (c:Chunk {id:row.chunkId}),(e:Entity {id:row.entityId}) MERGE (c)-[:MENTIONS]->(e)');
      await this.batch(documents.flatMap(d => d.chunks.slice(1).filter((c, index) => c.sectionId === d.chunks[index].sectionId).map(c => ({ previous: d.chunks[d.chunks.indexOf(c) - 1].id, next: c.id }))), 'MATCH (a:Chunk {id:row.previous}),(b:Chunk {id:row.next}) MERGE (a)-[:NEXT_CHUNK]->(b)');
      this.signature = signature;
      for (const doc of documents) { this.revisions.set(doc.id, doc.revisionId); this.chunkCounts.set(doc.id, doc.chunks.length); }
      this.indexedDocuments = this.revisions.size;
      this.indexedChunks = [...this.chunkCounts.values()].reduce((sum, count) => sum + count, 0);
      this.status = 'ready';
      this.lastError = undefined;
      logger.info('GraphService', 'Evidence graph synchronized', corpusService.counts());
      return true;
    } catch (error) {
      this.status = 'unavailable';
      this.lastError = error instanceof Error ? error.message : String(error);
      logger.warn('GraphService', 'Graph unavailable; source-ledger inspection remains available', { error: this.lastError });
      return false;
    }
  }

  async warmDocuments(ids: string[]) {
    if (this.syncing) await this.syncing;
    const documents = [...new Set(ids)].slice(0, 30).map(id => corpusService.document(id)).filter(doc => this.revisions.get(doc.id) !== doc.revisionId);
    if (!documents.length) return this.status === 'ready';
    this.syncing = this.sync(this.signature, documents).finally(() => { this.syncing = undefined; });
    return this.syncing;
  }

  startBackfill(limit = 6000) {
    if (this.backfill.status === 'running') return this.backfill;
    this.backfill = { status: 'running', processedDocuments: 0, limit: Math.max(1, Math.min(100000, Math.floor(limit))) };
    void (async () => {
      try {
        for (let offset = 0; offset < this.backfill.limit; offset += 25) {
          const documents = corpusService.documents(Math.min(25, this.backfill.limit - offset), offset);
          if (!documents.length) break;
          if (this.syncing) await this.syncing;
          this.syncing = this.sync(this.signature, documents).finally(() => { this.syncing = undefined; });
          if (!await this.syncing) throw new Error(this.lastError || 'Graph sync failed');
          this.backfill.processedDocuments += documents.length;
          await new Promise(resolve => setTimeout(resolve, 10));
        }
        this.backfill.status = 'complete';
      } catch (error) {
        this.backfill.status = 'failed';
        logger.error('GraphService', 'Graph backfill failed', error as Error);
      }
    })();
    return this.backfill;
  }

  async expand(ids: string[], limit: number, userQuery: string) {
    const boundedLimit = Math.max(0, Math.min(100, limit));
    const normalize = (text: string) => text.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
    const normalizedQuery = ` ${normalize(userQuery)} `;
    const entities = new Map(ids.flatMap(id => corpusService.chunk(id)?.document.entities || []).filter(entity => ['material', 'pollutant'].includes(entity.type) && normalizedQuery.includes(` ${normalize(entity.label)} `)).map(entity => [entity.id, entity]));
    const entityIds = [...entities.keys()];
    const policy = entityIds.length ? 'explicit-query-entity' : 'adjacent-source-context';
    const statement = entityIds.length
      ? `MATCH (seed:Chunk)-[:MENTIONS]->(entity:Entity)<-[:MENTIONS]-(neighbor:Chunk) WHERE seed.id IN $seedIds AND NOT neighbor.id IN $seedIds AND entity.id IN $entityIds RETURN DISTINCT neighbor.id AS chunkId,seed.id AS seedId,entity.id AS entityId,CASE WHEN seed.documentId <> neighbor.documentId THEN 0 ELSE 1 END AS documentPriority ORDER BY documentPriority,chunkId LIMIT $limit`
      : `MATCH (seed:Chunk)-[r:NEXT_CHUNK]-(neighbor:Chunk) WHERE seed.id IN $seedIds AND NOT neighbor.id IN $seedIds RETURN DISTINCT neighbor.id AS chunkId,seed.id AS seedId,startNode(r).id AS edgeSource,endNode(r).id AS edgeTarget ORDER BY chunkId LIMIT $limit`;
    const query = `CYPHER seedIds=${value(ids)} limit=${boundedLimit}${entityIds.length ? ` entityIds=${value(entityIds)}` : ''} ${statement}`;
    const rows = await this.query(query);
    const explain = await this.client.sendCommand(['GRAPH.EXPLAIN', config.graphName, query]);
    return { matches: rows.map(row => ({ chunkId: String(row[0]), seedId: String(row[1]), entityId: entityIds.length ? String(row[2]) : undefined, edgeSource: entityIds.length ? undefined : String(row[2]), edgeTarget: entityIds.length ? undefined : String(row[3]) })), execution: { command: 'GRAPH.RO_QUERY', graph: config.graphName, query: statement, parameters: { seedIds: ids, limit: boundedLimit, ...(entityIds.length ? { entityIds } : {}) }, executedQuery: query, explain, explainCommand: 'GRAPH.EXPLAIN', explainNote: 'Plan inspection is a separate operation and is included in this stage duration; it is not operator execution profiling.', policy, explicitQueryEntities: [...entities.values()].map(({ id, label, type }) => ({ id, label, type })), path: entityIds.length ? '(seed:Chunk)-[:MENTIONS]->(entity:Entity)<-[:MENTIONS]-(neighbor:Chunk)' : '(seed:Chunk)-[:NEXT_CHUNK]-(neighbor:Chunk)', maxHops: entityIds.length ? 2 : 1, connectionPolicy: entityIds.length ? 'Only material/pollutant dictionary labels explicitly named in the normalized user query; cross-document connections ordered first. Co-mention is unvalidated.' : 'No explicit material/pollutant term in query; expand only one-hop adjacent chunks from the same source section, preserving actual NEXT_CHUNK edge direction.' } };
  }

  async inspect(focus: { documentId?: string; sectionId?: string; chunkId?: string }, explicitIds?: string[]): Promise<GraphView> {
    const needed = explicitIds ? explicitIds.flatMap(id => { const result = corpusService.chunk(id); return result ? [result.document.id] : []; }) : focus.documentId ? [focus.documentId] : focus.chunkId ? [corpusService.chunk(focus.chunkId)?.document.id].filter((id): id is string => !!id) : [];
    if (needed.length) await this.warmDocuments(needed);
    const available = await this.ensure();
    const document = focus.documentId ? corpusService.document(focus.documentId) : undefined;
    const focusedChunk = focus.chunkId ? corpusService.chunk(focus.chunkId) : undefined;
    const all = explicitIds ? explicitIds.flatMap(id => { const result = corpusService.chunk(id); return result ? [result] : []; }) : focusedChunk ? [focusedChunk] : document ? document.chunks.map(chunk => ({ chunk, document })) : corpusService.allChunks();
    const selected = explicitIds ? all.filter(({ chunk }) => explicitIds.includes(chunk.id)) : all.filter(({ chunk, document }) => (!focus.documentId || document.id === focus.documentId) && (!focus.sectionId || chunk.sectionId === focus.sectionId) && (!focus.chunkId || chunk.id === focus.chunkId));
    const chosen = selected.slice(0, 100);
    const nodes = new Map<string, GraphNode>();
    const edges = new Map<string, GraphEdge>();
    const addEdge = (source: string, target: string, type: string) => { const id = `${source}|${type}|${target}`; edges.set(id, { id, source, target, type }); };
    for (const { chunk, document } of chosen) {
      nodes.set(document.id, { id: document.id, label: document.title, type: 'document', documentId: document.id });
      nodes.set(chunk.sectionId, { id: chunk.sectionId, label: chunk.sectionTitle, type: 'section', documentId: document.id, sectionId: chunk.sectionId });
      nodes.set(chunk.id, { id: chunk.id, label: `Chunk ${chunk.ordinal}`, type: 'chunk', documentId: document.id, sectionId: chunk.sectionId, chunkId: chunk.id, startOffset: chunk.startOffset, endOffset: chunk.endOffset, preview: chunk.text.slice(0, 180) });
      addEdge(document.id, chunk.sectionId, 'HAS_SECTION');
      addEdge(chunk.sectionId, chunk.id, 'HAS_CHUNK');
      for (const entity of document.entities.filter(e => e.mentions.some(m => m.chunkId === chunk.id))) {
        nodes.set(entity.id, { id: entity.id, label: entity.label, type: 'entity', entityType: entity.type });
        addEdge(chunk.id, entity.id, 'MENTIONS');
      }
    }
    for (const { chunk, document } of chosen) {
      const next = document.chunks.find(c => c.ordinal === chunk.ordinal + 1 && c.sectionId === chunk.sectionId);
      if (next && nodes.has(next.id)) addEdge(chunk.id, next.id, 'NEXT_CHUNK');
    }
    if (available && chosen.length) {
      const rows = await this.query(`MATCH (c:Chunk) WHERE c.id IN ${value(chosen.map(c => c.chunk.id))} RETURN c.id`);
      if (rows.length !== chosen.length) return { nodes: [...nodes.values()], edges: [...edges.values()], focus, truncated: selected.length > 100, source: 'source-ledger', status: 'graph verification incomplete' };
      const relations = await this.query(`MATCH (a)-[r]->(b) WHERE a.id IN ${value([...nodes.keys()])} AND b.id IN ${value([...nodes.keys()])} RETURN a.id,b.id,type(r) LIMIT 2000`);
      edges.clear();
      for (const row of relations) addEdge(String(row[0]), String(row[1]), String(row[2]));
    }
    return { nodes: [...nodes.values()], edges: [...edges.values()], focus, truncated: selected.length > 100, source: available ? 'falkordb' : 'source-ledger', status: this.status };
  }

  async diagnostics() {
    const available = await this.ensure();
    if (!available) return { status: this.status, error: this.lastError };
    const query = 'MATCH (c:Chunk) WHERE c.id = $chunkId RETURN c.id';
    const example = corpusService.documents(1)[0]?.chunks[0]?.id || '';
    const plan = await this.client.sendCommand(['GRAPH.EXPLAIN', config.graphName, `CYPHER chunkId=${value(example)} ${query}`]);
    const counts = await this.query('MATCH (n) RETURN count(n)');
    const relationships = await this.query('MATCH ()-[r]->() RETURN count(r)');
    return { status: this.status, name: config.graphName, nodes: counts[0]?.[0], edges: relationships[0]?.[0], indexedDocuments: this.indexedDocuments, indexedChunks: this.indexedChunks, initialProjectionDocuments: 300, backfill: this.backfill, exampleQuery: query, explain: plan, capabilities: { graphTraversal: true, propertyIndexes: true, vectorIndex: false, fulltextIndex: false }, note: 'BM25 is executed in SQLite FTS5; FalkorDB supplies the structural graph, property lookup indexes, and entity co-mention traversal. Selected documents are synchronized on demand; full backfill is explicit.' };
  }
}
export const graphService = new GraphService();
