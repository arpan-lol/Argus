import hashlib
import json
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns
from uuid import uuid4
from .models import Document, Evidence, Claim
from .retrieval import BM25Retriever


class JsonIngestor:
    def load(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8"))


class Engine:
    def __init__(self, store, graph):
        self.store, self.graph = store, graph
        self.retriever = BM25Retriever(store)

    def capabilities(self):
        return {"graph": self.graph.status(), "retrieval": {"bm25": True, "dense": False, "rrf": False, "reranker": False}, "ingestion": {"validated_json": True, "pdf": False, "xml": False, "automatic_extraction": False}, "generation": {"enabled": False, "token_usage": False, "cost_tracking": False}, "inspection": {"source_spans": True, "processing_events": True, "stage_timings": True}, "workflow": {"decision_contract": True, "decision_persistence": False}}

    @contextmanager
    def stage(self, run, name, detail=None):
        start = perf_counter_ns()
        self.store.event(run, {"stage": name, "status": "started", "at": datetime.now(timezone.utc).isoformat(), "detail": detail or {}})
        try:
            yield
        except Exception as exc:
            self.store.event(run, {"stage": name, "status": "failed", "duration_ms": (perf_counter_ns()-start)/1e6, "error": str(exc)})
            exc.run_id = run
            raise
        else:
            self.store.event(run, {"stage": name, "status": "completed", "duration_ms": (perf_counter_ns()-start)/1e6})

    def ingest(self, payload):
        run = str(uuid4())
        with self.stage(run, "validate"):
            docs = [Document(**d) for d in payload.get("documents", [])]
            evidence = [Evidence(**e) for e in payload.get("evidence", [])]
            claims = [Claim(**c) for c in payload.get("claims", [])]
            for items in [docs, evidence, claims]:
                if len({r.id for r in items}) != len(items):
                    raise ValueError("Duplicate IDs within import")
            lookup = {d.id: d for d in docs}
            for e in evidence:
                d = lookup.get(e.document_id)
                if d is None or not 0 <= e.start < e.end <= len(d.text) or d.text[e.start:e.end] != e.quote:
                    raise ValueError(f"Evidence does not match exact source offsets: {e.id}")
            eids = {e.id for e in evidence}
            for c in claims:
                if not c.evidence_ids or not set(c.evidence_ids) <= eids:
                    raise ValueError(f"Claim lacks valid evidence: {c.id}")
            for table, records in [("documents", docs), ("evidence", evidence), ("claims", claims)]:
                old = {r["id"]: r for r in self.store.records(table)}
                for r in records:
                    if r.id in old and old[r.id] != asdict(r):
                        raise ValueError(f"Immutable record changed: {r.id}; use a new revision ID")
        with self.stage(run, "graph_sync", {"documents": len(docs), "evidence": len(evidence), "claims": len(claims)}):
            self.graph.ingest(docs, evidence, claims)
        with self.stage(run, "persist"):
            self.store.save("documents", docs)
            self.store.save("evidence", evidence)
            self.store.save("claims", claims)
        return {"run_id": run, "documents": len(docs), "evidence": len(evidence), "claims": len(claims)}

    def query(self, question, limit=5, expand=True):
        if not isinstance(question, str) or not question.strip() or len(question) > 10000:
            raise ValueError("Question must contain 1–10000 characters")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("limit must be 1–100")
        run = str(uuid4())
        with self.stage(run, "bm25", {"query": question, "k1": 1.2, "b": 0.75, "limit": limit}):
            seeds = self.retriever.search(question, limit)
            self.store.event(run, {"stage": "bm25", "status": "result", "candidates": [asdict(c) for c in seeds]})
        expansion = None
        if expand and seeds:
            with self.stage(run, "graph_expansion"):
                expansion = self.graph.expand([c.evidence_id for c in seeds], limit * 4)
                self.store.event(run, {"stage": "graph_expansion", "status": "result", **expansion})
        ids = {c.evidence_id for c in seeds}
        if expansion:
            ids.update(p[-1] for p in expansion["paths"])
        rows = [e for e in self.store.records("evidence") if e["id"] in ids]
        manifest = json.dumps(self.store.records("documents"), sort_keys=True).encode()
        result = {"run_id": run, "question": question, "corpus_sha256": hashlib.sha256(manifest).hexdigest(), "seeds": [asdict(c) for c in seeds], "graph": expansion, "evidence": rows, "answer": None, "source_store_counts": self.store.counts(), "graph_sync_status": "unknown", "limitations": ["Evidence retrieval only; no answer generation enabled", "BM25 score is relevance, not confidence", "Graph neighbors are unranked candidates, not verified conclusions", "Source-store counts do not certify graph synchronization or extraction coverage"]}
        self.store.event(run, {"stage": "result", "status": "completed", "evidence_ids": sorted(ids), "corpus_sha256": result["corpus_sha256"]})
        return result
