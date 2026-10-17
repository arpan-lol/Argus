import json
import logging
import math
import time
import uuid

from psycopg.types.json import Jsonb
from falkordb import FalkorDB

from app.config import settings
from app.database import connection
from app.ingestion.config import fingerprint, processing_config
from app.ingestion.providers import Providers
from app.ingestion.publication import semantic_graph_name


logger = logging.getLogger("argus.retrieval")


class BudgetReached(RuntimeError):
    pass


class Session:
    def __init__(self, tool, arguments):
        self.id = str(uuid.uuid4())
        self.tool = tool
        self.arguments = arguments
        self.started = time.monotonic()
        self.config = processing_config()
        self.graph_name = semantic_graph_name(self.config)
        self.graph = FalkorDB(host=settings.falkor_host, port=settings.falkor_port, socket_connect_timeout=2, socket_timeout=3).select_graph(self.graph_name)
        self.trace = []
        self.warnings = []
        self.truncations = []
        self.calls = 0
        self.cache = {}
        self.manifest = {}
        self.jobs = []
        self.limits = {"databaseCalls": 64, "elapsedMs": 30000, "elapsedPolicy": "soft admission budget; in-flight operations and final consistency/persistence may finish later", "graphQueryMs": 1500, "sqlQueryMs": 1500, "publicationSnapshot": 10000, "annCandidates": 240, "fanout": 20, "frontier": 40, "outputCharacters": 64000, "chunkCharacters": 12000}
        rows = self.sql("SELECT p.job_id,p.source_id,p.published_at,j.revision,j.processing_version FROM ingestion_publications p JOIN ingestion_jobs j ON j.id=p.job_id JOIN published_documents d ON d.id=p.source_id WHERE p.active AND p.counts->>'graph'=%s AND d.metadata->>'revisionId'=j.revision AND d.metadata->>'processingVersion'=j.processing_version ORDER BY p.source_id LIMIT 10001", (self.graph_name,), "publication snapshot")
        if len(rows) > self.limits["publicationSnapshot"]:
            self.truncate("Publication snapshot capped at 10000 sources; search covers that snapshot only")
        self.manifest = {row["job_id"]: row for row in rows[:self.limits["publicationSnapshot"]]}
        self.jobs = list(self.manifest)

    def check(self):
        if self.calls >= self.limits["databaseCalls"] or (time.monotonic() - self.started) * 1000 >= self.limits["elapsedMs"]:
            self.truncate("Execution budget reached; search is incomplete")
            raise BudgetReached("Execution budget reached")

    def truncate(self, reason):
        if reason not in self.truncations:
            self.truncations.append(reason)

    def sql(self, query, parameters, stage):
        self.check()
        self.calls += 1
        started = time.monotonic()
        with connection() as conn:
            conn.execute("SET LOCAL statement_timeout = '1500ms'")
            rows = conn.execute(query, parameters).fetchall()
        self.trace.append({"stage": stage, "engine": "postgres", "durationMs": (time.monotonic() - started) * 1000, "outputCount": len(rows)})
        return rows

    def cypher(self, query, parameters, stage):
        self.check()
        self.calls += 1
        started = time.monotonic()
        result = self.graph.ro_query(query, {**parameters, "jobs": self.jobs}, timeout=self.limits["graphQueryMs"])
        self.trace.append({"stage": stage, "engine": "falkordb", "durationMs": (time.monotonic() - started) * 1000, "databaseMs": result.run_time_ms, "outputCount": len(result.result_set)})
        return result.result_set

    def chunks(self, ids):
        missing = list(set(ids) - self.cache.keys())
        if missing:
            rows = self.sql("SELECT c.id,c.document_id,c.payload,c.document_title,j.id AS job_id FROM published_chunks c JOIN ingestion_publications p ON p.source_id=c.document_id AND p.active JOIN ingestion_jobs j ON j.id=p.job_id WHERE c.id=ANY(%s) AND j.id=ANY(%s) AND c.payload->>'revisionId'=j.revision AND c.payload->>'processingVersion'=j.processing_version", (missing, self.jobs), "source support")
            for row in rows:
                self.cache[row["id"]] = row
        return {key: self.cache[key] for key in ids if key in self.cache}

    def citation(self, row, start=None, end=None):
        chunk = row["payload"]
        return {"chunkId": row["id"], "documentId": row["document_id"], "documentTitle": row["document_title"], "jobId": row["job_id"], "revisionId": chunk["revisionId"], "processingVersion": chunk["processingVersion"], "sectionId": chunk["sectionId"], "sectionTitle": chunk.get("sectionTitle", ""), "sourceUrl": chunk.get("sourceUrl"), "startOffset": chunk["startOffset"] if start is None else start, "endOffset": chunk["endOffset"] if end is None else end, "offsetUnit": "unicode_codepoint"}

    def excerpt(self, row):
        chunk = row["payload"]
        text = chunk["text"]
        cap = self.limits["chunkCharacters"]
        clipped = len(text) > cap
        if clipped:
            self.truncate("Source excerpts clipped; read original for full context")
        return {**self.citation(row), "text": text[:cap], "excerptEndOffset": chunk["startOffset"] + min(len(text), cap), "textTruncated": clipped}

    def query_vector(self, query):
        profile = {key: self.config.get(key) for key in ("provider", "embeddingModel", "embeddingDimensions", "embeddingResourceIdentity")}
        profile["task"] = "retrieval_query"
        key = fingerprint([profile, query])
        cached = self.sql("SELECT vector,receipt FROM retrieval_query_embeddings WHERE id=%s AND profile=%s", (key, Jsonb(profile)), "query embedding cache")
        if cached:
            vector = cached[0]["vector"]
            self.trace.append({"stage": "query embedding", "cacheHit": True, "profile": profile, "durationMs": 0})
        else:
            self.check()
            receipts = []
            try:
                vector = Providers(self.config, receipts.append).embed_query(query)
            finally:
                self.trace.extend({"stage": "query embedding", "cacheHit": False, **receipt} for receipt in receipts)
            self.sql("INSERT INTO retrieval_query_embeddings(id,profile,vector,receipt) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id", (key, Jsonb(profile), Jsonb(vector), Jsonb(receipts)), "cache query embedding")
        if len(vector) != profile["embeddingDimensions"] or any(not math.isfinite(value) for value in vector) or not any(vector):
            raise ValueError("Invalid query vector")
        return vector

    def entity(self, entity_id):
        rows = self.cypher("MATCH (e:Entity {id:$id})<-[:RESOLVED_TO]-(m:Mention)<-[:HAS_MENTION]-(c:Chunk) WHERE c.active=true AND m.active=true AND c.jobId IN $jobs AND m.jobId=c.jobId RETURN e.id,e.label,e.type,e.description,c.id,m.text,m.startOffset,m.endOffset ORDER BY c.id,m.id LIMIT 1", {"id": entity_id}, "resolve published entity")
        if not rows:
            return None
        row = rows[0]
        support = self.chunks([row[4]]).get(row[4])
        if not support:
            return None
        chunk = support["payload"]
        start, end = row[6], row[7]
        if start < chunk["startOffset"] or end > chunk["endOffset"] or end - start != len(row[5]) or chunk["text"][start - chunk["startOffset"]:end - chunk["startOffset"]] != row[5]:
            return None
        return {"id": row[0], "name": row[1], "type": row[2], "description": (row[3] or "")[:1200], "mention": row[5], "citation": self.citation(support, start, end), "metadataMeaning": "Canonical identity metadata; current source wording is in mention"}

    def finish(self, payload, outcome=None):
        current = []
        with connection() as conn:
            conn.execute("SET LOCAL statement_timeout = '1500ms'")
            current = conn.execute("SELECT job_id,published_at FROM ingestion_publications WHERE active AND job_id=ANY(%s)", (self.jobs,)).fetchall()
        unchanged = {row["job_id"]: row["published_at"] for row in current} == {key: row["published_at"] for key, row in self.manifest.items()}
        if not unchanged:
            payload = {"items": []}
            outcome = "stale_publication"
            self.warnings.append("Publication changed during retrieval. Results withheld; retry against the current revision.")
        response = {"runId": self.id, "tool": self.tool, "arguments": self.arguments, "outcome": outcome or ("truncated" if self.truncations else "answered" if payload.get("items") or payload.get("paths") else "not_found"), **payload, "graphName": self.graph_name, "publicationCount": len(self.jobs), "trace": self.trace, "warnings": self.warnings, "truncations": self.truncations, "budget": {"limits": self.limits, "databaseCalls": self.calls, "elapsedMs": (time.monotonic() - self.started) * 1000}, "generation": False}
        if len(json.dumps(response, ensure_ascii=False)) > self.limits["outputCharacters"]:
            response = {"runId": self.id, "tool": self.tool, "outcome": "output_budget_exceeded", "items": [], "paths": [], "graphName": self.graph_name, "publicationCount": len(self.jobs), "generation": False, "truncations": ["Structured result exceeds 64000 characters; request fewer results"], "budget": {"databaseCalls": self.calls, "elapsedMs": (time.monotonic() - self.started) * 1000}}
        with connection() as conn:
            conn.execute("INSERT INTO api_runs(id,payload) VALUES(%s,%s)", (self.id, Jsonb(response)))
        return response
