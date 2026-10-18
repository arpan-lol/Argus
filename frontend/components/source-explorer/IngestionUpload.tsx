'use client';

import { useId, useState, type FormEvent } from 'react';
import { Loader2, Upload, X } from 'lucide-react';
import { api } from '@/lib/evidence-types';
import type { IngestionJob } from '@/lib/ingestion-types';
import './IngestionSetup.css';

interface IngestionUploadProps {
  onClose: () => void;
  onUploaded: (job: IngestionJob) => void;
}

export function IngestionUpload({ onClose, onUploaded }: IngestionUploadProps) {
  const id = useId();
  const [file, setFile] = useState<File>();
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || busy) return;
    setBusy(true);
    setError('');
    const body = new FormData();
    body.append('file', file);
    if (prompt.trim()) body.append('prompt', prompt.trim());
    try {
      const job = await api<IngestionJob>('/ingestion/jobs', { method: 'POST', body });
      onUploaded(job);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Upload failed. Your file and instructions are still here; try again.');
    } finally {
      setBusy(false);
    }
  }

  return <form className="ce-ingestion-setup" onSubmit={event => void submit(event)} aria-labelledby={`${id}-title`} aria-busy={busy}>
    <div className="ce-ingestion-setup-heading"><h3 id={`${id}-title`}>Process a source</h3><button type="button" onClick={onClose} disabled={busy} aria-label="Close file upload"><X size={16} /></button></div>
    <label htmlFor={`${id}-file`}>Source file</label>
    <input id={`${id}-file`} type="file" required disabled={busy} onChange={event => setFile(event.target.files?.[0])} />
    <label htmlFor={`${id}-prompt`}>What should Argus look for? <span>Optional</span></label>
    <textarea id={`${id}-prompt`} value={prompt} onChange={event => setPrompt(event.target.value)} maxLength={12000} rows={3} disabled={busy} placeholder="Describe the things and connections relevant to your task." aria-describedby={`${id}-help`} />
    <p id={`${id}-help`}>Argus reads a sample and chooses extraction settings automatically. Leave this blank to extract the things and connections stated in the source.</p>
    {error && <p className="ce-ingestion-setup-error" role="alert">{error}</p>}
    <div className="ce-ingestion-setup-actions"><span>{busy ? 'Uploading source…' : 'Processing starts after upload.'}</span><button className="ce-ingestion-submit" type="submit" disabled={!file || busy}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}{busy ? 'Uploading…' : 'Process file'}</button></div>
    <p className="ce-ingestion-formats">Supported: XML/JATS, TXT, Markdown, HTML, text-based PDF, DOCX, CSV, TSV, XLSX, JSON, and gzip-compressed XML. Scanned PDFs need OCR.</p>
  </form>;
}
