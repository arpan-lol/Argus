import math
import time

import tiktoken

from app.database import connection
from .providers import ConfigurationRequired


def input_tokens(texts):
    if not 1 <= len(texts) <= 2048 or any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError('Embedding requests require 1–2048 nonempty texts')
    encoding = tiktoken.get_encoding('cl100k_base')
    counts = [len(encoding.encode(text, disallowed_special=())) for text in texts]
    if any(count > 8191 for count in counts):
        raise ValueError('An embedding input exceeds 8191 tokens; lower the chunk size')
    if sum(counts) > 300000:
        raise ValueError('Embedding batch exceeds the Azure 300000-token aggregate limit')
    return sum(counts)


def wait_for_capacity(config, tokens, stop_check=lambda: None):
    maximum = config.get('embeddingTokensPerMinute', 135000)
    if not isinstance(maximum, int) or maximum < 1:
        raise ConfigurationRequired('Embedding token rate must be a positive integer')
    reserved = math.ceil(tokens * 1.05)
    if reserved > maximum:
        raise ConfigurationRequired('Embedding batch exceeds the local per-minute token allowance')
    rate_key = str(config.get('embeddingResourceIdentity') or config['embeddingBaseUrl']) + ':' + config['embeddingModel']
    started = time.monotonic()
    while True:
        stop_check()
        with connection() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('embedding-admission:' + rate_key,))
            conn.execute("DELETE FROM ingestion_embedding_reservations WHERE rate_key=%s AND admitted_at<=clock_timestamp()-interval '60 seconds'", (rate_key,))
            usage = conn.execute("SELECT coalesce(sum(tokens),0) AS tokens,extract(epoch FROM min(admitted_at)+interval '60 seconds'-clock_timestamp()) AS wait FROM ingestion_embedding_reservations WHERE rate_key=%s", (rate_key,)).fetchone()
            if usage['tokens'] + reserved <= maximum:
                conn.execute('INSERT INTO ingestion_embedding_reservations(rate_key,tokens) VALUES(%s,%s)', (rate_key, reserved))
                return time.monotonic() - started
            delay = max(0.05, min(float(usage['wait'] or 0.05), 0.25))
        time.sleep(delay)
