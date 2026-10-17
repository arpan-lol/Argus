import math
import os

from psycopg.types.json import Jsonb

from app.database import connection
from .config import fingerprint
from .providers import Providers, ResolutionBatch, RESOLUTION_PROMPT
from .publication import graph_connection, index


def describe(entity):
    return {"name": entity["label"], "type": entity["entity_type"], "description": entity["description"], "quote": entity.get("source_quote")}


def plan_resolution(pipeline, job, provider, graph):
    version = "batched-pairs-deferred-2"
    previous = pipeline.item(job["id"], "resolve_plan", version)
    if previous:
        return previous
    records = []
    for chunk in pipeline.artifact(job["id"], "chunk")["chunks"]:
        extraction = pipeline.item(job["id"], "extract", chunk["id"])
        deferred = bool(extraction.get("metadata", {}).get("fallback"))
        for entity in extraction["entities"]:
            mention_id = "mention:" + fingerprint([chunk["id"], entity["key"]])
            records.append({"mentionId": mention_id, "entity": entity, "chunkId": chunk["id"], "provisionalId": "entity:" + fingerprint([job["id"], mention_id]), "deferred": deferred})
    missing = [record for record in records if pipeline.item(job["id"], "entity_embed", record["mentionId"]) is None]
    batch_size = job["configuration"].get("entityEmbeddingBatchSize", int(os.getenv("ARGUS_ENTITY_EMBED_BATCH_SIZE", "32")))
    if batch_size < 1:
        raise ValueError("Entity embedding batch size must be positive")
    for start in range(0, len(missing), batch_size):
        batch = missing[start:start + batch_size]
        key = fingerprint([job["configuration"]["embeddingModel"], [record["mentionId"] for record in batch]])
        payload = pipeline.retry_call(job, "entity_embed_batch", key, lambda rows=batch: {"vectors": provider.embed([row["entity"]["name"] + "\n" + row["entity"]["entity_type"] + "\n" + row["entity"]["description"] for row in rows])})
        for record, vector in zip(batch, payload["vectors"], strict=True):
            pipeline.save_item(job["id"], "entity_embed", record["mentionId"], {"vector": vector})
    for record in records:
        entity = record["entity"]
        vector = pipeline.item(job["id"], "entity_embed", record["mentionId"])["vector"]
        if any(not math.isfinite(value) for value in vector):
            raise ValueError("Entity embedding contains nonfinite values")
        with connection() as conn:
            conn.execute("INSERT INTO ingestion_entities(id,label,entity_type,description,aliases,embedding,embedding_model,created_by_job,source_quote) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (record["provisionalId"], entity["name"], entity["entity_type"], entity["description"], Jsonb([entity["name"]]), Jsonb(vector), job["configuration"]["embeddingModel"], job["id"], entity["quote"]))
        graph.query("MERGE (e:Entity {id:$id}) ON CREATE SET e.label=$name,e.type=$type,e.description=$description,e.embedding=vecf32($vector),e.embeddingModel=$model,e.jobId=$job,e.active=false SET e.resolutionDeferred=$deferred", {"id": record["provisionalId"], "name": entity["name"], "type": entity["entity_type"], "description": entity["description"], "vector": vector, "model": job["configuration"]["embeddingModel"], "job": job["id"], "deferred": record["deferred"]})
    pairs = {}
    anchors = set()
    provisional = {record["provisionalId"] for record in records}
    deferred_ids = [record["provisionalId"] for record in records if record["deferred"]]
    for record in records:
        if record["deferred"]:
            continue
        entity = record["entity"]
        vector = pipeline.item(job["id"], "entity_embed", record["mentionId"])["vector"]
        neighbors = graph.query("CALL db.idx.vector.queryNodes('Entity','embedding',$limit,vecf32($vector)) YIELD node,score WHERE node.embeddingModel=$model AND (node.active=true OR node.jobId=$job) AND coalesce(node.resolutionDeferred,false)=false RETURN node.id,score", {"limit": job["configuration"]["resolutionSearchCandidates"], "vector": vector, "model": job["configuration"]["embeddingModel"], "job": job["id"]}).result_set
        with connection() as conn:
            candidates = conn.execute("SELECT e.* FROM ingestion_entities e WHERE e.id<>%s AND embedding_model=%s AND (e.id=ANY(%s) OR lower(label)=lower(%s)) AND NOT(e.id=ANY(%s)) AND NOT EXISTS(SELECT 1 FROM ingestion_resolution_decisions blocked JOIN ingestion_publications published ON published.job_id=blocked.job_id WHERE blocked.canonical_id=e.id AND blocked.decision='deferred' AND published.active) AND (created_by_job=%s OR EXISTS(SELECT 1 FROM ingestion_resolution_decisions d JOIN ingestion_publications p ON p.job_id=d.job_id WHERE d.canonical_id=e.id AND d.decision<>'deferred' AND p.active)) ORDER BY CASE WHEN lower(label)=lower(%s) THEN 0 ELSE 1 END,created_at LIMIT %s", (record["provisionalId"], job["configuration"]["embeddingModel"], [row[0] for row in neighbors], entity["name"], deferred_ids, job["id"], entity["name"], job["configuration"]["resolutionSearchCandidates"])).fetchall()
        scored = []
        for candidate in candidates:
            other = candidate["embedding"]
            if not other or len(other) != len(vector):
                continue
            norm = math.sqrt(sum(x * x for x in vector) * sum(x * x for x in other))
            cosine = sum(a * b for a, b in zip(vector, other)) / norm if norm else 0
            if candidate["label"].casefold() == entity["name"].casefold() or cosine >= job["configuration"]["resolutionCosineThreshold"]:
                scored.append((cosine, candidate))
        for cosine, candidate in sorted(scored, key=lambda pair: (-pair[0], pair[1]["id"]))[:job["configuration"]["resolutionCandidates"]]:
            left, right = sorted([record["provisionalId"], candidate["id"]])
            pair_id = fingerprint([left, right])
            own = {"name": entity["name"], "type": entity["entity_type"], "description": entity["description"], "quote": entity["quote"]}
            pair_records = [own, describe(candidate)] if left == record["provisionalId"] else [describe(candidate), own]
            pairs.setdefault(pair_id, {"pair_id": pair_id, "left": left, "right": right, "records": pair_records, "cosine": cosine})
            if candidate["id"] not in provisional:
                anchors.add(candidate["id"])
    plan = {"version": version, "records": records, "pairs": sorted(pairs.values(), key=lambda pair: pair["pair_id"]), "anchors": sorted(anchors), "deferredMentions": len(deferred_ids), "pairBatchSize": job["configuration"].get("resolutionBatchPairs", int(os.getenv("ARGUS_RESOLUTION_BATCH_PAIRS", "32")))}
    if plan["pairBatchSize"] < 1:
        raise ValueError("Resolution pair batch size must be positive")
    pipeline.save_item(job["id"], "resolve_plan", version, plan)
    return plan


def resolve(pipeline, job):
    graph = graph_connection(job["configuration"])
    index(graph, "Entity", job["configuration"]["embeddingDimensions"])
    provider = Providers(job["configuration"], pipeline.call_recorder(job["id"]))
    plan = plan_resolution(pipeline, job, provider, graph)
    outcomes = {}
    prompt = RESOLUTION_PROMPT + " Evaluate every supplied pair independently. Return exactly one vote for each pair_id, retaining its identifier. Do not infer that different pairs are identical merely because they are in the same batch."
    for start in range(0, len(plan["pairs"]), plan["pairBatchSize"]):
        batch = plan["pairs"][start:start + plan["pairBatchSize"]]
        expected = {pair["pair_id"] for pair in batch}
        passes = []
        for reverse in (False, True):
            payload = [{"pair_id": pair["pair_id"], "records": list(reversed(pair["records"])) if reverse else pair["records"]} for pair in (list(reversed(batch)) if reverse else batch)]
            def judge(rows=payload):
                result = provider.structured(ResolutionBatch, prompt, {"pairs": rows}, judge=True)
                identifiers = [vote["pair_id"] for vote in result["votes"]]
                if len(identifiers) != len(expected) or set(identifiers) != expected:
                    raise ValueError("Resolution batch must return every requested pair exactly once")
                return result
            result = pipeline.retry_call(job, "judge_batch", fingerprint(payload), judge)
            passes.append({vote["pair_id"]: vote for vote in result["votes"]})
        for pair in batch:
            first, second = passes[0][pair["pair_id"]], passes[1][pair["pair_id"]]
            outcomes[pair["pair_id"]] = {**pair, "forward": first, "reverse": second}
    ids = {record["provisionalId"] for record in plan["records"]} | {value for pair in plan["pairs"] for value in (pair["left"], pair["right"])}
    parents = {key: key for key in ids}
    members = {key: {key} for key in ids}
    anchors = set(plan["anchors"])
    negatives = [(pair["left"], pair["right"]) for pair in outcomes.values() if "different" in (pair["forward"]["decision"], pair["reverse"]["decision"])]
    def find(key):
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key
    conflicts = []
    for pair in sorted(outcomes.values(), key=lambda value: (-value["cosine"], value["pair_id"])):
        if pair["forward"]["decision"] != "same" or pair["reverse"]["decision"] != "same":
            continue
        a, b = find(pair["left"]), find(pair["right"])
        if a == b:
            continue
        if (members[a] & anchors and members[b] & anchors) or any((left in members[a] and right in members[b]) or (right in members[a] and left in members[b]) for left, right in negatives):
            conflicts.append(pair["pair_id"])
            continue
        canonical = min(members[a] | members[b], key=lambda key: (key not in anchors, key))
        other = b if canonical in members[a] else a
        root = a if canonical in members[a] else b
        parents[other] = root
        members[root] |= members.pop(other)
    for record in plan["records"]:
        provisional = record["provisionalId"]
        canonical = min(members[find(provisional)], key=lambda key: (key not in anchors, key))
        incident = [pair for pair in outcomes.values() if provisional in (pair["left"], pair["right"])]
        votes = [{"pairId": pair["pair_id"], "candidateId": pair["right"] if pair["left"] == provisional else pair["left"], "cosine": pair["cosine"], "forward": pair["forward"], "reverse": pair["reverse"], "mergeConflict": pair["pair_id"] in conflicts} for pair in incident]
        uncertain = [vote for vote in votes if vote["mergeConflict"] or vote["forward"]["decision"] != vote["reverse"]["decision"] or vote["forward"]["decision"] == "uncertain"]
        verdict = "same" if canonical != provisional else "uncertain" if uncertain else "new"
        candidate_id = canonical if canonical != provisional else uncertain[0]["candidateId"] if uncertain else None
        rationale = "Canonical identity follows unanimous paired judgments; explicit negative pairs and distinct published anchors cannot be transitively merged." if verdict == "same" else "Identity remains separate; no consistent unanimous merge was established."
        if record["deferred"]:
            canonical = provisional
            verdict = "deferred"
            candidate_id = None
            votes = []
            rationale = "Duplicate checking is deferred because LLM extraction failed. This GLiNER-only mention remains separate until extraction is reviewed or retried."
        decision_id = "resolution:" + fingerprint([job["id"], record["mentionId"]])
        with connection() as conn:
            conn.execute("INSERT INTO ingestion_resolution_decisions(id,job_id,mention_id,candidate_id,canonical_id,decision,rationale,votes) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET candidate_id=excluded.candidate_id,canonical_id=excluded.canonical_id,decision=excluded.decision,rationale=excluded.rationale,votes=excluded.votes WHERE NOT ingestion_resolution_decisions.reverted", (decision_id, job["id"], record["mentionId"], candidate_id, canonical, verdict, rationale, Jsonb(votes)))
        pipeline.save_item(job["id"], "resolve", record["mentionId"], {"mentionId": record["mentionId"], "canonicalId": canonical, "decisionId": decision_id, "decision": verdict, "candidateId": candidate_id, "deferred": record["deferred"], "reason": rationale})
    for pair in outcomes.values():
        pipeline.save_item(job["id"], "identity_comparison", pair["pair_id"], pair)
    return {"resolvedMentions": len(plan["records"]), "deferredMentions": plan["deferredMentions"], "candidatePairs": len(plan["pairs"]), "pairBatchSize": plan["pairBatchSize"], "mergeConflicts": conflicts, "method": plan["version"], "mergePolicy": "Two order-reversed judgments for LLM-processed records; GLiNER-only fallback mentions remain separate and excluded from duplicate candidates", "deferredPolicy": "Review or retry failed extraction before automatic duplicate checking"}
