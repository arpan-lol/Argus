import json
import math

from falkordb import FalkorDB
from psycopg.types.json import Jsonb

from app.config import settings
from app.database import connection

from .config import fingerprint
from .extraction import source_span
from .structure import sections_for, chunk_sections


def semantic_graph_name(config):
    space = [config["provider"], config["embeddingModel"], config["embeddingDimensions"]]
    resource = config.get("embeddingResourceIdentity") or config.get("embeddingBaseUrl")
    if resource:
        space.append(resource)
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


def supported_spans(chunk, record):
    quote = record["quote"]
    spans = record.get("sourceSpans")
    if spans is None:
        spans = []
        cursor = 0
        while quote and (start := chunk["text"].find(quote, cursor)) >= 0:
            spans.append(source_span(chunk, start, start + len(quote)))
            cursor = start + 1
    if not spans:
        raise ValueError("Published source records require an exact source occurrence")
    verified = []
    for span in spans:
        start, end = span.get("chunkStart"), span.get("chunkEnd")
        if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
            raise ValueError("Published source occurrence requires integer offsets")
        if not 0 <= start < end <= len(chunk["text"]) or chunk["text"][start:end] != quote:
            raise ValueError("Published source occurrence does not match its source text")
        expected = source_span(chunk, start, end)
        if any(span.get(key) != expected[key] for key in ("startOffset", "endOffset", "offsetUnit")):
            raise ValueError("Published source occurrence absolute offsets are inconsistent")
        if expected not in verified:
            verified.append(expected)
    verified.sort(key=lambda span: (span["chunkStart"], span["chunkEnd"]))
    primary = record.get("sourceSpan")
    if primary is not None and primary not in verified:
        raise ValueError("Primary source occurrence is not one of the recorded exact occurrences")
    return verified, primary or verified[0], "multiple_occurrences" if len(verified) > 1 else "exact"


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
    affected_entities = {row[0] for row in graph.query("MATCH (m:Mention {documentId:$source})-[:RESOLVED_TO]->(e:Entity) RETURN DISTINCT e.id", {"source": job["source_id"]}).result_set}
    for label in ("Chunk", "Entity"):
        index(graph, label, job["configuration"]["embeddingDimensions"])
    for label in ("Document", "SourceRevision", "Section", "Chunk", "Entity", "Mention", "Assertion", "ResolutionDecision"):
        try:
            graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
        except Exception as error:
            if "already" not in str(error).lower() and "exists" not in str(error).lower():
                raise
    graph.query("MERGE (d:Document {id:$id}) ON CREATE SET d.title=$title,d.active=false MERGE (r:SourceRevision {id:$job}) SET r.sourceId=$id,r.revision=$revision,r.processingVersion=$version,r.active=false MERGE (d)-[:HAS_REVISION]->(r)", {"id": job["source_id"], "job": job["id"], "title": title, "revision": job["revision"], "version": job["processing_version"]})
    sections = sections_for(document, job)
    graph.query("MATCH (s:Section {documentId:$source}) WHERE s.jobId=$job SET s.projectionCurrent=false", {"source": job["source_id"], "job": job["id"]})
    for section in sections:
        graph.query("MATCH (d:Document {id:$document}),(r:SourceRevision {id:$job}) MERGE (s:Section {id:$id}) SET s.documentId=$document,s.jobId=$job,s.title=$title,s.startOffset=$start,s.endOffset=$end,s.projectionCurrent=true,s.active=false MERGE (d)-[:HAS_SECTION]->(s) MERGE (r)-[:HAS_SECTION]->(s)", {"document": job["source_id"], "job": job["id"], "id": section["id"], "title": section["title"], "start": section["startOffset"], "end": section["endOffset"]})
    mention_count = assertion_count = fallback_count = 0
    extraction_warnings = []
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
        extraction_metadata = extraction.get("metadata", {})
        if extraction_metadata.get("fallback"):
            fallback_count += 1
            extraction_warnings.append({"chunkId": chunk["id"], "code": "gliner_only_fallback", "message": extraction_metadata.get("warning", "Only local mentions were retained; connections were not extracted."), "reason": extraction_metadata.get("reason")})
        graph.query("MATCH (c:Chunk {id:$id}) SET c.extractionMethod=$method,c.llmVerified=$verified,c.extractionFallback=$fallback,c.extractionMetadata=$metadata", {"id": chunk["id"], "method": extraction_metadata.get("method", "unknown"), "verified": extraction_metadata.get("llmVerified") is True, "fallback": bool(extraction_metadata.get("fallback")), "metadata": json.dumps(extraction_metadata)})
        facts = extraction["relationships"]
        graph.query("MATCH (c:Chunk {id:$id}) OPTIONAL MATCH (c)-[r:MENTIONS]->() DELETE r", {"id": chunk["id"]})
        local = {}
        for entity in extraction["entities"]:
            mention_id = "mention:" + fingerprint([chunk["id"], entity["key"]])
            resolved = pipeline.item(job["id"], "resolve", mention_id)
            with connection() as conn:
                decision = conn.execute("SELECT * FROM ingestion_resolution_decisions WHERE id=%s", (resolved["decisionId"],)).fetchone()
                canonical = conn.execute("SELECT * FROM ingestion_entities WHERE id=%s", (decision["canonical_id"],)).fetchone()
            canonical_id = canonical["id"]
            affected_entities.add(canonical_id)
            accepted_aliases.setdefault(canonical_id, set()).add(entity["name"])
            local[entity["key"]] = canonical_id
            spans, primary_span, span_status = supported_spans(chunk, entity)
            start, end = primary_span["startOffset"], primary_span["endOffset"]
            method = entity.get("extractionMethod", extraction_metadata.get("method", "unknown"))
            llm_verified = entity.get("llmVerified", extraction_metadata.get("llmVerified")) is True
            graph.query("MATCH (c:Chunk {id:$chunk}) MERGE (e:Entity {id:$entity}) ON CREATE SET e.label=$label,e.type=$type,e.description=$description,e.embedding=vecf32($vector),e.embeddingModel=$model MERGE (m:Mention {id:$mention}) SET m.jobId=$job,m.text=$quote,m.startOffset=$start,m.endOffset=$end,m.sourceSpans=$spans,m.sourceSpanStatus=$spanStatus,m.sourceSpanAmbiguous=$ambiguous,m.extractionMethod=$method,m.llmVerified=$verified,m.confidence=$confidence,m.documentId=$document,m.active=false MERGE (c)-[:HAS_MENTION]->(m)", {"chunk": chunk["id"], "entity": canonical_id, "label": canonical["label"], "type": canonical["entity_type"], "description": canonical["description"], "vector": canonical["embedding"], "model": canonical["embedding_model"], "mention": mention_id, "job": job["id"], "document": job["source_id"], "quote": entity["quote"], "start": start, "end": end, "spans": json.dumps(spans), "spanStatus": span_status, "ambiguous": len(spans) > 1, "method": method, "verified": llm_verified, "confidence": entity.get("confidence")})
            graph.query("MATCH (m:Mention {id:$mention}) OPTIONAL MATCH (m)-[old:RESOLVED_TO]->() DELETE old", {"mention": mention_id})
            graph.query("MATCH (c:Chunk {id:$chunk}),(m:Mention {id:$mention}),(e:Entity {id:$entity}) MERGE (m)-[:RESOLVED_TO]->(e) MERGE (c)-[:MENTIONS]->(e) MERGE (r:ResolutionDecision {id:$decision}) SET r.jobId=$job,r.decision=$verdict,r.rationale=$rationale,r.reverted=$reverted MERGE (r)-[:RESOLVES]->(m)", {"chunk": chunk["id"], "mention": mention_id, "entity": canonical_id, "decision": decision["id"], "job": job["id"], "verdict": decision["decision"], "rationale": decision["rationale"], "reverted": decision["reverted"]})
            published_entity = entities.setdefault(canonical_id, {"id": canonical_id, "label": canonical["label"], "type": canonical["entity_type"], "extractionMethods": [], "llmVerified": True, "mentions": []})
            if method not in published_entity["extractionMethods"]:
                published_entity["extractionMethods"].append(method)
            published_entity["extractionMethod"] = method if len(published_entity["extractionMethods"]) == 1 else "mixed"
            published_entity["llmVerified"] = published_entity["llmVerified"] and llm_verified
            published_entity["mentions"].append({"id": mention_id, "chunkId": chunk["id"], "startOffset": start, "endOffset": end, "sourceSpans": spans, "sourceSpanStatus": span_status, "sourceSpanAmbiguous": len(spans) > 1, "text": entity["quote"], "extractionMethod": method, "llmVerified": llm_verified, "confidence": entity.get("confidence"), "duplicateCheckingDeferred": decision["decision"] == "deferred"})
            mention_count += 1
        for ordinal, relationship in enumerate(extraction["relationships"]):
            assertion_id = "assertion:" + fingerprint([job["id"], chunk["id"], ordinal, relationship])
            spans, primary_span, span_status = supported_spans(chunk, relationship)
            start, end = primary_span["startOffset"], primary_span["endOffset"]
            graph.query("MATCH (c:Chunk {id:$chunk}) MERGE (a:Assertion {id:$id}) SET a.jobId=$job,a.documentId=$document,a.predicate=$predicate,a.quote=$quote,a.conditions=$conditions,a.polarity=$polarity,a.startOffset=$start,a.endOffset=$end,a.sourceSpans=$spans,a.sourceSpanStatus=$spanStatus,a.sourceSpanAmbiguous=$ambiguous,a.extractionMethod=$method,a.llmVerified=$verified,a.active=false MERGE (a)-[:SUPPORTED_BY]->(c)", {"chunk": chunk["id"], "id": assertion_id, "job": job["id"], "document": job["source_id"], "predicate": relationship["predicate"], "quote": relationship["quote"], "conditions": json.dumps(relationship["conditions"]), "polarity": relationship["polarity"], "start": start, "end": end, "spans": json.dumps(spans), "spanStatus": span_status, "ambiguous": len(spans) > 1, "method": relationship.get("extractionMethod", extraction_metadata.get("method", "unknown")), "verified": relationship.get("llmVerified", extraction_metadata.get("llmVerified")) is True})
            graph.query("MATCH (a:Assertion {id:$id})-[:SUBJECT]->(s:Entity)-[r:RELATES]->() WHERE r.assertionId=$id DELETE r", {"id": assertion_id})
            graph.query("MATCH (a:Assertion {id:$id}) OPTIONAL MATCH (a)-[r:SUBJECT|OBJECT]->() DELETE r", {"id": assertion_id})
            graph.query("MATCH (a:Assertion {id:$id}),(s:Entity {id:$subject}),(o:Entity {id:$object}) MERGE (a)-[:SUBJECT]->(s) MERGE (a)-[:OBJECT]->(o) MERGE (s)-[r:RELATES {assertionId:$id}]->(o) SET r.predicate=$predicate,r.rel_type=$predicate,r.jobId=$job,r.sourceId=$source,r.active=false", {"id": assertion_id, "subject": local[relationship["subject"]], "object": local[relationship["object"]], "predicate": relationship["predicate"], "job": job["id"], "source": job["source_id"]})
            assertion_count += 1
            graph.query("MATCH (a:Assertion {id:$id}),(s:Entity)-[r:RELATES {assertionId:$id}]->() SET a.confidence=$confidence,a.polarityStatus=$polarityStatus,r.confidence=$confidence,r.extractionMethod=$method", {"id": assertion_id, "confidence": relationship.get("confidence"), "polarityStatus": relationship.get("polarityStatus", "source_classified"), "method": relationship.get("extractionMethod", extraction_metadata.get("method", "unknown"))})
        publication_chunks.append({**chunk, "documentId": job["source_id"], "revisionId": job["revision"], "processingVersion": job["processing_version"], "sectionId": section_id, "sectionIds": [section["id"] for section in related_sections], "sectionTitle": primary["title"], "sourceUrl": metadata.get("sourceUrl") or job["source_url"], "locationKind": "source", "extractionMetadata": extraction_metadata})

    from .code_publication import publish_code_structure
    code = publish_code_structure(graph, document, chunks, job, semantic_graph_name(job["configuration"]))
    entities.update(code["entities"])
    affected_entities.update(code["entities"])
    mention_count += code["mentions"]
    assertion_count += code["assertions"]
    extraction_quality = {"fallbackChunks": fallback_count, "quality": "local_model_and_parser", "warnings": [*metadata.get("warnings", []), *extraction_warnings], "sourceCoverage": metadata.get("sourceCoverage"), "structuralRelationships": code["assertions"]}
    payload = {**metadata, "id": job["source_id"], "revisionId": job["revision"], "processingVersion": job["processing_version"], "rawPath": job["original_path"], "title": title, "text": document["text"], "textLength": len(document["text"]), "sections": sections, "chunks": publication_chunks, "entities": list(entities.values()), "sourceUrl": metadata.get("sourceUrl") or job["source_url"], "offsetUnit": "unicode_codepoint", "blocks": document["blocks"], "normalization": document["normalization"], "extractionQuality": extraction_quality, "warnings": extraction_quality["warnings"], "extractionBoundary": "Source spans and structure checked. Semantic relationships are extracted locally by GLiNER-relex; code relationships come from Python syntax. Unresolved call names do not establish runtime targets."}
    from app.services.corpus import publish_document
    counts = {"documents": 1, "sections": len(sections), "chunks": len(chunks), "entities": len(entities), "mentions": mention_count, "assertions": assertion_count, "graph": semantic_graph_name(job["configuration"]), **extraction_quality}
    with connection() as conn:
        conn.execute("UPDATE ingestion_publications SET active=false WHERE source_id=%s", (job["source_id"],))
        publish_document(payload, conn)
        conn.execute("INSERT INTO ingestion_publications(job_id,source_id,counts,active) VALUES(%s,%s,%s,false) ON CONFLICT(job_id) DO UPDATE SET active=false,counts=excluded.counts,published_at=now()", (job["id"], job["source_id"], Jsonb(counts)))
    for label, property_name in (("SourceRevision", "sourceId"), ("Section", "documentId"), ("Chunk", "documentId"), ("Mention", "documentId"), ("Assertion", "documentId")):
        graph.query(f"MATCH (n:{label} {{{property_name}:$source}}) SET n.active=CASE WHEN (n.jobId=$job OR n.id=$job) AND coalesce(n.projectionCurrent,true) THEN true ELSE false END", {"source": job["source_id"], "job": job["id"]})
    graph.query("MATCH (a:Assertion {documentId:$source})-[:SUBJECT]->(s:Entity)-[r:RELATES]->() WHERE r.assertionId=a.id AND r.sourceId=$source SET r.active=(r.jobId=$job)", {"source": job["source_id"], "job": job["id"]})
    if affected_entities:
        graph.query("UNWIND $ids AS id MATCH (e:Entity {id:id}) OPTIONAL MATCH (e)<-[:RESOLVED_TO]-(m:Mention) WHERE m.active=true WITH e,count(m) AS mentions SET e.active=(mentions>0)", {"ids": sorted(affected_entities)})
    graph.query("MATCH (d:Document {id:$source}) SET d.active=true,d.activeJobId=$job,d.title=$title,d.revisionId=$revision,d.sourceUrl=$url,d.extractionQuality=$quality,d.sourceCoverage=$coverage", {"source": job["source_id"], "job": job["id"], "title": title, "revision": job["revision"], "url": metadata.get("sourceUrl") or job["source_url"] or "", "quality": json.dumps(extraction_quality), "coverage": json.dumps(metadata.get("sourceCoverage"))})
    graph.query("MATCH (r:SourceRevision {id:$job}) SET r.graphComplete=true", {"job": job["id"]})
    with connection() as conn:
        conn.execute("UPDATE ingestion_publications SET active=false WHERE source_id=%s AND job_id<>%s", (job["source_id"], job["id"]))
        for canonical_id, aliases in accepted_aliases.items():
            conn.execute("UPDATE ingestion_entities SET aliases=(SELECT jsonb_agg(DISTINCT value) FROM jsonb_array_elements(aliases || %s::jsonb)) WHERE id=%s", (Jsonb(sorted(aliases)), canonical_id))
        conn.execute("UPDATE ingestion_publications SET active=true,published_at=now() WHERE job_id=%s", (job["id"],))
    return counts
