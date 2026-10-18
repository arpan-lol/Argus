import argparse
import json
import math
import re
import sys
from pathlib import Path

from falkordb import FalkorDB
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.database import connection, migrate
from app.ingestion.config import fingerprint, processing_config
from app.ingestion.publication import semantic_graph_name
from app.services.corpus import publish_document


QUALITY = {
    "fallbackChunks": 0,
    "quality": "benchmark_corpus",
    "warnings": [
        "Source published directly by scripts/publish_benchmark.py without the ingestion pipeline; "
        "fact lines were parsed deterministically from benchmarks/graph-rag-fingerprint/benchmark-corpus.md and no model processed the text.",
    ],
    "sourceCoverage": None,
}
PROCESS = {
    "method": "benchmark_corpus",
    "llmVerified": False,
    "fallback": False,
    "spanStatus": "exact",
    "label": "Deterministic fact-line parse by scripts/publish_benchmark.py; no ingestion, parsing or model processing was run.",
}
SLUG = "graph-rag-fingerprint-benchmark-corpus"
CORPUS_PATH = Path(__file__).resolve().parents[3] / "benchmarks" / "graph-rag-fingerprint" / "benchmark-corpus.md"

SECTION_HEADER = re.compile(r"^## (\S+) - (\S+) - (\S+)$")
FACT_LINE = re.compile(r"^(?:- )?`(.+?) -> (!?[A-Z_]+) -> (.+?)`( \(.*\))?\.?$")
LINK_LINES = ("Supersedes:", "Restates:")


def parse_corpus(text):
    records = []
    current = None
    preamble = []
    for line in text.splitlines():
        line = line.rstrip()
        if line == "End of corpus.":
            break
        match = SECTION_HEADER.match(line)
        if match:
            if current:
                records.append(current)
            current = {"id": match.group(1), "kind": match.group(2), "stamp": match.group(3), "title": None, "body": [], "facts": []}
            continue
        if current is None:
            if line:
                preamble.append(line)
            continue
        fact = FACT_LINE.match(line)
        if fact:
            raw_note = (fact.group(4) or "").strip()
            note = raw_note[1:-1] if raw_note.startswith("(") else None
            current["facts"].append({"subject": fact.group(1), "predicate": fact.group(2), "object": fact.group(3), "note": note})
            current["body"].append(line[2:] if line.startswith("- ") else line)
        elif line.startswith(LINK_LINES) or line.startswith("#") or not line:
            continue
        elif current["title"] is None:
            current["title"] = line
        else:
            current["body"].append(line)
    if current:
        records.append(current)
    return records, "\n".join(preamble)


def spans(text, query):
    cursor = 0
    result = []
    while True:
        index = text.find(query, cursor)
        if index < 0:
            break
        result.append(index)
        cursor = index + 1
    return result


def chunk_text(record):
    head = record["title"] or record["id"] + " " + record["kind"]
    return head + "\n\n" + "\n".join(record["body"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", help="Existing project id; omit for the workspace scope")
    args = parser.parse_args()
    project_id = args.project
    if project_id:
        with connection() as conn:
            if not conn.execute("SELECT 1 FROM projects WHERE id=%s", (project_id,)).fetchone():
                raise SystemExit("Unknown project id")
    migrate()

    text = CORPUS_PATH.read_text(encoding="utf-8")
    records, preamble = parse_corpus(text)
    assert len(records) == 161, "expected 161 corpus sections, parsed " + str(len(records))
    fact_lines = sum(len(r["facts"]) for r in records)
    assert fact_lines == 323, "expected 323 corpus fact lines, parsed " + str(fact_lines)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import benchmark_model as m

    names = {}
    for eid, (etype, name, desc) in m.E.items():
        assert name not in names, "duplicate entity name " + name
        names[name] = eid

    authors = ["Argus Benchmark Fixture"]
    processed_at = "2026-10-18T00:00:00Z"
    paragraphs = []
    for record in records:
        body = chunk_text(record)
        if not body:
            raise SystemExit("Empty record body " + record["id"])
        paragraphs.append(body)
    join = "\n\n"
    doc_text = preamble_text = preamble + "\n\n" if preamble else ""
    doc_text = preamble + ("\n\n" if preamble else "") + join.join(paragraphs)

    config = processing_config(project_id)
    revision = fingerprint([doc_text])
    version = fingerprint(config)
    graph_name = semantic_graph_name(config)
    source_id = "source:" + fingerprint([config.get("projectId") or "workspace", SLUG])
    digest = fingerprint([doc_text])

    paragraph_spans = []
    cursor = len(preamble) + (2 if preamble else 0)
    for paragraph in paragraphs:
        paragraph_spans.append((cursor, cursor + len(paragraph)))
        cursor += len(paragraph) + 2

    chunks = []
    chunk_section = []
    for ordinal, record in enumerate(records):
        section_id = "section:" + fingerprint([ordinal, graph_name, SLUG])
        title = record["title"] or record["id"]
        chunks.append({
            "id": "chunk:" + fingerprint(["benchmark", SLUG, config.get("semanticGraph"), fingerprint(config), record["id"]]),
            "ordinal": ordinal,
            "text": doc_text[paragraph_spans[ordinal][0]:paragraph_spans[ordinal][1]],
            "startOffset": paragraph_spans[ordinal][0],
            "endOffset": paragraph_spans[ordinal][1],
            "tokenCount": None,
            "offsetUnit": "unicode_code_point",
            "blockOrdinals": [ordinal],
        })
        chunk_section.append((section_id, ordinal, title))

    mentions = []
    entities_payload = []
    entity_ids = {}
    for name, eid in names.items():
        entity_id = "entity:" + fingerprint([graph_name, name.strip().lower(), m.E[eid][0].strip().lower()])
        entity_ids[eid] = (entity_id, m.E[eid])
        etype, name_clean, desc = m.E[eid]
        found_chunks = []
        for chunk, (sid, ordinal, title) in zip(chunks, chunk_section, strict=True):
            hits = spans(chunk["text"], name)
            if not hits:
                continue
            found_chunks.append(chunk)
            chunk_offsets = []
            for hit in hits:
                chunk_offsets.append({
                    "chunkStart": hit,
                    "chunkEnd": hit + len(name),
                    "startOffset": chunk["startOffset"] + hit,
                    "endOffset": chunk["startOffset"] + hit + len(name),
                    "offsetUnit": "unicode_code_point",
                })
            primary = chunk_offsets[0]
            key = eid
            mentions.append({
                "id": "mention:" + fingerprint([chunk["id"], key]),
                "chunkId": chunk["id"],
                "key": key,
                "quote": name,
                "startOffset": primary["startOffset"],
                "endOffset": primary["endOffset"],
                "sourceSpans": chunk_offsets,
                "sourceSpanStatus": "multiple_occurrences" if len(hits) > 1 else "exact",
            })
        entities_payload.append({
            "id": entity_id,
            "label": name_clean,
            "type": etype,
            "extractionMethod": PROCESS["method"],
            "llmVerified": False,
            "mention_count": sum(1 for mention in mentions if mention["key"] == eid),
            "description": desc,
        })
    entities_payload.sort(key=lambda e: e["label"])

    assertions = []
    for chunk_index, record in enumerate(records):
        chunk = chunks[chunk_index]
        body = chunk["text"]
        for fact in record["facts"]:
            line = "`" + fact["subject"] + " -> " + fact["predicate"] + " -> " + fact["object"] + "`"
            if fact["note"]:
                line += " (" + fact["note"] + ")"
            hits = spans(body, line)
            if not hits:
                raise SystemExit("Fact line not found in its chunk: " + record["id"] + " :: " + line[:70])
            start = hits[0]
            all_hits = [
                {"chunkStart": hit, "chunkEnd": hit + len(line), "startOffset": chunk["startOffset"] + hit, "endOffset": chunk["startOffset"] + hit + len(line), "offsetUnit": "unicode_code_point"}
                for hit in hits
            ]
            polarity = "negated" if fact["predicate"].startswith("!") else "affirmed"
            predicate = fact["predicate"].lstrip("!")
            subject_id = names.get(fact["subject"])
            object_id = names.get(fact["object"])
            if not subject_id or not object_id:
                raise SystemExit("Unknown fact endpoint in " + record["id"] + " :: " + fact["subject"] + " -> " + fact["object"])
            conditions = [record["id"], record["kind"], record["stamp"]]
            if fact["note"]:
                conditions.append(fact["note"])
            assertions.append({
                "id": "assertion:" + fingerprint([chunk["id"], fact["subject"], predicate, fact["object"], record["id"]]),
                "chunkId": chunk["id"],
                "predicate": predicate,
                "quote": line,
                "conditions": conditions,
                "polarity": polarity,
                "startOffset": chunk["startOffset"] + start,
                "endOffset": chunk["startOffset"] + start + len(line),
                "sourceSpans": all_hits,
                "sourceSpanStatus": "exact" if len(hits) == 1 else "multiple_occurrences",
                "subject": subject_id,
                "object": object_id,
            })
    assertions.sort(key=lambda a: (a["chunkId"], a["predicate"], a["quote"]))

    original_dir = settings.data_dir / "originals" / digest[:2]
    original_dir.mkdir(parents=True, exist_ok=True)
    original = original_dir / (digest + "-" + SLUG + ".md")
    if not original.exists() or original.read_text(encoding="utf-8") != doc_text:
        original.write_text(doc_text, encoding="utf-8")

    job_id = "job:" + fingerprint([source_id, revision, version])
    payload_chunks = []
    for chunk, (section_id, ordinal, title) in zip(chunks, chunk_section, strict=True):
        payload_chunks.append({
            **chunk, "documentId": source_id, "revisionId": revision, "processingVersion": version,
            "sectionId": section_id, "sectionIds": [section_id], "sectionTitle": title,
            "sourceUrl": None, "locationKind": "source", "extractionMetadata": PROCESS,
            "authors": authors, "processedAt": processed_at, "structuralRank": chunk["ordinal"],
        })

    quality = {**QUALITY, "sourceCoverage": "Synthetic benchmark corpus; full coverage of the fact lines only, authored for Argus retrieval fingerprinting"}
    payload = {
        "id": source_id, "revisionId": revision, "processingVersion": version,
        "rawPath": str(original), "title": "Nimbusfield Logistics benchmark corpus", "text": doc_text, "textLength": len(doc_text),
        "sections": [
            {"id": section_id, "title": title, "ordinal": ordinal + 1, "startOffset": paragraph_spans[o_idx][0], "endOffset": paragraph_spans[o_idx][1], "documentId": source_id, "locationKind": "source", "sourceLocation": None}
            for o_idx, (section_id, ordinal, title) in enumerate(chunk_section)
        ],
        "chunks": payload_chunks,
        "entities": entities_payload,
        "sourceUrl": None, "offsetUnit": "unicode_codepoint",
        "blocks": [], "normalization": {"method": "benchmark_corpus", "steps": ["fact_lines"]},
        "extractionQuality": quality, "warnings": quality["warnings"],
        "extractionBoundary": "Synthetic benchmark corpus; every assertion comes from an exact fact line parsed deterministically and no model extracted anything.",
        "synthetic": True, "fixture": "scripts/publish_benchmark.py", "authors": authors, "processedAt": processed_at,
    }
    counts = {
        "documents": 1, "sections": len(payload["sections"]), "chunks": len(chunks),
        "entities": len(entities_payload), "mentions": len(mentions), "assertions": len(assertions),
        "graph": graph_name, **quality,
    }

    payload["rawPath"] = str(original)
    graph = FalkorDB(host=settings.falkor_host, port=settings.falkor_port).select_graph(graph_name)
    for label, property_name in (("Document", "id"), ("SourceRevision", "sourceId"), ("SourceRevision", "id"), ("Section", "id"), ("Section", "documentId"), ("Chunk", "id"), ("Chunk", "documentId"), ("Chunk", "jobId"), ("Entity", "id"), ("Entity", "label"), ("Mention", "id"), ("Mention", "documentId"), ("Assertion", "id"), ("Assertion", "documentId"), ("Assertion", "jobId")):
        try:
            graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.{property_name})")
        except Exception as error:
            if "already" not in str(error).lower() and "exists" not in str(error).lower():
                raise
    job_title = "Nimbusfield Logistics benchmark corpus"
    graph.query("MERGE (d:Document {id:$id}) SET d.title=$title MERGE (r:SourceRevision {id:$job}) SET r.sourceId=$id,r.revision=$revision,r.processingVersion=$version,r.active=false MERGE (d)-[:HAS_REVISION]->(r)", {"id": source_id, "job": job_id, "title": job_title, "revision": revision, "version": version})
    for eid, (entity_id, types) in entity_ids.items():
        etype, name, desc = types
        graph.query("MERGE (e:Entity {id:$id}) SET e.label=$label,e.type=$type,e.description=$description,e.sourceId=$source", {"id": entity_id, "label": name, "type": etype, "description": desc, "source": source_id})
    for o_idx, (section_id, ordinal, title) in enumerate(chunk_section):
        graph.query("MATCH (d:Document {id:$document}),(r:SourceRevision {id:$job}) MERGE (s:Section {id:$id}) SET s.documentId=$document,s.jobId=$job,s.title=$title,s.startOffset=$start,s.endOffset=$end,s.active=false MERGE (d)-[:HAS_SECTION]->(s) MERGE (r)-[:HAS_SECTION]->(s)", {"document": source_id, "job": job_id, "id": section_id, "title": title, "start": paragraph_spans[o_idx][0], "end": paragraph_spans[o_idx][1]})
    previous = None
    for chunk, (section_id, ordinal, title) in zip(chunks, chunk_section, strict=True):
        graph.query("MATCH (s:Section {id:$section}) MERGE (c:Chunk {id:$id}) SET c.documentId=$document,c.sectionId=$section,c.jobId=$job,c.text=$text,c.ordinal=$ordinal,c.startOffset=$start,c.endOffset=$end,c.extractionMethod=$method,c.llmVerified=$verified,c.extractionFallback=$fallback,c.active=false MERGE (s)-[:HAS_CHUNK]->(c)", {"section": section_id, "id": chunk["id"], "document": source_id, "job": job_id, "text": chunk["text"], "ordinal": chunk["ordinal"], "start": chunk["startOffset"], "end": chunk["endOffset"], "method": PROCESS["method"], "verified": False, "fallback": False})
        if previous:
            graph.query("MATCH (a:Chunk {id:$a}),(b:Chunk {id:$b}) MERGE (a)-[:NEXT_CHUNK {id:$relation}]->(b)", {"a": previous, "b": chunk["id"], "relation": fingerprint([previous, chunk["id"]])})
        previous = chunk["id"]
    for mention in mentions:
        entity_id, entity = entity_ids[mention["key"]]
        graph.query("MATCH (c:Chunk {id:$chunk}),(e:Entity {id:$entity}) MERGE (m:Mention {id:$mention}) SET m.jobId=$job,m.documentId=$document,m.text=$quote,m.startOffset=$start,m.endOffset=$end,m.sourceSpans=$source_spans,m.sourceSpanStatus=$status,m.sourceSpanAmbiguous=$ambiguous,m.extractionMethod=$method,m.llmVerified=$verified,m.active=false MERGE (c)-[:HAS_MENTION]->(m) MERGE (m)-[:RESOLVED_TO]->(e) MERGE (c)-[:MENTIONS]->(e)", {"chunk": mention["chunkId"], "entity": entity_id, "mention": mention["id"], "job": job_id, "document": source_id, "quote": mention["quote"], "start": mention["startOffset"], "end": mention["endOffset"], "source_spans": json.dumps(mention["sourceSpans"]), "status": mention["sourceSpanStatus"], "ambiguous": mention["sourceSpanStatus"] == "multiple_occurrences", "method": PROCESS["method"], "verified": False})
    for record_assertion in assertions:
        subject_id = entity_ids[record_assertion["subject"]][0]
        object_id = entity_ids[record_assertion["object"]][0]
        graph.query("MATCH (c:Chunk {id:$chunk}),(s:Entity {id:$subject}),(o:Entity {id:$object}) MERGE (a:Assertion {id:$id}) SET a.jobId=$job,a.documentId=$document,a.predicate=$predicate,a.quote=$quote,a.conditions=$conditions,a.polarity=$polarity,a.startOffset=$start,a.endOffset=$end,a.sourceSpans=$source_spans,a.sourceSpanStatus=$status,a.extractionMethod=$method,a.llmVerified=$verified,a.active=false MERGE (a)-[:SUPPORTED_BY]->(c) MERGE (a)-[:SUBJECT]->(s) MERGE (a)-[:OBJECT]->(o)", {"chunk": record_assertion["chunkId"], "id": record_assertion["id"], "job": job_id, "document": source_id, "predicate": record_assertion["predicate"], "quote": record_assertion["quote"], "conditions": json.dumps(record_assertion["conditions"]), "polarity": record_assertion["polarity"], "start": record_assertion["startOffset"], "end": record_assertion["endOffset"], "source_spans": json.dumps(record_assertion["sourceSpans"]), "status": record_assertion["sourceSpanStatus"], "method": PROCESS["method"], "verified": False, "subject": subject_id, "object": object_id})
        graph.query("MATCH (s:Entity {id:$subject}),(o:Entity {id:$object}) MERGE (s)-[r:RELATES {assertionId:$id}]->(o) SET r.predicate=$predicate,r.jobId=$job,r.sourceId=$source,r.active=false", {"id": record_assertion["id"], "subject": subject_id, "object": object_id, "predicate": record_assertion["predicate"], "job": job_id, "source": source_id})

    normalize = {"text": doc_text, "metadata": {"synthetic": True, "authors": authors, "processedAt": processed_at, "stage": "benchmark"}, "blocks": [], "normalization": {"method": "benchmark_corpus", "steps": ["fact_lines"]}}
    with connection() as conn:
        conn.execute("INSERT INTO ingestion_sources(id,filename,original_path,project_id) VALUES(%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET filename=excluded.filename,original_path=excluded.original_path", (source_id, SLUG + ".md", str(original), project_id))
        conn.execute("INSERT INTO ingestion_jobs(id,source_id,project_id,revision,processing_version,configuration,original_path,status,current_stage) VALUES(%s,%s,%s,%s,%s,%s,%s,'complete','publish') ON CONFLICT(id) DO UPDATE SET status='complete',current_stage='publish',configuration=excluded.configuration", (job_id, source_id, project_id, revision, version, Jsonb(config), str(original)))
        conn.execute("INSERT INTO ingestion_artifacts(job_id,stage,payload,digest) VALUES(%s,'normalize',%s,%s) ON CONFLICT(job_id,stage) DO UPDATE SET payload=excluded.payload,digest=excluded.digest,created_at=now()", (job_id, Jsonb(normalize), fingerprint(normalize)))
        conn.execute("UPDATE ingestion_publications SET active=false WHERE source_id=%s AND job_id<>%s", (source_id, job_id))
        publish_document(payload, conn)
        conn.execute("INSERT INTO ingestion_publications(job_id,source_id,counts,active) VALUES(%s,%s,%s,true) ON CONFLICT(job_id) DO UPDATE SET active=true,counts=excluded.counts,published_at=now()", (job_id, source_id, Jsonb(counts)))

    for label, ids_parameter in (("SourceRevision", [job_id]), ("Section", [section_id for section_id, _, _ in chunk_section]), ("Chunk", [chunk["id"] for chunk in chunks]), ("Mention", [mention["id"] for mention in mentions]), ("Assertion", [a["id"] for a in assertions])):
        graph.query(f"MATCH (n:{label}) WHERE n.documentId=$source OR n.sourceId=$source OR n.id=$source SET n.active=CASE WHEN n.id IN $ids THEN true ELSE false END", {"source": source_id, "ids": ids_parameter})
    graph.query("MATCH ()-[r:RELATES]->() WHERE r.sourceId=$source SET r.active=(r.jobId=$job)", {"source": source_id, "job": job_id})
    graph.query("MATCH (e:Entity) WHERE e.id IN $ids SET e.active=true", {"ids": [entry[0] for entry in entity_ids.values()]})
    graph.query("MATCH (d:Document {id:$source}) SET d.active=true,d.activeJobId=$job,d.title=$title,d.extractionQuality=$quality,d.sourceCoverage=$coverage", {"source": source_id, "job": job_id, "title": job_title, "quality": json.dumps(quality), "coverage": json.dumps({"sourceCoverage": quality["sourceCoverage"]})})
    graph.query("MATCH (r:SourceRevision {id:$job}) SET r.graphComplete=true", {"job": job_id})
    if project_id:
        with connection() as conn:
            for mode in ("network", "grouped"):
                conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("project-layout:" + project_id + mode,))
                root = conn.execute("SELECT x,y FROM project_layouts WHERE project_id=%s AND mode=%s AND node_id=%s", (project_id, mode, source_id)).fetchone()
                count = conn.execute("SELECT count(*) AS n FROM project_layouts WHERE project_id=%s AND mode=%s AND payload->>'type'='document'", (project_id, mode)).fetchone()["n"]
                angle = count * math.pi * (3 - math.sqrt(5))
                radius = 1200 * math.sqrt(count)
                location = (root["x"], root["y"]) if root else (radius * math.cos(angle), radius * math.sin(angle))

                def put(identifier, kind, px, py, label, **metadata):
                    layout_record = {"id": identifier, "type": kind, "label": label[:100], "preview": label[:180], "jobId": job_id, **metadata}
                    conn.execute("INSERT INTO project_layouts(project_id,mode,node_id,x,y,payload) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(project_id,mode,node_id) DO UPDATE SET payload=excluded.payload", (project_id, mode, identifier, px, py, Jsonb(layout_record)))

                put(source_id, "document", location[0], location[1], job_title, documentId=source_id)
                section_count = len(chunk_section)
                for position, (section_id, ordinal, title) in enumerate(chunk_section):
                    if mode == "grouped":
                        sx, sy = location[0] + (position - section_count / 2) * 130, location[1] + 150
                    else:
                        spread = math.tau * position / max(1, section_count)
                        sx, sy = location[0] + 250 * math.cos(spread), location[1] + 250 * math.sin(spread)
                    put(section_id, "section", sx, sy, title, documentId=source_id, sectionId=section_id)
                    cx, cy = sx + 60 * math.cos(math.tau * position / max(1, section_count)), sy + 60
                    put(chunks[position]["id"], "chunk", cx, cy, chunks[position]["text"][:100], documentId=source_id, sectionId=section_id, chunkId=chunks[position]["id"])
                    mentioned = sorted({mention["key"] for mention in mentions if mention["chunkId"] == chunks[position]["id"]})
                    for mention_index, key in enumerate(mentioned, 1):
                        entity_id, entity = entity_ids[key]
                        spread_b = math.tau * mention_index / max(1, len(mentioned))
                        put(entity_id, "entity", cx + 60 * math.cos(spread_b), cy + 60 * math.sin(spread_b), entity[1][1], entityType=entity[1][0])
            for mention in mentions:
                entity_id, _ = entity_ids[mention["key"]]
                conn.execute("INSERT INTO ingestion_resolution_decisions(id,job_id,mention_id,canonical_id,decision,rationale,votes) VALUES(%s,%s,%s,%s,'same',%s,%s) ON CONFLICT(id) DO UPDATE SET canonical_id=excluded.canonical_id,decision=excluded.decision,rationale=excluded.rationale WHERE NOT ingestion_resolution_decisions.reverted", ("resolution:" + fingerprint([job_id, mention["id"]]), job_id, mention["id"], entity_id, "Deterministic benchmark resolution: the mention maps to a single authored entity.", "[]"))

    result = {
        "sourceId": source_id, "jobId": job_id, "revision": revision, "processingVersion": version,
        "graph": graph_name, "path": str(original), "counts": counts, "project": project_id or "workspace",
        "records": len(records), "factLines": fact_lines,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
