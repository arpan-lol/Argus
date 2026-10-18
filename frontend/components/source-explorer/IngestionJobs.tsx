'use client';

import { Check, ChevronLeft, ChevronRight, Circle, File, FileCode2, FileImage, FileText, Loader2, Pause, RotateCcw } from 'lucide-react';
import { statusLabel, type IngestionJob } from '@/lib/ingestion-types';

interface IngestionJobsProps {
  jobs: IngestionJob[];
  total: number;
  offset: number;
  onPage: (offset: number) => void;
  busyJob?: string;
  pauseRequested?: string;
  onRetry: (jobId: string) => void;
  onPause: (jobId: string) => void;
  onOpen: (documentId: string, jobId: string) => void;
}

const complete = new Set(['complete', 'completed', 'published', 'succeeded']);
const resumable = new Set(['registered', 'paused', 'interrupted', 'budget_exceeded', 'failed', 'waiting_configuration']);
const checkpoints = [
  { label: 'Read', stages: ['register', 'parse', 'normalize'] },
  { label: 'Chunk', stages: ['chunk', 'configure'] },
  { label: 'Embed', stages: ['embed'] },
  { label: 'Extract', stages: ['extract', 'resolve', 'prepare'] },
  { label: 'Publish', stages: ['validate', 'publish'] },
];

function FileKindIcon({ filename }: { filename: string }) {
  const extension = filename.toLowerCase().split('.').pop();
  if (['pdf', 'doc', 'docx', 'txt', 'md', 'rtf'].includes(extension || '')) return <FileText size={19} />;
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'tif', 'tiff'].includes(extension || '')) return <FileImage size={19} />;
  if (['html', 'htm', 'xml', 'json', 'csv', 'tsv'].includes(extension || '')) return <FileCode2 size={19} />;
  return <File size={19} />;
}

function state(job: IngestionJob, names: string[]) {
  const stages = job.stages.filter(stage => names.includes(stage.name));
  if (stages.length && stages.every(stage => complete.has(stage.status))) return 'complete';
  if (stages.some(stage => ['running', 'processing'].includes(stage.status)) || names.includes(job.currentStage || '')) return 'active';
  return 'pending';
}

export function IngestionJobs({ jobs, total, offset, onPage, busyJob, pauseRequested, onRetry, onPause, onOpen }: IngestionJobsProps) {
  const unfinished = jobs.filter(job => !complete.has(job.status)).length;
  return <section className="ce-ingestion" aria-label="Workspace files">
    <div className="ce-ingestion-heading"><span>Files</span><small>{unfinished ? `${unfinished} in progress` : `${total.toLocaleString()} files`}</small></div>
    <div id="file-processing-jobs" className="ce-ingestion-jobs">
      {jobs.map(job => {
        const active = ['running', 'processing'].includes(job.status);
        const doneStages = job.stages.filter(stage => complete.has(stage.status)).length;
        const progress = complete.has(job.status) ? 100 : Math.round(doneStages / (job.stages.length || 1) * 100);
        const currentStage = job.stages.find(stage => stage.name === job.currentStage);
        const detail = currentStage?.metadata?.summary?.join(' ') || statusLabel(job.currentStage || job.status);
        return <article className={`ce-ingestion-job ${active ? 'is-active' : ''}`} key={job.id}>
          <button className="ce-ingestion-card" onClick={() => onOpen(job.documentId || '', job.id)} title={`Open ${job.filename}`}>
            <span className="ce-file-kind"><FileKindIcon filename={job.filename} /></span>
            <span className="ce-ingestion-card-main"><strong>{job.filename}</strong><small>{statusLabel(job.status)}{job.chunkCount ? ` · ${job.chunkCount.toLocaleString()} chunks` : ''}</small></span>
            <ChevronRight size={16} className="ce-ingestion-open" />
          </button>
          <div className="ce-ingestion-progress" role="progressbar" aria-label={`${job.filename} processing`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><span style={{ width: '100%', transform: `scaleX(${progress / 100})` }} /></div>
          {active && <div className="ce-ingestion-checkpoints">{checkpoints.map(checkpoint => { const value = state(job, checkpoint.stages); return <div key={checkpoint.label} className={`is-${value}`}><span>{value === 'complete' ? <Check size={12} /> : value === 'active' ? <Loader2 size={12} className="animate-spin" /> : <Circle size={10} />}</span><small>{checkpoint.label}</small></div>; })}</div>}
          <div className="ce-ingestion-card-footer"><span>{active ? pauseRequested === job.id ? 'Pausing after the current step…' : detail : job.error || (complete.has(job.status) ? 'Ready to view' : statusLabel(job.status))}</span>{active && <button onClick={() => onPause(job.id)} disabled={pauseRequested === job.id || busyJob === job.id} aria-label={`Pause ${job.filename}`}>{pauseRequested === job.id || busyJob === job.id ? <Loader2 size={13} className="animate-spin" /> : <Pause size={13} />}{pauseRequested === job.id ? 'Pausing' : 'Pause'}</button>}{resumable.has(job.status) && <button onClick={() => onRetry(job.id)} disabled={busyJob === job.id}>{busyJob === job.id ? <Loader2 size={13} className="animate-spin" /> : <RotateCcw size={13} />}{job.status === 'registered' ? 'Start' : ['paused', 'interrupted', 'budget_exceeded'].includes(job.status) ? 'Resume' : 'Retry'}</button>}</div>
          {job.error && <p className="ce-ingestion-job-error">{job.error}</p>}
        </article>;
      })}
      {!jobs.length && <p className="ce-ingestion-empty">No files yet. Add files to start building this workspace.</p>}
      {total > 50 && <div className="ce-file-pagination"><button aria-label="Previous files" disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - 50))}><ChevronLeft size={14} /></button><span>{offset + 1}–{Math.min(offset + 50, total)} of {total.toLocaleString()}</span><button aria-label="Next files" disabled={offset + 50 >= total} onClick={() => onPage(offset + 50)}><ChevronRight size={14} /></button></div>}
    </div>
  </section>;
}
