'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Expand, HelpCircle, Loader2, Minus, Plus, RotateCcw } from 'lucide-react';
import styles from './GraphMap.module.css';

export type MapNode = {
  id: string; type: 'group' | 'document' | 'section' | 'chunk' | 'entity';
  label: string; preview?: string; x: number; y: number; radius?: number;
  documentId?: string; sectionId?: string; chunkId?: string; count?: number;
  [key: string]: unknown;
};
type Bounds = { minX: number; minY: number; maxX: number; maxY: number };
type MapEdge = { id: string; source: string; target: string; type: string; derived?: boolean; [key: string]: unknown };
type MapView = { nodes: MapNode[]; edges: MapEdge[]; level: string; truncated?: boolean; source?: string; status?: string };
type Camera = { x: number; y: number; zoom: number };
type Props = {
  focus?: { nodeId: string; nonce: number } | null;
  onSelect: (node: MapNode) => void;
  onFocus?: (focus: { documentId?: string; sectionId?: string; chunkId?: string }) => void;
};

const names = { group: 'Source group', document: 'File', section: 'Heading', chunk: 'Chunk', entity: 'Shared name' };
const colors = { group: '#b99540', document: '#c6a34f', section: '#869ab2', chunk: '#5b9b88', entity: '#a187b5' };
const empty: MapView = { nodes: [], edges: [], level: 'groups' };
const clip = (text: string, size = 34) => text.length > size ? `${text.slice(0, size - 1)}…` : text;
const scale = (zoom: number) => Math.max(.003, Math.min(7, zoom));

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/map${path}`, { cache: 'no-store', signal });
  if (!response.ok) throw new Error('The source map could not load. Retry when the server is available.');
  return response.json();
}

export function GraphMap({ focus, onSelect, onFocus }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const camera = useRef<Camera>({ x: 0, y: 0, zoom: .015 });
  const dimensions = useRef({ width: 800, height: 700 });
  const world = useRef<Bounds | null>(null);
  const groups = useRef<MapNode[]>([]);
  const current = useRef<MapView>(empty);
  const screenNodes = useRef<{ node: MapNode; x: number; y: number; radius: number }[]>([]);
  const selected = useRef<string | null>(null);
  const hovered = useRef<string | null>(null);
  const dragging = useRef<{ x: number; y: number; startX: number; startY: number; moved: boolean } | null>(null);
  const animation = useRef(0);
  const disposed = useRef(false);
  const callbacks = useRef({ onSelect, onFocus });
  callbacks.current = { onSelect, onFocus };
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<{ node: MapNode; x: number; y: number } | null>(null);
  const [help, setHelp] = useState(false);
  const [zoomLabel, setZoomLabel] = useState('Overview');
  const [reload, setReload] = useState(0);
  const [truncated, setTruncated] = useState(false);
  const [accessible, setAccessible] = useState<MapNode[]>([]);

  const draw = useCallback(() => {
    const surface = canvas.current;
    if (!surface) return;
    const context = surface.getContext('2d');
    if (!context) return;
    const { width, height } = dimensions.current;
    const c = camera.current;
    const dark = window.document.documentElement.classList.contains('dark');
    context.clearRect(0, 0, width, height);
    context.fillStyle = dark ? '#171918' : '#fafbf8';
    context.fillRect(0, 0, width, height);
    const step = 28;
    context.fillStyle = dark ? '#282c29' : '#e2e7de';
    for (let x = ((-c.x * c.zoom) % step + step) % step; x < width; x += step) {
      for (let y = ((-c.y * c.zoom) % step + step) % step; y < height; y += step) context.fillRect(x, y, 1, 1);
    }
    const desired = c.zoom < .08 ? 'groups' : c.zoom < .45 ? 'documents' : 'detail';
    const view = current.current;
    const nodes = desired === 'groups' ? groups.current : view.nodes;
    const projected = new Map(nodes.map(node => [node.id, { node, x: (node.x - c.x) * c.zoom + width / 2, y: (node.y - c.y) * c.zoom + height / 2 }]));
    context.lineCap = 'round';
    for (const edge of view.edges) {
      const a = projected.get(edge.source), b = projected.get(edge.target);
      if (!a || !b) continue;
      if ((a.x < -30 && b.x < -30) || (a.x > width + 30 && b.x > width + 30) || (a.y < -30 && b.y < -30) || (a.y > height + 30 && b.y > height + 30)) continue;
      const active = [selected.current, hovered.current].some(id => id && (edge.source === id || edge.target === id));
      context.strokeStyle = active ? (dark ? '#cfb46b' : '#9c833e') : (dark ? '#39443e' : '#d2ddd4');
      context.lineWidth = active ? 1.8 : .7;
      context.setLineDash(edge.derived || edge.type === 'SHARES_TERM' || edge.type === 'SHARED_MENTION' ? [3, 4] : []);
      context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke();
    }
    context.setLineDash([]);
    screenNodes.current = [];
    for (const point of projected.values()) {
      const { node, x, y } = point;
      if (x < -100 || y < -70 || x > width + 100 || y > height + 70) continue;
      const active = node.id === selected.current || node.id === hovered.current;
      const radius = node.type === 'group' ? Math.max(13, Math.min(23, 11 + Math.log2((node.count || 1) + 1))) : node.type === 'document' ? 7 : node.type === 'entity' ? 6 : 4.5;
      screenNodes.current.push({ node, x, y, radius: radius + 7 });
      context.beginPath(); context.arc(x, y, radius + (active ? 4 : 0), 0, Math.PI * 2);
      context.fillStyle = active ? (dark ? '#655a39' : '#f0e8c9') : (dark ? '#202723' : '#fff'); context.fill();
      context.strokeStyle = colors[node.type]; context.lineWidth = active ? 2 : 1.2; context.stroke();
      if (node.type === 'group') {
        context.font = '600 11px var(--font-geist-sans), sans-serif'; context.textAlign = 'center'; context.textBaseline = 'middle';
        context.fillStyle = dark ? '#e8d49e' : '#725d26'; context.fillText(String(node.count || ''), x, y);
      } else {
        context.beginPath(); context.arc(x, y, Math.max(2, radius - 3), 0, Math.PI * 2); context.fillStyle = colors[node.type]; context.fill();
      }
      const showLabel = active || (node.type === 'group' && projected.size < 30) || (node.type === 'document' && (c.zoom > .12 || projected.size < 30)) || (node.type === 'entity' && projected.size < 100);
      if (showLabel) {
        const label = clip(node.label || node.preview || names[node.type], node.type === 'group' ? 20 : node.type === 'document' && c.zoom < .28 ? 14 : 31);
        context.font = `${active ? 600 : 400} 11px sans-serif`;
        const labelWidth = context.measureText(label).width + 12;
        context.fillStyle = dark ? '#1b211eed' : '#fafbf8ed';
        context.fillRect(x - labelWidth / 2, y + radius + 5, labelWidth, 20);
        context.fillStyle = dark ? '#d8dfd9' : '#4a564e'; context.textAlign = 'center'; context.textBaseline = 'middle';
        context.fillText(label, x, y + radius + 15);
      }
    }
  }, []);

  const move = useCallback((next: Camera) => {
    camera.current = { ...next, zoom: scale(next.zoom) };
    setZoomLabel(next.zoom < .08 ? 'Overview' : next.zoom < .45 ? 'Files' : 'Inside sources');
    draw();
  }, [draw]);

  const fit = useCallback(() => {
    if (!world.current) return;
    cancelAnimationFrame(animation.current);
    const b = world.current, { width, height } = dimensions.current;
    move({ x: (b.minX + b.maxX) / 2, y: (b.minY + b.maxY) / 2, zoom: Math.min(width / Math.max(1, b.maxX - b.minX), height / Math.max(1, b.maxY - b.minY)) * .82 });
  }, [move]);

  const fly = useCallback(async (nodeId: string) => {
    try {
      const destination = await request<{ node: MapNode; zoom: number; documentId?: string; sectionId?: string; chunkId?: string }>(`/locate/${encodeURIComponent(nodeId)}`);
      if (disposed.current) return;
      const node = destination.node;
      callbacks.current.onFocus?.({ documentId: destination.documentId || node.documentId, sectionId: destination.sectionId || node.sectionId, chunkId: destination.chunkId || node.chunkId });
      selected.current = node.id;
      const from = { ...camera.current }, target = { x: node.x, y: node.y, zoom: destination.zoom };
      cancelAnimationFrame(animation.current);
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { move(target); return; }
      const distance = Math.hypot(target.x - from.x, target.y - from.y);
      const travelZoom = scale(Math.min(from.zoom, target.zoom, Math.min(dimensions.current.width, dimensions.current.height) / Math.max(distance * 1.4, 1)));
      const started = performance.now(), duration = distance > 600 ? 1600 : 700;
      const ease = (n: number) => 1 - Math.pow(1 - n, 3);
      const interpolate = (a: number, b: number, amount: number) => a + (b - a) * amount;
      const frame = (now: number) => {
        if (disposed.current) return;
        const progress = Math.min(1, (now - started) / duration);
        const pan = ease(Math.max(0, Math.min(1, (progress - .18) / .58)));
        const zoom = progress < .3 ? Math.exp(interpolate(Math.log(from.zoom), Math.log(travelZoom), ease(progress / .3))) : progress > .65 ? Math.exp(interpolate(Math.log(travelZoom), Math.log(target.zoom), ease((progress - .65) / .35))) : travelZoom;
        move({ x: interpolate(from.x, target.x, pan), y: interpolate(from.y, target.y, pan), zoom });
        if (progress < 1) animation.current = requestAnimationFrame(frame);
      };
      animation.current = requestAnimationFrame(frame);
    } catch (failure) { if (!disposed.current) setError(failure instanceof Error ? failure.message : 'Unable to find this source.'); }
  }, [move]);

  useEffect(() => {
    disposed.current = false;
    let active = true;
    const element = host.current;
    if (!element) return;
    const resize = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      dimensions.current = { width, height };
      if (canvas.current) {
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        canvas.current.width = width * ratio; canvas.current.height = height * ratio;
        canvas.current.getContext('2d')?.setTransform(ratio, 0, 0, ratio, 0, 0);
      }
      draw();
    });
    resize.observe(element);
    const theme = new MutationObserver(draw); theme.observe(window.document.documentElement, { attributes: true, attributeFilter: ['class'] });
    request<{ bounds: Bounds; groups?: MapNode[] }>('/overview').then(result => {
      if (!active) return;
      world.current = result.bounds; groups.current = result.groups || [];
      fit(); setLoading(false);
    }).catch(failure => { if (active) { setError(failure.message); setLoading(false); } });
    return () => { active = false; disposed.current = true; resize.disconnect(); theme.disconnect(); cancelAnimationFrame(animation.current); };
  }, [draw, fit, reload]);

  useEffect(() => {
    let active = true, controller: AbortController | null = null, previous = '', sequence = 0, pending = false;
    const load = () => {
      if (!world.current || pending) return;
      const c = camera.current, { width, height } = dimensions.current;
      const bounds = { minX: Math.floor(c.x - width * .65 / c.zoom), maxX: Math.ceil(c.x + width * .65 / c.zoom), minY: Math.floor(c.y - height * .65 / c.zoom), maxY: Math.ceil(c.y + height * .65 / c.zoom) };
      const query = new URLSearchParams({ ...Object.fromEntries(Object.entries(bounds).map(([key, value]) => [key, String(value)])), zoom: String(c.zoom), limit: '800' }).toString();
      if (query === previous) return;
      previous = query; controller = new AbortController(); pending = true;
      const requestNumber = ++sequence;
      request<MapView>(`/view?${query}`, controller.signal).then(view => {
        if (!active || sequence !== requestNumber) return;
        current.current = view; setTruncated(!!view.truncated); setAccessible(view.nodes); setError(null); setLoading(false); draw();
      }).catch(failure => { if (active && failure.name !== 'AbortError') { setError(failure.message); previous = ''; } }).finally(() => { pending = false; });
    };
    const interval = window.setInterval(load, 180); load();
    return () => { active = false; window.clearInterval(interval); controller?.abort(); };
  }, [draw, reload]);

  useEffect(() => { if (!loading && focus?.nodeId) void fly(focus.nodeId); }, [focus?.nodeId, focus?.nonce, fly, loading]);

  const hit = (x: number, y: number) => [...screenNodes.current].reverse().find(point => Math.hypot(point.x - x, point.y - y) <= point.radius)?.node;
  const zoomBy = (factor: number) => { cancelAnimationFrame(animation.current); move({ ...camera.current, zoom: camera.current.zoom * factor }); };

  return <div className={styles.map} ref={host}>
    <canvas ref={canvas} className={styles.canvas} aria-label="Interactive source graph. Drag to pan, scroll to zoom. Select a node to read its details." role="application" tabIndex={0}
      onWheel={event => {
        event.preventDefault(); cancelAnimationFrame(animation.current);
        const rect = event.currentTarget.getBoundingClientRect(), x = event.clientX - rect.left, y = event.clientY - rect.top;
        const c = camera.current, zoom = scale(c.zoom * Math.exp(-event.deltaY * .0015));
        move({ x: c.x + (x - dimensions.current.width / 2) * (1 / c.zoom - 1 / zoom), y: c.y + (y - dimensions.current.height / 2) * (1 / c.zoom - 1 / zoom), zoom });
      }}
      onPointerDown={event => { cancelAnimationFrame(animation.current); event.currentTarget.setPointerCapture(event.pointerId); dragging.current = { x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY, moved: false }; }}
      onPointerMove={event => {
        const rect = event.currentTarget.getBoundingClientRect(), x = event.clientX - rect.left, y = event.clientY - rect.top;
        const drag = dragging.current;
        if (drag) {
          if (Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > 4) drag.moved = true;
          move({ ...camera.current, x: camera.current.x - (event.clientX - drag.x) / camera.current.zoom, y: camera.current.y - (event.clientY - drag.y) / camera.current.zoom });
          drag.x = event.clientX; drag.y = event.clientY; setTooltip(null); event.currentTarget.style.cursor = 'grabbing';
        } else {
          const node = hit(x, y); hovered.current = node?.id || null;
          setTooltip(node ? { node, x: Math.min(dimensions.current.width - 220, Math.max(8, x + 16)), y: Math.max(8, Math.min(dimensions.current.height - 80, y + 16)) } : null);
          event.currentTarget.style.cursor = node ? 'pointer' : 'grab'; draw();
        }
      }}
      onPointerUp={event => {
        const drag = dragging.current; dragging.current = null;
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
        event.currentTarget.style.cursor = 'grab';
        if (!drag?.moved) {
          const rect = event.currentTarget.getBoundingClientRect(), node = hit(event.clientX - rect.left, event.clientY - rect.top);
          if (node) { selected.current = node.id; draw(); if (node.type === 'group') void fly(node.id); else callbacks.current.onSelect(node); }
        }
      }}
      onPointerCancel={() => { dragging.current = null; }}
      onPointerLeave={() => { if (!dragging.current) { hovered.current = null; setTooltip(null); draw(); } }}
      onDoubleClick={event => { const rect = event.currentTarget.getBoundingClientRect(), node = hit(event.clientX - rect.left, event.clientY - rect.top); if (node) void fly(node.id); }}
      onKeyDown={event => {
        const c = camera.current, distance = 90 / c.zoom;
        if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '=', '-', 'Home', 'Enter'].includes(event.key)) event.preventDefault();
        if (event.key === 'ArrowLeft') move({ ...c, x: c.x - distance });
        if (event.key === 'ArrowRight') move({ ...c, x: c.x + distance });
        if (event.key === 'ArrowUp') move({ ...c, y: c.y - distance });
        if (event.key === 'ArrowDown') move({ ...c, y: c.y + distance });
        if (event.key === '+' || event.key === '=') zoomBy(1.5);
        if (event.key === '-') zoomBy(1 / 1.5);
        if (event.key === 'Home') fit();
        if (event.key === 'Enter') { const node = current.current.nodes.find(item => item.id === selected.current); if (node) callbacks.current.onSelect(node); }
      }} />
    <div className={styles.legend}><span className={styles.level}>{zoomLabel}</span><span><i style={{ background: colors.document }} />Files</span><span><i style={{ background: colors.chunk }} />Chunks</span><span><i style={{ background: colors.entity }} />Shared names</span></div>
    {tooltip && <div className={styles.tooltip} style={{ left: tooltip.x, top: tooltip.y }}><small>{names[tooltip.node.type]}</small><strong>{clip(tooltip.node.preview || tooltip.node.label, 100)}</strong></div>}
    {loading && <div className={styles.notice} role="status"><Loader2 size={15} className={styles.spin} />Opening source map…</div>}
    {error && <div className={styles.error} role="alert"><span>{error}</span><button onClick={() => { setError(null); setReload(value => value + 1); }}><RotateCcw size={13} />Retry</button></div>}
    {truncated && !error && <div className={styles.limit}>Zoom in to reveal more sources</div>}
    <div className={styles.controls}><button aria-label="Zoom in" onClick={() => zoomBy(1.7)}><Plus size={16} /></button><button aria-label="Zoom out" onClick={() => zoomBy(1 / 1.7)}><Minus size={16} /></button><button aria-label="Show whole source map" onClick={fit}><Expand size={15} /></button><button aria-label="About the source map" aria-expanded={help} onClick={() => setHelp(value => !value)}><HelpCircle size={16} /></button></div>
    {help && <div className={styles.help}><strong>Your sources, connected</strong><p>Zoom into a group to reveal files, then their headings and chunks. Shared names connect mentions across files.</p><p>Drag to move. Scroll to zoom. Double-click a file to explore it. A citation flies to its source.</p><p>Locations stay fixed for navigation. Distance does not measure similarity. Connections show recorded structure or shared mentions.</p></div>}
    <div className={styles.keyboard}><label htmlFor="map-node-keyboard">Navigate visible sources</label><select id="map-node-keyboard" value="" onChange={event => { const node = current.current.nodes.find(item => item.id === event.target.value); if (node) { if (node.type === 'group') void fly(node.id); else { selected.current = node.id; callbacks.current.onSelect(node); draw(); } } }}><option value="">Choose a visible source</option>{accessible.map(node => <option key={node.id} value={node.id}>{names[node.type]}: {clip(node.label, 70)}</option>)}</select></div>
  </div>;
}
