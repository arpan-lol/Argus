import math

from psycopg.types.json import Jsonb

from app.database import connection
from .config import fingerprint
from .providers import Providers
from .publication import semantic_graph_name
from .semantic_context import stable_identifier


def resolve_basic(pipeline, job):
    provider = Providers(job['configuration'], pipeline.call_recorder(job['id']), lambda: pipeline.check_paused(job['id']))
    space = semantic_graph_name(job['configuration'])
    mentions = deferred_count = 0
    records = []
    for chunk in pipeline.artifact(job['id'], 'chunk')['chunks']:
        extracted = pipeline.item(job['id'], 'extract', chunk['id'])
        deferred = bool(extracted.get('metadata', {}).get('fallback'))
        for entity in extracted['entities']:
            mention_id = 'mention:' + fingerprint([chunk['id'], entity['key']])
            identifier = stable_identifier(entity['name'])
            native_key = entity.get('nativeResolverKey')
            surface = entity['name'].strip().lower()
            ambiguous_short = len(surface) <= 3 and identifier is None and not native_key
            identity_key = ['identifier', identifier.lower(), entity['entity_type'].strip().lower()] if identifier else ['surface', surface, entity['entity_type'].strip().lower()]
            if native_key:
                identity_key = ['native_stix', native_key.lower(), entity['entity_type'].strip().lower()]
            if ambiguous_short:
                identity_key.append(job['source_id'])
            canonical_id = 'entity:' + fingerprint([space, identity_key]) if not deferred else 'entity:' + fingerprint([job['id'], mention_id])
            records.append((entity, mention_id, canonical_id, deferred))
    structure = pipeline.artifact(job['id'], 'normalize').get('codeGraph', {})
    for item in structure.get('entities', []):
        canonical_id = 'entity:' + fingerprint([space, item['name'].strip(), item['type']])
        for occurrence in item['occurrences']:
            mention_id = 'mention:' + fingerprint([job['id'], 'python_ast', item['key'], occurrence['start'], occurrence['end']])
            entity = {'name': item['name'], 'entity_type': item['type'], 'description': 'Python source module or symbol', 'quote': occurrence['quote']}
            records.append((entity, mention_id, canonical_id, False))
    unique = {canonical_id: entity for entity, _, canonical_id, _ in records}
    unique = dict(sorted(unique.items()))
    with connection() as conn:
        existing = {row['id']: row for row in conn.execute('SELECT id,embedding,embedding_model FROM ingestion_entities WHERE id=ANY(%s)', (list(unique),)).fetchall()} if unique else {}
        cached_vectors = {row['item_id']: row['payload']['vector'] for row in conn.execute("SELECT item_id,payload FROM ingestion_items WHERE job_id=%s AND stage='entity_embed'", (job['id'],)).fetchall()}
    vectors_by_id = {}
    for canonical_id in unique:
        prior = existing.get(canonical_id)
        vector = cached_vectors.get(canonical_id) or (prior['embedding'] if prior and prior['embedding_model'] == job['configuration']['embeddingModel'] else None)
        if vector and len(vector) == job['configuration']['embeddingDimensions'] and all(math.isfinite(value) for value in vector) and any(vector):
            vectors_by_id[canonical_id] = vector
    missing = [(entity, canonical_id) for canonical_id, entity in unique.items() if canonical_id not in vectors_by_id]
    for start in range(0, len(missing), 256):
        batch = missing[start:start + 256]
        key = fingerprint([job['configuration']['embeddingModel'], [mention_id for _, mention_id in batch]])
        vectors = pipeline.retry_call(job, 'entity_embed_batch', key, lambda rows=batch: {'vectors': provider.embed([entity['name'] + '\n' + entity['entity_type'] + '\n' + entity['description'] for entity, _ in rows])})['vectors']
        with connection() as conn, conn.cursor() as cursor:
            cursor.executemany("INSERT INTO ingestion_items(job_id,stage,item_id,payload) VALUES(%s,'entity_embed',%s,%s) ON CONFLICT(job_id,stage,item_id) DO UPDATE SET payload=excluded.payload", [(job['id'], identifier, Jsonb({'vector': vector})) for (_, identifier), vector in zip(batch, vectors, strict=True)])
        vectors_by_id.update({identifier: vector for (_, identifier), vector in zip(batch, vectors, strict=True)})
    decisions = []
    items = []
    for entity, mention_id, canonical_id, deferred in records:
        vector = vectors_by_id[canonical_id]
        if len(vector) != job['configuration']['embeddingDimensions'] or not any(vector) or any(not math.isfinite(value) for value in vector):
            raise ValueError('Entity vector is invalid')
        decision_id = 'resolution:' + fingerprint([job['id'], mention_id])
        verdict = 'deferred' if deferred else 'same'
        rationale = 'GLiNER fallback mention kept separate.' if deferred else 'STIX object ID and consistent native type key.' if entity.get('nativeResolverKey') else 'Exact qualified Python symbol, preserving case.' if entity['entity_type'].startswith('code_') else 'Stable identifier candidate grouping.' if stable_identifier(entity['name']) else 'Exact normalized name and type candidate grouping; identity is unverified and homonyms may remain.'
        decisions.append((decision_id, job['id'], mention_id, canonical_id, verdict, rationale, Jsonb([])))
        items.append((job['id'], mention_id, Jsonb({'mentionId': mention_id, 'canonicalId': canonical_id, 'decisionId': decision_id, 'deferred': deferred, 'reason': rationale, 'identityStatus': 'native_stix_id' if entity.get('nativeResolverKey') else 'exact_symbol' if entity['entity_type'].startswith('code_') else 'stable_identifier' if stable_identifier(entity['name']) else 'source_scoped_short_surface_form' if len(entity['name'].strip()) <= 3 else 'unverified_surface_form', 'nativeResolverKey': entity.get('nativeResolverKey'), 'nativeFormat': entity.get('nativeFormat')})))
        mentions += 1
        deferred_count += int(deferred)
    with connection() as conn, conn.cursor() as cursor:
        cursor.executemany("INSERT INTO ingestion_entities(id,label,entity_type,description,aliases,embedding,embedding_model,created_by_job,source_quote) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET description=CASE WHEN length(excluded.description)>length(ingestion_entities.description) THEN excluded.description ELSE ingestion_entities.description END", [(identifier, entity['name'], entity['entity_type'], entity['description'], Jsonb([entity['name']]), Jsonb(vectors_by_id[identifier]), job['configuration']['embeddingModel'], job['id'], entity['quote']) for identifier, entity in unique.items()])
        cursor.executemany('INSERT INTO ingestion_resolution_decisions(id,job_id,mention_id,canonical_id,decision,rationale,votes) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET canonical_id=excluded.canonical_id,decision=excluded.decision,rationale=excluded.rationale WHERE NOT ingestion_resolution_decisions.reverted', decisions)
        cursor.executemany("INSERT INTO ingestion_items(job_id,stage,item_id,payload) VALUES(%s,'resolve',%s,%s) ON CONFLICT(job_id,stage,item_id) DO UPDATE SET payload=excluded.payload", items)
        conn.execute('UPDATE ingestion_jobs SET updated_at=now() WHERE id=%s', (job['id'],))
    return {'resolvedMentions': mentions, 'deferredMentions': deferred_count, 'candidatePairs': 0, 'duplicateLlmCalls': 0, 'entityEmbeddingsCreated': len(missing), 'entityEmbeddingsReused': len(unique) - len(missing), 'method': 'sdk-style-normalized-name-type-1'}
