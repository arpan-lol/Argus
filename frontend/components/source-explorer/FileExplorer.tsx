'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ChevronLeft, ChevronRight, ExternalLink, FileText, Layers3, Loader2, Upload, X } from 'lucide-react';
import { api, chunkColor, type DocumentSummary, type EvidenceDocument, type EvidenceResult } from '@/lib/evidence-types';
import FileViewer from '@/components/viewers/FileViewer';
import './FileExplorer.css';

let consumedUploadRequest = 0;

interface FileExplorerProps {
  focusDocumentId?: string;
  focusChunkId?: string;
  documentId?: string;
  chunkId?: string;
  uploadRequest?: number;
  onDocumentFocus?: (documentId: string, chunkId?: string) => void;
  onSourceSelect?: (source: EvidenceResult) => void;
}

export function FileExplorer({ focusDocumentId, focusChunkId, documentId, chunkId, uploadRequest = 0, onDocumentFocus }: FileExplorerProps) {
  const selectedDocumentId = focusDocumentId ?? documentId;
  const selectedChunkId = focusChunkId ?? chunkId;
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [articleId, setArticleId] = useState<string | undefined>(selectedDocumentId);
  const [article, setArticle] = useState<EvidenceDocument | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [mode, setMode] = useState<'reader' | 'chunks'>('reader');
  const [preview, setPreview] = useState<{ name: string; url: string } | null>(null);
  const [page, setPage] = useState(1);
  const fileInput = useRef<HTMLInputElement>(null);
  const chunkRefs = useRef<Map<string, HTMLElement>>(new Map());
  const limit = 24;
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
    let active = true;
    api<{ documents: DocumentSummary[]; total: number }>(`/documents?offset=${offset}&limit=${limit}`)
      .then(result => { if (active) { setDocuments(result.documents); setTotal(result.total); } })
      .catch(reason => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [offset]);

  useEffect(() => {
    if (selectedDocumentId) { setArticleId(selectedDocumentId); setPreview(null); }
    if (selectedChunkId) setMode('chunks');
  }, [selectedDocumentId, selectedChunkId]);

  useEffect(() => {
    if (!articleId) { setArticle(null); return; }
    let active = true;
    setLoading(true);
    setError('');
    api<EvidenceDocument>(`/documents/${encodeURIComponent(articleId)}`)
      .then(result => { if (active) setArticle(result); })
      .catch(reason => { if (active) setError(reason.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [articleId]);

  useEffect(() => {
    if (selectedChunkId && article && mode === 'chunks') chunkRefs.current.get(selectedChunkId)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [article, selectedChunkId, mode]);

  useEffect(() => {
    if (uploadRequest > consumedUploadRequest) { consumedUploadRequest = uploadRequest; fileInput.current?.click(); }
  }, [uploadRequest]);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url); }, [preview]);

  function openArticle(id: string) {
    setPreview(null);
    setArticleId(id);
    setMode('reader');
    onDocumentFocus?.(id);
  }

  function openLocalFile(file?: File) {
    if (!file) return;
    setError('');
    setPage(1);
    setPreview({ name: file.name, url: URL.createObjectURL(file) });
  }

  return <div className="ce-file-explorer">
    <input ref={fileInput} type="file" hidden accept=".pdf,.docx,.doc,.png,.jpg,.jpeg,.gif,.webp,.csv,.xlsx,.xls,.ppt,.pptx,.txt,.md,.json,.xml,.html,.log" onChange={event => { openLocalFile(event.target.files?.[0]); event.target.value = ''; }} />
    <div className="ce-file-toolbar">
      {(articleId || preview) ? <button className="ce-file-back" onClick={() => { setArticleId(undefined); setPreview(null); setError(''); }}><ArrowLeft size={15} /> All files</button> : <span className="ce-file-count">{total.toLocaleString()} files</span>}
      <button className="ce-file-preview-button" onClick={() => fileInput.current?.click()}><Upload size={14} /> Preview file</button>
    </div>
    {error && <div className="ce-file-error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError('')}><X size={14} /></button></div>}
    {preview ? <div className="ce-file-preview">
      <div className="ce-file-local-heading"><FileText size={16} /><strong title={preview.name}>{preview.name}</strong><span>Preview only</span></div>
      <p className="ce-file-local-note">This file stays in your browser. Ingestion is not connected yet.</p>
      <div className="ce-file-preview-content"><FileViewer fileUrl={preview.url} filename={preview.name} fileType="" currentPage={page} onPageChange={setPage} /></div>
    </div> : articleId ? <>
      {loading ? <div className="ce-file-empty"><Loader2 className="animate-spin" size={22} /> Opening source…</div> : article ? <>
        <div className="ce-file-document-heading"><span>{article.journal || 'Research article'}{article.year ? ` · ${article.year}` : ''}</span><h2>{article.title}</h2><div className="ce-file-document-actions"><div className="ce-file-mode" role="group" aria-label="Document view"><button aria-pressed={mode === 'reader'} onClick={() => setMode('reader')}><FileText size={14} /> Read</button><button aria-pressed={mode === 'chunks'} onClick={() => setMode('chunks')}><Layers3 size={14} /> Chunks</button></div>{article.sourceUrl && <a href={article.sourceUrl} target="_blank" rel="noreferrer" aria-label="Open original source"><ExternalLink size={15} /></a>}</div></div>
        <div className="ce-file-reading-area">
          {mode === 'reader' ? <article className="ce-file-paper"><h1>{article.title}</h1>{readerBlocks.map(block => <section key={block.offset}>{block.titles.map(title => <h2 key={title}>{title}</h2>)}<p>{block.text}</p></section>)}</article> : <div className="ce-file-chunks">{article.chunks.map((chunk, index) => { const color = chunkColor(chunk.id); return <article key={chunk.id} ref={element => { if (element) chunkRefs.current.set(chunk.id, element); else chunkRefs.current.delete(chunk.id); }} className={`ce-file-chunk ${selectedChunkId === chunk.id ? 'is-focused' : ''}`} style={{ '--chunk-ink': color.ink, '--chunk-tint': color.tint } as React.CSSProperties}><div><span>Chunk {index + 1}</span><small>{chunk.sectionTitle}</small></div><p>{chunk.text}</p><button onClick={() => onDocumentFocus?.(article.id, chunk.id)}>Focus in graph</button></article>; })}</div>}
        </div>
      </> : !error && <div className="ce-file-empty">No document found.</div>}
    </> : <>
      <div className="ce-file-list-heading"><h2>Your sources</h2><p>Open a paper to read it or explore its chunks.</p></div>
      <div className="ce-file-list">{documents.map(document => <button key={document.id} className="ce-file-row" onClick={() => openArticle(document.id)}><span className="ce-file-row-icon"><FileText size={19} /></span><span><strong>{document.title}</strong><small>{document.year || 'Research article'} · {document.chunkCount} chunks</small></span><ChevronRight size={15} /></button>)}{!documents.length && !error && <div className="ce-file-empty"><Loader2 className="animate-spin" size={20} /> Loading files…</div>}</div>
      <div className="ce-file-pagination"><button aria-label="Previous files" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}><ChevronLeft size={16} /></button><span>{Math.min(offset + 1, total)}–{Math.min(offset + limit, total)} of {total.toLocaleString()}</span><button aria-label="Next files" disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}><ChevronRight size={16} /></button></div>
    </>}
  </div>;
}

export default FileExplorer;
