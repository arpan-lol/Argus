import re

import tiktoken

from .config import fingerprint


UPSTREAM = "https://github.com/FalkorDB/GraphRAG-SDK/blob/v1.4.0/graphrag_sdk/src/graphrag_sdk/ingestion/chunking_strategies/sentence_token_cap.py"


def chunk_document(document, scope, config):
    encoding = tiktoken.get_encoding(config["tokenEncoding"])
    text = document["text"]
    bounds = []
    cursor = 0
    for part in re.split(r"(?<=[.!?])\s+", text):
        stripped = part.strip()
        if stripped:
            start = text.find(stripped, cursor)
            bounds.append((start, start + len(stripped), len(encoding.encode(stripped))))
            cursor = start + len(stripped)
    chunks = []
    start = 0
    while start < len(bounds):
        end = start
        tokens = 0
        while end < len(bounds):
            needed = bounds[end][2] + (1 if end > start else 0)
            if tokens + needed > config["chunkTokens"]:
                break
            tokens += needed
            end += 1
        if end == start:
            end = start + 1
            tokens = bounds[start][2]
        left, right = bounds[start][0], bounds[end - 1][1]
        related = [block for block in document["blocks"] if block["startOffset"] < right and block["endOffset"] > left]
        chunks.append({
            "id": "chunk:" + fingerprint([scope, left, right]),
            "ordinal": len(chunks) + 1, "text": text[left:right],
            "startOffset": left, "endOffset": right, "tokenCount": tokens,
            "offsetUnit": "unicode_code_point", "blockOrdinals": [block["ordinal"] for block in related],
            "sourceLocations": [block["location"] for block in related],
            "oversizedSentence": tokens > config["chunkTokens"],
        })
        if end >= len(bounds):
            break
        start = max(end - config["overlapSentences"], start + 1)
    return {"chunks": chunks, "strategy": "sentence_token_cap", "upstream": UPSTREAM, "upstreamVersion": "v1.4.0", "adaptation": "Greedy sentence windows and SDK token accounting retained; original normalized whitespace retained for exact citation offsets rather than rejoining with spaces."}
