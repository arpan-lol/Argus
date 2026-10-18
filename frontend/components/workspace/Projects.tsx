'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2, Plus } from 'lucide-react';
import { api } from '@/lib/evidence-types';
import type { Project } from '@/lib/projects';
import GlassFolder, { hashString, type ArtPreset, type FolderFile } from '@/components/ui/glass-folder-cards';
import { GlassScene } from '@/components/liquid/glass-scene';
import { CreateProjectModal } from './CreateProjectModal';
import './Projects.css';

interface ProjectDocument { id: string; filename: string; chunkCount?: number }

const FOLDER_ART: ArtPreset[] = ['aurora', 'ember', 'dusk', 'glacier', 'verdant'];
const FOLDER_MIN_WIDTH = 240;
const FOLDER_MAX_WIDTH = 340;
const FOLDER_GAP = 20;

export function Projects() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [documents, setDocuments] = useState<Record<string, FolderFile[]>>({});
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const gridRef = useRef<HTMLDivElement>(null);
  const [folderWidth, setFolderWidth] = useState(FOLDER_MAX_WIDTH);

  useEffect(() => {
    const element = gridRef.current;
    if (!element) return;
    const update = () => {
      const available = element.clientWidth;
      if (!available) return;
      const columns = Math.max(1, Math.floor((available + FOLDER_GAP) / (FOLDER_MAX_WIDTH + FOLDER_GAP)));
      setFolderWidth(Math.max(FOLDER_MIN_WIDTH, Math.min(FOLDER_MAX_WIDTH, Math.floor((available - FOLDER_GAP * (columns - 1)) / columns))));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [loading]);

  function load() {
    setLoading(true);
    setError('');
    setDocuments({});
    api<{projects: Project[]}>('/projects')
      .then(async result => {
        setProjects(result.projects);
        const entries = await Promise.all(result.projects.map(async project => {
          const files = await api<{documents: ProjectDocument[]}>(`/projects/${encodeURIComponent(project.id)}/ingestion/documents?limit=8`)
            .then(body => body.documents.map(document => ({ name: document.filename, meta: document.chunkCount ? `${document.chunkCount.toLocaleString()} chunk${document.chunkCount === 1 ? '' : 's'}` : undefined })))
            .catch(() => [] as FolderFile[]);
          return [project.id, files] as const;
        }));
        setDocuments(Object.fromEntries(entries));
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : 'Could not load projects. Try again.'))
      .finally(() => setLoading(false));
  }
  useEffect(() => { load(); }, []);

  const openProject = (project: Project) => router.push(`/dashboard?project=${encodeURIComponent(project.id)}`);

  return <main className="argus-projects lg-root">
    <GlassScene variant="projects" />
    <header className="argus-projects-brand"><img src="/argus-logo.svg" alt="" width={30} height={30} /><span>Argus</span></header>
    <div className="argus-projects-content"><div className="argus-projects-heading"><h1>Projects</h1><p>A workspace for your sources, conversations, and connected knowledge.</p></div>
      {error && <div className="argus-projects-error" role="alert"><p>{error}</p>{!creating && <button onClick={load}>Try again</button>}</div>}
      {loading ? <p className="argus-projects-loading" role="status"><Loader2 size={18} className="animate-spin" />Loading projects…</p> : <div ref={gridRef} className="argus-projects-grid" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${folderWidth}px, ${folderWidth}px))` }}>
        {projects.map((project, index) => <div
          key={project.id}
          className="argus-project-cell"
          data-glass-anchor={`project:${project.id}`}
          data-glass-radius={30}
        ><GlassFolder
          label={project.name}
          meta={`${(project.files || 0).toLocaleString()} ${(project.files || 0) === 1 ? 'source' : 'sources'}`}
          art={FOLDER_ART[hashString(project.id) % FOLDER_ART.length]}
          seed={hashString(project.id) % 997}
          files={documents[project.id] ?? []}
          action="more"
          menu={[{ label: 'Open project', onSelect: () => openProject(project) }]}
          onFileSelect={() => openProject(project)}
          open={false}
          onOpenChange={next => { if (next) openProject(project); }}
          width={folderWidth}
          appearDelay={index * 70}
        /></div>)}
        <button className="argus-project-card argus-project-add" data-glass-anchor="new-project" data-glass-radius={12} onClick={() => setCreating(true)}><Plus size={30} strokeWidth={1.5} /><span>New Project</span></button>
      </div>}
    </div>
    {creating && <CreateProjectModal onClose={() => setCreating(false)} />}
  </main>;
}
