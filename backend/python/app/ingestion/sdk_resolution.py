import math

from psycopg.types.json import Jsonb

from app.database import connection
from .config import fingerprint
from .providers import Providers
from .publication import semantic_graph_name


def resolve_basic(pipeline, job):
    provider = Providers(job['configuration'], pipeline.call_recorder(job['id']))
    space = semantic_graph_name(job['configuration'])
    mentions = deferred_count = 0
    for chunk in pipeline.artifact(job['id'], 'chunk')['chunks']:
        extracted = pipeline.item(job['id'], 'extract', chunk['id'])
        deferred = bool(extracted.get('metadata', {}).get('fallback'))
        for entity in extracted['entities']:
            mention_id = 'mention:' + fingerprint([chunk['id'], entity['key']])
            canonical_id = 'entity:' + fingerprint([space, entity['name'].strip().lower(), entity['entity_type'].strip().lower()]) if not deferred else 'entity:' + fingerprint([job['id'], mention_id])
            vector = pipeline.retry_call(job, 'entity_embed', mention_id, lambda row=entity: {'vector': provider.embed([row['name'] + '\n' + row['entity_type'] + '\n' + row['description']])[0]})['vector']
            if len(vector) != job['configuration']['embeddingDimensions'] or not any(vector) or any(not math.isfinite(value) for value in vector):
                raise ValueError('Entity vector is invalid')
            decision_id = 'resolution:' + fingerprint([job['id'], mention_id])
            verdict = 'deferred' if deferred else 'same'
            rationale = 'GLiNER fallback mention kept separate.' if deferred else 'SDK-style exact normalized name and type grouping; no LLM duplicate judgment.'
            with connection() as conn:
                conn.execute("INSERT INTO ingestion_entities(id,label,entity_type,description,aliases,embedding,embedding_model,created_by_job,source_quote) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET description=CASE WHEN length(excluded.description)>length(ingestion_entities.description) THEN excluded.description ELSE ingestion_entities.description END", (canonical_id, entity['name'], entity['entity_type'], entity['description'], Jsonb([entity['name']]), Jsonb(vector), job['configuration']['embeddingModel'], job['id'], entity['quote']))
                conn.execute('INSERT INTO ingestion_resolution_decisions(id,job_id,mention_id,canonical_id,decision,rationale,votes) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET canonical_id=excluded.canonical_id,decision=excluded.decision,rationale=excluded.rationale WHERE NOT ingestion_resolution_decisions.reverted', (decision_id, job['id'], mention_id, canonical_id, verdict, rationale, Jsonb([])))
            pipeline.save_item(job['id'], 'resolve', mention_id, {'mentionId': mention_id, 'canonicalId': canonical_id, 'decisionId': decision_id, 'decision': verdict, 'deferred': deferred, 'reason': rationale})
            mentions += 1
            deferred_count += int(deferred)
    return {'resolvedMentions': mentions, 'deferredMentions': deferred_count, 'candidatePairs': 0, 'duplicateLlmCalls': 0, 'method': 'sdk-style-normalized-name-type-1'}
