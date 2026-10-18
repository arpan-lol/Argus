import time

from .extraction import source_span
from .local_models import relex_many
from .providers import Providers


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


def convert_output(chunk, result, offset=0):
    entities = []
    positions = {}
    for item in result["entities"]:
        start, end = item["start"] + offset, item["end"] + offset
        if chunk["text"][start:end] != item["text"]:
            raise ValueError("Local extractor entity offsets do not match the source")
        key = "local_" + str(offset) + "_" + str(len(entities))
        positions[(item["start"], item["end"])] = key
        span = source_span(chunk, start, end)
        entities.append({"key": key, "name": item["text"], "entity_type": item["label"], "description": "", "quote": item["text"], "confidence": float(item["score"]), "sourceSpan": span, "sourceSpans": [span], "sourceSpanStatus": "exact", "extractionMethod": "gliner_relex", "llmVerified": False})
    relations = []
    for edge in result["relationships"]:
        subject = positions.get((edge["head"]["start"], edge["head"]["end"]))
        target = positions.get((edge["tail"]["start"], edge["tail"]["end"]))
        if not subject or not target or subject == target:
            continue
        left = offset + min(edge["head"]["start"], edge["tail"]["start"])
        right = offset + max(edge["head"]["end"], edge["tail"]["end"])
        boundary = chunk["text"].rfind(". ", 0, left)
        left = boundary + 2 if boundary >= 0 else 0
        ending = chunk["text"].find(". ", right)
        right = ending + 1 if ending >= 0 else len(chunk["text"])
        span = source_span(chunk, left, right)
        relations.append({"subject": subject, "predicate": edge["relation"], "object": target, "quote": chunk["text"][left:right], "conditions": [], "polarity": "unclassified", "confidence": float(edge["score"]), "sourceSpan": span, "sourceSpans": [span], "sourceSpanStatus": "exact", "extractionMethod": "gliner_relex", "llmVerified": False, "polarityStatus": "not_classified_by_local_model"})
    return {"entities": entities, "relationships": relations}


def extract_local(pipeline, job):
    document = pipeline.artifact(job["id"], "normalize")
    profile = pipeline.artifact(job["id"], "configure")
    counts = {"entities": 0, "relationships": 0}
    for chunk in pipeline.artifact(job["id"], "chunk")["chunks"]:
        def operation(c=chunk):
            started = time.monotonic()
            output = {"entities": [], "relationships": []}
            windows = 0
            segments = prose_segments(document, c)
            predictions = relex_many([text for _, text in segments], profile, job['configuration']) if segments else []
            for (offset, text), raw in zip(segments, predictions, strict=True):
                converted = convert_output(c, raw, offset)
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
                span = source_span(c, start, end)
                output['entities'].append({'key': 'early_' + str(len(output['entities'])), 'name': quote, 'entity_type': mention['label'], 'description': '', 'quote': quote, 'confidence': float(mention['score']), 'sourceSpan': span, 'sourceSpans': [span], 'sourceSpanStatus': 'exact', 'extractionMethod': 'gliner', 'llmVerified': False})
                retained.add((start, end))
            output["metadata"] = {"method": "gliner_relex" if windows else "python_ast_structure", "model": job["configuration"]["relexModel"], "llmVerified": False, "fallback": False, "llmAttempts": 0, "windows": windows, "durationMs": (time.monotonic() - started) * 1000, "scoreMeaning": "Uncalibrated local model score; source offsets and structure are checked, semantic correctness is not independently verified"}
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
    config = job["configuration"]
    types = seed_settings(config["categories"])["entityTypes"]
    provider = Providers(config)
    count = 0
    for chunk in pipeline.artifact(job["id"], "chunk")["chunks"]:
        found = pipeline.retry_call(job, "local_ner", chunk["id"], lambda c=chunk: provider.gliner(c["text"], types), max_attempts=1)
        count += len(found["mentions"])
    return {"entities": count, "method": "gliner", "llmCalls": 0, "entityTypes": types}
