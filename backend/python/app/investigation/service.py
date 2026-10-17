import json
import logging
import math
import os
import queue
import threading
import time
import uuid

from fastapi import HTTPException
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.types.json import Jsonb

from app.config import settings
from app.database import connection
from app.ingestion.config import processing_config
from app.ingestion.deployments import deployment
from app.ingestion.publication import semantic_graph_name
from .contracts import Report, report_references
from .runtime import Investigation, validate_sources


logger = logging.getLogger("argus.chat")
slots = threading.BoundedSemaphore(2)


def configuration():
    config = processing_config()
    config["chatModel"] = os.getenv("ARGUS_CHAT_MODEL") or config["extractionModel"]
    config["chatProvider"] = os.getenv("ARGUS_CHAT_PROVIDER") or config.get("llmProvider", config["provider"])
    config["chatBaseUrl"] = os.getenv("ARGUS_CHAT_BASE_URL") or config.get("llmBaseUrl")
    config["chatApiVersion"] = os.getenv("ARGUS_CHAT_API_VERSION", config.get("llmApiVersion") if config["chatProvider"] == config.get("llmProvider") else None) or None
    config["chatApi"] = os.getenv("ARGUS_CHAT_API", "chat_completions")
    if config["chatApi"] not in ("chat_completions", "responses"):
        raise HTTPException(400, "Unknown chat API protocol")
    primary = deployment("LLM1")
    if primary:
        config.update(chatModel=primary["model"], chatProvider="azure_openai", chatBaseUrl=primary["baseUrl"], chatApiVersion=None, chatApi=primary["api"], chatCredentialEnv=primary["credentialEnv"])
    config["chatLimits"] = {"modelCalls": 8, "toolCalls": 8, "totalTokens": 64000, "contextTokens": 10000, "outputTokens": 2048, "elapsedMs": 180000, "costUsd": 0.25}
    for field, environment in (("modelCalls", "ARGUS_CHAT_MODEL_CALLS"), ("toolCalls", "ARGUS_CHAT_TOOL_CALLS"), ("totalTokens", "ARGUS_CHAT_TOTAL_TOKENS"), ("contextTokens", "ARGUS_CHAT_CONTEXT_TOKENS"), ("outputTokens", "ARGUS_CHAT_OUTPUT_TOKENS"), ("elapsedMs", "ARGUS_CHAT_ELAPSED_MS")):
        value = int(os.getenv(environment, config["chatLimits"][field]))
        if not 1 <= value <= config["chatLimits"][field]:
            raise HTTPException(400, f"{environment} must be between 1 and {config['chatLimits'][field]}")
        config["chatLimits"][field] = value
    input_price, output_price = os.getenv("ARGUS_CHAT_INPUT_USD_PER_MILLION"), os.getenv("ARGUS_CHAT_OUTPUT_USD_PER_MILLION")
    config["chatPrices"] = None
    if input_price is not None or output_price is not None:
        if not input_price or not output_price:
            raise HTTPException(400, "Configure both chat input and output token prices")
        prices = {"input": float(input_price), "output": float(output_price)}
        if any(not math.isfinite(value) or value < 0 for value in prices.values()):
            raise HTTPException(400, "Chat token prices must be finite and nonnegative")
        config["chatPrices"] = prices
    with connection() as conn:
        count = conn.execute("SELECT count(*) AS n FROM ingestion_publications p JOIN ingestion_jobs j ON j.id=p.job_id JOIN published_documents d ON d.id=p.source_id WHERE p.active AND p.counts->>'graph'=%s AND d.metadata->>'revisionId'=j.revision AND d.metadata->>'processingVersion'=j.processing_version", (semantic_graph_name(config),)).fetchone()["n"]
        legacy = conn.execute("SELECT count(*) AS n FROM legacy_documents").fetchone()["n"]
    config["coverage"] = {"publishedDocuments": count, "legacyDocuments": legacy, "searchScope": "Published semantic sources only. The legacy catalog is separate."}
    return config


def get_run(run_id):
    with connection() as conn:
        row = conn.execute("SELECT * FROM chat_runs WHERE id=%s", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Investigation not found")
    return row


def public_event(kind, payload):
    return {"type": kind, **payload}


def run_worker(run_id, updates):
    investigation = None
    owns_run = False
    started = time.monotonic()
    def emit(kind, payload):
        with connection() as conn:
            row = conn.execute("INSERT INTO chat_events(run_id,kind,payload) VALUES(%s,%s,%s) RETURNING sequence", (run_id, kind, Jsonb(payload))).fetchone()
        updates.put({**public_event(kind, payload), "sequence": row["sequence"]})
    try:
        with connection() as lease:
            acquired = lease.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok", ("chat-run:" + run_id,)).fetchone()["ok"]
            if not acquired:
                raise RuntimeError("This investigation is already running; reconnect to its saved results")
            owns_run = True
            slot = None
            for index in range(2):
                if lease.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok", (f"chat-slot:{index}",)).fetchone()["ok"]:
                    slot = index
                    break
            if slot is None:
                raise RuntimeError("Both investigation workers are busy. Resume this run shortly.")
            lease.commit()
            row = get_run(run_id)
            if row["status"] == "complete":
                updates.put(public_event("done", row["result"]))
                return
            with connection() as conn:
                conn.execute("UPDATE chat_runs SET status='running',error=NULL,updated_at=now() WHERE id=%s", (run_id,))
            emit("started", {"runId": run_id, "query": row["request"]["query"], "model": row["configuration"]["chatModel"], "coverage": row["configuration"]["coverage"], "limits": row["configuration"]["chatLimits"]})
            investigation = Investigation(row, emit)
            with PostgresSaver.from_conn_string(settings.database_url) as saver:
                graph = investigation.graph(saver)
                options = {"configurable": {"thread_id": "chat:" + run_id}, "recursion_limit": 40}
                snapshot = graph.get_state(options)
                initial = None if snapshot.values else {"messages": [], "pending": [], "sources": {}, "report": None, "tool_count": 0, "seen_calls": [], "draft": None}
                state = graph.invoke(initial, options)
            report = Report.model_validate(state["report"])
            sources = validate_sources(state["sources"], report_references(report), row["configuration"])
            with connection() as conn:
                budget = conn.execute("SELECT budget FROM chat_runs WHERE id=%s", (run_id,)).fetchone()["budget"]
            result = {"runId": run_id, "model": row["configuration"]["chatModel"], "report": report.model_dump(), "sources": sources, "coverage": row["configuration"]["coverage"], "usage": {**budget, "toolCalls": state["tool_count"], "runtimeMs": investigation.elapsed(), "costKnown": row["configuration"]["chatPrices"] is not None, "tokensMeaning": "Conservative reservations include maximum output, tool schemas and context; actual usage is recorded in events."}}
            with connection() as conn:
                conn.execute("UPDATE chat_runs SET status='complete',result=%s,runtime_ms=%s,updated_at=now() WHERE id=%s", (Jsonb(result), investigation.elapsed(), run_id))
            emit("done", result)
    except Exception as error:
        logger.exception("Investigation failed: %s", run_id)
        message = str(error) if isinstance(error, (ValueError, RuntimeError)) else "The model or retrieval service failed. Resume this investigation to retry its unfinished step."
        message = message[:600]
        if owns_run:
            with connection() as conn:
                elapsed = investigation.elapsed() if investigation else (time.monotonic() - started) * 1000
                conn.execute("UPDATE chat_runs SET status='failed',error=%s,runtime_ms=%s,updated_at=now() WHERE id=%s AND status<>'complete'", (message, elapsed, run_id))
        emit("error", {"runId": run_id, "message": message})
    finally:
        slots.release()
        updates.put(None)


def start(body=None, run_id=None):
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Both investigation workers are busy. Try again shortly.")
    try:
        if run_id:
            row = get_run(run_id)
            if row["status"] == "running":
                with connection() as conn:
                    acquired = conn.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok", ("chat-run:" + run_id,)).fetchone()["ok"]
                if not acquired:
                    raise HTTPException(409, "This investigation is still running. Reconnect to its results.")
        else:
            run_id = str(uuid.uuid4())
            config = configuration()
            with connection() as conn:
                conn.execute("INSERT INTO chat_runs(id,request,configuration) VALUES(%s,%s,%s)", (run_id, Jsonb(body.model_dump()), Jsonb(config)))
        updates = queue.Queue()
        threading.Thread(target=run_worker, args=(str(run_id), updates), daemon=True, name="argus-investigation").start()
        return str(run_id), updates
    except Exception:
        slots.release()
        raise


def events(updates, run_id):
    yield json.dumps({"type": "accepted", "runId": run_id}) + "\n"
    while True:
        try:
            event = updates.get(timeout=10)
        except queue.Empty:
            yield json.dumps({"type": "heartbeat", "runId": run_id}) + "\n"
            continue
        if event is None:
            return
        yield json.dumps(event, ensure_ascii=False) + "\n"


def detail(run_id):
    row = get_run(run_id)
    if row["status"] == "running":
        with connection() as conn:
            available = conn.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok", ("chat-run:" + run_id,)).fetchone()["ok"]
            if available:
                conn.execute("UPDATE chat_runs SET status='interrupted' WHERE id=%s AND status='running'", (run_id,))
                row["status"] = "interrupted"
    with connection() as conn:
        events = conn.execute("SELECT sequence,kind,payload FROM chat_events WHERE run_id=%s ORDER BY sequence", (run_id,)).fetchall()
    return {"runId": str(row["id"]), "query": row["request"]["query"], "status": row["status"], "error": row["error"], "result": row["result"], "model": row["configuration"]["chatModel"], "coverage": row["configuration"]["coverage"], "events": [{**public_event(event["kind"], event["payload"]), "sequence": event["sequence"]} for event in events]}
