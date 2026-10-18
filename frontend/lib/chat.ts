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
    pathUsable?: boolean;
    excludedAssertionIds?: string[];
    reviewRequiredAssertionIds?: string[];
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

export interface ChatConversation {
  id: string;
  title: string;
  updatedAt: string;
  runs: { id: string; query: string; status: string }[];
}

export async function streamChat(path: string, body: unknown, onEvent: (event: ChatEvent) => void) {
  const startPath = path.endsWith('/resume') ? `${path}-start` : `${path}/start`;
  const response = await fetch(`/api${startPath}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.error === 'string' ? error.error : `The request failed (${response.status}). Please retry.`);
  }
  const { runId } = await response.json() as { runId: string };
  const runPath = path.endsWith('/resume') ? path.slice(0, -'/resume'.length) : `${path}/${runId}`;
  onEvent({type: 'accepted', runId});
  await new Promise<void>((resolve, reject) => {
    let sequence = 0;
    let finished = false;
    let polling = false;
    let failures = 0;
    const source = new EventSource(`/api${runPath}/events`);
    const timer = window.setInterval(() => void poll(), 700);
    const timeout = window.setTimeout(() => stop(new Error('The investigation is still running. Reconnect to its saved results.')), 390000);
    function stop(error?: Error) {
      if (finished) return;
      finished = true;
      source.close();
      window.clearInterval(timer);
      window.clearTimeout(timeout);
      if (error) reject(error); else resolve();
    }
    function receive(event: ChatEvent) {
      if (finished || event.sequence && event.sequence <= sequence) return;
      if (event.sequence) sequence = event.sequence;
      onEvent(event);
      if (event.type === 'done' || event.type === 'error') stop();
    }
    async function poll() {
      if (polling || finished) return;
      polling = true;
      try {
        const snapshot = await fetch(`/api${runPath}`, {cache: 'no-store'});
        if (!snapshot.ok) throw new Error(`Could not read investigation progress (${snapshot.status})`);
        const saved = await snapshot.json() as SavedChat;
        failures = 0;
        saved.events.forEach(receive);
        if (!finished && saved.status === 'complete' && saved.result) receive({type: 'done', ...saved.result});
        if (!finished && saved.status === 'failed') receive({type: 'error', message: saved.error || 'The investigation stopped.'});
      } catch (error) {
        failures += 1;
        if (failures >= 8) stop(error instanceof Error ? error : new Error('Could not read investigation progress.'));
      } finally { polling = false; }
    }
    source.onmessage = message => {
      try { receive(JSON.parse(message.data) as ChatEvent); } catch { void poll(); }
    };
    source.onerror = () => { source.close(); void poll(); };
    void poll();
  });
}
