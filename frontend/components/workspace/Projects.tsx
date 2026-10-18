'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowUpRight, FolderOpen, Loader2, Moon, Plus, Sun } from 'lucide-react';
import { api } from '@/lib/evidence-types';
import type { Project } from '@/lib/projects';
import { CreateProjectModal } from './CreateProjectModal';
import './Projects.css';

export function Projects() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [dark, setDark] = useState(false);

  function load() {
    setLoading(true);
    setError('');
    api<{projects: Project[]}>('/projects').then(result => setProjects(result.projects))
      .catch(reason => setError(reason instanceof Error ? reason.message : 'Could not load projects. Try again.'))
      .finally(() => setLoading(false));
  }
  useEffect(() => { load(); }, []);
  useEffect(() => {
    const value = localStorage.getItem('falkor-theme') === 'dark';
    setDark(value);
    document.documentElement.classList.toggle('dark', value);
  }, []);

  function toggleTheme() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle('dark', next);
    localStorage.setItem('falkor-theme', next ? 'dark' : 'light');
  }

  return <main className="argus-projects">
    <header className="argus-projects-brand"><img src="/argus-logo.svg" alt="" width={30} height={30} /><span>Argus</span><button className="argus-projects-theme" type="button" onClick={toggleTheme} aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`} title={`Switch to ${dark ? 'light' : 'dark'} mode`}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button></header>
    <div className="argus-projects-content"><div className="argus-projects-heading"><h1>Projects</h1><p>A workspace for your sources, conversations, and connected knowledge.</p></div>
      {error && <div className="argus-projects-error" role="alert"><p>{error}</p>{!creating && <button onClick={load}>Try again</button>}</div>}
      {loading ? <p className="argus-projects-loading" role="status"><Loader2 size={18} className="animate-spin" />Loading projects…</p> : <div className="argus-projects-grid">
        {projects.map(project => <button key={project.id} className="argus-project-card" onClick={() => router.push(`/dashboard?project=${encodeURIComponent(project.id)}`)}><div className="argus-project-card-top"><FolderOpen size={23} /><ArrowUpRight size={18} /></div><h2>{project.name}</h2><div className="argus-project-card-bottom"><span>{(project.files || 0).toLocaleString()} {(project.files || 0) === 1 ? 'source' : 'sources'}</span><span>{(project.published || 0).toLocaleString()} searchable</span></div></button>)}
        <button className="argus-project-card argus-project-add" onClick={() => setCreating(true)}><Plus size={30} strokeWidth={1.5} /><span>New Project</span></button>
      </div>}
    </div>
    {creating && <CreateProjectModal onClose={() => setCreating(false)} />}
  </main>;
}
