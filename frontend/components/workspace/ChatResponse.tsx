'use client';

import { ArrowUpRight, Check, GitBranch, Loader2, RotateCcw } from 'lucide-react';
import { CitationButton } from '@/components/CitationButton';
import type { ChatSource, ChatTurn } from '@/lib/chat';

const toolLabels: Record<string, string> = {
  inspect_available_tools: 'Inspect available tools',
  source_authors: 'Read source authors', recent_source_updates: 'Check source updates', rank_entities: 'Rank graph connections',
  search_sources: 'Search sources', find_entities: 'Find entities', read_chunks: 'Read passages',
  inspect_assertions: 'Inspect findings', expand_connections: 'Explore connections', find_paths: 'Trace a connection', review_path: 'Review path support',
  resolve_entities: 'Resolve graph names', blast_radius: 'Blast radius · graph reach', path_between: 'Shortest path · path between', load_bearing: 'PageRank · load bearing', recent_changes: 'Recent source indexing',
};

export function ChatResponse({ turn, pending, onCitation, onToolSource, onTrace, onResume }: { turn: ChatTurn; pending: boolean; onCitation: (source: ChatSource) => void; onToolSource: (documentId: string, chunkId?: string, jobId?: string) => void; onTrace: (assertionIds: string[]) => void; onResume: () => void }) {
  const result = turn.result;
  const exhausted = /\b(limit|budget)\b/i.test(turn.error || '');
  const sources = result?.sources || [];
  const starts = turn.events.filter(event => event.type === 'tool_start');
  const latest = turn.events.filter(event => event.type === 'model' || event.type === 'tool_start' || event.type === 'tool_end').at(-1);
  const finalTrail = turn.events.filter(event => event.type === 'tool_end' && event.result?.tree.length).at(-1)?.result?.tree || [];
  const excludedHops = new Set(turn.events.filter(event => event.type === 'tool_end' && event.tool === 'review_path').flatMap(event => event.result?.excludedAssertionIds || []));
  const candidateTrail = finalTrail.some(hop => excludedHops.has(hop.assertionId));
  const citations = (references: string[]) => references.map(reference => {
    const index = sources.findIndex(source => source.id === reference);
    const source = sources[index];
    return source ? <CitationButton key={reference} citation={source} index={index + 1} onCitationClick={() => onCitation(source)} /> : null;
  });
  return <div className="ce-response">
    <div className="ce-response-name"><img src="/argus-logo.svg" alt="" width={22} height={22} /><strong>Argus</strong></div>
    {(pending || starts.length > 0) && <div className="ce-chat-trace" aria-label="Investigation steps">
      {pending && <div className="ce-chat-live ce-live-processing is-working" role="status" aria-live="polite">{latest?.type === 'tool_end' ? 'Reviewing retrieved results' : latest?.label || toolLabels[latest?.tool || ''] || 'Starting investigation'}</div>}
      {starts.map((event, index) => {
        const end = turn.events.find(candidate => candidate.type === 'tool_end' && candidate.callId === event.callId);
        const preview = end?.result;
        const tree = preview?.tree || [];
        return <article className="ce-tool-block" key={`${event.callId}-${index}`}>
          <header><span className="ce-tool-icon">{end ? <Check size={14} /> : <Loader2 size={14} className="spinning" />}</span><strong>{toolLabels[event.tool || ''] || 'Retrieve sources'}</strong><small>{end ? `${end.count ?? 0} results · ${((end.durationMs || 0) / 1000).toFixed(1)}s` : 'Running'}</small></header>
          {end?.outcome && !['answered', 'not_found'].includes(end.outcome) && <p className="ce-tool-outcome">{end.outcome.replaceAll('_', ' ')}</p>}
          {[...(end?.warnings || []), ...(end?.truncations || [])].slice(0, 2).map((warning, warningIndex) => <p className="ce-tool-outcome" key={warningIndex}>{warning}</p>)}
          {tree.length > 0 ? <div className="ce-traversal"><div className="ce-traversal-heading"><span><GitBranch size={14} />{event.tool === 'find_paths' || event.tool === 'path_between' ? 'Connection path' : 'Traversal tree'} · {tree.length} {tree.length === 1 ? 'hop' : 'hops'}</span><button type="button" onClick={() => onTrace(tree.map(hop => hop.assertionId))}>Show in graph<ArrowUpRight size={13} /></button></div><ol>{tree.map((hop, hopIndex) => <li key={hop.assertionId}><span className="ce-hop-number">{hopIndex + 1}</span><div><strong>{hop.from === hop.subject?.id ? hop.subject?.name : hop.object?.name} <em>{hop.from === hop.subject?.id ? '→' : '←'} {hop.predicate.replaceAll('_', ' ')}</em> {hop.from === hop.subject?.id ? hop.object?.name : hop.subject?.name}</strong><p>{hop.quote}</p><small className="ce-hop-status">{hop.extractionMethod === 'python_ast' ? 'Syntax link' : hop.extractionMethod === 'codebase_graph_builder' ? 'Codebase agent · unverified' : hop.traversalStatus === 'source_structured' ? 'Source-defined' : 'Model extraction · unverified'}{hop.polarity && hop.polarity !== 'affirmed' ? ` · ${hop.polarity}` : ''}</small>{hop.documentId && <button type="button" className="ce-tool-source" onClick={() => onToolSource(hop.documentId!, hop.chunkId, hop.jobId)}>{hop.documentTitle || 'Source document'}<ArrowUpRight size={12} /></button>}</div></li>)}</ol><p className="ce-traversal-note">Each hop is a recorded relationship with source text. A path does not establish a new claim.</p></div> : preview?.items.length ? <div className="ce-tool-items">{preview.items.slice(0, 5).map((item, itemIndex) => <div key={`${item.id || item.name}-${itemIndex}`}><strong>{item.subject && item.object ? `${item.subject.name} → ${item.predicate?.replaceAll('_', ' ')} → ${item.object.name}` : item.name || item.documentTitle || 'Source passage'}</strong>{item.quote && <p>{item.quote}</p>}{item.documentId && <button type="button" className="ce-tool-source" onClick={() => onToolSource(item.documentId!, item.chunkId, item.jobId)}>{item.documentTitle || 'Source document'}<ArrowUpRight size={12} /></button>}</div>)}{preview.totalItems > 5 && <small>Showing 5 of {preview.totalItems} results</small>}</div> : end && <p className="ce-tool-outcome">No matching records in this bounded search.</p>}
        </article>;
      })}
      {excludedHops.size > 0 && <p className="ce-tool-outcome" role="status">Path review excluded {excludedHops.size} {excludedHops.size === 1 ? 'hop' : 'hops'}. The displayed route is a candidate, not a verified connection.</p>}
    </div>}
    {result && <div className="ce-answer-body" aria-live="polite">
      {finalTrail.length > 0 && <button type="button" className="ce-answer-trail" onClick={() => onTrace(finalTrail.map(hop => hop.assertionId))}><GitBranch size={17} /><span><strong>{candidateTrail ? 'Candidate graph trail' : 'Explored graph trail'} · {finalTrail.length} {finalTrail.length === 1 ? 'hop' : 'hops'}</strong><small>{candidateTrail ? 'Path review excluded a hop; inspect the graph before relying on this route' : 'Inspect the visited relationships and their sources'}</small></span><ArrowUpRight size={15} /></button>}
      {result.report.paragraphs.map((paragraph, index) => <div className="ce-answer-paragraph" key={index}><p>{paragraph.text}</p>{paragraph.citations.length > 0 && <div className="ce-answer-citations">{citations(paragraph.citations)}</div>}</div>)}
      {result.report.comparison.length > 0 && <div className="ce-comparison-scroll"><table><thead><tr><th>Subject</th><th>Reported finding</th><th>Conditions</th><th>Sources</th></tr></thead><tbody>{result.report.comparison.map((row, index) => <tr key={index}><th scope="row">{row.subject}</th><td>{row.finding}</td><td>{row.conditions}</td><td>{citations(row.citations)}</td></tr>)}</tbody></table></div>}
      {result.report.gaps.length > 0 && <div className="ce-answer-gaps"><strong>Open questions</strong><ul>{result.report.gaps.map((gap, index) => <li key={index}>{gap}</li>)}</ul></div>}
      {sources.length > 0 && <details className="ce-answer-sources"><summary>{sources.length} {sources.length === 1 ? 'citation' : 'citations'}</summary>{sources.map((source, index) => <button key={source.id} onClick={() => onCitation(source)}><span>{index + 1}</span><span><strong>{source.documentTitle}</strong><small>{source.sectionTitle || 'Source passage'} · Open processed file</small></span></button>)}</details>}
    </div>}
    {turn.error && <div className="ce-inline-error" role="alert"><p>{turn.error}</p>{turn.runId && <button className="ce-chat-resume" onClick={onResume} disabled={pending}><RotateCcw size={14} />{exhausted ? 'Start fresh investigation' : 'Reconnect or resume'}</button>}</div>}
  </div>;
}
