export interface ChatSource {
  id: string;
  jobId: string;
  chunkId?: string;
  sourceKind?: 'metadata';
  metadataField?: 'authors' | 'indexedAt';
  documentId: string;
  documentTitle: string;
  sectionTitle: string;
  startOffset?: number;
  endOffset?: number;
  revisionId: string;
  processingVersion: string;
  text: string;
}

export interface ChatReport {
  purpose: 'conversation' | 'source_answer' | 'insufficient_support';
  paragraphs: { text: string; citations: string[] }[];
  comparison: { subject: string; finding: string; conditions: string; citations: string[] }[];
  gaps: string[];
}

export interface ChatCoverage { publishedDocuments: number; legacyDocuments: number; searchScope: string }
export interface ChatResult {
  runId: string;
  model: string;
  report: ChatReport;
  sources: ChatSource[];
  coverage: ChatCoverage;
  usage: { modelCalls: number; toolCalls: number; runtimeMs: number; reportedTokens?: number; reservedTokens: number; costKnown: boolean };
}

export interface ChatEvent {
  type: string;
  sequence?: number;
  runId?: string;
  model?: string;
  label?: string;
  tool?: string;
  callId?: string;
  count?: number;
  durationMs?: number;
  outcome?: string;
  warnings?: string[];
  truncations?: string[];
  message?: string;
  coverage?: ChatCoverage;
  result?: {
    items: { id?: string; name?: string; predicate?: string; subject?: { id: string; name: string }; object?: { id: string; name: string }; quote?: string; documentTitle?: string; chunkId?: string; documentId?: string; jobId?: string; polarity?: string; extractionMethod?: string; traversalStatus?: string }[];
    tree: { assertionId: string; from: string; to: string; predicate: string; subject: { id: string; name: string }; object: { id: string; name: string }; quote: string; documentTitle?: string; chunkId?: string; documentId?: string; jobId?: string; polarity?: string; extractionMethod?: string; traversalStatus?: string }[];
    pathCount: number;
    shownItems: number;
    totalItems: number;
    truncated: boolean;
  };
}

export interface ChatTurn {
  id: string;
  query: string;
  runId?: string;
  model?: string;
  events: ChatEvent[];
  result?: ChatResult;
  error?: string;
}

export interface SavedChat {
  runId: string;
  query: string;
  status: string;
  model: string;
  result?: ChatResult;
  error?: string;
  events: ChatEvent[];
}

export async function streamChat(path: string, body: unknown, onEvent: (event: ChatEvent) => void) {
  const response = await fetch(`/api${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.error === 'string' ? error.error : `The request failed (${response.status}). Please retry.`);
  }
  if (!response.body) throw new Error('The response stream is unavailable. Please retry.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  let finished = false;
  const consume = (line: string) => {
    if (!line.trim() || line.startsWith(':') || line.startsWith('id:')) return;
    if (line.startsWith('data:')) line = line.slice(5).trimStart();
    const event = JSON.parse(line) as ChatEvent;
    if (event.type === 'done' || event.type === 'error') finished = true;
    if (event.type !== 'heartbeat') onEvent(event);
  };
  try {
    for (;;) {
      const { done, value } = await reader.read();
      pending += decoder.decode(value, { stream: !done });
      const lines = pending.split('\n');
      pending = lines.pop() || '';
      lines.forEach(consume);
      if (done) break;
    }
    consume(pending);
    if (!finished) throw new Error('The connection closed before the answer arrived. Reconnect to the saved investigation.');
  } finally {
    reader.releaseLock();
  }
}
