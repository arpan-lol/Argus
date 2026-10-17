import fs from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { config } from '../config/env.js';
import { corpusService } from './corpus.service.js';
import { graphService } from './graph.service.js';
import { AppError } from '../types/errors.js';
import type { MapBounds, MapNode, MapEdge } from '../types/map.types.js';
import type { Chunk, Entity } from '../types/evidence.types.js';
import { logger } from '../utils/logger.util.js';

const CELL = 512;
const COLUMNS = 80;
const GROUP = 8;
const quote = (value: unknown) => JSON.stringify(value);
const short = (value: string, length = 70) => value.length > length ? `${value.slice(0, length).trim()}…` : value;
type LayoutDocument = { id: string; title: string; slot: number; x: number; y: number };

class MapService {
  private source?: DatabaseSync;
  private layout?: DatabaseSync;
  private initialized = false;
  private documents = new Map<string, LayoutDocument>();
  private entities = new Map<string, MapNode>();
  private groupEdges: MapEdge[] = [];
  private childPositions = new Map<string, Map<string, { x: number; y: number }>>();

  private initialize() {
    if (this.initialized && Number(this.source!.prepare('SELECT count(*) AS count FROM documents').get()?.count) === this.documents.size) return;
    const target = path.join(config.dataDir, 'corpus.sqlite3');
    if (!fs.existsSync(target)) throw new AppError('Source collection is not available yet', 503, true);
    this.source ||= new DatabaseSync(target, { readOnly: true });
    this.layout ||= new DatabaseSync(path.join(config.dataDir, 'graph-layout.sqlite'));
    this.layout.exec('PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS document_positions(id TEXT PRIMARY KEY,slot INTEGER UNIQUE,x REAL,y REAL); CREATE TABLE IF NOT EXISTS entity_positions(id TEXT PRIMARY KEY,label TEXT,kind TEXT,x REAL,y REAL);');
    const existing = this.layout.prepare('SELECT id,slot,x,y FROM document_positions').all();
    const positions = new Map(existing.map(row => [String(row.id), row]));
    let nextSlot = existing.reduce((max, row) => Math.max(max, Number(row.slot) + 1), 0);
    const insert = this.layout.prepare('INSERT INTO document_positions(id,slot,x,y) VALUES(?,?,?,?)');
    const entityHomes = new Map<string, { label: string; type: string; x: number; y: number; count: number; groups: Map<string, number> }>();
    this.documents.clear();
    this.entities.clear();
    this.childPositions.clear();
    this.layout.exec('BEGIN');
    try {
      const rows = this.source.prepare(`SELECT d.id,d.title,(SELECT json_group_array(json_object('id',json_extract(e.value,'$.id'),'label',json_extract(e.value,'$.label'),'type',json_extract(e.value,'$.type'))) FROM json_each(d.metadata_json,'$.entities') e) AS entities_json FROM documents d ORDER BY d.id`).all();
      for (const row of rows) {
        const id = String(row.id);
        let position = positions.get(id);
        if (!position) {
          const slot = nextSlot++;
          position = { id, slot, x: (slot % COLUMNS) * CELL, y: Math.floor(slot / COLUMNS) * CELL };
          insert.run(id, slot, Number(position.x), Number(position.y));
        }
        const document = { id, title: String(row.title), slot: Number(position.slot), x: Number(position.x), y: Number(position.y) };
        this.documents.set(id, document);
        const terms = JSON.parse(String(row.entities_json || '[]')) as Pick<Entity, 'id' | 'label' | 'type'>[];
        for (const entity of terms) {
          const home = entityHomes.get(entity.id) || { label: entity.label, type: entity.type, x: 0, y: 0, count: 0, groups: new Map<string, number>() };
          home.x += document.x + CELL / 2;
          home.y += document.y + CELL / 2;
          home.count++;
          const groupId = this.groupId(document);
          home.groups.set(groupId, (home.groups.get(groupId) || 0) + 1);
          entityHomes.set(entity.id, home);
        }
      }
      const entityInsert = this.layout.prepare('INSERT OR IGNORE INTO entity_positions(id,label,kind,x,y) VALUES(?,?,?,?,?)');
      let index = 0;
      for (const [id, entity] of entityHomes) {
        const angle = index++ * 2.399963;
        entityInsert.run(id, entity.label, entity.type, entity.x / entity.count + Math.cos(angle) * 80, entity.y / entity.count + Math.sin(angle) * 80);
      }
      this.layout.exec('COMMIT');
      for (const row of this.layout.prepare('SELECT * FROM entity_positions').all()) {
        this.entities.set(String(row.id), { id: String(row.id), type: 'entity', label: String(row.label), entityType: String(row.kind), x: Number(row.x), y: Number(row.y), radius: 8, count: entityHomes.get(String(row.id))?.count || 0 });
      }
      const groupEdges = new Map<string, MapEdge>();
      for (const [entityId, term] of [...entityHomes].sort((a, b) => b[1].groups.size - a[1].groups.size)) {
        const groups = [...term.groups.keys()].sort((a, b) => {
          const [, ax, ay] = a.split(':').map(Number);
          const [, bx, by] = b.split(':').map(Number);
          return ay * COLUMNS + ax - (by * COLUMNS + bx);
        });
        for (let index = 1; index < groups.length; index++) {
          const source = groups[index - 1];
          const target = groups[index];
          const id = `${source}|SHARES_TERM|${target}`;
          const previous = groupEdges.get(id);
          if (previous) {
            previous.count = Number(previous.count) + 1;
            previous.sharedTermCount = previous.count;
            if (previous.viaEntityIds!.length < 6) { previous.viaEntityIds!.push(entityId); previous.labels!.push(term.label); }
          } else if (groupEdges.size < 200) {
            groupEdges.set(id, { id, source, target, type: 'SHARES_TERM', derived: true, viaEntityIds: [entityId], labels: [term.label], count: 1, sharedTermCount: 1, meaning: 'At least one source in each neighborhood mentions the same dictionary term. This aggregated link does not connect every document or assert a scientific relationship.', membershipSource: 'source-ledger' });
          }
        }
      }
      this.groupEdges = [...groupEdges.values()];
      this.initialized = true;
      logger.info('MapService', 'Stable source map initialized', { documents: this.documents.size, entities: this.entities.size });
    } catch (error) { this.layout.exec('ROLLBACK'); throw error; }
  }

  private documentNode(document: LayoutDocument): MapNode {
    return { id: document.id, type: 'document', label: short(document.title), preview: document.title, documentId: document.id, x: document.x + CELL / 2, y: document.y + 38, radius: 12 };
  }

  private groupId(document: LayoutDocument) {
    return `map-group:${Math.floor((document.slot % COLUMNS) / GROUP)}:${Math.floor(Math.floor(document.slot / COLUMNS) / GROUP)}`;
  }

  private childNode(id: string, documentId: string, sectionId?: string): MapNode {
    const document = this.documents.get(documentId);
    if (!document) throw new AppError('Map document not found', 404, true);
    const position = this.childPosition(id, document);
    if (sectionId) {
      const row = this.source!.prepare('SELECT payload FROM chunks WHERE id=?').get(id);
      if (!row) throw new AppError('Chunk not found', 404, true);
      const chunk = JSON.parse(String(row.payload)) as Chunk;
      return { id, type: 'chunk', label: short(chunk.text, 52), preview: short(chunk.text, 220), documentId, sectionId, chunkId: id, ...position, radius: 4, ordinal: chunk.ordinal, startOffset: chunk.startOffset, endOffset: chunk.endOffset };
    }
    const row = this.source!.prepare('SELECT title,metadata_json FROM sections WHERE id=?').get(id);
    if (!row) throw new AppError('Section not found', 404, true);
    return { id, type: 'section', label: String(row.title), preview: String(row.title), documentId, sectionId: id, ...position, radius: 6 };
  }

  private childPosition(id: string, document: LayoutDocument) {
    let positions = this.childPositions.get(document.id);
    if (!positions) {
      positions = new Map();
      const sections = this.source!.prepare('SELECT id FROM sections WHERE document_id=? ORDER BY start_offset,id').all(document.id);
      const chunks = this.source!.prepare('SELECT id,section_id FROM chunks WHERE document_id=? ORDER BY start_offset,id').all(document.id);
      const children = new Map<string, string[]>();
      for (const chunk of chunks) {
        const key = String(chunk.section_id);
        const entries = children.get(key) || [];
        entries.push(String(chunk.id)); children.set(key, entries);
      }
      const leaves = sections.reduce((count, section) => count + Math.max(1, children.get(String(section.id))?.length || 0), 0);
      const spacing = Math.min(18, 384 / Math.max(1, leaves - 1));
      const startX = document.x + CELL / 2 - (leaves - 1) * spacing / 2;
      let slot = 0;
      for (const section of sections) {
        const entries = children.get(String(section.id)) || [];
        const width = Math.max(1, entries.length);
        positions.set(String(section.id), { x: startX + (slot + (width - 1) / 2) * spacing, y: document.y + 116 });
        entries.forEach((chunkId, index) => positions!.set(chunkId, { x: startX + (slot + index) * spacing, y: document.y + 206 }));
        slot += width;
      }
      this.childPositions.set(document.id, positions);
    }
    return positions.get(id) || { x: document.x + CELL / 2, y: document.y + 206 };
  }

  private groups(): MapNode[] {
    const groups = new Map<string, MapNode>();
    for (const document of this.documents.values()) {
      const gx = Math.floor((document.slot % COLUMNS) / GROUP);
      const gy = Math.floor(Math.floor(document.slot / COLUMNS) / GROUP);
      const id = this.groupId(document);
      const group = groups.get(id) || { id, type: 'group', label: 'Source neighborhood', preview: 'A fixed navigation grouping of documents, not a scientific topic cluster.', x: gx * CELL * GROUP + CELL * GROUP / 2, y: gy * CELL * GROUP + CELL * GROUP / 2, count: 0, radius: 28 };
      group.count = Number(group.count) + 1;
      group.label = `${group.count} documents`;
      groups.set(id, group);
    }
    return [...groups.values()];
  }

  overview() {
    this.initialize();
    const rows = Math.ceil(Math.max(1, ...[...this.documents.values()].map(document => document.slot + 1)) / COLUMNS);
    const bounds = { minX: 0, minY: 0, maxX: COLUMNS * CELL, maxY: rows * CELL };
    return { version: 1, bounds, worldBounds: bounds, groups: this.groups(), edges: this.groupEdges, source: 'source-ledger', counts: corpusService.counts(), layout: { cellSize: CELL, groupSize: GROUP, columns: COLUMNS, coordinateMeaning: 'Fixed navigation grouping. Distance does not imply scientific similarity.' } };
  }

  locate(id: string) {
    this.initialize();
    let node: MapNode | undefined;
    if (id.startsWith('map-group:')) node = this.groups().find(group => group.id === id);
    else if (this.documents.has(id)) node = this.documentNode(this.documents.get(id)!);
    else if (this.entities.has(id)) node = this.entities.get(id);
    else {
      const chunk = this.source!.prepare('SELECT document_id,section_id FROM chunks WHERE id=?').get(id);
      if (chunk) node = this.childNode(id, String(chunk.document_id), String(chunk.section_id));
      else {
        const section = this.source!.prepare('SELECT document_id FROM sections WHERE id=?').get(id);
        if (section) node = this.childNode(id, String(section.document_id));
      }
    }
    if (!node) throw new AppError('Source map node not found', 404, true);
    return { node, zoom: node.type === 'group' ? 0.16 : node.type === 'document' ? 1.2 : 2.5, documentId: node.documentId, sectionId: node.sectionId, chunkId: node.chunkId };
  }

  async view(bounds: MapBounds, zoom: number, requestedLimit = 800) {
    this.initialize();
    const limit = Math.max(50, Math.min(800, Math.floor(requestedLimit)));
    const level = zoom < 0.08 ? 'groups' : zoom < 0.45 ? 'documents' : 'detail';
    const inside = (node: { x: number; y: number }, margin = 0) => node.x >= bounds.minX - margin && node.x <= bounds.maxX + margin && node.y >= bounds.minY - margin && node.y <= bounds.maxY + margin;
    if (level === 'groups') {
      const nodes = this.groups().filter(node => inside(node, CELL * GROUP / 2));
      const ids = new Set(nodes.map(node => node.id));
      return { nodes, edges: this.groupEdges.filter(edge => ids.has(edge.source) && ids.has(edge.target)), level, bounds, truncated: false, source: 'source-ledger', status: 'ready', note: 'Neighborhood links summarize actual dictionary-term memberships from the source ledger. A link does not imply that every document is connected or scientifically related.' };
    }
    const centerX = (bounds.minX + bounds.maxX) / 2;
    const centerY = (bounds.minY + bounds.maxY) / 2;
    const candidates = [...this.documents.values()].filter(document => document.x <= bounds.maxX + CELL && document.x + CELL >= bounds.minX - CELL && document.y <= bounds.maxY + CELL && document.y + CELL >= bounds.minY - CELL).sort((a, b) => Math.hypot(a.x + CELL / 2 - centerX, a.y + CELL / 2 - centerY) - Math.hypot(b.x + CELL / 2 - centerX, b.y + CELL / 2 - centerY));
    const chosen = candidates.slice(0, level === 'detail' ? 12 : 220);
    const nodes = new Map<string, MapNode>();
    const edges = new Map<string, MapEdge>();
    const addEdge = (source: string, target: string, type: string, extra: Partial<MapEdge> = {}) => { if (nodes.has(source) && nodes.has(target)) { const id = `${source}|${type}|${target}`; edges.set(id, { id, source, target, type, ...extra }); } };
    let truncated = candidates.length > chosen.length;
    for (const document of chosen) {
      if (nodes.size >= limit - 1) { truncated = true; break; }
      nodes.set(document.id, this.documentNode(document));
      if (level !== 'detail') continue;
      const sections = this.source!.prepare('SELECT id FROM sections WHERE document_id=? ORDER BY start_offset,id').all(document.id);
      for (const section of sections) {
        const node = this.childNode(String(section.id), document.id);
        if (inside(node, 90) && nodes.size < limit - 40) { nodes.set(node.id, node); addEdge(document.id, node.id, 'HAS_SECTION'); }
      }
      const chunks = this.source!.prepare('SELECT id,section_id FROM chunks WHERE document_id=? ORDER BY start_offset,id').all(document.id);
      for (const chunk of chunks) {
        const node = this.childNode(String(chunk.id), document.id, String(chunk.section_id));
        if (!inside(node, 90)) continue;
        if (nodes.size >= limit - 40) { truncated = true; break; }
        nodes.set(node.id, node);
        if (!nodes.has(node.sectionId!)) { const section = this.childNode(node.sectionId!, document.id); nodes.set(section.id, section); addEdge(document.id, section.id, 'HAS_SECTION'); }
        addEdge(node.sectionId!, node.id, 'HAS_CHUNK');
      }
    }
    let source = 'source-ledger';
    let status = 'ready';
    let note = 'Structure is read from the parsed source ledger. Shared mentions are dictionary matches, not verified scientific relationships.';
    if (chosen.length) {
      try {
        const rows = await graphService.query(`MATCH (d:Document)-[:HAS_SECTION]->(:Section)-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(e:Entity) WHERE d.id IN ${quote(chosen.map(document => document.id))} RETURN DISTINCT d.id,e.id,e.label,e.kind LIMIT 6000`);
        const mentions = new Map<string, { label: string; documents: string[] }>();
        for (const row of rows) {
          const term = mentions.get(String(row[1])) || { label: String(row[2]), documents: [] };
          term.documents.push(String(row[0]));
          mentions.set(String(row[1]), term);
        }
        for (const [entityId, term] of [...mentions].sort((a, b) => a[1].documents.length - b[1].documents.length)) {
          const ids = [...new Set(term.documents)].sort((a, b) => this.documents.get(a)!.slot - this.documents.get(b)!.slot);
          for (let index = 1; index < ids.length; index++) {
            const sourceId = ids[index - 1];
            const targetId = ids[index];
            const edgeId = `${sourceId}|SHARES_TERM|${targetId}`;
            const previous = edges.get(edgeId);
            if (previous) { if (previous.viaEntityIds!.length < 6) { previous.viaEntityIds!.push(entityId); previous.labels!.push(term.label); } }
            else if (edges.size < 1000) addEdge(sourceId, targetId, 'SHARES_TERM', { derived: true, viaEntityIds: [entityId], labels: [term.label], meaning: 'Both documents contain a chunk mentioning this dictionary term. This is not a scientific claim.' });
          }
          const entity = this.entities.get(entityId);
          if (entity && inside(entity, 90) && nodes.size < limit) nodes.set(entity.id, entity);
        }
        if (level === 'detail') {
          const nodeIds = [...nodes.keys()];
          const relations = (await Promise.all(['Document', 'Section', 'Chunk'].map(label => graphService.query(`MATCH (a:${label})-[r]->(b) WHERE a.id IN ${quote(nodeIds)} AND b.id IN ${quote(nodeIds)} RETURN a.id,b.id,type(r) LIMIT 1500`)))).flat();
          for (const edge of [...edges.values()]) if (!edge.derived) edges.delete(edge.id);
          for (const row of relations) addEdge(String(row[0]), String(row[1]), String(row[2]));
          if (relations.length >= 1500) truncated = true;
        }
        source = 'falkordb';
      } catch (error) {
        status = 'graph unavailable';
        note += ' FalkorDB relationships could not be loaded; no cross-document links have been invented.';
        logger.warn('MapService', 'Viewport graph relationships unavailable', { error: String(error) });
      }
    }
    return { nodes: [...nodes.values()], edges: [...edges.values()].slice(0, 1500), level, bounds, truncated, source, status, note };
  }

  async node(id: string) {
    const location = this.locate(id);
    const node = location.node;
    const descriptions = { group: 'A fixed spatial group of documents for navigation; not a topic cluster. Its links summarize terms mentioned by at least one document in each connected group, not relationships between every paper.', document: 'One parsed source article. Sections and chunks belong to this source.', section: 'A heading-delimited region of the original document.', chunk: 'A bounded text segment used for retrieval, preserving exact source offsets.', entity: 'A dictionary term actually mentioned in one or more source chunks. A shared mention is not a verified scientific relationship.' };
    let content: unknown;
    if (node.type === 'group') {
      const connections = this.groupEdges.filter(edge => edge.source === id || edge.target === id);
      content = { documentCount: node.count, linkedGroupCount: connections.length, sampleSharedTerms: [...new Set(connections.flatMap(edge => edge.labels || []))].slice(0, 12), source: 'source-ledger', connectionMeaning: 'At least one document on each side mentions a shared dictionary term. Not every paper is linked, and no scientific claim is asserted.' };
    }
    if (node.type === 'chunk') content = corpusService.chunk(id)?.chunk;
    if (node.type === 'document') {
      const row = this.source!.prepare('SELECT metadata_json FROM documents WHERE id=?').get(id);
      const { entities: _entities, ...metadata } = JSON.parse(String(row?.metadata_json || '{}'));
      content = metadata;
    }
    if (node.type === 'section') content = this.source!.prepare('SELECT title,start_offset,end_offset FROM sections WHERE id=?').get(id);
    let neighbors: unknown[] = [];
    let source = 'source-ledger';
    if (node.type !== 'group') {
      try {
        const label = { document: 'Document', section: 'Section', chunk: 'Chunk', entity: 'Entity' }[node.type];
        const rows = await graphService.query(`MATCH (a:${label})-[r]-(b) WHERE a.id=${quote(id)} RETURN DISTINCT b.id,labels(b),type(r),startNode(r).id,endNode(r).id LIMIT 31`);
        neighbors = rows.slice(0, 30).map(row => ({ id: row[0], labels: row[1], relationship: row[2], source: row[3], target: row[4] }));
        source = 'falkordb';
        return { ...location, description: descriptions[node.type], content, neighbors, neighborsTruncated: rows.length > 30, source };
      } catch { source = 'source-ledger'; }
    }
    return { ...location, description: descriptions[node.type], content, neighbors, source };
  }
}

export const mapService = new MapService();
