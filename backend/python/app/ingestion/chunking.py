import re

import tiktoken

from .config import fingerprint


UPSTREAM = "https://github.com/FalkorDB/GraphRAG-SDK/blob/v1.4.0/graphrag_sdk/src/graphrag_sdk/ingestion/chunking_strategies/sentence_token_cap.py"


def chunk_document(document, scope, config):
    encoding = tiktoken.get_encoding(config["tokenEncoding"])
    text = document["text"]
    bounds = []
    parser = document.get("metadata", {}).get("parser")
    code = parser in {"python_ast", "source_text"}
    native_records = parser == "stix_native_json"
    for block in document.get("blocks", []):
        block_start, block_end = block["startOffset"], block["endOffset"]
        content = text[block_start:block_end]
        if code or block.get("kind") in {"heading", "table", "record", "citation", "preformatted", "code", "list_item"}:
            parts = [content]
        else:
            parts = re.split(r"(?<=[.!?;])\s+", content)
        local_cursor = 0
        for part in parts:
            stripped = part.strip()
            if stripped:
                relative = content.find(stripped, local_cursor)
                start = block_start + relative
                end = start + len(stripped)
                local_cursor = relative + len(stripped)
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
    chunks = []
    heading_offsets = {block['startOffset'] for block in document.get('blocks', []) if block['kind'] == 'heading'}
    start = 0
    while start < len(bounds):
        end = start
        tokens = 0
        while end < len(bounds):
            if end > start and bounds[end][0] in heading_offsets:
                break
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
            "sourceContext": [{"kind": block["kind"], "role": block.get("role", "content"), "location": block["location"], "startOffset": block['startOffset'], "endOffset": block['endOffset'], "structured": block.get("structured")} for block in related],
            "headingContext": next((block['location']['sectionPath'] for block in related if block.get('location', {}).get('sectionPath')), []),
            "actualTokenCount": len(encoding.encode(text[left:right], disallowed_special=())),
            "oversizedSentence": tokens > config["chunkTokens"],
        })
        if end >= len(bounds):
            break
        start = end if native_records or bounds[end][0] in heading_offsets else max(end - config["overlapSentences"], start + 1)
    return {"chunks": chunks, "strategy": "code_line_token_cap" if code else "structure_sentence_clause_token_cap", "upstream": UPSTREAM, "upstreamVersion": "v1.4.0", "adaptation": "Code uses source lines; prose is segmented within parser blocks at sentence and semicolon-clause boundaries. Headings, tables, records, citations, preformatted blocks and list items remain intact unless they exceed the token cap. Oversized units split at source character boundaries. Normalized whitespace retained for exact citation offsets."}
