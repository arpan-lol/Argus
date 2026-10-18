'use client';

import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, FolderUp, Loader2, Plus, Upload, X } from 'lucide-react';
import { api } from '@/lib/evidence-types';
import { fileIdentity, formatBytes, mergeFiles } from '@/lib/file-selection';
import { stageProjectUpload } from '@/lib/project-upload-handoff';
import type { Project } from '@/lib/projects';

export function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    dialog.current?.showModal();
    folderInput.current?.setAttribute('webkitdirectory', '');
    nameInput.current?.focus();
    return () => { if (dialog.current?.open) dialog.current.close(); };
  }, []);

  function select(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.currentTarget.files || []);
    event.currentTarget.value = '';
    if (selected.length) setFiles(current => mergeFiles(current, selected));
  }

  function choose(input: React.RefObject<HTMLInputElement | null>) {
    if (!input.current) return;
    input.current.value = '';
    input.current.click();
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    setError('');
    try {
      const project = await api<Project>('/projects', { method: 'POST', body: JSON.stringify({ name: name.trim(), description: description.trim() }) });
      stageProjectUpload(project.id, files);
      router.push(`/dashboard?project=${encodeURIComponent(project.id)}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not create this project. Try again.');
      setBusy(false);
    }
  }

  const totalBytes = files.reduce((sum, file) => sum + file.size, 0);

  return <dialog ref={dialog} className="argus-project-modal" aria-labelledby="project-modal-title" aria-describedby="project-modal-intro" onCancel={event => { if (busy) event.preventDefault(); else onClose(); }}>
    <form onSubmit={event => void create(event)}>
      <div className="argus-project-modal-top"><button type="button" className="argus-project-modal-close" disabled={busy} onClick={onClose} aria-label="Close new project"><X size={18} /></button></div>
      <header className="argus-project-modal-heading"><h2 id="project-modal-title">Create a project</h2><p id="project-modal-intro">Bring your files together in one workspace</p></header>

      <div className="argus-project-modal-field"><label htmlFor="new-project-name">Project name</label><input id="new-project-name" ref={nameInput} value={name} onChange={event => setName(event.target.value)} maxLength={120} disabled={busy} required placeholder="e.g. Materials research" /></div>

      <div className="argus-project-modal-field"><label htmlFor="new-project-description">What is this project about? <span>Optional</span></label><p id="new-project-description-hint">Describe the nature of your data to help the agent ingest it better; this applies to the whole workspace</p><textarea id="new-project-description" value={description} onChange={event => setDescription(event.target.value)} aria-describedby="new-project-description-hint" maxLength={12000} rows={3} disabled={busy} placeholder="What do these sources cover? Which connections matter to you?" /></div>

      <section className="argus-project-modal-files" aria-labelledby="new-project-files-title"><div className="argus-project-modal-section-heading"><h3 id="new-project-files-title">Files <span>Optional</span></h3>{files.length > 0 && <span>{files.length.toLocaleString()} selected · {formatBytes(totalBytes)}</span>}</div>
        <input ref={fileInput} hidden type="file" multiple onChange={select} disabled={busy} />
        <input ref={folderInput} hidden type="file" multiple onChange={select} disabled={busy} />
        <div className="argus-project-modal-pickers"><button type="button" disabled={busy} onClick={() => choose(fileInput)}><Plus size={19} /><span><strong>Choose files</strong></span></button><button type="button" disabled={busy} onClick={() => choose(folderInput)}><Upload size={19} /><span><strong>Choose a folder</strong></span></button></div>
        <p className="argus-project-modal-file-types">Supported: XML/JATS, TXT, Markdown, HTML, text-based PDF, DOCX, CSV, TSV, XLSX, JSON, and gzip-compressed XML. Scanned PDFs need OCR.</p>
        {files.length > 0 && <><ul className="argus-project-modal-file-list">{files.slice(0, 60).map((file, index) => <li key={fileIdentity(file)}><span title={file.webkitRelativePath || file.name}>{file.webkitRelativePath || file.name}</span><small>{formatBytes(file.size)}</small><button type="button" disabled={busy} onClick={() => setFiles(current => current.filter((_, position) => position !== index))} aria-label={`Remove ${file.name}`}><X size={14} /></button></li>)}</ul>{files.length > 60 && <p className="argus-project-modal-file-overflow">Showing 60 of {files.length.toLocaleString()} selected files</p>}</>}
      </section>

      {error && <p className="argus-project-modal-error" role="alert">{error}</p>}
      <footer className="argus-project-modal-footer"><button type="button" className="argus-project-modal-cancel" disabled={busy} onClick={onClose}>Cancel</button><button type="submit" className="argus-project-modal-next" disabled={!name.trim() || busy}>{busy ? 'Creating project…' : 'Next'}{busy ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}</button></footer>
    </form>
  </dialog>;
}
