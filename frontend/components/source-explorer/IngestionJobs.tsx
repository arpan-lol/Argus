'use client';

import { Check, ChevronDown, ChevronLeft, ChevronRight, Circle, Loader2, RotateCcw, TriangleAlert } from 'lucide-react';
import { statusLabel, type IngestionJob } from '@/lib/ingestion-types';
import { IngestionSettings } from './IngestionSettings';

interface IngestionJobsProps {
  apiRoot?: string;
  jobs: IngestionJob[];
  total: number;
  offset: number;
  onPage: (offset: number) => void;
  expanded: boolean;
  busyJob?: string;
  onToggle: () => void;
  onRetry: (jobId: string) => void;
  onOpen: (documentId: string, jobId: string) => void;
}

const completed = new Set(['complete', 'completed', 'published', 'succeeded']);
const running = new Set(['running', 'processing']);
const resumable = new Set(['registered', 'paused', 'interrupted', 'budget_exceeded', 'failed', 'waiting_configuration']);

export function IngestionJobs({ apiRoot, jobs, total, offset, onPage, expanded, busyJob, onToggle, onRetry, onOpen }: IngestionJobsProps) {
  const unfinished = jobs.filter(job => !completed.has(job.status)).length;
  return <section className="ce-ingestion" aria-label="File processing">
    <button className="ce-ingestion-heading" onClick={onToggle} aria-expanded={expanded} aria-controls="file-processing-jobs"><span>{expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}File processing</span><small>{unfinished ? `${unfinished} pending on this page` : `${jobs.length} complete on this page`}</small></button>
    {expanded && <div id="file-processing-jobs" className="ce-ingestion-jobs">
      {jobs.map(job => <details className="ce-ingestion-job" key={job.id}>
        <summary><span className="ce-ingestion-job-name" title={job.filename}>{job.filename}</span><span className={`ce-ingestion-status is-${job.status}`}>{statusLabel(job.status)}</span><ChevronDown size={12} /></summary>
        <ol className="ce-ingestion-stages">{job.stages.map(stage => <li key={stage.name} className={`is-${stage.status}`}><span className="ce-ingestion-stage-icon">{stage.metadata?.summary?.length ? <TriangleAlert size={13} /> : completed.has(stage.status) ? <Check size={13} /> : running.has(stage.status) ? <Loader2 size={13} className="animate-spin" /> : resumable.has(stage.status) ? <TriangleAlert size={13} /> : <Circle size={10} />}</span><div><strong>{statusLabel(stage.name)}</strong><span>{statusLabel(stage.status)}{stage.attempts > 0 ? ` · ${stage.attempts} ${stage.attempts === 1 ? 'attempt' : 'attempts'}` : ''}{stage.durationMs != null ? ` · ${(stage.durationMs / 1000).toFixed(1)}s` : ''}</span>{stage.error && <p role="alert">{stage.error}</p>}{stage.metadata?.summary?.map(message => <p key={message} role="status">{message}</p>)}{stage.history && stage.history.length > 1 && <details className="ce-ingestion-attempt-history"><summary>Attempt history</summary><ol>{stage.history.map(attempt => <li key={attempt.attempt}><span>Attempt {attempt.attempt} · {statusLabel(attempt.status)}{attempt.duration_ms != null ? ` · ${(attempt.duration_ms / 1000).toFixed(1)}s` : ''}{attempt.started_at ? ` · ${new Date(attempt.started_at).toLocaleString()}` : ''}</span>{attempt.error && <p>{attempt.error}</p>}</li>)}</ol></details>}</div></li>)}</ol>
        <IngestionSettings job={job} apiRoot={apiRoot} />
        {job.error && <p className="ce-ingestion-job-error">{job.error}</p>}
        <div className="ce-ingestion-job-actions">{job.documentId && job.stages.some(stage => stage.name === 'normalize' && completed.has(stage.status)) && <button onClick={() => onOpen(job.documentId!, job.id)}>Read file<ChevronRight size={13} /></button>}{resumable.has(job.status) && <button onClick={() => onRetry(job.id)} disabled={busyJob === job.id}>{busyJob === job.id ? <Loader2 size={13} className="animate-spin" /> : <RotateCcw size={13} />}{job.status === 'registered' ? 'Start processing' : ['paused', 'interrupted', 'budget_exceeded'].includes(job.status) ? 'Resume processing' : 'Retry stage'}</button>}</div>
      </details>)}
      {total > 50 && <div className="ce-file-pagination"><button aria-label="Previous processing jobs" disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - 50))}><ChevronLeft size={14} /></button><span>{offset + 1}–{Math.min(offset + 50, total)} of {total.toLocaleString()}</span><button aria-label="Next processing jobs" disabled={offset + 50 >= total} onClick={() => onPage(offset + 50)}><ChevronRight size={14} /></button></div>}
    </div>}
  </section>;
}
