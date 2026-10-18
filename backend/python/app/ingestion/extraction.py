def source_span(chunk, start, end):
    return {
        "chunkStart": start,
        "chunkEnd": end,
        "startOffset": chunk["startOffset"] + start,
        "endOffset": chunk["startOffset"] + end,
        "offsetUnit": "unicode_code_point",
    }
