# FalkorDB GraphRAG SDK adaptation

`app/ingestion/chunking.py` adapts the sentence boundary, greedy token accounting, oversized-sentence policy, and overlap algorithm from FalkorDB GraphRAG SDK v1.4.0, copyright 2026 FalkorDB, licensed under Apache License 2.0. The complete upstream license accompanies this notice.

Upstream source: https://github.com/FalkorDB/GraphRAG-SDK/blob/v1.4.0/graphrag_sdk/src/graphrag_sdk/ingestion/chunking_strategies/sentence_token_cap.py

Argus modifications: retains normalized source whitespace rather than joining sentence strings, adds exact source offsets, deterministic revision/processing identities, block locations, and an oversized-sentence indicator. The upstream SDK is not installed or represented as the orchestrator; Argus uses the adapted chunking algorithm inside its own LangGraph workflow.
