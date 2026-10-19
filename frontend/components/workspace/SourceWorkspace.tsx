'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowUp, ArrowUpRight, ChevronDown, FileText, Loader2, MessageSquare, Moon, Network, Pause, PanelLeftClose, PanelLeftOpen, Paperclip, Play, Plus, Settings2, Sun, Upload, X } from 'lucide-react';
import type { ImperativePanelHandle } from 'react-resizable-panels';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable';
import { ChatResponse } from './ChatResponse';
import { streamChat, type ChatTurn, type ChatSource, type ChatResult, type ChatEvent, type SavedChat, type ChatCoverage, type ChatConversation } from '@/lib/chat';
import { ProjectSources } from '@/components/source-explorer/ProjectSources';
import { ProcessingActivity } from '@/components/source-explorer/ProcessingActivity';
import { projectApi, projectRoot, type Project, type ProcessingEvent } from '@/lib/projects';
import { normalizeSourceDocument } from '@/lib/ingestion-types';
import { GraphMap, type MapNode } from '@/components/source-explorer/GraphMap';
import { KnowledgeGraph } from '@/components/source-explorer/KnowledgeGraph';
import { api, type DocumentSummary, type EvidenceDocument } from '@/lib/evidence-types';
import { statusLabel, type IngestionJob } from '@/lib/ingestion-types';

type EngineSettings = { graphHops: number; hybridSearch: boolean; rrfSearch: boolean };
const DEFAULT_ENGINE_SETTINGS: EngineSettings = { graphHops: 5, hybridSearch: true, rrfSearch: true };

function storedEngineSettings(projectId: string): EngineSettings {
  try {
    const saved = JSON.parse(localStorage.getItem(`argus-engine:${projectId}`) || '{}') as Partial<EngineSettings>;
    return {
      graphHops: Number.isInteger(saved.graphHops) && (saved.graphHops ?? 0) >= 2 && (saved.graphHops ?? 11) <= 10 ? saved.graphHops! : 5,
      hybridSearch: typeof saved.hybridSearch === 'boolean' ? saved.hybridSearch : true,
      rrfSearch: typeof saved.rrfSearch === 'boolean' ? saved.rrfSearch : true,
    };
  } catch { return DEFAULT_ENGINE_SETTINGS; }
}


function savedRuns(projectId: string): string[] {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(`argus-chat-runs:${projectId}`) || '[]');
    return Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string' && /^[a-f0-9-]{36}$/.test(id)).slice(-12) : [];
  } catch { return []; }
}

export function SourceWorkspace({ projectId }: { projectId: string }) {
  const root = projectRoot(projectId);
  const workspaceApi = useCallback(<T,>(path: string, init?: RequestInit) => api<T>(root + path, init), [root]);
  const [project, setProject] = useState<Project>();
  const [clockNow, setClockNow] = useState(Date.now());
  const [projectError, setProjectError] = useState('');
  const [processingEvents, setProcessingEvents] = useState<ProcessingEvent[]>([]);
  const [workspaceJobs, setWorkspaceJobs] = useState<IngestionJob[]>([]);
  const [streamConnected, setStreamConnected] = useState(false);
  const [dataVersion, setDataVersion] = useState(0);
  const [graphVersion, setGraphVersion] = useState(0);
  const [queueControlBusy, setQueueControlBusy] = useState<'pause' | 'resume' | null>(null);
  const [queuePaused, setQueuePaused] = useState<boolean | null>(null);
  const [queueControlStatus, setQueueControlStatus] = useState('');
  const [queueControlError, setQueueControlError] = useState('');

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [dark, setDark] = useState(false);
  const [graphView, setGraphView] = useState<'knowledge' | 'sources'>('sources');
  const [graphTrace, setGraphTrace] = useState<{assertionIds: string[]; nonce: number} | null>(null);
  const [graphFullscreen, setGraphFullscreen] = useState(false);
  const [graphCompact, setGraphCompact] = useState(false);
  const [configurationOpen, setConfigurationOpen] = useState(false);
  const [engineSettings, setEngineSettings] = useState<EngineSettings>(DEFAULT_ENGINE_SETTINGS);
  const [uploadRequest, setUploadRequest] = useState(0);
  const [documentId, setDocumentId] = useState<string>();
  const [document, setDocument] = useState<EvidenceDocument | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mapFocus, setMapFocus] = useState<{nodeId: string; nonce: number; kind?: 'entity' | 'source'} | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<MapNode | null>(null);
  const [nodeDetails, setNodeDetails] = useState<Record<string, unknown> | null>(null);
  const [query, setQuery] = useState('');
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [conversationId, setConversationId] = useState('');
  const [pipelineFocus, setPipelineFocus] = useState<ChatSource | null>(null);
  const [readerRequest, setReaderRequest] = useState<{ documentId: string; chunkId?: string; jobId?: string; nonce: number } | null>(null);
  const [chatConfig, setChatConfig] = useState<{model: string; coverage: ChatCoverage} | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeTurnId, setActiveTurnId] = useState<string>();
  const messages = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const nodeDialog = useRef<HTMLDialogElement>(null);
  const pendingChunk = useRef<string | undefined>(undefined);
  const filePanel = useRef<ImperativePanelHandle>(null);
  const graphPanel = useRef<ImperativePanelHandle>(null);

  useEffect(() => {
    setEngineSettings(storedEngineSettings(projectId));
    void workspaceApi<{model: string; coverage: ChatCoverage}>('/chat-config').then(setChatConfig).catch(() => undefined);
    const active = localStorage.getItem(`argus-conversation:${projectId}`);
    void workspaceApi<{conversations: ChatConversation[]}>('/chat/history').then(async result => {
      setConversations(result.conversations);
      const chosen = result.conversations.find(item => item.id === active) || result.conversations[0];
      if (!chosen) { setConversationId(active || crypto.randomUUID()); return; }
      setConversationId(chosen.id);
      localStorage.setItem(`argus-conversation:${projectId}`, chosen.id);
      const runs = await Promise.all(chosen.runs.map(run => workspaceApi<SavedChat>(`/chat/${run.id}`).catch(() => null)));
      setTurns(runs.filter((run): run is SavedChat => !!run).map(run => ({id: run.runId, runId: run.runId, query: run.query, model: run.model, events: run.events, result: run.result || undefined, error: run.result ? undefined : run.error || 'This investigation has saved progress. Reconnect to continue.'})));
    }).catch(() => {
      const saved = savedRuns(projectId);
      setConversationId(active || crypto.randomUUID());
      void Promise.all(saved.map(id => workspaceApi<SavedChat>(`/chat/${id}`).catch(() => null))).then(runs => setTurns(runs.filter((run): run is SavedChat => !!run).map(run => ({id: run.runId, runId: run.runId, query: run.query, model: run.model, events: run.events, result: run.result || undefined}))));
    });
    const value = localStorage.getItem('falkor-theme') === 'dark';
    setDark(value);
    window.document.documentElement.classList.toggle('dark', value);
  }, []);

  const updateEngineSettings = (next: EngineSettings) => {
    setEngineSettings(next);
    localStorage.setItem(`argus-engine:${projectId}`, JSON.stringify(next));
  };

  const openConversation = async (item: ChatConversation) => {
    if (busy) return;
    setConversationId(item.id);
    localStorage.setItem(`argus-conversation:${projectId}`, item.id);
    const runs = await Promise.all(item.runs.map(run => workspaceApi<SavedChat>(`/chat/${run.id}`).catch(() => null)));
    setTurns(runs.filter((run): run is SavedChat => !!run).map(run => ({id: run.runId, runId: run.runId, query: run.query, model: run.model, events: run.events, result: run.result || undefined, error: run.result ? undefined : run.error || 'This investigation has saved progress. Reconnect to continue.'})));
  };

  useEffect(() => {
    if (!documentId) return;
    let active = true;
    void workspaceApi<unknown>(`/ingestion/documents/${encodeURIComponent(documentId)}`).then(normalizeSourceDocument).then(next => {
      if (!active) return;
      setDocument(next);
      const chunk = next.chunks.find(item => item.id === pendingChunk.current) || next.chunks[0];
      setSelectedId(chunk?.id || next.id);
      pendingChunk.current = undefined;
    }).catch(failure => { if (active) setGraphError(failure.message); });
    return () => { active = false; };
  }, [documentId, workspaceApi]);

  useEffect(() => {
    if (!selectedNode) { setNodeDetails(null); return; }
    let active = true;
    setNodeDetails(null);
    void workspaceApi<Record<string, unknown>>(`/map/node/${encodeURIComponent(selectedNode.id)}`).then(next => { if (active) setNodeDetails(next); }).catch(() => undefined);
    return () => { active = false; };
  }, [selectedNode, workspaceApi]);

  useEffect(() => {
    if (!graphFullscreen) return;
    const previousOverflow = window.document.body.style.overflow;
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setGraphFullscreen(false); };
    window.document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', close);
    return () => { window.document.body.style.overflow = previousOverflow; window.removeEventListener('keydown', close); };
  }, [graphFullscreen]);

  useEffect(() => { messages.current?.scrollTo({ top: messages.current.scrollHeight, behavior: 'smooth' }); }, [turns, busy]);
  useEffect(() => {
    const textarea = composer.current;
    if (textarea) { textarea.style.height = 'auto'; textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`; }
  }, [query]);
  useEffect(() => { if (selectedNode) nodeDialog.current?.showModal(); else nodeDialog.current?.close(); }, [selectedNode]);
  useEffect(() => {
    if (!configurationOpen) return;
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setConfigurationOpen(false); };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [configurationOpen]);

  useEffect(() => {
    let active = true;
    let stream: EventSource | undefined;
    let refreshTimer: number | undefined;
    let reconnectTimer: number | undefined;
    let cursor = 0;
    let lastMessageAt = Date.now();
    let published = -1;
    let snapshotRequest = 0;
    const refreshSnapshot = async (forceGraph = false) => {
      const request = ++snapshotRequest;
      try {
        const next = await workspaceApi<{model: string; coverage: ChatCoverage}>('/chat-config');
        if (!active || request !== snapshotRequest) return;
        if (forceGraph || next.coverage.publishedDocuments !== published) setGraphVersion(version => version + 1);
        published = next.coverage.publishedDocuments;
        setChatConfig(next);
        setDataVersion(version => version + 1);
      } catch { if (active) setStreamConnected(false); }
    };
    const connect = () => {
      if (!active) return;
      stream = new EventSource(`/api${root}/events?after=${cursor}`);
      stream.onopen = () => { lastMessageAt = Date.now(); setStreamConnected(true); void refreshSnapshot(true); };
      stream.onerror = () => {
        if (!active) return;
        setStreamConnected(false);
        stream?.close();
        window.clearTimeout(reconnectTimer);
        reconnectTimer = window.setTimeout(connect, 3000);
      };
      stream.onmessage = message => {
        if (!active) return;
        lastMessageAt = Date.now();
        const event = JSON.parse(message.data) as ProcessingEvent;
        cursor = Math.max(cursor, event.sequence);
        setProcessingEvents(previous => previous.some(item => item.sequence === event.sequence) ? previous : [...previous, event].slice(-300));
        if (event.type === 'graph_updated') { setGraphVersion(version => version + 1); void refreshSnapshot(); }
        if (!refreshTimer) refreshTimer = window.setTimeout(() => { refreshTimer = undefined; setDataVersion(version => version + 1); }, 1000);
      };
    };
    void workspaceApi<Project>('').then(value => {
      if (!active) return;
      setProject(value);
      cursor = Math.max(0, (value.lastEventSequence || 0) - 300);
      connect();
    }).catch(error => { if (active) setProjectError(error.message); });
    const fallback = window.setInterval(() => { if (Date.now() - lastMessageAt > 15000) void refreshSnapshot(); }, 10000);
    return () => { active = false; stream?.close(); window.clearTimeout(refreshTimer); window.clearTimeout(reconnectTimer); window.clearInterval(fallback); };
  }, [workspaceApi, root]);

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    window.document.documentElement.classList.toggle('dark', next);
    localStorage.setItem('falkor-theme', next ? 'dark' : 'light');
  };
  const focusSource = (nextDocumentId: string, chunkId?: string) => {
    setPipelineFocus(null);
    if (nextDocumentId !== documentId) { pendingChunk.current = chunkId; setDocumentId(nextDocumentId); }
    else {
      setSelectedId(chunkId || nextDocumentId);
    }
  };
  const selectCitation = (source: ChatSource) => { setGraphView('sources'); graphPanel.current?.resize(65); setPipelineFocus(source); setDocumentId(source.documentId); setMapFocus({nodeId: source.chunkId || source.documentId, nonce: Date.now(), kind: 'source'}); setReaderRequest({documentId:source.documentId,chunkId:source.chunkId,jobId:source.jobId,nonce:Date.now()}); };
  const selectNode = (node: MapNode) => { if (node.type === 'entity') { setSelectedNode(null); setGraphView('knowledge'); setMapFocus({nodeId: node.id, nonce: Date.now(), kind: 'entity'}); return; } if (node.documentId) focusSource(node.documentId, node.chunkId); setSelectedId(node.id); setSelectedNode(node); };
  const showFiles = () => filePanel.current?.resize(85);
  const showGraph = () => graphPanel.current?.resize(70);
  const graphSwitcher = <div className="ce-map-modes" role="group" aria-label="Graph view"><button aria-pressed={graphView === 'knowledge'} onClick={() => { setGraphView('knowledge'); showGraph(); }}>Knowledge graph</button><button aria-pressed={graphView === 'sources'} onClick={() => setGraphView('sources')}>Source graph</button></div>;
  const upload = () => { setUploadRequest(previous => previous + 1); };
  const controlIngestion = async (action: 'pause' | 'resume') => {
    setQueueControlBusy(action); setQueueControlError(''); setQueueControlStatus('');
    try {
      const result = await projectApi<{ action?: 'pause' | 'resume'; counts?: Record<string, number>; [key: string]: unknown }>(projectId, '/ingestion-control', { method: 'POST', body: JSON.stringify({ action }) });
      const appliedAction = result.action || action;
      setQueuePaused(appliedAction === 'pause');
      const counts = result.counts || Object.fromEntries(Object.entries(result).filter(([key, value]) => key !== 'action' && typeof value === 'number')) as Record<string, number>;
      const summary = Object.entries(counts).map(([name, count]) => `${count.toLocaleString()} ${name}`).join(' · ');
      setQueueControlStatus(`Ingestion ${appliedAction === 'pause' ? 'paused' : 'resumed'}${summary ? ` · ${summary}` : ''}`);
      setDataVersion(version => version + 1);
    } catch (reason) {
      setQueueControlError(reason instanceof Error ? reason.message : 'Ingestion queue control failed. Try again.');
    } finally { setQueueControlBusy(null); }
  };
  const activeStages = new Set<string>();
  for (const event of processingEvents) {
    const key = `${event.jobId || ''}:${event.stage || ''}`;
    if (event.type === 'stage_start') activeStages.add(key);
    if (event.type === 'stage_complete' || event.type === 'stage_failed') activeStages.delete(key);
  }
  const runningJob = workspaceJobs.find(job => ['running', 'processing'].includes(job.status));
  const lastProcessingEvent = [...processingEvents].reverse().find(event => event.jobId === runningJob?.id && event.stage && activeStages.has(`${event.jobId || ''}:${event.stage}`));
  const processingStart = runningJob && (runningJob.stages.find(stage => stage.startedAt)?.startedAt || runningJob.createdAt);
  useEffect(() => {
    if (!runningJob) return;
    const timer = window.setInterval(() => setClockNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [runningJob?.id]);
  const elapsedSeconds = processingStart ? Math.max(0, Math.floor((clockNow - new Date(processingStart).getTime()) / 1000)) : 0;
  const elapsedLabel = elapsedSeconds >= 60 ? `${Math.floor(elapsedSeconds / 60)}m ${String(elapsedSeconds % 60).padStart(2, '0')}s` : `${elapsedSeconds}s`;
  const queuedFiles = workspaceJobs.filter(job => ['registered', 'queued'].includes(job.status)).length;
  const stoppedFiles = workspaceJobs.filter(job => ['failed', 'interrupted', 'budget_exceeded', 'waiting_configuration'].includes(job.status)).length;
  const pausedFiles = workspaceJobs.filter(job => job.status === 'paused').length;
  useEffect(() => {
    if (queuePaused !== null) return;
    const activeOrQueued = workspaceJobs.some(job => ['registered', 'queued', 'running', 'processing'].includes(job.status));
    if (pausedFiles && !activeOrQueued) setQueuePaused(true);
    else if (workspaceJobs.length) setQueuePaused(false);
  }, [workspaceJobs, pausedFiles, queuePaused]);
  const activeStage = lastProcessingEvent?.stage || runningJob?.currentStage || '';
  const stageSummary = runningJob?.stages.find(stage => stage.name === activeStage)?.metadata?.summary?.join(' ');
  const liveProcessingStatus = runningJob ? `${statusLabel(activeStage || runningJob.status)}${lastProcessingEvent?.counts ? ` · ${Object.entries(lastProcessingEvent.counts).map(([name, count]) => `${count.toLocaleString()} ${name}`).join(', ')}` : stageSummary ? ` · ${stageSummary}` : ''} · ${elapsedLabel}` : [queuedFiles ? `${queuedFiles} queued` : '', stoppedFiles ? `${stoppedFiles} needs attention` : '', pausedFiles ? `${pausedFiles} paused` : ''].filter(Boolean).join(' · ') || (workspaceJobs.length ? 'Up to date' : '');
  const receive = (id: string, event: ChatEvent) => {
    if (event.type === 'accepted' && event.runId) {
      const saved = savedRuns(projectId);
      sessionStorage.setItem(`argus-chat-runs:${projectId}`, JSON.stringify([...new Set([...saved, event.runId])].slice(-12)));
      void workspaceApi<{conversations: ChatConversation[]}>('/chat/history').then(result => setConversations(result.conversations)).catch(() => undefined);
    }
    setTurns(previous => previous.map(turn => turn.id === id ? {
      ...turn, runId: event.runId || turn.runId, model: event.model || turn.model,
      events: [...turn.events, event],
      ...(event.type === 'done' ? {result: event as unknown as ChatResult, error: undefined} : {}),
      ...(event.type === 'error' ? {error: event.message || 'The investigation stopped. Resume to retry.'} : {}),
    } : turn));
  };
  const resume = async (turn: ChatTurn) => {
    if (/\b(limit|budget)\b/i.test(turn.error || '')) { await submit(undefined, turn.query); return; }
    if (!turn.runId || busy) return;
    setBusy(true); setActiveTurnId(turn.id);
    try {
      const saved = await workspaceApi<SavedChat>(`/chat/${turn.runId}`);
      if (saved.result) receive(turn.id, {type: 'done', ...saved.result} as ChatEvent);
      else if (saved.status === 'running') throw new Error('The investigation is still running. Reconnect shortly to retrieve its answer.');
      else {
        setTurns(previous => previous.map(item => item.id === turn.id ? {...item, error: undefined} : item));
        await streamChat(`${root}/chat/${turn.runId}/resume`, {}, event => receive(turn.id, event));
      }
    } catch (failure) { setTurns(previous => previous.map(item => item.id === turn.id ? {...item, error: failure instanceof Error ? failure.message : 'Could not reconnect.'} : item)); }
    finally { setBusy(false); }
  };
  const submit = async (event?: FormEvent, suggestion?: string) => {
    event?.preventDefault();
    const value = (suggestion || query).trim();
    if (!value || busy) return;
    const id = crypto.randomUUID();
    const history = turns.filter(turn => turn.result).flatMap(turn => [
      {role: 'user', content: turn.query},
      {role: 'assistant', content: turn.result!.report.paragraphs.map(paragraph => paragraph.text).join('\n')},
    ]);
    setTurns(previous => [...previous, {id, query: value, model: chatConfig?.model, events: []}]);
    setQuery(''); setBusy(true); setActiveTurnId(id);
    const activeConversation = conversationId || crypto.randomUUID();
    if (!conversationId) setConversationId(activeConversation);
    localStorage.setItem(`argus-conversation:${projectId}`, activeConversation);
    try { await streamChat(`${root}/chat`, {query: value, history, conversation_id: activeConversation, graph_hops: engineSettings.graphHops, hybrid_search: engineSettings.hybridSearch, rrf_search: engineSettings.rrfSearch}, event => receive(id, event)); }
    catch (failure) { setTurns(previous => previous.map(turn => turn.id === id ? {...turn, error: failure instanceof Error ? failure.message : 'The request failed. Please retry.'} : turn)); }
    finally { setBusy(false); }
  };
  const selectedChunk = document?.chunks.find(chunk => chunk.id === (selectedNode?.chunkId || selectedNode?.id));
  const selectedSection = document?.sections.find(section => section.id === (selectedNode?.sectionId || selectedNode?.id));
  const recordContent = nodeDetails?.content && typeof nodeDetails.content === 'object' ? nodeDetails.content as Record<string, unknown> : null;
  const selectedSource = document?.id === selectedNode?.documentId ? document : null;
  const sourceTitle = selectedSource?.title || (selectedNode?.type === 'document' ? selectedNode.preview || selectedNode.label : null);

  return <div className={`ce-workspace ${sidebarOpen ? '' : 'ce-sidebar-collapsed'}`}>
    <aside className="ce-sidebar">
      <div className="ce-brand"><img src="/argus-logo.svg" alt="" width={29} height={29} /><strong>Argus</strong><button className="ce-icon" onClick={() => setSidebarOpen(false)} aria-label="Collapse sidebar"><PanelLeftClose size={17} /></button></div>
      <a className="ce-project-return" href="/"><ArrowLeft size={17} />Projects</a>
      <div className="ce-navigation-label ce-project-name">{project?.name || 'Workspace'}</div>
      <button className="ce-session ce-new-chat" onClick={() => { const next = crypto.randomUUID(); setConversationId(next); localStorage.setItem(`argus-conversation:${projectId}`, next); setTurns([]); setQuery(''); composer.current?.focus(); }} disabled={busy}><Plus size={17} /><span>New chat</span></button>
      <button className="ce-session active" onClick={() => messages.current?.scrollTo({ top: 0, behavior: 'smooth' })}><MessageSquare size={16} /><span>Current conversation</span></button>
      {!!conversations.length && <div className="ce-chat-history" aria-label="Saved conversations">{conversations.slice(0, 20).map(item => <button key={item.id} type="button" className={`ce-session ${item.id === conversationId ? 'active' : ''}`} onClick={() => void openConversation(item)} disabled={busy} title={item.title}><MessageSquare size={14} /><span>{item.title}</span></button>)}</div>}
      <div className="ce-sidebar-bottom">
        <div className="ce-engine">
          <button className={`ce-theme ${configurationOpen ? 'is-active' : ''}`} onClick={() => setConfigurationOpen(previous => !previous)} aria-label="Engine configuration" aria-controls="engine-configuration" aria-expanded={configurationOpen}><Settings2 size={16} /><span>Engine configuration</span></button>
          {configurationOpen && <section id="engine-configuration" className="ce-configuration" aria-label="Engine configuration">
            <div><strong>Engine configuration</strong><button className="ce-icon" onClick={() => setConfigurationOpen(false)} aria-label="Close engine configuration"><X size={16} /></button></div>
            <div className="ce-engine-setting"><div className="ce-engine-setting-heading"><label htmlFor="graph-hops">Graph hops</label><output htmlFor="graph-hops">{engineSettings.graphHops}</output></div><input id="graph-hops" type="range" min="2" max="10" step="1" value={engineSettings.graphHops} onChange={event => updateEngineSettings({...engineSettings, graphHops: Number(event.target.value)})} /><div className="ce-engine-range-labels"><span>2</span><span>10</span></div><small>Maximum relationship hops explored per source search and path.</small></div>
            <label className="ce-engine-toggle"><span><strong>Hybrid search</strong><small>Search passages with vectors and BM25.</small></span><input type="checkbox" checked={engineSettings.hybridSearch} onChange={event => updateEngineSettings({...engineSettings, hybridSearch: event.target.checked})} /></label>
            <label className="ce-engine-toggle"><span><strong>RRF ranking</strong><small>Combine vector and BM25 ranks.</small></span><input type="checkbox" checked={engineSettings.rrfSearch} disabled={!engineSettings.hybridSearch} onChange={event => updateEngineSettings({...engineSettings, rrfSearch: event.target.checked})} /></label>
          </section>}
        </div>
        <div className="ce-user"><span className="ce-avatar"><img src="/argus-logo.svg" alt="" width={24} height={24} /></span><strong>Test User</strong></div>
        <div className="ce-sidebar-utility-row"><ProcessingActivity projectId={projectId} events={processingEvents} connected={streamConnected} /><button className="ce-theme ce-theme-compact" onClick={toggleTheme} aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`} title={`Switch to ${dark ? 'light' : 'dark'} mode`}>{dark ? <Sun size={16} /> : <Moon size={16} />}</button></div>
      </div>
    </aside>
    <main className="ce-main">
      <ResizablePanelGroup direction="horizontal" className="ce-panels">
        <ResizablePanel defaultSize={52} minSize={30} className="ce-chat-panel">
          <div className="ce-chat-heading">{!sidebarOpen && <><button className="ce-icon" onClick={() => setSidebarOpen(true)} aria-label="Expand sidebar"><PanelLeftOpen size={18} /></button><span className="ce-mobile-brand">Argus</span></>}<span>Chat</span><button className="ce-icon ce-mobile-theme" onClick={toggleTheme} aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`}>{dark ? <Sun size={16} /> : <Moon size={16} />}</button><button className="ce-icon ce-mobile-source" onClick={() => window.document.querySelector('.ce-explorer-panel')?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'})} aria-label="Open files and graph"><Network size={17} /></button></div>
          <div className="ce-messages" ref={messages}>
            {!turns.length && <div className="ce-chat-empty"><img src="/argus-logo.svg" alt="" width={46} height={46} /><h1>Start with a question.</h1><p>Ask Argus a question and inspect every source it uses.</p><div className="ce-suggestions"><button onClick={() => void submit(undefined, 'Summarize a published source')}>Summarize a published source<ArrowUp size={14} /></button><button onClick={() => void submit(undefined, 'What sources can you search?')}>What can you search?<ArrowUp size={14} /></button></div></div>}
            {turns.map(turn => <div className="ce-turn" key={turn.id}><div className="ce-user-message">{turn.query}</div><ChatResponse turn={turn} pending={busy && turn.id === activeTurnId && !turn.result && !turn.error} onCitation={selectCitation} onToolSource={(nextDocumentId, chunkId, jobId) => { setGraphView('sources'); setDocumentId(nextDocumentId); setMapFocus({nodeId: chunkId || nextDocumentId, nonce: Date.now(), kind: 'source'}); setReaderRequest({documentId:nextDocumentId,chunkId,jobId,nonce:Date.now()}); }} onTrace={assertionIds => { setGraphTrace({assertionIds, nonce: Date.now()}); setMapFocus(null); setGraphView('knowledge'); showGraph(); }} onResume={() => void resume(turn)} /></div>)}
          </div>
          <form className="ce-composer-wrap" onSubmit={submit}><div className="ce-composer"><button type="button" className="ce-icon" onClick={upload} aria-label="Add files"><Paperclip size={20} /></button><textarea ref={composer} value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit(); } }} rows={1} placeholder="Ask about your sources…" aria-label="Message" disabled={busy} /><button type="submit" className="ce-send" disabled={busy || !query.trim()} aria-label="Send message">{busy ? <Loader2 size={18} className="spinning" /> : <ArrowUp size={19} />}</button></div></form>
        </ResizablePanel>
        <ResizableHandle withHandle className="ce-resize" />
        <ResizablePanel defaultSize={48} minSize={28} className="ce-explorer-panel">
          <div className="ce-explorer-shell" aria-labelledby="source-explorer-title">
          <div className="ce-explorer-heading"><div className="ce-workspace-title"><h2 id="source-explorer-title" className="ce-project-name">{project?.name || 'Workspace'}</h2><span className={`ce-live-processing ${runningJob ? 'is-working' : ''}`} role="status" aria-live="polite" title={liveProcessingStatus}>{liveProcessingStatus}</span></div><div className="ce-explorer-actions"><button className="ce-queue-control" onClick={() => void controlIngestion('pause')} disabled={!project || queueControlBusy !== null || queuePaused === true} aria-label="Pause ingestion">{queueControlBusy === 'pause' ? <Loader2 size={14} className="spinning" /> : <Pause size={14} />}<span>Pause ingestion</span></button><button className="ce-queue-control" onClick={() => void controlIngestion('resume')} disabled={!project || queueControlBusy !== null || queuePaused === false} aria-label="Resume ingestion">{queueControlBusy === 'resume' ? <Loader2 size={14} className="spinning" /> : <Play size={14} />}<span>Resume ingestion</span></button><button className="ce-add-files" onClick={upload} disabled={!project}><Plus size={16} />Add files</button></div></div>
          {(queueControlError || queueControlStatus) && <div className={`ce-queue-control-message ${queueControlError ? 'is-error' : ''}`} role={queueControlError ? 'alert' : 'status'} aria-live="polite">{queueControlError || queueControlStatus}</div>}
          {projectError && <p className="ce-inline-error" role="alert">{projectError} <a href="/">Return to projects</a></p>}
          <div className="ce-explorer-content">
            <ResizablePanelGroup direction="vertical" className="ce-source-panels" autoSaveId={`argus-source-split:${projectId}`}>
              <ResizablePanel ref={filePanel} defaultSize={30} minSize={15} className="ce-project-file-panel">
                {project ? <ProjectSources project={project} uploadRequest={uploadRequest} refreshVersion={dataVersion} focus={pipelineFocus} readerRequest={readerRequest} documentId={documentId} chunkId={selectedNode?.type === 'chunk' ? selectedNode.id : undefined} onProject={setProject} onJobsChange={setWorkspaceJobs} onUploaded={() => setDataVersion(version => version + 1)} onBackToGraph={() => { setDocumentId(undefined); setPipelineFocus(null); setGraphView('knowledge'); graphPanel.current?.resize(70); }} onFocus={(id, chunkId) => { focusSource(id, chunkId); setGraphView('sources'); setMapFocus({nodeId: chunkId || id, nonce: Date.now(), kind: 'source'}); }} /> : !projectError && <div className="ce-file-empty" role="status">Loading workspace…</div>}
              </ResizablePanel>
              <ResizableHandle withHandle className="ce-source-resize" aria-label="Resize files and graph" />
              <ResizablePanel ref={graphPanel} defaultSize={70} minSize={10} onResize={size => setGraphCompact(size < 20)} className={`ce-project-graph-panel ${graphCompact ? 'is-compact' : ''}`}>
              {graphView === 'sources' && <div className="ce-map-toolbar">{graphSwitcher}</div>}
              <div className={`ce-project-graph-content${graphFullscreen && graphView === 'sources' ? ' is-fullscreen' : ''}`}>
                {graphView === 'knowledge' ? <KnowledgeGraph apiRoot={root} refreshToken={graphVersion} expanded={graphFullscreen} onExpand={() => setGraphFullscreen(value => !value)} viewSwitcher={graphSwitcher} focus={mapFocus} trace={graphTrace} onSource={target => { setGraphView('sources'); setMapFocus({nodeId: target.nodeId, nonce: Date.now(), kind: 'source'}); graphPanel.current?.resize(75); }} /> : <GraphMap apiRoot={root} refreshToken={graphVersion} focus={mapFocus} expanded={graphFullscreen} onExpand={() => setGraphFullscreen(value => !value)} onSelect={selectNode} onFocus={target => { if (target.documentId) focusSource(target.documentId, target.chunkId); }} />}
                {chatConfig?.coverage.publishedDocuments === 0 && <div className="ce-project-graph-empty"><p>Your graph starts here.<br />Connections appear as source files finish ingestion.</p></div>}
              </div>
              </ResizablePanel>
            </ResizablePanelGroup>
          </div>
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </main>
    <dialog ref={nodeDialog} className="ce-node-dialog" onCancel={() => setSelectedNode(null)} onClick={event => { if (event.target === event.currentTarget) setSelectedNode(null); }} aria-labelledby="node-title">
      <div className="ce-node-dialog-heading"><h2 id="node-title">{selectedNode?.type === 'chunk' ? 'Chunk preview' : selectedNode?.type === 'document' ? 'Source document' : selectedNode?.label}</h2><button className="ce-icon" onClick={() => setSelectedNode(null)} aria-label="Close node details"><X size={18} /></button></div>
      {selectedNode?.documentId && <div className="ce-node-source"><span>Source</span><button disabled={!sourceTitle} onClick={() => { if (selectedNode?.documentId) { showGraph(); setMapFocus({nodeId:selectedNode.documentId,nonce:Date.now(),kind:'source'}); } setSelectedNode(null); }}>{sourceTitle || 'Loading document…'}{sourceTitle && <ArrowUpRight size={15} />}</button></div>}
      {selectedNode?.type === 'entity' && typeof nodeDetails?.description === 'string' && <p className="ce-node-description">{nodeDetails.description}</p>}
      {selectedNode?.type !== 'document' && <p className="ce-node-content">{typeof recordContent?.text === 'string' ? recordContent.text : selectedChunk?.text || selectedSection?.title || selectedNode?.preview}</p>}
      <div className="ce-node-actions">{selectedNode?.type === 'chunk' && <button className="ce-open-file" onClick={() => { setMapFocus({nodeId:selectedNode.id,nonce:Date.now(),kind:'source'}); showGraph(); setSelectedNode(null); }}><Network size={15} />Explore connections</button>}<button className="ce-open-file" onClick={() => { if (selectedNode) setMapFocus({nodeId:selectedNode.id,nonce:Date.now(),kind:selectedNode.type === 'entity' ? 'entity' : 'source'}); showGraph(); setSelectedNode(null); }}><Network size={15} />Show in graph</button></div>
    </dialog>
  </div>;
}
