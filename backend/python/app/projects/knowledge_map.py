import hashlib
import json
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Query

from app.database import connection
from app.ingestion.config import processing_config
from app.ingestion.publication import graph_connection, semantic_graph_name


router = APIRouter()
_layouts = {}
_entity_pattern = "MATCH (e:Entity)<-[:RESOLVED_TO]-(m:Mention)<-[:HAS_MENTION]-(c:Chunk) WHERE e.active=true AND m.active=true AND c.active=true AND m.jobId=c.jobId AND c.jobId IN $jobs"
_relationship_pattern = "MATCH (s:Entity)-[r:RELATES]->(o:Entity),(a:Assertion) WHERE s.active=true AND o.active=true AND r.active=true AND a.active=true AND a.id=r.assertionId AND a.jobId=r.jobId AND a.jobId IN $jobs"


def _snapshot(project_id):
    config = processing_config(project_id)
    namespace = semantic_graph_name(config)
    with connection() as conn:
        conn.execute("SET LOCAL statement_timeout = '3000ms'")
        rows = conn.execute("SELECT p.job_id FROM ingestion_publications p JOIN ingestion_jobs j ON j.id=p.job_id JOIN published_documents d ON d.id=p.source_id WHERE j.project_id=%s AND p.active AND p.counts->>'graph'=%s AND d.metadata->>'revisionId'=j.revision AND d.metadata->>'processingVersion'=j.processing_version ORDER BY p.job_id", (project_id, namespace)).fetchall()
    return graph_connection(config), [row['job_id'] for row in rows], namespace


def _query(graph, statement, jobs, **parameters):
    return graph.ro_query(statement, {'jobs': jobs, **parameters}, timeout=3000).result_set


def _json(value, default):
    if not value:
        return default
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return default


def _coordinates(graph, jobs, namespace):
    key = (namespace, tuple(jobs))
    cached = _layouts.get(key)
    if cached and time.monotonic() - cached['created'] < 120:
        return cached
    links = _query(graph, _relationship_pattern + " RETURN DISTINCT s.id,o.id ORDER BY s.id,o.id LIMIT 20001", jobs)
    adjacent = defaultdict(set)
    for source, target in links[:20000]:
        if source != target:
            adjacent[source].add(target)
            adjacent[target].add(source)
    pending = set(adjacent)
    components = []
    while pending:
        root = min(pending, key=lambda item: (-len(adjacent[item]), item))
        visited = {root}
        frontier = deque([(root, 0)])
        layers = defaultdict(list)
        while frontier:
            node, depth = frontier.popleft()
            pending.discard(node)
            layers[depth].append(node)
            for neighbor in sorted(adjacent[node], key=lambda item: (-len(adjacent[item]), item)):
                if neighbor not in visited:
                    visited.add(neighbor)
                    frontier.append((neighbor, depth + 1))
        components.append((root, layers, len(visited)))
    positions = {}
    cursor_x = cursor_y = row_height = 0
    for root, layers, count in sorted(components, key=lambda item: (-item[2], item[0])):
        width = max(360, max(len(nodes) for nodes in layers.values()) * 150)
        height = max(240, len(layers) * 165)
        if cursor_x and cursor_x + width > 3600:
            cursor_x = 0
            cursor_y += row_height + 240
            row_height = 0
        for depth, nodes in layers.items():
            for ordinal, identifier in enumerate(nodes):
                positions[identifier] = (cursor_x + width / 2 + (ordinal - (len(nodes) - 1) / 2) * 150, cursor_y + depth * 165)
        cursor_x += width + 240
        row_height = max(row_height, height)
    cached = {'positions': positions, 'created': time.monotonic(), 'truncated': len(links) > 20000, 'orphanY': cursor_y + row_height + 300}
    if len(_layouts) >= 8:
        _layouts.pop(next(iter(_layouts)))
    _layouts[key] = cached
    return cached


def _fallback(identifier, base_y):
    value = int(hashlib.sha256(identifier.encode()).hexdigest()[:12], 16)
    return (value % 48 * 150, base_y + (value // 48 % 48) * 140)


def _entities(graph, jobs, identifiers, layout):
    if not identifiers:
        return []
    rows = _query(graph, _entity_pattern + " AND e.id IN $ids RETURN e.id,e.label,e.type,e.description,count(DISTINCT m),count(DISTINCT c.documentId) ORDER BY e.label,e.id", jobs, ids=identifiers)
    return [{'id': identifier, 'type': 'entity', 'label': label or 'Unnamed entity', 'entityType': kind, 'description': description or '', 'mentionCount': mentions, 'documentCount': documents, 'x': layout['positions'].get(identifier, _fallback(identifier, layout['orphanY']))[0], 'y': layout['positions'].get(identifier, _fallback(identifier, layout['orphanY']))[1]} for identifier, label, kind, description, mentions, documents in rows]


@router.get('/knowledge')
def knowledge(project_id: str, offset: int = Query(0, ge=0), limit: int = Query(80, ge=1, le=160), focus: str | None = None, relationOffset: int = Query(0, ge=0), relationLimit: int = Query(160, ge=1, le=240), q: str = Query('', max_length=200)):
    graph, jobs, namespace = _snapshot(project_id)
    search = " AND (toLower(e.label) CONTAINS toLower($q) OR toLower(e.type) CONTAINS toLower($q))" if q.strip() else ''
    entity_total = _query(graph, _entity_pattern + search + " RETURN count(DISTINCT e)", jobs, q=q)[0][0]
    relation_filter = " AND (s.id=$focus OR o.id=$focus)" if focus else ''
    if q.strip():
        relation_filter += " AND (toLower(s.label) CONTAINS toLower($q) OR toLower(o.label) CONTAINS toLower($q) OR toLower(s.type) CONTAINS toLower($q) OR toLower(o.type) CONTAINS toLower($q))"
    relationship_total = _query(graph, _relationship_pattern + relation_filter + " RETURN count(r)", jobs, focus=focus, q=q)[0][0]
    rows = _query(graph, _relationship_pattern + relation_filter + " RETURN s.id,o.id,a.id,r.predicate,a.confidence,a.traversalStatus,a.extractionMethod,a.quote,a.documentId,a.polarity,a.context,a.startOffset,a.endOffset ORDER BY CASE WHEN a.extractionMethod='stix_native' THEN 0 ELSE 1 END,a.id SKIP $offset LIMIT $limit", jobs, focus=focus, q=q, offset=relationOffset, limit=relationLimit)
    edges = [{'id': row[2], 'source': row[0], 'target': row[1], 'type': 'RELATES', 'label': row[3], 'predicate': row[3], 'confidence': row[4], 'traversalStatus': row[5] or 'unclassified', 'extractionMethod': row[6] or 'unknown', 'quote': row[7], 'documentId': row[8], 'polarity': row[9], 'context': _json(row[10], {}), 'startOffset': row[11], 'endOffset': row[12]} for row in rows]
    identifiers = {identifier for row in rows for identifier in row[:2]}
    if focus:
        identifiers.add(focus)
    elif not rows or q.strip() or offset > 0:
        extra = _query(graph, _entity_pattern + search + " WITH e,count(DISTINCT m) AS mentions RETURN e.id ORDER BY mentions DESC,e.id SKIP $offset LIMIT $limit", jobs, q=q, offset=offset, limit=limit)
        identifiers.update(row[0] for row in extra)
    layout = _coordinates(graph, jobs, namespace)
    nodes = _entities(graph, jobs, sorted(identifiers), layout)
    if focus and not any(node['id'] == focus for node in nodes):
        raise HTTPException(404, 'Entity is not published in this workspace')
    available = {node['id'] for node in nodes}
    edges = [edge for edge in edges if edge['source'] in available and edge['target'] in available]
    support = _query(graph, "MATCH (a:Assertion)-[:SUPPORTED_BY]->(c:Chunk) WHERE a.id IN $ids AND a.active=true AND c.active=true AND a.jobId=c.jobId AND c.jobId IN $jobs RETURN a.id,min(c.id)", jobs, ids=[edge['id'] for edge in edges]) if edges else []
    chunks = {row[0]: row[1] for row in support}
    document_ids = sorted({edge['documentId'] for edge in edges if edge.get('documentId')})
    with connection() as conn:
        titles = {row['id']: row['title'] for row in conn.execute('SELECT id,title FROM published_documents WHERE id=ANY(%s)', (document_ids,)).fetchall()} if document_ids else {}
    for edge in edges:
        edge['documentTitle'] = titles.get(edge.get('documentId'), 'Source document')
        edge['chunkId'] = chunks.get(edge['id'])
        edge['confidenceStatus'] = 'uncalibrated_model_score' if edge['confidence'] is not None else 'not_provided'
    xs = [node['x'] for node in nodes] or [0]
    ys = [node['y'] for node in nodes] or [0]
    return {'nodes': nodes, 'edges': edges, 'bounds': {'minX': min(xs) - 120, 'maxX': max(xs) + 120, 'minY': min(ys) - 100, 'maxY': max(ys) + 100}, 'pagination': {'entityTotal': entity_total, 'entityOffset': offset, 'entityLimit': limit, 'hasMoreEntities': not focus and offset + limit < entity_total, 'relationshipTotal': relationship_total, 'relationshipOffset': relationOffset, 'relationshipLimit': relationLimit, 'hasMoreRelationships': relationOffset + relationLimit < relationship_total}, 'focusId': focus, 'source': 'falkordb', 'status': 'ready', 'layout': 'Static connected-component breadth-first layout; isolated entities use deterministic positions', 'layoutTruncated': layout['truncated'], 'note': 'Edges are stored semantic relationships. Local model scores are uncalibrated; source-structured records and review statuses remain distinct. Source containment is available in the source graph view.'}


@router.get('/entity/{identifier}/mentions')
def mentions(project_id: str, identifier: str, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    graph, jobs, namespace = _snapshot(project_id)
    pattern = _entity_pattern + " AND e.id=$id"
    summary = _query(graph, pattern + " RETURN e.id,e.label,e.type,e.description,count(DISTINCT m),count(DISTINCT c),count(DISTINCT c.documentId)", jobs, id=identifier)
    if not summary:
        raise HTTPException(404, 'Entity is not published in this workspace')
    item = summary[0]
    rows = _query(graph, pattern + " WITH m,collect(DISTINCT c)[0] AS c RETURN m.id,m.text,m.sourceSpans,m.startOffset,m.endOffset,c.id,c.text,c.documentId,m.extractionMethod,m.confidence,m.sourceSpanStatus,m.sourceSpanAmbiguous,c.startOffset,c.jobId ORDER BY c.documentId,c.id,m.startOffset,m.id SKIP $offset LIMIT $limit", jobs, id=identifier, offset=offset, limit=limit)
    document_ids = sorted({row[7] for row in rows})
    with connection() as conn:
        documents = {row['id']: row for row in conn.execute('SELECT id,title,metadata FROM published_documents WHERE id=ANY(%s)', (document_ids,)).fetchall()} if document_ids else {}
    records = []
    for row in rows:
        document = documents.get(row[7], {})
        metadata = document.get('metadata') or {}
        records.append({'id': row[0], 'text': row[1], 'sourceSpans': _json(row[2], []), 'startOffset': row[3], 'endOffset': row[4], 'chunkId': row[5], 'chunkText': (row[6] or '')[:12000], 'chunkTextTruncated': len(row[6] or '') > 12000, 'documentId': row[7], 'documentTitle': document.get('title') or 'Source document', 'sourceUrl': metadata.get('sourceUrl'), 'extractionMethod': row[8], 'confidence': row[9], 'sourceSpanStatus': row[10], 'sourceSpanAmbiguous': row[11], 'chunkStartOffset': row[12], 'jobId': row[13]})
    span_rows = _query(graph, pattern + " WITH DISTINCT m RETURN m.sourceSpans", jobs, id=identifier)
    occurrence_count = sum(max(1, len(_json(row[0], []))) for row in span_rows)
    return {'entity': {'id': item[0], 'label': item[1], 'entityType': item[2], 'description': item[3] or ''}, 'mentions': records, 'pagination': {'total': item[4], 'offset': offset, 'limit': limit, 'hasMore': offset + limit < item[4]}, 'counts': {'documents': item[6], 'chunks': item[5], 'occurrences': occurrence_count, 'mentionRecords': item[4]}, 'note': 'Every stored mention is reachable through pagination. A mention record can retain several exact source spans in sourceSpans; confidence is uncalibrated.'}
