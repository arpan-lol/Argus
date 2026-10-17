import json
import math
import os

from falkordb import FalkorDB
from psycopg.types.json import Jsonb

from app.config import settings
from app.database import connection

from .config import fingerprint
from .providers import Providers
from .structure import sections_for, chunk_sections


def semantic_graph_name(config):
    space = [config["provider"], config["embeddingModel"], config["embeddingDimensions"]]
    if config.get("embeddingBaseUrl"):
        space.append(config["embeddingBaseUrl"])
    return config["semanticGraph"] + "_" + fingerprint(space)[:10]


def graph_connection(config):
    return FalkorDB(host=settings.falkor_host, port=settings.falkor_port).select_graph(semantic_graph_name(config))


def index(graph, label, dimensions):
    try:
        graph.query(f"CREATE VECTOR INDEX FOR (n:{label}) ON (n.embedding) OPTIONS {{dimension:{int(dimensions)}, similarityFunction:'cosine'}}")
    except Exception as error:
        if "already" not in str(error).lower() and "exists" not in str(error).lower():
            raise


def publication_lease_key(source_id):
    return "argus-source-publication:" + source_id


def publish(pipeline, job):
    with connection() as lease:
        key=publication_lease_key(job["source_id"])
        acquired=lease.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired",(key,)).fetchone()["acquired"]
        if not acquired:
            raise RuntimeError("Another revision is publishing this source. Retry the publication stage after it finishes.")
        try:
            newer=lease.execute("SELECT p.job_id FROM ingestion_publications p JOIN ingestion_jobs published ON published.id=p.job_id JOIN ingestion_jobs requested ON requested.id=%s WHERE p.source_id=%s AND p.active AND published.created_at>requested.created_at LIMIT 1",(job["id"],job["source_id"])).fetchone()
            if newer:
                raise ValueError("A newer revision of this source is already published. An older job cannot replace the current publication.")
            lease.execute("UPDATE ingestion_publications SET active=false WHERE job_id=%s", (job["id"],))
            lease.commit()
            graph=graph_connection(job["configuration"])
            for label,property_name in (("SourceRevision","sourceId"),("Section","documentId"),("Chunk","documentId"),("Mention","documentId"),("Assertion","documentId")):
                try:
                    graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.{property_name})")
                except Exception as error:
                    if "already" not in str(error).lower() and "exists" not in str(error).lower():
                        raise
            return _publish(pipeline,job)
        finally:
            lease.rollback()
            lease.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))",(key,))


def _publish(pipeline, job):
    document = pipeline.artifact(job["id"], "normalize")
    chunks = pipeline.artifact(job["id"], "chunk")["chunks"]
    metadata = document["metadata"]
    title = metadata.get("title") or job["filename"]
    graph = graph_connection(job["configuration"])
    provider = Providers(job["configuration"], pipeline.call_recorder(job["id"]))
    for label in ("Chunk", "Entity", "Assertion"):
        index(graph, label, job["configuration"]["embeddingDimensions"])
    for label in ("Document", "SourceRevision", "Section", "Chunk", "Entity", "Mention", "Assertion", "ResolutionDecision"):
        try:
            graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
        except Exception as error:
            if "already" not in str(error).lower() and "exists" not in str(error).lower():
                raise
    graph.query("MERGE (d:Document {id:$id}) ON CREATE SET d.title=$title,d.active=false MERGE (r:SourceRevision {id:$job}) SET r.sourceId=$id,r.revision=$revision,r.processingVersion=$version,r.active=false MERGE (d)-[:HAS_REVISION]->(r)", {"id": job["source_id"], "job": job["id"], "title": title, "revision": job["revision"], "version": job["processing_version"]})
    sections = sections_for(document, job)
    graph.query("MATCH (s:Section {jobId:$job}) SET s.projectionCurrent=false", {"job": job["id"]})
    for section in sections:
        graph.query("MATCH (d:Document {id:$document}),(r:SourceRevision {id:$job}) MERGE (s:Section {id:$id}) SET s.documentId=$document,s.jobId=$job,s.title=$title,s.startOffset=$start,s.endOffset=$end,s.projectionCurrent=true,s.active=false MERGE (d)-[:HAS_SECTION]->(s) MERGE (r)-[:HAS_SECTION]->(s)", {"document": job["source_id"], "job": job["id"], "id": section["id"], "title": section["title"], "start": section["startOffset"], "end": section["endOffset"]})
    mention_count = assertion_count = 0
    entities = {}
    accepted_aliases = {}
    publication_chunks = []
    previous = None
    for chunk in chunks:
        primary, related_sections = chunk_sections(chunk, sections)
        section_id = primary["id"]
        vector = pipeline.item(job["id"], "embed", chunk["id"])["vector"]
        graph.query("MATCH (s:Section {id:$section}) MERGE (c:Chunk {id:$id}) SET c.documentId=$document,c.sectionId=$section,c.jobId=$job,c.text=$text,c.ordinal=$ordinal,c.startOffset=$start,c.endOffset=$end,c.embedding=vecf32($vector),c.active=false MERGE (s)-[:HAS_CHUNK]->(c)", {"section": section_id, "id": chunk["id"], "document": job["source_id"], "job": job["id"], "text": chunk["text"], "ordinal": chunk["ordinal"], "start": chunk["startOffset"], "end": chunk["endOffset"], "vector": vector})
        for section in related_sections:
            graph.query("MATCH (s:Section {id:$section}),(c:Chunk {id:$chunk}) MERGE (s)-[:HAS_CHUNK]->(c)", {"section": section["id"], "chunk": chunk["id"]})
        if previous:
            graph.query("MATCH (a:Chunk {id:$a}),(b:Chunk {id:$b}) MERGE (a)-[:NEXT_CHUNK]->(b)", {"a": previous, "b": chunk["id"]})
        previous = chunk["id"]
        extraction = pipeline.item(job["id"], "extract", chunk["id"])
        facts = extraction["relationships"]
        fact_vectors = pipeline.retry_call(job, "assertion_embed", chunk["id"], lambda rows=facts: {"vectors": provider.embed([row["predicate"] + "\n" + row["polarity"] + "\n" + row["quote"] for row in rows]) if rows else []})["vectors"]
        if len(fact_vectors) != len(facts) or any(len(vector) != job["configuration"]["embeddingDimensions"] or any(not math.isfinite(value) for value in vector) for vector in fact_vectors):
            raise ValueError("Assertion embeddings must be finite and match the configured vector space")
        graph.query("MATCH (c:Chunk {id:$id}) OPTIONAL MATCH (c)-[r:MENTIONS]->() DELETE r", {"id": chunk["id"]})
        local = {}
        for entity in extraction["entities"]:
            mention_id = "mention:" + fingerprint([chunk["id"], entity["key"]])
            resolved = pipeline.item(job["id"], "resolve", mention_id)
            with connection() as conn:
                decision = conn.execute("SELECT * FROM ingestion_resolution_decisions WHERE id=%s", (resolved["decisionId"],)).fetchone()
                canonical = conn.execute("SELECT * FROM ingestion_entities WHERE id=%s", (decision["canonical_id"],)).fetchone()
            canonical_id = canonical["id"]
            accepted_aliases.setdefault(canonical_id, set()).add(entity["name"])
            local[entity["key"]] = canonical_id
            relative = chunk["text"].index(entity["quote"])
            start = chunk["startOffset"] + relative
            graph.query("MATCH (c:Chunk {id:$chunk}) MERGE (e:Entity {id:$entity}) ON CREATE SET e.label=$label,e.type=$type,e.description=$description,e.embedding=vecf32($vector),e.embeddingModel=$model MERGE (m:Mention {id:$mention}) SET m.jobId=$job,m.text=$quote,m.startOffset=$start,m.endOffset=$end,m.documentId=$document,m.active=false MERGE (c)-[:HAS_MENTION]->(m)", {"chunk": chunk["id"], "entity": canonical_id, "label": canonical["label"], "type": canonical["entity_type"], "description": canonical["description"], "vector": canonical["embedding"], "model": canonical["embedding_model"], "mention": mention_id, "job": job["id"], "document": job["source_id"], "quote": entity["quote"], "start": start, "end": start + len(entity["quote"])})
            graph.query("MATCH (m:Mention {id:$mention}) OPTIONAL MATCH (m)-[old:RESOLVED_TO]->() DELETE old", {"mention": mention_id})
            graph.query("MATCH (c:Chunk {id:$chunk}),(m:Mention {id:$mention}),(e:Entity {id:$entity}) MERGE (m)-[:RESOLVED_TO]->(e) MERGE (c)-[:MENTIONS]->(e) MERGE (r:ResolutionDecision {id:$decision}) SET r.jobId=$job,r.decision=$verdict,r.rationale=$rationale,r.reverted=$reverted MERGE (r)-[:RESOLVES]->(m)", {"chunk": chunk["id"], "mention": mention_id, "entity": canonical_id, "decision": decision["id"], "job": job["id"], "verdict": decision["decision"], "rationale": decision["rationale"], "reverted": decision["reverted"]})
            entities.setdefault(canonical_id, {"id": canonical_id, "label": canonical["label"], "type": canonical["entity_type"], "extractionMethod": "gliner_llm_verified", "mentions": []})["mentions"].append({"chunkId": chunk["id"], "startOffset": start, "endOffset": start + len(entity["quote"]), "text": entity["quote"]})
            mention_count += 1
        for ordinal, relationship in enumerate(extraction["relationships"]):
            assertion_id = "assertion:" + fingerprint([job["id"], chunk["id"], ordinal, relationship])
            relative = chunk["text"].index(relationship["quote"])
            start = chunk["startOffset"] + relative
            graph.query("MATCH (c:Chunk {id:$chunk}) MERGE (a:Assertion {id:$id}) SET a.jobId=$job,a.documentId=$document,a.predicate=$predicate,a.quote=$quote,a.conditions=$conditions,a.polarity=$polarity,a.startOffset=$start,a.endOffset=$end,a.embedding=vecf32($vector),a.embeddingModel=$model,a.active=false MERGE (a)-[:SUPPORTED_BY]->(c)", {"chunk": chunk["id"], "id": assertion_id, "job": job["id"], "document": job["source_id"], "predicate": relationship["predicate"], "quote": relationship["quote"], "conditions": json.dumps(relationship["conditions"]), "polarity": relationship["polarity"], "start": start, "end": start + len(relationship["quote"]), "vector": fact_vectors[ordinal], "model": job["configuration"]["embeddingModel"]})
            graph.query("MATCH (a:Assertion {id:$id}) OPTIONAL MATCH (a)-[r:SUBJECT|OBJECT]->() DELETE r", {"id": assertion_id})
            graph.query("MATCH ()-[r:RELATES {assertionId:$id}]->() DELETE r", {"id": assertion_id})
            graph.query("MATCH (a:Assertion {id:$id}),(s:Entity {id:$subject}),(o:Entity {id:$object}) MERGE (a)-[:SUBJECT]->(s) MERGE (a)-[:OBJECT]->(o) MERGE (s)-[r:RELATES {assertionId:$id}]->(o) SET r.predicate=$predicate,r.rel_type=$predicate,r.jobId=$job,r.sourceId=$source,r.active=false", {"id": assertion_id, "subject": local[relationship["subject"]], "object": local[relationship["object"]], "predicate": relationship["predicate"], "job": job["id"], "source": job["source_id"]})
            assertion_count += 1
        publication_chunks.append({**chunk, "documentId": job["source_id"], "revisionId": job["revision"], "processingVersion": job["processing_version"], "sectionId": section_id, "sectionIds": [section["id"] for section in related_sections], "sectionTitle": primary["title"], "sourceUrl": metadata.get("sourceUrl") or job["source_url"], "locationKind": "source"})

    payload = {**metadata, "id": job["source_id"], "revisionId": job["revision"], "processingVersion": job["processing_version"], "rawPath": job["original_path"], "title": title, "text": document["text"], "textLength": len(document["text"]), "sections": sections, "chunks": publication_chunks, "entities": list(entities.values()), "sourceUrl": metadata.get("sourceUrl") or job["source_url"], "offsetUnit": "unicode_codepoint", "blocks": document["blocks"], "normalization": document["normalization"], "extractionBoundary": "GLiNER candidate recognition and source-grounded LLM assertions; exact support is structurally verified, scientific correctness has not been independently reviewed."}
    from app.services.corpus import publish_document
    counts = {"documents": 1, "sections": len(sections), "chunks": len(chunks), "entities": len(entities), "mentions": mention_count, "assertions": assertion_count, "graph": semantic_graph_name(job["configuration"])}
    with connection() as conn:
        conn.execute("UPDATE ingestion_publications SET active=false WHERE source_id=%s", (job["source_id"],))
        publish_document(payload, conn)
        conn.execute("INSERT INTO ingestion_publications(job_id,source_id,counts,active) VALUES(%s,%s,%s,false) ON CONFLICT(job_id) DO UPDATE SET active=false,counts=excluded.counts,published_at=now()", (job["id"], job["source_id"], Jsonb(counts)))
    graph.query("MATCH (d:Document {id:$source}) SET d.active=true,d.activeJobId=$job,d.title=$title,d.revisionId=$revision,d.sourceUrl=$url WITH d MATCH (n) WHERE n.documentId=$source OR n.sourceId=$source SET n.active=CASE WHEN (n.jobId=$job OR n.id=$job) AND coalesce(n.projectionCurrent,true) THEN true ELSE false END WITH DISTINCT d OPTIONAL MATCH ()-[r:RELATES]->() WHERE r.sourceId=$source SET r.active=(r.jobId=$job) WITH DISTINCT d MATCH (e:Entity) OPTIONAL MATCH (m:Mention {active:true})-[:RESOLVED_TO]->(e) WITH e,count(m) AS mentions SET e.active=(mentions>0)", {"source": job["source_id"], "job": job["id"], "title": title, "revision": job["revision"], "url": metadata.get("sourceUrl") or job["source_url"] or ""})
    graph.query("MATCH (r:SourceRevision {id:$job}) SET r.graphComplete=true", {"job": job["id"]})
    with connection() as conn:
        conn.execute("UPDATE ingestion_publications SET active=false WHERE source_id=%s AND job_id<>%s", (job["source_id"], job["id"]))
        for canonical_id, aliases in accepted_aliases.items():
            conn.execute("UPDATE ingestion_entities SET aliases=(SELECT jsonb_agg(DISTINCT value) FROM jsonb_array_elements(aliases || %s::jsonb)) WHERE id=%s", (Jsonb(sorted(aliases)), canonical_id))
        conn.execute("UPDATE ingestion_publications SET active=true,published_at=now() WHERE job_id=%s", (job["id"],))
    return counts
