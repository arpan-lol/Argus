'use client';

import { useId } from 'react';
import type { ChatEvent } from '@/lib/chat';

type Hop = NonNullable<ChatEvent['result']>['tree'][number];

const short = (value: string) => value.length > 27 ? `${value.slice(0, 25)}…` : value;

export function ChatGraphPreview({ hops, candidate, onOpen }: { hops: Hop[]; candidate: boolean; onOpen: () => void }) {
  const markerId = useId();
  const names = new Map<string, string>();
  const depths = new Map<string, number>();
  depths.set(hops[0].from, 0);
  for (const hop of hops) {
    names.set(hop.subject.id, hop.subject.name);
    names.set(hop.object.id, hop.object.name);
    if (!depths.has(hop.from)) depths.set(hop.from, 0);
    if (!depths.has(hop.to)) depths.set(hop.to, (depths.get(hop.from) || 0) + 1);
  }
  const columns = new Map<number, string[]>();
  for (const [identifier, depth] of depths) columns.set(depth, [...(columns.get(depth) || []), identifier]);
  const width = Math.max(520, (Math.max(...columns.keys()) + 1) * 170 + 70);
  const height = Math.max(164, Math.max(...[...columns.values()].map(column => column.length)) * 76 + 55);
  const positions = new Map<string, { x: number; y: number }>();
  for (const [depth, identifiers] of columns) identifiers.forEach((identifier, index) => positions.set(identifier, { x: 80 + depth * 170, y: (height - (identifiers.length - 1) * 76) / 2 + index * 76 - 10 }));

  return <button type="button" className={`ce-answer-graph${candidate ? ' is-candidate' : ''}`} onClick={onOpen} aria-label={`Show ${hops.length}-hop graph trail in the Knowledge Graph`}>
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden="true">
      <defs><marker id={markerId} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 1 1 L 9 5 L 1 9" fill="none" stroke="currentColor" strokeWidth="1.5" /></marker></defs>
      {hops.map(hop => {
        const source = positions.get(hop.subject.id);
        const target = positions.get(hop.object.id);
        if (!source || !target) return null;
        const direction = source.x <= target.x ? 1 : -1;
        const middleX = (source.x + target.x) / 2;
        return <g key={hop.assertionId} className="ce-answer-graph-edge">
          <path d={`M ${source.x + direction * 9} ${source.y} Q ${middleX} ${(source.y + target.y) / 2 - 27} ${target.x - direction * 12} ${target.y}`} markerEnd={`url(#${markerId})`} />
          <text x={middleX} y={(source.y + target.y) / 2 - 25} textAnchor="middle">{short(hop.predicate.replaceAll('_', ' '))}</text>
        </g>;
      })}
      {[...positions].map(([identifier, position]) => <g key={identifier} className="ce-answer-graph-node" transform={`translate(${position.x} ${position.y})`}><circle r="8" /><text y="25" textAnchor="middle">{short(names.get(identifier) || 'Entity')}</text></g>)}
    </svg>
    <span>{candidate ? 'Candidate route · inspect source support' : 'Open this graph trail'}</span>
  </button>;
}
