import type { EvidenceDocument } from './evidence-types';

export interface IngestionAttempt {
  attempt: number;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  error?: string | null;
}

export interface IngestionStage {
  name: string;
  status: string;
  attempts: number;
  error?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  durationMs?: number | null;
  history?: IngestionAttempt[];
  metadata?: { summary?: string[]; fallbackChunks?: number; limitedSource?: boolean; deferredMentions?: number };
}

export interface IngestionJob {
  id: string;
  filename: string;
  status: string;
  currentStage?: string | null;
  stages: IngestionStage[];
  documentId?: string | null;
  createdAt: string;
  error?: string | null;
}

export interface UploadedDocument {
  id: string;
  title: string;
  filename: string;
  status: string;
  chunkCount: number;
  sourceUrl?: string;
}

export interface IngestedDocument extends EvidenceDocument {
  processingWarnings?: string[];
  filename?: string;
  status?: string;
}

export function statusLabel(status: string) {
  const stages: Record<string, string> = { register: 'Preserve original', parse: 'Read file', normalize: 'Prepare source text', chunk: 'Split into chunks', configure: 'Choose extraction settings', embed: 'Embed source text', extract: 'Find things and connections', resolve: 'Check repeated names', prepare: 'Embed connections', validate: 'Check results', publish: 'Make searchable' };
  if (stages[status]) return stages[status];
  if (status === 'waiting_configuration') return 'Configuration needed';
  if (['complete', 'completed', 'published', 'succeeded'].includes(status)) return 'Complete';
  return status.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase());
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function string(value: unknown, fallback = '') {
  return typeof value === 'string' ? value : fallback;
}

function number(value: unknown, fallback = 0) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

export function normalizeSourceDocument(value: unknown): IngestedDocument {
  const source = record(value);
  const metadata = record(source.metadata);
  if (typeof source.id !== 'string' || typeof source.text !== 'string') throw new Error('The source is not ready to read. Wait for parsing and normalization to complete.');
  const id = source.id;
  const text = source.text;
  const textLength = Array.from(text).length;
  const title = string(source.title, string(metadata.title, string(source.filename, 'Source document')));
  const blocks = Array.isArray(source.blocks) ? source.blocks.map(record) : [];
  const rawSections = Array.isArray(source.sections) ? source.sections.map(record) : blocks.filter(block => block.kind === 'heading');
  const sections = rawSections.map((section, ordinal) => ({
    id: string(section.id, `${id}:section:${ordinal}`),
    title: string(section.title, string(section.text, title)),
    ordinal: number(section.ordinal, ordinal),
    startOffset: number(section.startOffset),
    endOffset: number(section.endOffset, textLength),
  }));
  if (!sections.length) sections.push({ id: `${id}:body`, title, ordinal: 0, startOffset: 0, endOffset: textLength });
  const chunks = (Array.isArray(source.chunks) ? source.chunks : []).map((value, ordinal) => {
    const chunk = record(value);
    if (typeof chunk.id !== 'string' || typeof chunk.text !== 'string') throw new Error('The source returned an invalid chunk. Retry the processing stage before opening its chunks.');
    const startOffset = number(chunk.startOffset);
    const section = sections.find(item => item.id === chunk.sectionId) || [...sections].reverse().find(item => item.startOffset <= startOffset) || sections[0];
    return {
      id: chunk.id,
      text: chunk.text,
      documentId: string(chunk.documentId, id),
      sectionId: string(chunk.sectionId, section.id),
      sectionTitle: string(chunk.sectionTitle, section.title),
      ordinal: number(chunk.ordinal, ordinal),
      startOffset,
      endOffset: number(chunk.endOffset, startOffset + Array.from(chunk.text).length),
    };
  });
  return {
    id, text, title, sections, chunks,
    processingWarnings: [...new Set([...(Array.isArray(source.processingWarnings) ? source.processingWarnings : []), ...(Array.isArray(metadata.warnings) ? metadata.warnings : [])].filter((warning): warning is string => typeof warning === 'string'))].slice(0, 20),
    revisionId: string(source.revisionId, string(source.revision)),
    filename: string(source.filename, string(metadata.filename)),
    status: string(source.status),
    year: string(source.year, string(metadata.year)),
    journal: string(source.journal, string(metadata.journal)),
    doi: string(source.doi, string(metadata.doi)),
    sourceUrl: string(source.sourceUrl, string(metadata.sourceUrl)),
    sectionCount: sections.length,
    chunkCount: chunks.length,
    entities: [],
  };
}
