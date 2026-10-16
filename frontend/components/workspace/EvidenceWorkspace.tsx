'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { Activity, ArrowDownToLine, ArrowRight, BookOpen, Check, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, Database, ExternalLink, FileText, FlaskConical, Layers3, Loader2, Network, PanelLeftClose, PanelLeftOpen, RefreshCw, Search, Settings2, SlidersHorizontal, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable';
import { CitationButton } from '@/components/CitationButton';
import { GraphCanvas } from './GraphCanvas';
import { useSearchOptions } from '@/hooks/use-search-options';
import { api, chunkColor, type Chunk, type Corpus, type DocumentSummary, type EvidenceDocument, type EvidenceGraph, type EvidenceResult, type GraphNode, type SearchRun } from '@/lib/evidence-types';

const number = (value?: number) => new Intl.NumberFormat().format(value || 0);
const ms = (value: number) => `${value.toFixed(value < 10 ? 2 : 1)} ms`;

export function EvidenceWorkspace() {
  const [corpus, setCorpus] = useState<Corpus | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [documentTotal, setDocumentTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [diagnostics, setDiagnostics] = useState<Record<string, unknown> | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [document, setDocument] = useState<EvidenceDocument | null>(null);
  const [sectionId, setSectionId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [graph, setGraph] = useState<EvidenceGraph | null>(null);
  const [filter, setFilter] = useState('');
  const [query, setQuery] = useState('adsorption regeneration water');
  const [run, setRun] = useState<SearchRun | null>(null);
  const [runs, setRuns] = useState<SearchRun[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [documentLoading, setDocumentLoading] = useState(false);
  const [graphLoading, setGraphLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inspectorTab, setInspectorTab] = useState<'trace' | 'record' | 'corpus'>('trace');
  const [libraryOpen, setLibraryOpen] = useState(true);
  const [scope, setScope] = useState(false);
  const [savedEvidence, setSavedEvidence] = useState<EvidenceResult[]>([]);
  const [savedLoaded, setSavedLoaded] = useState(false);
  const reviewed = useMemo(() => new Set(savedEvidence.map(item => item.chunkId)), [savedEvidence]);
  const pendingCitation = useRef<EvidenceResult | null>(null);
  const sourceScroll = useRef<HTMLDivElement | null>(null);
  const { options, updateOptions } = useSearchOptions('materials-evidence');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [nextCorpus, nextDocuments] = await Promise.all([api<Corpus>('/corpus'), api<{ documents: DocumentSummary[]; total: number }>('/documents?limit=100')]);
      setCorpus(nextCorpus); setDocuments(nextDocuments.documents);
      setDocumentTotal(nextDocuments.total);
      setDocumentId(current => current || nextDocuments.documents[0]?.id || null); setError(null);
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to load the corpus.'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const interval = window.setInterval(() => { void api<Corpus>('/corpus').then(next => { setCorpus(next); setDocumentTotal(next.counts.documents); }).catch(() => undefined); }, 15000);
    return () => window.clearInterval(interval);
  }, []);
  useEffect(() => {
    try { const stored = JSON.parse(localStorage.getItem('falkor-materials-evidence-tray') || '[]'); if (Array.isArray(stored)) setSavedEvidence(stored.filter(item => item && typeof item.chunkId === 'string' && typeof item.text === 'string')); } catch {}
    setSavedLoaded(true);
  }, []);
  useEffect(() => { if (savedLoaded) { try { localStorage.setItem('falkor-materials-evidence-tray', JSON.stringify(savedEvidence)); } catch {} } }, [savedEvidence, savedLoaded]);
  useEffect(() => {
    if (inspectorTab !== 'corpus') return;
    void api<Record<string, unknown>>('/graph/diagnostics').then(setDiagnostics).catch(failure => setDiagnostics({ error: failure.message }));
  }, [inspectorTab]);
  useEffect(() => {
    if (!documentId) return;
    let cancelled = false;
    setDocumentLoading(true);
    api<EvidenceDocument>(`/documents/${encodeURIComponent(documentId)}`).then(next => {
      if (cancelled) return;
      setDocument(next);
      const citation = pendingCitation.current;
      setSectionId(citation?.documentId === next.id ? citation.sectionId : next.chunks[0]?.sectionId || next.sections[0]?.id || null);
      setSelectedId(citation?.documentId === next.id ? citation.chunkId : next.chunks[0]?.id || next.id);
      pendingCitation.current = null;
    }).catch(failure => { if (!cancelled) setError(failure.message); }).finally(() => { if (!cancelled) setDocumentLoading(false); });
    return () => { cancelled = true; };
  }, [documentId]);

  useEffect(() => {
    if (!documentId) return;
    let cancelled = false;
    setGraphLoading(true);
    const params = new URLSearchParams({ documentId });
    if (sectionId) params.set('sectionId', sectionId);
    api<EvidenceGraph>(`/graph?${params}`).then(next => { if (!cancelled) setGraph(next); })
      .catch(failure => { if (!cancelled) setError(failure.message); }).finally(() => { if (!cancelled) setGraphLoading(false); });
    return () => { cancelled = true; };
  }, [documentId, sectionId]);

  useEffect(() => {
    if (!selectedId) return;
    const container = sourceScroll.current;
    const target = window.document.getElementById(`chunk-${selectedId}`);
    if (!container || !target) return;
    const offset = target.getBoundingClientRect().top - container.getBoundingClientRect().top;
    if (offset < 0 || offset + target.clientHeight > container.clientHeight) container.scrollTo({ top: container.scrollTop + offset - 12, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
  }, [selectedId, sectionId, document]);

  const chunks = useMemo(() => document?.chunks.filter(chunk => !sectionId || chunk.sectionId === sectionId) || [], [document, sectionId]);
  const navigableSections = useMemo(() => document?.sections.filter(section => document.chunks.some(chunk => chunk.sectionId === section.id)) || [], [document]);
  const sectionIndex = navigableSections.findIndex(section => section.id === sectionId);
  const currentSection = document?.sections.find(section => section.id === sectionId);
  const selectedChunk = document?.chunks.find(chunk => chunk.id === selectedId);
  const selectedNode = graph?.nodes.find(node => node.id === selectedId);
  const selectedResult = run?.results.find(result => result.chunkId === selectedId);
  const visibleDocuments = documents.filter(doc => `${doc.title} ${doc.id}`.toLowerCase().includes(filter.toLowerCase()));

  const selectNode = (node: GraphNode) => {
    if (node.documentId && node.documentId !== documentId) setDocumentId(node.documentId);
    if (node.type === 'section' && navigableSections.some(section => section.id === (node.sectionId || node.id))) setSectionId(node.sectionId || node.id);
    if (node.type === 'chunk') {
      const chunk = document?.chunks.find(item => item.id === (node.chunkId || node.id));
      if (chunk) setSectionId(chunk.sectionId);
    }
    setSelectedId(node.chunkId || node.id); setInspectorTab('record');
  };
  const selectCitation = (result: EvidenceResult) => {
    if (result.documentId !== documentId) { pendingCitation.current = result; setDocumentId(result.documentId); }
    else { setSectionId(result.sectionId); setSelectedId(result.chunkId); }
    setInspectorTab('record');
  };
  const search = async (event: React.FormEvent) => {
    event.preventDefault(); if (!query.trim()) return;
    setBusy(true); setError(null);
    try {
      const next = await api<SearchRun>('/search', { method: 'POST', body: JSON.stringify({ query: query.trim(), options: { graphExpansion: options.graphExpansion, limit: 8, ...(scope && documentId ? { documentId } : {}) } }) });
      setRun(next); setRuns(previous => [next, ...previous].slice(0, 12)); setInspectorTab('trace');
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Search failed. Please retry.'); }
    finally { setBusy(false); }
  };
  const changeSection = (offset: number) => {
    const section = navigableSections[sectionIndex + offset];
    if (section) { setSectionId(section.id); setSelectedId(document?.chunks.find(chunk => chunk.sectionId === section.id)?.id || section.id); }
  };
  const exportDossier = () => {
    if (!run && !savedEvidence.length) return;
    const payload = { exportedAt: new Date().toISOString(), collection: corpus?.collection, selectedEvidence: savedEvidence, run, notice: 'Kept source evidence for human review. Not a scientific recommendation.' };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
    const anchor = window.document.createElement('a'); anchor.href = url; anchor.download = `evidence-${run?.runId || 'selected'}.json`; anchor.click(); URL.revokeObjectURL(url);
  };
  const loadMore = async () => {
    setLoadingMore(true);
    try { const next = await api<{ documents: DocumentSummary[]; total: number }>(`/documents?limit=100&offset=${documents.length}`); setDocuments(previous => [...previous, ...next.documents.filter(item => !previous.some(doc => doc.id === item.id))]); setDocumentTotal(next.total); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not load more documents.'); }
    finally { setLoadingMore(false); }
  };
  const toggleEvidence = (result: EvidenceResult) => setSavedEvidence(previous => previous.some(item => item.chunkId === result.chunkId) ? previous.filter(item => item.chunkId !== result.chunkId) : [...previous, result]);

  return <div className={`workspace ${libraryOpen ? '' : 'library-collapsed'}`}>
    <header className="workspace-header">
      <div className="brand"><img src="/cosmic-logo.png" alt="" width={29} height={29} /><strong>falkor<span>/</span></strong><span className="brand-subtitle">evidence engine</span></div>
      <div className="workspace-context"><FlaskConical size={15} /><span>Materials evidence</span><span className="context-divider">/</span><span className="muted">Use case A</span></div>
      <div className="header-actions"><span className={`connection ${corpus?.capabilities.graph ? 'connected' : ''}`}><i />{corpus ? corpus.capabilities.graph ? 'FalkorDB connected' : 'Source ledger mode' : 'Connecting…'}</span><Button size="sm" variant="outline" onClick={() => { setInspectorTab('corpus'); setLibraryOpen(true); }}><Database size={14} /><span>Inspect corpus</span></Button></div>
    </header>

    <aside className="library">
      <div className="library-heading"><span><BookOpen size={16} />Source library</span><button aria-label="Collapse source library" onClick={() => setLibraryOpen(false)}><PanelLeftClose size={15} /></button></div>
      <div className="collection"><div className="collection-icon"><FlaskConical size={18} /></div><div><strong>Materials & water</strong><span>Published scientific evidence</span></div></div>
      <div className="corpus-counts"><span><b>{number(corpus?.counts.documents)}</b> papers</span><span><b>{number(corpus?.counts.chunks)}</b> chunks</span><button onClick={() => void refresh()} disabled={loading} aria-label="Refresh corpus"><RefreshCw size={12} className={loading ? 'spinning' : ''} /></button></div>
      <label className="library-search"><Search size={14} /><input aria-label="Filter source library" placeholder="Filter loaded papers…" value={filter} onChange={event => setFilter(event.target.value)} />{filter && <button onClick={() => setFilter('')} aria-label="Clear source filter"><X size={12} /></button>}</label>
      <div className="document-list" aria-label="Documents">
        {loading ? <div className="loading-copy"><Loader2 size={16} className="spinning" />Loading source manifest…</div> : visibleDocuments.length ? visibleDocuments.map(doc => <button key={doc.id} className={`document-item ${doc.id === documentId ? 'active' : ''}`} onClick={() => setDocumentId(doc.id)}>
          <FileText size={15} /><span><strong>{doc.title}</strong><small>{doc.id} <span>·</span> {doc.year || 'Year unavailable'} <span>·</span> {doc.chunkCount} chunks</small></span>
        </button>) : <div className="loading-copy">{filter ? 'No papers match this filter.' : 'No papers have been ingested yet.'}</div>}
      </div>
      <div className="library-pagination"><span>{documents.length} of {number(documentTotal)} loaded</span>{documents.length < documentTotal && <button onClick={() => void loadMore()} disabled={loadingMore}>{loadingMore ? 'Loading…' : 'Load 100 more'}<ChevronDown size={11} /></button>}</div><div className="strategy-panel"><h2><SlidersHorizontal size={14} />Retrieval strategies</h2>
        <div className="strategy"><label htmlFor="graph-strategy">Expand related evidence<small>Follow linked evidence after retrieval</small></label><Switch id="graph-strategy" checked={options.graphExpansion} onCheckedChange={checked => updateOptions({ graphExpansion: checked })} /></div>
        <div className="strategy"><label htmlFor="lexical-strategy">BM25 retrieval<small>Lexical starting points · always on</small></label><Switch id="lexical-strategy" checked disabled /></div>
        <div className="strategy unavailable"><label htmlFor="vector-strategy">Vector + RRF<small>Embedding pipeline not connected</small></label><Switch id="vector-strategy" checked={false} disabled /></div>
        <div className="strategy-note"><CircleHelp size={12} /><span>Source and provenance graphs stay on. Toggles affect the next search.</span></div>
      </div>
      <div className="cosmic-credit"><img src="/cosmic-logo.png" alt="" width={16} height={16} /><span>Built on Cosmic Engine</span><span className="version">v0.1</span></div>
    </aside>

    <main className="workbench">
      <div className="workbench-heading"><div className="heading-group">{!libraryOpen && <button className="icon-button" onClick={() => setLibraryOpen(true)} aria-label="Open source library"><PanelLeftOpen size={17} /></button>}<h1>Evidence workspace</h1><span className="workspace-badge">Live sources</span></div><Button size="sm" variant="outline" onClick={exportDossier} disabled={!run && !savedEvidence.length}><ArrowDownToLine size={13} />Export dossier{savedEvidence.length ? ` · ${savedEvidence.length} kept` : ''}</Button></div>
      {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={() => void refresh()}>Retry</button><button onClick={() => setError(null)} aria-label="Dismiss error"><X size={14} /></button></div>}
      <div className="workbench-body">
        <ResizablePanelGroup direction="horizontal" className="workspace-panels">
          <ResizablePanel defaultSize={62} minSize={38} className="exploration-panel">
            <div className="document-context"><div><FileText size={15} /><strong title={document?.title}>{documentLoading ? 'Loading paper…' : document?.title || 'Select a source to explore'}</strong></div>{document?.sourceUrl && <a href={document.sourceUrl} target="_blank" rel="noreferrer" aria-label="Open original publication"><ExternalLink size={14} /></a>}</div>
            <ResizablePanelGroup direction="vertical">
              <ResizablePanel defaultSize={47} minSize={25}>
                <section className="graph-section" aria-label="Evidence neighborhood">
                  <div className="panel-heading"><h2><Network size={15} />Evidence neighborhood</h2><span className="quiet-tag">{graph?.source === 'falkordb' ? 'FalkorDB' : graph?.source ? 'Source ledger' : 'Loading'}</span></div>
                  <GraphCanvas graph={graph} selectedId={selectedId} onSelect={selectNode} loading={graphLoading} />
                </section>
              </ResizablePanel>
              <ResizableHandle withHandle />
              <ResizablePanel defaultSize={53} minSize={25}>
                <section className="source-section" aria-label="Source passages">
                  <div className="panel-heading"><h2><Layers3 size={15} />Source passages</h2><span className="muted tiny">{chunks.length} chunks in view</span></div>
                  <div className="section-navigation"><button disabled={sectionIndex <= 0} onClick={() => changeSection(-1)} aria-label="Previous section"><ChevronLeft size={15} /></button><label><span className="sr-only">Focused section</span><select value={sectionId || ''} onChange={event => { setSectionId(event.target.value); setSelectedId(document?.chunks.find(chunk => chunk.sectionId === event.target.value)?.id || event.target.value); }} disabled={!navigableSections.length}>{navigableSections.map((section, index) => <option key={section.id} value={section.id}>{index + 1}. {section.title}</option>)}</select><ChevronDown size={12} /></label><span>{sectionIndex >= 0 ? sectionIndex + 1 : 0} / {navigableSections.length}</span><button disabled={!document || sectionIndex >= navigableSections.length - 1} onClick={() => changeSection(1)} aria-label="Next section"><ChevronRight size={15} /></button></div>
                  <div className="source-scroll" ref={sourceScroll}>{documentLoading ? <div className="empty-state"><Loader2 className="spinning" /><span>Loading source passages…</span></div> : chunks.length ? <><div className="source-paper-heading"><span>{document?.id} · structured full text</span><h3>{currentSection?.title || document?.title}</h3></div>{chunks.map(chunk => <SourceChunk key={chunk.id} chunk={chunk} selected={chunk.id === selectedId} onSelect={() => { setSelectedId(chunk.id); setInspectorTab('record'); }} />)}<p className="source-footnote">Navigation includes JATS sections containing chunks, not PDF pages. Offsets are Unicode code points in the normalized article text.</p></> : <div className="empty-state"><FileText size={24} /><strong>No passages in this section</strong><span>Choose another section or ingest a source.</span></div>}</div>
                </section>
              </ResizablePanel>
            </ResizablePanelGroup>
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize={38} minSize={26} className="review-panel">
            <section className="review-search"><div className="panel-heading"><h2><Search size={15} />Find evidence</h2><span className="quiet-tag">Corpus search</span></div><form onSubmit={search}><label htmlFor="evidence-query" className="sr-only">Evidence query</label><textarea id="evidence-query" rows={2} value={query} onChange={event => setQuery(event.target.value)} placeholder="What evidence are you looking for?" onKeyDown={event => { if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) void search(event); }} /><div className="search-form-footer"><label className="scope-toggle"><input type="checkbox" checked={scope} onChange={event => setScope(event.target.checked)} />This paper only</label><Button size="sm" type="submit" disabled={busy || !query.trim() || !corpus}>{busy ? <Loader2 size={13} className="spinning" /> : <ArrowRight size={14} />}Find evidence</Button></div></form></section>
            <div className="review-results">{savedEvidence.length > 0 && <details className="kept-tray"><summary>{savedEvidence.length} kept passages · saved in this browser</summary><div className="kept-tray-list">{savedEvidence.map((item, index) => <div key={item.chunkId}><CitationButton citation={item} index={index + 1} onCitationClick={() => selectCitation(item)} /><button aria-label={`Remove kept passage ${index + 1}`} onClick={() => toggleEvidence(item)}><X size={12} /></button></div>)}</div></details>}<div className="results-heading"><h2>{run ? 'Evidence dossier' : 'Start with the evidence'}</h2>{run && <span>{run.results.length} passages · {ms(run.timings.totalMs)}</span>}</div>
              {!run ? <div className="dossier-empty"><div className="dossier-icon"><BookOpen size={24} /></div><h3>From a claim to its source.</h3><p>Search the corpus, inspect the surrounding evidence, and collect passages worth reviewing.</p><button onClick={() => setQuery('adsorption capacity regeneration wastewater')}>Try adsorption & regeneration<ArrowRight size={13} /></button><div className="honest-note">This slice retrieves real passages. Scientific claim extraction and generated answers are not connected.</div></div> : !run.results.length ? <div className="empty-state"><Search size={23} /><strong>No matching evidence</strong><span>Try fewer terms, another material, or search the full corpus.</span></div> : <><div className="evidence-notice"><span className="status-dot" />Retrieved source evidence · review before drawing conclusions</div>{run.results.map((result, index) => <article className={`evidence-result ${result.chunkId === selectedId ? 'focused' : ''}`} key={`${result.chunkId}-${index}`}><div className="result-meta"><span className="result-number">{String(index + 1).padStart(2, '0')}</span><span>{result.retrieval === 'graph' ? 'Relationship expansion' : 'Lexical match'}</span><span className="result-score" title="Raw retrieval score, not confidence">{result.scoreType === 'graph_path' ? 'Linked evidence' : `${result.scoreType} ${result.score.toFixed(3)}`}</span></div><h3>{result.documentTitle}</h3><p>{result.text.slice(0, 390)}{result.text.length > 390 ? '…' : ''}</p><div className="result-bottom"><CitationButton citation={result} index={index + 1} onCitationClick={() => selectCitation(result)} selected={result.chunkId === selectedId} /><button className={`review-button ${reviewed.has(result.chunkId) ? 'reviewed' : ''}`} aria-pressed={reviewed.has(result.chunkId)} onClick={() => toggleEvidence(result)}><Check size={12} />{reviewed.has(result.chunkId) ? 'Kept' : 'Keep evidence'}</button></div></article>)}{run.warnings?.map((warning, index) => <p className="warning-note" key={index}>{warning}</p>)}</>}
            </div>
            <section className="inspector"><div className="inspector-heading"><h2><Activity size={14} />Inspector</h2><span className="tiny muted">Everything traceable</span></div><div className="inspector-tabs" role="tablist" aria-label="Inspector views">{(['trace', 'record', 'corpus'] as const).map(tab => <button role="tab" aria-selected={inspectorTab === tab} aria-controls={`inspector-${tab}`} id={`tab-${tab}`} key={tab} onClick={() => setInspectorTab(tab)}>{tab === 'trace' ? 'Execution' : tab === 'record' ? 'Selected record' : 'Corpus & DB'}</button>)}</div><div className="inspector-content" role="tabpanel" id={`inspector-${inspectorTab}`} aria-labelledby={`tab-${inspectorTab}`}>
              {inspectorTab === 'trace' ? run ? <><div className="run-summary"><span>Run <code title={run.runId}>{run.runId.slice(0, 8)}</code></span><b>{ms(run.timings.totalMs)}</b></div><div className="trace-stages">{run.trace.map(stage => <div className="trace-stage" key={stage.id}><span className={`trace-dot ${stage.status === 'skipped' ? 'skipped' : ''}`} /><span className="stage-name">{stage.stage}<small>{stage.outputCount !== undefined ? `${stage.outputCount} outputs` : stage.status}</small></span><span className="timing-bar"><i style={{ width: `${Math.max(2, Math.min(100, stage.durationMs / Math.max(run.timings.totalMs, .01) * 100))}%` }} /></span><code>{ms(stage.durationMs)}</code></div>)}</div><details><summary>Inspect full execution record</summary><pre>{JSON.stringify(run, null, 2)}</pre></details>{runs.length > 1 && <div className="run-history"><label htmlFor="previous-run">Previous runs</label><select id="previous-run" value={run.runId} onChange={event => setRun(runs.find(item => item.runId === event.target.value) || run)}>{runs.map(item => <option key={item.runId} value={item.runId}>{item.query.slice(0, 28)} · {ms(item.timings.totalMs)} · graph {item.options.graphExpansion ? 'on' : 'off'}</option>)}</select></div>}</> : <div className="inspector-empty"><Settings2 size={18} /><span>Run a search to see each retrieval stage, score, and measured duration.</span></div> : inspectorTab === 'record' ? selectedId ? <><dl className="record-fields"><div><dt>Record type</dt><dd>{selectedChunk ? 'Source chunk' : selectedNode?.type || 'Source record'}</dd></div><div><dt>Stable ID</dt><dd><code>{selectedId}</code></dd></div>{selectedChunk && <><div><dt>Source offsets</dt><dd><code>{selectedChunk.startOffset}–{selectedChunk.endOffset}</code> Unicode code points</dd></div><div><dt>Revision</dt><dd><code>{document?.revisionId}</code></dd></div><div><dt>Section</dt><dd>{selectedChunk.sectionTitle}</dd></div></>}</dl>{selectedResult && <div className="retrieval-reason"><strong>Why this passage?</strong>{selectedResult.reasons.map((reason, index) => <p key={index}>{reason}</p>)}<span>{selectedResult.scoreType === 'graph_path' ? 'Graph relationship · no similarity score' : `${selectedResult.scoreType} score ${selectedResult.score.toFixed(4)} · rank ${selectedResult.rank}`}</span></div>}<details><summary>Inspect record & relationships</summary><pre>{JSON.stringify({ record: selectedChunk || selectedNode, edges: graph?.edges.filter(edge => edge.source === selectedId || edge.target === selectedId), retrieval: selectedResult }, null, 2)}</pre></details></> : <div className="inspector-empty">Select any graph node, source chunk, or citation.</div> : <><dl className="record-fields"><div><dt>Graph provider</dt><dd>{corpus?.capabilities.graph ? 'FalkorDB' : 'Source ledger fallback'}</dd></div><div><dt>Stored documents</dt><dd>{number(corpus?.counts.documents)}</dd></div><div><dt>Sections / chunks</dt><dd>{number(corpus?.counts.sections)} / {number(corpus?.counts.chunks)}</dd></div><div><dt>Entity records</dt><dd>{number(corpus?.counts.entities)}</dd></div><div><dt>Graph coverage</dt><dd>{number(corpus?.graph.indexedDocuments as number)} papers / {number(corpus?.graph.indexedChunks as number)} chunks</dd></div><div><dt>Vector / generation</dt><dd>Not connected</dd></div></dl><div className="db-plan"><strong>FalkorDB query plan</strong><p>{diagnostics ? `${number(diagnostics.nodes as number)} nodes · ${number(diagnostics.edges as number)} edges` : 'Loading database diagnostics…'}</p>{Array.isArray(diagnostics?.explain) && <pre>{diagnostics.explain.join("\n")}</pre>}</div><details><summary>Acquisition, capabilities & DB status</summary><pre>{JSON.stringify({ corpus, diagnostics }, null, 2)}</pre></details></>}
            </div></section>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
      <footer className="workspace-status"><span><i className="status-dot" />{loading ? 'Loading corpus' : `${number(corpus?.counts.documents)} papers indexed · ${number(corpus?.counts.sections)} sections · ${number(corpus?.counts.chunks)} chunks`}</span><span>Exact source offsets<span className="status-separator">·</span>No generated scientific claims</span></footer>
    </main>
  </div>;
}

function SourceChunk({ chunk, selected, onSelect }: { chunk: Chunk; selected: boolean; onSelect: () => void }) {
  const color = chunkColor(chunk.id);
  return <button style={{ '--chunk-tint': color.tint, '--chunk-ink': color.ink } as CSSProperties} className={`source-chunk ${selected ? 'selected' : ''}`} id={`chunk-${chunk.id}`} onClick={onSelect} aria-pressed={selected}>
    <span className="chunk-meta"><span><i />Chunk {chunk.ordinal}</span><code>{chunk.startOffset}–{chunk.endOffset}</code>{selected && <span className="selected-label"><Network size={11} />In focus</span>}</span><span className="chunk-text">{chunk.text}</span>
  </button>;
}
