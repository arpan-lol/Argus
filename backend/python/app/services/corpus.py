import gzip
import json
from functools import lru_cache
from psycopg.types.json import Jsonb
from fastapi import HTTPException
from app.database import connection


def catalog():
    with connection() as conn:
        row = conn.execute("SELECT payload FROM catalog_metadata WHERE id='legacy'").fetchone()
        return row["payload"] if row else {"schemaVersion": 2, "collection": "Argus sources", "updatedAt": "", "discovery": {}, "ingestion": {}}


def counts():
    with connection() as conn:
        row = conn.execute("SELECT (SELECT count(*) FROM legacy_documents) AS documents,(SELECT count(*) FROM legacy_chunks) AS chunks,(SELECT count(*) FROM legacy_sections) AS sections").fetchone()
    previous = catalog().get("tableCounts", {})
    return {**row, "entities": previous.get("entities", 0), "entityMentions": previous.get("entityMentions", 0)}


@lru_cache(maxsize=48)
def document(identifier):
    with connection() as conn:
        row = conn.execute("SELECT payload FROM legacy_documents WHERE id=%s", (identifier,)).fetchone()
    if not row:
        raise HTTPException(404, "Document not found")
    return json.loads(gzip.decompress(row["payload"]))


def summaries(limit=24, offset=0):
    with connection() as conn:
        return conn.execute('SELECT d.id,d.title,d.metadata->\'year\' AS year,d.metadata->>\'doi\' AS doi,d.metadata->>\'journal\' AS journal,d.metadata->>\'sourceUrl\' AS "sourceUrl",(SELECT count(*) FROM legacy_sections s WHERE s.document_id=d.id) AS "sectionCount",(SELECT count(*) FROM legacy_chunks c WHERE c.document_id=d.id) AS "chunkCount" FROM legacy_documents d ORDER BY d.id DESC LIMIT %s OFFSET %s', (limit, offset)).fetchall()


def chunk(identifier):
    with connection() as conn:
        row = conn.execute("SELECT payload,document_id FROM legacy_chunks WHERE id=%s", (identifier,)).fetchone()
    return {"chunk": row["payload"], "document": document(row["document_id"])} if row else None


def lexical(query, limit, document_id=None):
    with connection() as conn:
        return conn.execute("SELECT payload,document_id,paradedb.score(id) AS score FROM legacy_chunks WHERE id @@@ paradedb.match('text',%s) AND (%s::text IS NULL OR document_id=%s) ORDER BY score DESC LIMIT %s", (query, document_id, document_id, limit)).fetchall()


def publish_document(payload, transaction=None):
    metadata={key:value for key,value in payload.items() if key not in ("text","chunks","sections")}
    metadata["legacy"]=False
    if transaction is None:
        with connection() as conn:
            return publish_document(payload, conn)
    conn = transaction
    if conn is not None:
        conn.execute("INSERT INTO published_documents(id,title,metadata,payload) VALUES(%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET title=excluded.title,metadata=excluded.metadata,payload=excluded.payload,published_at=now()",(payload["id"],payload["title"],Jsonb(metadata),gzip.compress(json.dumps(payload,ensure_ascii=False).encode())))
        conn.execute("DELETE FROM published_chunks WHERE document_id=%s",(payload["id"],))
        conn.execute("DELETE FROM published_sections WHERE document_id=%s",(payload["id"],))
        for section in payload.get("sections",[]):
            conn.execute("INSERT INTO published_sections(id,document_id,title,start_offset,end_offset,payload) VALUES(%s,%s,%s,%s,%s,%s)",(section["id"],payload["id"],section["title"],section["startOffset"],section["endOffset"],Jsonb(section)))
        for chunk in payload.get("chunks",[]):
            conn.execute("INSERT INTO published_chunks(id,document_id,section_id,start_offset,text,document_title,section_title,payload) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",(chunk["id"],payload["id"],chunk["sectionId"],chunk["startOffset"],chunk["text"],payload["title"],chunk.get("sectionTitle",""),Jsonb(chunk)))
