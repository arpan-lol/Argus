'use client';

import { useEffect, useState } from 'react';
import { Bell } from 'lucide-react';
import { projectApi, type ProcessingEvent } from '@/lib/projects';
import { statusLabel } from '@/lib/ingestion-types';
import './ProcessingActivity.css';

interface Metrics {
  actualReportedUsage: { inputTokens: number; outputTokens: number; embeddingTokens: number; llmCalls: number; embeddingCalls: number; failedCalls: number; usageMissingCalls: number };
  duplicateMode: string;
  execution: { queue: string; workers: number; parallelStages: string[]; chunkEmbeddingBatchSize: number; embeddingTokensPerMinute?: number };
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
  const summary = latest ? `${latest.filename ? `${latest.filename} · ` : ''}${label(latest)}` : connected ? 'All caught up' : 'Reconnecting';
  return <section className="argus-processing" aria-label="Notifications">
    <button className="argus-processing-heading" onClick={() => setOpen(value => !value)} aria-label="Notifications" title={`Notifications · ${summary}`} aria-expanded={open}><Bell size={16} /><span className={`argus-notification-indicator ${connected ? 'is-connected' : ''}`} /><span className="argus-processing-tooltip">Notifications · {summary}</span></button>
    {open && <div className="argus-processing-content">
      {usage && <dl className="argus-processing-usage"><div><dt>LLM input</dt><dd>{usage.inputTokens.toLocaleString()}</dd></div><div><dt>LLM output</dt><dd>{usage.outputTokens.toLocaleString()}</dd></div><div><dt>Embedding tokens</dt><dd>{usage.embeddingTokens.toLocaleString()}</dd></div><div><dt>LLM calls</dt><dd>{usage.llmCalls.toLocaleString()}</dd></div><div><dt>Embedding calls</dt><dd>{usage.embeddingCalls.toLocaleString()}</dd></div></dl>}
      <p className="argus-processing-explanation">Reported tokens, not a cost estimate.{usage?.usageMissingCalls ? ` Usage was unavailable for ${usage.usageMissingCalls} calls.` : ''} Duplicate resolution groups exact normalized entity names and types without an LLM call.</p>
      {metrics?.execution && <p className="argus-processing-explanation">Execution: {metrics.execution.queue}, {metrics.execution.workers} ingestion worker{metrics.execution.workers === 1 ? '' : 's'}. Chunk embeddings use batches of up to {metrics.execution.chunkEmbeddingBatchSize}. {metrics.execution.embeddingTokensPerMinute ? ` Ingestion allowance: ${metrics.execution.embeddingTokensPerMinute.toLocaleString()} embedding tokens per minute.` : ''} Workspace labels are discovered from sampled batches; entity and relationship extraction runs locally.</p>}
      <ol className="argus-processing-events">{events.slice(-80).reverse().map(event => <li key={event.sequence} className={event.type.endsWith('failed') ? 'is-failed' : ''}><div><strong>{label(event)}</strong>{event.at && <time dateTime={event.at}>{new Date(event.at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>}</div>{event.filename && <p>{event.filename}</p>}{event.durationMs != null && <span>{(event.durationMs / 1000).toFixed(1)}s</span>}{event.rateWaitSeconds != null && event.rateWaitSeconds > 0.1 && <span>Quota wait {event.rateWaitSeconds.toFixed(1)}s</span>}{event.attempt != null && <span>Attempt {event.attempt}</span>}{event.counts && <p>{Object.entries(event.counts).map(([name, count]) => `${count.toLocaleString()} ${name}`).join(' · ')}</p>}{event.message && <p>{event.message}</p>}</li>)}</ol>
      {!events.length && <p className="argus-processing-explanation">File updates, model calls, retries, and graph publication will appear here.</p>}
    </div>}
  </section>;
}
