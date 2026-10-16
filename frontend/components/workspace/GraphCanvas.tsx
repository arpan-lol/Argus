'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Minus, Plus, Maximize2, Network } from 'lucide-react';
import type { EvidenceGraph, GraphNode } from '@/lib/evidence-types';
import { chunkColor } from '@/lib/evidence-types';

const colors = { document: '#c18a17', section: '#637a94', chunk: '#3b8a75', entity: '#9b6fa9' };
const names = { document: 'Document', section: 'Section', chunk: 'Chunk', entity: 'Entity' };

export function GraphCanvas({ graph, selectedId, onSelect, loading }: {
  graph: EvidenceGraph | null; selectedId: string | null; onSelect: (node: GraphNode) => void; loading: boolean;
}) {
  const [zoom, setZoom] = useState(1);
  const scroll = useRef<HTMLDivElement | null>(null);
  const layout = useMemo(() => {
    const neighbors = new Set((graph?.edges || []).filter(edge => edge.source === selectedId || edge.target === selectedId).flatMap(edge => [edge.source, edge.target]));
    const groups: GraphNode[][] = ['document', 'section', 'chunk', 'entity'].map(type => (graph?.nodes || []).filter(node => node.type === type).sort((a, b) => Number(b.id === selectedId) - Number(a.id === selectedId) || Number(neighbors.has(b.id)) - Number(neighbors.has(a.id))).slice(0, 6));
    const height = Math.max(340, ...groups.map(group => group.length * 56 + 84));
    const positions = new Map<string, { x: number; y: number; node: GraphNode }>();
    groups.forEach((group, col) => group.forEach((node, index) => positions.set(node.id, { x: 100 + col * 205, y: 64 + (index + .5) * (height - 100) / Math.max(group.length, 1), node })));
    return { positions, height, groups };
  }, [graph, selectedId]);
  const connected = useMemo(() => new Set((graph?.edges || []).filter(edge => edge.source === selectedId || edge.target === selectedId).flatMap(edge => [edge.source, edge.target])), [graph, selectedId]);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const container = scroll.current;
      const selected = container?.querySelector('[data-selected="true"]');
      if (!container || !selected) return;
      const bounds = selected.getBoundingClientRect(), viewport = container.getBoundingClientRect();
      container.scrollTo({ left: container.scrollLeft + bounds.left + bounds.width / 2 - viewport.left - viewport.width / 2, top: container.scrollTop + bounds.top + bounds.height / 2 - viewport.top - viewport.height / 2, behavior: 'instant' });
    });
    return () => cancelAnimationFrame(frame);
  }, [graph, selectedId, zoom]);
  const fit = () => { if (scroll.current) { setZoom(Math.min(1, scroll.current.clientWidth / 680)); scroll.current.scrollTo({ left: 0, top: 0, behavior: 'instant' }); } };

  return <div className="graph-canvas" aria-busy={loading}>
    <div className="graph-legend">{Object.entries(names).map(([type, name]) => <span key={type}><i style={{ background: colors[type as keyof typeof colors] }} />{name}</span>)}</div>
    {loading && <div className="graph-loading" role="status">Loading evidence neighborhood…</div>}
    {!graph?.nodes.length && !loading ? <div className="empty-state"><Network size={28} /><strong>No graph in this view</strong><span>Select a document or another section to explore its evidence.</span></div> :
      <div className="graph-scroll" ref={scroll}><svg className="evidence-graph" viewBox={`0 0 820 ${layout.height}`} style={{ minWidth: `${zoom * 680}px`, width: `${zoom * 100}%` }} role="img" aria-label="Evidence graph. Select a node to inspect its source and relationships.">
        <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#aab3b2" /></marker></defs>
        {layout.groups.map((group, i) => group.length > 0 && <text key={i} x={100 + i * 205} y={28} textAnchor="middle" className="graph-column">{group[0].type === 'entity' && group.length > 1 ? 'Entities' : `${names[group[0].type]}${group.length > 1 ? 's' : ''}`} · {group.length}</text>)}
        {(graph?.edges || []).map(edge => {
          const from = layout.positions.get(edge.source), to = layout.positions.get(edge.target);
          if (!from || !to) return null;
          const active = edge.source === selectedId || edge.target === selectedId;
          return <g key={edge.id}><path d={`M ${from.x + 72} ${from.y} C ${from.x + 120} ${from.y}, ${to.x - 120} ${to.y}, ${to.x - 76} ${to.y}`} fill="none" stroke={active ? '#8d701f' : '#d3dbd7'} strokeWidth={active ? 2 : 1.15} opacity={selectedId && !active ? .5 : 1} markerEnd="url(#arrow)" /><title>{edge.type}</title></g>;
        })}
        {Array.from(layout.positions.values()).map(({ node, x, y }) => {
          const selected = selectedId === node.id;
          const ink = node.type === 'chunk' ? chunkColor(node.chunkId || node.id).ink : colors[node.type];
          const tint = node.type === 'chunk' ? chunkColor(node.chunkId || node.id).tint : '#fff';
          return <g key={node.id} className="graph-node" role="button" tabIndex={0} data-selected={selected} aria-label={`${names[node.type]}: ${node.label}`} aria-pressed={selected}
            onClick={() => onSelect(node)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(node); } }}
            opacity={selectedId && !selected && !connected.has(node.id) ? .66 : 1}>
            <title>{node.label}</title><rect x={x - 74} y={y - 19} width={148} height={38} rx={7} fill={selected ? ink : tint} stroke={selected ? ink : connected.has(node.id) ? ink : '#d6ded9'} strokeWidth={selected ? 2 : 1} />
            <circle cx={x - 60} cy={y} r={3.5} fill={selected ? '#fff' : ink} />
            <text x={x - 49} y={y + 4} fontSize={10.5} fill={selected ? '#fff' : '#35443d'}>{node.label.length > 20 ? `${node.label.slice(0, 19)}…` : node.label}</text>
          </g>;
        })}
      </svg></div>}
    <div className="graph-footer"><span>{layout.positions.size} / {graph?.nodes.length || 0} nodes · {graph?.edges.filter(edge => layout.positions.has(edge.source) && layout.positions.has(edge.target)).length || 0} visible edges · focused view</span><div className="graph-zoom"><button aria-label="Zoom out" onClick={() => setZoom(value => Math.max(.3, value - .2))}><Minus size={13} /></button><span>{Math.round(zoom * 100)}%</span><button aria-label="Zoom in" onClick={() => setZoom(value => Math.min(2, value + .2))}><Plus size={13} /></button><button aria-label="Fit graph to panel" onClick={fit}><Maximize2 size={12} /></button></div><label className="graph-node-picker"><span>Focus any returned record</span><select value={selectedId || ''} onChange={event => { const node = graph?.nodes.find(item => item.id === event.target.value); if (node) onSelect(node); }}><option value="" disabled>Select a record…</option>{graph?.nodes.map(node => <option value={node.id} key={node.id}>{names[node.type]} · {node.label}</option>)}</select></label></div>
  </div>;
}
