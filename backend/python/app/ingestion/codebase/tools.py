import hashlib
import json
from collections import OrderedDict

import tiktoken

from app.database import connection
from ..chunking import chunk_document
from ..parsers import normalize
from ..parser_routing import parse_source
from ..profiles import source_quality
from . import storage


class RepositoryTools:
    def __init__(self, pipeline, job, manifest, changed=None):
        self.pipeline, self.job = pipeline, job
        self.project = job['project_id']
        self.manifest = {source['source_id']: source for source in manifest}
        self.cache = OrderedDict()
        self.encoding = tiktoken.get_encoding(job['configuration']['profileTokenEncoding'])
        self.maximum = job['configuration']['profileBatchTokens']
        self.changed = set(self.manifest if changed is None else changed)

    def present(self, identifier, chunk):
        first_line = self.source(identifier)['document']['text'].count('\n', 0, chunk['startOffset']) + 1
        lines = [{'line': number, 'text': line.rstrip('\r\n')} for number, line in enumerate(chunk['text'].splitlines(keepends=True), first_line)]
        return {'source_id': identifier, 'filename': self.manifest[identifier]['filename'], 'chunk_id': chunk['id'], 'lines': lines, 'ordinal': chunk['ordinal']}

    def source(self, identifier):
        if identifier not in self.manifest:
            raise ValueError('Source is outside this workspace snapshot')
        if identifier not in self.cache:
            row = self.manifest[identifier]
            document = self.pipeline.artifact(row['id'], 'normalize')
            if document is None:
                from pathlib import Path
                if hashlib.sha256(Path(row['original_path']).read_bytes()).hexdigest() != row['revision']:
                    raise ValueError('Original source digest changed')
                document = source_quality(normalize(parse_source(row['original_path'], row['configuration'], row['filename'])))
            chunks = self.pipeline.artifact(row['id'], 'chunk')
            if chunks is None:
                chunks = chunk_document(document, [row['source_id'], row['revision'], row['processing_version']], row['configuration'])
            while self.cache and sum(len(value['document']['text']) for value in self.cache.values()) + len(document['text']) > 4000000:
                self.cache.popitem(last=False)
            self.cache[identifier] = {'document': document, 'chunks': chunks['chunks']}
        self.cache.move_to_end(identifier)
        return self.cache[identifier]

    def citation(self, citation, seen):
        citation = dict(citation)
        source = self.source(citation['source_id'])
        lines = source['document']['text'].splitlines(keepends=True)
        number = citation['line']
        if number > len(lines):
            raise ValueError('Citation line is outside the source file')
        absolute_start = sum(len(line) for line in lines[:number - 1])
        quote = lines[number - 1].rstrip('\r\n')
        if not quote.strip():
            raise ValueError('Citation cannot select an empty source line')
        absolute_end = absolute_start + len(quote)
        chunk = next((item for item in source['chunks'] if item['id'] in seen and item['startOffset'] <= absolute_start and item['endOffset'] >= absolute_end), None)
        if chunk is None:
            raise ValueError('Citation line must be contained in a chunk returned by read_sources or search_sources')
        return {**citation, 'chunk_id': chunk['id'], 'quote': quote, 'start': absolute_start - chunk['startOffset'], 'end': absolute_end - chunk['startOffset'], 'revision': self.manifest[citation['source_id']]['revision'], 'startOffset': absolute_start, 'endOffset': absolute_end}

    def execute(self, action, state):
        tool = action['tool']
        seen = list(state.get('seen', []))
        claims = list(state.get('claims', []))
        staged = dict(state.get('entities', {}))
        result = {}
        if tool == 'list_files':
            sources = list(self.manifest.values())
            start = action['cursor']
            result = {'files': [{'source_id': row['source_id'], 'filename': row['filename'], 'revision': row['revision'], 'changed_or_incomplete': row['source_id'] in self.changed} for row in sources[start:start + 60]], 'next_cursor': start + 60 if start + 60 < len(sources) else None, 'total': len(sources)}
        elif tool == 'read_sources':
            result = {'chunks': [], 'sources': []}
            tokens = 0
            for identifier in action['source_ids']:
                source = self.source(identifier)
                offset = action['chunk_offset']
                returned = 0
                for chunk in source['chunks'][offset:offset + 4]:
                    presented = self.present(identifier, chunk)
                    count = len(self.encoding.encode(json.dumps(presented, ensure_ascii=False), disallowed_special=()))
                    if count > self.maximum:
                        raise ValueError('Source chunk exceeds the fixed tool response budget; reduce the configured chunk size before retrying')
                    if tokens + count > self.maximum:
                        break
                    tokens += count
                    returned += 1
                    result['chunks'].append(presented)
                    if chunk['id'] not in seen:
                        seen.append(chunk['id'])
                result['sources'].append({'source_id': identifier, 'total_chunks': len(source['chunks']), 'next_chunk_offset': offset + returned if offset + returned < len(source['chunks']) else None})
        elif tool == 'search_sources':
            if not action['query'].strip():
                raise ValueError('search_sources requires a literal text query')
            matches = []
            tokens = 0
            for identifier in self.manifest:
                self.pipeline.check_paused(self.job['id'])
                for chunk in self.source(identifier)['chunks']:
                    if action['query'].casefold() not in chunk['text'].casefold():
                        continue
                    presented = self.present(identifier, chunk)
                    count = len(self.encoding.encode(json.dumps(presented, ensure_ascii=False), disallowed_special=()))
                    if tokens + count > self.maximum or len(matches) >= 12:
                        result = {'chunks': matches, 'truncated': True}
                        return result, seen, claims, staged
                    tokens += count
                    matches.append(presented)
                    if chunk['id'] not in seen:
                        seen.append(chunk['id'])
            result = {'chunks': matches, 'truncated': False}
        elif tool == 'find_entities':
            result = {'entities': [{key: item[key] for key in ('key', 'name', 'entity_type', 'description')} for item in storage.find_entities(self.project, action['query'])], 'meaning': 'Existing concept identities for reuse, not verified behavior facts'}
        elif tool == 'write_graph':
            entities = [{**item, 'citation': self.citation(item['citation'], seen)} for item in action['entities']]
            known = {**staged, **{item['key']: item for item in entities}}
            relations = []
            for relation in action['relationships']:
                if relation['subject'] == relation['object']:
                    raise ValueError('Self relationships are not useful codebase graph writes')
                for key in (relation['subject'], relation['object']):
                    if key not in known:
                        with connection() as conn:
                            row = conn.execute('SELECT payload FROM ingestion_codebase_entities WHERE project_id=%s AND entity_key=%s', (self.project, key)).fetchone()
                        if not row:
                            raise ValueError('Unknown endpoint key: ' + key + '; find or create the entity first')
                        known[key] = row['payload']
                relations.append({**relation, 'citation': self.citation(relation['citation'], seen)})
            with connection() as lease:
                lease.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('codebase-entities:' + self.project,))
                for entity in entities:
                    storage.save_entity(self.project, entity, lease)
            staged.update(known)
            for item in entities:
                claim = {'kind': 'entity', 'entity': item, 'citation': item['citation']}
                if claim not in claims:
                    claims.append(claim)
            for relation in relations:
                claim = {'kind': 'relationship', 'relationship': relation, 'citation': relation['citation']}
                if claim not in claims:
                    claims.append(claim)
            result = {'accepted_entities': len(entities), 'accepted_relationships': len(relations), 'identities': [{key: item[key] for key in ('key', 'name', 'entity_type')} for item in entities], 'publication': 'Validated staging; each file publishes through the shared ingestion lifecycle', 'validation': 'Exact source support and typed endpoints, not independent semantic verification'}
        elif tool == 'finish':
            result = {'finished': True, 'summary': action['reason']}
        else:
            raise ValueError('Unsupported tool')
        return result, seen, claims, staged

    def coverage(self, seen):
        output = []
        for identifier, row in self.manifest.items():
            cached = self.cache.get(identifier)
            if cached is None and seen:
                try:
                    cached = self.source(identifier)
                except (ValueError, OSError, SyntaxError):
                    cached = None
            if cached is None:
                output.append({'sourceId': identifier, 'filename': row['filename'], 'readChunks': 0, 'totalChunks': None, 'status': 'not_inspected'})
                continue
            chunks = cached['chunks']
            read = sum(chunk['id'] in seen for chunk in chunks)
            output.append({'sourceId': identifier, 'filename': row['filename'], 'readChunks': read, 'totalChunks': len(chunks), 'status': 'read' if read == len(chunks) else 'partially_inspected' if read else 'not_inspected'})
        return output
