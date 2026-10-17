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
const hash = (value: string) => { let result = 2166136261; for (const char of value) result = Math.imul(result ^ char.charCodeAt(0), 16777619); return result >>> 0; };
const quote = (value: unknown) => JSON.stringify(value);
const short = (value: string, length = 70) => value.length > length ? `${value.slice(0, length).trim()}…` : value;
export type MapMode = 'network' | 'grouped';
type LayoutDocument = { id: string; title: string; slot: number; x: number; y: number };

class MapService {
  private source?: DatabaseSync;
  private layout?: DatabaseSync;
  private initialized = false;
  private documents = new Map<string, LayoutDocument>();
  private entities = new Map<string, MapNode>();
  private groupedDocuments = new Map<string, LayoutDocument>();
  private groupedEntities = new Map<string, MapNode>();
  private groupedEdges: MapEdge[] = [];
  private groupEdges: MapEdge[] = [];
  private childPositions = new Map<string, Map<string, { x: number; y: number }>>();

  private initialize() {
    if (this.initialized && Number(this.source!.prepare('SELECT count(*) AS count FROM documents').get()?.count) === this.documents.size) return;
    const target = path.join(config.dataDir, 'corpus.sqlite3');
    if (!fs.existsSync(target)) throw new AppError('Source collection is not available yet', 503, true);
    this.source ||= new DatabaseSync(target, { readOnly: true });
    this.layout ||= new DatabaseSync(path.join(config.dataDir, 'graph-layout.sqlite'));
    this.layout.exec('PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS network_document_positions(id TEXT PRIMARY KEY,slot INTEGER UNIQUE,x REAL,y REAL); CREATE TABLE IF NOT EXISTS network_entity_positions(id TEXT PRIMARY KEY,label TEXT,kind TEXT,x REAL,y REAL);');
    const rows = this.source.prepare(`SELECT d.id,d.title,(SELECT json_group_array(json_object('id',json_extract(e.value,'$.id'),'label',json_extract(e.value,'$.label'),'type',json_extract(e.value,'$.type'))) FROM json_each(d.metadata_json,'$.entities') e) AS entities_json FROM documents d ORDER BY d.id`).all();
    const existing = new Map(this.layout.prepare('SELECT id,slot,x,y FROM network_document_positions').all().map(row => [String(row.id), row]));
    const terms = new Map<string, { label: string; type: string; members: number[] }>();
    const memberships = rows.map((row, index) => {
      const entities = JSON.parse(String(row.entities_json || '[]')) as Pick<Entity, 'id' | 'label' | 'type'>[];
      for (const entity of entities) {
        const term = terms.get(entity.id) || { label: entity.label, type: entity.type, members: [] };
        term.members.push(index); terms.set(entity.id, term);
      }
      return entities.map(entity => entity.id);
    });
    const links = new Map<string, MapEdge>();
    for (const [entityId, term] of terms) {
      const ordered = [...term.members].sort((a, b) => hash(String(rows[a].id) + entityId) - hash(String(rows[b].id) + entityId));
      for (let i = 1; i < ordered.length; i++) {
        const pair = [String(rows[ordered[i - 1]].id), String(rows[ordered[i]].id)].sort();
        const id = `${pair[0]}|SHARES_TERM|${pair[1]}`;
        const previous = links.get(id);
        if (previous) { previous.viaEntityIds!.push(entityId); previous.labels!.push(term.label); previous.count = Number(previous.count) + 1; }
        else links.set(id, { id, source: pair[0], target: pair[1], type: 'SHARES_TERM', derived: true, viaEntityIds: [entityId], labels: [term.label], count: 1, meaning: 'Both documents contain chunks mentioning this dictionary term. This sparse navigation link is not a scientific relationship.', membershipSource: 'source-ledger' });
      }
    }
    const anchors = new Map([...terms].sort((a, b) => a[0].localeCompare(b[0])).map(([id], index) => {
      const angle = index * 2.399963229728653;
      const radius = Math.sqrt(index + 1) * 2300;
      return [id, { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius }];
    }));
    const points = rows.map((row, index) => {
      const saved = existing.get(String(row.id));
      if (saved) return { x: Number(saved.x), y: Number(saved.y), fixed: true };
      const ids = memberships[index];
      let x = 0, y = 0, weight = 0;
      for (const id of ids) {
        const importance = 1 / Math.sqrt(terms.get(id)!.members.length);
        x += anchors.get(id)!.x * importance; y += anchors.get(id)!.y * importance; weight += importance;
      }
      const angle = hash(String(row.id)) / 4294967296 * Math.PI * 2;
      const radius = 1600 + (hash(String(row.id) + ':radius') % 4200);
      return { x: (weight ? x / weight : 0) + Math.cos(angle) * radius, y: (weight ? y / weight : 0) + Math.sin(angle) * radius, fixed: false };
    });
    if (points.some(point => !point.fixed)) {
      const indexById = new Map(rows.map((row, index) => [String(row.id), index]));
      const springs = [...links.values()].filter(edge => edge.viaEntityIds!.some(id => terms.get(id)!.members.length < rows.length * 0.3)).map(edge => ({ a: indexById.get(edge.source)!, b: indexById.get(edge.target)!, weight: edge.viaEntityIds!.reduce((sum, id) => sum + 1 / Math.sqrt(terms.get(id)!.members.length), 0) }));
      for (let iteration = 0; iteration < 100; iteration++) {
        const forces = points.map(() => ({ x: 0, y: 0 }));
        for (const spring of springs) {
          const a = points[spring.a], b = points[spring.b];
          const dx = b.x - a.x, dy = b.y - a.y, distance = Math.max(1, Math.hypot(dx, dy));
          const force = Math.min(100, (distance - 950) * spring.weight * 0.12);
          forces[spring.a].x += dx / distance * force; forces[spring.a].y += dy / distance * force;
          forces[spring.b].x -= dx / distance * force; forces[spring.b].y -= dy / distance * force;
        }
        const cells = new Map<string, number[]>();
        points.forEach((point, index) => { const key = `${Math.floor(point.x / 620)},${Math.floor(point.y / 620)}`; const cell = cells.get(key) || []; cell.push(index); cells.set(key, cell); });
        points.forEach((point, index) => {
          if (point.fixed) return;
          const cx = Math.floor(point.x / 620), cy = Math.floor(point.y / 620);
          for (let x = cx - 1; x <= cx + 1; x++) for (let y = cy - 1; y <= cy + 1; y++) for (const other of cells.get(`${x},${y}`) || []) {
            if (other === index) continue;
            let dx = point.x - points[other].x, dy = point.y - points[other].y;
            let distance = Math.hypot(dx, dy);
            if (distance < 1) { dx = Math.cos(index); dy = Math.sin(index); distance = 1; }
            if (distance < 620) { const force = (620 - distance) * 0.48; forces[index].x += dx / distance * force; forces[index].y += dy / distance * force; }
          }
          const force = forces[index]; const length = Math.max(1, Math.hypot(force.x, force.y)); const cap = Math.min(180, length);
          point.x += force.x / length * cap; point.y += force.y / length * cap;
        });
      }
    }
    this.documents.clear(); this.entities.clear(); this.childPositions.clear();
    const insert = this.layout.prepare('INSERT OR IGNORE INTO network_document_positions(id,slot,x,y) VALUES(?,?,?,?)');
    this.layout.exec('BEGIN');
    try {
      let nextSlot = Math.max(0, ...[...existing.values()].map(row => Number(row.slot) + 1));
      rows.forEach((row, index) => {
        const id = String(row.id), saved = existing.get(id), point = points[index];
        const document = { id, title: String(row.title), slot: saved ? Number(saved.slot) : nextSlot++, x: point.x, y: point.y };
        insert.run(id, document.slot, document.x, document.y); this.documents.set(id, document);
      });
      const entityInsert = this.layout.prepare('INSERT OR IGNORE INTO network_entity_positions(id,label,kind,x,y) VALUES(?,?,?,?,?)');
      for (const [id, term] of terms) {
        const x = term.members.reduce((sum, index) => sum + points[index].x + CELL / 2, 0) / term.members.length;
        const y = term.members.reduce((sum, index) => sum + points[index].y + 280, 0) / term.members.length;
        entityInsert.run(id, term.label, term.type, x, y);
      }
      this.layout.exec('COMMIT');
    } catch (error) { this.layout.exec('ROLLBACK'); throw error; }
    for (const row of this.layout.prepare('SELECT * FROM network_entity_positions').all()) this.entities.set(String(row.id), { id: String(row.id), type: 'entity', label: String(row.label), entityType: String(row.kind), x: Number(row.x), y: Number(row.y), radius: 8, count: terms.get(String(row.id))?.members.length || 0 });
    const nearbyLinks = new Map<string, MapEdge>();
    for (const [entityId, term] of terms) {
      const members = term.members.map(index => this.documents.get(String(rows[index].id))!).sort((a, b) => a.x - b.x || a.y - b.y);
      members.forEach((document, index) => {
        const nearby = members.slice(Math.max(0, index - 18), Math.min(members.length, index + 19)).filter(other => other.id !== document.id).sort((a, b) => Math.hypot(a.x - document.x, a.y - document.y) - Math.hypot(b.x - document.x, b.y - document.y)).slice(0, 2);
        for (const other of nearby) {
          const pair = [document.id, other.id].sort(), id = `${pair[0]}|SHARES_TERM|${pair[1]}`;
          const previous = nearbyLinks.get(id);
          if (previous) { if (!previous.viaEntityIds!.includes(entityId)) { previous.viaEntityIds!.push(entityId); previous.labels!.push(term.label); previous.count = Number(previous.count) + 1; } }
          else nearbyLinks.set(id, { id, source: pair[0], target: pair[1], type: 'SHARES_TERM', derived: true, viaEntityIds: [entityId], labels: [term.label], count: 1, meaning: 'Both documents contain chunks mentioning this dictionary term. This sparse navigation link is not a scientific relationship.', membershipSource: 'source-ledger' });
        }
      });
    }
    const length = (edge: MapEdge) => { const a = this.documents.get(edge.source)!, b = this.documents.get(edge.target)!; return Math.hypot(a.x - b.x, a.y - b.y); };
    const orderedEdges = [...nearbyLinks.values()].sort((a, b) => length(a) - length(b) || Number(b.count) - Number(a.count));
    const degree = new Map<string, number>();
    this.groupEdges = orderedEdges.filter(edge => {
      const a = degree.get(edge.source) || 0, b = degree.get(edge.target) || 0;
      if (a >= 3 || b >= 3) return false;
      degree.set(edge.source, a + 1); degree.set(edge.target, b + 1); return true;
    }).slice(0, 9000);
    this.initializeGrouped(rows);
    this.initialized = true;
    logger.info('MapService', 'Persistent organic source network initialized', { documents: this.documents.size, entities: this.entities.size, overviewLinks: this.groupEdges.length });
  }

  private initializeGrouped(rows: Record<string, unknown>[]) {
    this.layout!.exec('CREATE TABLE IF NOT EXISTS document_positions(id TEXT PRIMARY KEY,slot INTEGER UNIQUE,x REAL,y REAL); CREATE TABLE IF NOT EXISTS entity_positions(id TEXT PRIMARY KEY,label TEXT,kind TEXT,x REAL,y REAL);');
    const existing = this.layout!.prepare('SELECT id,slot,x,y FROM document_positions').all();
    const positions = new Map(existing.map(row => [String(row.id), row]));
    let nextSlot = existing.reduce((max, row) => Math.max(max, Number(row.slot) + 1), 0);
    const insert = this.layout!.prepare('INSERT INTO document_positions(id,slot,x,y) VALUES(?,?,?,?)');
    const homes = new Map<string, { label: string; type: string; x: number; y: number; count: number; groups: Set<string> }>();
    this.groupedDocuments.clear(); this.groupedEntities.clear();
    this.layout!.exec('BEGIN');
    try {
      for (const row of rows) {
        const id = String(row.id);
        let position = positions.get(id);
        if (!position) {
          const slot = nextSlot++;
          position = { id, slot, x: (slot % 80) * CELL, y: Math.floor(slot / 80) * CELL };
          insert.run(id, slot, Number(position.x), Number(position.y));
        }
        const document = { id, title: String(row.title), slot: Number(position.slot), x: Number(position.x), y: Number(position.y) };
        this.groupedDocuments.set(id, document);
        for (const entity of JSON.parse(String(row.entities_json || '[]')) as Pick<Entity, 'id' | 'label' | 'type'>[]) {
          const home = homes.get(entity.id) || { label: entity.label, type: entity.type, x: 0, y: 0, count: 0, groups: new Set<string>() };
          home.x += document.x + CELL / 2; home.y += document.y + CELL / 2; home.count++;
          home.groups.add(this.groupId(document)); homes.set(entity.id, home);
        }
      }
      const entityInsert = this.layout!.prepare('INSERT OR IGNORE INTO entity_positions(id,label,kind,x,y) VALUES(?,?,?,?,?)');
      let index = 0;
      for (const [id, home] of homes) { const angle = index++ * 2.399963; entityInsert.run(id, home.label, home.type, home.x / home.count + Math.cos(angle) * 80, home.y / home.count + Math.sin(angle) * 80); }
      this.layout!.exec('COMMIT');
    } catch (error) { this.layout!.exec('ROLLBACK'); throw error; }
    for (const row of this.layout!.prepare('SELECT * FROM entity_positions').all()) this.groupedEntities.set(String(row.id), { id: String(row.id), type: 'entity', label: String(row.label), entityType: String(row.kind), x: Number(row.x), y: Number(row.y), radius: 8, count: homes.get(String(row.id))?.count || 0 });
    const edges = new Map<string, MapEdge>();
    for (const [entityId, home] of homes) {
      const groups = [...home.groups].sort((a, b) => { const [, ax, ay] = a.split(':').map(Number), [, bx, by] = b.split(':').map(Number); return ay * 80 + ax - (by * 80 + bx); });
      for (let index = 1; index < groups.length; index++) {
        const source = groups[index - 1], target = groups[index], id = `${source}|SHARES_TERM|${target}`, previous = edges.get(id);
        if (previous) { previous.count = Number(previous.count) + 1; if (previous.viaEntityIds!.length < 6) { previous.viaEntityIds!.push(entityId); previous.labels!.push(home.label); } }
        else if (edges.size < 200) edges.set(id, { id, source, target, type: 'SHARES_TERM', derived: true, viaEntityIds: [entityId], labels: [home.label], count: 1, meaning: 'At least one document in each navigation group mentions the same dictionary term. This does not connect every document or assert a scientific relationship.', membershipSource: 'source-ledger' });
      }
    }
    this.groupedEdges = [...edges.values()];
  }

  private documentsFor(mode: MapMode) { return mode === 'grouped' ? this.groupedDocuments : this.documents; }
  private entitiesFor(mode: MapMode) { return mode === 'grouped' ? this.groupedEntities : this.entities; }
  private groupId(document: LayoutDocument) { return `map-group:${Math.floor((document.slot % 80) / 8)}:${Math.floor(Math.floor(document.slot / 80) / 8)}`; }
  private groups(): MapNode[] {
    const groups = new Map<string, MapNode>();
    for (const document of this.groupedDocuments.values()) {
      const id = this.groupId(document), gx = Math.floor((document.slot % 80) / 8), gy = Math.floor(Math.floor(document.slot / 80) / 8);
      const group = groups.get(id) || { id, type: 'group', label: 'Source neighborhood', preview: 'Fixed navigation grouping, not a scientific topic cluster.', x: gx * CELL * 8 + CELL * 4, y: gy * CELL * 8 + CELL * 4, count: 0, radius: 28 };
      group.count = Number(group.count) + 1; group.label = `${group.count} documents`; groups.set(id, group);
    }
    return [...groups.values()];
  }

  private documentNode(document: LayoutDocument): MapNode {
    return { id: document.id, type: 'document', label: short(document.title), preview: document.title, documentId: document.id, x: document.x + CELL / 2, y: document.y + 38, radius: 12 };
  }

  private childNode(id: string, documentId: string, sectionId?: string, mode: MapMode = 'network'): MapNode {
    const document = this.documentsFor(mode).get(documentId);
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
    const cacheKey = `${document.id}:${document.x}:${document.y}`;
    let positions = this.childPositions.get(cacheKey);
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
      this.childPositions.set(cacheKey, positions);
    }
    return positions.get(id) || { x: document.x + CELL / 2, y: document.y + 206 };
  }

  overview(mode: MapMode = 'network') {
    this.initialize();
    if (mode === 'grouped') {
      const rows = Math.ceil(Math.max(1, ...[...this.groupedDocuments.values()].map(document => document.slot + 1)) / 80);
      const bounds = { minX: 0, minY: 0, maxX: 80 * CELL, maxY: rows * CELL };
      return { version: 1, mode, bounds, worldBounds: bounds, nodes: this.groups(), groups: this.groups(), edges: this.groupedEdges, source: 'source-ledger', counts: corpusService.counts(), layout: { cellSize: CELL, groupSize: 8, columns: 80, kind: 'persistent-grouped-map', coordinateMeaning: 'Fixed navigation grouping. Distance does not imply scientific similarity.' } };
    }
    const documents = [...this.documents.values()];
    const bounds = { minX: Math.min(...documents.map(document => document.x)) - CELL, minY: Math.min(...documents.map(document => document.y)) - CELL, maxX: Math.max(...documents.map(document => document.x)) + CELL * 2, maxY: Math.max(...documents.map(document => document.y)) + CELL * 2 };
    return { version: 2, bounds, worldBounds: bounds, nodes: documents.map(document => this.documentNode(document)), groups: [], edges: this.groupEdges, source: 'source-ledger', counts: corpusService.counts(), layout: { cellSize: CELL, kind: 'persistent-organic-network', coordinateMeaning: 'A stable navigation layout influenced by shared dictionary terms. Proximity does not establish scientific similarity; overview links are a sparse selection of real shared-mention paths.' } };
  }

  locate(id: string, mode: MapMode = 'network') {
    this.initialize();
    let node: MapNode | undefined;
    if (mode === 'grouped' && id.startsWith('map-group:')) node = this.groups().find(group => group.id === id);
    else if (this.documentsFor(mode).has(id)) node = this.documentNode(this.documentsFor(mode).get(id)!);
    else if (this.entitiesFor(mode).has(id)) node = this.entitiesFor(mode).get(id);
    else {
      const chunk = this.source!.prepare('SELECT document_id,section_id FROM chunks WHERE id=?').get(id);
      if (chunk) node = this.childNode(id, String(chunk.document_id), String(chunk.section_id), mode);
      else {
        const section = this.source!.prepare('SELECT document_id FROM sections WHERE id=?').get(id);
        if (section) node = this.childNode(id, String(section.document_id), undefined, mode);
      }
    }
    if (!node) throw new AppError('Source map node not found', 404, true);
    return { node, zoom: node.type === 'group' ? 0.16 : node.type === 'document' ? 1.2 : 2.5, documentId: node.documentId, sectionId: node.sectionId, chunkId: node.chunkId };
  }

  async view(bounds: MapBounds, zoom: number, requestedLimit = 800, mode: MapMode = 'network') {
    this.initialize();
    const limit = Math.max(50, Math.min(800, Math.floor(requestedLimit)));
    const level = zoom < 0.08 ? 'overview' : zoom < 0.45 ? 'documents' : 'detail';
    const inside = (node: { x: number; y: number }, margin = 0) => node.x >= bounds.minX - margin && node.x <= bounds.maxX + margin && node.y >= bounds.minY - margin && node.y <= bounds.maxY + margin;
    if (level === 'overview' && mode === 'grouped') {
      const nodes = this.groups().filter(node => inside(node, CELL * 4));
      const ids = new Set(nodes.map(node => node.id));
      return { nodes, edges: this.groupedEdges.filter(edge => ids.has(edge.source) && ids.has(edge.target)), level: 'groups', bounds, truncated: false, source: 'source-ledger', status: 'ready', note: 'Fixed document navigation groups. Links summarize shared dictionary mentions, not scientific relationships.' };
    }
    if (level === 'overview') {
      const nodes = [...this.documentsFor(mode).values()].map(document => this.documentNode(document)).filter(node => inside(node, CELL));
      const ids = new Set(nodes.map(node => node.id));
      return { nodes, edges: this.groupEdges.filter(edge => ids.has(edge.source) && ids.has(edge.target)), level, bounds, truncated: false, source: 'source-ledger', status: 'ready', note: 'An organic document network with a sparse selection of actual shared dictionary-term paths. A shared mention does not establish a scientific relationship.' };
    }
    const centerX = (bounds.minX + bounds.maxX) / 2;
    const centerY = (bounds.minY + bounds.maxY) / 2;
    const candidates = [...this.documentsFor(mode).values()].filter(document => document.x <= bounds.maxX + CELL && document.x + CELL >= bounds.minX - CELL && document.y <= bounds.maxY + CELL && document.y + CELL >= bounds.minY - CELL).sort((a, b) => Math.hypot(a.x + CELL / 2 - centerX, a.y + CELL / 2 - centerY) - Math.hypot(b.x + CELL / 2 - centerX, b.y + CELL / 2 - centerY));
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
        const node = this.childNode(String(section.id), document.id, undefined, mode);
        if (inside(node, 90) && nodes.size < limit - 40) { nodes.set(node.id, node); addEdge(document.id, node.id, 'HAS_SECTION'); }
      }
      const chunks = this.source!.prepare('SELECT id,section_id FROM chunks WHERE document_id=? ORDER BY start_offset,id').all(document.id);
      for (const chunk of chunks) {
        const node = this.childNode(String(chunk.id), document.id, String(chunk.section_id), mode);
        if (!inside(node, 90)) continue;
        if (nodes.size >= limit - 40) { truncated = true; break; }
        nodes.set(node.id, node);
        if (!nodes.has(node.sectionId!)) { const section = this.childNode(node.sectionId!, document.id, undefined, mode); nodes.set(section.id, section); addEdge(document.id, section.id, 'HAS_SECTION'); }
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
          const ids = [...new Set(term.documents)].sort((a, b) => this.documentsFor(mode).get(a)!.slot - this.documentsFor(mode).get(b)!.slot);
          for (let index = 1; index < ids.length; index++) {
            const sourceId = ids[index - 1];
            const targetId = ids[index];
            const edgeId = `${sourceId}|SHARES_TERM|${targetId}`;
            const previous = edges.get(edgeId);
            if (previous) { if (previous.viaEntityIds!.length < 6) { previous.viaEntityIds!.push(entityId); previous.labels!.push(term.label); } }
            else if (edges.size < 1000) addEdge(sourceId, targetId, 'SHARES_TERM', { derived: true, viaEntityIds: [entityId], labels: [term.label], meaning: 'Both documents contain a chunk mentioning this dictionary term. This is not a scientific claim.' });
          }
          const entity = this.entitiesFor(mode).get(entityId);
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

  async neighborhood(id: string, mode: MapMode = 'network') {
    this.initialize();
    const focus = this.locate(id, mode).node;
    const nodes = new Map<string, MapNode>();
    const edges = new Map<string, MapEdge>();
    const paths: { sourceChunkId: string; targetChunkId: string; entityId: string; label: string; documentId: string; documentTitle: string }[] = [];
    const addEdge = (source: string, target: string, type: string) => { const edgeId = `${source}|${type}|${target}`; edges.set(edgeId, { id: edgeId, source, target, type }); };
    const addChunk = (chunkId: string) => {
      const chunk = this.locate(chunkId, mode).node;
      if (chunk.type !== 'chunk' || !chunk.documentId || !chunk.sectionId) return;
      nodes.set(chunk.id, chunk);
      const document = this.documentNode(this.documentsFor(mode).get(chunk.documentId)!);
      const section = this.childNode(chunk.sectionId, chunk.documentId, undefined, mode);
      nodes.set(document.id, document); nodes.set(section.id, section);
      addEdge(document.id, section.id, 'HAS_SECTION'); addEdge(section.id, chunk.id, 'HAS_CHUNK');
      return chunk;
    };
    nodes.set(focus.id, focus);
    if (focus.type !== 'chunk') return { nodes: [...nodes.values()], edges: [], paths, truncated: false, note: 'Select a chunk to follow its shared mentions into other source documents.', source: 'source-ledger', status: 'ready', focusId: id };
    addChunk(id);
    try {
      const entityRows = await graphService.query(`MATCH (c:Chunk)-[:MENTIONS]->(e:Entity) WHERE c.id=${quote(id)} RETURN DISTINCT e.id,e.label LIMIT 50`);
      const selected = entityRows.sort((a, b) => Number(this.entitiesFor(mode).get(String(a[0]))?.count || 0) - Number(this.entitiesFor(mode).get(String(b[0]))?.count || 0)).slice(0, 3);
      let truncated = entityRows.length > selected.length;
      const targetDocuments = new Set<string>();
      for (const row of selected) {
        const entityId = String(row[0]);
        const entity = this.entitiesFor(mode).get(entityId);
        if (!entity) continue;
        nodes.set(entityId, entity); addEdge(id, entityId, 'MENTIONS');
        const documents = await graphService.query(`MATCH (c:Chunk)-[:MENTIONS]->(e:Entity) WHERE e.id=${quote(entityId)} AND c.documentId<>${quote(focus.documentId)} RETURN DISTINCT c.documentId LIMIT 4`);
        if (documents.length > 3) truncated = true;
        for (const documentRow of documents) {
          const documentId = String(documentRow[0]);
          if (!this.documentsFor(mode).has(documentId)) continue;
          if (!targetDocuments.has(documentId) && targetDocuments.size >= 3) { truncated = true; continue; }
          targetDocuments.add(documentId);
          const chunks = await graphService.query(`MATCH (c:Chunk)-[:MENTIONS]->(e:Entity) WHERE e.id=${quote(entityId)} AND c.documentId=${quote(documentId)} RETURN DISTINCT c.id LIMIT 3`);
          if (chunks.length > 2) truncated = true;
          for (const chunkRow of chunks.slice(0, 2)) {
            const chunk = addChunk(String(chunkRow[0]));
            if (!chunk) continue;
            addEdge(chunk.id, entityId, 'MENTIONS');
            paths.push({ sourceChunkId: id, targetChunkId: chunk.id, entityId, label: String(row[1]), documentId, documentTitle: this.documentsFor(mode).get(documentId)!.title });
          }
        }
      }
      const adjacent = await graphService.query(`MATCH (a:Chunk)-[r:NEXT_CHUNK]-(b:Chunk) WHERE a.id=${quote(id)} RETURN DISTINCT b.id,startNode(r).id,endNode(r).id LIMIT 4`);
      for (const row of adjacent) { addChunk(String(row[0])); addEdge(String(row[1]), String(row[2]), 'NEXT_CHUNK'); }
      return { nodes: [...nodes.values()], edges: [...edges.values()], paths, truncated, note: 'Shared-mention paths connect real source passages through the same dictionary term. They do not establish agreement, contradiction, or a scientific relationship. Showing up to three terms, three other documents, and two chunks per document per term; positions remain fixed.', source: 'falkordb', status: 'ready', focusId: id };
    } catch (error) {
      logger.warn('MapService', 'Chunk neighborhood unavailable', { error: String(error) });
      return { nodes: [...nodes.values()], edges: [], paths: [], truncated: true, note: 'FalkorDB connection paths are unavailable. No cross-document connections have been inferred.', source: 'source-ledger', status: 'graph unavailable', focusId: id };
    }
  }

  async node(id: string, mode: MapMode = 'network') {
    const location = this.locate(id, mode);
    const node = location.node;
    const descriptions = { group: 'A fixed spatial group of documents for navigation; not a topic cluster. Its links summarize terms mentioned by at least one document in each connected group, not relationships between every paper.', document: 'One parsed source article. Sections and chunks belong to this source.', section: 'A heading-delimited region of the original document.', chunk: 'A bounded text segment used for retrieval, preserving exact source offsets.', entity: 'A dictionary term actually mentioned in one or more source chunks. A shared mention is not a verified scientific relationship.' };
    let content: unknown;
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
