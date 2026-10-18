import math

from psycopg.types.json import Jsonb

from app.database import connection
from .config import fingerprint, processing_config
from .graph_batch import write_batches
from .providers import Providers
from .publication import graph_connection, index, semantic_graph_name


def finalize_entities(pipeline, project_id):
    config = processing_config(project_id)
    graph = graph_connection(config)
    key = 'argus-entity-finalization:' + semantic_graph_name(config)
    created = reused = 0
    with connection() as lease:
        acquired = lease.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired', (key,)).fetchone()['acquired']
        if not acquired:
            raise RuntimeError('Entity finalization is already running for this workspace')
        try:
            while True:
                with connection() as conn:
                    if conn.execute("SELECT 1 FROM ingestion_jobs WHERE project_id=%s AND status IN ('queued','running') LIMIT 1", (project_id,)).fetchone():
                        raise RuntimeError('Finish or pause workspace ingestion before finalizing entity vectors')
                ids = [row[0] for row in graph.query('MATCH (e:Entity) WHERE e.active=true AND e.embedding IS NULL RETURN e.id ORDER BY e.id LIMIT 256').result_set]
                if not ids:
                    break
                with connection() as conn:
                    rows = conn.execute('SELECT * FROM ingestion_entities WHERE id=ANY(%s) ORDER BY id', (ids,)).fetchall()
                    owners = {row['created_by_job'] for row in rows}
                    jobs = {row['id']: row for row in conn.execute('SELECT j.*,s.filename FROM ingestion_jobs j JOIN ingestion_sources s ON s.id=j.source_id WHERE j.id=ANY(%s) AND j.project_id=%s', (list(owners), project_id)).fetchall()}
                if len(rows) != len(ids) or set(jobs) != owners:
                    raise ValueError('Entity finalization requires workspace-owned persisted entities')
                batches = {}
                vectors = {}
                for row in rows:
                    vector = row['embedding']
                    if row['embedding_model'] == config['embeddingModel'] and vector and len(vector) == config['embeddingDimensions'] and all(math.isfinite(value) for value in vector) and any(vector):
                        vectors[row['id']] = vector
                        reused += 1
                    else:
                        batches.setdefault(row['created_by_job'], []).append(row)
                for owner, pending in batches.items():
                    job = jobs[owner]
                    provider = Providers(config, pipeline.call_recorder(owner))
                    texts = [row['label'] for row in pending]
                    batch_key = fingerprint(['entity-name-finalization-1', semantic_graph_name(config), [(row['id'], text) for row, text in zip(pending, texts, strict=True)]])
                    result = pipeline.retry_call(job, 'entity_finalize_batch', batch_key, lambda: {'vectors': provider.embed(texts)})
                    for row, vector in zip(pending, result['vectors'], strict=True):
                        if len(vector) != config['embeddingDimensions'] or not all(math.isfinite(value) for value in vector) or not any(vector):
                            raise ValueError('Finalized entity vector is invalid')
                        vectors[row['id']] = vector
                    created += len(pending)
                with connection() as conn, conn.cursor() as cursor:
                    cursor.executemany('UPDATE ingestion_entities SET embedding=%s,embedding_model=%s WHERE id=%s', [(Jsonb(vector), config['embeddingModel'], identifier) for identifier, vector in vectors.items()])
                write_batches(graph, 'UNWIND $items AS item MATCH (e:Entity {id:item.id}) SET e.embedding=vecf32(item.vector),e.embeddingModel=$model,e.embeddingInputPolicy=$policy', 'items', [{'id': identifier, 'vector': vector} for identifier, vector in vectors.items()], {'model': config['embeddingModel'], 'policy': 'entity-name-finalization-1'}, batch_size=32)
            index(graph, 'Entity', config['embeddingDimensions'])
            return {'entityEmbeddingsCreated': created, 'entityEmbeddingsReused': reused, 'entityVectorIndexReady': True, 'scope': 'active workspace entities at finalization', 'inputPolicy': 'entity names only', 'automatic': False}
        finally:
            lease.rollback()
            lease.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))', (key,))
