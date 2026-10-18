SDK_VERIFY_EXTRACT_PROMPT = """You are an expert knowledge graph builder.
Given the text and pre-extracted entities below, do two things:
Verify the proposed entities against the source: remove false positives, correct names, and identify missed entities. Describe each entity using only its own source-supported attributes and roles. Preserve distinctions between similarly named entities using identifiers, scope, place, role or date when supplied. Never transfer one entity's properties to another.
Extract the supported connections between the verified entities, covering the source rather than selecting only a summary. Relationship endpoints must refer to entities in the returned result. Make descriptions understandable in their own context and retain where the source supports each connection.
Use the application-supplied structured output schema and source-grounding requirements. In this adaptation, endpoints use local entity keys, quotations are exact source substrings, conditions retain literal values, and relationships require explicit source support rather than implication alone. The JSON request supplies entity types, proposed mentions, source text and task instructions."""

SDK_PROMPT_SOURCE = 'https://github.com/FalkorDB/GraphRAG-SDK/blob/35e67a0b27fdcc7f2c28508b09e86169851a8187/graphrag_sdk/src/graphrag_sdk/ingestion/extraction_strategies/graph_extraction.py'
