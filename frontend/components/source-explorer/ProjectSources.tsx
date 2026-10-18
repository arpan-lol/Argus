'use client';

import { useEffect, useRef, useState } from 'react';
import { Loader2, Plus, Upload, X } from 'lucide-react';
import { projectApi, projectRoot, type Project } from '@/lib/projects';
import { fileIdentity, formatBytes, mergeFiles } from '@/lib/file-selection';
import { takeProjectUpload } from '@/lib/project-upload-handoff';
import { FileExplorer } from './FileExplorer';
import type { ChatSource } from '@/lib/chat';
import type { IngestionJob } from '@/lib/ingestion-types';
import './ProjectSources.css';
import { CategorySelection } from '../workspace/CategorySelection';

interface Props {
  project: Project;
  uploadRequest: number;
  refreshVersion: number;
  focus?: ChatSource | null;
  documentId?: string;
  chunkId?: string;
  onProject: (project: Project) => void;
  onUploaded: () => void;
  onFocus: (documentId: string, chunkId?: string) => void;
  onOpenReader?: () => void;
  onBackToGraph: () => void;
  onJobsChange?: (jobs: IngestionJob[]) => void;
}

export function ProjectSources({ project, uploadRequest, refreshVersion, focus, documentId, chunkId, onProject, onUploaded, onFocus, onOpenReader, onBackToGraph, onJobsChange }: Props) {
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [queuedFromCreation, setQueuedFromCreation] = useState<File[] | null>(null);
  const [description, setDescription] = useState(project.description);
  const [categories, setCategories] = useState(project.categories || ['general_documents']);
  const [busy, setBusy] = useState(false);
  const [transfer, setTransfer] = useState<{ loaded: number; total: number }>();
  const [error, setError] = useState('');
  const [report, setReport] = useState<{ queued: number; skipped: { filename: string; reason: string }[] }>();
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const handledRequest = useRef(0);
  const uploadActive = useRef(false);

  function selectFiles(event: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.currentTarget.files || []);
    event.currentTarget.value = '';
    if (selected.length) setFiles(previous => mergeFiles(previous, selected));
  }

  function chooseFiles(target: React.RefObject<HTMLInputElement | null>) {
    if (!target.current) return;
    target.current.value = '';
    target.current.click();
  }

  useEffect(() => {
    if (uploadRequest !== handledRequest.current) { handledRequest.current = uploadRequest; setOpen(true); }
  }, [uploadRequest]);
  useEffect(() => {
    if (open && !dialog.current?.open) dialog.current?.showModal();
    if (!open) dialog.current?.close();
  }, [open]);
  useEffect(() => { folderInput.current?.setAttribute('webkitdirectory', ''); }, []);
  useEffect(() => {
    const selected = takeProjectUpload(project.id);
    if (!selected?.length) return;
    setFiles(selected);
    setOpen(true);
    if (project.description.trim()) setQueuedFromCreation(selected);
  }, [project.id]);
  useEffect(() => {
    if (!queuedFromCreation || !project.description.trim()) return;
    const frame = window.requestAnimationFrame(() => {
      setQueuedFromCreation(null);
      void upload(queuedFromCreation, project.description);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [queuedFromCreation, project.description]);

  async function upload(selectedFiles = files, selectedDescription = description) {
    if (!selectedFiles.length || !categories.length || uploadActive.current || !selectedDescription.trim()) return;
    uploadActive.current = true;
    setBusy(true);
    setError('');
    try {
      if (!project.description || !project.configurationLocked) {
        const saved = await projectApi<Project>(project.id, '/description', { method: 'PUT', body: JSON.stringify({ description: selectedDescription.trim(), categories }) });
        onProject(saved);
      }
      const result = await uploadWithProgress(selectedFiles);
      setReport({ queued: result.jobs?.length || 0, skipped: result.skippedFiles || [] });
      onProject({ ...project, description: selectedDescription.trim(), categories, configurationLocked: true });
      setFiles([]);
      setTransfer(undefined);
      setOpen(false);
      onUploaded();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not upload your files. They are still selected; try again.');
    } finally { uploadActive.current = false; setBusy(false); setTransfer(undefined); }
  }

  function uploadWithProgress(selectedFiles: File[]) {
    const body = new FormData();
    selectedFiles.forEach(file => body.append('files', file, file.webkitRelativePath || file.name));
    return new Promise<{ jobs?: unknown[]; skippedFiles?: { filename: string; reason: string }[] }>((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open('POST', `/api${projectRoot(project.id)}/uploads`);
      request.responseType = 'json';
      request.upload.onprogress = event => setTransfer({ loaded: event.loaded, total: event.lengthComputable ? event.total : 0 });
      request.onerror = () => reject(new Error('Network interrupted while sending your files. Your selected files are still here; try again.'));
      request.onabort = () => reject(new Error('Upload was canceled. Your selected files are still here; try again.'));
      request.onload = () => {
        const payload = request.response && typeof request.response === 'object' ? request.response as { error?: unknown; jobs?: unknown[]; skippedFiles?: { filename: string; reason: string }[] } : {};
        if (request.status < 200 || request.status >= 300) {
          reject(new Error(typeof payload.error === 'string' ? payload.error : `Upload failed (${request.status}). Your selected files are still here; try again.`));
          return;
        }
        setTransfer(undefined);
        resolve(payload);
      };
      request.send(body);
    });
  }

  const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
  return <>
    {report && <div className="argus-source-report" role="status"><div><span>{report.queued.toLocaleString()} files queued{report.skipped.length ? ` · ${report.skipped.length.toLocaleString()} skipped` : ''}</span><button type="button" onClick={() => setReport(undefined)} aria-label="Dismiss upload report"><X size={14} /></button></div>{report.skipped.length > 0 && <details><summary>Review skipped files</summary><ul>{report.skipped.map((file, index) => <li key={`${file.filename}-${index}`}><span>{file.filename}</span><small>{file.reason}</small></li>)}</ul></details>}</div>}
    <FileExplorer projectId={project.id} focusDocumentId={focus?.documentId || documentId} focusChunkId={focus?.chunkId || chunkId} focusJobId={focus?.jobId} focusCollection="pipeline" refreshToken={refreshVersion} onUpload={() => setOpen(true)} onDocumentFocus={onFocus} onOpenReader={onOpenReader} onBackToGraph={onBackToGraph} onJobsChange={onJobsChange} />
    <dialog ref={dialog} className="argus-source-onboarding" onCancel={event => { if (busy) event.preventDefault(); else setOpen(false); }} aria-labelledby="source-onboarding-title">
      <div className="argus-source-onboarding-heading"><h2 id="source-onboarding-title">{project.description ? 'Add data sources' : files.length ? 'What is the data in this workspace about?' : 'Start by adding data sources.'}</h2><button disabled={busy} onClick={() => setOpen(false)} aria-label="Close source upload"><X size={18} /></button></div>
      <input ref={input} hidden type="file" multiple disabled={busy} onChange={selectFiles} />
      <input ref={folderInput} hidden type="file" multiple disabled={busy} onChange={selectFiles} />
      {!project.configurationLocked && <CategorySelection value={categories} onChange={setCategories} disabled={busy} />}
      {!files.length ? <div className="argus-source-pickers"><button type="button" className="argus-source-add-large" disabled={busy} onClick={() => chooseFiles(input)}><Plus size={30} strokeWidth={1.4} /><strong>Choose files</strong><span>Add individual documents</span></button><button type="button" className="argus-source-add-large" disabled={busy} onClick={() => chooseFiles(folderInput)}><Upload size={29} strokeWidth={1.4} /><strong>Choose a folder</strong><span>Select a corpus folder from your device</span></button></div> : <>
        <div className="argus-source-selection-summary"><strong>{files.length.toLocaleString()} {files.length === 1 ? 'file' : 'files'} selected</strong><span>{formatBytes(totalBytes)} total</span></div>
        <ul className="argus-source-pending">{files.slice(0, 60).map((file, index) => <li key={fileIdentity(file)}><span title={file.webkitRelativePath || file.name}>{file.webkitRelativePath || file.name}</span><small>{formatBytes(file.size)}</small><button disabled={busy} onClick={() => setFiles(previous => previous.filter((_, item) => item !== index))} aria-label={`Remove ${file.name}`}><X size={14} /></button></li>)}</ul>
        {files.length > 60 && <p className="argus-source-local-note">Showing the first 60 names. All {files.length.toLocaleString()} selected files will be sent.</p>}
        {!project.description ? <><label htmlFor="workspace-data-description">Describe the data and what you want to find</label><textarea id="workspace-data-description" value={description} onChange={event => setDescription(event.target.value)} disabled={busy} maxLength={12000} rows={4} placeholder="What do these documents cover? Which entities and relationships matter to your work?" aria-describedby="workspace-description-hint" /><p id="workspace-description-hint" className="argus-source-description-hint">Saved for this entire workspace and any files you add later.</p></> : <p className="argus-source-saved-description">Uses this workspace’s saved description: {project.description}</p>}
        {!project.description && <p className="argus-source-local-note">These files are still on your device. Nothing is sent until you start ingestion.</p>}
        <div className="argus-source-upload-actions"><button type="button" className="argus-source-more" disabled={busy} onClick={() => chooseFiles(input)}><Plus size={15} />Add files</button><button type="button" className="argus-source-more" disabled={busy} onClick={() => chooseFiles(folderInput)}><Plus size={15} />Add folder</button><button type="button" className="argus-source-upload" disabled={busy || !description.trim() || !categories.length} onClick={() => void upload()}>{busy ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}{busy ? 'Starting ingestion…' : 'Start ingestion'}</button></div>
        {busy && transfer && <div className="argus-source-transfer" role="status"><div><span>Sending {files.length.toLocaleString()} files</span><span>{transfer.total ? `${Math.round(transfer.loaded / transfer.total * 100)}%` : formatBytes(transfer.loaded)}</span></div><progress max={transfer.total || undefined} value={transfer.total ? transfer.loaded : undefined} /></div>}
      </>}
      {error && <p className="argus-source-upload-error" role="alert">{error}</p>}
    </dialog>
  </>;
}
