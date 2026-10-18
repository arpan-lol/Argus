import re

import tiktoken

from .config import fingerprint


UPSTREAM = "https://github.com/FalkorDB/GraphRAG-SDK/blob/v1.4.0/graphrag_sdk/src/graphrag_sdk/ingestion/chunking_strategies/sentence_token_cap.py"


def chunk_document(document, scope, config):
    encoding = tiktoken.get_encoding(config["tokenEncoding"])
    text = document["text"]
    bounds = []
    cursor = 0
    code = document.get("metadata", {}).get("parser") in {"python_ast", "source_text"}
    parts = text.splitlines(keepends=True) if code else re.split(r"(?<=[.!?])\s+", text)
    for part in parts:
        stripped = part.strip()
        if stripped:
            start = text.find(stripped, cursor)
            end = start + len(stripped)
            while start < end:
                tokens = len(encoding.encode(text[start:end], disallowed_special=()))
                if tokens <= config["chunkTokens"]:
                    bounds.append((start, end, tokens))
                    break
                low, high = start + 1, end
                while low < high:
                    middle = (low + high + 1) // 2
                    if len(encoding.encode(text[start:middle], disallowed_special=())) <= config["chunkTokens"]:
                        low = middle
                    else:
                        high = middle - 1
                bounds.append((start, low, len(encoding.encode(text[start:low], disallowed_special=()))))
                start = low
            cursor = end
    chunks = []
    start = 0
    while start < len(bounds):
        end = start
        tokens = 0
        while end < len(bounds):
            needed = len(encoding.encode(text[bounds[start][0]:bounds[end][1]], disallowed_special=()))
            if needed > config["chunkTokens"]:
                break
            tokens = needed
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
            "sourceContext": [{"kind": block["kind"], "role": block.get("role", "content"), "location": block["location"]} for block in related],
            "actualTokenCount": len(encoding.encode(text[left:right], disallowed_special=())),
            "oversizedSentence": tokens > config["chunkTokens"],
        })
        if end >= len(bounds):
            break
        start = max(end - config["overlapSentences"], start + 1)
    return {"chunks": chunks, "strategy": "code_line_token_cap" if code else "sentence_token_cap", "upstream": UPSTREAM, "upstreamVersion": "v1.4.0", "adaptation": "Code uses source lines; prose uses sentence windows. Oversized units split at source character boundaries. Normalized whitespace retained for exact citation offsets."}
