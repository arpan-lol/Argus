import argparse
import json
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


TITLE = "Synthetic fixture: MOF-BP-1 and bisphenol A"
PARAGRAPHS = [
    "Synthetic fixture prepared for Argus retrieval testing without the ingestion pipeline. MOF-BP-1 adsorbed 91 percent of bisphenol A from water within two hours at pH 6.5 and 25 degrees Celsius. Activated carbon adsorbed a comparable share of bisphenol A under identical conditions in this same fixture.",
    "All statements in this document were authored for testing and were not measured in any laboratory. Hydrothermal synthesis did not change the adsorption capacity of MOF-BP-1 in this authored account, and no real publication supports this fixture.",
]
ENTITIES = [
    {"key": "mof", "name": "MOF-BP-1", "type": "Product", "description": "Synthetic fixture placeholder material used for retrieval testing."},
    {"key": "bpa", "name": "bisphenol A", "type": "Concept", "description": "Synthetic fixture placeholder chemical used for retrieval testing."},
    {"key": "carb", "name": "Activated carbon", "type": "Product", "description": "Synthetic fixture comparator material used for retrieval testing."},
    {"key": "hydr", "name": "Hydrothermal synthesis", "type": "Method", "description": "Synthetic fixture preparation step used for retrieval testing."},
]
ASSERTIONS = [
    {"subject": "mof", "predicate": "adsorbs", "object": "bpa", "quote": "MOF-BP-1 adsorbed 91 percent of bisphenol A from water within two hours at pH 6.5 and 25 degrees Celsius", "conditions": ["two hour contact", "pH 6.5", "25 degrees Celsius"], "polarity": "affirmed"},
    {"subject": "carb", "predicate": "adsorbs", "object": "bpa", "quote": "Activated carbon adsorbed a comparable share of bisphenol A under identical conditions", "conditions": ["identical fixture conditions"], "polarity": "affirmed"},
    {"subject": "hydr", "predicate": "changes", "object": "mof", "quote": "Hydrothermal synthesis did not change the adsorption capacity of MOF-BP-1 in this authored account", "conditions": ["synthetic fixture text"], "polarity": "negated"},
]
COVERAGE = "Synthetic fixture; complete coverage of the fixture text only, authored without laboratory measurements"
QUALITY = {"fallbackChunks": 0, "quality": "manual_fixture", "warnings": ["This source was published directly by scripts/publish_fixture.py without the ingestion pipeline; entities and assertions were authored by hand."], "sourceCoverage": COVERAGE}
PROCESS = {"method": "manual_fixture", "llmVerified": False, "fallback": False, "spanStatus": "exact", "label": "Authored directly by scripts/publish_fixture.py; no ingestion, parsing or model processing was run."}


def canonical(graph_name, key):
    entity = next(item for item in ENTITIES if item["key"] == key)
    return "entity:" + fingerprint([graph_name, entity["name"].strip().lower(), entity["type"].strip().lower()]), entity


def spans(chunk, quote):
    cursor = 0
    result = []
    while True:
        index = chunk["text"].find(quote, cursor)
        if index < 0:
            break
        result.append({"chunkStart": index, "chunkEnd": index + len(quote), "startOffset": chunk["startOffset"] + index, "endOffset": chunk["startOffset"] + index + len(quote), "offsetUnit": "unicode_code_point"})
        cursor = index + 1
    return result


def stage_file(text):
    fixture_path = settings.data_dir / "fixtures" / "manual-fixture-mof-bpa.md"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(text, encoding="utf-8")
    digest = fingerprint([text])
    original_dir = settings.data_dir / "originals" / digest[:2]
    original_dir.mkdir(parents=True, exist_ok=True)
    original = original_dir / (digest + "-manual-fixture-mof-bpa.md")
    if not original.exists() or original.read_bytes() != fixture_path.read_bytes():
        original.write_bytes(fixture_path.read_bytes())
    return original, digest


def build(text, config):
    revision = fingerprint([text])
    version = fingerprint(config)
    graph_name = semantic_graph_name(config)
    section_id = "section:" + fingerprint([0, len(text), "fixture"])
    boundaries = [(0, len(PARAGRAPHS[0])), (len(PARAGRAPHS[0]) + 1, len(text))]
    chunks = [{"id": "chunk:" + fingerprint([chunk_scope(config), left, right]), "ordinal": ordinal, "text": text[left:right], "startOffset": left, "endOffset": right, "tokenCount": None, "offsetUnit": "unicode_code_point", "blockOrdinals": [ordinal]} for ordinal, (left, right) in enumerate(boundaries, 1)]
    sections = [{"id": section_id, "title": "Fixture text", "ordinal": 1, "startOffset": 0, "endOffset": len(text)}]
    sections_merged = [{**sections[0], "documentId": sections[0]["id"], "locationKind": "source", "sourceLocation": None}]
    mentions = []
    for entity in ENTITIES:
        for chunk in chunks:
            found = spans(chunk, entity["name"])
            if not found:
                continue
            for index, occurrence in enumerate(found, 1):
                mentions.append({"id": "mention:" + fingerprint([chunk["id"], f"{entity['key']}-{index}"]), "chunkId": chunk["id"], "key": entity["key"], "quote": entity["name"], "startOffset": occurrence["startOffset"], "endOffset": occurrence["endOffset"], "sourceSpans": found, "sourceSpanStatus": "multiple_occurrences" if len(found) > 1 else "exact"})
    assertions = []
    for ordinal, assertion in enumerate(ASSERTIONS, 1):
        holder = next(chunk for chunk in chunks if spans(chunk, assertion["quote"]))
        primary = spans(holder, assertion["quote"])[0]
        all_spans = spans(holder, assertion["quote"])
        assertions.append({**assertion, "id": "assertion:" + fingerprint([holder["id"], ordinal, assertion["predicate"], assertion["quote"]]), "chunkId": holder["id"], "startOffset": primary["startOffset"], "endOffset": primary["endOffset"], "sourceSpans": all_spans, "sourceSpanStatus": "exact" if len(all_spans) == 1 else "multiple_occurrences"})
    return revision, version, graph_name, sections_merged, chunks, mentions, assertions


def chunk_scope(config):
    return ["fixture", config.get("semanticGraph"), fingerprint(config)]


def publish(project_id):
    text = " ".join(PARAGRAPHS)
    original, digest = stage_file(text)
    config = processing_config(project_id)
    revision, version, graph_name, sections, chunks, mentions, assertions = build(text, config)
    source_id = "source:" + fingerprint([config.get("projectId") or "workspace", str(original)])
    job_id = "job:" + fingerprint([source_id, revision, version])
    payload_chunks = [{**chunk, "documentId": source_id, "revisionId": revision, "processingVersion": version, "sectionId": sections[0]["id"], "sectionIds": [sections[0]["id"]], "sectionTitle": sections[0]["title"], "sourceUrl": None, "locationKind": "source", "extractionMetadata": PROCESS} for chunk in chunks]
    payload = {
        "id": source_id, "revisionId": revision, "processingVersion": version, "rawPath": str(original), "title": TITLE, "text": text, "textLength": len(text),
        "sections": sections, "chunks": payload_chunks,
        "entities": [{"id": canonical(graph_name, entity["key"])[0], "label": entity["name"], "type": entity["type"], "extractionMethod": PROCESS["method"], "llmVerified": False, "mention_count": sum(1 for mention in mentions if mention["key"] == entity["key"])} for entity in ENTITIES],
        "sourceUrl": None, "offsetUnit": "unicode_codepoint",
        "blocks": [], "normalization": {"method": "manual_fixture", "steps": ["fixture"]},
        "extractionQuality": QUALITY, "warnings": QUALITY["warnings"],
        "extractionBoundary": "This is a synthetic fixture; entities and assertions were authored manually and no model processed the text.",
        "synthetic": True, "fixture": "scripts/publish_fixture.py",
    }
    counts = {"documents": 1, "sections": len(sections), "chunks": len(chunks), "entities": len(ENTITIES), "mentions": len(mentions), "assertions": len(assertions), "graph": graph_name, **QUALITY}
    normalize = {"text": text, "metadata": {"synthetic": True, "authors": [], "stage": "fixture"}, "blocks": [], "normalization": {"method": "manual_fixture", "steps": ["fixture"]}}
    graph = FalkorDB(host=settings.falkor_host, port=settings.falkor_port).select_graph(graph_name)
    for label, property_name in (("Document", "id"), ("SourceRevision", "sourceId"), ("SourceRevision", "id"), ("Section", "id"), ("Section", "documentId"), ("Chunk", "id"), ("Chunk", "documentId"), ("Chunk", "jobId"), ("Entity", "id"), ("Entity", "label"), ("Mention", "id"), ("Mention", "documentId"), ("Assertion", "id"), ("Assertion", "documentId"), ("Assertion", "jobId")):
        try:
            graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.{property_name})")
        except Exception as error:
            if "already" not in str(error).lower() and "exists" not in str(error).lower():
                raise
    graph.query("MERGE (d:Document {id:$id}) SET d.title=$title,d.revisionId=$revision,d.sourceUrl=coalesce(d.sourceUrl,'') MERGE (r:SourceRevision {id:$job}) SET r.sourceId=$id,r.revision=$revision,r.processingVersion=$version,r.active=false MERGE (d)-[:HAS_REVISION]->(r)", {"id": source_id, "job": job_id, "title": TITLE, "revision": revision, "version": version})
    for entity in ENTITIES:
        entity_id, _ = canonical(graph_name, entity["key"])
        graph.query("MERGE (e:Entity {id:$id}) SET e.label=$label,e.type=$type,e.description=$description,e.sourceId=$source", {"id": entity_id, "label": entity["name"], "type": entity["type"], "description": entity["description"], "source": source_id})
    for section in sections:
        graph.query("MATCH (d:Document {id:$document}),(r:SourceRevision {id:$job}) MERGE (s:Section {id:$id}) SET s.documentId=$document,s.jobId=$job,s.title=$title,s.startOffset=$start,s.endOffset=$end,s.active=false MERGE (d)-[:HAS_SECTION]->(s) MERGE (r)-[:HAS_SECTION]->(s)", {"document": source_id, "job": job_id, "id": section["id"], "title": section["title"], "start": section["startOffset"], "end": section["endOffset"]})
    previous = None
    for chunk in chunks:
        graph.query("MATCH (s:Section {id:$section}) MERGE (c:Chunk {id:$id}) SET c.documentId=$document,c.sectionId=$section,c.jobId=$job,c.text=$text,c.ordinal=$ordinal,c.startOffset=$start,c.endOffset=$end,c.extractionMethod=$method,c.llmVerified=$verified,c.extractionFallback=$fallback,c.active=false MERGE (s)-[:HAS_CHUNK]->(c)", {"section": sections[0]["id"], "id": chunk["id"], "document": source_id, "job": job_id, "text": chunk["text"], "ordinal": chunk["ordinal"], "start": chunk["startOffset"], "end": chunk["endOffset"], "method": PROCESS["method"], "verified": False, "fallback": False})
        if previous:
            graph.query("MATCH (a:Chunk {id:$a}),(b:Chunk {id:$b}) MERGE (a)-[:NEXT_CHUNK {id:$relation}]->(b)", {"a": previous, "b": chunk["id"], "relation": fingerprint([previous, chunk["id"]])})
        previous = chunk["id"]
    for mention in mentions:
        entity_id, entity = canonical(graph_name, mention["key"])
        graph.query("MATCH (c:Chunk {id:$chunk}),(e:Entity {id:$entity}) MERGE (m:Mention {id:$mention}) SET m.jobId=$job,m.documentId=$document,m.text=$quote,m.startOffset=$start,m.endOffset=$end,m.sourceSpans=$source_spans,m.sourceSpanStatus=$status,m.sourceSpanAmbiguous=$ambiguous,m.extractionMethod=$method,m.llmVerified=$verified,m.active=false MERGE (c)-[:HAS_MENTION]->(m) MERGE (m)-[:RESOLVED_TO]->(e) MERGE (c)-[:MENTIONS]->(e)", {"chunk": mention["chunkId"], "entity": entity_id, "mention": mention["id"], "job": job_id, "document": source_id, "quote": mention["quote"], "start": mention["startOffset"], "end": mention["endOffset"], "source_spans": json.dumps(mention["sourceSpans"]), "status": mention["sourceSpanStatus"], "ambiguous": mention["sourceSpanStatus"] == "multiple_occurrences", "method": PROCESS["method"], "verified": False})
    for record in assertions:
        graph.query("MATCH (c:Chunk {id:$chunk}),(s:Entity {id:$subject}),(o:Entity {id:$object}) MERGE (a:Assertion {id:$id}) SET a.jobId=$job,a.documentId=$document,a.predicate=$predicate,a.quote=$quote,a.conditions=$conditions,a.polarity=$polarity,a.startOffset=$start,a.endOffset=$end,a.sourceSpans=$source_spans,a.sourceSpanStatus=$status,a.extractionMethod=$method,a.llmVerified=$verified,a.active=false MERGE (a)-[:SUPPORTED_BY]->(c) MERGE (a)-[:SUBJECT]->(s) MERGE (a)-[:OBJECT]->(o)", {"chunk": record["chunkId"], "id": record["id"], "job": job_id, "document": source_id, "predicate": record["predicate"], "quote": record["quote"], "conditions": json.dumps(record["conditions"]), "polarity": record["polarity"], "start": record["startOffset"], "end": record["endOffset"], "source_spans": json.dumps(record["sourceSpans"]), "status": record["sourceSpanStatus"], "method": PROCESS["method"], "verified": False, "subject": canonical(graph_name, record["subject"])[0], "object": canonical(graph_name, record["object"])[0]})
        graph.query("MATCH (s:Entity {id:$subject}),(o:Entity {id:$object}) MERGE (s)-[r:RELATES {assertionId:$id}]->(o) SET r.predicate=$predicate,r.jobId=$job,r.sourceId=$source,r.active=false", {"id": record["id"], "subject": canonical(graph_name, record["subject"])[0], "object": canonical(graph_name, record["object"])[0], "predicate": record["predicate"], "job": job_id, "source": source_id})
    with connection() as conn:
        conn.execute("INSERT INTO ingestion_sources(id,filename,original_path,project_id) VALUES(%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET filename=excluded.filename,original_path=excluded.original_path", (source_id, "manual-fixture-mof-bpa.md", str(original), project_id))
        conn.execute("INSERT INTO ingestion_jobs(id,source_id,project_id,revision,processing_version,configuration,original_path,status,current_stage) VALUES(%s,%s,%s,%s,%s,%s,%s,'complete','publish') ON CONFLICT(id) DO UPDATE SET status='complete',current_stage='publish',configuration=excluded.configuration", (job_id, source_id, project_id, revision, version, Jsonb(config), str(original)))
        conn.execute("INSERT INTO ingestion_artifacts(job_id,stage,payload,digest) VALUES(%s,'normalize',%s,%s) ON CONFLICT(job_id,stage) DO UPDATE SET payload=excluded.payload,digest=excluded.digest,created_at=now()", (job_id, Jsonb(normalize), fingerprint(normalize)))
        conn.execute("UPDATE ingestion_publications SET active=false WHERE source_id=%s AND job_id<>%s", (source_id, job_id))
        publish_document(payload, conn)
        conn.execute("INSERT INTO ingestion_publications(job_id,source_id,counts,active) VALUES(%s,%s,%s,true) ON CONFLICT(job_id) DO UPDATE SET active=true,counts=excluded.counts,published_at=now()", (job_id, source_id, Jsonb(counts)))
    for label, property_name in (("SourceRevision", "sourceId"), ("Section", "documentId"), ("Chunk", "documentId"), ("Mention", "documentId"), ("Assertion", "documentId")):
        graph.query(f"MATCH (n:{label} {{{property_name}:$source}}) SET n.active=CASE WHEN n.jobId=$job OR n.id=$job THEN true ELSE false END", {"source": source_id, "job": job_id})
    graph.query("MATCH (s:Entity)-[r:RELATES]->() WHERE r.sourceId=$source SET r.active=(r.jobId=$job)", {"source": source_id, "job": job_id})
    graph.query("MATCH (e:Entity) WHERE e.id IN $ids SET e.active=true", {"ids": [canonical(graph_name, entity["key"])[0] for entity in ENTITIES]})
    graph.query("MATCH (d:Document {id:$source}) SET d.active=true,d.activeJobId=$job,d.title=$title,d.extractionQuality=$quality,d.sourceCoverage=$coverage", {"source": source_id, "job": job_id, "title": TITLE, "quality": json.dumps(QUALITY), "coverage": json.dumps({"sourceCoverage": COVERAGE})})
    graph.query("MATCH (r:SourceRevision {id:$job}) SET r.graphComplete=true", {"job": job_id})
    return {"sourceId": source_id, "jobId": job_id, "revision": revision, "processingVersion": version, "graph": graph_name, "path": str(original), "counts": counts, "project": project_id or "workspace"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", help="Project id; omit for the workspace scope")
    arguments = parser.parse_args()
    if arguments.project:
        with connection() as conn:
            if not conn.execute("SELECT 1 FROM projects WHERE id=%s", (arguments.project,)).fetchone():
                raise SystemExit("Unknown project id")
    migrate()
    result = publish(arguments.project)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
