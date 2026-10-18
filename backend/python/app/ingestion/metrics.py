import os

from app.database import connection
from .batching import status
from .config import processing_config
from .local_models import runtime_status


def project_metrics(project_id):
    with connection() as conn:
        receipts = conn.execute("SELECT i.payload FROM ingestion_items i JOIN ingestion_jobs j ON j.id=i.job_id WHERE j.project_id=%s AND i.stage='provider_call'", (project_id,)).fetchall()
        stages = conn.execute("SELECT a.stage,count(*) AS attempts,count(*) FILTER (WHERE a.status='failed') AS failures,round(sum(a.duration_ms)::numeric,1) AS total_ms,round(avg(a.duration_ms)::numeric,1) AS mean_ms,round(percentile_cont(.95) WITHIN GROUP (ORDER BY a.duration_ms)::numeric,1) AS p95_ms FROM ingestion_attempts a JOIN ingestion_jobs j ON j.id=a.job_id WHERE j.project_id=%s GROUP BY a.stage ORDER BY sum(a.duration_ms) DESC NULLS LAST", (project_id,)).fetchall()
        jobs = conn.execute("SELECT status,count(*) AS count FROM ingestion_jobs WHERE project_id=%s GROUP BY status", (project_id,)).fetchall()
        timing = conn.execute("SELECT min(created_at) AS first_upload,max(updated_at) AS last_update,extract(epoch FROM max(updated_at)-min(created_at)) AS observed_seconds FROM ingestion_jobs WHERE project_id=%s", (project_id,)).fetchone()
        publications = conn.execute("SELECT p.counts FROM ingestion_publications p JOIN ingestion_jobs j ON j.id=p.job_id WHERE j.project_id=%s AND p.active", (project_id,)).fetchall()
    totals = {'inputTokens': 0, 'outputTokens': 0, 'embeddingTokens': 0, 'llmCalls': 0, 'embeddingCalls': 0, 'embeddingBatchParticipations': 0, 'failedCalls': 0, 'durationMs': 0, 'usageMissingCalls': 0, 'embeddingRateWaitSeconds': 0}
    for row in receipts:
        value = row['payload']
        embedding = value.get('kind') in {'embedding', 'embedding_share', 'query_embedding'}
        network = value.get('networkCall', True)
        usage = value.get('attributedUsage') or value.get('usage') or {}
        if embedding:
            totals['embeddingBatchParticipations'] += 1
        if network:
            totals['embeddingCalls' if embedding else 'llmCalls'] += 1
            totals['failedCalls'] += int(value.get('status') == 'failed')
            totals['durationMs'] += value.get('durationMs') or 0
            totals['embeddingRateWaitSeconds'] += value.get('rateWaitSeconds', 0) if embedding else 0
        totals['usageMissingCalls'] += int(not usage and network)
        totals['embeddingTokens' if embedding else 'inputTokens'] += usage.get('input_tokens', usage.get('prompt_tokens', 0)) or 0
        if not embedding:
            totals['outputTokens'] += usage.get('output_tokens', usage.get('completion_tokens', 0)) or 0
    counts = {}
    for row in publications:
        for key in ('documents', 'sections', 'chunks', 'entities', 'mentions', 'assertions', 'contextReviewRelationships', 'nativeRelationships'):
            counts[key] = counts.get(key, 0) + (row['counts'].get(key) or 0)
    rate_names = ('ARGUS_COST_LLM_INPUT_PER_MILLION', 'ARGUS_COST_LLM_OUTPUT_PER_MILLION', 'ARGUS_COST_EMBEDDING_PER_MILLION')
    rates = [float(os.environ[name]) if os.getenv(name) else None for name in rate_names]
    cost = sum(tokens * rate / 1_000_000 for tokens, rate in zip((totals['inputTokens'], totals['outputTokens'], totals['embeddingTokens']), rates, strict=True)) if all(rate is not None for rate in rates) else None
    config = processing_config(project_id)
    return {'actualReportedUsage': totals, 'costUsd': cost, 'costMeaning': 'Estimate from configured per-million-token rates; shared embedding usage allocated by input token share. Not an Azure invoice. Failed requests with unavailable usage are excluded.', 'costRatesConfigured': all(rate is not None for rate in rates), 'duplicateMode': 'sdk_basic', 'jobs': jobs, 'publishedCounts': counts, 'timing': timing, 'stages': stages, 'stageTimingMeaning': 'Summed attempt durations overlap across workers and parallel stages; not elapsed ingestion time', 'batching': status(), 'localRuntime': runtime_status(), 'execution': {'queue': 'one job per file', 'workers': int(os.getenv('ARGUS_INGESTION_WORKERS', '4')), 'parallelStages': ['embed', 'mentions', 'configure'], 'chunkEmbeddingBatchSize': 128, 'embeddingRequestMaxItems': 256, 'embeddingRequestMaxTokens': 32000, 'embeddingTokensPerMinute': config['embeddingTokensPerMinute']}, 'estimate': {'duplicateLlmCalls': 0, 'extractionLlmCalls': 0, 'workspaceDiscovery': 'Bounded random sample batches; 30-second call dispatch window; dispatched responses finish; durable workspace token reservation'}}
