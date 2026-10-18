'use client';

import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, ArrowUpRight, CircleHelp, Focus, List, Loader2, Minus, Network, Plus, Search, X } from 'lucide-react';
import { api } from '@/lib/evidence-types';
import styles from './KnowledgeGraph.module.css';

type Entity = { id: string; type: 'entity'; label: string; entityType: string; x: number; y: number; mentionCount?: number; documentCount?: number; aliases?: string[]; resolutionStatus?: string };
type Relationship = { id: string; source: string; target: string; label: string; confidence?: number | null; traversalStatus?: string; extractionMethod?: string; quote?: string; chunkId?: string; documentId?: string };
type KnowledgeView = { nodes: Entity[]; entityPage?: Entity[]; edges: Relationship[]; status?: string; pagination: { entityTotal: number; connectedEntityTotal?: number | null; entityOffset: number; entityLimit: number; hasMoreEntities: boolean; relationshipTotal: number; relationshipOffset: number; relationshipLimit: number; hasMoreRelationships: boolean } };
type Mention = { id: string; text: string; chunkId: string; chunkText?: string; documentId: string; documentTitle: string; sourceSpans?: unknown[]; extractionMethod?: string; confidence?: number | null };
type Mentions = { entity: Entity; mentions: Mention[]; counts: { documents: number; chunks: number; occurrences: number; occurrenceCountTruncated?: boolean; status?: string }; pagination: { total: number; offset: number; limit: number; hasMore: boolean } };
type Props = { apiRoot: string; refreshToken?: number; expanded?: boolean; focus?: { nodeId: string; nonce: number } | null; trace?: { assertionIds: string[]; nonce: number } | null; onSelect?: (node: Entity) => void; onSource?: (source: { nodeId: string; label?: string }) => void };
type Camera = { x: number; y: number; zoom: number };
const ENTITY_PAGE = 40;
const RELATION_PAGE = 60;
const EMPTY: KnowledgeView = { nodes: [], edges: [], pagination: { entityTotal: 0, entityOffset: 0, entityLimit: 60, hasMoreEntities: false, relationshipTotal: 0, relationshipOffset: 0, relationshipLimit: 100, hasMoreRelationships: false } };
const clip = (value: string, length = 30) => value.length > length ? `${value.slice(0, length - 1)}…` : value;
const human = (value: string) => value.replace(/_/g, ' ');
const native = (edge: Relationship) => edge.traversalStatus === 'source_structured' || /native|stix/.test(edge.extractionMethod || '');
const codebaseAgent = (edge: Relationship) => edge.extractionMethod === 'codebase_graph_builder';
const review = (edge: Relationship) => /review|revoked|deprecated/.test(edge.traversalStatus || '');
const relationshipStatus = (edge: Relationship) => review(edge) ? 'Needs review' : native(edge) ? 'Source-defined relationship' : codebaseAgent(edge) ? 'Codebase agent · unverified' : 'Model extraction · unverified';
const structuredMention = (mention: Mention) => {
  const text = mention.chunkText || mention.text;
  return /^\s*[\[{]/.test(text) || /"(?:type|id|spec_version|source_ref|target_ref|external_references)"\s*:/.test(text) || /^(?:M\d{3,}|[\w-]+--[0-9a-f]{8}-[0-9a-f-]{27,})$/i.test(mention.text.trim());
};
const hue = (value: string) => { let hash = 0; for (const char of value) hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0; return Math.abs(hash) % 5; };
const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });

export function KnowledgeGraph({ apiRoot, refreshToken = 0, expanded = false, focus, trace, onSelect, onSource }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const animation = useRef(0);
  const drag = useRef<{ x: number; y: number; camera: Camera } | null>(null);
  const cameraRef = useRef<Camera>({ x: 0, y: 0, zoom: 1 });
  const id = useId().replace(/:/g, '');
  const [camera, setCamera] = useState<Camera>(cameraRef.current);
  const [size, setSize] = useState({ width: 700, height: 500 });
  const [view, setView] = useState<KnowledgeView>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [relationOffset, setRelationOffset] = useState(0);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Entity | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<Relationship | null>(null);
  const [mentions, setMentions] = useState<Mentions | null>(null);
  const [mentionOffset, setMentionOffset] = useState(0);
  const [mentionLoading, setMentionLoading] = useState(false);
  const [mentionError, setMentionError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [help, setHelp] = useState(false);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [reload, setReload] = useState(0);
  const [detailTab, setDetailTab] = useState<'mentions' | 'relationships'>('mentions');
  const fitPending = useRef(true);
  const previousExpanded = useRef(expanded);
  const externalSelection = useRef<string | null>(null);
  const nodes = useMemo(() => new Map(view.nodes.map(node => [node.id, node])), [view.nodes]);
  const edges = useMemo(() => view.edges.filter(edge => nodes.has(edge.source) && nodes.has(edge.target)), [view.edges, nodes]);
  const tracedEdges = useMemo(() => new Set(trace?.assertionIds || []), [trace]);
  const tracedNodes = useMemo(() => new Set(view.edges.filter(edge => tracedEdges.has(edge.id)).flatMap(edge => [edge.source, edge.target])), [view.edges, tracedEdges]);
  const related = useMemo(() => selected ? view.edges.filter(edge => edge.source === selected.id || edge.target === selected.id) : [], [selected, view.edges]);
  const matching = useMemo(() => (view.entityPage || view.nodes).filter(node => `${node.label} ${node.entityType}`.toLowerCase().includes(search.toLowerCase())), [search, view.nodes, view.entityPage]);

  const moveCamera = useCallback((next: Camera, animate = false) => {
    cancelAnimationFrame(animation.current);
    const start = cameraRef.current;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!animate || reduced) { cameraRef.current = next; setCamera(next); return; }
    const started = performance.now();
    const frame = (now: number) => {
      const progress = Math.min(1, (now - started) / 620);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = { x: start.x + (next.x - start.x) * eased, y: start.y + (next.y - start.y) * eased, zoom: start.zoom + (next.zoom - start.zoom) * eased };
      cameraRef.current = current; setCamera(current);
      if (progress < 1) animation.current = requestAnimationFrame(frame);
    };
    animation.current = requestAnimationFrame(frame);
  }, []);

  const fit = useCallback((animate = true) => {
    if (!view.nodes.length) return;
    const minX = Math.min(...view.nodes.map(node => node.x)) - 110;
    const maxX = Math.max(...view.nodes.map(node => node.x)) + 110;
    const minY = Math.min(...view.nodes.map(node => node.y)) - 55;
    const maxY = Math.max(...view.nodes.map(node => node.y)) + 55;
    moveCamera({ x: (minX + maxX) / 2, y: (minY + maxY) / 2, zoom: Math.min(1.25, Math.max(.005, Math.min((size.width - 48) / (maxX - minX), (size.height - 60) / (maxY - minY)))) }, animate);
  }, [view.nodes, size, moveCamera]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const observer = new ResizeObserver(entries => {
      const rect = entries[0]?.contentRect;
      if (rect?.width && rect.height) setSize({ width: rect.width, height: rect.height });
    });
    observer.observe(element);
    return () => { observer.disconnect(); cancelAnimationFrame(animation.current); };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(search.trim()); setOffset(0); setRelationOffset(0);
      if (search.trim()) setFocusId(null);
      fitPending.current = true;
    }, 350);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(null);
    const params = new URLSearchParams({ offset: String(offset), limit: String(ENTITY_PAGE), relationOffset: String(relationOffset), relationLimit: String(RELATION_PAGE) });
    if (focusId) params.set('focus', focusId);
    if (query) params.set('q', query);
    trace?.assertionIds.forEach(identifier => params.append('path', identifier));
    api<KnowledgeView>(`${apiRoot}/map/knowledge?${params}`, { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      setView(result); setLoading(false);
      if (externalSelection.current) {
        const target = result.nodes.find(node => node.id === externalSelection.current) || result.entityPage?.find(node => node.id === externalSelection.current);
        if (target) { setSelected(target); setSelectedEdge(null); setMentionOffset(0); setMentions(null); setDetailTab('mentions'); externalSelection.current = null; }
      }
    }).catch(reason => {
      if (!controller.signal.aborted) { setError(reason instanceof Error ? reason.message : 'The knowledge graph could not load'); setLoading(false); }
    });
    return () => controller.abort();
  }, [apiRoot, offset, relationOffset, focusId, refreshToken, reload, query, trace]);

  useEffect(() => {
    if (previousExpanded.current !== expanded) {
      previousExpanded.current = expanded;
      fitPending.current = true;
    }
  }, [expanded]);

  useEffect(() => {
    if (!loading && fitPending.current && view.nodes.length) { fit(); fitPending.current = false; }
  }, [loading, view.nodes, fit]);

  useEffect(() => {
    if (!focus?.nodeId) return;
    externalSelection.current = focus.nodeId; fitPending.current = true; setFocusId(focus.nodeId); setRelationOffset(0);
  }, [focus?.nodeId, focus?.nonce]);

  useEffect(() => {
    if (!trace?.assertionIds.length || loading) return;
    const pathNodes = view.nodes.filter(node => tracedNodes.has(node.id));
    if (!pathNodes.length) return;
    const minX = Math.min(...pathNodes.map(node => node.x)) - 90;
    const maxX = Math.max(...pathNodes.map(node => node.x)) + 90;
    const minY = Math.min(...pathNodes.map(node => node.y)) - 90;
    const maxY = Math.max(...pathNodes.map(node => node.y)) + 90;
    moveCamera({ x: (minX + maxX) / 2, y: (minY + maxY) / 2, zoom: Math.min(1.6, Math.max(.005, Math.min((size.width - 50) / (maxX - minX), (size.height - 60) / (maxY - minY)))) }, true);
  }, [trace?.nonce, loading, view.nodes, tracedNodes, size, moveCamera]);

  useEffect(() => {
    if (!selected) { setMentions(null); return; }
    const controller = new AbortController();
    setMentionLoading(true); setMentionError(null);
    api<Mentions>(`${apiRoot}/map/entity/${encodeURIComponent(selected.id)}/mentions?offset=${mentionOffset}&limit=8`, { signal: controller.signal }).then(result => {
      if (!controller.signal.aborted) { setMentions(result); setMentionLoading(false); }
    }).catch(reason => {
      if (!controller.signal.aborted) { setMentionError(reason instanceof Error ? reason.message : 'Source mentions could not load'); setMentionLoading(false); }
    });
    return () => controller.abort();
  }, [selected, mentionOffset, apiRoot, refreshToken, reload]);

  const zoom = useCallback((factor: number) => moveCamera({ ...cameraRef.current, zoom: Math.min(4, Math.max(.005, cameraRef.current.zoom * factor)) }, true), [moveCamera]);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const bounds = element.getBoundingClientRect();
      const current = cameraRef.current;
      const nextZoom = Math.min(4, Math.max(.005, current.zoom * Math.exp(-event.deltaY * .0015)));
      const x = event.clientX - bounds.left - bounds.width / 2, y = event.clientY - bounds.top - bounds.height / 2;
      moveCamera({ x: current.x + x / current.zoom - x / nextZoom, y: current.y + y / current.zoom - y / nextZoom, zoom: nextZoom });
    };
    element.addEventListener('wheel', wheel, { passive: false });
    return () => element.removeEventListener('wheel', wheel);
  }, [moveCamera]);

  const select = useCallback((node: Entity) => {
    setSelected(node); setSelectedEdge(null); setMentionOffset(0); setMentions(null); setDetailTab('mentions'); onSelect?.(node);
  }, [onSelect]);
  const explore = (entityId: string) => { fitPending.current = true; setFocusId(entityId); setRelationOffset(0); setSearch(''); };
  const browse = () => { fitPending.current = true; setFocusId(null); setOffset(0); setRelationOffset(0); setSelected(null); setSelectedEdge(null); };
  const page = (direction: number) => {
    fitPending.current = true;
    if (focusId) setRelationOffset(current => Math.max(0, current + direction * RELATION_PAGE));
    else { setOffset(current => Math.max(0, current + direction * ENTITY_PAGE)); setRelationOffset(0); }
    setSelected(null); setSelectedEdge(null); if (!focusId) setCatalogOpen(true);
  };
  const openSource = (chunkId?: string, label?: string) => { if (chunkId) onSource?.({ nodeId: chunkId, label }); };
  const sourceEntity = selectedEdge ? nodes.get(selectedEdge.source) : undefined;
  const targetEntity = selectedEdge ? nodes.get(selectedEdge.target) : undefined;
  const visibleLabels = useMemo(() => {
    const occupied: { x: number; y: number; width: number }[] = [];
    const shown = new Set<string>();
    const degrees = new Map<string, number>();
    edges.forEach(edge => { degrees.set(edge.source, (degrees.get(edge.source) || 0) + 1); degrees.set(edge.target, (degrees.get(edge.target) || 0) + 1); });
    const priority = (node: Entity) => (node.id === selected?.id || node.id === hoverId || node.id === focusId ? 10000 : 0) + (degrees.get(node.id) || 0) * 100 + Math.log1p(node.mentionCount || 0);
    const prioritized = [...view.nodes].sort((a, b) => priority(b) - priority(a) || a.label.localeCompare(b.label));
    const labelBudget = Math.max(6, Math.min(16, Math.floor(size.width * size.height / 18000)));
    for (const node of prioritized) {
      if (shown.size >= labelBudget && node.id !== selected?.id && node.id !== hoverId) continue;
      const x = (node.x - camera.x) * camera.zoom + size.width / 2;
      const y = (node.y - camera.y) * camera.zoom + size.height / 2 + 18;
      const width = Math.min(180, clip(node.label, 30).length * 5.8);
      if (x < -width || x > size.width + width || y < -20 || y > size.height + 20) continue;
      if (node.id === selected?.id || node.id === hoverId || !occupied.some(box => Math.abs(box.x - x) < (box.width + width) / 2 + 7 && Math.abs(box.y - y) < 15)) { shown.add(node.id); occupied.push({ x, y, width }); }
    }
    return shown;
  }, [view.nodes, edges, camera, size, selected?.id, focusId, hoverId]);
  const hasPrevious = focusId ? relationOffset > 0 : offset > 0;
  const hasNext = focusId ? view.pagination.hasMoreRelationships : view.pagination.hasMoreEntities;

  return <section className={styles.root} aria-label="Knowledge graph">
    <div className={styles.toolbar}>
      <div className={styles.heading}><Network size={16} aria-hidden="true" /><strong>{focusId ? 'Entity neighborhood' : 'Entities & relationships'}</strong><button type="button" className={styles.iconButton} aria-label="About this graph" aria-expanded={help} onClick={() => setHelp(value => !value)}><CircleHelp size={15} /></button></div>
      <div className={styles.tools}>
        <button type="button" className={`${styles.iconButton} ${catalogOpen ? styles.activeTool : ''}`} title="Browse all entities" aria-label="Browse all entities" aria-expanded={catalogOpen} onClick={() => setCatalogOpen(value => !value)}><List size={16} /></button>
        <label className={styles.find}><Search size={14} aria-hidden="true" /><input aria-label="Search workspace entities" placeholder="Search entities" value={search} onChange={event => setSearch(event.target.value)} /></label>
      </div>
      {help && <div className={styles.help}><strong>A knowledge graph, with sources one click away</strong><p>Nodes are extracted entities. Arrows show directed, labelled semantic relationships. Documents and chunks are available through each entity’s source mentions.</p><p>Solid arrows come from structured source records. Dashed arrows are unverified model extractions. Dotted arrows need review. A model score is not a probability of truth.</p><p>Loaded counts describe this page. Indexed entities include entities with no relationships, while connected entities participate in at least one. Browse more entities or explore one entity’s relationships without loading the whole corpus.</p></div>}
    </div>
    {search && <div className={styles.searchResults} aria-label="Matching entities">{matching.slice(0, 12).map(node => <button type="button" key={node.id} onClick={() => { select(node); explore(node.id); setCatalogOpen(false); }}>{node.label}<small>{human(node.entityType)}</small></button>)}{!matching.length && <span>No matching entities. Try another name or type.</span>}{matching.length > 12 && <span>Keep typing to narrow {matching.length} matches.</span>}</div>}
    {catalogOpen && <section className={styles.catalog} aria-label="Workspace entity catalog"><header><strong>Workspace entities</strong><button type="button" className={styles.iconButton} aria-label="Close entity catalog" onClick={() => setCatalogOpen(false)}><X size={14} /></button></header><div className={styles.catalogList}>{(view.entityPage || view.nodes).map(node => <button type="button" key={node.id} onClick={() => { select(node); explore(node.id); setCatalogOpen(false); }}><strong>{node.label}</strong><span>{human(node.entityType)}</span><small>{node.documentCount ?? 0} documents · {node.mentionCount ?? 0} mentions</small></button>)}{!loading && !(view.entityPage || view.nodes).length && <p>No entities match this search.</p>}</div><div className={styles.mentionPages}><button type="button" disabled={!offset || loading} onClick={() => setOffset(value => Math.max(0, value - ENTITY_PAGE))}><ArrowLeft size={13} />Previous</button><span>{view.pagination.entityTotal ? `${offset + 1}–${Math.min(offset + (view.entityPage || view.nodes).length, view.pagination.entityTotal)} of ${view.pagination.entityTotal.toLocaleString()}` : '0 entities'}</span><button type="button" disabled={!view.pagination.hasMoreEntities || loading} onClick={() => setOffset(value => value + ENTITY_PAGE)}>Next<ArrowRight size={13} /></button></div></section>}
    <div className={styles.graph} ref={host}>
      <svg className={styles.canvas} viewBox={`0 0 ${size.width} ${size.height}`} role="group" aria-label="Entity relationship map. Drag to pan, scroll to zoom. Use Tab to select an entity." tabIndex={0}
        onKeyDown={event => {
          if (event.target !== event.currentTarget) return;
          const current = cameraRef.current;
          if (event.key === '+' || event.key === '=') zoom(1.3);
          else if (event.key === '-') zoom(1 / 1.3);
          else if (event.key === 'Home') fit();
          else if (event.key.startsWith('Arrow')) { event.preventDefault(); moveCamera({ ...current, x: current.x + (event.key === 'ArrowRight' ? 70 : event.key === 'ArrowLeft' ? -70 : 0) / current.zoom, y: current.y + (event.key === 'ArrowDown' ? 70 : event.key === 'ArrowUp' ? -70 : 0) / current.zoom }); }
        }}
        onPointerDown={event => { if ((event.target as Element).closest('[data-graph-control]')) return; drag.current = { x: event.clientX, y: event.clientY, camera: cameraRef.current }; event.currentTarget.setPointerCapture(event.pointerId); }}
        onPointerMove={event => { if (!drag.current) return; moveCamera({ ...drag.current.camera, x: drag.current.camera.x - (event.clientX - drag.current.x) / drag.current.camera.zoom, y: drag.current.camera.y - (event.clientY - drag.current.y) / drag.current.camera.zoom }); }}
        onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
        <defs><marker id={`${id}-arrow`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 1 1 L 9 5 L 1 9" fill="none" className={styles.arrow} strokeWidth="1.4" /></marker></defs>
        <g transform={`translate(${size.width / 2} ${size.height / 2}) scale(${camera.zoom}) translate(${-camera.x} ${-camera.y})`}>
          {edges.map((edge, index) => {
            const source = nodes.get(edge.source)!, target = nodes.get(edge.target)!;
            const dx = target.x - source.x, dy = target.y - source.y, length = Math.hypot(dx, dy) || 1;
            const ux = dx / length, uy = dy / length;
            const sourceX = source.x + ux * 10, sourceY = source.y + uy * 10, targetX = target.x - ux * 13, targetY = target.y - uy * 13;
            const bend = edge.source === edge.target ? 65 : (index % 3 - 1) * 18;
            const midX = (sourceX + targetX) / 2 - uy * bend, midY = (sourceY + targetY) / 2 + ux * bend;
            const path = edge.source === edge.target ? `M ${source.x - 5} ${source.y - 8} C ${source.x - 65} ${source.y - 90} ${source.x + 65} ${source.y - 90} ${source.x + 5} ${source.y - 8}` : `M ${sourceX} ${sourceY} Q ${midX} ${midY} ${targetX} ${targetY}`;
            const faded = selected && edge.source !== selected.id && edge.target !== selected.id;
            return <g key={edge.id} data-graph-control="edge" className={`${styles.edge} ${native(edge) && !review(edge) ? styles.native : review(edge) ? styles.review : styles.unverified} ${tracedEdges.has(edge.id) ? styles.tracedEdge : ''} ${selectedEdge?.id === edge.id ? styles.activeEdge : ''} ${faded && !tracedEdges.has(edge.id) ? styles.faded : ''}`} role="button" tabIndex={0} aria-label={`${source.label} ${human(edge.label)} ${target.label}. ${relationshipStatus(edge)}`} onMouseEnter={() => setHoverId(edge.id)} onMouseLeave={() => setHoverId(null)} onClick={() => { setSelectedEdge(edge); setSelected(null); }} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedEdge(edge); setSelected(null); } }}>
              <title>{`${source.label} → ${human(edge.label)} → ${target.label}\n${relationshipStatus(edge)}`}</title>
              <path className={styles.edgeHit} d={path} /><path className={styles.edgeLine} d={path} markerEnd={`url(#${id}-arrow)`} />
              {(selectedEdge?.id === edge.id || hoverId === edge.id) && <text className={styles.edgeLabel} style={{ fontSize: 10 / camera.zoom, strokeWidth: 4 / camera.zoom }} x={midX} y={midY - 5 / camera.zoom} textAnchor="middle">{clip(human(edge.label), 25)}</text>}
            </g>;
          })}
          {view.nodes.map(node => <g key={node.id} data-graph-control="node" role="button" tabIndex={0} aria-label={`${node.label}, ${human(node.entityType)}, ${node.mentionCount ?? 0} mentions`} className={`${styles.node} ${styles[`hue${hue(node.entityType)}`]} ${tracedNodes.has(node.id) ? styles.tracedNode : ''} ${selected?.id === node.id ? styles.selectedNode : ''} ${search && !matching.some(match => match.id === node.id) && !tracedNodes.has(node.id) ? styles.faded : ''}`} transform={`translate(${node.x} ${node.y})`} onMouseEnter={() => setHoverId(node.id)} onMouseLeave={() => setHoverId(null)} onClick={() => select(node)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(node); } }}>
            <title>{`${node.label}\n${human(node.entityType)}`}</title><circle r={(selected?.id === node.id ? 6 : 4) / camera.zoom} style={{ strokeWidth: 1.5 / camera.zoom }} />{visibleLabels.has(node.id) && <text y={18 / camera.zoom} style={{ fontSize: 11 / camera.zoom, strokeWidth: 4 / camera.zoom }} textAnchor="middle">{clip(node.label, 30)}</text>}
          </g>)}
        </g>
      </svg>
      {loading && <div className={styles.loading} role="status"><Loader2 size={15} className={styles.spin} />Loading entities & relationships…</div>}
      {error && <div className={styles.empty} role="alert"><strong>Knowledge graph unavailable</strong><p>{error}</p><button type="button" onClick={() => setReload(value => value + 1)}>Retry graph</button></div>}
      {!loading && !error && !view.nodes.length && <div className={styles.empty}><Network size={26} /><strong>{view.pagination.entityTotal ? 'No semantic relationships in this view' : 'No entities to display yet'}</strong><p>{view.pagination.entityTotal ? 'Search or browse the entity catalog, then select an entity to explore its relationships and source mentions.' : 'Published entities will appear here after ingestion. Source files remain available in the Sources view.'}</p>{!!view.pagination.entityTotal && <button type="button" onClick={() => setCatalogOpen(true)}>Browse entities</button>}</div>}
      {!loading && !error && !!view.nodes.length && !edges.length && <div className={styles.noEdges}>No semantic relationships on this page · select an entity to explore its neighborhood</div>}
      <div className={styles.controls} aria-label="Graph camera controls"><button type="button" aria-label="Zoom in" onClick={() => zoom(1.35)}><Plus size={16} /></button><button type="button" aria-label="Zoom out" onClick={() => zoom(1 / 1.35)}><Minus size={16} /></button><button type="button" aria-label="Fit graph" onClick={() => fit()}><Focus size={16} /></button></div>
    </div>
    {(selected || selectedEdge) && <section className={styles.details} aria-label={selected ? `${selected.label} details` : 'Relationship details'}>
      <header className={styles.detailHeader}><div><strong>{selected?.label || human(selectedEdge?.label || '')}</strong><small>{selected ? human(selected.entityType) : relationshipStatus(selectedEdge!)}</small></div><button type="button" className={styles.iconButton} aria-label="Close graph details" onClick={() => { setSelected(null); setSelectedEdge(null); }}><X size={16} /></button></header>
      {selected && <><div className={styles.detailActions}><div className={styles.tabs} role="tablist" aria-label="Entity details"><button type="button" role="tab" aria-selected={detailTab === 'mentions'} onClick={() => setDetailTab('mentions')}>Source mentions{mentions ? ` · ${compact.format(mentions.counts.occurrences)}` : ''}</button><button type="button" role="tab" aria-selected={detailTab === 'relationships'} onClick={() => setDetailTab('relationships')}>Relationships</button></div><button type="button" className={styles.explore} onClick={() => explore(selected.id)}>Explore<ArrowUpRight size={13} /></button></div>
        <div className={styles.detailBody}>
          {detailTab === 'mentions' ? <>
            {mentionLoading && <p className={styles.status} role="status"><Loader2 size={14} className={styles.spin} />Loading source occurrences…</p>}
            {mentionError && <p className={styles.status} role="alert">{mentionError}<button type="button" onClick={() => setReload(value => value + 1)}>Retry</button></p>}
            {!mentionLoading && !mentionError && mentions && <><p className={styles.mentionSummary}>{mentions.counts.occurrenceCountTruncated ? 'At least ' : ''}{mentions.counts.occurrences.toLocaleString()} occurrences across {mentions.counts.documents.toLocaleString()} documents and {mentions.counts.chunks.toLocaleString()} passages</p>{selected.aliases?.length ? <p className={styles.mentionSummary}>Aliases: {selected.aliases.join(', ')}</p> : null}{mentions.mentions.map(mention => { const structured = structuredMention(mention); return <article className={styles.mention} key={mention.id}><button type="button" className={styles.sourceLink} disabled={!onSource} onClick={() => openSource(mention.chunkId, mention.documentTitle)}><span>{mention.documentTitle || 'Source document'}</span><ArrowUpRight size={13} /></button><p>{structured ? 'Structured source record · open the document to inspect its original fields.' : clip(mention.chunkText || mention.text, 320)}</p><small>{structured ? 'Structured source record' : mention.text}{mention.sourceSpans && mention.sourceSpans.length > 1 ? ` · ${mention.sourceSpans.length} source spans` : ''}</small></article>; })}{!mentions.mentions.length && <p className={styles.status}>No published source mentions are available for this entity.</p>}<div className={styles.mentionPages}><button type="button" disabled={!mentionOffset} onClick={() => setMentionOffset(value => Math.max(0, value - 8))}><ArrowLeft size={13} />Previous</button><span>{mentions.pagination.total ? `${mentions.pagination.offset + 1}–${Math.min(mentions.pagination.offset + mentions.mentions.length, mentions.pagination.total)} of ${mentions.pagination.total}` : '0 mentions'}</span><button type="button" disabled={!mentions.pagination.hasMore} onClick={() => setMentionOffset(value => value + 8)}>Next<ArrowRight size={13} /></button></div></>}
          </> : <><p className={styles.mentionSummary}>Relationships in the loaded graph. Explore this entity to load its full neighborhood in pages.</p>{related.map(edge => <button type="button" className={styles.relationshipRow} key={edge.id} onClick={() => { setSelectedEdge(edge); setSelected(null); }}><span>{nodes.get(edge.source)?.label || 'Entity'}<b>{human(edge.label)}</b>{nodes.get(edge.target)?.label || 'Entity'}</span><small>{relationshipStatus(edge)}</small></button>)}{!related.length && <p className={styles.status}>No relationships in this page. Select Explore to check this entity’s neighborhood.</p>}</>}
        </div></>}
      {selectedEdge && <div className={styles.detailBody}><div className={styles.triple}><span>{sourceEntity?.label || 'Source entity'}</span><ArrowRight size={15} /><b>{human(selectedEdge.label)}</b><ArrowRight size={15} /><span>{targetEntity?.label || 'Target entity'}</span></div>{selectedEdge.quote && <blockquote>{selectedEdge.quote}</blockquote>}<p className={styles.mentionSummary}>{native(selectedEdge) ? 'Recorded explicitly in structured source data. This is source attribution, not independent verification.' : codebaseAgent(selectedEdge) ? 'Proposed by the GPT-4.1 mini codebase agent from the cited source line. The source match was checked; the relationship meaning was not independently verified.' : 'Extracted by a local model. Check the source passage and its context before relying on this relationship.'}{typeof selectedEdge.confidence === 'number' ? ` Model score: ${selectedEdge.confidence.toFixed(3)} · uncalibrated` : ''}</p>{selectedEdge.chunkId && onSource && <button type="button" className={styles.sourceLink} onClick={() => openSource(selectedEdge.chunkId, sourceEntity?.label)}>Open source passage<ArrowUpRight size={13} /></button>}</div>}
    </section>}
    <footer className={styles.footer}><div className={styles.pageStatus} role="status"><span>{view.nodes.length.toLocaleString()} entities · {edges.length.toLocaleString()} relationships loaded</span><small>{view.pagination.connectedEntityTotal == null ? 'Connected total unavailable' : `${view.pagination.connectedEntityTotal.toLocaleString()} entities with relationships`} · {view.pagination.entityTotal.toLocaleString()} indexed entities · {view.pagination.relationshipTotal.toLocaleString()} {focusId ? 'relationships in neighborhood' : 'relationships total'}</small></div><div className={styles.paging}>{focusId && <button type="button" title="Return to the graph overview" onClick={browse}>Overview</button>}<button type="button" aria-label={focusId ? 'Previous relationships' : 'Previous entities'} disabled={!hasPrevious || loading} onClick={() => page(-1)}><ArrowLeft size={14} /></button><button type="button" aria-label={focusId ? 'Next relationships' : 'Next entities'} disabled={!hasNext || loading} onClick={() => page(1)}><ArrowRight size={14} /></button></div></footer>
  </section>;
}
