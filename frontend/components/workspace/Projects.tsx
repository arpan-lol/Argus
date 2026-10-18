'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowUpRight, FolderOpen, Loader2, Plus, X } from 'lucide-react';
import { api } from '@/lib/evidence-types';
import type { Project } from '@/lib/projects';
import './Projects.css';

export function Projects() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null);

  function load() {
    setLoading(true);
    setError('');
    api<{projects: Project[]}>('/projects').then(result => setProjects(result.projects))
      .catch(reason => setError(reason instanceof Error ? reason.message : 'Could not load projects. Try again.'))
      .finally(() => setLoading(false));
  }
  useEffect(() => { load(); }, []);
  useEffect(() => { if (creating) input.current?.focus(); }, [creating]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    setError('');
    try {
      const project = await api<Project>('/projects', { method: 'POST', body: JSON.stringify({ name: name.trim() }) });
      router.push(`/dashboard?project=${encodeURIComponent(project.id)}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not create your project. Try again.');
      setBusy(false);
    }
  }

  return <main className="argus-projects">
    <header className="argus-projects-brand"><img src="/argus-logo.svg" alt="" width={30} height={30} /><span>Argus</span></header>
    <div className="argus-projects-content"><div className="argus-projects-heading"><h1>Projects</h1><p>A workspace for your sources, conversations, and connected knowledge.</p></div>
      {error && <div className="argus-projects-error" role="alert"><p>{error}</p>{!creating && <button onClick={load}>Try again</button>}</div>}
      {loading ? <p className="argus-projects-loading" role="status"><Loader2 size={18} className="animate-spin" />Loading projects…</p> : <div className="argus-projects-grid">
        {projects.map(project => <button key={project.id} className="argus-project-card" onClick={() => router.push(`/dashboard?project=${encodeURIComponent(project.id)}`)}><div className="argus-project-card-top"><FolderOpen size={23} /><ArrowUpRight size={18} /></div><h2>{project.name}</h2><div className="argus-project-card-bottom"><span>{(project.files || 0).toLocaleString()} {(project.files || 0) === 1 ? 'source' : 'sources'}</span><span>{(project.published || 0).toLocaleString()} searchable</span></div></button>)}
        {creating ? <form className="argus-project-card argus-project-create" onSubmit={event => void create(event)}><div className="argus-project-create-heading"><h2>New Project</h2><button type="button" disabled={busy} onClick={() => { setCreating(false); setName(''); }} aria-label="Cancel new project"><X size={17} /></button></div><label htmlFor="project-name">Project name</label><input id="project-name" ref={input} value={name} onChange={event => setName(event.target.value)} maxLength={120} disabled={busy} required placeholder="Name your workspace" /><button className="argus-project-create-submit" type="submit" disabled={!name.trim() || busy}>{busy && <Loader2 size={14} className="animate-spin" />}{busy ? 'Creating…' : 'Create project'}</button></form> : <button className="argus-project-card argus-project-add" onClick={() => setCreating(true)}><Plus size={30} strokeWidth={1.5} /><span>New Project</span></button>}
      </div>}
    </div>
  </main>;
}
