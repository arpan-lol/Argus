export interface Section { id: string; title: string; ordinal: number; startOffset: number; endOffset: number }
export interface Chunk { id: string; documentId: string; sectionId: string; sectionTitle: string; ordinal: number; text: string; startOffset: number; endOffset: number; sourceUrl: string }
export interface Entity { id: string; label: string; type: string; mentions: { chunkId: string; startOffset: number; endOffset: number; text: string }[] }
export interface Document { id: string; revisionId: string; title: string; text: string; year?: string | number; doi?: string; journal?: string; sourceUrl: string; sections: Section[]; chunks: Chunk[]; entities: Entity[]; [key: string]: unknown }
export interface Catalog { schemaVersion: number; collection: unknown; updatedAt: string; documents: Document[]; discovery: unknown; ingestion: unknown; [key: string]: unknown }
export interface GraphNode { id: string; label: string; type: string; documentId?: string; sectionId?: string; chunkId?: string; [key: string]: unknown }
export interface GraphEdge { id: string; source: string; target: string; type: string }
export interface GraphView { nodes: GraphNode[]; edges: GraphEdge[]; focus: Record<string, string | undefined>; truncated: boolean; source: string; status: string }
export interface SearchOptions { graphExpansion?: boolean; limit?: number; documentId?: string; [key: string]: unknown }
export interface EvidenceHit extends Chunk { chunkId: string; documentTitle: string; score: number; scoreType: string; rank: number; reasons: string[]; pathIds: string[]; retrieval: string }
export interface Trace { id: string; stage: string; status: string; durationMs: number; inputCount?: number; outputCount?: number; details?: unknown }
