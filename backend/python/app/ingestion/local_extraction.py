import time

from .extraction import source_span
from .local_models import relex_many
from .providers import Providers
from .relation_schema import endpoint_types_allowed, relation_constraints
from .semantic_context import relation_scope, sentence_context, source_context, valid_entity_mention
from .native_records import extract_native_chunk
from .extraction_context import contextual_input, remove_context


def prose_segments(document, chunk):
    if "codeGraph" not in document:
        return [(0, chunk["text"])]
    segments = []
    for span in document["codeGraph"].get("prose", []):
        left = max(span["start"], chunk["startOffset"])
        right = min(span["end"], chunk["endOffset"])
        if left < right:
            local = left - chunk["startOffset"]
            segments.append((local, chunk["text"][local:local + right - left]))
    return segments


def convert_output(chunk, result, offset=0, constraints=None):
    entities = []
    positions = {}
    types_by_key = {}
    for item in result["entities"]:
        start, end = item["start"] + offset, item["end"] + offset
        if chunk["text"][start:end] != item["text"]:
            raise ValueError("Local extractor entity offsets do not match the source")
        if not valid_entity_mention(item["text"], item.get("label"), chunk["text"]):
            continue
        key = "local_" + str(offset) + "_" + str(len(entities))
        positions[(item["start"], item["end"])] = key
        types_by_key[key] = item["label"]
        span = source_span(chunk, start, end)
        entities.append({"key": key, "name": item["text"], "entity_type": item["label"], "description": "", "quote": item["text"], "confidence": float(item["score"]), "sourceSpan": span, "sourceSpans": [span], "sourceSpanStatus": "exact", "extractionMethod": "gliner_relex", "llmVerified": False})
    relations = []
    for edge in result["relationships"]:
        subject = positions.get((edge["head"]["start"], edge["head"]["end"]))
        target = positions.get((edge["tail"]["start"], edge["tail"]["end"]))
        if not subject or not target or subject == target:
            continue
        if not endpoint_types_allowed(edge["relation"], types_by_key[subject], types_by_key[target], constraints or {}):
            continue
        left = offset + min(edge["head"]["start"], edge["tail"]["start"])
        right = offset + max(edge["head"]["end"], edge["tail"]["end"])
        context_start, context_end, context = sentence_context(chunk["text"], left, right)
        span = source_span(chunk, context_start, context_end)
        relations.append({"subject": subject, "predicate": edge["relation"], "object": target, "quote": context, **source_context(context), **relation_scope(chunk["text"], left, right, context), "confidence": float(edge["score"]), "sourceSpan": span, "sourceSpans": [span], "sourceSpanStatus": "exact", "extractionMethod": "gliner_relex", "llmVerified": False})
    return {"entities": entities, "relationships": relations}


def extract_local(pipeline, job):
    document = pipeline.artifact(job["id"], "normalize")
    profile = pipeline.artifact(job["id"], "configure")
    constraints = relation_constraints(job["configuration"].get("categories", []))
    counts = {"entities": 0, "relationships": 0}
    chunks = pipeline.artifact(job['id'], 'chunk')['chunks']
    if document.get("metadata", {}).get("parser") == "stix_native_json":
        known_objects = {block["structured"]["nativeRecordId"]: block["structured"]["nativeRecord"] for block in document["blocks"] if block.get("structured", {}).get("nativeRecord")}
        native_warnings = []
        unpublished_relationships = 0
        for chunk in chunks:
            def native_operation(c=chunk):
                native = extract_native_chunk(c, document, known_objects, chunks)
                return {"entities": native["entities"], "relationships": native["relationships"], "metadata": {"method": "stix_native", "windows": 0, "llmVerified": False, "fallback": False, "extractionLlmCalls": 0, "scoreMeaning": "Native STIX object identifiers and relationship references; no model score", "nativeWarnings": native["warnings"], "unpublishedRelationships": native["unpublishedRelationships"]}}
            output = pipeline.retry_call(job, "extract", chunk["id"], native_operation, max_attempts=1)
            pipeline.validate_extraction(chunk, output)
            native_warnings.extend(output.get("metadata", {}).get("nativeWarnings", []))
            unpublished_relationships += output.get("metadata", {}).get("unpublishedRelationships", 0)
            for key in counts:
                counts[key] += len(output[key])
        return {**counts, "quality": "native_structured", "method": "stix_native", "extractionLlmCalls": 0, "fallbackChunks": 0, "warnings": [*document.get("metadata", {}).get("warnings", []), *native_warnings], "unpublishedRelationships": unpublished_relationships, "nativeRecordCount": document.get("metadata", {}).get("nativeRecordCount", 0), "danglingReferenceCount": document.get("metadata", {}).get("danglingReferenceCount", 0)}
    for first in range(0, len(chunks), 16):
        batch = chunks[first:first + 16]
        pending = [chunk for chunk in batch if pipeline.item(job['id'], 'extract', chunk['id']) is None]
        segments_by_chunk = {chunk['id']: prose_segments(document, chunk) for chunk in pending}
        owners = [(chunk['id'], *contextual_input(chunk, text)) for chunk in pending for _, text in segments_by_chunk[chunk['id']]]
        pipeline.check_paused(job['id'])
        inference_started = time.monotonic()
        predictions = relex_many([text for _, text, _ in owners], profile, job['configuration']) if owners else []
        inference_ms = (time.monotonic() - inference_started) * 1000
        predictions_by_chunk = {chunk['id']: [] for chunk in pending}
        for (identifier, _, prefix), prediction in zip(owners, predictions, strict=True):
            predictions_by_chunk[identifier].append(remove_context(prediction, prefix))
        pipeline.check_paused(job['id'])
        for chunk in batch:
            def operation(c=chunk):
                started = time.monotonic()
                output = {"entities": [], "relationships": []}
                windows = 0
                segments = prose_segments(document, c)
                predictions = predictions_by_chunk[c["id"]]
                for (offset, text), raw in zip(segments, predictions, strict=True):
                    converted = convert_output(c, raw, offset, constraints)
                    output["entities"].extend(converted["entities"])
                    output["relationships"].extend(converted["relationships"])
                    windows += len(raw["windows"])
                initial = pipeline.item(job['id'], 'local_ner', c['id']) or {}
                retained = {(entity['sourceSpan']['chunkStart'], entity['sourceSpan']['chunkEnd']) for entity in output['entities']}
                for mention in initial.get('mentions', []):
                    start, end = mention['start'], mention['end']
                    if (start, end) in retained:
                        continue
                    quote = c['text'][start:end]
                    if not quote or quote != mention['text']:
                        raise ValueError('Initial GLiNER mention offsets do not match the source')
                    if not valid_entity_mention(quote, mention['label'], c['text']):
                        continue
                    span = source_span(c, start, end)
                    output['entities'].append({'key': 'early_' + str(len(output['entities'])), 'name': quote, 'entity_type': mention['label'], 'description': '', 'quote': quote, 'confidence': float(mention['score']), 'sourceSpan': span, 'sourceSpans': [span], 'sourceSpanStatus': 'exact', 'extractionMethod': 'gliner', 'llmVerified': False})
                    retained.add((start, end))
                output["metadata"] = {"method": "gliner_relex" if windows else "python_ast_structure", "model": job["configuration"]["relexModel"], "llmVerified": False, "fallback": False, "llmAttempts": 0, "windows": windows, "durationMs": (time.monotonic() - started) * 1000, "sharedInferenceDurationMs": inference_ms, "inferenceBatchChunks": len(pending), "scoreMeaning": "Uncalibrated local model score; source offsets and structure are checked, semantic correctness is not independently verified"}
                output['metadata']['memoryWindowSplit'] = any(raw.get('memoryWindowSplit') for raw in predictions)
                output['metadata']['localAdapter'] = next((raw.get('localAdapter') for raw in predictions if raw.get('localAdapter')), None)
                output['metadata']['spanCandidates'] = [value for raw in predictions for value in raw.get('spanCandidates', [])]
                output['metadata']['spanCandidateLimit'] = job['configuration'].get('relexMaxSpans', 64)
                output['metadata']['candidateLimitMeaning'] = 'Ranked internal span beam before quadratic relation pairing; may reduce relation recall. Scores are uncalibrated.'
                pipeline.validate_extraction(c, output)
                return output
            output = pipeline.retry_call(job, "extract", chunk["id"], operation, max_attempts=1)
            for key in counts:
                counts[key] += len(output[key])
    graph = document.get("codeGraph", {})
    return {**counts, "structuralEntities": len(graph.get("entities", [])), "structuralRelationships": len(graph.get("relationships", [])), "quality": "local_model_and_parser", "method": "gliner_relex_plus_format_parser", "extractionLlmCalls": 0, "fallbackChunks": 0, "warnings": [], "entityTypes": profile["entityTypes"]}


def extract_early_mentions(pipeline, job):
    from .categories import seed_settings
    document = pipeline.artifact(job["id"], "normalize")
    graph = document.get("codeGraph")
    if graph is not None:
        return {"entities": len(graph["entities"]), "method": "python_ast", "llmCalls": 0}
    if document.get("metadata", {}).get("parser") == "stix_native_json":
        return {"entities": 0, "method": "stix_native", "llmCalls": 0}
    config = job["configuration"]
    types = seed_settings(config["categories"])["entityTypes"]
    provider = Providers(config, stop_check=lambda: pipeline.check_paused(job["id"]))
    count = 0
    chunks = pipeline.artifact(job['id'], 'chunk')['chunks']
    for first in range(0, len(chunks), 16):
        batch = chunks[first:first + 16]
        pending = [chunk for chunk in batch if pipeline.item(job['id'], 'local_ner', chunk['id']) is None]
        found = provider.gliner_many([chunk['text'] for chunk in pending], types) if pending else []
        predictions = {chunk['id']: value for chunk, value in zip(pending, found, strict=True)}
        for chunk in batch:
            result = pipeline.retry_call(job, 'local_ner', chunk['id'], lambda c=chunk: predictions[c['id']], max_attempts=1)
            count += len(result['mentions'])
    return {'entities': count, 'method': 'gliner', 'llmCalls': 0, 'entityTypes': types}
