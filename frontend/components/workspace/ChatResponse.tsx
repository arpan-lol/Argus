'use client';

import { ArrowUpRight, Check, ChevronDown, GitBranch, Loader2, RotateCcw } from 'lucide-react';
import { CitationButton } from '@/components/CitationButton';
import type { ChatSource, ChatTurn } from '@/lib/chat';
import { ChatGraphPreview } from './ChatGraphPreview';

const toolLabels: Record<string, string> = {
  inspect_available_tools: 'List available retrieval tools',
  source_authors: 'Read source authors', recent_source_updates: 'Check source updates', rank_entities: 'Rank graph connections',
  search_sources: 'Search source passages', find_entities: 'Find graph nodes', read_chunks: 'Read source passages',
  inspect_assertions: 'Inspect node relationships', expand_connections: 'Traverse graph relationships', find_paths: 'Trace a graph path', review_path: 'Check path sources',
  resolve_entities: 'Match names to graph nodes', blast_radius: 'Traverse nearby graph nodes', path_between: 'Find a relationship path', load_bearing: 'Rank graph connectivity', recent_changes: 'Recent source indexing',
};

const toolDescriptions: Record<string, string> = {
  search_sources: 'Ranks passages by keyword and vector similarity, then explores graph neighbors and paths between their entities.',
  find_entities: 'Looks up matching entity nodes already published in this workspace graph.',
  resolve_entities: 'Checks which graph nodes match the names in your question.',
  read_chunks: 'Opens the retrieved passage and nearby text from the same source.',
  inspect_assertions: 'Lists source-backed relationships attached to a selected graph node.',
  blast_radius: 'Walks outward from selected nodes and shows the relationships it reaches.',
  path_between: 'Searches for a chain of relationships between two graph nodes.',
  review_path: 'Checks each proposed relationship against its published source passage.',
};

function toolDescription(event: ChatTurn['events'][number]) {
  const query = typeof event.arguments?.query === 'string' ? event.arguments.query.trim() : '';
  const excerpt = query.length > 96 ? `${query.slice(0, 93)}…` : query;
  if (event.tool === 'search_sources' && excerpt) return `Searching for “${excerpt}” · keyword + vector ranking, followed by graph exploration.`;
  if (event.tool === 'find_entities' && excerpt) return `Looking for graph nodes named “${excerpt}”.`;
  return toolDescriptions[event.tool || ''] || 'Reads published workspace records for this answer.';
}

function toolSummary(event: ChatTurn['events'][number], end?: ChatTurn['events'][number]) {
  if (!end) return 'Working';
  const result = end.result;
  if (event.tool === 'search_sources') {
    const passages = `${end.count ?? 0} ${end.count === 1 ? 'passage' : 'passages'}`;
    if (result?.graphNodes?.length || result?.graphRelationshipCount) return `${passages} · ${result.graphNodes?.length ?? 0} starting nodes · ${result.graphRelationshipCount ?? 0} relationships · ${result.graphReachedCount ?? 0} reached nodes${result.graphPathHopCount ? ` · ${result.graphPathHopCount}-hop route${result.intermediateNodeCount ? ` with ${result.intermediateNodeCount} middle node${result.intermediateNodeCount === 1 ? '' : 's'}` : ''}` : ''}`;
    return `${passages} · ${result?.graphStatus === 'no_graph_entities' ? 'no graph nodes matched those passages' : 'graph expansion found no relationship edges'}`;
  }
  if (event.tool === 'path_between') return `${result?.pathCount ?? 0} ${result?.pathCount === 1 ? 'path' : 'paths'} found · ${result?.tree.length ?? 0} hops shown`;
  if (event.tool === 'read_chunks') return `${end.count ?? 0} source passages opened`;
  if (event.tool === 'find_entities' || event.tool === 'resolve_entities') return `${end.count ?? 0} graph nodes matched`;
  if (event.tool === 'review_path') return result?.pathUsable === false ? 'Some relationships did not pass source checks' : `${end.count ?? 0} relationships checked`;
  return `${end.count ?? 0} ${end.count === 1 ? 'result' : 'results'}`;
}

export function ChatResponse({ turn, pending, onCitation, onToolSource, onTrace, onResume }: { turn: ChatTurn; pending: boolean; onCitation: (source: ChatSource) => void; onToolSource: (documentId: string, chunkId?: string, jobId?: string) => void; onTrace: (assertionIds: string[]) => void; onResume: () => void }) {
  const result = turn.result;
  const exhausted = /\b(limit|budget)\b/i.test(turn.error || '');
  const sources = result?.sources || [];
  const starts = turn.events.filter(event => event.type === 'tool_start');
  const latest = turn.events.filter(event => event.type === 'model' || event.type === 'tool_start' || event.type === 'tool_end').at(-1);
  const trailEvents = turn.events.filter(event => event.type === 'tool_end' && event.result?.tree.length);
  const trailEvent = trailEvents.filter(event => event.tool === 'path_between' || event.tool === 'find_paths').at(-1) || trailEvents.at(-1);
  const finalTrail = trailEvent?.result?.tree || [];
  const excludedHops = new Set(turn.events.filter(event => event.type === 'tool_end' && event.tool === 'review_path').flatMap(event => event.result?.excludedAssertionIds || []));
  const answerReferences = new Set([...(result?.report.paragraphs.flatMap(paragraph => paragraph.citations) || []), ...(result?.report.comparison.flatMap(row => row.citations) || [])]);
  const citedTrail = finalTrail.length > 0 && finalTrail.every(hop => hop.sourceReference && answerReferences.has(hop.sourceReference));
  const candidateTrail = trailEvent?.result?.pathUsable === false || finalTrail.some(hop => excludedHops.has(hop.assertionId)) || !citedTrail;
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
        return <details className="ce-tool-block" key={`${event.callId}-${index}`}>
          <summary className="ce-tool-summary"><span className="ce-tool-icon">{end ? <Check size={14} /> : <Loader2 size={14} className="spinning" />}</span><span className="ce-tool-title"><strong>{toolLabels[event.tool || ''] || 'Retrieve workspace data'}</strong><small>{toolDescription(event)}</small></span><span className="ce-tool-meta">{toolSummary(event, end)}<small>{end ? `${((end.durationMs || 0) / 1000).toFixed(1)}s` : 'Running'}</small></span><ChevronDown size={15} className="ce-tool-chevron" /></summary>
          <div className="ce-tool-content">
          {end?.outcome && !['answered', 'not_found'].includes(end.outcome) && <p className="ce-tool-outcome">{end.outcome.replaceAll('_', ' ')}</p>}
          {[...(end?.warnings || []), ...(end?.truncations || [])].slice(0, 2).map((warning, warningIndex) => <p className="ce-tool-outcome" key={warningIndex}>{warning}</p>)}
          {preview?.graphNodes?.length ? <div className="ce-graph-exploration"><div className="ce-traversal-heading"><span><GitBranch size={14} />Automatic graph exploration · up to 2 hops{preview.graphPathHopCount ? ` · ${preview.graphPathHopCount}-hop path search` : ''}</span>{tree.length > 0 && <button type="button" onClick={() => onTrace(tree.map(hop => hop.assertionId))}>Show reached nodes in graph<ArrowUpRight size={13} /></button>}</div><div className="ce-graph-seeds"><strong>Starting nodes found in matched passages</strong><ul>{preview.graphNodes.slice(0, 8).map(node => <li key={node.id}><span><b>{node.name}</b><small>{node.type || 'Entity'}{node.documentTitle ? ` · ${node.documentTitle}` : ''}</small></span>{node.documentId && <button type="button" className="ce-tool-source" onClick={() => onToolSource(node.documentId!, node.sourceChunkId, node.jobId)} aria-label={`Open ${node.name} in its source passage`}><ArrowUpRight size={13} /></button>}</li>)}</ul></div>{tree.length > 0 ? <ol className="ce-graph-hops">{tree.map((hop, hopIndex) => { const fromName = hop.from === hop.subject?.id ? hop.subject?.name : hop.object?.name; const toName = hop.to === hop.object?.id ? hop.object?.name : hop.subject?.name; return <li key={hop.assertionId}><span className="ce-hop-number">{hopIndex + 1}</span><div><small>{(preview.graphPathHopCount ?? 0) > 1 ? `Path hop ${hopIndex + 1} · reached node` : 'Reached node'}</small><strong>{toName}</strong><p className="ce-hop-walk">From {fromName} · graph relationship: {hop.subject?.name} <em>— {hop.predicate.replaceAll('_', ' ')} →</em> {hop.object?.name}</p>{hop.quote && <p>{hop.quote}</p>}{hop.documentId && <button type="button" className="ce-tool-source" onClick={() => onToolSource(hop.documentId!, hop.chunkId, hop.jobId)}>{hop.documentTitle || 'Open relationship source'}<ArrowUpRight size={12} /></button>}</div></li>;})}</ol> : <p className="ce-tool-outcome">{preview.graphRelationshipCount ? `The search traversed ${preview.graphRelationshipCount} published relationships but did not discover a new node or connecting path to display.` : 'The matched passages named graph nodes, but no published relationship edges or connecting path were found.'}</p>}</div> : null}
          {tree.length > 0 && event.tool !== 'search_sources' ? <div className="ce-traversal"><div className="ce-traversal-heading"><span><GitBranch size={14} />{event.tool === 'find_paths' || event.tool === 'path_between' ? 'Connection path' : 'Graph traversal'} · {tree.length} {tree.length === 1 ? 'hop' : 'hops'}</span><button type="button" onClick={() => onTrace(tree.map(hop => hop.assertionId))}>Show in graph<ArrowUpRight size={13} /></button></div><ol>{tree.map((hop, hopIndex) => <li key={hop.assertionId}><span className="ce-hop-number">{hopIndex + 1}</span><div><strong>{hop.from === hop.subject?.id ? hop.subject?.name : hop.object?.name} <em>{hop.from === hop.subject?.id ? '→' : '←'} {hop.predicate.replaceAll('_', ' ')}</em> {hop.from === hop.subject?.id ? hop.object?.name : hop.subject?.name}</strong><p>{hop.quote}</p><small className="ce-hop-status">{hop.extractionMethod === 'python_ast' ? 'Syntax link' : hop.extractionMethod === 'codebase_graph_builder' ? 'Codebase agent · unverified' : hop.traversalStatus === 'source_structured' ? 'Source-defined' : 'Model extraction · unverified'}{hop.polarity && hop.polarity !== 'affirmed' ? ` · ${hop.polarity}` : ''}</small>{hop.documentId && <button type="button" className="ce-tool-source" onClick={() => onToolSource(hop.documentId!, hop.chunkId, hop.jobId)}>{hop.documentTitle || 'Source document'}<ArrowUpRight size={12} /></button>}</div></li>)}</ol><p className="ce-traversal-note">Each hop is a recorded relationship with source text. A path does not establish a new claim.</p></div> : null}
          {preview?.items.length ? <div className="ce-tool-items">{preview.items.slice(0, 5).map((item, itemIndex) => <div key={`${item.id || item.name}-${itemIndex}`}><strong>{item.subject && item.object ? `${item.subject.name} → ${item.predicate?.replaceAll('_', ' ')} → ${item.object.name}` : item.name || item.documentTitle || 'Source passage'}</strong>{item.quote && <p>{item.quote}</p>}{item.documentId && <button type="button" className="ce-tool-source" onClick={() => onToolSource(item.documentId!, item.chunkId, item.jobId)}>{item.documentTitle || 'Source document'}<ArrowUpRight size={12} /></button>}</div>)}{preview.totalItems > 5 && <small>Showing 5 of {preview.totalItems} results</small>}</div> : end && !preview?.graphNodes?.length && !tree.length && <p className="ce-tool-outcome">No matching published graph records were returned.</p>}
          </div>
        </details>;
      })}
      {excludedHops.size > 0 && <p className="ce-tool-outcome" role="status">Path review excluded {excludedHops.size} {excludedHops.size === 1 ? 'hop' : 'hops'}. The displayed route is a candidate, not a verified connection.</p>}
    </div>}
    {result && <div className="ce-answer-body" aria-live="polite">
      {finalTrail.length > 0 && <button type="button" className="ce-answer-trail" onClick={() => onTrace(finalTrail.map(hop => hop.assertionId))}><GitBranch size={17} /><span><strong>{candidateTrail ? 'Explored graph trail' : 'Cited graph trail'} · {finalTrail.length} {finalTrail.length === 1 ? 'hop' : 'hops'}</strong><small>{excludedHops.size ? 'Path review excluded a hop; inspect the graph before relying on this route' : !citedTrail ? 'This route was explored but not fully cited in the answer' : 'Inspect the visited relationships and their sources'}</small></span><ArrowUpRight size={15} /></button>}
      {finalTrail.length > 0 && <ChatGraphPreview hops={finalTrail} candidate={candidateTrail} onOpen={() => onTrace(finalTrail.map(hop => hop.assertionId))} />}
      {result.report.paragraphs.map((paragraph, index) => <div className="ce-answer-paragraph" key={index}><p>{paragraph.text}</p>{paragraph.citations.length > 0 && <div className="ce-answer-citations">{citations(paragraph.citations)}</div>}</div>)}
      {result.report.comparison.length > 0 && <div className="ce-comparison-scroll"><table><thead><tr><th>Subject</th><th>Reported finding</th><th>Conditions</th><th>Sources</th></tr></thead><tbody>{result.report.comparison.map((row, index) => <tr key={index}><th scope="row">{row.subject}</th><td>{row.finding}</td><td>{row.conditions}</td><td>{citations(row.citations)}</td></tr>)}</tbody></table></div>}
      {result.report.gaps.length > 0 && <div className="ce-answer-gaps"><strong>Open questions</strong><ul>{result.report.gaps.map((gap, index) => <li key={index}>{gap}</li>)}</ul></div>}
      {sources.length > 0 && <details className="ce-answer-sources"><summary>{sources.length} {sources.length === 1 ? 'citation' : 'citations'}</summary>{sources.map((source, index) => <button key={source.id} onClick={() => onCitation(source)}><span>{index + 1}</span><span><strong>{source.documentTitle}</strong><small>{source.sectionTitle || 'Source passage'} · Open processed file</small></span></button>)}</details>}
    </div>}
    {turn.error && <div className="ce-inline-error" role="alert"><p>{turn.error}</p>{turn.runId && <button className="ce-chat-resume" onClick={onResume} disabled={pending}><RotateCcw size={14} />{exhausted ? 'Start fresh investigation' : 'Reconnect or resume'}</button>}</div>}
  </div>;
}
