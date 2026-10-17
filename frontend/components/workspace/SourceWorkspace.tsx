'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowUp, ArrowUpRight, ChevronDown, FileText, Loader2, Maximize2, MessageSquare, Minimize2, Moon, Network, PanelLeftClose, PanelLeftOpen, Paperclip, Plus, Settings2, Sun, Upload, X } from 'lucide-react';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable';
import { Switch } from '@/components/ui/switch';
import { CitationButton } from '@/components/CitationButton';
import { FileExplorer } from '@/components/source-explorer/FileExplorer';
import { GraphMap, type MapNode } from '@/components/source-explorer/GraphMap';
import { useSearchOptions } from '@/hooks/use-search-options';
import { api, type DocumentSummary, type EvidenceDocument, type EvidenceResult, type SearchRun } from '@/lib/evidence-types';

type Turn = { id: string; query: string; run?: SearchRun; error?: string };

export function SourceWorkspace() {
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
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const { options, updateOptions } = useSearchOptions('source-workspace');
  const messages = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const nodeDialog = useRef<HTMLDialogElement>(null);
  const explorerDialog = useRef<HTMLDialogElement>(null);
  const pendingChunk = useRef<string | undefined>(undefined);

  useEffect(() => {
    setMapMode(localStorage.getItem('argus-map-mode') === 'grouped' ? 'grouped' : 'network');
    const value = localStorage.getItem('falkor-theme') === 'dark';
    setDark(value);
    window.document.documentElement.classList.toggle('dark', value);
    void api<{ documents: DocumentSummary[] }>('/documents?limit=1').then(result => setDocumentId(current => current || result.documents[0]?.id)).catch(failure => setGraphError(failure.message));
  }, []);

  useEffect(() => {
    if (!documentId) return;
    let active = true;
    void api<EvidenceDocument>(`/documents/${encodeURIComponent(documentId)}`).then(next => {
      if (!active) return;
      setDocument(next);
      const chunk = next.chunks.find(item => item.id === pendingChunk.current) || next.chunks[0];
      setSelectedId(chunk?.id || next.id);
      pendingChunk.current = undefined;
    }).catch(failure => { if (active) setGraphError(failure.message); });
    return () => { active = false; };
  }, [documentId]);

  useEffect(() => {
    if (!selectedNode) { setNodeDetails(null); return; }
    let active = true;
    setNodeDetails(null);
    void api<Record<string, unknown>>(`/map/node/${encodeURIComponent(selectedNode.id)}?mode=${mapMode}`).then(next => { if (active) setNodeDetails(next); }).catch(() => undefined);
    return () => { active = false; };
  }, [selectedNode, mapMode]);

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

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    window.document.documentElement.classList.toggle('dark', next);
    localStorage.setItem('falkor-theme', next ? 'dark' : 'light');
  };
  const focusSource = (nextDocumentId: string, chunkId?: string) => {
    if (nextDocumentId !== documentId) { pendingChunk.current = chunkId; setDocumentId(nextDocumentId); }
    else {
      setSelectedId(chunkId || nextDocumentId);
    }
  };
  const selectCitation = (source: EvidenceResult) => { focusSource(source.documentId, source.chunkId); setMapFocus({nodeId:source.chunkId,nonce:Date.now()}); setView('graph'); };
  const selectNode = (node: MapNode) => { if (node.documentId) focusSource(node.documentId, node.chunkId); setSelectedId(node.id); setSelectedNode(node); };
  const upload = () => { setView('files'); setUploadRequest(previous => previous + 1); };
  const submit = async (event?: FormEvent, suggestion?: string) => {
    event?.preventDefault();
    const value = (suggestion || query).trim();
    if (!value || busy) return;
    const id = crypto.randomUUID();
    setTurns(previous => [...previous, { id, query: value }]);
    setQuery(''); setBusy(true);
    try {
      const run = await api<SearchRun>('/search', { method: 'POST', body: JSON.stringify({ query: value, options: { graphExpansion: options.graphExpansion, limit: 8 } }) });
      setTurns(previous => previous.map(turn => turn.id === id ? { ...turn, run } : turn));
    } catch (failure) { setTurns(previous => previous.map(turn => turn.id === id ? { ...turn, error: failure instanceof Error ? failure.message : 'Search failed. Please retry.' } : turn)); }
    finally { setBusy(false); }
  };
  const selectedChunk = document?.chunks.find(chunk => chunk.id === (selectedNode?.chunkId || selectedNode?.id));
  const selectedSection = document?.sections.find(section => section.id === (selectedNode?.sectionId || selectedNode?.id));
  const recordContent = nodeDetails?.content && typeof nodeDetails.content === 'object' ? nodeDetails.content as Record<string, unknown> : null;
  const selectedSource = document?.id === selectedNode?.documentId ? document : null;
  const sourceTitle = selectedSource?.title || (selectedNode?.type === 'document' ? selectedNode.preview || selectedNode.label : null);

  return <div className={`ce-workspace ${sidebarOpen ? '' : 'ce-sidebar-collapsed'}`}>
    <aside className="ce-sidebar">
      <div className="ce-brand"><img src="/cosmic-logo.png" alt="" width={29} height={29} /><strong>Argus</strong><button className="ce-icon" onClick={() => setSidebarOpen(false)} aria-label="Collapse sidebar"><PanelLeftClose size={17} /></button></div>
      <button className="ce-new-chat" onClick={() => { setTurns([]); setQuery(''); composer.current?.focus(); }} disabled={busy}><Plus size={17} />New chat</button>
      <div className="ce-navigation-label">Your workspace</div>
      <button className="ce-session active" onClick={() => messages.current?.scrollTo({ top: 0, behavior: 'smooth' })}><MessageSquare size={16} /><span>Materials & water</span></button>
      <div className="ce-sidebar-bottom"><div className="ce-user"><span className="ce-avatar">AT</span><span><strong>Arpan Taneja</strong><small>Local workspace · demo profile</small></span></div><button className="ce-theme" onClick={toggleTheme} aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`}>{dark ? <Sun size={16} /> : <Moon size={16} />}<span>{dark ? 'Light mode' : 'Dark mode'}</span></button></div>
    </aside>
    <main className="ce-main">
      <ResizablePanelGroup direction="horizontal" className="ce-panels">
        <ResizablePanel defaultSize={52} minSize={30} className="ce-chat-panel">
          <div className="ce-chat-heading">{!sidebarOpen && <><button className="ce-icon" onClick={() => setSidebarOpen(true)} aria-label="Expand sidebar"><PanelLeftOpen size={18} /></button><span className="ce-mobile-brand">Argus</span></>}<span>Chat</span><button className="ce-icon ce-mobile-theme" onClick={toggleTheme} aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`}>{dark ? <Sun size={16} /> : <Moon size={16} />}</button><button className="ce-icon ce-mobile-source" onClick={() => window.document.querySelector('.ce-explorer-panel')?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'})} aria-label="Open Source Explorer"><Network size={17} /></button></div>
          <div className="ce-messages" ref={messages}>
            {!turns.length && <div className="ce-chat-empty"><img src="/cosmic-logo.png" alt="" width={46} height={46} /><h1>Start with a question.</h1><p>Explore your sources, follow their connections,<br />and pick up right where a citation leads.</p><div className="ce-suggestions"><button onClick={() => void submit(undefined, 'adsorption regeneration water')}>Find research on water treatment<ArrowUp size={14} /></button><button onClick={() => void submit(undefined, 'metal organic framework pollutant removal')}>Explore metal–organic frameworks<ArrowUp size={14} /></button></div></div>}
            {turns.map(turn => <div className="ce-turn" key={turn.id}><div className="ce-user-message">{turn.query}</div><div className="ce-response"><div className="ce-response-name"><img src="/cosmic-logo.png" alt="" width={22} height={22} /><strong>Source search</strong></div>{turn.error ? <div className="ce-inline-error" role="alert">{turn.error}</div> : !turn.run ? <div className="ce-searching"><Loader2 size={15} className="spinning" />Searching your sources…</div> : <><p className="ce-response-summary">{turn.run.results.length ? `Found ${turn.run.results.length} source matches. Select a citation to explore its location in the graph.` : 'No source matches. Try another phrase or a more specific term.'}</p><p className="ce-retrieval-note">Retrieved excerpts · answer generation is not connected</p>{turn.run.results.map((source, index) => <article className={`ce-source-match ${selectedId === source.chunkId ? 'is-focused' : ''}`} key={source.chunkId}><h2>{source.documentTitle}</h2><p>{source.text.length > 550 ? `${source.text.slice(0, 550)}…` : source.text}</p><CitationButton citation={source} index={index + 1} onCitationClick={() => selectCitation(source)} selected={selectedId === source.chunkId} /></article>)}</>}</div></div>)}
          </div>
          <form className="ce-composer-wrap" onSubmit={submit}><div className="ce-composer"><button type="button" className="ce-icon" onClick={upload} aria-label="Upload a file"><Paperclip size={20} /></button><textarea ref={composer} value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit(); } }} rows={1} placeholder="Ask about your sources…" aria-label="Message" disabled={busy} /><button type="submit" className="ce-send" disabled={busy || !query.trim()} aria-label="Send message">{busy ? <Loader2 size={18} className="spinning" /> : <ArrowUp size={19} />}</button></div></form>
        </ResizablePanel>
        <ResizableHandle withHandle className="ce-resize" />
        <ResizablePanel defaultSize={48} minSize={28} className="ce-explorer-panel">
          <dialog open ref={explorerDialog} className={`ce-explorer-shell ${explorerExpanded ? 'is-expanded' : ''}`} aria-labelledby="source-explorer-title" onCancel={event => { event.preventDefault(); if (explorerExpanded) setExplorerExpanded(false); }}>
          <div className="ce-explorer-heading"><h2 id="source-explorer-title">Source Explorer</h2><div className="ce-explorer-actions"><button className="ce-icon" onClick={() => setExplorerExpanded(previous => !previous)} title={explorerExpanded ? 'Restore Source Explorer' : 'Expand Source Explorer'} aria-label={explorerExpanded ? 'Restore Source Explorer' : 'Expand Source Explorer'}>{explorerExpanded ? <Minimize2 size={17} /> : <Maximize2 size={17} />}</button><button className="ce-icon" onClick={upload} title="Upload file" aria-label="Upload file"><Upload size={17} /></button><button className={`ce-icon ${view === 'files' ? 'is-active' : ''}`} onClick={() => setView(previous => previous === 'graph' ? 'files' : 'graph')} title={view === 'graph' ? 'Open file viewer' : 'Open graph'} aria-label={view === 'graph' ? 'Open file viewer' : 'Open graph'}>{view === 'graph' ? <FileText size={18} /> : <Network size={18} />}</button><button className={`ce-configuration-button ${configurationOpen ? 'is-active' : ''}`} onClick={() => setConfigurationOpen(previous => !previous)} aria-label="Engine configuration" aria-expanded={configurationOpen} aria-controls="engine-configuration"><Settings2 size={16} /><span>Engine configuration</span><ChevronDown size={12} /></button></div></div>
          {view === 'graph' && <div className="ce-map-toolbar"><div className="ce-map-modes" role="group" aria-label="Graph layout"><button aria-pressed={mapMode === 'network'} onClick={() => { setMapMode('network'); localStorage.setItem('argus-map-mode', 'network'); }}>Network</button><button aria-pressed={mapMode === 'grouped'} onClick={() => { setMapMode('grouped'); localStorage.setItem('argus-map-mode', 'grouped'); }}>Trees</button></div><span title="This view uses the original dictionary-based corpus. New processing results are available in Files.">Legacy graph · {mapMode === 'network' ? 'Shared mentions' : 'Document branches'}</span></div>}
          {configurationOpen && <section id="engine-configuration" className="ce-configuration"><div><strong>Engine configuration</strong><button className="ce-icon" onClick={() => setConfigurationOpen(false)} aria-label="Close engine configuration"><X size={16} /></button></div><label><span>Graph expansion<small>Follow shared connections after search</small></span><Switch checked={options.graphExpansion} onCheckedChange={checked => updateOptions({ graphExpansion: checked })} /></label><label><span>BM25 search<small>Lexical retrieval · always on</small></span><Switch checked disabled /></label><label><span>Vector search + RRF<small>Embedding pipeline not connected</small></span><Switch checked={false} disabled /></label><p>Changes apply to your next message.</p></section>}
          <div className="ce-explorer-content">{view === 'graph' ? <>{graphError && <div className="ce-inline-error" role="alert">{graphError}</div>}<GraphMap mode={mapMode} expanded={explorerExpanded} onExpand={() => setExplorerExpanded(previous => !previous)} focus={mapFocus} onSelect={selectNode} onFocus={target => { if (target.documentId) focusSource(target.documentId, target.chunkId); }} /></> : <FileExplorer focusDocumentId={documentId} focusChunkId={selectedId || undefined} uploadRequest={uploadRequest} onDocumentFocus={(id, chunkId) => { focusSource(id, chunkId); if (chunkId) { setMapFocus({nodeId:chunkId,nonce:Date.now()}); setView('graph'); } }} />}</div>
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
