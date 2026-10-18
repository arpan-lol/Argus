'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowUp, ArrowUpRight, ChevronDown, FileText, Loader2, MessageSquare, Moon, Network, PanelLeftClose, PanelLeftOpen, Paperclip, Plus, Settings2, Sun, Upload, X } from 'lucide-react';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable';
import { Switch } from '@/components/ui/switch';
import { ChatResponse } from './ChatResponse';
import { streamChat, type ChatTurn, type ChatSource, type ChatResult, type ChatEvent, type SavedChat, type ChatCoverage } from '@/lib/chat';
import { ProjectSources } from '@/components/source-explorer/ProjectSources';
import { ProcessingActivity } from '@/components/source-explorer/ProcessingActivity';
import { projectRoot, type Project, type ProcessingEvent } from '@/lib/projects';
import { normalizeSourceDocument } from '@/lib/ingestion-types';
import { GraphMap, type MapNode } from '@/components/source-explorer/GraphMap';
import { useSearchOptions } from '@/hooks/use-search-options';
import { api, type DocumentSummary, type EvidenceDocument } from '@/lib/evidence-types';
import { statusLabel } from '@/lib/ingestion-types';



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
  const [streamConnected, setStreamConnected] = useState(false);
  const [dataVersion, setDataVersion] = useState(0);
  const [graphVersion, setGraphVersion] = useState(0);

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [dark, setDark] = useState(false);
  const [mapMode, setMapMode] = useState<'network' | 'grouped'>('network');
  const [explorerExpanded, setExplorerExpanded] = useState(false);
  const [view, setView] = useState<'graph' | 'files'>('graph');
  const [configurationOpen, setConfigurationOpen] = useState(false);
  const [uploadRequest, setUploadRequest] = useState(0);
  const [documentId, setDocumentId] = useState<string>();
  const [document, setDocument] = useState<EvidenceDocument | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mapFocus, setMapFocus] = useState<{nodeId: string; nonce: number} | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<MapNode | null>(null);
  const [nodeDetails, setNodeDetails] = useState<Record<string, unknown> | null>(null);
  const [query, setQuery] = useState('');
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [pipelineFocus, setPipelineFocus] = useState<ChatSource | null>(null);
  const [chatConfig, setChatConfig] = useState<{model: string; coverage: ChatCoverage} | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeTurnId, setActiveTurnId] = useState<string>();
  const { options, updateOptions } = useSearchOptions('source-workspace');
  const messages = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const nodeDialog = useRef<HTMLDialogElement>(null);
  const explorerDialog = useRef<HTMLDialogElement>(null);
  const pendingChunk = useRef<string | undefined>(undefined);

  useEffect(() => {
    void workspaceApi<{model: string; coverage: ChatCoverage}>('/chat-config').then(setChatConfig).catch(() => undefined);
    const saved = savedRuns(projectId);
    void Promise.all(saved.slice(-12).map(id => workspaceApi<SavedChat>(`/chat/${id}`).catch(() => null))).then(runs => setTurns(runs.filter((run): run is SavedChat => !!run).map(run => ({id: run.runId, runId: run.runId, query: run.query, model: run.model, events: run.events, result: run.result || undefined, error: run.result ? undefined : run.error || 'This investigation has saved progress. Reconnect to continue.'}))));
    setMapMode(localStorage.getItem('argus-map-mode') === 'grouped' ? 'grouped' : 'network');
    const value = localStorage.getItem('falkor-theme') === 'dark';
    setDark(value);
    window.document.documentElement.classList.toggle('dark', value);
    void workspaceApi<{ documents: DocumentSummary[] }>('/ingestion/documents?limit=1').then(result => setDocumentId(current => current || result.documents[0]?.id)).catch(failure => setGraphError(failure.message));
  }, []);

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
    void workspaceApi<Record<string, unknown>>(`/map/node/${encodeURIComponent(selectedNode.id)}?mode=${mapMode}`).then(next => { if (active) setNodeDetails(next); }).catch(() => undefined);
    return () => { active = false; };
  }, [selectedNode, mapMode, workspaceApi]);

  useEffect(() => {
    const dialog = explorerDialog.current;
    if (!dialog) return;
    if (explorerExpanded) {
      if (dialog.open) dialog.close();
      dialog.showModal();
    } else if (dialog.matches(':modal')) {
      dialog.close();
      dialog.show();
    } else if (!dialog.open) dialog.show();
    const previousOverflow = window.document.body.style.overflow;
    if (explorerExpanded) window.document.body.style.overflow = 'hidden';
    return () => { window.document.body.style.overflow = previousOverflow; };
  }, [explorerExpanded]);

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
    void workspaceApi<Project>('').then(value => {
      if (!active) return;
      setProject(value);
      stream = new EventSource(`/api${root}/events?after=${Math.max(0, (value.lastEventSequence || 0) - 300)}`);
      stream.onopen = () => { setStreamConnected(true); setDataVersion(version => version + 1); };
      stream.onerror = () => setStreamConnected(false);
      stream.onmessage = message => {
        const event = JSON.parse(message.data) as ProcessingEvent;
        setProcessingEvents(previous => previous.some(item => item.sequence === event.sequence) ? previous : [...previous, event].slice(-300));
        if (event.type === 'graph_updated') {
          setGraphVersion(version => version + 1);
          void workspaceApi<{model: string; coverage: ChatCoverage}>('/chat-config').then(setChatConfig).catch(() => undefined);
        }
        window.clearTimeout(refreshTimer);
        refreshTimer = window.setTimeout(() => setDataVersion(version => version + 1), 200);
      };
    }).catch(error => { if (active) setProjectError(error.message); });
    return () => { active = false; stream?.close(); window.clearTimeout(refreshTimer); };
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
  const selectCitation = (source: ChatSource) => { setPipelineFocus(source); setDocumentId(source.documentId); setMapFocus({nodeId: source.chunkId, nonce: Date.now()}); };
  const selectNode = (node: MapNode) => { if (node.documentId) focusSource(node.documentId, node.chunkId); setSelectedId(node.id); setSelectedNode(node); };
  const upload = () => { setView('files'); setUploadRequest(previous => previous + 1); };
  const recentEvent = processingEvents.at(-1);
  const lastProcessingEvent = recentEvent && ['stage_start', 'item_start', 'item_complete', 'item_failed'].includes(recentEvent.type) ? recentEvent : undefined;
  const processingStart = lastProcessingEvent && processingEvents.find(event => event.jobId === lastProcessingEvent.jobId && event.type === 'stage_start')?.at;
  useEffect(() => {
    if (!lastProcessingEvent) return;
    const timer = window.setInterval(() => setClockNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [lastProcessingEvent?.jobId]);
  const elapsedSeconds = processingStart ? Math.max(0, Math.floor((clockNow - new Date(processingStart).getTime()) / 1000)) : 0;
  const elapsedLabel = elapsedSeconds >= 60 ? `${Math.floor(elapsedSeconds / 60)}m ${String(elapsedSeconds % 60).padStart(2, '0')}s` : `${elapsedSeconds}s`;
  const liveProcessingStatus = lastProcessingEvent ? `${lastProcessingEvent.filename ? `${lastProcessingEvent.filename} · ` : ''}${statusLabel(lastProcessingEvent.stage || lastProcessingEvent.type)}${lastProcessingEvent.counts ? ` · ${Object.entries(lastProcessingEvent.counts).map(([name, count]) => `${count.toLocaleString()} ${name}`).join(', ')}` : ''} · Worked for ${elapsedLabel} ›` : undefined;
  const receive = (id: string, event: ChatEvent) => {
    if (event.type === 'accepted' && event.runId) {
      const saved = savedRuns(projectId);
      sessionStorage.setItem(`argus-chat-runs:${projectId}`, JSON.stringify([...new Set([...saved, event.runId])].slice(-12)));
    }
    setTurns(previous => previous.map(turn => turn.id === id ? {
      ...turn, runId: event.runId || turn.runId, model: event.model || turn.model,
      events: [...turn.events, event],
      ...(event.type === 'done' ? {result: event as unknown as ChatResult, error: undefined} : {}),
      ...(event.type === 'error' ? {error: event.message || 'The investigation stopped. Resume to retry.'} : {}),
    } : turn));
  };
  const resume = async (turn: ChatTurn) => {
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
    const history = turns.filter(turn => turn.result).slice(-2).flatMap(turn => [
      {role: 'user', content: turn.query.slice(0, 2000)},
      {role: 'assistant', content: turn.result!.report.paragraphs.map(paragraph => paragraph.text).join('\n').slice(0, 2000)},
    ]);
    setTurns(previous => [...previous, {id, query: value, model: chatConfig?.model, events: []}]);
    setQuery(''); setBusy(true); setActiveTurnId(id);
    try { await streamChat(`${root}/chat`, {query: value, history, graph_expansion: options.graphExpansion}, event => receive(id, event)); }
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
      <button className="ce-session ce-new-chat" onClick={() => { setTurns([]); sessionStorage.removeItem(`argus-chat-runs:${projectId}`); setQuery(''); composer.current?.focus(); }} disabled={busy}><Plus size={17} /><span>New chat</span></button>
      <button className="ce-session active" onClick={() => messages.current?.scrollTo({ top: 0, behavior: 'smooth' })}><MessageSquare size={16} /><span>Current conversation</span></button>
      <div className="ce-sidebar-bottom"><button className={`ce-theme ${configurationOpen ? 'is-active' : ''}`} onClick={() => setConfigurationOpen(previous => !previous)} aria-label="Engine configuration" aria-expanded={configurationOpen}><Settings2 size={16} /><span>Engine configuration</span></button><div className="ce-user"><span className="ce-avatar">AT</span><span><strong>Arpan Taneja</strong><small>Local workspace · demo profile</small></span></div><button className="ce-theme" onClick={toggleTheme} aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`}>{dark ? <Sun size={16} /> : <Moon size={16} />}<span>{dark ? 'Light mode' : 'Dark mode'}</span></button></div>
    </aside>
    <main className="ce-main">
      <ResizablePanelGroup direction="horizontal" className="ce-panels">
        <ResizablePanel defaultSize={52} minSize={30} className="ce-chat-panel">
          <div className="ce-chat-heading">{!sidebarOpen && <><button className="ce-icon" onClick={() => setSidebarOpen(true)} aria-label="Expand sidebar"><PanelLeftOpen size={18} /></button><span className="ce-mobile-brand">Argus</span></>}<span>Chat</span><button className="ce-icon ce-mobile-theme" onClick={toggleTheme} aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`}>{dark ? <Sun size={16} /> : <Moon size={16} />}</button><button className="ce-icon ce-mobile-source" onClick={() => window.document.querySelector('.ce-explorer-panel')?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'})} aria-label="Open files and graph"><Network size={17} /></button></div>
          <div className="ce-messages" ref={messages}>
            {!turns.length && <div className="ce-chat-empty"><img src="/argus-logo.svg" alt="" width={46} height={46} /><h1>Start with a question.</h1><p>Ask Argus a question and open its citations.<br />{chatConfig ? `${chatConfig.model.toUpperCase()} · ${chatConfig.coverage.publishedDocuments} published sources available` : 'Connecting to the assistant…'}</p><div className="ce-suggestions"><button onClick={() => void submit(undefined, 'Summarize a published source')}>Summarize a published source<ArrowUp size={14} /></button><button onClick={() => void submit(undefined, 'What sources can you search?')}>What can you search?<ArrowUp size={14} /></button></div></div>}
            {turns.map(turn => <div className="ce-turn" key={turn.id}><div className="ce-user-message">{turn.query}</div><ChatResponse turn={turn} pending={busy && turn.id === activeTurnId && !turn.result && !turn.error} onCitation={selectCitation} onResume={() => void resume(turn)} /></div>)}
          </div>
          <ProcessingActivity projectId={projectId} events={processingEvents} connected={streamConnected} />
          <form className="ce-composer-wrap" onSubmit={submit}><div className="ce-composer"><button type="button" className="ce-icon" onClick={upload} aria-label="Add files"><Paperclip size={20} /></button><textarea ref={composer} value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit(); } }} rows={1} placeholder="Ask about your sources…" aria-label="Message" disabled={busy} /><button type="submit" className="ce-send" disabled={busy || !query.trim()} aria-label="Send message">{busy ? <Loader2 size={18} className="spinning" /> : <ArrowUp size={19} />}</button></div></form>
        </ResizablePanel>
        <ResizableHandle withHandle className="ce-resize" />
        <ResizablePanel defaultSize={48} minSize={28} className="ce-explorer-panel">
          <dialog open ref={explorerDialog} className={`ce-explorer-shell ${explorerExpanded ? 'is-expanded' : ''}`} aria-labelledby="source-explorer-title" onCancel={event => { event.preventDefault(); if (explorerExpanded) setExplorerExpanded(false); }}>
          <div className="ce-explorer-heading"><h2 id="source-explorer-title" className="ce-project-name">{project?.name || 'Workspace'}</h2>{liveProcessingStatus && <span className="ce-live-processing" role="status" aria-live="polite">{liveProcessingStatus}</span>}<div className="ce-explorer-actions">{view === 'files' && <button className="ce-graph-return" onClick={() => setView('graph')}><Network size={15} />Graph</button>}<button className="ce-add-files" onClick={upload}><Plus size={16} />Add files</button></div></div>
          {configurationOpen && <section id="engine-configuration" className="ce-configuration"><div><strong>Engine configuration</strong><button className="ce-icon" onClick={() => setConfigurationOpen(false)} aria-label="Close engine configuration"><X size={16} /></button></div><label><span>Graph expansion<small>Follow shared connections after search</small></span><Switch checked={options.graphExpansion} onCheckedChange={checked => updateOptions({ graphExpansion: checked })} /></label><p>{chatConfig?.model.toUpperCase() || 'GPT-5'} · {chatConfig?.coverage.publishedDocuments ?? '…'} searchable sources in this project.</p><p>{project?.description || 'Add sources to describe this workspace.'}</p></section>}
          {projectError && <p className="ce-inline-error" role="alert">{projectError} <a href="/">Return to projects</a></p>}
          <div className="ce-explorer-content">
            {view === 'files' ? project ? <ProjectSources project={project} uploadRequest={uploadRequest} refreshVersion={dataVersion} focus={pipelineFocus} documentId={documentId} chunkId={selectedNode?.type === 'chunk' ? selectedNode.id : undefined} onProject={setProject} onUploaded={() => setDataVersion(version => version + 1)} onOpenReader={() => setView('files')} onBackToGraph={() => setView('graph')} onFocus={(id, chunkId) => { focusSource(id, chunkId); if (chunkId) setMapFocus({nodeId: chunkId, nonce: Date.now()}); }} /> : !projectError && <div className="ce-file-empty" role="status">Loading workspace…</div> : <div className="ce-project-graph-panel">
              <div className="ce-map-toolbar"><h2>Graph</h2><div className="ce-map-modes" role="group" aria-label="Graph layout"><button aria-pressed={mapMode === 'network'} onClick={() => { setMapMode('network'); localStorage.setItem('argus-map-mode', 'network'); }}>Network</button><button aria-pressed={mapMode === 'grouped'} onClick={() => { setMapMode('grouped'); localStorage.setItem('argus-map-mode', 'grouped'); }}>Trees</button></div></div>
              <div className="ce-project-graph-content"><GraphMap apiRoot={root} refreshToken={graphVersion} mode={mapMode} focus={mapFocus} onSelect={selectNode} onFocus={target => { if (target.documentId) focusSource(target.documentId, target.chunkId); }} />{chatConfig?.coverage.publishedDocuments === 0 && <div className="ce-project-graph-empty"><p>Your graph starts here.<br />Connections appear as source files finish ingestion.</p></div>}</div>
            </div>}
          </div>
          </dialog>
        </ResizablePanel>
      </ResizablePanelGroup>
    </main>
    <dialog ref={nodeDialog} className="ce-node-dialog" onCancel={() => setSelectedNode(null)} onClick={event => { if (event.target === event.currentTarget) setSelectedNode(null); }} aria-labelledby="node-title">
      <div className="ce-node-dialog-heading"><h2 id="node-title">{selectedNode?.type === 'chunk' ? 'Chunk preview' : selectedNode?.type === 'document' ? 'Source document' : selectedNode?.label}</h2><button className="ce-icon" onClick={() => setSelectedNode(null)} aria-label="Close node details"><X size={18} /></button></div>
      {selectedNode?.documentId && <div className="ce-node-source"><span>Source</span><button disabled={!sourceTitle} onClick={() => { if (selectedNode?.documentId) { setView('graph'); setMapFocus({nodeId:selectedNode.documentId,nonce:Date.now()}); } setSelectedNode(null); }}>{sourceTitle || 'Loading document…'}{sourceTitle && <ArrowUpRight size={15} />}</button></div>}
      {(selectedNode?.type === 'entity' || selectedNode?.type === 'group') && typeof nodeDetails?.description === 'string' && <p className="ce-node-description">{nodeDetails.description}</p>}
      {selectedNode?.type !== 'document' && <p className="ce-node-content">{typeof recordContent?.text === 'string' ? recordContent.text : selectedChunk?.text || selectedSection?.title || selectedNode?.preview}</p>}
      <div className="ce-node-actions">{selectedNode?.type === 'chunk' && <button className="ce-open-file" onClick={() => { setMapFocus({nodeId:selectedNode.id,nonce:Date.now()}); setView('graph'); setSelectedNode(null); }}><Network size={15} />Explore connections</button>}{selectedNode?.documentId ? <button className="ce-open-file" onClick={() => { if (selectedNode?.documentId) focusSource(selectedNode.documentId, selectedNode.chunkId || (selectedNode.type === 'chunk' ? selectedNode.id : undefined)); setView('files'); setSelectedNode(null); }}><FileText size={15} />Read file</button> : <button className="ce-open-file" onClick={() => { if (selectedNode) setMapFocus({nodeId:selectedNode.id,nonce:Date.now()}); setSelectedNode(null); }}><Network size={15} />Show in graph</button>}</div>
    </dialog>
  </div>;
}
