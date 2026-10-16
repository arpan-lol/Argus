export interface MapBounds { minX: number; minY: number; maxX: number; maxY: number }
export interface MapNode { id: string; type: 'group' | 'document' | 'section' | 'chunk' | 'entity'; label: string; preview?: string; x: number; y: number; radius?: number; documentId?: string; sectionId?: string; chunkId?: string; entityType?: string; count?: number; [key: string]: unknown }
export interface MapEdge { id: string; source: string; target: string; type: string; derived?: boolean; viaEntityIds?: string[]; labels?: string[]; [key: string]: unknown }
