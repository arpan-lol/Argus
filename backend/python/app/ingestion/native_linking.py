import json
import re

from app.database import connection
from .config import fingerprint
from .graph_batch import GraphWrites, write_batches


MAX_ACTIVE_CHUNKS = 10000
MAX_EXTERNAL_IDS = 10000
MAX_REFERENCE_MENTIONS = 50000


def _external_id_mapping(document, native_canonical_ids):
    candidates = {}
    blocks = document.get("blocks", [])
    records_truncated = len(blocks) > MAX_EXTERNAL_IDS
    for block in blocks[:MAX_EXTERNAL_IDS]:
        structured = block.get("structured") or {}
        record = structured.get("nativeRecord")
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            continue
        canonical_id = native_canonical_ids.get(record["id"])
        if not canonical_id:
            continue
        for reference in record.get("external_references", []):
            external_id = reference.get("external_id") if isinstance(reference, dict) else None
            if not isinstance(external_id, str):
                continue
            external_id = external_id.strip()
            if len(external_id) < 2 or len(external_id) > 128 or not re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]*", external_id) or not any(char.isdigit() for char in external_id):
                continue
            candidates.setdefault(external_id, set()).add((record["id"], canonical_id))
    ambiguous = {external_id for external_id, targets in candidates.items() if len(targets) != 1}
    resolved = {external_id: next(iter(targets)) for external_id, targets in candidates.items() if len(targets) == 1}
    truncated = records_truncated or len(resolved) > MAX_EXTERNAL_IDS
    if truncated:
        resolved = dict(sorted(resolved.items())[:MAX_EXTERNAL_IDS])
    return resolved, len(ambiguous), truncated


def _native_canonical_ids(pipeline, job, chunks):
    identifiers = {}
    ambiguous = set()
    with connection() as conn:
        saved = {(row["stage"], row["item_id"]): row["payload"] for row in conn.execute("SELECT stage,item_id,payload FROM ingestion_items WHERE job_id=%s AND stage=ANY(%s)", (job["id"], ["extract", "resolve"])).fetchall()}
    for chunk in chunks[:MAX_ACTIVE_CHUNKS]:
        extracted = saved.get(("extract", chunk["id"])) or {}
        for entity in extracted.get("entities", []):
            native_id = entity.get("nativeResolverKey")
            if not native_id or entity.get("nativeFormat") != "stix":
                continue
            mention_id = "mention:" + fingerprint([chunk["id"], entity["key"]])
            resolved = saved.get(("resolve", mention_id)) or {}
            canonical_id = resolved.get("canonicalId")
            if not canonical_id:
                continue
            if native_id in identifiers and identifiers[native_id] != canonical_id:
                ambiguous.add(native_id)
            else:
                identifiers[native_id] = canonical_id
    for native_id in ambiguous:
        identifiers.pop(native_id, None)
    return identifiers, len(ambiguous), len(chunks) > MAX_ACTIVE_CHUNKS


def _deactivate_prior_links(graph, source_id):
    old_entities = [row[0] for row in graph.query("MATCH (m:Mention {nativeAnchorSourceId:$source})-[:RESOLVED_TO]->(e:Entity) RETURN DISTINCT e.id", {"source": source_id}).result_set]
    graph.query("MATCH (m:Mention {nativeAnchorSourceId:$source}) OPTIONAL MATCH (c:Chunk)-[:HAS_MENTION]->(m) OPTIONAL MATCH (m)-[:RESOLVED_TO]->(e:Entity) SET m.active=false WITH c,e WHERE c IS NOT NULL AND e IS NOT NULL OPTIONAL MATCH (c)-[:HAS_MENTION]->(other:Mention)-[:RESOLVED_TO]->(e) WHERE other.active=true WITH c,e,count(other) AS activeSupport WHERE activeSupport=0 MATCH (c)-[r:MENTIONS]->(e) DELETE r", {"source": source_id})
    if old_entities:
        write_batches(graph, "UNWIND $ids AS id MATCH (e:Entity {id:id}) OPTIONAL MATCH (e)<-[:RESOLVED_TO]-(m:Mention) WHERE m.active=true WITH e,count(m) AS mentions SET e.active=(mentions>0)", "ids", sorted(set(old_entities)))


def link_native_references(graph, document, chunks, job, pipeline):
    native = document.get("metadata", {}).get("parser") == "stix_native_json"
    ambiguous_native_ids = 0
    native_chunks_truncated = False
    if native:
        native_ids, ambiguous_native_ids, native_chunks_truncated = _native_canonical_ids(pipeline, job, chunks)
        mapping, ambiguous_external_ids, external_ids_truncated = _external_id_mapping(document, native_ids)
        external_ids = {identifier: (*target, job['id'], job['source_id']) for identifier, target in mapping.items()}
        pipeline.save_item(job['id'], 'native_external_ids', 'current', {'targets': external_ids})
        _deactivate_prior_links(graph, job['source_id'])
    else:
        with connection() as conn:
            registries = conn.execute("SELECT i.payload FROM ingestion_items i JOIN ingestion_publications p ON p.job_id=i.job_id JOIN ingestion_jobs j ON j.id=p.job_id WHERE j.project_id=%s AND p.active AND i.stage='native_external_ids' AND i.item_id='current' ORDER BY p.published_at DESC LIMIT 65", (job['configuration'].get('projectId'),)).fetchall()
        candidates = {}
        external_ids_truncated = len(registries) > 64
        for row in registries[:64]:
            for identifier, target in row['payload']['targets'].items():
                if len(candidates) >= MAX_EXTERNAL_IDS and identifier not in candidates:
                    external_ids_truncated = True
                    continue
                candidates.setdefault(identifier, {})[target[1]] = tuple(target)
        ambiguous_external_ids = sum(len(targets) != 1 for targets in candidates.values())
        external_ids = {identifier: next(iter(targets.values())) for identifier, targets in candidates.items() if len(targets) == 1}
    if not external_ids:
        return {"nativeReferenceMentions": 0, "crossFileChunks": 0, "scannedActiveChunks": 0, "ambiguousNativeIds": ambiguous_native_ids, "ambiguousExternalIds": ambiguous_external_ids, "truncated": external_ids_truncated or native_chunks_truncated}

    patterns = sorted(external_ids, key=lambda value: (-len(value), value))
    matcher = re.compile(r"(?<![\w.-])(?:" + "|".join(re.escape(value) for value in patterns) + r")(?![\w.-])")
    if native:
        rows = graph.query("MATCH (c:Chunk) WHERE c.active=true AND c.text IS NOT NULL WITH c ORDER BY c.id LIMIT $limit RETURN c.id,c.documentId,c.jobId,c.text,c.startOffset", {"limit": MAX_ACTIVE_CHUNKS + 1}).result_set
    else:
        rows = [(chunk["id"], job["source_id"], job["id"], chunk["text"], chunk["startOffset"]) for chunk in chunks[:MAX_ACTIVE_CHUNKS + 1]]
    scan_truncated = len(rows) > MAX_ACTIVE_CHUNKS
    rows = rows[:MAX_ACTIVE_CHUNKS]

    writes = GraphWrites(graph)
    count = 0
    cross_file_chunks = set()
    affected_entities = set()
    mentions_truncated = False
    for chunk_id, document_id, _, text, chunk_start in rows:
        if not isinstance(text, str):
            continue
        for match in matcher.finditer(text):
            external_id = match.group(0)
            target = external_ids.get(external_id)
            if target is None:
                continue
            if count >= MAX_REFERENCE_MENTIONS:
                mentions_truncated = True
                break
            native_id, canonical_id, anchor_job, anchor_source = target
            affected_entities.add(canonical_id)
            start, end = match.span()
            quote = text[start:end]
            span = {"startOffset": int(chunk_start) + start, "endOffset": int(chunk_start) + end, "chunkStart": start, "chunkEnd": end, "offsetUnit": "unicode_codepoint"}
            mention_id = "mention:native-ref:" + fingerprint([chunk_id, anchor_job, anchor_source, native_id, external_id, start, end])
            writes.add("MATCH (c:Chunk {id:$chunk}),(e:Entity {id:$entity}) MERGE (m:Mention {id:$mention}) SET m.jobId=c.jobId,m.documentId=c.documentId,m.text=$quote,m.startOffset=$start,m.endOffset=$end,m.sourceSpans=$spans,m.sourceSpanStatus='exact',m.sourceSpanAmbiguous=false,m.extractionMethod='native_identifier_reference',m.llmVerified=false,m.identityStatus='stable_external_identifier',m.nativeResolverKey=$externalId,m.nativeFormat='stix',m.nativeAnchorJobId=$anchorJob,m.nativeAnchorSourceId=$anchorSource,m.nativeAnchorRecordId=$nativeId,m.active=c.active MERGE (c)-[:HAS_MENTION]->(m) MERGE (m)-[:RESOLVED_TO]->(e) MERGE (c)-[:MENTIONS]->(e)", {"chunk": chunk_id, "entity": canonical_id, "mention": mention_id, "quote": quote, "start": span["startOffset"], "end": span["endOffset"], "spans": json.dumps([span]), "externalId": external_id, "anchorJob": anchor_job, "anchorSource": anchor_source, "nativeId": native_id})
            count += 1
            if document_id != anchor_source:
                cross_file_chunks.add(chunk_id)
        if mentions_truncated:
            break
    writes.flush()
    affected_entities.update(target[1] for target in external_ids.values())
    if affected_entities:
        write_batches(graph, "UNWIND $ids AS id MATCH (e:Entity {id:id}) OPTIONAL MATCH (e)<-[:RESOLVED_TO]-(m:Mention) WHERE m.active=true WITH e,count(m) AS mentions SET e.active=(mentions>0)", "ids", sorted(affected_entities))
    return {"nativeReferenceMentions": count, "crossFileChunks": len(cross_file_chunks), "scannedActiveChunks": len(rows), "ambiguousNativeIds": ambiguous_native_ids, "ambiguousExternalIds": ambiguous_external_ids, "truncated": scan_truncated or external_ids_truncated or native_chunks_truncated or mentions_truncated}
