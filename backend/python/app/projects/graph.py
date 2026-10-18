import hashlib
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.types.json import Jsonb

from app.database import connection
from app.ingestion.config import processing_config
from app.ingestion.publication import graph_connection
from app.ingestion.structure import sections_for, chunk_sections
from .scope import project_scope


router = APIRouter(prefix='/projects/{project_id}/map', dependencies=[Depends(project_scope)])


def store_layout(pipeline, job):
    project_id = job['configuration'].get('projectId')
    if not project_id:
        return
    document = pipeline.artifact(job['id'], 'normalize')
    sections = sections_for(document, job)
    chunks = pipeline.artifact(job['id'], 'chunk')['chunks']
    for mode in ('network', 'grouped'):
        with connection() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('project-layout:' + project_id + mode,))
            root = conn.execute('SELECT x,y FROM project_layouts WHERE project_id=%s AND mode=%s AND node_id=%s', (project_id, mode, job['source_id'])).fetchone()
            count = conn.execute("SELECT count(*) AS n FROM project_layouts WHERE project_id=%s AND mode=%s AND payload->>'type'='document'", (project_id, mode)).fetchone()['n']
            angle = count * math.pi * (3 - math.sqrt(5))
            radius = 1200 * math.sqrt(count)
            x, y = (root['x'], root['y']) if root else (radius * math.cos(angle), radius * math.sin(angle))
            def put(identifier, kind, px, py, label, **metadata):
                payload = {'id': identifier, 'type': kind, 'label': label[:100], 'preview': label[:180], 'jobId': job['id'], **metadata}
                conn.execute('INSERT INTO project_layouts(project_id,mode,node_id,x,y,payload) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(project_id,mode,node_id) DO UPDATE SET payload=excluded.payload', (project_id, mode, identifier, px, py, Jsonb(payload)))
            put(job['source_id'], 'document', x, y, document['metadata'].get('title', job['filename']), documentId=job['source_id'])
            section_positions = {}
            for position, section in enumerate(sections):
                angle = math.tau * position / max(1, len(sections))
                sx, sy = (x + (position - len(sections) / 2) * 130, y + 150) if mode == 'grouped' else (x + 250 * math.cos(angle), y + 250 * math.sin(angle))
                section_positions[section['id']] = (sx, sy)
                put(section['id'], 'section', sx, sy, section['title'], documentId=job['source_id'], sectionId=section['id'])
            child_counts = {}
            for chunk in chunks:
                primary, _ = chunk_sections(chunk, sections)
                sx, sy = section_positions[primary['id']]
                ordinal = child_counts.get(primary['id'], 0)
                child_counts[primary['id']] = ordinal + 1
                angle = ordinal * math.pi * (3 - math.sqrt(5))
                r = 55 * math.sqrt(ordinal + 1)
                cx, cy = (sx + (ordinal % 9 - 4) * 28, sy + 90 + ordinal // 9 * 30) if mode == 'grouped' else (sx + r * math.cos(angle), sy + r * math.sin(angle))
                put(chunk['id'], 'chunk', cx, cy, chunk['text'], documentId=job['source_id'], sectionId=primary['id'], chunkId=chunk['id'])
                extracted = pipeline.item(job['id'], 'extract', chunk['id'])
                for entity in extracted['entities']:
                    from app.ingestion.config import fingerprint
                    mention_id = 'mention:' + fingerprint([chunk['id'], entity['key']])
                    decision = pipeline.item(job['id'], 'resolve', mention_id)
                    entity_id = decision['canonicalId']
                    h = int(hashlib.sha256(entity_id.encode()).hexdigest()[:12], 16)
                    ea = h / (16 ** 12) * math.tau
                    put(entity_id, 'entity', cx + 80 * math.cos(ea), cy + 80 * math.sin(ea), entity['name'], entityType=entity['entity_type'])


def nodes_for(project_id, mode, bounds=None, limit=800, documents_only=False, identifiers=None):
    query = "SELECT l.* FROM project_layouts l WHERE l.project_id=%s AND l.mode=%s AND (((l.payload->>'type')='entity' AND EXISTS(SELECT 1 FROM ingestion_resolution_decisions d JOIN ingestion_publications p ON p.job_id=d.job_id JOIN ingestion_jobs j ON j.id=d.job_id WHERE d.canonical_id=l.node_id AND p.active AND j.project_id=l.project_id)) OR ((l.payload->>'type')<>'entity' AND EXISTS(SELECT 1 FROM ingestion_publications p WHERE p.job_id=l.payload->>'jobId' AND p.active)))"
    parameters = [project_id, mode]
    if bounds:
        query += ' AND l.x BETWEEN %s AND %s AND l.y BETWEEN %s AND %s'
        parameters.extend([bounds['minX'], bounds['maxX'], bounds['minY'], bounds['maxY']])
    if documents_only:
        query += " AND l.payload->>'type'='document'"
    if identifiers is not None:
        query += ' AND l.node_id=ANY(%s)'
        parameters.append(identifiers)
    query += ' ORDER BY l.node_id LIMIT %s'
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
    rows = graph.ro_query("MATCH (a)-[r:HAS_SECTION|HAS_CHUNK|NEXT_CHUNK|MENTIONS|RELATES]->(b) WHERE a.id IN $ids AND b.id IN $ids AND a.active=true AND b.active=true AND (type(r)<>'RELATES' OR r.active=true) RETURN a.id,b.id,type(r),r.predicate LIMIT 4000", {'ids': ids}, timeout=1500).result_set
    return [{'id': a + '|' + kind + '|' + b + '|' + (predicate or ''), 'source': a, 'target': b, 'type': kind, 'predicate': predicate} for a, b, kind, predicate in rows]


@router.get('/overview')
def overview(project_id: str, mode: str = Query('network', pattern='^(network|grouped)$')):
    nodes, truncated = nodes_for(project_id, mode, limit=2000, documents_only=True)
    bounds = {'minX': min((node['x'] for node in nodes), default=0) - 500, 'maxX': max((node['x'] for node in nodes), default=0) + 500, 'minY': min((node['y'] for node in nodes), default=0) - 500, 'maxY': max((node['y'] for node in nodes), default=0) + 500}
    return {'nodes': nodes, 'edges': [], 'bounds': bounds, 'source': 'published semantic sources', 'truncated': truncated}


@router.get('/view')
def view(project_id: str, minX: float, maxX: float, minY: float, maxY: float, zoom: float, mode: str = Query('network', pattern='^(network|grouped)$'), limit: int = Query(800, ge=1, le=1000)):
    nodes, truncated = nodes_for(project_id, mode, {'minX': minX, 'maxX': maxX, 'minY': minY, 'maxY': maxY}, limit, zoom < .45)
    return {'nodes': nodes, 'edges': connections(nodes), 'level': 'documents' if zoom < .45 else 'detail', 'truncated': truncated, 'source': 'falkordb', 'status': 'ready'}


@router.get('/locate/{identifier}')
def locate(project_id: str, identifier: str, mode: str = Query('network', pattern='^(network|grouped)$')):
    nodes, _ = nodes_for(project_id, mode, identifiers=[identifier])
    if not nodes:
        raise HTTPException(404, 'Graph node not published in this project')
    node = nodes[0]
    return {'node': node, 'zoom': 1.1 if node['type'] == 'document' else 2.5, **{key: node[key] for key in ('documentId', 'chunkId', 'sectionId') if key in node}}


@router.get('/node/{identifier}')
def inspect(project_id: str, identifier: str, mode: str = Query('network', pattern='^(network|grouped)$')):
    node = locate(project_id, identifier, mode)['node']
    return {**node, 'description': node.get('entityType', ''), 'content': {'text': node['preview']}}


@router.get('/neighborhood/{identifier}')
def neighborhood(project_id: str, identifier: str, mode: str = Query('network', pattern='^(network|grouped)$')):
    focus = locate(project_id, identifier, mode)['node']
    graph = graph_connection(processing_config())
    rows = graph.ro_query("MATCH p=(a {id:$id})-[:MENTIONS|RELATES|HAS_SECTION|HAS_CHUNK*1..2]-(b) WHERE all(n IN nodes(p) WHERE n.active=true) AND all(r IN relationships(p) WHERE type(r)<>'RELATES' OR r.active=true) RETURN DISTINCT b.id LIMIT 201", {'id': identifier}, timeout=1500).result_set
    nodes, truncated = nodes_for(project_id, mode, identifiers=[identifier, *[row[0] for row in rows[:200]]])
    return {'nodes': nodes, 'edges': connections(nodes), 'paths': [], 'truncated': truncated or len(rows) > 200, 'note': 'Published local connections. Shared mentions are navigation, not agreement between sources.', 'focusId': focus['id']}
