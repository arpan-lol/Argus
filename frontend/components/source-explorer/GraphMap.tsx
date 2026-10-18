'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Expand, HelpCircle, Loader2, LocateFixed, Minimize2, Minus, Plus, RotateCcw } from 'lucide-react';
import styles from './GraphMap.module.css';
import { ConnectionPaths, type ConnectionPath } from './ConnectionPaths';

export type MapNode = {
  id: string; type: 'document' | 'section' | 'chunk' | 'entity';
  label: string; preview?: string; x: number; y: number; radius?: number;
  documentId?: string; sectionId?: string; chunkId?: string; count?: number;
  [key: string]: unknown;
};
type Bounds = { minX: number; minY: number; maxX: number; maxY: number };
type MapEdge = { id: string; source: string; target: string; type: string; derived?: boolean; [key: string]: unknown };
type MapView = { nodes: MapNode[]; edges: MapEdge[]; level: string; truncated?: boolean; summaryTruncated?: boolean; source?: string; status?: string };
type Camera = { x: number; y: number; zoom: number };
type Neighborhood = { nodes: MapNode[]; edges: MapEdge[]; paths: ConnectionPath[]; truncated?: boolean; status?: string; note?: string };
type ScreenEdge = { edge: MapEdge; points: { x: number; y: number }[]; minX: number; maxX: number; minY: number; maxY: number };
type Props = {
  apiRoot?: string;
  refreshToken?: number;
  expanded?: boolean;
  onExpand?: () => void;
  focus?: { nodeId: string; nonce: number } | null;
  onSelect: (node: MapNode) => void;
  onFocus?: (focus: { documentId?: string; sectionId?: string; chunkId?: string }) => void;
};

const names = { document: 'Document', section: 'Section', chunk: 'Chunk', entity: 'Entity' };
const colors = { document: '#31edae', section: '#869ab2', chunk: '#5b9b88', entity: '#a187b5' };
const empty: MapView = { nodes: [], edges: [], level: 'overview' };
const mergeViews = (previous: MapView, next: MapView): MapView => {
  const nodes = [...new Map([...previous.nodes, ...next.nodes].map(node => [node.id, node])).values()].slice(-3000);
  const ids = new Set(nodes.map(node => node.id));
  const edges = [...new Map([...previous.edges, ...next.edges].map(edge => [edge.id, edge])).values()].filter(edge => ids.has(edge.source) && ids.has(edge.target)).slice(-12000);
  return { ...next, nodes, edges };
};
const boundedView = (view: MapView, camera: Camera, dimensions: { width: number; height: number }, keep: Set<string> = new Set()) => {
  const marginX = dimensions.width * .9 / camera.zoom, marginY = dimensions.height * .9 / camera.zoom;
  const visible = view.nodes.filter(node => keep.has(node.id) || (Math.abs(node.x - camera.x) <= marginX && Math.abs(node.y - camera.y) <= marginY));
  visible.sort((a, b) => Number(keep.has(b.id)) - Number(keep.has(a.id)) || Math.hypot(a.x - camera.x, a.y - camera.y) - Math.hypot(b.x - camera.x, b.y - camera.y));
  const nodeLimit = Math.max(400, Math.min(1600, Math.floor(dimensions.width * dimensions.height / 170)));
  const nodes = visible.slice(0, nodeLimit);
  const ids = new Set(nodes.map(node => node.id));
  const edges = view.edges.filter(edge => ids.has(edge.source) && ids.has(edge.target)).sort((a, b) => {
    const score = (edge: MapEdge) => (edge.type === 'RELATES' ? 0 : edge.type === 'SHARES_ENTITY' || edge.derived ? 2 : 1) + (keep.has(edge.source) || keep.has(edge.target) ? -1 : 0);
    return score(a) - score(b);
  });
  const edgeLimit = Math.max(900, Math.min(3600, nodeLimit * 2));
  return { ...view, nodes, edges: edges.slice(0, edgeLimit), truncated: !!view.truncated || visible.length > nodes.length || edges.length > edgeLimit };
};
const viewQuery = (target: Camera, width: number, height: number) => new URLSearchParams({
  minX: String(Math.floor(target.x - width * .7 / target.zoom)), maxX: String(Math.ceil(target.x + width * .7 / target.zoom)),
  minY: String(Math.floor(target.y - height * .7 / target.zoom)), maxY: String(Math.ceil(target.y + height * .7 / target.zoom)),
  zoom: String(target.zoom), limit: '1000',
}).toString();
const viewportQuery = (target: Camera, width: number, height: number) => {
  const bounds = { minX: Math.floor(target.x - width * .65 / target.zoom), maxX: Math.ceil(target.x + width * .65 / target.zoom), minY: Math.floor(target.y - height * .65 / target.zoom), maxY: Math.ceil(target.y + height * .65 / target.zoom) };
  return { bounds, query: new URLSearchParams({ ...Object.fromEntries(Object.entries(bounds).map(([key, value]) => [key, String(value)])), zoom: String(target.zoom), limit: '800' }).toString() };
};
const clip = (text: string, size = 34) => text.length > size ? `${text.slice(0, size - 1)}…` : text;
const scale = (zoom: number) => Math.max(.003, Math.min(7, zoom));
const edgeMeaning = (edge: MapEdge) => {
  if (edge.type === 'RELATES') return [String(edge.predicate || 'Related to'), 'An extracted relationship. Open its source to inspect supporting text and conditions.'];
  const labels = Array.isArray(edge.labels) ? edge.labels.filter(label => typeof label === 'string').join(', ') : '';
  const meanings: Record<string, [string, string]> = {
    HAS_SECTION: ['Contains heading', 'This heading belongs to the connected document.'],
    HAS_CHUNK: ['Contains chunk', 'This passage belongs to the connected heading.'],
    NEXT_CHUNK: ['Next chunk', 'The arrow follows reading order within the same source document.'],
    MENTIONS: ['Mentions', 'This passage mentions the connected entity. The edge records a source occurrence.'],
    SHARES_ENTITY: ['Shared entity · derived', labels ? `Both documents reference these entities: ${labels}. Derived document summary.` : 'Derived summary of documents referencing common entities.'],
  };
  return meanings[edge.type] || ['Source connection', 'A recorded relationship between these sources.'];
};

async function request<T>(path: string, signal?: AbortSignal, apiRoot = ''): Promise<T> {
  const response = await fetch(`/api${apiRoot}/map${path}`, { cache: 'no-store', signal });
  if (!response.ok) throw new Error('The source map could not load. Retry when the server is available.');
  return response.json();
}

export function GraphMap({ apiRoot = '', refreshToken = 0, focus, onSelect, onFocus, expanded = false, onExpand }: Props) {
  const mapRequest = useCallback(<T,>(path: string, signal?: AbortSignal) => request<T>(path, signal, apiRoot), [apiRoot]);
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
  const mapGeneration = useRef(0);
  const refreshSequence = useRef(0);
  const refreshRequest = useRef<AbortController | null>(null);
  const overviewRequest = useRef<AbortController | null>(null);
  const viewportRequest = useRef<AbortController | null>(null);
  const viewportRequestKey = useRef('');
  const observedRefreshToken = useRef(refreshToken);
  const viewportEffectRefreshToken = useRef(refreshToken);
  const ready = useRef(false);
  const fitted = useRef(false);
  const current = useRef<MapView>(empty);
  const screenNodes = useRef<{ node: MapNode; x: number; y: number; radius: number }[]>([]);
  const screenEdges = useRef<ScreenEdge[]>([]);
  const hoveredEdge = useRef<string | null>(null);
  const selected = useRef<string | null>(null);
  const hovered = useRef<string | null>(null);
  const dragging = useRef<{ x: number; y: number; startX: number; startY: number; moved: boolean } | null>(null);
  const animation = useRef(0);
  const revealAnimation = useRef(0);
  const appeared = useRef(new Map<string, number>());
  const appearanceUntil = useRef(0);
  const renderLimitReached = useRef(false);
  const navigating = useRef(false);
  const travelingUntil = useRef(0);
  const [navigatingTo, setNavigatingTo] = useState(false);
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
  const [renderTruncated, setRenderTruncated] = useState(false);
  const [summaryTruncated, setSummaryTruncated] = useState(false);
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
    context.fillStyle = dark ? '#171918' : '#f4efe6';
    context.fillRect(0, 0, width, height);
    const step = 28;
    context.fillStyle = dark ? '#282c29' : '#e7dfd3';
    for (let x = ((-c.x * c.zoom) % step + step) % step; x < width; x += step) {
      for (let y = ((-c.y * c.zoom) % step + step) % step; y < height; y += step) context.fillRect(x, y, 1, 1);
    }
    const desired = c.zoom < .025 ? 'overview' : c.zoom < .12 ? 'documents' : 'detail';
    const view = mergeViews(overview.current, current.current);
    const now = performance.now();
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const opacity = (id: string) => {
      if (!appeared.current.has(id)) {
        appeared.current.set(id, now);
        appearanceUntil.current = Math.max(appearanceUntil.current, now + 340);
        if (appeared.current.size > 8192) appeared.current.delete(appeared.current.keys().next().value!);
      }
      return reducedMotion ? 1 : Math.min(1, .2 + (now - appeared.current.get(id)!) / 320);
    };
    const linked = neighborhood.current;
    const allNodes = [...new Map([...view.nodes, ...(linked?.nodes || [])].map(node => [node.id, node])).values()];
    const linkIds = new Set(linked?.nodes.map(node => node.id) || []);
    const path = activePath.current;
    const pathIds = new Set(path ? [path.sourceChunkId, path.entityId, path.targetChunkId] : []);
    const renderLimit = Math.max(400, Math.min(1600, Math.floor(width * height / 170)));
    const forcedIds = new Set([...pathIds, ...linkIds, selected.current, hovered.current].filter((id): id is string => !!id));
    const candidates = allNodes.filter(node => forcedIds.has(node.id) || ((node.x - c.x) * c.zoom + width / 2 >= -100 && (node.x - c.x) * c.zoom + width / 2 <= width + 100 && (node.y - c.y) * c.zoom + height / 2 >= -70 && (node.y - c.y) * c.zoom + height / 2 <= height + 70));
    candidates.sort((a, b) => Number(forcedIds.has(b.id)) - Number(forcedIds.has(a.id)) || Math.hypot(a.x - c.x, a.y - c.y) - Math.hypot(b.x - c.x, b.y - c.y));
    const visibleNodes = candidates.filter(node => forcedIds.has(node.id)).concat(candidates.filter(node => !forcedIds.has(node.id)).slice(0, Math.max(0, renderLimit - candidates.filter(node => forcedIds.has(node.id)).length)));
    const projected = new Map(visibleNodes.map(node => [node.id, { node, x: (node.x - c.x) * c.zoom + width / 2, y: (node.y - c.y) * c.zoom + height / 2 }]));
    const onScreen = (point: { x: number; y: number }) => point.x >= -100 && point.x <= width + 100 && point.y >= -70 && point.y <= height + 70;
    context.lineCap = 'round';
    screenEdges.current = [];
    const allEdges = [...new Map([...view.edges, ...(linked?.edges || [])].map(edge => [edge.id, edge])).values()];
    const eligibleEdges = allEdges.filter(edge => {
      const a = projected.get(edge.source), b = projected.get(edge.target);
      return !!a && !!b && (onScreen(a) || pathIds.has(edge.source)) && (onScreen(b) || pathIds.has(edge.target));
    });
    const priority = (edge: MapEdge) => edge.type === 'MENTIONS' && pathIds.has(edge.source) && pathIds.has(edge.target) ? 0 : forcedIds.has(edge.source) && forcedIds.has(edge.target) ? 1 : edge.type === 'RELATES' ? 2 : edge.type === 'SHARES_ENTITY' || edge.derived ? 4 : 3;
    eligibleEdges.sort((a, b) => priority(a) - priority(b));
    const edgeLimit = Math.max(900, Math.min(3600, renderLimit * 2));
    const atRenderLimit = candidates.length > renderLimit || eligibleEdges.length > edgeLimit;
    if (atRenderLimit !== renderLimitReached.current) {
      renderLimitReached.current = atRenderLimit;
      setRenderTruncated(atRenderLimit);
    }
    for (const edge of eligibleEdges.slice(0, edgeLimit)) {
      const a = projected.get(edge.source), b = projected.get(edge.target);
      if (!a || !b) continue;
      if ((a.x < -30 && b.x < -30) || (a.x > width + 30 && b.x > width + 30) || (a.y < -30 && b.y < -30) || (a.y > height + 30 && b.y > height + 30)) continue;
      const pathEdge = edge.type === 'MENTIONS' && (path ? pathIds.has(edge.source) && pathIds.has(edge.target) : linkIds.has(edge.source) && linkIds.has(edge.target));
      const active = pathEdge || edge.id === hoveredEdge.current || [path ? null : selected.current, hovered.current].some(id => id && (edge.source === id || edge.target === id));
      const branch = edge.type === 'HAS_SECTION' || edge.type === 'HAS_CHUNK';
      context.strokeStyle = active ? (dark ? '#31edae' : '#087a55') : branch ? (dark ? '#9aa79e' : '#c4bdae') : (dark ? '#a5afa8' : '#cbc4b8');
      context.lineWidth = pathEdge ? 2.3 : active ? 1.9 : desired === 'overview' ? .6 : branch ? 1.25 : 1;
      const derived = edge.derived || edge.type === 'SHARES_ENTITY' || edge.type === 'SHARED_MENTION';
      context.globalAlpha = (active ? 1 : derived ? (dark ? .34 : .34) : branch ? (dark ? .4 : .4) : (dark ? .38 : .38)) * opacity(edge.id);
      context.setLineDash(edge.derived || edge.type === 'SHARES_ENTITY' || edge.type === 'SHARED_MENTION' ? [3, 4] : []);
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
      context.globalAlpha = opacity(node.id);
      const coarse = projected.size > 160 && desired === 'overview' && !(path ? pathIds.has(node.id) : linkIds.has(node.id)) && !active;
      const radius = coarse ? 1 : node.type === 'document' ? 7 : node.type === 'entity' ? 6 : 4.5;
      screenNodes.current.push({ node, x, y, radius: radius + (coarse ? 2 : 7) });
      if (coarse) {
        context.beginPath(); context.arc(x, y, radius, 0, Math.PI * 2);
        context.fillStyle = dark ? '#829082' : '#7d8c7e'; context.fill();
        continue;
      }
      context.beginPath(); context.arc(x, y, radius + (active ? 4 : 0), 0, Math.PI * 2);
      context.fillStyle = active ? (dark ? '#655a39' : '#fffaf0') : colors[node.type]; context.fill();
      context.strokeStyle = active ? (dark ? '#31edae' : '#087a55') : (dark ? '#171918' : '#fffaf0'); context.lineWidth = active ? 2 : 1.5; context.stroke();
      const showLabel = path ? pathIds.has(node.id) || node.id === hovered.current : active || (linkIds.has(node.id) && node.type !== 'section') || (node.type === 'document' && (c.zoom > .12 || projected.size < 30)) || (node.type === 'entity' && projected.size < 100);
      if (showLabel) {
        const label = clip(node.label || node.preview || names[node.type], node.type === 'document' && c.zoom < .28 ? 14 : 31);
        context.font = `${active ? 600 : 400} 11px sans-serif`;
        const labelWidth = context.measureText(label).width + 12;
        context.fillStyle = dark ? '#1b211eed' : '#fffaf0ed';
        context.fillRect(x - labelWidth / 2, y + radius + 5, labelWidth, 20);
        context.fillStyle = dark ? '#d8dfd9' : '#4a564e'; context.textAlign = 'center'; context.textBaseline = 'middle';
        context.fillText(label, x, y + radius + 15);
      }
    }
    context.globalAlpha = 1;
    if (!reducedMotion && now < appearanceUntil.current) {
      cancelAnimationFrame(revealAnimation.current);
      revealAnimation.current = requestAnimationFrame(draw);
    }
  }, []);

  const move = useCallback((next: Camera) => {
    fitted.current = false;
    camera.current = { ...next, zoom: scale(next.zoom) };
    setZoomLabel(next.zoom < .025 ? 'Overview' : next.zoom < .12 ? 'Files' : 'Inside sources');
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
      const zoomOutMs = distance > 600 ? 180 : 100;
      const panMs = distance > 600 ? Math.min(650, 320 + Math.sqrt(distance) * 2) : 220;
      const zoomInMs = distance > 600 ? 620 : 460;
      const started = performance.now(), duration = zoomOutMs + panMs + zoomInMs;
      travelingUntil.current = started + duration;
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
    activePath.current = null;
    setActiveConnection(null);
    setConnectionsError(null); setConnectionsOpen(true); setConnectionsLoading(true);
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
    navigating.current = true; setNavigatingTo(true);
    try {
      const destination = await mapRequest<{ node: MapNode; zoom: number; documentId?: string; sectionId?: string; chunkId?: string }>(`/locate/${encodeURIComponent(nodeId)}`);
      if (disposed.current || sequence !== navigationSequence.current) return;
      const node = destination.node;
      callbacks.current.onFocus?.({ documentId: destination.documentId || node.documentId, sectionId: destination.sectionId || node.sectionId, chunkId: destination.chunkId || node.chunkId });
      selected.current = node.id;
      const target = { x: node.x, y: node.y, zoom: destination.zoom };
      const { width, height } = dimensions.current;
      const [detail] = await Promise.all([
        mapRequest<MapView>(`/view?${viewQuery(target, width, height)}`),
        node.type === 'chunk' || node.type === 'entity' ? loadConnections(node.id) : Promise.resolve(),
      ]);
      if (disposed.current || sequence !== navigationSequence.current) return;
      current.current = boundedView(mergeViews(current.current, detail), target, dimensions.current, new Set([node.id]));
      if (node.type !== 'chunk') clearConnections();
      draw();
      travel(target);
    } catch (failure) { if (!disposed.current && sequence === navigationSequence.current) setError(failure instanceof Error ? failure.message : 'Unable to find this source.'); }
    finally { if (sequence === navigationSequence.current) { navigating.current = false; setNavigatingTo(false); } }
  }, [travel, loadConnections, clearConnections, mapRequest, draw]);

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
    if (node.type === 'document' && camera.current.zoom < .45) { void fly(node.id); return; }
    selected.current = node.id;
    if (node.type === 'chunk' || node.type === 'entity') void loadConnections(node.id);
    callbacks.current.onSelect(node); draw();
  };

  useEffect(() => {
    const generation = ++mapGeneration.current;
    refreshRequest.current?.abort(); refreshRequest.current = null;
    viewportRequest.current?.abort(); viewportRequest.current = null;
    viewportRequestKey.current = '';
    ++refreshSequence.current;
    disposed.current = false;
    ready.current = false; ++navigationSequence.current;
    setLoading(true); setError(null); clearConnections();
    world.current = null; overview.current = empty; current.current = empty; appeared.current.clear(); appearanceUntil.current = 0;
    renderLimitReached.current = false; setRenderTruncated(false); setSummaryTruncated(false);
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
    overviewRequest.current = controller;
    mapRequest<{ bounds: Bounds; nodes?: MapNode[]; edges?: MapEdge[]; truncated?: boolean; summaryTruncated?: boolean }>('/overview', controller.signal).then(result => {
      if (!active || generation !== mapGeneration.current) return;
      world.current = result.bounds; overview.current = { nodes: result.nodes || [], edges: result.edges || [], level: 'overview', truncated: result.truncated, summaryTruncated: result.summaryTruncated };
      setTruncated(!!result.truncated);
      setSummaryTruncated(!!result.summaryTruncated);
      fit();
      ready.current = true; setLoading(false);
    }).catch(failure => { if (active && generation === mapGeneration.current && failure.name !== 'AbortError') { setError(failure.message); setLoading(false); } });
    return () => { active = false; disposed.current = true; controller.abort(); overviewRequest.current = null; refreshRequest.current?.abort(); viewportRequest.current?.abort(); neighborhoodRequest.current?.abort(); resize.disconnect(); theme.disconnect(); cancelAnimationFrame(animation.current); cancelAnimationFrame(revealAnimation.current); };
  }, [draw, fit, move, connectionCamera, clearConnections, mapRequest, reload]);

  useEffect(() => {
    let active = true, sequence = 0, pending = false;
    const generation = mapGeneration.current;
    if (viewportEffectRefreshToken.current !== refreshToken) {
      viewportEffectRefreshToken.current = refreshToken;
      viewportRequestKey.current = '';
    }
    const load = () => {
      if (!world.current || pending || navigating.current || performance.now() < travelingUntil.current) return;
      const c = camera.current, { width, height } = dimensions.current;
      const { bounds, query } = viewportQuery(c, width, height);
      const key = query;
      if (key === viewportRequestKey.current) return;
      if (c.zoom < .025 && overview.current.nodes.length > 100) {
        viewportRequestKey.current = key; setTruncated(!!overview.current.truncated);
        const nearest = overview.current.nodes.filter(node => node.x >= bounds.minX && node.x <= bounds.maxX && node.y >= bounds.minY && node.y <= bounds.maxY).sort((a, b) => Math.hypot(a.x - c.x, a.y - c.y) - Math.hypot(b.x - c.x, b.y - c.y));
        setAccessible(nearest.slice(0, 100)); draw(); return;
      }
      viewportRequestKey.current = key;
      viewportRequest.current?.abort();
      const controller = new AbortController(); viewportRequest.current = controller; pending = true;
      const requestNumber = ++sequence;
      mapRequest<MapView>(`/view?${query}`, controller.signal).then(view => {
        if (!active || generation !== mapGeneration.current || sequence !== requestNumber) return;
        current.current = boundedView(mergeViews(current.current, view), c, dimensions.current, new Set([selected.current, hovered.current, ...((neighborhood.current?.nodes || []).map(node => node.id))].filter((id): id is string => !!id)));
        setTruncated(!!view.truncated || !!overview.current.truncated || !!current.current.truncated); setSummaryTruncated(!!view.summaryTruncated); setAccessible(view.nodes.slice(0, 200)); setError(null); setLoading(false); draw();
      }).catch(failure => { if (active && generation === mapGeneration.current && failure.name !== 'AbortError') { setError(failure.message); viewportRequestKey.current = ''; } }).finally(() => { if (sequence === requestNumber) { pending = false; if (viewportRequest.current === controller) viewportRequest.current = null; } });
    };
    const interval = window.setInterval(load, 180); load();
    return () => { active = false; window.clearInterval(interval); viewportRequest.current?.abort(); };
  }, [draw, mapRequest, reload, refreshToken]);

  useEffect(() => {
    if (observedRefreshToken.current === refreshToken) return;
    observedRefreshToken.current = refreshToken;
    const generation = mapGeneration.current;
    const sequence = ++refreshSequence.current;
    const controller = new AbortController();
    refreshRequest.current?.abort();
    refreshRequest.current = controller;
    overviewRequest.current?.abort();
    overviewRequest.current = null;
    viewportRequest.current?.abort();
    const target = { ...camera.current };
    const { width, height } = dimensions.current;
    const { query } = viewportQuery(target, width, height);
    const preserve = new Set([selected.current, hovered.current, ...((neighborhood.current?.nodes || []).map(node => node.id))].filter((id): id is string => !!id));
    const hadDocuments = overview.current.nodes.length > 0;
    void Promise.all([
      mapRequest<{ bounds: Bounds; nodes?: MapNode[]; edges?: MapEdge[]; truncated?: boolean; summaryTruncated?: boolean }>('/overview', controller.signal),
      mapRequest<MapView>(`/view?${query}`, controller.signal),
    ]).then(([freshOverview, freshView]) => {
      if (controller.signal.aborted || generation !== mapGeneration.current || sequence !== refreshSequence.current) return;
      const overviewNodes = freshOverview.nodes || [];
      world.current = freshOverview.bounds;
      overview.current = { nodes: overviewNodes, edges: freshOverview.edges || [], level: 'overview', truncated: freshOverview.truncated, summaryTruncated: freshOverview.summaryTruncated };
      current.current = boundedView(mergeViews({ ...current.current, nodes: current.current.nodes.filter(node => preserve.has(node.id)), edges: current.current.edges.filter(edge => preserve.has(edge.source) && preserve.has(edge.target)) }, freshView), target, dimensions.current, preserve);
      viewportRequestKey.current = query;
      setTruncated(!!freshOverview.truncated || !!freshView.truncated || !!current.current.truncated);
      setSummaryTruncated(!!freshView.summaryTruncated || !!freshOverview.summaryTruncated);
      setAccessible(freshView.nodes.slice(0, 200));
      setError(null);
      setLoading(false);
      if (!hadDocuments && overviewNodes.length > 0) fit();
      draw();
    }).catch(failure => {
      if (!controller.signal.aborted && generation === mapGeneration.current && sequence === refreshSequence.current) {
        viewportRequestKey.current = '';
        setError(failure instanceof Error ? failure.message : 'The source map could not refresh.');
        setLoading(false);
      }
    }).finally(() => {
      if (refreshRequest.current === controller) refreshRequest.current = null;
    });
    return () => { controller.abort(); };
  }, [refreshToken, mapRequest, draw, fit]);

  useEffect(() => { if (!loading && ready.current && focus?.nodeId) void fly(focus.nodeId); }, [focus?.nodeId, focus?.nonce, fly, loading]);

  const hit = (x: number, y: number) => { for (let index = screenNodes.current.length - 1; index >= 0; index--) { const point = screenNodes.current[index]; if (Math.hypot(point.x - x, point.y - y) <= point.radius) return point.node; } return undefined; };
  const hitEdge = (x: number, y: number) => {
    for (let edgeIndex = screenEdges.current.length - 1; edgeIndex >= 0; edgeIndex--) {
      const item = screenEdges.current[edgeIndex];
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
        event.preventDefault(); travelingUntil.current = 0; cancelAnimationFrame(animation.current);
        const rect = event.currentTarget.getBoundingClientRect(), x = event.clientX - rect.left, y = event.clientY - rect.top;
        const c = camera.current, zoom = scale(c.zoom * Math.exp(-event.deltaY * .0015));
        move({ x: c.x + (x - dimensions.current.width / 2) * (1 / c.zoom - 1 / zoom), y: c.y + (y - dimensions.current.height / 2) * (1 / c.zoom - 1 / zoom), zoom });
      }}
      onPointerDown={event => { travelingUntil.current = 0; cancelAnimationFrame(animation.current); event.currentTarget.setPointerCapture(event.pointerId); dragging.current = { x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY, moved: false }; }}
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
    <div className={styles.legend}><span className={styles.level}>{zoomLabel}</span><span><i style={{ background: colors.document }} />Documents</span><span><i style={{ background: colors.chunk }} />Chunks</span><span><i style={{ background: colors.entity }} />Entities</span></div>
    {tooltip && <div className={styles.tooltip} style={{ left: tooltip.x, top: tooltip.y }}><small>{names[tooltip.node.type]}</small><strong>{clip(tooltip.node.preview || tooltip.node.label, 100)}</strong></div>}
    {edgeTooltip && <div className={styles.tooltip} role="tooltip" style={{ left: edgeTooltip.x, top: edgeTooltip.y }}><strong>{edgeMeaning(edgeTooltip.edge)[0]}</strong><p>{edgeMeaning(edgeTooltip.edge)[1]}</p></div>}
    {loading && <div className={styles.notice} role="status"><Loader2 size={15} className={styles.spin} />Opening source map…</div>}
    {navigatingTo && !loading && <div className={styles.navigationStatus} role="status"><Loader2 size={14} className={styles.spin} />Loading destination connections…</div>}
    {error && <div className={styles.error} role="alert"><span>{error}</span><button onClick={() => { setError(null); setReload(value => value + 1); }}><RotateCcw size={13} />Retry</button></div>}
    {(truncated || renderTruncated) && !error && !connectionsOpen && <div className={styles.limit}>Zoom in to reveal more sources</div>}
    {summaryTruncated && !error && !connectionsOpen && <div className={`${styles.limit} ${truncated || renderTruncated ? styles.limitSecondary : ''}`}>Some derived shared-entity links are hidden in this overview</div>}
    {connectionsOpen && <ConnectionPaths paths={connections?.paths || []} loading={connectionsLoading} error={connectionsError} truncated={connections?.truncated} activeTargetChunkId={activeConnection?.targetChunkId} onFollow={followConnection} onClose={clearConnections} />}
    <div className={styles.controls}><button aria-label="Zoom in" onClick={() => zoomBy(1.7)}><Plus size={16} /></button><button aria-label="Zoom out" onClick={() => zoomBy(1 / 1.7)}><Minus size={16} /></button>{onExpand && <button aria-label={expanded ? 'Collapse Source Explorer' : 'Expand Source Explorer'} onClick={onExpand}>{expanded ? <Minimize2 size={15} /> : <Expand size={15} />}</button>}<button aria-label="Show whole source map" onClick={fit}><LocateFixed size={15} /></button><button aria-label="About the source map" aria-expanded={help} onClick={() => setHelp(value => !value)}><HelpCircle size={16} /></button></div>
    {help && <div className={styles.help}><strong>Your sources, connected</strong><p>Each point is a document. Positions remain stable as documents arrive. Dashed edges summarize common entities.</p><dl className={styles.edgeMeanings}><div><dt>HAS_SECTION / HAS_CHUNK</dt><dd>Document → Section → Chunk.</dd></div><div><dt>NEXT_CHUNK</dt><dd>Reading order within a document.</dd></div><div><dt>MENTIONS</dt><dd>A chunk contains a mention of this entity.</dd></div><div><dt>Shared entity · derived</dt><dd>Both documents mention a common entity.</dd></div></dl><p>Containment and mention edges describe source structure. RELATES edges show extracted semantic predicates; inspect their source and status.</p></div>}
    <div className={styles.keyboard}><label htmlFor="map-node-keyboard">Navigate visible sources</label><select id="map-node-keyboard" value="" onChange={event => { const node = [...current.current.nodes, ...(neighborhood.current?.nodes || [])].find(item => item.id === event.target.value); if (node) activate(node); }}><option value="">Choose a visible source</option>{[...new Map([...accessible, ...(connections?.nodes || [])].map(node => [node.id, node])).values()].map(node => <option key={node.id} value={node.id}>{names[node.type]}: {clip(node.label, 70)}</option>)}</select></div>
  </div>;
}
