from pathlib import PurePosixPath


def selected(job, profile=None):
    from ..parser_routing import SOURCE_SUFFIXES
    categories = set(job['configuration'].get('categories', []))
    return bool(job['configuration'].get('codeAgentDeliveryRunId')) or bool(categories & {'code_repository', 'codebase', 'code_base'}) or PurePosixPath(job['filename']).suffix.lower() in SOURCE_SUFFIXES or job['source_id'] in (profile or {}).get('codeSourceIds', [])


def configure(job):
    from typing import get_args
    from .contracts import EdgeType, NodeType
    return {'entityTypes': list(get_args(NodeType)), 'relationshipTypes': [value.lower() for value in get_args(EdgeType)], 'profileOrigin': 'codebase_graph_builder', 'ingestionRoute': 'codebase_agent', 'description': job['configuration'].get('workspaceDescription', '')}


def extract(pipeline, job):
    from .runner import build_workspace
    from .projection import project_claims
    run = job['configuration'].get('codeAgentDeliveryRunId')
    if run:
        from app.database import connection
        with connection() as conn:
            saved = conn.execute("SELECT payload FROM ingestion_codebase_runs WHERE id=%s AND project_id=%s AND status='complete'", (run, job['project_id'])).fetchone()
        if not saved:
            raise ValueError('Codebase delivery run is unavailable in this workspace')
        result = saved['payload']
    else:
        result = build_workspace(pipeline, job)
    return project_claims(pipeline, job, result)
