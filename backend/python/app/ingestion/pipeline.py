import hashlib
import json
import logging
import math
import mimetypes
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Annotated, TypedDict
from operator import or_

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Overwrite
from psycopg.types.json import Jsonb

from app.config import settings
from app.database import connection, migrate

from .chunking import chunk_document
from .config import fingerprint, processing_config
from .parsers import normalize
from .providers import ConfigurationRequired, Providers
from .schema import ensure_schema


STAGES = ("register", "parse", "normalize", "chunk", "mentions", "configure", "embed", "extract", "resolve", "prepare", "validate", "publish")
logger = logging.getLogger("argus.ingestion")


class PauseRequested(Exception):
    pass


class PipelineState(TypedDict):
    job_id: str
    through: str
    stopped: Annotated[bool, or_]


def initialize():
    migrate()
    with connection() as conn:
        ensure_schema(conn)
        running = conn.execute("SELECT id FROM ingestion_jobs WHERE status='running'").fetchall()
        for row in running:
            acquired = conn.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired", (row["id"],)).fetchone()["acquired"]
            if acquired:
                try:
                    conn.execute("UPDATE ingestion_jobs SET status='interrupted',error='Worker stopped; resume from persisted artifacts',updated_at=now() WHERE id=%s AND status='running'", (row["id"],))
                    conn.execute("UPDATE ingestion_attempts SET status='interrupted',finished_at=now(),error='Worker stopped' WHERE job_id=%s AND status='running'", (row["id"],))
                finally:
                    conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (row["id"],))
    with PostgresSaver.from_conn_string(settings.database_url) as saver:
        saver.setup()


def serialize(value):
    return json.loads(json.dumps(value, default=str))


class IngestionPipeline:
    def __init__(self):
        builder = StateGraph(PipelineState)
        for stage in STAGES:
            builder.add_node(stage, self.node(stage))
        builder.add_edge(START, STAGES[0])
        for first, second in (("register", "parse"), ("parse", "normalize"), ("normalize", "chunk"), ("chunk", "configure"), ("chunk", "embed"), ("chunk", "mentions"), ("extract", "resolve"), ("resolve", "prepare"), ("validate", "publish")):
            builder.add_edge(first, second)
        builder.add_edge(["configure", "mentions"], "extract")
        builder.add_edge(["embed", "prepare"], "validate")
        builder.add_edge("publish", END)
        self.builder = builder

    def describe_source(self, path, source_id=None, source_url=None, filename=None):
        path = Path(path).resolve()
        config = processing_config()
        if path.stat().st_size > config["maxUploadBytes"]:
            raise ValueError(f"File exceeds configured {config['maxUploadBytes']} byte input limit")
        raw_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        source_id = source_id or "source:" + fingerprint([config.get('projectId'), str(path)])
        directory = Path(settings.data_dir) / "originals" / raw_digest[:2]
        directory.mkdir(parents=True, exist_ok=True)
        original = directory / (raw_digest + "-" + Path(filename or path.name).name)
        if original != path and not original.exists():
            shutil.copyfile(path, original)
        return {"sourceId": source_id, "revision": raw_digest, "originalPath": str(original), "filename": filename or path.name, "sourceUrl": source_url}

    def register_file(self, path, source_id=None, source_url=None, filename=None, profile_id=None, prompt=None):
        from .profiles import create_profile, get_profile
        if profile_id and prompt:
            raise ValueError("Supply either a corpus profile or a new prompt")
        source = self.describe_source(path, source_id, source_url, filename)
        config = processing_config()
        if prompt:
            profile_id = create_profile(prompt, [source], config)["id"]
        if profile_id:
            get_profile(profile_id)
            config["corpusProfileId"] = profile_id
        version = fingerprint(config)
        job_id = "job:" + fingerprint([source["sourceId"], source["revision"], version])
        with connection() as conn:
            conn.execute("INSERT INTO ingestion_sources(id,filename,original_path,source_url,media_type,project_id) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET filename=excluded.filename,original_path=excluded.original_path,source_url=COALESCE(excluded.source_url,ingestion_sources.source_url)", (source["sourceId"], source["filename"], source["originalPath"], source_url, mimetypes.guess_type(source["filename"])[0], config.get('projectId')))
            conn.execute("INSERT INTO ingestion_jobs(id,source_id,revision,processing_version,configuration,original_path,project_id) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (job_id, source["sourceId"], source["revision"], version, Jsonb(config), source["originalPath"], config.get('projectId')))
        return self.get_job(job_id)

    def job_row(self, job_id):
        with connection() as conn:
            row = conn.execute("SELECT j.*,s.filename,COALESCE(j.original_path,s.original_path) AS original_path,s.source_url FROM ingestion_jobs j JOIN ingestion_sources s ON s.id=j.source_id WHERE j.id=%s", (job_id,)).fetchone()
        if not row:
            raise KeyError(job_id)
        from app.projects.scope import current_project
        if current_project.get() and row.get('project_id') != current_project.get():
            raise KeyError(job_id)
        return row

    def register_sources(self, sources, config, profile_id, through):
        if through not in STAGES:
            raise ValueError('Unknown ingestion stage')
        config = {**config, 'corpusProfileId': profile_id}
        version = fingerprint(config)
        identifiers = ['job:' + fingerprint([source['sourceId'], source['revision'], version]) for source in sources]
        with connection() as conn, conn.cursor() as cursor:
            cursor.executemany('INSERT INTO ingestion_sources(id,filename,original_path,source_url,media_type,project_id) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET filename=excluded.filename,original_path=excluded.original_path,source_url=COALESCE(excluded.source_url,ingestion_sources.source_url)', [(source['sourceId'], source['filename'], source['originalPath'], source.get('sourceUrl'), mimetypes.guess_type(source['filename'])[0], config.get('projectId')) for source in sources])
            cursor.executemany('INSERT INTO ingestion_jobs(id,source_id,revision,processing_version,configuration,original_path,project_id) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', [(identifier, source['sourceId'], source['revision'], version, Jsonb(config), source['originalPath'], config.get('projectId')) for identifier, source in zip(identifiers, sources, strict=True)])
            conn.execute("WITH eligible AS (SELECT id FROM ingestion_jobs WHERE id=ANY(%s) AND status NOT IN ('complete','running','queued')),locked AS (SELECT id FROM eligible WHERE pg_try_advisory_xact_lock(hashtextextended(id,0))) UPDATE ingestion_jobs j SET status='queued',error=NULL,stop_requested=false,queued_through=%s,updated_at=now() FROM locked WHERE j.id=locked.id AND j.status NOT IN ('complete','running','queued')", (identifiers, through))
            cursor.executemany("INSERT INTO project_events(project_id,job_id,kind,payload) VALUES(%s,%s,'file_registered',%s)", [(config['projectId'], identifier, Jsonb({'filename': source['filename']})) for identifier, source in zip(identifiers, sources, strict=True)])
            rows = conn.execute('SELECT j.id,j.status,j.source_id,j.created_at,s.filename FROM ingestion_jobs j JOIN ingestion_sources s ON s.id=j.source_id WHERE j.id=ANY(%s) ORDER BY s.filename', (identifiers,)).fetchall()
        return serialize([{'id': row['id'], 'status': row['status'], 'documentId': row['source_id'], 'filename': row['filename'], 'createdAt': row['created_at']} for row in rows])

    def job_response(self, row, attempts, artifacts, item_counts, publication_state):
        stages = []
        for stage in STAGES:
            history = [attempt for attempt in attempts if attempt["stage"] == stage]
            latest = history[-1] if history else {}
            stages.append({"name": stage, "status": latest.get("status", "queued"), "attempts": len(history), "error": latest.get("error"), "startedAt": latest.get("started_at"), "completedAt": latest.get("finished_at"), "durationMs": latest.get("duration_ms"), "metadata": latest.get("metadata", {}), "history": history})
        return serialize({"id": row["id"], "filename": row["filename"], "documentId": row["source_id"], "status": row["status"], "currentStage": row["current_stage"], "createdAt": row["created_at"], "updatedAt": row["updated_at"], "error": row["error"], "revision": row["revision"], "processingVersion": row["processing_version"], "configuration": row["configuration"], "stages": stages, "chunkCount": artifacts.get("chunk", {}).get("count", 0), "itemCounts": item_counts, "counts": artifacts.get("publish", {}), "publicationState": publication_state})

    def job_details(self, rows):
        identifiers = [row['id'] for row in rows]
        grouped = {identifier: {'attempts': [], 'artifacts': {}, 'counts': [], 'publication': None} for identifier in identifiers}
        if identifiers:
            with connection() as conn:
                for attempt in conn.execute('SELECT * FROM ingestion_attempts WHERE job_id=ANY(%s) ORDER BY id', (identifiers,)).fetchall():
                    grouped[attempt['job_id']]['attempts'].append(attempt)
                for artifact in conn.execute("SELECT job_id,stage,CASE WHEN stage='chunk' THEN jsonb_build_object('count',jsonb_array_length(payload->'chunks')) ELSE payload END AS payload FROM ingestion_artifacts WHERE job_id=ANY(%s) AND stage IN ('chunk','publish')", (identifiers,)).fetchall():
                    grouped[artifact['job_id']]['artifacts'][artifact['stage']] = artifact['payload']
                for count in conn.execute('SELECT job_id,stage,count(*) AS count FROM ingestion_items WHERE job_id=ANY(%s) GROUP BY job_id,stage', (identifiers,)).fetchall():
                    grouped[count['job_id']]['counts'].append({'stage': count['stage'], 'count': count['count']})
                for state in conn.execute("SELECT job_id,payload FROM ingestion_items WHERE job_id=ANY(%s) AND stage='publication_state' AND item_id='current'", (identifiers,)).fetchall():
                    grouped[state['job_id']]['publication'] = state['payload']
        return [self.job_response(row, grouped[row['id']]['attempts'], grouped[row['id']]['artifacts'], grouped[row['id']]['counts'], grouped[row['id']]['publication']) for row in rows]

    def get_job(self, job_id):
        return self.job_details([self.job_row(job_id)])[0]

    def list_jobs(self, limit=50, offset=0):
        from app.projects.scope import current_project
        project_id = current_project.get()
        with connection() as conn:
            rows = conn.execute("SELECT j.*,s.filename FROM ingestion_jobs j JOIN ingestion_sources s ON s.id=j.source_id WHERE j.project_id IS NOT DISTINCT FROM %s ORDER BY (j.status='running') DESC,(j.status IN ('failed','waiting_configuration','interrupted')) DESC,(j.status='registered') ASC,j.updated_at DESC LIMIT %s OFFSET %s", (project_id, limit, offset)).fetchall()
            total = conn.execute("SELECT count(*) AS count FROM ingestion_jobs WHERE project_id IS NOT DISTINCT FROM %s", (project_id,)).fetchone()["count"]
        return {"jobs": self.job_details(rows), "total": total, "limit": limit, "offset": offset}

    def artifact(self, job_id, stage):
        with connection() as conn:
            row = conn.execute("SELECT payload FROM ingestion_artifacts WHERE job_id=%s AND stage=%s", (job_id, stage)).fetchone()
        return row["payload"] if row else None

    def save_artifact(self, job_id, stage, payload):
        with connection() as conn:
            conn.execute("INSERT INTO ingestion_artifacts(job_id,stage,payload,digest) VALUES(%s,%s,%s,%s) ON CONFLICT(job_id,stage) DO UPDATE SET payload=excluded.payload,digest=excluded.digest,created_at=now()", (job_id, stage, Jsonb(payload), fingerprint(payload)))

    def item(self, job_id, stage, item_id):
        with connection() as conn:
            row = conn.execute("SELECT payload FROM ingestion_items WHERE job_id=%s AND stage=%s AND item_id=%s", (job_id, stage, item_id)).fetchone()
        return row["payload"] if row else None

    def save_item(self, job_id, stage, item_id, payload):
        with connection() as conn:
            conn.execute("INSERT INTO ingestion_items(job_id,stage,item_id,payload) VALUES(%s,%s,%s,%s) ON CONFLICT(job_id,stage,item_id) DO UPDATE SET payload=excluded.payload", (job_id, stage, item_id, Jsonb(serialize(payload))))
            conn.execute("UPDATE ingestion_jobs SET updated_at=now() WHERE id=%s", (job_id,))

    def call_recorder(self, job_id):
        def record(payload):
            self.save_item(job_id, "provider_call", str(uuid.uuid4()), payload)
            from app.projects.events import job_event
            job_event(self.job_row(job_id), 'model_call', payload)
        return record

    def check_paused(self, job_id):
        if self.job_row(job_id).get('stop_requested'):
            raise PauseRequested()

    def node(self, stage):
        def execute(state):
            job = self.job_row(state["job_id"])
            if state["stopped"] or job.get("stop_requested") or STAGES.index(stage) > STAGES.index(state["through"]) or self.artifact(job["id"], stage) is not None:
                return {}
            with connection() as conn:
                attempt = conn.execute("SELECT COALESCE(max(attempt),0)+1 AS n FROM ingestion_attempts WHERE job_id=%s AND stage=%s", (job["id"], stage)).fetchone()["n"]
                attempt_id = conn.execute("INSERT INTO ingestion_attempts(job_id,stage,attempt,status) VALUES(%s,%s,%s,'running') RETURNING id", (job["id"], stage, attempt)).fetchone()["id"]
                conn.execute("UPDATE ingestion_jobs SET status='running',current_stage=%s,error=NULL,updated_at=now() WHERE id=%s", (stage, job["id"]))
            started = time.monotonic()
            from app.projects.events import job_event
            job_event(job, 'stage_start', {'stage': stage, 'attempt': attempt, 'filename': job['filename']})
            try:
                result = getattr(self, "stage_" + stage)(job)
                self.save_artifact(job["id"], stage, result)
                receipt = {"artifactDigest": fingerprint(result)}
                for key in ("quality", "fallbackChunks", "profileId", "entityTypes", "deferredMentions"):
                    if key in result:
                        receipt[key] = result[key]
                summaries = []
                parser = result.get('metadata', {}).get('parser')
                if parser:
                    summaries.append('Parser: ' + parser.replace('_', ' '))
                if result.get('structuralRelationships') is not None:
                    summaries.append(str(result['structuralRelationships']) + ' Python syntax relationships')
                sampling = result.get('sampling', {})
                if sampling:
                    summaries.append(str(sampling.get('callsThisRun', 0)) + ' label discovery calls; stopped: ' + sampling.get('stopReason', 'complete').replace('_', ' '))
                if result.get("fallbackChunks"):
                    summaries.append(f"{result['fallbackChunks']} chunks kept local GLiNER mentions after failed extraction; no relationships extracted for those chunks.")
                if result.get("deferredMentions"):
                    summaries.append(f"{result['deferredMentions']} mentions kept separate; duplicate checks deferred.")
                coverage = result.get("metadata", {}).get("sourceCoverage", {})
                if coverage.get("limitedSource"):
                    receipt["limitedSource"] = True
                    summaries.append("Only available source text was retained; the full article body was not supplied.")
                receipt["summary"] = summaries
                with connection() as conn:
                    conn.execute("UPDATE ingestion_attempts SET status='complete',finished_at=now(),duration_ms=%s,metadata=%s WHERE id=%s", ((time.monotonic() - started) * 1000, Jsonb(receipt), attempt_id))
                    if stage == "publish":
                        conn.execute("UPDATE ingestion_jobs SET status='complete',updated_at=now() WHERE id=%s", (job["id"],))
                job_event(job, 'stage_complete', {'stage': stage, 'durationMs': (time.monotonic() - started) * 1000, 'summary': receipt})
                if stage == 'publish':
                    job_event(job, 'graph_updated', {'counts': {key: result[key] for key in ('documents', 'sections', 'chunks', 'entities', 'mentions', 'assertions') if key in result}})
                return {}
            except PauseRequested:
                with connection() as conn:
                    conn.execute("UPDATE ingestion_attempts SET status='paused',finished_at=now(),duration_ms=%s,error='Paused by user; saved item results remain available' WHERE id=%s", ((time.monotonic() - started) * 1000, attempt_id))
                    conn.execute("UPDATE ingestion_jobs SET status='paused',error=NULL,updated_at=now() WHERE id=%s", (job["id"],))
                job_event(job, 'stage_complete', {'stage': stage, 'status': 'paused', 'message': 'Paused by user. Completed work is saved.'})
                return {"stopped": True}
            except Exception as error:
                status = "waiting_configuration" if isinstance(error, ConfigurationRequired) else "failed"
                logger.exception("ingestion stage failed: %s %s", job["id"], stage)
                with connection() as conn:
                    conn.execute("UPDATE ingestion_attempts SET status=%s,finished_at=now(),duration_ms=%s,error=%s WHERE id=%s", (status, (time.monotonic() - started) * 1000, str(error), attempt_id))
                    conn.execute("UPDATE ingestion_jobs SET status=%s,error=%s,updated_at=now() WHERE id=%s", (status, str(error), job["id"]))
                job_event(job, 'stage_failed', {'stage': stage, 'status': status, 'message': str(error)})
                return {"stopped": True}
        return execute

    def retry_call(self, job, stage, key, operation, max_attempts=None):
        previous = self.item(job["id"], stage, key)
        if previous is not None:
            return previous
        attempts = job["configuration"]["retries"] if max_attempts is None else max_attempts
        if attempts < 1:
            raise ConfigurationRequired("Provider attempts must be positive")
        for attempt in range(attempts):
            if self.job_row(job["id"]).get("stop_requested"):
                raise PauseRequested()
            try:
                from app.projects.events import job_event
                job_event(job, 'item_start', {'stage': stage, 'itemId': key, 'attempt': attempt + 1})
                payload = operation()
                self.save_item(job["id"], stage, key, payload)
                counts = {name: len(payload[name]) for name in ('entities', 'relationships', 'mentions', 'vectors', 'votes') if isinstance(payload.get(name), list)}
                job_event(job, 'item_complete', {'stage': stage, 'itemId': key, 'attempt': attempt + 1, 'counts': counts})
                if self.job_row(job["id"]).get("stop_requested"):
                    raise PauseRequested()
                return payload
            except ConfigurationRequired:
                raise
            except PauseRequested:
                raise
            except Exception as error:
                self.save_item(job["id"], "retry_history", str(uuid.uuid4()), {"stage": stage, "itemId": key, "attempt": attempt + 1, "error": str(error)})
                job_event(job, 'item_failed', {'stage': stage, 'itemId': key, 'attempt': attempt + 1, 'message': str(error), 'willRetry': attempt + 1 < attempts})
                if attempt + 1 >= attempts:
                    raise
                provider_delay = re.search(r"retry (?:in|after)\s+([\d.]+)\s*s", str(error), re.IGNORECASE)
                headers = getattr(getattr(error, 'response', None), 'headers', {}) or {}
                try:
                    header_delay = float(headers.get('retry-after-ms', '0')) / 1000 or float(headers.get('retry-after', '0'))
                except (ValueError, TypeError):
                    header_delay = 0
                delay = max(job["configuration"]["retryBaseSeconds"] * (2 ** attempt), float(provider_delay.group(1)) + 1 if provider_delay else 0, header_delay + 0.25 if header_delay else 0)
                deadline = time.monotonic() + delay
                while time.monotonic() < deadline:
                    if self.job_row(job["id"]).get("stop_requested"):
                        raise PauseRequested()
                    time.sleep(min(0.25, deadline - time.monotonic()))

    def enqueue(self, job_id, through="publish"):
        if through not in STAGES:
            raise ValueError("Unknown stage")
        row = self.job_row(job_id)
        if row['configuration'].get('contract') != processing_config(row.get('project_id'))['contract']:
            raise RuntimeError('This upload uses an earlier ingestion pipeline. Create a new workspace and upload the original files to rebuild with local extraction.')
        with connection() as conn:
            acquired = conn.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired", (job_id,)).fetchone()["acquired"]
            if not acquired:
                raise RuntimeError("Job already has an active worker")
            try:
                conn.execute("UPDATE ingestion_jobs SET status='queued',error=NULL,stop_requested=false,queued_through=%s,updated_at=now() WHERE id=%s", (through, job_id))
            finally:
                conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (job_id,))
        return self.get_job(job_id)

    def run_job(self, job_id, through="publish", queued_only=False):
        if through not in STAGES:
            raise ValueError("Unknown stage")
        with connection() as lease:
            acquired = lease.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired", (job_id,)).fetchone()["acquired"]
            if not acquired:
                return self.get_job(job_id)
            lease.commit()
            try:
                with connection() as conn:
                    if queued_only:
                        claimed = conn.execute("UPDATE ingestion_jobs SET status='running',error=NULL,updated_at=now() WHERE id=%s AND status='queued' AND queued_through IS NOT NULL RETURNING id,queued_through", (job_id,)).fetchone()
                        if not claimed:
                            return self.get_job(job_id)
                        through = claimed["queued_through"]
                    else:
                        conn.execute("UPDATE ingestion_jobs SET status='running',error=NULL,queued_through=%s,updated_at=now() WHERE id=%s", (through, job_id))
                with PostgresSaver.from_conn_string(settings.database_url) as saver:
                    graph = self.builder.compile(checkpointer=saver)
                    result = graph.invoke({"job_id": job_id, "through": through, "stopped": Overwrite(False)}, {"recursion_limit": len(STAGES) + 5, "configurable": {"thread_id": job_id}})
                if not result["stopped"]:
                    complete = self.artifact(job_id, "publish") is not None
                    with connection() as conn:
                        conn.execute("UPDATE ingestion_jobs SET status=%s,updated_at=now() WHERE id=%s", ("complete" if complete else "paused", job_id))
                else:
                    with connection() as conn:
                        failure = conn.execute("SELECT a.stage,a.status,a.error FROM ingestion_attempts a WHERE a.job_id=%s AND a.status IN ('failed','waiting_configuration') AND NOT EXISTS(SELECT 1 FROM ingestion_attempts newer WHERE newer.job_id=a.job_id AND newer.stage=a.stage AND newer.id>a.id) ORDER BY a.id DESC LIMIT 1", (job_id,)).fetchone()
                        if failure:
                            conn.execute("UPDATE ingestion_jobs SET status=%s,current_stage=%s,error=%s,updated_at=now() WHERE id=%s", (failure["status"], failure["stage"], failure["error"], job_id))
            finally:
                lease.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (job_id,))
        return self.get_job(job_id)

    def stage_register(self, job):
        raw = Path(job["original_path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != job["revision"]:
            raise ValueError("Immutable original digest mismatch")
        return {"sourceId": job["source_id"], "revision": job["revision"], "byteLength": len(raw), "originalPath": job["original_path"]}

    def stage_parse(self, job):
        from .parser_routing import parse_source
        result = parse_source(job["original_path"], job["configuration"], job["filename"])
        if job["source_url"]:
            result["metadata"]["sourceUrl"] = job["source_url"]
        return result

    def stage_normalize(self, job):
        from .profiles import source_quality
        from .parser_routing import attach_structure
        result = attach_structure(source_quality(normalize(self.artifact(job["id"], "parse"))), job["filename"])
        for block in result["blocks"]:
            block["id"] = "block:" + fingerprint([job["id"], block["ordinal"]])
        return result

    def stage_chunk(self, job):
        return chunk_document(self.artifact(job["id"], "normalize"), [job["source_id"], job["revision"], job["processing_version"]], job["configuration"])

    def stage_embed(self, job):
        provider = Providers(job["configuration"], self.call_recorder(job["id"]), lambda: self.check_paused(job['id']))
        chunks = self.artifact(job["id"], "chunk")["chunks"]
        with connection() as conn:
            completed = {row['item_id'] for row in conn.execute("SELECT item_id FROM ingestion_items WHERE job_id=%s AND stage='embed'", (job['id'],)).fetchall()}
        missing = [chunk for chunk in chunks if chunk['id'] not in completed]
        for start in range(0, len(missing), 128):
            batch = missing[start:start + 128]
            key = fingerprint([job["configuration"]["embeddingModel"], [chunk["id"] for chunk in batch]])
            vectors = self.retry_call(job, "embed_batch", key, lambda rows=batch: {"vectors": provider.embed([chunk["text"] for chunk in rows])})["vectors"]
            with connection() as conn, conn.cursor() as cursor:
                cursor.executemany("INSERT INTO ingestion_items(job_id,stage,item_id,payload) VALUES(%s,'embed',%s,%s) ON CONFLICT(job_id,stage,item_id) DO UPDATE SET payload=excluded.payload", [(job['id'], chunk['id'], Jsonb({'vector': vector, 'model': job['configuration']['embeddingModel']})) for chunk, vector in zip(batch, vectors, strict=True)])
        return {"chunks": len(chunks), "model": job["configuration"]["embeddingModel"], "dimensions": job["configuration"]["embeddingDimensions"], "storage": "Durable PostgreSQL staging; FalkorDB vector properties/index published only after validation"}

    def stage_configure(self, job):
        config = job["configuration"]
        from .profiles import prepare_profile
        from .categories import seed_settings
        if config.get("corpusProfileId"):
            return prepare_profile(self, job, config["corpusProfileId"])
        return seed_settings(config["categories"], config["profileEntityCap"], config["profileRelationshipCap"])

    def stage_mentions(self, job):
        from .local_extraction import extract_early_mentions
        return extract_early_mentions(self, job)

    def stage_extract(self, job):
        from .local_extraction import extract_local
        return extract_local(self, job)

    def stage_prepare(self, job):
        return {"relationshipVectors": 0, "providerCalls": 0}

    def validate_extraction(self, chunk, extraction):
        entities = {entity["key"] for entity in extraction["entities"]}
        if len(entities) != len(extraction["entities"]):
            raise ValueError("Extraction entity keys are not unique")
        for entity in extraction["entities"]:
            if not entity["name"].strip() or not entity["quote"] or entity["quote"] not in chunk["text"]:
                raise ValueError(f"Entity {entity['key']!r} quote is not an exact, case-sensitive source substring: {entity['quote']!r}")
        for relationship in extraction["relationships"]:
            if relationship["subject"] not in entities or relationship["object"] not in entities:
                raise ValueError(f"Relationship endpoints {relationship['subject']!r}, {relationship['object']!r} must be entity keys, not names or new entities. Valid keys are {sorted(entities)!r}. Add a source-supported entity or omit this relationship.")
            if not relationship["predicate"].strip() or not relationship["quote"] or relationship["quote"] not in chunk["text"]:
                quote = relationship["quote"]
                location = chunk["text"].lower().find(quote.lower()) if quote else -1
                hint = chunk["text"][location:location + len(quote)] if location >= 0 and len(chunk["text"].lower()) == len(chunk["text"]) else None
                raise ValueError(f"Relationship {relationship['subject']!r} {relationship['predicate']!r} {relationship['object']!r} needs an exact, case-sensitive source quote. Re-copy or omit this unsupported quote: {quote!r}. Original source candidate to re-check: {hint!r}")
            for condition in relationship.get("conditions", []):
                if not condition["value"] or condition["value"] not in relationship["quote"]:
                    raise ValueError(f"Condition {condition['name']!r} value {condition['value']!r} must occur verbatim in quote {relationship['quote']!r}; omit the condition if it is not stated there")
                if condition.get("unit") and condition["unit"] not in relationship["quote"]:
                    raise ValueError("Relationship condition unit must occur verbatim in its supporting quote")

    def stage_resolve(self, job):
        from .sdk_resolution import resolve_basic
        return resolve_basic(self, job)

    def stage_validate(self, job):
        from .publication import supported_spans
        document = self.artifact(job["id"], "normalize")
        chunks = self.artifact(job["id"], "chunk")["chunks"]
        assertions = 0
        for chunk in chunks:
            if document["text"][chunk["startOffset"]:chunk["endOffset"]] != chunk["text"]:
                raise ValueError("Chunk source offset mismatch")
            embedded = self.item(job["id"], "embed", chunk["id"])
            if not embedded or len(embedded["vector"]) != job["configuration"]["embeddingDimensions"] or not any(embedded["vector"]) or any(not math.isfinite(value) for value in embedded["vector"]):
                raise ValueError("Chunk embedding missing, nonfinite or wrong dimensionality")
            extraction = self.item(job["id"], "extract", chunk["id"])
            self.validate_extraction(chunk, extraction)
            for record in extraction["entities"] + extraction["relationships"]:
                supported_spans(chunk, record)
            facts = extraction["relationships"]
            assertions += len(facts)
            for entity in extraction["entities"]:
                mention_id = "mention:" + fingerprint([chunk["id"], entity["key"]])
                if not self.item(job["id"], "resolve", mention_id):
                    raise ValueError("Entity resolution artifact missing")
        fallback_count = (self.artifact(job["id"], "extract") or {}).get("fallbackChunks", 0)
        graph = document.get("codeGraph", {})
        occurrences = [occurrence for entity in graph.get('entities', []) for occurrence in entity['occurrences']]
        for record in graph.get("entities", []) + graph.get("relationships", []) + occurrences:
            if document["text"][record["start"]:record["end"]] != record["quote"] or not record["quote"]:
                raise ValueError("Code parser source offsets are inconsistent")
        return {"chunks": len(chunks), "assertions": assertions, "offsets": "exact_match", "fallbackChunks": fallback_count, "structuralRelationships": len(graph.get("relationships", [])), "semanticValidation": "Source offsets and graph structure checked. Local semantic predictions are not independently verified. Code relations describe syntax, not runtime execution."}

    def stage_publish(self, job):
        from .publication import publish
        result = publish(self, job)
        from app.projects.graph import store_layout
        store_layout(self, job)
        return result
