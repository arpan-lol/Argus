'use client';

import { useEffect, useState } from 'react';
import { Activity, Bell, ChevronDown } from 'lucide-react';
import { projectApi, type ProcessingEvent } from '@/lib/projects';
import { statusLabel } from '@/lib/ingestion-types';
import './ProcessingActivity.css';

interface Metrics {
  actualReportedUsage: { inputTokens: number; outputTokens: number; embeddingTokens: number; llmCalls: number; embeddingCalls: number; failedCalls: number; usageMissingCalls: number };
  duplicateMode: string;
  execution: { queue: string; workers: number; parallelStages: string[]; chunkEmbeddingBatchSize: number };
}

export function ProcessingActivity({ projectId, events, connected }: { projectId: string; events: ProcessingEvent[]; connected: boolean }) {
  const [metrics, setMetrics] = useState<Metrics>();
  const [open, setOpen] = useState(false);
  const sequence = events.at(-1)?.sequence;
  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      void projectApi<Metrics>(projectId, '/metrics').then(result => { if (active) setMetrics(result); }).catch(() => undefined);
    }, 300);
    return () => { active = false; window.clearTimeout(timer); };
  }, [projectId, sequence]);
  const usage = metrics?.actualReportedUsage;
  const label = (event: ProcessingEvent) => {
    if (event.type === 'file_registered') return 'File queued';
    if (event.type === 'graph_updated') return 'Graph updated';
    if (event.type === 'model_call') return `${event.model || 'Model'} · ${event.status || 'returned'}`;
    if (event.type === 'stage_start') return `${statusLabel(event.stage || '')} started`;
    if (event.type === 'stage_complete') return `${statusLabel(event.stage || '')} completed`;
    if (event.type === 'stage_failed') return `${statusLabel(event.stage || '')} stopped`;
    if (event.type === 'item_start') return `${statusLabel(event.stage || '')} · item started`;
    if (event.type === 'item_complete') return `${statusLabel(event.stage || '')} · item completed`;
    if (event.type === 'item_failed') return `${statusLabel(event.stage || '')} · attempt failed`;
    return statusLabel(event.type);
  };
  const latest = events.at(-1);
  return <section className="argus-processing" aria-label="Notifications">
    <button className="argus-processing-heading" onClick={() => setOpen(value => !value)} aria-expanded={open}><span><Bell size={14} />Notifications{latest ? <small>{latest.filename ? `${latest.filename} · ` : ''}{label(latest)}</small> : <small>{connected ? 'All caught up' : 'Reconnecting…'}</small>}</span><small>{connected ? 'Live' : 'Offline'}</small><ChevronDown size={13} /></button>
    {open && <div className="argus-processing-content">
      {usage && <dl className="argus-processing-usage"><div><dt>LLM input</dt><dd>{usage.inputTokens.toLocaleString()}</dd></div><div><dt>LLM output</dt><dd>{usage.outputTokens.toLocaleString()}</dd></div><div><dt>Embedding tokens</dt><dd>{usage.embeddingTokens.toLocaleString()}</dd></div><div><dt>Model calls</dt><dd>{(usage.llmCalls + usage.embeddingCalls).toLocaleString()}</dd></div></dl>}
      <p className="argus-processing-explanation">Reported tokens, not a cost estimate.{usage?.usageMissingCalls ? ` Usage was unavailable for ${usage.usageMissingCalls} calls.` : ''} Duplicate checks: {metrics?.duplicateMode === 'custom' ? 'custom paired LLM judgments' : 'SDK-style name/type grouping'}.</p>
      {metrics?.execution && <p className="argus-processing-explanation">Execution: {metrics.execution.queue}, {metrics.execution.workers} active worker{metrics.execution.workers === 1 ? '' : 's'}. Chunk embedding and extraction run in parallel per file; each embedding request currently sends {metrics.execution.chunkEmbeddingBatchSize} chunk at a time.</p>}
      <ol className="argus-processing-events">{events.slice(-80).reverse().map(event => <li key={event.sequence} className={event.type.endsWith('failed') ? 'is-failed' : ''}><div><strong>{label(event)}</strong>{event.at && <time dateTime={event.at}>{new Date(event.at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>}</div>{event.filename && <p>{event.filename}</p>}{event.durationMs != null && <span>{(event.durationMs / 1000).toFixed(1)}s</span>}{event.attempt != null && <span>Attempt {event.attempt}</span>}{event.counts && <p>{Object.entries(event.counts).map(([name, count]) => `${count.toLocaleString()} ${name}`).join(' · ')}</p>}{event.message && <p>{event.message}</p>}</li>)}</ol>
      {!events.length && <p className="argus-processing-explanation">File updates, model calls, retries, and graph publication will appear here.</p>}
    </div>}
  </section>;
}
