import fs from 'node:fs';
import path from 'node:path';
import { config } from '../config/env.js';
import { AppError } from '../types/errors.js';
import type { Catalog, Document, Chunk } from '../types/evidence.types.js';
import { DatabaseSync } from 'node:sqlite';
import { gunzipSync } from 'node:zlib';

const decodeDocumentPayload = (payload: unknown): Document => {
  if (typeof payload === 'string') return JSON.parse(payload) as Document;
  if (payload instanceof Uint8Array) return JSON.parse(gunzipSync(Buffer.from(payload)).toString('utf8')) as Document;
  throw new AppError('Unsupported source document encoding', 503, true);
};

class CorpusService {
  private stamp = '';
  private catalog: Catalog = { schemaVersion: 1, collection: 'Use Case A · materials evidence', updatedAt: '', documents: [], discovery: {}, ingestion: { status: 'awaiting ingestion' } };
  private chunks = new Map<string, { chunk: Chunk; document: Document }>();
  private database?: DatabaseSync;

  private db() {
    const target = path.join(config.dataDir, 'corpus.sqlite3');
    if (!this.database && fs.existsSync(target)) this.database = new DatabaseSync(target, { readOnly: true });
    return this.database;
  }

  read(): Catalog {
    const target = path.join(config.dataDir, 'corpus.json');
    if (!fs.existsSync(target)) return this.catalog;
    const stat = fs.statSync(target);
    const stamp = `${stat.mtimeMs}:${stat.size}`;
    if (stamp !== this.stamp) {
      const catalog = JSON.parse(fs.readFileSync(target, 'utf8')) as Catalog;
      if (!Array.isArray(catalog.documents)) throw new AppError('Invalid ingestion catalog', 503, true);
      this.catalog = catalog;
      this.stamp = stamp;
      this.chunks.clear();
      for (const document of catalog.documents) for (const chunk of document.chunks) this.chunks.set(chunk.id, { chunk, document });
    }
    return this.catalog;
  }

  document(id: string): Document {
    const row = this.db()?.prepare('SELECT payload FROM documents WHERE id=?').get(id);
    if (row) return decodeDocumentPayload(row.payload);
    const document = this.read().documents.find(item => item.id === id);
    if (!document) throw new AppError('Document not found', 404, true);
    return document;
  }

  documents(limit = 24, offset = 0): Document[] {
    const db = this.db();
    if (db) return db.prepare('SELECT payload FROM documents ORDER BY CAST(substr(id,4) AS INTEGER) DESC LIMIT ? OFFSET ?').all(limit, offset).map(row => decodeDocumentPayload(row.payload));
    return this.read().documents.slice(offset, offset + limit);
  }
  summaries(limit = 24, offset = 0) {
    const db = this.db();
    if (db) return db.prepare(`SELECT d.id,d.title,
      json_extract(d.metadata_json,'$.year') AS year,
      json_extract(d.metadata_json,'$.doi') AS doi,
      json_extract(d.metadata_json,'$.journal') AS journal,
      json_extract(d.metadata_json,'$.sourceUrl') AS sourceUrl,
      (SELECT COUNT(*) FROM sections s WHERE s.document_id=d.id) AS sectionCount,
      (SELECT COUNT(*) FROM chunks c WHERE c.document_id=d.id) AS chunkCount
      FROM documents d ORDER BY CAST(substr(d.id,4) AS INTEGER) DESC LIMIT ? OFFSET ?`).all(limit, offset);
    return this.documents(limit, offset).map(({ id, title, year, doi, journal, sourceUrl, sections, chunks }) => ({ id, title, year, doi, journal, sourceUrl, sectionCount: sections.length, chunkCount: chunks.length }));
  }
  allChunks() { return this.documents(300).flatMap(document => document.chunks.map(chunk => ({ chunk, document }))); }
  chunk(id: string) {
    const row = this.db()?.prepare('SELECT document_id,payload FROM chunks WHERE id=?').get(id);
    if (row) return { chunk: JSON.parse(String(row.payload)) as Chunk, document: this.document(String(row.document_id)) };
    this.read(); return this.chunks.get(id);
  }
  lexical(query: string, limit: number, documentId?: string) {
    const tokens = query.toLowerCase().match(/[\p{L}\p{N}]+/gu)?.filter(t => t.length > 1).slice(0, 32) || [];
    if (!tokens.length || !this.db()) return [];
    const match = tokens.map(t => `"${t.replaceAll('"', '""')}"`).join(' OR ');
    const scope = documentId ? ' AND c.document_id=?' : '';
    const sql = `SELECT c.id,c.document_id,c.payload,bm25(chunks_fts,0,1,2,1) AS score FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.chunk_id WHERE chunks_fts MATCH ?${scope} ORDER BY score LIMIT ?`;
    const params = documentId ? [match, documentId, limit] : [match, limit];
    return this.db()!.prepare(sql).all(...params).map(row => ({ chunk: JSON.parse(String(row.payload)) as Chunk, document: this.document(String(row.document_id)), score: -Number(row.score) }));
  }
  counts() {
    const db = this.db();
    if (db) {
      const documents = Number(db.prepare('SELECT COUNT(*) AS n FROM documents').get()?.n || 0);
      const chunks = Number(db.prepare('SELECT COUNT(*) AS n FROM chunks').get()?.n || 0);
      const sections = Number(db.prepare('SELECT COUNT(*) AS n FROM sections').get()?.n || 0);
      const counts = this.read().tableCounts as Record<string, number> | undefined;
      return { documents, chunks, sections, entities: counts?.entities || 0, entityMentions: counts?.entityMentions || 0 };
    }
    const documents = this.read().documents;
    return { documents: documents.length, sections: documents.reduce((sum, d) => sum + d.sections.length, 0), chunks: this.chunks.size, entities: new Set(documents.flatMap(d => d.entities.map(e => e.id))).size, entityMentions: documents.reduce((sum, d) => sum + d.entities.reduce((n, e) => n + e.mentions.length, 0), 0) };
  }
}
export const corpusService = new CorpusService();
