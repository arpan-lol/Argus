import hashlib
import math
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.types.json import Jsonb

from app.database import connection
from app.ingestion.config import processing_config
from app.ingestion.publication import graph_connection
from app.ingestion.structure import sections_for, chunk_sections
from .scope import project_scope


_summary_cache = {}
_SOURCE_LAYOUT = 'network'


router = APIRouter(prefix='/projects/{project_id}/map', dependencies=[Depends(project_scope)])


def store_layout(pipeline, job):
    project_id = job['configuration'].get('projectId')
    if not project_id:
        return
    document = pipeline.artifact(job['id'], 'normalize')
    sections = sections_for(document, job)
    chunks = pipeline.artifact(job['id'], 'chunk')['chunks']
    with connection() as conn:
        items = {(row['stage'], row['item_id']): row['payload'] for row in conn.execute("SELECT stage,item_id,payload FROM ingestion_items WHERE job_id=%s AND stage=ANY(%s)", (job['id'], ['extract', 'resolve'])).fetchall()}
    with connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('project-layout:' + project_id + _SOURCE_LAYOUT,))
        root = conn.execute('SELECT x,y FROM project_layouts WHERE project_id=%s AND mode=%s AND node_id=%s', (project_id, _SOURCE_LAYOUT, job['source_id'])).fetchone()
        count = conn.execute("SELECT count(*) AS n FROM project_layouts WHERE project_id=%s AND mode=%s AND payload->>'type'='document'", (project_id, _SOURCE_LAYOUT)).fetchone()['n']
        angle = count * math.pi * (3 - math.sqrt(5))
        radius = 1200 * math.sqrt(count)
        x, y = (root['x'], root['y']) if root else (radius * math.cos(angle), radius * math.sin(angle))
        pending = []
        def put(identifier, kind, px, py, label, **metadata):
            payload = {'id': identifier, 'type': kind, 'label': label[:100], 'preview': label[:180], 'jobId': job['id'], **metadata}
            pending.append((project_id, _SOURCE_LAYOUT, identifier, px, py, Jsonb(payload)))
        put(job['source_id'], 'document', x, y, document['metadata'].get('title', job['filename']), documentId=job['source_id'])
        section_positions = {}
        for position, section in enumerate(sections):
            angle = math.tau * position / max(1, len(sections))
            sx, sy = x + 250 * math.cos(angle), y + 250 * math.sin(angle)
            section_positions[section['id']] = (sx, sy)
            put(section['id'], 'section', sx, sy, section['title'], documentId=job['source_id'], sectionId=section['id'])
        child_counts = {}
        chunk_positions = {}
        for chunk in chunks:
            primary, _ = chunk_sections(chunk, sections)
            sx, sy = section_positions[primary['id']]
            ordinal = child_counts.get(primary['id'], 0)
            child_counts[primary['id']] = ordinal + 1
            angle = ordinal * math.pi * (3 - math.sqrt(5))
            r = 55 * math.sqrt(ordinal + 1)
            cx, cy = sx + r * math.cos(angle), sy + r * math.sin(angle)
            put(chunk['id'], 'chunk', cx, cy, chunk['text'], documentId=job['source_id'], sectionId=primary['id'], chunkId=chunk['id'])
            chunk_positions[chunk['id']] = (cx, cy)
            extracted = items['extract', chunk['id']]
            for entity in extracted['entities']:
                from app.ingestion.config import fingerprint
                mention_id = 'mention:' + fingerprint([chunk['id'], entity['key']])
                decision = items['resolve', mention_id]
                entity_id = decision['canonicalId']
                h = int(hashlib.sha256(entity_id.encode()).hexdigest()[:12], 16)
                ea = h / (16 ** 12) * math.tau
                put(entity_id, 'entity', cx + 80 * math.cos(ea), cy + 80 * math.sin(ea), entity['name'], entityType=entity['entity_type'])
        for entity in document.get('codeGraph', {}).get('entities', []):
            from app.ingestion.config import fingerprint
            from app.ingestion.publication import semantic_graph_name
            entity_id = 'entity:' + fingerprint([semantic_graph_name(job['configuration']), entity['name'].strip(), entity['type']])
            supporting = next((chunk for chunk in chunks if chunk['startOffset'] < entity['end'] and chunk['endOffset'] > entity['start']), None)
            if supporting:
                ax, ay = chunk_positions[supporting['id']]
                h = int(hashlib.sha256(entity_id.encode()).hexdigest()[:12], 16)
                ea = h / (16 ** 12) * math.tau
                put(entity_id, 'entity', ax + 80 * math.cos(ea), ay + 80 * math.sin(ea), entity['name'], entityType=entity['type'], extractionMethod='python_ast')
        with conn.cursor() as cursor:
            cursor.executemany('INSERT INTO project_layouts(project_id,mode,node_id,x,y,payload) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(project_id,mode,node_id) DO UPDATE SET payload=excluded.payload', pending)


def nodes_for(project_id, bounds=None, limit=800, documents_only=False, identifiers=None):
    query = "SELECT l.* FROM project_layouts l WHERE l.project_id=%s AND l.mode=%s AND (((l.payload->>'type')='entity' AND EXISTS(SELECT 1 FROM ingestion_resolution_decisions d JOIN ingestion_publications p ON p.job_id=d.job_id JOIN ingestion_jobs j ON j.id=d.job_id WHERE d.canonical_id=l.node_id AND p.active AND j.project_id=l.project_id)) OR ((l.payload->>'type')<>'entity' AND EXISTS(SELECT 1 FROM ingestion_publications p WHERE p.job_id=l.payload->>'jobId' AND p.active)))"
    parameters = [project_id, _SOURCE_LAYOUT]
    if bounds:
        query += ' AND l.x BETWEEN %s AND %s AND l.y BETWEEN %s AND %s'
        parameters.extend([bounds['minX'], bounds['maxX'], bounds['minY'], bounds['maxY']])
    if documents_only:
        query += " AND l.payload->>'type'='document'"
    if identifiers is not None:
        query += ' AND l.node_id=ANY(%s)'
        parameters.append(identifiers)
    query += " ORDER BY CASE l.payload->>'type' WHEN 'document' THEN 0 WHEN 'section' THEN 1 WHEN 'chunk' THEN 2 ELSE 3 END,l.node_id LIMIT %s"
    parameters.append(limit + 1)
    with connection() as conn:
        rows = conn.execute(query, parameters).fetchall()
    nodes = [{**row['payload'], 'x': row['x'], 'y': row['y']} for row in rows[:limit]]
    return nodes, len(rows) > limit


def connections(nodes):
    if not nodes:
        return []
    ids = [node['id'] for node in nodes]
    graph = graph_connection(processing_config())
    rows = graph.ro_query("MATCH (a)-[r:HAS_SECTION|HAS_CHUNK|NEXT_CHUNK|MENTIONS|RELATES]->(b) WHERE a.id IN $ids AND b.id IN $ids AND a.active=true AND b.active=true AND (type(r)<>'RELATES' OR r.active=true) RETURN a.id,b.id,type(r),r.predicate,r.assertionId,r.extractionMethod,r.confidence LIMIT 4000", {'ids': ids}, timeout=1500).result_set
    return [{'id': a + '|' + kind + '|' + b + '|' + (assertion or predicate or ''), 'source': a, 'target': b, 'type': kind, 'predicate': predicate, 'assertionId': assertion, 'extractionMethod': method, 'confidence': score} for a, b, kind, predicate, assertion, method, score in rows]


def shared_document_connections(nodes):
    ids = [node['id'] for node in nodes if node['type'] == 'document']
    if len(ids) < 2:
        return [], False
    config = processing_config()
    key = (config['semanticGraph'], tuple(sorted(ids)))
    cached = _summary_cache.get(key)
    if cached and time.monotonic() - cached[0] < 5:
        return cached[1], cached[2]
    graph = graph_connection(config)
    rows = graph.ro_query("MATCH (c:Chunk)-[:MENTIONS]->(e:Entity) WHERE c.active=true AND e.active=true AND c.documentId IN $ids RETURN DISTINCT e.id,e.label,c.documentId ORDER BY e.id,c.documentId LIMIT 12001", {'ids': ids}, timeout=2000).result_set
    pairs_by_entity = {}
    labels_by_entity = {}
    for entity_id, label, document_id in rows[:12000]:
        pairs_by_entity.setdefault(entity_id, set()).add(document_id)
        labels_by_entity[entity_id] = label
    truncated = len(rows) > 12000
    scores = {}
    pair_budget = 20000
    pair_work = 0
    ordered_entities = sorted(pairs_by_entity.items(), key=lambda item: (len(item[1]), item[0]))
    for entity_id, documents in ordered_entities:
        if len(documents) > 40:
            truncated = True
            documents = set(sorted(documents)[:40])
        if len(documents) < 2:
            continue
        ordered = sorted(documents)
        pair_count = len(ordered) * (len(ordered) - 1) // 2
        if pair_work + pair_count > pair_budget:
            remaining = pair_budget - pair_work
            bounded_count = max(0, math.floor((1 + math.sqrt(1 + 8 * remaining)) / 2))
            ordered = ordered[:bounded_count]
            pair_count = len(ordered) * (len(ordered) - 1) // 2
            truncated = True
        if len(ordered) < 2:
            break
        pair_work += pair_count
        contribution = 1 / (len(documents) - 1)
        for index, source in enumerate(ordered):
            for target in ordered[index + 1:]:
                score = scores.setdefault((source, target), {'shared': 0, 'score': 0.0, 'labels': [], 'entityIds': []})
                score['shared'] += 1
                score['score'] += contribution
                if len(score['labels']) < 6:
                    score['labels'].append(labels_by_entity[entity_id])
                    score['entityIds'].append(entity_id)
        if pair_work >= pair_budget:
            break
    ranked = sorted(scores.items(), key=lambda item: (-item[1]['score'], -item[1]['shared'], item[0]))
    if len(ranked) > 1200:
        truncated = True
    edges = [{'id': a + '|SHARES_ENTITY|' + b, 'source': a, 'target': b, 'type': 'SHARES_ENTITY', 'derived': True, 'sharedEntities': score['shared'], 'sharedScore': round(score['score'], 6), 'labels': score['labels'], 'entityIds': score['entityIds']} for (a, b), score in ranked[:1200]]
    if len(_summary_cache) >= 64:
        _summary_cache.pop(next(iter(_summary_cache)))
    _summary_cache[key] = (time.monotonic(), edges, truncated)
    return edges, truncated


@router.get('/overview')
def overview(project_id: str):
    nodes, truncated = nodes_for(project_id, limit=2000, documents_only=True)
    bounds = {'minX': min((node['x'] for node in nodes), default=0) - 500, 'maxX': max((node['x'] for node in nodes), default=0) + 500, 'minY': min((node['y'] for node in nodes), default=0) - 500, 'maxY': max((node['y'] for node in nodes), default=0) + 500}
    edges, summary_truncated = shared_document_connections(nodes)
    return {'nodes': nodes, 'edges': edges, 'bounds': bounds, 'source': 'published semantic sources', 'truncated': truncated, 'summaryTruncated': summary_truncated}


@router.get('/view')
def view(project_id: str, minX: float, maxX: float, minY: float, maxY: float, zoom: float, limit: int = Query(800, ge=1, le=1000)):
    bounds = {'minX': minX, 'maxX': maxX, 'minY': minY, 'maxY': maxY}
    documents, _ = nodes_for(project_id, bounds, limit, True)
    documents_only = zoom < .12 and len(documents) > 16
    nodes, truncated = nodes_for(project_id, bounds, limit, documents_only)
    shared_edges, summary_truncated = shared_document_connections(documents)
    return {'nodes': nodes, 'edges': [*shared_edges, *connections(nodes)], 'level': 'documents' if documents_only else 'detail', 'truncated': truncated, 'summaryTruncated': summary_truncated, 'source': 'falkordb', 'status': 'ready'}


@router.get('/locate/{identifier}')
def locate(project_id: str, identifier: str):
    nodes, _ = nodes_for(project_id, identifiers=[identifier])
    if not nodes:
        raise HTTPException(404, 'Graph node not published in this project')
    node = nodes[0]
    return {'node': node, 'zoom': 1.1 if node['type'] == 'document' else 2.5, **{key: node[key] for key in ('documentId', 'chunkId', 'sectionId') if key in node}}


@router.get('/node/{identifier}')
def inspect(project_id: str, identifier: str):
    node = locate(project_id, identifier)['node']
    return {**node, 'description': node.get('entityType', ''), 'content': {'text': node['preview']}}


@router.get('/neighborhood/{identifier}')
def neighborhood(project_id: str, identifier: str):
    focus = locate(project_id, identifier)['node']
    graph = graph_connection(processing_config())
    rows = graph.ro_query("MATCH p=(a {id:$id})-[:MENTIONS|RELATES|HAS_SECTION|HAS_CHUNK*1..2]-(b) WHERE all(n IN nodes(p) WHERE n.active=true) AND all(r IN relationships(p) WHERE type(r)<>'RELATES' OR r.active=true) RETURN DISTINCT b.id LIMIT 201", {'id': identifier}, timeout=1500).result_set
    shared = graph.ro_query("MATCH (a:Chunk {id:$id})-[:MENTIONS]->(e:Entity)<-[:MENTIONS]-(b:Chunk) WHERE a.active=true AND e.active=true AND b.active=true AND a.documentId<>b.documentId RETURN DISTINCT e.id,e.label,b.id,b.documentId LIMIT 41", {'id': identifier}, timeout=1500).result_set if focus['type'] == 'chunk' else []
    identifiers = [identifier, *[row[0] for row in rows[:200]], *[value for entity, label, chunk, document in shared[:40] for value in (entity, chunk, document)]]
    nodes, truncated = nodes_for(project_id, identifiers=identifiers)
    titles = {node['id']: node['label'] for node in nodes if node['type'] == 'document'}
    paths = [{'sourceChunkId': identifier, 'targetChunkId': chunk, 'entityId': entity, 'label': label, 'documentId': document, 'documentTitle': titles.get(document, 'Connected source')} for entity, label, chunk, document in shared[:40]]
    return {'nodes': nodes, 'edges': connections(nodes), 'paths': paths, 'truncated': truncated or len(rows) > 200 or len(shared) > 40, 'note': 'Published local connections. Shared mentions are navigation, not agreement between sources.', 'focusId': focus['id']}


from .knowledge_map import router as knowledge_router

router.include_router(knowledge_router)
