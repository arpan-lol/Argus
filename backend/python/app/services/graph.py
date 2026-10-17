import json
import redis
from app.config import settings

client = redis.Redis(host=settings.falkor_host, port=settings.falkor_port, decode_responses=True, socket_connect_timeout=2, socket_timeout=12)


def query(statement, parameters=None, readonly=True):
    prefix = "CYPHER " + " ".join(f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in parameters.items()) + " " if parameters else ""
    result = client.execute_command("GRAPH.RO_QUERY" if readonly else "GRAPH.QUERY", settings.legacy_graph_name, prefix + statement, "TIMEOUT", "10000")
    return result[1] if len(result) > 1 and isinstance(result[1], list) else []


def status():
    try:
        rows = query("MATCH (d:Document) RETURN count(d)")
        chunks = query("MATCH (c:Chunk) RETURN count(c)")
        return {"status": "ready", "name": settings.legacy_graph_name, "indexedDocuments": rows[0][0], "indexedChunks": chunks[0][0]}
    except Exception as error:
        return {"status": "unavailable", "name": settings.legacy_graph_name, "indexedDocuments": 0, "indexedChunks": 0, "lastError": str(error)}


def inspect(focus=None, ids=None):
    from app.services import corpus
    focus = focus or {}
    if ids:
        selected = [value for identifier in ids if (value := corpus.chunk(identifier))]
    elif focus.get("chunkId"):
        selected = [value] if (value := corpus.chunk(focus["chunkId"])) else []
    elif focus.get("documentId"):
        doc = corpus.document(focus["documentId"])
        selected = [{"chunk": chunk, "document": doc} for chunk in doc["chunks"] if not focus.get("sectionId") or chunk["sectionId"] == focus["sectionId"]]
    else:
        with __import__('app.database', fromlist=['connection']).connection() as conn:
            selected = [{"chunk": row["payload"], "document": {"id": row["document_id"], "title": row["document_title"]}} for row in conn.execute("SELECT payload,document_id,document_title FROM legacy_chunks LIMIT 100")]
    nodes = {}
    for item in selected[:100]:
        chunk, doc = item["chunk"], item["document"]
        nodes[doc["id"]] = {"id": doc["id"], "label": doc["title"], "type": "document", "documentId": doc["id"]}
        nodes[chunk["sectionId"]] = {"id": chunk["sectionId"], "label": chunk.get("sectionTitle", "Section"), "type": "section", "documentId": doc["id"], "sectionId": chunk["sectionId"]}
        nodes[chunk["id"]] = {**chunk, "type": "chunk", "chunkId": chunk["id"], "label": chunk["text"][:70], "preview": chunk["text"][:180]}
    try:
        rows = query("MATCH (a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids RETURN a.id,b.id,type(r) LIMIT 2000", {"ids": list(nodes)})
        edges = [{"id": f"{a}|{kind}|{b}", "source": a, "target": b, "type": kind} for a,b,kind in rows]
        return {"nodes": list(nodes.values()), "edges": edges, "focus": focus, "truncated": len(selected)>100, "source": "falkordb", "status": "ready"}
    except Exception:
        return {"nodes": list(nodes.values()), "edges": [], "focus": focus, "truncated": len(selected)>100, "source": "postgres", "status": "graph unavailable"}
