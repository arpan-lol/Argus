export interface Corpus {
  collection: string;
  updatedAt?: string;
  counts: { documents: number; sections: number; chunks: number; entities: number };
  discovery?: Record<string, unknown>;
  ingestion?: Record<string, unknown>;
  capabilities: { lexical: boolean; graph: boolean; vector: boolean; generation: boolean };
  graph: { status: string; name?: string; [key: string]: unknown };
}

export interface DocumentSummary {
  id: string;
  title: string;
  year?: string | number;
  doi?: string;
  journal?: string;
  sourceUrl?: string;
  sectionCount: number;
  chunkCount: number;
}

export interface Section { id: string; title: string; ordinal: number; startOffset: number; endOffset: number }
export interface Chunk {
  id: string; documentId: string; sectionId: string; sectionTitle: string; ordinal: number;
  text: string; startOffset: number; endOffset: number; sourceUrl?: string;
}
export interface EvidenceDocument extends DocumentSummary {
  revisionId: string; text: string; sections: Section[]; chunks: Chunk[];
  entities: { id: string; label?: string; name?: string; type?: string }[];
}
export interface GraphNode {
  id: string; label: string; type: 'document' | 'section' | 'chunk' | 'entity';
  documentId?: string; sectionId?: string; chunkId?: string;
}
export interface GraphEdge { id: string; source: string; target: string; type: string }
export interface EvidenceGraph {
  nodes: GraphNode[]; edges: GraphEdge[]; source: string; status?: string; truncated?: boolean;
  focus?: { documentId?: string; sectionId?: string; chunkId?: string };
}
export interface EvidenceResult extends Omit<Chunk, 'ordinal'> {
  chunkId: string;
  documentTitle: string; score: number; scoreType: string; rank: number; reasons: string[]; pathIds: string[];
  retrieval: 'lexical' | 'graph';
}

export const chunkColors = [
  { tint: '#edf4ed', ink: '#3c755e' }, { tint: '#f7f0df', ink: '#8e7529' },
  { tint: '#eff0f8', ink: '#75628e' }, { tint: '#faefeb', ink: '#9a6855' },
];
export function chunkColor(id: string) {
  let hash = 0;
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) | 0;
  return chunkColors[Math.abs(hash) % chunkColors.length];
}
export interface TraceStage {
  id: string; stage: string; status: string; durationMs: number; inputCount?: number; outputCount?: number; details?: unknown;
}
export interface SearchRun {
  runId: string; query: string; results: EvidenceResult[]; trace: TraceStage[];
  timings: { totalMs: number }; options: Record<string, unknown>; capabilities: Corpus['capabilities'];
  warnings: string[]; graph?: EvidenceGraph;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(`/api${path}`, { ...init, headers, cache: 'no-store' });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.message || (typeof body.error === 'string' ? body.error : body.error?.message) || `Request failed (${response.status}). Check that the backend is running.`);
  }
  const body = await response.json();
  return body.data ?? body;
}
