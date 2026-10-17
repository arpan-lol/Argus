'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Expand, HelpCircle, Loader2, LocateFixed, Minimize2, Minus, Plus, RotateCcw } from 'lucide-react';
import styles from './GraphMap.module.css';
import { ConnectionPaths, type ConnectionPath } from './ConnectionPaths';

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
type Neighborhood = { nodes: MapNode[]; edges: MapEdge[]; paths: ConnectionPath[]; truncated?: boolean; status?: string; note?: string };
type ScreenEdge = { edge: MapEdge; points: { x: number; y: number }[]; minX: number; maxX: number; minY: number; maxY: number };
type Props = {
  mode?: 'network' | 'grouped';
  expanded?: boolean;
  onExpand?: () => void;
  focus?: { nodeId: string; nonce: number } | null;
  onSelect: (node: MapNode) => void;
  onFocus?: (focus: { documentId?: string; sectionId?: string; chunkId?: string }) => void;
};

const names = { group: 'Source group', document: 'File', section: 'Heading', chunk: 'Chunk', entity: 'Shared name' };
const colors = { group: '#b99540', document: '#c6a34f', section: '#869ab2', chunk: '#5b9b88', entity: '#a187b5' };
const empty: MapView = { nodes: [], edges: [], level: 'overview' };
const clip = (text: string, size = 34) => text.length > size ? `${text.slice(0, size - 1)}…` : text;
const scale = (zoom: number) => Math.max(.003, Math.min(7, zoom));
const edgeMeaning = (edge: MapEdge) => {
  const labels = Array.isArray(edge.labels) ? edge.labels.filter(label => typeof label === 'string').join(', ') : '';
  const meanings: Record<string, [string, string]> = {
    HAS_SECTION: ['Contains heading', 'This heading belongs to the connected document.'],
    HAS_CHUNK: ['Contains chunk', 'This passage belongs to the connected heading.'],
    NEXT_CHUNK: ['Next chunk', 'The arrow follows reading order within the same source section.'],
    MENTIONS: ['Mentions', 'This passage mentions the connected name. This does not establish a scientific relationship.'],
    SHARES_TERM: ['Shared name · summarized', labels ? `Shared mentions: ${labels}. This is a navigation summary, not agreement between sources.` : 'A summary of a shared-mention path, not agreement between sources.'],
  };
  return meanings[edge.type] || ['Source connection', 'A recorded relationship between these sources.'];
};

async function request<T>(path: string, signal?: AbortSignal, mode = 'network'): Promise<T> {
  const response = await fetch(`/api/map${path}${path.includes('?') ? '&' : '?'}mode=${mode}`, { cache: 'no-store', signal });
  if (!response.ok) throw new Error('The source map could not load. Retry when the server is available.');
  return response.json();
}

export function GraphMap({ focus, onSelect, onFocus, mode = 'network', expanded = false, onExpand }: Props) {
  const mapRequest = useCallback(<T,>(path: string, signal?: AbortSignal) => request<T>(path, signal, mode), [mode]);
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const camera = useRef<Camera>({ x: 0, y: 0, zoom: .015 });
  const dimensions = useRef({ width: 800, height: 700 });
  const world = useRef<Bounds | null>(null);
  const overview = useRef<MapView>(empty);
  const neighborhood = useRef<Neighborhood | null>(null);
  const activePath = useRef<ConnectionPath | null>(null);
  const neighborhoodRequest = useRef<AbortController | null>(null);
  const navigationSequence = useRef(0);
  const readyMode = useRef<string | null>(null);
  const modeCameras = useRef<Partial<Record<'network' | 'grouped', Camera>>>({});
  const fitted = useRef(false);
  const current = useRef<MapView>(empty);
  const screenNodes = useRef<{ node: MapNode; x: number; y: number; radius: number }[]>([]);
  const screenEdges = useRef<ScreenEdge[]>([]);
  const hoveredEdge = useRef<string | null>(null);
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
  const [edgeTooltip, setEdgeTooltip] = useState<{ edge: MapEdge; x: number; y: number } | null>(null);
  const [help, setHelp] = useState(false);
  const [zoomLabel, setZoomLabel] = useState('Overview');
  const [reload, setReload] = useState(0);
  const [truncated, setTruncated] = useState(false);
  const [accessible, setAccessible] = useState<MapNode[]>([]);
  const [connections, setConnections] = useState<Neighborhood | null>(null);
  const [connectionsLoading, setConnectionsLoading] = useState(false);
  const [connectionsError, setConnectionsError] = useState<string | null>(null);
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [activeConnection, setActiveConnection] = useState<ConnectionPath | null>(null);

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
    const desired = c.zoom < .08 ? 'overview' : c.zoom < .45 ? 'documents' : 'detail';
    const view = desired === 'overview' ? overview.current : current.current;
    const linked = neighborhood.current;
    const nodes = [...new Map([...view.nodes, ...(linked?.nodes || [])].map(node => [node.id, node])).values()];
    const linkIds = new Set(linked?.nodes.map(node => node.id) || []);
    const path = activePath.current;
    const pathIds = new Set(path ? [path.sourceChunkId, path.entityId, path.targetChunkId] : []);
    const projected = new Map(nodes.map(node => [node.id, { node, x: (node.x - c.x) * c.zoom + width / 2, y: (node.y - c.y) * c.zoom + height / 2 }]));
    context.lineCap = 'round';
    screenEdges.current = [];
    for (const edge of new Map([...view.edges, ...(linked?.edges || [])].map(edge => [edge.id, edge])).values()) {
      const a = projected.get(edge.source), b = projected.get(edge.target);
      if (!a || !b) continue;
      if ((a.x < -30 && b.x < -30) || (a.x > width + 30 && b.x > width + 30) || (a.y < -30 && b.y < -30) || (a.y > height + 30 && b.y > height + 30)) continue;
      const pathEdge = edge.type === 'MENTIONS' && (path ? pathIds.has(edge.source) && pathIds.has(edge.target) : linkIds.has(edge.source) && linkIds.has(edge.target));
      const active = pathEdge || edge.id === hoveredEdge.current || [path ? null : selected.current, hovered.current].some(id => id && (edge.source === id || edge.target === id));
      const branch = edge.type === 'HAS_SECTION' || edge.type === 'HAS_CHUNK';
      context.strokeStyle = active ? (dark ? '#dfc374' : '#88702c') : branch ? (dark ? '#80968a' : '#7c9284') : (dark ? '#64796b' : '#92a497');
      context.lineWidth = pathEdge ? 2.3 : active ? 1.9 : desired === 'overview' ? .6 : branch ? 1.25 : 1;
      context.globalAlpha = desired === 'overview' && !active ? .32 : 1;
      context.setLineDash(edge.derived || edge.type === 'SHARES_TERM' || edge.type === 'SHARED_MENTION' ? [3, 4] : []);
      context.beginPath(); context.moveTo(a.x, a.y);
      if (branch) {
        const junction = a.y + (b.y - a.y) * .52;
        context.bezierCurveTo(a.x, junction, b.x, junction, b.x, b.y);
      } else if (edge.type === 'NEXT_CHUNK') {
        const bend = Math.min(28, Math.abs(b.x - a.x) * .25 + 9);
        context.bezierCurveTo(a.x, a.y + bend, b.x, b.y + bend, b.x, b.y);
      } else context.lineTo(b.x, b.y);
      context.stroke();
      const points = Array.from({ length: branch || edge.type === 'NEXT_CHUNK' ? 13 : 2 }, () => ({ x: 0, y: 0 }));
      const count = points.length - 1;
      for (let index = 0; index <= count; index++) {
        const t = index / count, u = 1 - t;
        const bend = Math.min(28, Math.abs(b.x - a.x) * .25 + 9);
        const c1 = branch ? { x: a.x, y: a.y + (b.y - a.y) * .52 } : { x: a.x, y: a.y + bend };
        const c2 = branch ? { x: b.x, y: a.y + (b.y - a.y) * .52 } : { x: b.x, y: b.y + bend };
        points[index] = branch || edge.type === 'NEXT_CHUNK' ? { x: u ** 3 * a.x + 3 * u ** 2 * t * c1.x + 3 * u * t ** 2 * c2.x + t ** 3 * b.x, y: u ** 3 * a.y + 3 * u ** 2 * t * c1.y + 3 * u * t ** 2 * c2.y + t ** 3 * b.y } : { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
      }
      screenEdges.current.push({ edge, points, minX: Math.min(...points.map(point => point.x)) - 5, maxX: Math.max(...points.map(point => point.x)) + 5, minY: Math.min(...points.map(point => point.y)) - 5, maxY: Math.max(...points.map(point => point.y)) + 5 });
      if (edge.id === hoveredEdge.current && !edge.derived) {
        const previous = points[points.length - 2], last = points[points.length - 1];
        const angle = Math.atan2(last.y - previous.y, last.x - previous.x);
        const tip = { x: last.x - Math.cos(angle) * 9, y: last.y - Math.sin(angle) * 9 };
        context.beginPath(); context.moveTo(tip.x, tip.y);
        context.lineTo(tip.x - Math.cos(angle - .5) * 8, tip.y - Math.sin(angle - .5) * 8);
        context.lineTo(tip.x - Math.cos(angle + .5) * 8, tip.y - Math.sin(angle + .5) * 8);
        context.closePath(); context.fillStyle = context.strokeStyle; context.fill();
      }
    }
    context.globalAlpha = 1;
    context.setLineDash([]);
    screenNodes.current = [];
    for (const point of projected.values()) {
      const { node, x, y } = point;
      if (x < -100 || y < -70 || x > width + 100 || y > height + 70) continue;
      const active = node.id === selected.current || node.id === hovered.current || pathIds.has(node.id);
      const group = node.type === 'group';
      const coarse = desired === 'overview' && !group && !(path ? pathIds.has(node.id) : linkIds.has(node.id)) && !active;
      const radius = group ? Math.max(7, Math.min(17, c.zoom * 4096 * .33)) : coarse ? 1 : node.type === 'document' ? 7 : node.type === 'entity' ? 6 : 4.5;
      screenNodes.current.push({ node, x, y, radius: radius + (coarse ? 2 : 7) });
      if (coarse) {
        context.beginPath(); context.arc(x, y, radius, 0, Math.PI * 2);
        context.fillStyle = dark ? '#829082' : '#7d8c7e'; context.fill();
        continue;
      }
      context.beginPath(); context.arc(x, y, radius + (active ? 4 : 0), 0, Math.PI * 2);
      context.fillStyle = active ? (dark ? '#655a39' : '#f0e8c9') : (dark ? '#202723' : '#fff'); context.fill();
      context.strokeStyle = colors[node.type]; context.lineWidth = active ? 2 : 1.2; context.stroke();
      if (group) {
        context.font = `600 ${radius < 12 ? 9 : 11}px sans-serif`; context.textAlign = 'center'; context.textBaseline = 'middle';
        context.fillStyle = dark ? '#e8d49e' : '#725d26'; context.fillText(String(node.count || ''), x, y);
      } else if (!coarse) {
        context.beginPath(); context.arc(x, y, Math.max(2, radius - 3), 0, Math.PI * 2); context.fillStyle = colors[node.type]; context.fill();
      }
      const showLabel = path ? pathIds.has(node.id) || node.id === hovered.current : active || (linkIds.has(node.id) && node.type !== 'section') || (node.type === 'document' && (c.zoom > .12 || projected.size < 30)) || (node.type === 'entity' && projected.size < 100);
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
    fitted.current = false;
    camera.current = { ...next, zoom: scale(next.zoom) };
    setZoomLabel(next.zoom < .08 ? 'Overview' : next.zoom < .45 ? 'Files' : 'Inside sources');
    draw();
  }, [draw]);

  const fit = useCallback(() => {
    if (!world.current) return;
    cancelAnimationFrame(animation.current);
    const b = world.current, { width, height } = dimensions.current;
    move({ x: (b.minX + b.maxX) / 2, y: (b.minY + b.maxY) / 2, zoom: Math.min(width / Math.max(1, b.maxX - b.minX), height / Math.max(1, b.maxY - b.minY)) * .82 });
    fitted.current = true;
  }, [move]);

  const travel = useCallback((target: Camera) => {
      const from = { ...camera.current };
      cancelAnimationFrame(animation.current);
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { move(target); return; }
      const distance = Math.hypot(target.x - from.x, target.y - from.y);
      const travelZoom = scale(Math.min(from.zoom, target.zoom, Math.min(dimensions.current.width, dimensions.current.height) / Math.max(distance * 1.4, 1)));
      const zoomOutMs = distance > 600 ? 480 : 210;
      const panMs = distance > 600 ? Math.min(2400, 1200 + Math.sqrt(distance) * 5) : 650;
      const zoomInMs = distance > 600 ? 560 : 245;
      const started = performance.now(), duration = zoomOutMs + panMs + zoomInMs;
      const ease = (n: number) => 1 - Math.pow(1 - n, 3);
      const smooth = (n: number) => n * n * (3 - 2 * n);
      const interpolate = (a: number, b: number, amount: number) => a + (b - a) * amount;
      const frame = (now: number) => {
        if (disposed.current) return;
        const elapsed = Math.min(duration, now - started);
        const pan = smooth(Math.max(0, Math.min(1, (elapsed - zoomOutMs) / panMs)));
        const zoom = elapsed < zoomOutMs ? Math.exp(interpolate(Math.log(from.zoom), Math.log(travelZoom), ease(elapsed / zoomOutMs))) : elapsed > zoomOutMs + panMs ? Math.exp(interpolate(Math.log(travelZoom), Math.log(target.zoom), ease((elapsed - zoomOutMs - panMs) / zoomInMs))) : travelZoom;
        move({ x: interpolate(from.x, target.x, pan), y: interpolate(from.y, target.y, pan), zoom });
        if (elapsed < duration) animation.current = requestAnimationFrame(frame);
      };
      animation.current = requestAnimationFrame(frame);
  }, [move]);

  const clearConnections = useCallback(() => {
    neighborhoodRequest.current?.abort();
    neighborhood.current = null; activePath.current = null;
    setActiveConnection(null);
    setConnections(null); setConnectionsOpen(false); setConnectionsLoading(false);
    draw();
  }, [draw]);

  const loadConnections = useCallback(async (nodeId: string) => {
    neighborhoodRequest.current?.abort();
    const controller = new AbortController(); neighborhoodRequest.current = controller;
    neighborhood.current = null; activePath.current = null;
    setActiveConnection(null);
    setConnections(null); setConnectionsError(null); setConnectionsOpen(true); setConnectionsLoading(true);
    try {
      const result = await mapRequest<Neighborhood>(`/neighborhood/${encodeURIComponent(nodeId)}`, controller.signal);
      if (disposed.current || controller.signal.aborted) return;
      neighborhood.current = result; setConnections(result);
      if (result.status && result.status !== 'ready') setConnectionsError(result.note || 'Connections are unavailable.');
      draw();
    } catch (failure) {
      if (!controller.signal.aborted && !disposed.current) setConnectionsError(failure instanceof Error ? failure.message : 'Connections are unavailable.');
    } finally { if (!controller.signal.aborted && !disposed.current) setConnectionsLoading(false); }
  }, [draw, mapRequest]);

  const fly = useCallback(async (nodeId: string) => {
    const sequence = ++navigationSequence.current;
    try {
      const destination = await mapRequest<{ node: MapNode; zoom: number; documentId?: string; sectionId?: string; chunkId?: string }>(`/locate/${encodeURIComponent(nodeId)}`);
      if (disposed.current || sequence !== navigationSequence.current) return;
      const node = destination.node;
      callbacks.current.onFocus?.({ documentId: destination.documentId || node.documentId, sectionId: destination.sectionId || node.sectionId, chunkId: destination.chunkId || node.chunkId });
      selected.current = node.id;
      if (node.type === 'chunk') void loadConnections(node.id); else clearConnections();
      travel({ x: node.x, y: node.y, zoom: destination.zoom });
    } catch (failure) { if (!disposed.current) setError(failure instanceof Error ? failure.message : 'Unable to find this source.'); }
  }, [travel, loadConnections, clearConnections, mapRequest]);

  const connectionCamera = useCallback((path: ConnectionPath): Camera | null => {
    const ids = new Set([path.sourceChunkId, path.entityId, path.targetChunkId]);
    const nodes = neighborhood.current?.nodes.filter(node => ids.has(node.id)) || [];
    if (nodes.length < 3) return null;
    const xs = nodes.map(node => node.x), ys = nodes.map(node => node.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const { width, height } = dimensions.current;
    const zoom = scale(Math.min(width * .68 / Math.max(200, maxX - minX), height * .48 / Math.max(180, maxY - minY), .9));
    return { x: (minX + maxX) / 2, y: (minY + maxY) / 2 + height * .12 / zoom, zoom };
  }, []);

  const followConnection = (path: ConnectionPath) => {
    activePath.current = path; setActiveConnection(path);
    const target = connectionCamera(path);
    if (target) travel(target);
  };

  const activate = (node: MapNode) => {
    if (node.type === 'group') { void fly(node.id); return; }
    if (node.type === 'document' && camera.current.zoom < .45) { void fly(node.id); return; }
    selected.current = node.id;
    if (node.type === 'chunk') void loadConnections(node.id);
    callbacks.current.onSelect(node); draw();
  };

  useEffect(() => {
    disposed.current = false;
    readyMode.current = null; ++navigationSequence.current;
    setLoading(true); setError(null); clearConnections();
    world.current = null; overview.current = empty; current.current = empty;
    setAccessible([]); setTooltip(null); setEdgeTooltip(null); hovered.current = null; hoveredEdge.current = null;
    let active = true;
    const element = host.current;
    if (!element) return;
    const initialBounds = element.getBoundingClientRect();
    dimensions.current = { width: initialBounds.width, height: initialBounds.height };
    const resize = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      dimensions.current = { width, height };
      if (canvas.current) {
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        canvas.current.width = width * ratio; canvas.current.height = height * ratio;
        canvas.current.getContext('2d')?.setTransform(ratio, 0, 0, ratio, 0, 0);
      }
      if (fitted.current) fit();
      else if (activePath.current) {
        const target = connectionCamera(activePath.current);
        if (target) { cancelAnimationFrame(animation.current); move(target); } else draw();
      } else draw();
    });
    resize.observe(element);
    const theme = new MutationObserver(draw); theme.observe(window.document.documentElement, { attributes: true, attributeFilter: ['class'] });
    const controller = new AbortController();
    mapRequest<{ bounds: Bounds; nodes?: MapNode[]; groups?: MapNode[]; edges?: MapEdge[] }>('/overview', controller.signal).then(result => {
      if (!active) return;
      world.current = result.bounds; overview.current = { nodes: result.nodes || result.groups || [], edges: result.edges || [], level: 'overview' };
      const saved = modeCameras.current[mode];
      if (saved) move(saved); else fit();
      readyMode.current = mode; setLoading(false);
    }).catch(failure => { if (active) { setError(failure.message); setLoading(false); } });
    return () => { modeCameras.current[mode] = { ...camera.current }; active = false; disposed.current = true; controller.abort(); neighborhoodRequest.current?.abort(); resize.disconnect(); theme.disconnect(); cancelAnimationFrame(animation.current); };
  }, [draw, fit, move, connectionCamera, clearConnections, mapRequest, mode, reload]);

  useEffect(() => {
    let active = true, controller: AbortController | null = null, previous = '', sequence = 0, pending = false;
    const load = () => {
      if (!world.current || pending) return;
      const c = camera.current, { width, height } = dimensions.current;
      const bounds = { minX: Math.floor(c.x - width * .65 / c.zoom), maxX: Math.ceil(c.x + width * .65 / c.zoom), minY: Math.floor(c.y - height * .65 / c.zoom), maxY: Math.ceil(c.y + height * .65 / c.zoom) };
      const query = new URLSearchParams({ ...Object.fromEntries(Object.entries(bounds).map(([key, value]) => [key, String(value)])), zoom: String(c.zoom), limit: '800' }).toString();
      if (query === previous) return;
      if (c.zoom < .08) {
        previous = query; current.current = overview.current; setTruncated(false);
        const nearest = overview.current.nodes.filter(node => node.x >= bounds.minX && node.x <= bounds.maxX && node.y >= bounds.minY && node.y <= bounds.maxY).sort((a, b) => Math.hypot(a.x - c.x, a.y - c.y) - Math.hypot(b.x - c.x, b.y - c.y));
        setAccessible(nearest.slice(0, 100)); draw(); return;
      }
      previous = query; controller = new AbortController(); pending = true;
      const requestNumber = ++sequence;
      mapRequest<MapView>(`/view?${query}`, controller.signal).then(view => {
        if (!active || sequence !== requestNumber) return;
        current.current = view; setTruncated(!!view.truncated); setAccessible(view.nodes.slice(0, 200)); setError(null); setLoading(false); draw();
      }).catch(failure => { if (active && failure.name !== 'AbortError') { setError(failure.message); previous = ''; } }).finally(() => { pending = false; });
    };
    const interval = window.setInterval(load, 180); load();
    return () => { active = false; window.clearInterval(interval); controller?.abort(); };
  }, [draw, mapRequest, reload]);

  useEffect(() => { if (!loading && readyMode.current === mode && focus?.nodeId) void fly(focus.nodeId); }, [focus?.nodeId, focus?.nonce, fly, loading, mode]);

  const hit = (x: number, y: number) => [...screenNodes.current].reverse().find(point => Math.hypot(point.x - x, point.y - y) <= point.radius)?.node;
  const hitEdge = (x: number, y: number) => {
    for (const item of [...screenEdges.current].reverse()) {
      if (x < item.minX || x > item.maxX || y < item.minY || y > item.maxY) continue;
      for (let index = 1; index < item.points.length; index++) {
        const a = item.points[index - 1], b = item.points[index], dx = b.x - a.x, dy = b.y - a.y;
        const t = Math.max(0, Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / Math.max(1, dx * dx + dy * dy)));
        if (Math.hypot(x - a.x - t * dx, y - a.y - t * dy) <= 4) return item.edge;
      }
    }
    return null;
  };
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
          drag.x = event.clientX; drag.y = event.clientY; setTooltip(null); setEdgeTooltip(null); hoveredEdge.current = null; event.currentTarget.style.cursor = 'grabbing';
        } else {
          const node = hit(x, y); hovered.current = node?.id || null;
          const edge = node ? null : hitEdge(x, y); hoveredEdge.current = edge?.id || null;
          setTooltip(node ? { node, x: Math.min(dimensions.current.width - 220, Math.max(8, x + 16)), y: Math.max(8, Math.min(dimensions.current.height - 80, y + 16)) } : null);
          setEdgeTooltip(edge ? { edge, x: Math.min(dimensions.current.width - 220, Math.max(8, x + 16)), y: Math.max(8, Math.min(dimensions.current.height - 150, y + 16)) } : null);
          event.currentTarget.style.cursor = node ? 'pointer' : edge ? 'help' : 'grab'; draw();
        }
      }}
      onPointerUp={event => {
        const drag = dragging.current; dragging.current = null;
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
        event.currentTarget.style.cursor = 'grab';
        if (!drag?.moved) {
          const rect = event.currentTarget.getBoundingClientRect(), node = hit(event.clientX - rect.left, event.clientY - rect.top);
          if (node) activate(node);
        }
      }}
      onPointerCancel={() => { dragging.current = null; }}
      onPointerLeave={() => { if (!dragging.current) { hovered.current = null; hoveredEdge.current = null; setTooltip(null); setEdgeTooltip(null); draw(); } }}
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
        if (event.key === 'Enter') { const node = [...current.current.nodes, ...(neighborhood.current?.nodes || [])].find(item => item.id === selected.current); if (node) activate(node); }
      }} />
    <div className={styles.legend}><span className={styles.level}>{zoomLabel}</span><span><i style={{ background: colors.document }} />Files</span><span><i style={{ background: colors.chunk }} />Chunks</span><span><i style={{ background: colors.entity }} />Shared names</span></div>
    {tooltip && <div className={styles.tooltip} style={{ left: tooltip.x, top: tooltip.y }}><small>{names[tooltip.node.type]}</small><strong>{clip(tooltip.node.preview || tooltip.node.label, 100)}</strong></div>}
    {edgeTooltip && <div className={styles.tooltip} role="tooltip" style={{ left: edgeTooltip.x, top: edgeTooltip.y }}><strong>{edgeMeaning(edgeTooltip.edge)[0]}</strong><p>{edgeMeaning(edgeTooltip.edge)[1]}</p></div>}
    {loading && <div className={styles.notice} role="status"><Loader2 size={15} className={styles.spin} />Opening source map…</div>}
    {error && <div className={styles.error} role="alert"><span>{error}</span><button onClick={() => { setError(null); setReload(value => value + 1); }}><RotateCcw size={13} />Retry</button></div>}
    {truncated && !error && !connectionsOpen && <div className={styles.limit}>Zoom in to reveal more sources</div>}
    {connectionsOpen && <ConnectionPaths paths={connections?.paths || []} loading={connectionsLoading} error={connectionsError} truncated={connections?.truncated} activeTargetChunkId={activeConnection?.targetChunkId} onFollow={followConnection} onClose={clearConnections} />}
    <div className={styles.controls}><button aria-label="Zoom in" onClick={() => zoomBy(1.7)}><Plus size={16} /></button><button aria-label="Zoom out" onClick={() => zoomBy(1 / 1.7)}><Minus size={16} /></button>{onExpand && <button aria-label={expanded ? 'Collapse Source Explorer' : 'Expand Source Explorer'} onClick={onExpand}>{expanded ? <Minimize2 size={15} /> : <Expand size={15} />}</button>}<button aria-label="Show whole source map" onClick={fit}><LocateFixed size={15} /></button><button aria-label="About the source map" aria-expanded={help} onClick={() => setHelp(value => !value)}><HelpCircle size={16} /></button></div>
    {help && <div className={styles.help}><strong>Your sources, connected</strong><p>{mode === 'grouped' ? 'Groups organize documents for navigation. Zoom in for document trees; group membership is not a topic classification.' : 'Each point is a document. Their arrangement follows shared names; it is not a topic classification.'}</p><dl className={styles.edgeMeanings}><div><dt>Contains</dt><dd>Document → heading → chunk.</dd></div><div><dt>Next chunk</dt><dd>Reading order within a section.</dd></div><div><dt>Mentions</dt><dd>A chunk names this entity.</dd></div><div><dt>Shared name · dashed</dt><dd>A summarized shared-mention path.</dd></div></dl><p>These links describe structure and mentions. They do not establish agreement, contradiction, or a scientific relationship.</p></div>}
    <div className={styles.keyboard}><label htmlFor="map-node-keyboard">Navigate visible sources</label><select id="map-node-keyboard" value="" onChange={event => { const node = [...current.current.nodes, ...(neighborhood.current?.nodes || [])].find(item => item.id === event.target.value); if (node) activate(node); }}><option value="">Choose a visible source</option>{[...new Map([...accessible, ...(connections?.nodes || [])].map(node => [node.id, node])).values()].map(node => <option key={node.id} value={node.id}>{names[node.type]}: {clip(node.label, 70)}</option>)}</select></div>
  </div>;
}
