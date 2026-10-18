# FalkorDB GraphRAG SDK adaptation

`app/ingestion/chunking.py` adapts the sentence boundary, greedy token accounting, oversized-sentence policy, and overlap algorithm from FalkorDB GraphRAG SDK v1.4.0, copyright 2026 FalkorDB, licensed under Apache License 2.0. The complete upstream license accompanies this notice.

Upstream source: https://github.com/FalkorDB/GraphRAG-SDK/blob/v1.4.0/graphrag_sdk/src/graphrag_sdk/ingestion/chunking_strategies/sentence_token_cap.py

Argus modifications: retains normalized source whitespace rather than joining sentence strings, adds exact source offsets, deterministic revision/processing identities, block locations, and an oversized-sentence indicator. The upstream SDK is not installed or represented as the orchestrator; Argus uses the adapted chunking algorithm inside its own LangGraph workflow.

`app/ingestion/sdk_prompts.py` adapts the verification/extraction prompt from FalkorDB GraphRAG SDK commit `35e67a0b27fdcc7f2c28508b09e86169851a8187`, Apache License 2.0. Argus changes: structured schema uses entity keys and exact quotations; source-only conditions, negation, task context and explicit support remain mandatory. The adapted instructions do not adopt upstream implied-relationship extraction.

Source: https://github.com/FalkorDB/GraphRAG-SDK/blob/35e67a0b27fdcc7f2c28508b09e86169851a8187/graphrag_sdk/src/graphrag_sdk/ingestion/extraction_strategies/graph_extraction.py

`app/ingestion/sdk_resolution.py` implements the documented basic normalized-name/type grouping semantics inside Argus's source-record contract. It is an adapter, not an invocation of SDK finalize or its optional LLM deduplicator. Ambiguous identical names can be overmerged in basic mode; the optional custom paired-judgment mode remains available.
