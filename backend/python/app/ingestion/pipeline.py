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
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.types.json import Jsonb

from app.config import settings
from app.database import connection

from .chunking import chunk_document
from .config import fingerprint, processing_config
from .parsers import normalize, parse
from .providers import ConfigurationRequired, Extraction, Profile, Providers, ResolutionVote, EXTRACTION_PROMPT, PROFILE_PROMPT, RESOLUTION_PROMPT
from .providers import relationship_repair_schema, extraction_schema
from .schema import ensure_schema


STAGES = ("register", "parse", "normalize", "chunk", "embed", "extract", "resolve", "validate", "publish")
logger = logging.getLogger("argus.ingestion")


class PipelineState(TypedDict):
    job_id: str
    through: str
    stopped: bool


def initialize():
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
        for index, stage in enumerate(STAGES):
            next_stage = STAGES[index + 1] if index + 1 < len(STAGES) else END
            builder.add_conditional_edges(stage, lambda state, s=stage: "stop" if state["stopped"] or state["through"] == s else "next", {"stop": END, "next": next_stage})
        self.builder = builder

    def register_file(self, path, source_id=None, source_url=None, filename=None):
        path = Path(path).resolve()
        config = processing_config()
        if path.stat().st_size > config["maxUploadBytes"]:
            raise ValueError(f"File exceeds configured {config['maxUploadBytes']} byte input limit")
        raw_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        source_id = source_id or "source:" + fingerprint(str(path))
        version = fingerprint(config)
        job_id = "job:" + fingerprint([source_id, raw_digest, version])
        directory = Path(settings.data_dir) / "originals" / raw_digest[:2]
        directory.mkdir(parents=True, exist_ok=True)
        original = directory / (raw_digest + "-" + Path(filename or path.name).name)
        if original != path and not original.exists():
            shutil.copyfile(path, original)
        with connection() as conn:
            conn.execute("INSERT INTO ingestion_sources(id,filename,original_path,source_url,media_type) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET filename=excluded.filename,original_path=excluded.original_path,source_url=COALESCE(excluded.source_url,ingestion_sources.source_url)", (source_id, filename or path.name, str(original), source_url, mimetypes.guess_type(filename or path.name)[0]))
            conn.execute("INSERT INTO ingestion_jobs(id,source_id,revision,processing_version,configuration,original_path) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (job_id, source_id, raw_digest, version, Jsonb(config), str(original)))
        return self.get_job(job_id)

    def job_row(self, job_id):
        with connection() as conn:
            row = conn.execute("SELECT j.*,s.filename,COALESCE(j.original_path,s.original_path) AS original_path,s.source_url FROM ingestion_jobs j JOIN ingestion_sources s ON s.id=j.source_id WHERE j.id=%s", (job_id,)).fetchone()
        if not row:
            raise KeyError(job_id)
        return row

    def get_job(self, job_id):
        row = self.job_row(job_id)
        with connection() as conn:
            attempts = conn.execute("SELECT * FROM ingestion_attempts WHERE job_id=%s ORDER BY id", (job_id,)).fetchall()
            artifacts = {r["stage"]: r["payload"] for r in conn.execute("SELECT stage,CASE WHEN stage='chunk' THEN jsonb_build_object('count',jsonb_array_length(payload->'chunks')) ELSE payload END AS payload FROM ingestion_artifacts WHERE job_id=%s AND stage IN ('chunk','publish')", (job_id,)).fetchall()}
            item_counts = conn.execute("SELECT stage,count(*) AS count FROM ingestion_items WHERE job_id=%s GROUP BY stage", (job_id,)).fetchall()
        stages = []
        for stage in STAGES:
            history = [a for a in attempts if a["stage"] == stage]
            latest = history[-1] if history else {}
            stages.append({"name": stage, "status": latest.get("status", "queued"), "attempts": len(history), "error": latest.get("error"), "startedAt": latest.get("started_at"), "completedAt": latest.get("finished_at"), "durationMs": latest.get("duration_ms"), "metadata": latest.get("metadata", {}), "history": history})
        return serialize({"id": row["id"], "filename": row["filename"], "documentId": row["source_id"], "status": row["status"], "currentStage": row["current_stage"], "createdAt": row["created_at"], "updatedAt": row["updated_at"], "error": row["error"], "revision": row["revision"], "processingVersion": row["processing_version"], "configuration": row["configuration"], "stages": stages, "chunkCount": artifacts.get("chunk", {}).get("count", 0), "itemCounts": item_counts, "counts": artifacts.get("publish", {})})

    def list_jobs(self, limit=50, offset=0):
        with connection() as conn:
            rows = conn.execute("SELECT id FROM ingestion_jobs ORDER BY (status='running') DESC,(status IN ('failed','waiting_configuration','interrupted')) DESC,(status='registered') ASC,updated_at DESC LIMIT %s OFFSET %s", (limit, offset)).fetchall()
            total = conn.execute("SELECT count(*) AS count FROM ingestion_jobs").fetchone()["count"]
        return {"jobs": [self.get_job(row["id"]) for row in rows], "total": total, "limit": limit, "offset": offset}

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
        return record

    def budget(self, job):
        maximum = job["configuration"]["maxLlmCallsPerJob"]
        if maximum:
            with connection() as conn:
                count = conn.execute("SELECT count(*) AS count FROM ingestion_items WHERE job_id=%s AND stage='provider_call' AND payload->>'kind'='llm'", (job["id"],)).fetchone()["count"]
            if count >= maximum:
                raise ConfigurationRequired(f"Configured job LLM call budget ({maximum}) exhausted. Register this source with a higher configured budget to create a new processing version. Existing job outputs remain retained.")

    def node(self, stage):
        def execute(state):
            job = self.job_row(state["job_id"])
            if self.artifact(job["id"], stage) is not None:
                return state
            with connection() as conn:
                attempt = conn.execute("SELECT COALESCE(max(attempt),0)+1 AS n FROM ingestion_attempts WHERE job_id=%s AND stage=%s", (job["id"], stage)).fetchone()["n"]
                attempt_id = conn.execute("INSERT INTO ingestion_attempts(job_id,stage,attempt,status) VALUES(%s,%s,%s,'running') RETURNING id", (job["id"], stage, attempt)).fetchone()["id"]
                conn.execute("UPDATE ingestion_jobs SET status='running',current_stage=%s,error=NULL,updated_at=now() WHERE id=%s", (stage, job["id"]))
            started = time.monotonic()
            try:
                result = getattr(self, "stage_" + stage)(job)
                self.save_artifact(job["id"], stage, result)
                with connection() as conn:
                    conn.execute("UPDATE ingestion_attempts SET status='complete',finished_at=now(),duration_ms=%s,metadata=%s WHERE id=%s", ((time.monotonic() - started) * 1000, Jsonb({"artifactDigest": fingerprint(result)}), attempt_id))
                    if stage == "publish":
                        conn.execute("UPDATE ingestion_jobs SET status='complete',updated_at=now() WHERE id=%s", (job["id"],))
                    elif state["through"] == stage:
                        conn.execute("UPDATE ingestion_jobs SET status='paused',updated_at=now() WHERE id=%s", (job["id"],))
                return state
            except Exception as error:
                status = "waiting_configuration" if isinstance(error, ConfigurationRequired) else "failed"
                logger.exception("ingestion stage failed: %s %s", job["id"], stage)
                with connection() as conn:
                    conn.execute("UPDATE ingestion_attempts SET status=%s,finished_at=now(),duration_ms=%s,error=%s WHERE id=%s", (status, (time.monotonic() - started) * 1000, str(error), attempt_id))
                    conn.execute("UPDATE ingestion_jobs SET status=%s,error=%s,updated_at=now() WHERE id=%s", (status, str(error), job["id"]))
                return {**state, "stopped": True}
        return execute

    def retry_call(self, job, stage, key, operation):
        previous = self.item(job["id"], stage, key)
        if previous is not None:
            return previous
        for attempt in range(job["configuration"]["retries"]):
            try:
                if stage not in {"embed", "entity_embed", "entity_embed_batch", "assertion_embed"}:
                    self.budget(job)
                payload = operation()
                self.save_item(job["id"], stage, key, payload)
                return payload
            except ConfigurationRequired:
                raise
            except Exception as error:
                self.save_item(job["id"], "retry_history", str(uuid.uuid4()), {"stage": stage, "itemId": key, "attempt": attempt + 1, "error": str(error)})
                if attempt + 1 >= job["configuration"]["retries"]:
                    raise
                provider_delay = re.search(r"retry in\s+([\d.]+)\s*s", str(error), re.IGNORECASE)
                delay = max(job["configuration"]["retryBaseSeconds"] * (2 ** attempt), float(provider_delay.group(1)) + 1 if provider_delay else 0)
                time.sleep(delay)

    def enqueue(self, job_id, through="publish"):
        if through not in STAGES:
            raise ValueError("Unknown stage")
        self.job_row(job_id)
        with connection() as conn:
            acquired = conn.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired", (job_id,)).fetchone()["acquired"]
            if not acquired:
                raise RuntimeError("Job already has an active worker")
            try:
                conn.execute("UPDATE ingestion_jobs SET status='queued',error=NULL,queued_through=%s,updated_at=now() WHERE id=%s", (through, job_id))
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
                    result = graph.invoke({"job_id": job_id, "through": through, "stopped": False}, {"recursion_limit": len(STAGES) + 5, "configurable": {"thread_id": job_id}})
                if not result["stopped"]:
                    with connection() as conn:
                        conn.execute("UPDATE ingestion_jobs SET status=%s,updated_at=now() WHERE id=%s", ("complete" if self.artifact(job_id, "publish") else "paused", job_id))
            finally:
                lease.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (job_id,))
        return self.get_job(job_id)

    def stage_register(self, job):
        raw = Path(job["original_path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != job["revision"]:
            raise ValueError("Immutable original digest mismatch")
        return {"sourceId": job["source_id"], "revision": job["revision"], "byteLength": len(raw), "originalPath": job["original_path"]}

    def stage_parse(self, job):
        result = parse(job["original_path"], job["configuration"]["maxDecompressedBytes"], job["configuration"].get("maxExtractedTextCharacters", 20971520), job["configuration"].get("maxArchiveMembers", 10000))
        if job["source_url"]:
            result["metadata"]["sourceUrl"] = job["source_url"]
        return result

    def stage_normalize(self, job):
        result = normalize(self.artifact(job["id"], "parse"))
        for block in result["blocks"]:
            block["id"] = "block:" + fingerprint([job["id"], block["ordinal"]])
        return result

    def stage_chunk(self, job):
        return chunk_document(self.artifact(job["id"], "normalize"), [job["source_id"], job["revision"], job["processing_version"]], job["configuration"])

    def stage_embed(self, job):
        provider = Providers(job["configuration"], self.call_recorder(job["id"]))
        chunks = self.artifact(job["id"], "chunk")["chunks"]
        for chunk in chunks:
            self.retry_call(job, "embed", chunk["id"], lambda c=chunk: {"vector": provider.embed([c["text"]])[0], "model": job["configuration"]["embeddingModel"]})
        return {"chunks": len(chunks), "model": job["configuration"]["embeddingModel"], "dimensions": job["configuration"]["embeddingDimensions"], "storage": "Durable PostgreSQL staging; FalkorDB vector properties/index published only after validation"}

    def stage_extract(self, job):
        provider = Providers(job["configuration"], self.call_recorder(job["id"]))
        document = self.artifact(job["id"], "normalize")
        chunks = self.artifact(job["id"], "chunk")["chunks"]
        types = job["configuration"]["entityTypes"]
        if not types:
            profile = self.retry_call(job, "profile", "document", lambda: provider.structured(Profile, PROFILE_PROMPT, {"title": document["metadata"].get("title", job["filename"]), "source": chunks[0]["text"]}))
            types = profile["entity_types"]
            if not types or any(not isinstance(value, str) or not value.strip() for value in types):
                raise ValueError("LLM inferred an invalid entity type profile")
        entities = relationships = 0
        for chunk in chunks:
            if self.item(job["id"], "extract", chunk["id"]):
                result = self.item(job["id"], "extract", chunk["id"])
            else:
                candidates = self.retry_call(job, "gliner", chunk["id"], lambda c=chunk: provider.gliner(c["text"], types))
                feedback = {}
                with connection() as conn:
                    rejected = conn.execute("SELECT payload FROM ingestion_items WHERE job_id=%s AND stage='rejected_extraction' AND payload->>'chunkId'=%s ORDER BY created_at DESC LIMIT 1", (job["id"], chunk["id"])).fetchone()
                if rejected:
                    prior = rejected["payload"]["output"]
                    try:
                        self.validate_extraction(chunk, prior)
                    except ValueError as error:
                        feedback.update({"error": str(error), "previous_output": prior, "instruction": "Repair this rejected output using exact case-sensitive substrings of the original source. Omit unsupported records."})
                def extract(c=chunk, mentions=candidates):
                    prior_entities = feedback.get("previous_output", {}).get("entities", [])
                    keys = [entity["key"] for entity in prior_entities]
                    repair = bool(keys) and len(keys) == len(set(keys)) and all(entity["name"].strip() and entity["quote"] and entity["quote"] in c["text"] and entity["entity_type"] in types for entity in prior_entities)
                    payload = {"entity_types": types, "gliner_candidates": mentions["mentions"], "source": c["text"], "validation_feedback": feedback}
                    if repair:
                        payload["fixed_entities"] = prior_entities
                        fixed = provider.structured(relationship_repair_schema(keys), EXTRACTION_PROMPT + " Repair relationships for the fixed_entities only. Endpoints must be keys from that list. Record literal values as conditions when supported, never as invented entity keys. Return only the repaired relationships.", payload)
                        result = {"entities": prior_entities, "relationships": fixed["relationships"]}
                    else:
                        result = provider.structured(extraction_schema(types), EXTRACTION_PROMPT, payload)
                    try:
                        self.validate_extraction(c, result)
                        if any(entity["entity_type"] not in types for entity in result["entities"]):
                            raise ValueError("Entity type must belong to the recorded extraction vocabulary")
                    except ValueError as error:
                        feedback.update({"error": str(error), "previous_output": result, "instruction": "Repair the output using the original source. Keep exact quotes and omit unsupported conditions."})
                        self.save_item(job["id"], "rejected_extraction", str(uuid.uuid4()), {"chunkId": c["id"], "error": str(error), "output": result})
                        raise
                    return result
                result = self.retry_call(job, "extract", chunk["id"], extract)
            entities += len(result["entities"])
            relationships += len(result["relationships"])
        return {"entities": entities, "relationships": relationships, "entityTypes": types, "profileOrigin": "configuration" if job["configuration"]["entityTypes"] else "llm_document_inferred", "promptVersion": job["configuration"]["promptVersion"]}

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
        from .resolution import resolve
        return resolve(self, job)

    def stage_validate(self, job):
        document = self.artifact(job["id"], "normalize")
        chunks = self.artifact(job["id"], "chunk")["chunks"]
        assertions = 0
        for chunk in chunks:
            if document["text"][chunk["startOffset"]:chunk["endOffset"]] != chunk["text"]:
                raise ValueError("Chunk source offset mismatch")
            embedded = self.item(job["id"], "embed", chunk["id"])
            if not embedded or len(embedded["vector"]) != job["configuration"]["embeddingDimensions"] or any(not math.isfinite(value) for value in embedded["vector"]):
                raise ValueError("Chunk embedding missing, nonfinite or wrong dimensionality")
            extraction = self.item(job["id"], "extract", chunk["id"])
            self.validate_extraction(chunk, extraction)
            assertions += len(extraction["relationships"])
            for entity in extraction["entities"]:
                mention_id = "mention:" + fingerprint([chunk["id"], entity["key"]])
                if not self.item(job["id"], "resolve", mention_id):
                    raise ValueError("Entity resolution artifact missing")
        return {"chunks": len(chunks), "assertions": assertions, "offsets": "exact_match", "semanticValidation": "LLM source grounding plus structural validation; scientific correctness not independently established"}

    def stage_publish(self, job):
        from .publication import publish
        return publish(self, job)
