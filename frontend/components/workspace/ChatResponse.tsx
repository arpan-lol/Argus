'use client';

import { Check, ChevronDown, Loader2, RotateCcw } from 'lucide-react';
import { CitationButton } from '@/components/CitationButton';
import type { ChatSource, ChatTurn } from '@/lib/chat';

const toolLabels: Record<string, string> = {
  source_authors: 'Read source authors', recent_source_updates: 'Check source updates', rank_entities: 'Rank graph connections',
  search_sources: 'Search sources', find_entities: 'Find entities', read_chunks: 'Read passages',
  inspect_assertions: 'Inspect findings', expand_connections: 'Explore connections', find_paths: 'Trace a connection',
};

export function ChatResponse({ turn, pending, onCitation, onResume }: { turn: ChatTurn; pending: boolean; onCitation: (source: ChatSource) => void; onResume: () => void }) {
  const result = turn.result;
  const sources = result?.sources || [];
  const starts = turn.events.filter(event => event.type === 'tool_start');
  const latest = turn.events.filter(event => event.type === 'model' || event.type === 'tool_start').at(-1);
  const citations = (references: string[]) => references.map(reference => {
    const index = sources.findIndex(source => source.id === reference);
    const source = sources[index];
    return source ? <CitationButton key={reference} citation={source} index={index + 1} onCitationClick={() => onCitation(source)} /> : null;
  });
  return <div className="ce-response">
    <div className="ce-response-name"><img src="/argus-logo.svg" alt="" width={22} height={22} /><strong>Argus</strong><span className="ce-model-label">{(result?.model || turn.model || 'gpt-5').toUpperCase()}</span></div>
    {(starts.length > 0 || pending) && <details className="ce-chat-activity" open={pending}>
      <summary>{pending ? <Loader2 size={13} className="spinning" /> : <Check size={13} />}<span>{pending ? latest?.label || toolLabels[latest?.tool || ''] || 'Preparing the response' : `${starts.length} tool ${starts.length === 1 ? 'call' : 'calls'}`}</span><ChevronDown size={13} /></summary>
      {starts.length > 0 && <ol>{starts.map((event, index) => {
        const end = turn.events.find(candidate => candidate.type === 'tool_end' && candidate.callId === event.callId);
        return <li key={`${event.callId}-${index}`}><span>{toolLabels[event.tool || ''] || 'Retrieve sources'}</span><small>{end ? `${end.count ?? 0} results · ${((end.durationMs || 0) / 1000).toFixed(1)}s${end.outcome && !['answered', 'not_found'].includes(end.outcome) ? ` · ${end.outcome.replaceAll('_', ' ')}` : ''}` : 'Running…'}</small></li>;
      })}</ol>}
    </details>}
    {result && <div className="ce-answer-body" aria-live="polite">
      {result.report.paragraphs.map((paragraph, index) => <div className="ce-answer-paragraph" key={index}><p>{paragraph.text}</p>{paragraph.citations.length > 0 && <div className="ce-answer-citations">{citations(paragraph.citations)}</div>}</div>)}
      {result.report.comparison.length > 0 && <div className="ce-comparison-scroll"><table><thead><tr><th>Subject</th><th>Reported finding</th><th>Conditions</th><th>Sources</th></tr></thead><tbody>{result.report.comparison.map((row, index) => <tr key={index}><th scope="row">{row.subject}</th><td>{row.finding}</td><td>{row.conditions}</td><td>{citations(row.citations)}</td></tr>)}</tbody></table></div>}
      {result.report.gaps.length > 0 && <div className="ce-answer-gaps"><strong>Open questions</strong><ul>{result.report.gaps.map((gap, index) => <li key={index}>{gap}</li>)}</ul></div>}
      {sources.length > 0 && <details className="ce-answer-sources"><summary>{sources.length} {sources.length === 1 ? 'citation' : 'citations'}</summary>{sources.map((source, index) => <button key={source.id} onClick={() => onCitation(source)}><span>{index + 1}</span><span><strong>{source.documentTitle}</strong><small>{source.sectionTitle || 'Source passage'} · Open processed file</small></span></button>)}</details>}
      <p className="ce-answer-meta">{(result.usage.runtimeMs / 1000).toFixed(1)}s{result.usage.reportedTokens != null && ` · ${result.usage.reportedTokens.toLocaleString()} tokens`}{result.report.purpose !== 'conversation' && ` · ${result.coverage.publishedDocuments} published ${result.coverage.publishedDocuments === 1 ? 'document' : 'documents'} available`}</p>
    </div>}
    {turn.error && <div className="ce-inline-error" role="alert"><p>{turn.error}</p>{turn.runId && <button className="ce-chat-resume" onClick={onResume} disabled={pending}><RotateCcw size={14} />Reconnect or resume</button>}</div>}
  </div>;
}
