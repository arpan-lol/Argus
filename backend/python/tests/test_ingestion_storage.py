import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
import zipfile
from urllib.parse import urlsplit, urlunsplit

import pytest


@pytest.mark.skipif(os.getenv('ARGUS_RUN_STORAGE_TESTS') != '1', reason='Requires local Postgres and FalkorDB')
def test_isolated_graph_ingestion():
    import psycopg
    from psycopg import sql
    from app.config import settings
    name = 'argus_ingestion_check_' + uuid.uuid4().hex
    target = urlunsplit(urlsplit(settings.database_url)._replace(path='/' + name))
    root = Path(__file__).resolve().parents[3]
    with psycopg.connect(settings.database_url, autocommit=True) as admin, tempfile.TemporaryDirectory() as directory:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            env = {**os.environ, 'DATABASE_URL': target, 'DATA_DIR': directory, 'ARGUS_INGESTION_WORKERS': '0', 'PYTHONPATH': str(root / 'backend' / 'python')}
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child'], cwd=root, env=env, capture_output=True, text=True, timeout=180)
            assert result.returncode == 0, result.stdout + '\n' + result.stderr
            assert '"crossFileCall": true' in result.stdout
            print(result.stdout)
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


def check_storage():
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import connection
    from app.ingestion.pipeline import IngestionPipeline
    from app.ingestion.providers import Providers
    from app.ingestion.publication import graph_connection, semantic_graph_name
    pipeline = IngestionPipeline()
    graphs = {}
    calls = []

    def settings_call(self, schema, prompt, payload, **kwargs):
        calls.append(payload)
        return {'entityTypes': [], 'relationshipTypes': [], 'rationale': 'Synthetic test category labels cover the source'}

    def vectors(self, texts):
        return [[1.0] + [0.01] * (self.config['embeddingDimensions'] - 1) for text in texts]

    def local_relations(texts, profile, config):
        outputs = []
        for text in texts:
            entities = []
            relationships = []
            if 'Zeolite adsorbs lead.' in text:
                for name, label in [('Zeolite', 'material'), ('lead', 'chemical')]:
                    start = text.index(name)
                    entities.append({'start': start, 'end': start + len(name), 'text': name, 'label': label, 'score': 0.92})
                relationships.append({'head': entities[0], 'tail': entities[1], 'relation': 'adsorbs', 'score': 0.91})
            outputs.append({'entities': entities, 'relationships': relationships, 'windows': [{'start': 0, 'end': len(text)}], 'model': 'synthetic_fixture'})
        return outputs

    def upload(client, project, files):
        response = client.post(f'/api/projects/{project}/uploads', files=files)
        assert response.status_code == 202, response.text
        payload = response.json()
        for job in payload['jobs']:
            config = pipeline.job_row(job['id'])['configuration']
            graphs[semantic_graph_name(config)] = graph_connection(config)
            result = pipeline.run_job(job['id'])
            assert result['status'] == 'complete', json.dumps(result)
        return payload

    try:
        with patch.object(Providers, 'structured', settings_call), patch.object(Providers, 'embed', vectors), patch.object(Providers, 'gliner', return_value={'mentions': []}), patch('app.ingestion.local_extraction.relex_many', local_relations), TestClient(app) as client:
            assert len(client.get('/api/projects/categories').json()['categories']) == 8
            project = client.post('/api/projects', json={'name': 'Synthetic code check', 'description': 'Synthetic Python repository for an ingestion test', 'categories': ['code_repository']}).json()['id']
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, 'w') as zipped:
                zipped.writestr('repo/src/demo/main.py', 'from demo.utils import store\n\ndef run(item):\n    return store(item)\n')
                zipped.writestr('repo/src/demo/utils.py', 'def store(item):\n    return item\n\ndef Store(item):\n    return item\n')
                zipped.writestr('repo/.env', 'SYNTHETIC=value')
                zipped.writestr('repo/logo.png', 'synthetic unsupported image')
            first = upload(client, project, [('files', ('repo.zip', archive.getvalue(), 'application/zip'))])
            assert len(first['jobs']) == 2 and len(first['skippedFiles']) == 2
            graph = graphs[pipeline.artifact(first['jobs'][0]['id'], 'publish')['graph']]
            found = graph.ro_query("MATCH (s:Entity)-[r:RELATES {predicate:'calls'}]->(o:Entity) WHERE r.active=true RETURN s.label,o.label").result_set
            assert ['demo.main.run', 'demo.utils.store'] in found, found
            nodes = client.get(f'/api/projects/{project}/map/view', params={'minX': -100000, 'maxX': 100000, 'minY': -100000, 'maxY': 100000, 'zoom': 1, 'mode': 'network'}).json()
            assert any(node['label'] == 'demo.utils.store' for node in nodes['nodes']), nodes
            assert any(edge.get('predicate') == 'calls' for edge in nodes['edges']), nodes
            symbol = next(node for node in nodes['nodes'] if node['label'] == 'demo.utils.store')
            capitalized = next(node for node in nodes['nodes'] if node['label'] == 'demo.utils.Store')
            assert symbol['id'] != capitalized['id']
            inspected = client.post(f'/api/projects/{project}/retrieval/tools/inspect_assertions', json={'arguments': {'entity_id': symbol['id']}}).json()
            assert inspected['items'] and any(item['extraction']['method'] == 'python_ast' for item in inspected['items']), inspected
            setup_calls = len(calls)
            upload(client, project, [('files', ('src/demo/other.py', b'from demo.utils import store\n\ndef work(item):\n    return store(item)\n', 'text/plain'))])
            assert len(calls) == setup_calls
            revised = upload(client, project, [('files', ('src/demo/main.py', b'from demo.utils import store\n\ndef run(item):\n    return store(item)\n\ndef extra(item):\n    return run(item)\n', 'text/plain'))])
            with connection() as conn:
                assert conn.execute('SELECT count(*) AS n FROM ingestion_publications WHERE source_id=%s AND active', (revised['jobs'][0]['documentId'],)).fetchone()['n'] == 1
                profile = conn.execute('SELECT p.* FROM ingestion_profiles p JOIN projects w ON w.profile_id=p.id WHERE w.id=%s', (project,)).fetchone()
                assert 0 < profile['tokens_reserved'] < 24000
            from app.ingestion.embedding_limits import wait_for_capacity
            pacing = {'embeddingResourceIdentity': 'synthetic-' + project, 'embeddingModel': 'synthetic', 'embeddingTokensPerMinute': 1000}
            assert wait_for_capacity(pacing, 10) < 1
            with connection() as conn:
                assert conn.execute('SELECT sum(tokens) AS tokens FROM ingestion_embedding_reservations').fetchone()['tokens'] == 11
            chemistry = client.post('/api/projects', json={'name': 'Synthetic chemistry check', 'description': 'Synthetic adsorption relation check', 'categories': ['scientific_documents', 'research_papers']}).json()['id']
            article = b'<article><front><article-meta><title-group><article-title>Synthetic chemistry</article-title></title-group></article-meta></front><body><sec><title>Results</title><p>Zeolite adsorbs lead.</p></sec></body></article>'
            chemical = upload(client, chemistry, [('files', ('sample.nxml', article, 'application/xml'))])
            chemical_graph = graphs[pipeline.artifact(chemical['jobs'][0]['id'], 'publish')['graph']]
            relations = chemical_graph.ro_query("MATCH (s:Entity)-[r:RELATES {predicate:'adsorbs'}]->(o:Entity) WHERE r.active=true RETURN s.label,o.label,r.confidence").result_set
            assert len(relations) == 1 and relations[0][:2] == ['Zeolite', 'lead'], relations
            return {'crossFileCall': True, 'mapEntitiesVisible': True, 'laterUploadReusesProfile': True, 'revisionReplacement': True, 'chemistrySourcePublished': True, 'workspaceTokenReservation': profile['tokens_reserved'], 'fixtureOnly': True, 'azureCalls': 0}
    finally:
        for graph in graphs.values():
            try:
                graph.delete()
            except Exception:
                pass


if __name__ == '__main__':
    print(json.dumps(check_storage()))
