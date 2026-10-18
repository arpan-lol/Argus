from app.database import connection
from .config import fingerprint


def publish_code_structure(graph, document, chunks, job, space):
    structure = document.get("codeGraph")
    if not structure:
        return {"entities": {}, "mentions": 0, "assertions": 0}
    entities = {}
    identities = {}
    nodes = []
    mentions = []
    assertions = []
    identifiers = ['entity:' + fingerprint([space, item['name'].strip(), item['type']]) for item in structure['entities']]
    with connection() as conn:
        canonical = {row['id']: row for row in conn.execute('SELECT * FROM ingestion_entities WHERE id=ANY(%s)', (identifiers,)).fetchall()} if identifiers else {}
    for item in structure["entities"]:
        identifier = "entity:" + fingerprint([space, item["name"].strip(), item["type"]])
        identities[item["key"]] = identifier
        row = canonical[identifier]
        nodes.append({"id": identifier, "name": item["name"], "entityType": item["type"], "description": row['description'], 'vector': row['embedding'], 'model': row['embedding_model']})
        published = {"id": identifier, "label": item["name"], "type": item["type"], "extractionMethod": "python_ast", "llmVerified": False, "mentions": []}
        for occurrence in item['occurrences']:
            relevant = [chunk["id"] for chunk in chunks if chunk["startOffset"] < occurrence["end"] and chunk["endOffset"] > occurrence["start"]]
            if not relevant:
                raise ValueError("Code symbol has no source chunk")
            mention_id = "mention:" + fingerprint([job["id"], "python_ast", item["key"], occurrence['start'], occurrence['end']])
            mentions.append({"id": mention_id, "entity": identifier, "chunkIds": relevant, "start": occurrence["start"], "end": occurrence["end"], "text": occurrence["quote"], "type": item["type"], "contextFromFilename": occurrence["contextFromFilename"]})
            published['mentions'].append({"id": mention_id, "chunkId": relevant[0], "startOffset": occurrence["start"], "endOffset": occurrence["end"], "text": occurrence["quote"], "extractionMethod": "python_ast", 'contextFromFilename': occurrence['contextFromFilename']})
        entities[identifier] = published
    for ordinal, item in enumerate(structure["relationships"]):
        relevant = [chunk["id"] for chunk in chunks if chunk["startOffset"] < item["end"] and chunk["endOffset"] > item["start"]]
        if not relevant:
            raise ValueError("Code relationship has no supporting source chunk")
        identifier = "assertion:" + fingerprint([job["id"], "python_ast", ordinal, item])
        assertions.append({"id": identifier, "subject": identities[item["subject"]], "object": identities[item["object"]], "predicate": item["predicate"], "quote": item["quote"], "start": item["start"], "end": item["end"], "chunks": relevant, "resolution": item["resolution"]})
    params = {"job": job["id"], "source": job["source_id"]}
    graph.query("UNWIND $nodes AS item MERGE (e:Entity {id:item.id}) SET e.label=item.name,e.type=item.entityType,e.description=item.description,e.embedding=vecf32(item.vector),e.embeddingModel=item.model,e.extractionMethod='python_ast',e.llmVerified=false", {**params, "nodes": nodes})
    graph.query("UNWIND $items AS item MATCH (e:Entity {id:item.entity}) MERGE (m:Mention {id:item.id}) SET m.jobId=$job,m.documentId=$source,m.text=item.text,m.entityType=item.type,m.startOffset=item.start,m.endOffset=item.end,m.extractionMethod='python_ast',m.contextFromFilename=item.contextFromFilename,m.active=false MERGE (m)-[:RESOLVED_TO]->(e) WITH m,e,item UNWIND item.chunkIds AS chunkId MATCH (c:Chunk {id:chunkId}) MERGE (c)-[:HAS_MENTION]->(m) MERGE (c)-[:MENTIONS]->(e)", {**params, "items": mentions})
    graph.query("UNWIND $items AS item MATCH (s:Entity {id:item.subject}),(o:Entity {id:item.object}) MERGE (a:Assertion {id:item.id}) SET a.jobId=$job,a.documentId=$source,a.predicate=item.predicate,a.quote=item.quote,a.startOffset=item.start,a.endOffset=item.end,a.conditions='[]',a.polarity='affirmed',a.extractionMethod='python_ast',a.resolution=item.resolution,a.llmVerified=false,a.active=false MERGE (a)-[:SUBJECT]->(s) MERGE (a)-[:OBJECT]->(o) MERGE (s)-[r:RELATES {assertionId:item.id}]->(o) SET r.predicate=item.predicate,r.rel_type=item.predicate,r.jobId=$job,r.sourceId=$source,r.extractionMethod='python_ast',r.resolution=item.resolution,r.active=false WITH a,item UNWIND item.chunks AS chunkId MATCH (c:Chunk {id:chunkId}) MERGE (a)-[:SUPPORTED_BY]->(c)", {**params, "items": assertions})
    return {"entities": entities, "mentions": len(mentions), "assertions": len(assertions)}
