'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ChevronLeft, ChevronRight, Download, ExternalLink, FileText, Layers3, Loader2, Plus, Upload, X } from 'lucide-react';
import { api, chunkColor, type DocumentSummary, type EvidenceResult } from '@/lib/evidence-types';
// import FileViewer from '@/components/viewers/FileViewer';
import { IngestionJobs } from './IngestionJobs';
import { IngestionUpload } from './IngestionUpload';
import { normalizeSourceDocument, statusLabel, type IngestedDocument, type IngestionJob, type UploadedDocument } from '@/lib/ingestion-types';
import './FileExplorer.css';

let consumedUploadRequest = 0;

interface FileExplorerProps {
  projectId?: string;
  refreshToken?: number;
  onUpload?: () => void;
  focusDocumentId?: string;
  focusCollection?: 'pipeline' | 'legacy';
  focusJobId?: string;
  focusChunkId?: string;
  documentId?: string;
  chunkId?: string;
  uploadRequest?: number;
  onDocumentFocus?: (documentId: string, chunkId?: string) => void;
  onOpenReader?: () => void;
  onBackToGraph?: () => void;
  onJobsChange?: (jobs: IngestionJob[]) => void;
  onSourceSelect?: (source: EvidenceResult) => void;
}

export function FileExplorer({ projectId, refreshToken = 0, onUpload, focusDocumentId, focusChunkId, focusCollection = 'legacy', focusJobId, documentId, chunkId, uploadRequest = 0, onDocumentFocus, onOpenReader, onBackToGraph, onJobsChange }: FileExplorerProps) {
  const apiRoot = projectId ? `/projects/${encodeURIComponent(projectId)}` : '';
  const fileApi = useCallback(<T,>(path: string, init?: RequestInit) => api<T>(apiRoot + path, init), [apiRoot]);
  const selectedDocumentId = focusDocumentId ?? documentId;
  const selectedChunkId = focusChunkId ?? chunkId;
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [articleId, setArticleId] = useState<string | undefined>(selectedDocumentId);
  const [article, setArticle] = useState<IngestedDocument | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [originalOnly, setOriginalOnly] = useState(false);
  const [mode, setMode] = useState<'reader' | 'chunks' | 'original'>('reader');
  const [uploaded, setUploaded] = useState<UploadedDocument[]>([]);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [jobTotal, setJobTotal] = useState(0);
  const [jobOffset, setJobOffset] = useState(0);
  const [uploadedTotal, setUploadedTotal] = useState(0);
  const [uploadedOffset, setUploadedOffset] = useState(0);
  const [uploadedSelection, setUploadedSelection] = useState(!!projectId || focusCollection === 'pipeline');
  const [pinnedJobId, setPinnedJobId] = useState(focusJobId);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [pipelineLoading, setPipelineLoading] = useState(true);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [busyJob, setBusyJob] = useState<string>();
  const [pauseRequested, setPauseRequested] = useState<string>();
  const [page, setPage] = useState(1);
  const chunkRefs = useRef<Map<string, HTMLElement>>(new Map());
  const limit = 24;
  useEffect(() => { onJobsChange?.(jobs); }, [jobs, onJobsChange]);
  const selectedJobVersion = uploadedSelection ? jobs.filter(job => job.documentId === articleId).map(job => `${job.status}:${job.chunkCount || 0}`).join('|') : '';
  const readerBlocks = useMemo(() => {
    if (!article) return [];
    const text = Array.from(article.text);
    const headings = new Map<number, string[]>();
    for (const section of article.sections) {
      if (section.startOffset < 0 || section.startOffset >= text.length) continue;
      const titles = headings.get(section.startOffset) || [];
      if (!titles.includes(section.title)) titles.push(section.title);
      headings.set(section.startOffset, titles);
    }
    const offsets = [...new Set([0, ...headings.keys(), text.length])].sort((a, b) => a - b);
    return offsets.slice(0, -1).map((offset, index) => ({ offset, titles: headings.get(offset) || [], text: text.slice(offset, offsets[index + 1]).join('') }));
  }, [article]);

  useEffect(() => {
    if (projectId) { setCatalogLoading(false); return; }
    let active = true;
    api<{ documents: DocumentSummary[]; total: number }>(`/documents?offset=${offset}&limit=${limit}`)
      .then(result => { if (active) { setDocuments(result.documents); setTotal(result.total); } })
      .catch(reason => { if (active) setError(reason.message); })
      .finally(() => { if (active) setCatalogLoading(false); });
    return () => { active = false; };
  }, [offset, projectId]);

  /* File reading is temporarily disabled.
  useEffect(() => {
    if (selectedDocumentId) { setArticleId(selectedDocumentId); setUploadedSelection(focusCollection === 'pipeline'); setPinnedJobId(focusJobId); }
    setMode(selectedChunkId ? 'chunks' : 'reader');
  }, [selectedDocumentId, selectedChunkId, focusCollection, focusJobId]);

  useEffect(() => {
    if (!articleId) { setArticle(null); return; }
    let active = true;
    setLoading(true);
    setArticle(null);
    setError('');
    setOriginalOnly(false);
    fileApi<unknown>(pinnedJobId ? `/ingestion/jobs/${encodeURIComponent(pinnedJobId)}/document` : `${uploadedSelection ? '/ingestion' : ''}/documents/${encodeURIComponent(articleId)}`)
      .then(normalizeSourceDocument)
      .then(result => { if (active) setArticle(result); })
      .catch(reason => { if (active) { if (pinnedJobId) setOriginalOnly(true); else setError(reason.message); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [articleId, uploadedSelection, selectedJobVersion, pinnedJobId, fileApi]);

  useEffect(() => {
    if (selectedChunkId && article && mode === 'chunks') chunkRefs.current.get(selectedChunkId)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [article, selectedChunkId, mode]);

  */

  useEffect(() => {
    if (uploadRequest > consumedUploadRequest) { consumedUploadRequest = uploadRequest; setUploadOpen(true); }
  }, [uploadRequest]);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const [jobResult, documentResult] = await Promise.all([
          fileApi<{ jobs: IngestionJob[]; total: number }>(`/ingestion/jobs?limit=50&offset=${jobOffset}${projectId ? '&latest_source=true' : ''}`),
          fileApi<{ documents: UploadedDocument[]; total: number }>(`/ingestion/documents?limit=${limit}&offset=${uploadedOffset}`),
        ]);
        if (active) { setJobs(jobResult.jobs); setJobTotal(jobResult.total); setUploaded(documentResult.documents); setUploadedTotal(documentResult.total); setPauseRequested(current => current && jobResult.jobs.some(job => job.id === current && ['paused', 'complete', 'failed', 'interrupted'].includes(job.status)) ? undefined : current); }
      } catch (reason) { if (active) setError(reason instanceof Error ? reason.message : 'File processing could not be loaded.'); }
      finally { if (active) setPipelineLoading(false); }
    };
    void refresh();
    const timer = projectId ? undefined : window.setInterval(() => { if (!window.document.hidden) void refresh(); }, 4000);
    return () => { active = false; window.clearInterval(timer); };
  }, [jobOffset, uploadedOffset, refreshVersion, refreshToken, projectId, fileApi]);

  function openArticle(id: string, isUploaded = false) {
    if (projectId || !isUploaded) onDocumentFocus?.(id);
  }

  function uploadedFile(job: IngestionJob) {
    setError('');
    setJobs(current => [job, ...current.filter(item => item.id !== job.id)]);
    setRefreshVersion(current => current + 1);
    setJobOffset(0);
    setUploadedOffset(0);
    setArticleId(undefined);
    setUploadOpen(false);
  }

  async function retryJob(id: string) {
    setBusyJob(id);
    setError('');
    try {
      const job = await fileApi<IngestionJob>(`/ingestion/jobs/${encodeURIComponent(id)}/retry`, { method: 'POST' });
      setJobs(current => current.map(item => item.id === id ? job : item));
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Retry failed. Please try again.'); }
    finally { setBusyJob(undefined); }
  }

  async function pauseJob(id: string) {
    setBusyJob(id);
    setError('');
    try {
      const job = await fileApi<IngestionJob>(`/ingestion/jobs/${encodeURIComponent(id)}/pause`, { method: 'POST' });
      setJobs(current => current.map(item => item.id === id ? job : item));
      setPauseRequested(job.status === 'paused' ? undefined : id);
    } catch (reason) { setPauseRequested(undefined); setError(reason instanceof Error ? reason.message : 'Could not pause this file.'); }
    finally { setBusyJob(undefined); }
  }

  return <div className="ce-file-explorer">
    {(articleId || !projectId) && <div className="ce-file-toolbar">
      {articleId ? <button className="ce-file-back" onClick={() => { setArticleId(undefined); setPinnedJobId(undefined); setError(''); if (projectId) onBackToGraph?.(); }}><ArrowLeft size={15} />All files</button> : <span className="ce-file-count">{projectId ? pipelineLoading ? 'Loading files…' : `${jobTotal.toLocaleString()} files` : `${total.toLocaleString()} legacy · ${uploadedTotal.toLocaleString()} processing`}</span>}
      {!projectId && <button className="ce-file-preview-button" aria-expanded={uploadOpen} onClick={() => onUpload ? onUpload() : setUploadOpen(true)}><Upload size={14} />Upload file</button>}
    </div>}
    {uploadOpen && <IngestionUpload onClose={() => setUploadOpen(false)} onUploaded={uploadedFile} />}
    {error && <div className="ce-file-error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError('')}><X size={14} /></button></div>}
    {!articleId && jobs.length > 0 && <IngestionJobs jobs={jobs} total={jobTotal} offset={jobOffset} onPage={setJobOffset} busyJob={busyJob} pauseRequested={pauseRequested} onPause={id => void pauseJob(id)} onRetry={id => void retryJob(id)} onOpen={(id, jobId) => { openArticle(id, true); setPinnedJobId(jobId); }} />}
    {/* File reader retained for re-enabling.
    {articleId ? <>
      {loading ? <div className="ce-file-empty"><Loader2 className="animate-spin" size={22} /> Opening file…</div> : originalOnly && pinnedJobId ? <div className="ce-file-original ce-file-original-pending"><FileViewer fileUrl={`/api${apiRoot}/ingestion/jobs/${encodeURIComponent(pinnedJobId)}/original`} filename={jobs.find(job => job.id === pinnedJobId)?.filename || 'Source file'} fileType="" currentPage={page} onPageChange={setPage} /></div> : article ? <>
        <div className="ce-file-document-heading"><span>{uploadedSelection ? statusLabel(article.status || 'processing') : article.journal || 'Research article'}{article.year ? ` · ${article.year}` : ''}</span><h2>{article.title}</h2><div className="ce-file-document-actions"><div className="ce-file-mode" role="group" aria-label="Document view"><button aria-pressed={mode === 'reader'} onClick={() => setMode('reader')}><FileText size={14} /> Read</button><button aria-pressed={mode === 'chunks'} onClick={() => setMode('chunks')}><Layers3 size={14} /> Chunks</button>{uploadedSelection && <button aria-pressed={mode === 'original'} onClick={() => { setMode('original'); setPage(1); }}>Original</button>}</div>{uploadedSelection ? <a href={pinnedJobId ? `/api${apiRoot}/ingestion/jobs/${encodeURIComponent(pinnedJobId)}/original` : `/api${apiRoot}/ingestion/documents/${encodeURIComponent(article.id)}/download`} download={article.filename} aria-label="Download original file"><Download size={15} /></a> : article.sourceUrl && <a href={article.sourceUrl} target="_blank" rel="noreferrer" aria-label="Open original source"><ExternalLink size={15} /></a>}</div></div>
        {article.processingWarnings?.map((warning, index) => <p key={index} className="ce-file-processing-note" role="status">{warning}</p>)}
        <div className="ce-file-reading-area">
          {mode === 'original' && uploadedSelection ? <div className="ce-file-original"><FileViewer fileUrl={pinnedJobId ? `/api${apiRoot}/ingestion/jobs/${encodeURIComponent(pinnedJobId)}/original` : `/api${apiRoot}/ingestion/documents/${encodeURIComponent(article.id)}/download`} filename={article.filename || article.title} fileType="" currentPage={page} onPageChange={setPage} /></div> : mode === 'reader' ? <article className="ce-file-paper"><h1>{article.title}</h1>{readerBlocks.map(block => <section key={block.offset}>{block.titles.map(title => <h2 key={title}>{title}</h2>)}<p>{block.text}</p></section>)}</article> : <div className="ce-file-chunks">{!article.chunks.length && <p className="ce-file-processing-note">Chunks will appear after the chunking stage completes.</p>}{article.chunks.map((chunk, index) => { const color = chunkColor(chunk.id); return <article key={chunk.id} ref={element => { if (element) chunkRefs.current.set(chunk.id, element); else chunkRefs.current.delete(chunk.id); }} className={`ce-file-chunk ${selectedChunkId === chunk.id ? 'is-focused' : ''}`} style={{ '--chunk-ink': color.ink, '--chunk-tint': color.tint } as React.CSSProperties}><div><span>Chunk {index + 1}</span><small>{chunk.sectionTitle}</small></div><p>{chunk.text}</p>{(!uploadedSelection || projectId) && <button onClick={() => onDocumentFocus?.(article.id, chunk.id)}>Focus in graph</button>}</article>; })}</div>}
        </div>
      </> : !error && <div className="ce-file-empty">No document found.</div>}
    </> : <>
    */}
    <>
      {(!projectId || !jobs.length) && <div className="ce-file-list">{!projectId && uploadedTotal > 0 && <h3 className="ce-file-collection-name">Processing pipeline</h3>}{uploaded.filter(document => !projectId || !jobs.some(job => job.documentId === document.id)).map(document => <button key={document.id} className="ce-file-row" onClick={() => openArticle(document.id, true)}><span className="ce-file-row-icon"><FileText size={19} /></span><span><strong>{document.title || document.filename}</strong><small>{statusLabel(document.status)} · {document.chunkCount} chunks</small></span><ChevronRight size={15} /></button>)}{!projectId && total > 0 && <div className="ce-file-collection-heading"><h3 className="ce-file-collection-name">Legacy corpus</h3><p>Earlier parsed files.</p></div>}{!projectId && documents.map(document => <button key={document.id} className="ce-file-row" onClick={() => openArticle(document.id)}><span className="ce-file-row-icon"><FileText size={19} /></span><span><strong>{document.title}</strong><small>{document.year || 'Research article'} · {document.chunkCount} chunks</small></span><ChevronRight size={15} /></button>)}{!projectId && !documents.length && !uploaded.length && !error && <div className="ce-file-empty">{catalogLoading || pipelineLoading ? <><Loader2 className="animate-spin" size={20} /> Loading files…</> : <p>No files have been uploaded.</p>}</div>}{projectId && !jobs.length && !uploaded.length && !error && <div className="ce-file-empty">{pipelineLoading ? <><Loader2 className="animate-spin" size={20} /> Loading files…</> : <p>No files yet. Add files to get started.</p>}</div>}</div>}
      {!projectId && <div className="ce-file-pagination"><button aria-label="Previous files" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}><ChevronLeft size={16} /></button><span>{Math.min(offset + 1, total)}–{Math.min(offset + limit, total)} of {total.toLocaleString()}</span><button aria-label="Next files" disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}><ChevronRight size={16} /></button></div>}
    </>
  </div>;
}

export default FileExplorer;
