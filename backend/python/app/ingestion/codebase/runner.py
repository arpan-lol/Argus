import json
import math
import time
from typing import TypedDict

import tiktoken
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg.types.json import Jsonb

from app.config import settings
from app.database import connection
from app.projects.events import job_event
from ..config import fingerprint
from ..providers import Providers
from . import selected, storage
from .contracts import Action, SYSTEM
from .tools import RepositoryTools


class BuilderState(TypedDict):
    step: int
    history: list
    action: dict
    seen: list
    claims: list
    entities: dict
    done: bool
    stop_reason: str


def manifest_for(job):
    with connection() as conn:
        rows = conn.execute("SELECT DISTINCT ON (j.source_id) j.id,j.source_id,j.revision,j.processing_version,j.configuration,j.status,COALESCE(j.original_path,s.original_path) AS original_path,s.filename,s.source_url,j.created_at FROM ingestion_jobs j JOIN ingestion_sources s ON s.id=j.source_id WHERE j.project_id=%s AND NOT (j.configuration ? 'codeAgentDeliveryRunId') ORDER BY j.source_id,j.created_at DESC,j.id DESC", (job['project_id'],)).fetchall()
        profiles = conn.execute("SELECT settings FROM ingestion_profiles WHERE model_configuration->>'projectId'=%s AND settings IS NOT NULL", (job['project_id'],)).fetchall()
    profile = {'codeSourceIds': [job['source_id'], *[identifier for row in profiles for identifier in row['settings'].get('codeSourceIds', [])]]}
    result = [row for row in rows if row['status'] not in {'paused', 'failed', 'waiting_configuration', 'interrupted'} and selected(row, profile)]
    if not any(row['source_id'] == job['source_id'] for row in result):
        result.append(job)
    return sorted(result, key=lambda row: row['filename'])


class GraphBuilder:
    def __init__(self, pipeline, job, manifest, run, changed):
        self.pipeline, self.job, self.manifest, self.run = pipeline, job, manifest, run
        self.tools = RepositoryTools(pipeline, job, manifest, changed)
        self.config = job['configuration']
        self.encoding = tiktoken.get_encoding(self.config['profileTokenEncoding'])
        provider_config = {**self.config, 'maxOutputTokens': self.config.get('codeAgentOutputTokens', 4096)}
        self.provider = Providers(provider_config, self.record_call, lambda: pipeline.check_paused(job['id']))

    def record_call(self, payload):
        self.pipeline.call_recorder(self.job['id'])({**payload, 'purpose': 'codebase_graph_builder', 'codebaseRunId': self.run})

    def model(self, state):
        self.pipeline.check_paused(self.job['id'])
        if state['step'] >= self.config.get('codeAgentMaxSteps', 96):
            return {'done': True, 'stop_reason': 'step_safety_limit'}
        recent = state['history'][-3:]
        if len(recent) == 3 and (all(item['tool'] == 'list_files' for item in recent) or all('error' in item['result'] and item['result']['error'] == recent[0]['result'].get('error') for item in recent)):
            return {'done': True, 'stop_reason': 'tool_stall'}
        history = [dict(item) for item in state['history'][-8:]]
        source_reads = [index for index, item in enumerate(history) if item['tool'] in {'read_sources', 'search_sources'} and 'chunks' in item['result']]
        for index in source_reads[:-2]:
            item = history[index]
            history[index] = {**item, 'result': {**item['result'], 'chunks': [{key: chunk[key] for key in ('source_id', 'filename', 'chunk_id', 'ordinal')} for chunk in item['result']['chunks']], 'textOmitted': True}}
        payload = {'workspaceDescription': self.config.get('workspaceDescription', ''), 'workspaceId': self.job['project_id'], 'fileCount': len(self.manifest), 'filesInSnapshot': [{'source_id': row['source_id'], 'filename': row['filename']} for row in self.manifest] if len(self.manifest) <= 20 else None, 'recentTools': history, 'graphProgress': {'entities': len(state['entities']), 'claims': len(state['claims']), 'chunksRead': len(state['seen']), 'knownEntities': [{'key': key, 'name': value['name']} for key, value in list(state['entities'].items())[-32:]]}, 'instruction': 'When filesInSnapshot is present, do not list files. Read several source IDs in one action, then write source-cited entities and cross-file relationships. Copy a short exact line from citation_spans for each citation. Reuse known entity keys. Never write a self relationship or repeat a failed write unchanged.'}
        def encoded_request():
            return self.encoding.encode(json.dumps({'system': SYSTEM, 'payload': payload, 'schema': Action.model_json_schema()}, ensure_ascii=False), disallowed_special=())
        while len(encoded_request()) > self.config.get('codeAgentContextTokens', 18000) and history:
            history.pop(0)
        if len(encoded_request()) > self.config.get('codeAgentContextTokens', 18000):
            from ..providers import ConfigurationRequired
            raise ConfigurationRequired('Code agent context budget cannot fit workspace instructions and its fixed tool schema')
        reserved = math.ceil(len(encoded_request()) * 1.25) + 1024 + self.provider.config['maxOutputTokens']
        identifier = storage.reserve(self.job['project_id'], self.run, reserved, self.config.get('codeAgentTokenBudget', self.config['profileTokenBudget']))
        if identifier is None:
            return {'done': True, 'stop_reason': 'workspace_token_budget'}
        started = time.monotonic()
        try:
            action = self.provider.structured(Action, SYSTEM, payload)
        except Exception as error:
            storage.finish_call(identifier, 'failed', {'error': self.provider.safe_error(error)})
            raise
        storage.finish_call(identifier, 'complete', {'step': state['step'], 'tool': action['tool'], 'durationMs': (time.monotonic() - started) * 1000})
        return {'action': action, 'step': state['step'] + 1}

    def tool(self, state):
        self.pipeline.check_paused(self.job['id'])
        action = state['action']
        try:
            result, seen, claims, entities = self.tools.execute(action, state)
        except (ValueError, KeyError, OSError, SyntaxError) as error:
            result, seen, claims, entities = {'error': str(error)}, state['seen'], state['claims'], state['entities']
        history = [*state['history'], {'tool': action['tool'], 'reason': action['reason'], 'result': result}][-12:]
        done = action['tool'] == 'finish' and 'error' not in result
        job_event(self.job, 'codebase_tool', {'runId': self.run, 'step': state['step'], 'tool': action['tool'], 'reason': action['reason'], 'result': result})
        return {'history': history, 'seen': seen, 'claims': claims, 'entities': entities, 'done': done, 'stop_reason': action['reason'] if done else ''}

    def graph(self):
        builder = StateGraph(BuilderState)
        builder.add_node('codebase_model', self.model)
        builder.add_node('codebase_tool', self.tool)
        builder.add_edge(START, 'codebase_model')
        builder.add_conditional_edges('codebase_model', lambda state: END if state.get('done') else 'codebase_tool')
        builder.add_conditional_edges('codebase_tool', lambda state: END if state.get('done') else 'codebase_model')
        return builder


def build_workspace(pipeline, job):
    if not job.get('project_id'):
        raise ValueError('Codebase graph building requires a workspace')
    config = job['configuration']
    for key, low, high in [('codeAgentTokenBudget', 1, 100000000), ('codeAgentMaxSteps', 1, 256), ('codeAgentContextTokens', 2048, 64000), ('codeAgentOutputTokens', 512, 8192)]:
        if not low <= config.get(key, 0) <= high:
            raise ValueError(f'{key} must be between {low} and {high}')
    storage.ensure()
    with connection() as lease:
        notified = False
        while not lease.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok', ('codebase-run:' + job['project_id'],)).fetchone()['ok']:
            lease.rollback()
            if not notified:
                job_event(job, 'codebase_waiting', {'message': 'Sharing the active workspace graph builder; no duplicate agent is started'})
                notified = True
            pipeline.check_paused(job['id'])
            time.sleep(.25)
        lease.commit()
        try:
            manifest = manifest_for(job)
            signature = {key: job['configuration'].get(key) for key in ('codeAgentVersion', 'extractionModel', 'llmResourceIdentity', 'workspaceDescription', 'codeAgentContextTokens', 'codeAgentMaxSteps', 'codeAgentTokenBudget', 'codeAgentOutputTokens')}
            run = 'codebase:' + fingerprint([job['project_id'], [(row['source_id'], row['revision'], row['processing_version']) for row in manifest], signature])
            with connection() as conn:
                prior = conn.execute('SELECT * FROM ingestion_codebase_runs WHERE id=%s', (run,)).fetchone()
                if prior and prior['status'] == 'complete':
                    result = prior['payload']
                    result['deliveryJobs'] = queue_deliveries(pipeline, job, manifest, result)
                    storage.save_run(run, result, 'complete')
                    return result
                previous = conn.execute("SELECT manifest,payload FROM ingestion_codebase_runs WHERE project_id=%s AND status='complete' AND id<>%s ORDER BY updated_at DESC LIMIT 1", (job['project_id'], run)).fetchone()
                conn.execute('INSERT INTO ingestion_codebase_runs(id,project_id,manifest) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING', (run, job['project_id'], Jsonb([{key: row[key] for key in ('id', 'source_id', 'filename', 'revision', 'processing_version')} for row in manifest])))
            before = {row['source_id']: row for row in previous['manifest']} if previous else {}
            incomplete = {row['sourceId'] for row in previous['payload'].get('coverage', []) if row['status'] != 'read'} if previous else set()
            changed = {row['source_id'] for row in manifest if row['source_id'] in incomplete or (row['revision'], row['processing_version']) != (before.get(row['source_id'], {}).get('revision'), before.get(row['source_id'], {}).get('processing_version'))}
            unchanged = {row['source_id'] for row in manifest} - changed
            seed = previous['payload'] if previous else {}
            initial_claims = [claim for claim in seed.get('claims', []) if claim['citation']['source_id'] in unchanged]
            agent = GraphBuilder(pipeline, job, manifest, run, changed)
            with PostgresSaver.from_conn_string(settings.database_url) as saver:
                graph = agent.graph().compile(checkpointer=saver)
                options = {'recursion_limit': 2 * job['configuration'].get('codeAgentMaxSteps', 96) + 4, 'configurable': {'thread_id': run, 'checkpoint_ns': ''}}
                checkpoint = graph.get_state(options)
                initial = {'step': 0, 'history': [{'tool': 'incremental_context', 'result': {'changed_or_incomplete_files': len(changed), 'reused_claims': len(initial_claims), 'instruction': 'Prioritize changed_or_incomplete files in list_files. Read dependencies to verify behavior. Unchanged source claims are retained.'}}], 'action': {}, 'seen': seed.get('seen', []), 'claims': initial_claims, 'entities': seed.get('entities', {}), 'done': False, 'stop_reason': ''}
                if checkpoint.values and not checkpoint.next:
                    state = dict(checkpoint.values)
                else:
                    try:
                        state = graph.invoke(None if checkpoint.values else initial, options)
                    except Exception as error:
                        storage.save_run(run, {'error': agent.provider.safe_error(error), 'checkpointThreadId': run}, 'interrupted')
                        raise
            coverage = agent.tools.coverage(state['seen'])
            result = {'runId': run, 'entities': state['entities'], 'claims': state['claims'], 'seen': state['seen'], 'coverage': coverage, 'steps': state['step'], 'stopReason': state['stop_reason'], 'quality': 'partial' if any(row['status'] != 'read' for row in coverage) or state['stop_reason'] in {'workspace_token_budget', 'step_safety_limit', 'tool_stall'} else 'source_read_not_semantically_verified', 'method': 'codebase_graph_builder', 'incremental': {'changedOrIncompleteFiles': len(changed), 'reusedClaims': len(initial_claims)}, 'limitations': ['Agent-generated software behavior, not independently verified semantics', 'Read coverage is not proof of comprehensive behavior extraction']}
            new_claims = [claim for claim in result['claims'] if claim not in initial_claims]
            result['deliverySourceIds'] = sorted({claim['citation']['source_id'] for claim in new_claims} & {row['source_id'] for row in manifest if row['status'] == 'complete'})
            storage.save_run(run, result, 'complete')
            result['deliveryJobs'] = queue_deliveries(pipeline, job, manifest, result)
            storage.save_run(run, result, 'complete')
            pipeline.save_item(job['id'], 'codebase_builder', run, result)
            return result
        finally:
            lease.rollback()
            lease.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))', ('codebase-run:' + job['project_id'],))


def queue_deliveries(pipeline, job, manifest, result):
    needed = set(result.get('deliverySourceIds', []))
    deliveries = []
    for source in manifest:
        if source['source_id'] not in needed or source['status'] != 'complete':
            continue
        config = {**job['configuration'], 'codeAgentDeliveryRunId': result['runId'], 'codeAgentDeliverySourceJobId': source['id'], 'corpusProfileId': None}
        version = fingerprint(config)
        identifier = 'job:' + fingerprint([source['source_id'], source['revision'], version])
        with connection() as conn:
            latest = conn.execute("SELECT id FROM ingestion_jobs WHERE source_id=%s AND project_id=%s AND NOT (configuration ? 'codeAgentDeliveryRunId') ORDER BY created_at DESC,id DESC LIMIT 1", (source['source_id'], job['project_id'])).fetchone()
            if not latest or latest['id'] != source['id']:
                continue
            inserted = conn.execute("INSERT INTO ingestion_jobs(id,source_id,revision,processing_version,configuration,original_path,project_id,status,queued_through) VALUES(%s,%s,%s,%s,%s,%s,%s,'queued','publish') ON CONFLICT DO NOTHING RETURNING id", (identifier, source['source_id'], source['revision'], version, Jsonb(config), source['original_path'], job['project_id'])).fetchone()
            if inserted:
                conn.execute("INSERT INTO project_events(project_id,job_id,kind,payload) VALUES(%s,%s,'file_registered',%s)", (job['project_id'], identifier, Jsonb({'filename': source['filename'], 'reason': 'Publishing newly modeled codebase behavior from this source; no additional builder run'})))
            row = conn.execute('SELECT id,status FROM ingestion_jobs WHERE id=%s', (identifier,)).fetchone()
            deliveries.append({**row, 'sourceId': source['source_id']})
    return deliveries
