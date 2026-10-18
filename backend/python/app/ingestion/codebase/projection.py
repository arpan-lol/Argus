from ..config import fingerprint
from ..extraction import source_span
from ..semantic_context import source_context


def project_claims(pipeline, job, result):
    chunks = pipeline.artifact(job['id'], 'chunk')['chunks']
    outputs = {chunk['id']: {'entities': [], 'relationships': []} for chunk in chunks}
    by_id = {chunk['id']: chunk for chunk in chunks}
    coverage = next((row for row in result['coverage'] if row['sourceId'] == job['source_id']), {'status': 'not_inspected'})

    def entity_for(key, citation):
        entity = result['entities'][key]
        chunk = by_id[citation['chunk_id']]
        local = 'codebase_' + fingerprint([key, citation['start'], citation['end']])[:24]
        output = outputs[chunk['id']]
        if not any(row['key'] == local for row in output['entities']):
            span = source_span(chunk, citation['start'], citation['end'])
            output['entities'].append({'key': local, 'name': entity['name'], 'entity_type': entity['entity_type'], 'description': entity['description'], 'quote': citation['quote'], 'sourceSpan': span, 'sourceSpans': [span], 'sourceSpanStatus': 'exact', 'extractionMethod': 'codebase_graph_builder', 'llmVerified': False, 'codeResolverKey': key, 'referenceMeaning': 'Source-supported software concept; quote is supporting context, not necessarily a verbatim entity name'})
        return local

    seen_claims = set()
    for claim in result['claims']:
        citation = claim['citation']
        if citation['source_id'] != job['source_id']:
            continue
        if claim['kind'] == 'entity':
            signature = ('entity', claim['entity']['key'], citation['source_id'], citation['startOffset'], citation['endOffset'])
        else:
            relation = claim['relationship']
            signature = ('relationship', relation['subject'], relation['predicate'], relation['object'], relation['polarity'], citation['source_id'], citation['startOffset'], citation['endOffset'])
        if signature in seen_claims:
            continue
        seen_claims.add(signature)
        if citation['revision'] != job['revision']:
            raise ValueError('Codebase builder citation belongs to another source revision')
        if citation['chunk_id'] not in by_id:
            remapped = next((chunk for chunk in chunks if chunk['startOffset'] <= citation['startOffset'] and chunk['endOffset'] >= citation['endOffset']), None)
            if remapped is None:
                raise ValueError('Codebase delivery cannot preserve the exact supporting source range')
            citation = {**citation, 'chunk_id': remapped['id'], 'start': citation['startOffset'] - remapped['startOffset'], 'end': citation['endOffset'] - remapped['startOffset']}
        chunk = by_id[citation['chunk_id']]
        if chunk['text'][citation['start']:citation['end']] != citation['quote']:
            raise ValueError('Codebase builder citation changed before projection')
        if claim['kind'] == 'entity':
            entity_for(claim['entity']['key'], citation)
        else:
            relation = claim['relationship']
            subject = entity_for(relation['subject'], citation)
            target = entity_for(relation['object'], citation)
            span = source_span(chunk, citation['start'], citation['end'])
            context = source_context(citation['quote'])
            review = context['traversalStatus'] == 'needs_context_review' or relation['polarity'] != 'affirmed'
            polarity = 'uncertain' if relation['polarity'] == 'conditional' else relation['polarity']
            outputs[chunk['id']]['relationships'].append({'subject': subject, 'predicate': relation['predicate'].lower(), 'object': target, 'quote': citation['quote'], 'conditions': [], **context, 'polarity': polarity, 'agentPolarity': relation['polarity'], 'polarityStatus': 'agent_classified_not_independently_verified', 'traversalStatus': 'needs_context_review' if review else 'unverified_no_context_cue', 'sourceSpan': span, 'sourceSpans': [span], 'sourceSpanStatus': 'exact', 'extractionMethod': 'codebase_graph_builder', 'llmVerified': False, 'agentExplanation': relation['explanation'], 'codebaseRunId': result['runId']})

    counts = {'entities': 0, 'relationships': 0}
    for chunk in chunks:
        output = outputs[chunk['id']]
        output['metadata'] = {'method': 'codebase_graph_builder', 'runId': result['runId'], 'quality': result['quality'], 'coverage': coverage, 'stopReason': result['stopReason'], 'fallback': False, 'llmVerified': False, 'limitations': result['limitations'], 'sharedWorkspaceSteps': result['steps'], 'scoreMeaning': 'No probability score; agent-generated behavior with validated source references'}
        pipeline.validate_extraction(chunk, output)
        pipeline.save_item(job['id'], 'extract', chunk['id'], output)
        for key in counts:
            counts[key] += len(output[key])
    pipeline.save_item(job['id'], 'codebase_summary', 'current', {'runId': result['runId'], 'coverage': coverage, 'quality': result['quality'], 'stopReason': result['stopReason'], 'steps': result['steps']})
    return {**counts, 'method': 'codebase_graph_builder', 'codebaseRunId': result['runId'], 'quality': result['quality'], 'coverage': coverage, 'steps': result['steps'], 'fallbackChunks': 0, 'stopReason': result['stopReason'], 'warnings': result['limitations']}
